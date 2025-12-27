"""CLI interface for Claude Context Keeper."""

import click
from pathlib import Path
from rich.console import Console

from .scanner import scan_project
from .generator import generate_claude_md, generate_brief_context, AUTO_START, AUTO_END

console = Console()


def merge_with_existing(existing_content: str, new_auto_content: str) -> str:
    """Merge new auto-generated content while preserving user content.

    Preserves:
    - Content before AUTO_START marker (user's header content)
    - Content after AUTO_END marker (user's custom sections)

    Replaces:
    - Content between AUTO_START and AUTO_END markers
    """
    if not existing_content:
        return new_auto_content

    # Find existing markers
    start_idx = existing_content.find(AUTO_START)
    end_idx = existing_content.find(AUTO_END)

    if start_idx == -1 or end_idx == -1:
        # No markers found - this is first run or legacy file
        # Append new content after existing
        return existing_content.rstrip() + "\n\n---\n\n" + new_auto_content

    # Extract user content
    user_before = existing_content[:start_idx].rstrip()
    user_after = existing_content[end_idx + len(AUTO_END):].lstrip()

    # Build merged content
    parts = []
    if user_before:
        parts.append(user_before)
        parts.append("")  # blank line
    parts.append(new_auto_content)
    if user_after:
        parts.append("")  # blank line
        parts.append(user_after)

    return "\n".join(parts)


@click.group()
@click.version_option()
def main():
    """Claude Context Keeper - Auto-generate CLAUDE.md for Claude Code.

    Stop re-explaining your codebase every session.
    """
    pass


@main.command()
@click.argument('path', type=click.Path(exists=True), default='.')
@click.option('--output', '-o', type=click.Path(), default='CLAUDE.md',
              help='Output file path (default: CLAUDE.md)')
@click.option('--dry-run', is_flag=True, help='Preview without writing')
def sync(path: str, output: str, dry_run: bool):
    """Scan codebase and generate/update CLAUDE.md.

    User-written content outside the auto-generated markers is preserved.

    Examples:

        cck sync                    # Scan current dir, output CLAUDE.md
        cck sync ./myproject        # Scan specific dir
        cck sync --dry-run          # Preview only
        cck sync --output ctx.md    # Custom output path
    """
    project_path = Path(path).resolve()
    output_path = project_path / output if not Path(output).is_absolute() else Path(output)

    console.print(f"[bold blue]Scanning:[/] {project_path}")

    # Scan project
    context = scan_project(project_path)

    # Generate CLAUDE.md content
    new_content = generate_claude_md(context)

    # Read existing content if present
    existing_content = ""
    if output_path.exists():
        existing_content = output_path.read_text()

    # Merge: preserve user content outside markers
    final_content = merge_with_existing(existing_content, new_content)

    if dry_run:
        console.print("\n[bold yellow]--- Preview (dry-run) ---[/]\n")
        console.print(final_content)
        console.print("\n[bold yellow]--- End Preview ---[/]")
        return

    output_path.write_text(final_content)
    console.print(f"[bold green]Written:[/] {output_path}")
    if existing_content:
        console.print("[dim]User content outside markers preserved[/dim]")


@main.command()
@click.argument('path', type=click.Path(exists=True), default='.')
def info(path: str):
    """Show detected project info without generating."""
    project_path = Path(path).resolve()

    console.print(f"[bold blue]Analyzing:[/] {project_path}")

    context = scan_project(project_path)

    console.print("\n[bold]Project Type:[/]", context.get('project_type', 'unknown'))
    console.print("[bold]Languages:[/]", ', '.join(context.get('languages', [])))
    console.print("[bold]Entry Points:[/]", ', '.join(context.get('entry_points', [])))
    console.print("[bold]Test Patterns:[/]", ', '.join(context.get('test_patterns', [])))
    console.print("[bold]Build Commands:[/]", ', '.join(context.get('build_commands', [])))


@main.command()
@click.argument('path', type=click.Path(exists=True), default='.')
@click.option('--output', '-o', type=click.Path(), default='CLAUDE.md',
              help='Output file path (default: CLAUDE.md)')
@click.option('--interval', type=int, default=30,
              help='Check interval in seconds (default: 30)')
def watch(path: str, output: str, interval: int):
    """Watch for changes and auto-sync CLAUDE.md.

    User-written content outside the auto-generated markers is preserved.

    Examples:

        cck watch                    # Watch current dir
        cck watch ./myproject        # Watch specific dir
        cck watch --interval 60      # Check every 60 seconds
    """
    import time
    import hashlib

    project_path = Path(path).resolve()
    output_path = project_path / output if not Path(output).is_absolute() else Path(output)

    console.print(f"[bold blue]Watching:[/] {project_path}")
    console.print(f"[dim]Interval: {interval}s, Output: {output_path}[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    def get_dir_hash(p: Path) -> str:
        """Get hash of directory state (file names + mtimes)."""
        items = []
        ignore = {'.git', '__pycache__', 'node_modules', '.venv', 'venv'}
        try:
            for f in sorted(p.rglob('*')):
                if any(i in f.parts for i in ignore):
                    continue
                if f.is_file():
                    items.append(f"{f}:{f.stat().st_mtime}")
        except Exception:
            pass
        return hashlib.md5('|'.join(items).encode()).hexdigest()

    last_hash = ""

    try:
        while True:
            current_hash = get_dir_hash(project_path)

            if current_hash != last_hash:
                console.print(f"[yellow]Change detected, syncing...[/yellow]")
                context = scan_project(project_path)
                new_content = generate_claude_md(context)

                # Preserve user content outside markers
                existing_content = ""
                if output_path.exists():
                    existing_content = output_path.read_text()
                final_content = merge_with_existing(existing_content, new_content)

                output_path.write_text(final_content)
                console.print(f"[green]Synced:[/] {output_path}")
                last_hash = current_hash

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped[/dim]")


# Default reminder template
REMINDER_TEMPLATE = '''# Project Reminders

<!-- CCK:REMINDER -->
<!-- Edit this file to customize per-turn context injection -->

## Key Rules

- [Add your project-specific rules here]

## Current Focus

- [What you're working on]

## Quick Commands

```bash
# [Add frequently used commands]
```
'''

# Hook script template (auto-detect mode)
HOOK_SCRIPT = '''#!/usr/bin/env python3
"""CCK User Prompt Submit Hook - Injects project context every turn.

Generated by: cck hook install
Docs: https://github.com/takawasi/claude-context-keeper
"""
import sys
from pathlib import Path

def find_project_root() -> Path:
    """Find project root by looking for common markers."""
    cwd = Path.cwd()
    markers = ['.git', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod']
    for p in [cwd] + list(cwd.parents):
        if any((p / m).exists() for m in markers):
            return p
    return cwd

def generate_context(root: Path) -> str:
    """Generate brief project context."""
    lines = []

    # Detect project type
    ptype = "unknown"
    langs = []
    if (root / 'package.json').exists():
        ptype = "node"
        langs.append("JavaScript/TypeScript")
    elif (root / 'pyproject.toml').exists() or (root / 'setup.py').exists():
        ptype = "python"
        langs.append("Python")
    elif (root / 'Cargo.toml').exists():
        ptype = "rust"
        langs.append("Rust")
    elif (root / 'go.mod').exists():
        ptype = "go"
        langs.append("Go")

    lines.append(f"[CCK] {root.name} ({ptype})")
    if langs:
        lines.append(f"Languages: {', '.join(langs)}")

    return '\\n'.join(lines)

if __name__ == "__main__":
    try:
        root = find_project_root()
        context = generate_context(root)
        sys.stdout.write(context)
    except Exception:
        pass  # Fail silently to not break Claude Code
'''

# Hook script template (reminder.md mode)
HOOK_SCRIPT_REMINDER = '''#!/usr/bin/env python3
"""CCK User Prompt Submit Hook - Reads reminder.md for per-turn context.

Generated by: cck hook install --use-reminder
Docs: https://github.com/takawasi/claude-context-keeper

This hook reads .claude/reminder.md (or reminder.md) and outputs its content.
Edit the reminder.md file to customize what context is injected each turn.
"""
import sys
from pathlib import Path

def find_project_root() -> Path:
    """Find project root by looking for common markers."""
    cwd = Path.cwd()
    markers = ['.git', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod']
    for p in [cwd] + list(cwd.parents):
        if any((p / m).exists() for m in markers):
            return p
    return cwd

def get_reminder(root: Path) -> str:
    """Read reminder.md content."""
    # Check multiple locations
    candidates = [
        root / '.claude' / 'reminder.md',
        root / 'reminder.md',
    ]

    for path in candidates:
        if path.exists():
            return path.read_text().strip()

    # Fallback: basic project info
    return f"[CCK] {root.name} - No reminder.md found"

if __name__ == "__main__":
    try:
        root = find_project_root()
        reminder = get_reminder(root)
        sys.stdout.write(reminder)
    except Exception:
        pass  # Fail silently to not break Claude Code
'''


@main.group()
def hook():
    """Manage UserPromptSubmit hooks for per-turn context.

    Instead of CLAUDE.md (session-start), hooks inject context every turn.
    """
    pass


@hook.command('install')
@click.option('--global', 'is_global', is_flag=True,
              help='Install to ~/.claude/hooks (applies to all projects)')
@click.option('--use-reminder', is_flag=True,
              help='Use reminder.md mode instead of auto-detect')
def hook_install(is_global: bool, use_reminder: bool):
    """Install CCK hook for UserPromptSubmit.

    This injects brief project context on every turn, not just session start.

    Two modes available:
    - Default: Auto-detects project type and generates context
    - --use-reminder: Reads from .claude/reminder.md (fully customizable)

    Examples:

        cck hook install                  # Auto-detect mode
        cck hook install --use-reminder   # Read reminder.md
        cck hook install --global         # Install to ~/.claude/hooks
    """
    if is_global:
        hooks_dir = Path.home() / '.claude' / 'hooks'
    else:
        hooks_dir = Path.cwd() / '.claude' / 'hooks'

    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / 'user-prompt-submit.py'

    if hook_path.exists():
        console.print(f"[yellow]Hook already exists:[/] {hook_path}")
        console.print("[dim]Use 'cck hook remove' first to reinstall[/dim]")
        return

    # Choose script based on mode
    if use_reminder:
        hook_path.write_text(HOOK_SCRIPT_REMINDER)
        mode_desc = "reminder.md mode"
    else:
        hook_path.write_text(HOOK_SCRIPT)
        mode_desc = "auto-detect mode"

    hook_path.chmod(0o755)

    console.print(f"[bold green]Hook installed:[/] {hook_path}")
    console.print(f"[dim]Mode: {mode_desc}[/dim]")

    if use_reminder:
        console.print("[dim]Create .claude/reminder.md with 'cck reminder init'[/dim]")


@hook.command('status')
@click.option('--global', 'is_global', is_flag=True,
              help='Check ~/.claude/hooks instead of local')
def hook_status(is_global: bool):
    """Show current hook installation status."""
    if is_global:
        hook_path = Path.home() / '.claude' / 'hooks' / 'user-prompt-submit.py'
        location = "Global"
    else:
        hook_path = Path.cwd() / '.claude' / 'hooks' / 'user-prompt-submit.py'
        location = "Local"

    if hook_path.exists():
        console.print(f"[bold green]{location} hook installed:[/] {hook_path}")
        # Check if it's CCK hook
        content = hook_path.read_text()
        if 'CCK' in content:
            console.print("[dim]This is a CCK-generated hook[/dim]")
        else:
            console.print("[yellow]This hook was not generated by CCK[/yellow]")
    else:
        console.print(f"[dim]{location} hook not installed[/dim]")


@hook.command('remove')
@click.option('--global', 'is_global', is_flag=True,
              help='Remove from ~/.claude/hooks instead of local')
def hook_remove(is_global: bool):
    """Remove CCK hook."""
    if is_global:
        hook_path = Path.home() / '.claude' / 'hooks' / 'user-prompt-submit.py'
    else:
        hook_path = Path.cwd() / '.claude' / 'hooks' / 'user-prompt-submit.py'

    if not hook_path.exists():
        console.print("[dim]Hook not installed[/dim]")
        return

    # Safety check
    content = hook_path.read_text()
    if 'CCK' not in content:
        console.print("[yellow]Warning: This hook was not generated by CCK[/yellow]")
        console.print("[yellow]Skipping removal to avoid breaking custom hooks[/yellow]")
        return

    hook_path.unlink()
    console.print(f"[bold green]Hook removed:[/] {hook_path}")


@hook.command('test')
@click.option('--use-reminder', is_flag=True,
              help='Test reminder.md mode instead of auto-detect')
def hook_test(use_reminder: bool):
    """Test hook output (preview what would be injected)."""
    project_path = Path.cwd()

    if use_reminder:
        # Test reminder.md mode
        candidates = [
            project_path / '.claude' / 'reminder.md',
            project_path / 'reminder.md',
        ]
        for path in candidates:
            if path.exists():
                console.print(f"[bold blue]Reminder found:[/] {path}")
                console.print("[bold blue]Content:[/]")
                console.print(path.read_text())
                return
        console.print("[yellow]No reminder.md found[/yellow]")
        console.print("[dim]Create one with: cck reminder init[/dim]")
    else:
        context = scan_project(project_path)
        brief = generate_brief_context(context)
        console.print("[bold blue]Hook output preview (auto-detect):[/]")
        console.print(brief)


@main.group()
def reminder():
    """Manage reminder.md for customizable per-turn context.

    Unlike auto-detect mode, reminder.md lets you write exactly what
    context is injected on every turn.
    """
    pass


@reminder.command('init')
@click.option('--in-claude-dir', is_flag=True, default=True,
              help='Create in .claude/ directory (default)')
@click.option('--in-root', is_flag=True,
              help='Create in project root instead')
def reminder_init(in_claude_dir: bool, in_root: bool):
    """Create a reminder.md template.

    Examples:

        cck reminder init              # Create .claude/reminder.md
        cck reminder init --in-root    # Create reminder.md in project root
    """
    if in_root:
        target_dir = Path.cwd()
    else:
        target_dir = Path.cwd() / '.claude'
        target_dir.mkdir(parents=True, exist_ok=True)

    reminder_path = target_dir / 'reminder.md'

    if reminder_path.exists():
        console.print(f"[yellow]Already exists:[/] {reminder_path}")
        return

    reminder_path.write_text(REMINDER_TEMPLATE)
    console.print(f"[bold green]Created:[/] {reminder_path}")
    console.print("[dim]Edit this file to customize per-turn context[/dim]")
    console.print("[dim]Then install hook with: cck hook install --use-reminder[/dim]")


@reminder.command('show')
def reminder_show():
    """Show current reminder.md content."""
    project_path = Path.cwd()
    candidates = [
        project_path / '.claude' / 'reminder.md',
        project_path / 'reminder.md',
    ]

    for path in candidates:
        if path.exists():
            console.print(f"[bold blue]Found:[/] {path}")
            console.print("")
            console.print(path.read_text())
            return

    console.print("[dim]No reminder.md found[/dim]")
    console.print("[dim]Create one with: cck reminder init[/dim]")


if __name__ == '__main__':
    main()
