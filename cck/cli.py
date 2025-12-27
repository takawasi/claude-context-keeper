"""CLI interface for Claude Context Keeper."""

import click
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt, Confirm

from .scanner import scan_project
from .generator import generate_claude_md, generate_brief_context, AUTO_START, AUTO_END
from .config import (
    load_config, save_config, find_config_path,
    CONFIG_TEMPLATE_MINIMAL, CONFIG_TEMPLATE_CB_STYLE
)
from .history import (
    init_db, get_combined_history, format_history_compact, format_history_detailed,
    log_file_change, cleanup_old_entries
)

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
@click.option('--minimal', is_flag=True, help='Use minimal config (just reminder.md)')
@click.option('--cb-style', is_flag=True, help='Use CB-style config (file watching + history)')
@click.option('--non-interactive', is_flag=True, help='Skip prompts, use defaults')
def setup(minimal: bool, cb_style: bool, non_interactive: bool):
    """Interactive setup for CCK configuration.

    Creates .claude/cck.yaml with your preferred settings.
    Claude Code can call this to configure monitoring.

    Examples:

        cck setup                # Interactive setup
        cck setup --minimal      # Quick setup with reminder.md only
        cck setup --cb-style     # Full workflow with file watching + history
    """
    project_path = Path.cwd()

    # Check for existing config
    existing = find_config_path(project_path)
    if existing:
        console.print(f"[yellow]Config already exists:[/] {existing}")
        if not non_interactive:
            if not Confirm.ask("Overwrite?", default=False):
                console.print("[dim]Aborted[/dim]")
                return

    # Determine config template
    if minimal:
        config_content = CONFIG_TEMPLATE_MINIMAL
        mode = "minimal"
    elif cb_style:
        config_content = CONFIG_TEMPLATE_CB_STYLE
        mode = "CB-style"
    elif non_interactive:
        config_content = CONFIG_TEMPLATE_MINIMAL
        mode = "minimal (default)"
    else:
        # Interactive mode
        console.print("\n[bold]CCK Setup[/bold]\n")
        console.print("Choose a configuration style:\n")
        console.print("  [1] Minimal - Just reminder.md, you write what to inject")
        console.print("  [2] CB-style - File watching + operation history (recommended)")
        console.print("")

        choice = Prompt.ask("Select", choices=["1", "2"], default="2")

        if choice == "1":
            config_content = CONFIG_TEMPLATE_MINIMAL
            mode = "minimal"
        else:
            config_content = CONFIG_TEMPLATE_CB_STYLE
            mode = "CB-style"

            # Additional CB-style options
            console.print("\n[bold]CB-style options:[/bold]")

            watch_paths = Prompt.ask(
                "Watch paths (comma-separated)",
                default="."
            )
            history_limit = Prompt.ask(
                "History entries to show in reminder",
                default="20"
            )

            # Update config with user choices
            config_content = config_content.replace(
                "    - .  # Monitor entire project",
                "\n".join(f"    - {p.strip()}" for p in watch_paths.split(","))
            )
            config_content = config_content.replace(
                "history_limit: 20",
                f"history_limit: {history_limit}"
            )

    # Save config
    config_path = save_config(project_path, config_content)
    console.print(f"\n[bold green]Config created:[/] {config_path}")
    console.print(f"[dim]Mode: {mode}[/dim]")

    # Next steps
    console.print("\n[bold]Next steps:[/bold]")
    if "CB-style" in mode:
        console.print("  1. Start file watcher: [cyan]cck watch --with-history[/cyan]")
        console.print("  2. Install hook: [cyan]cck hook install --use-history[/cyan]")
    else:
        console.print("  1. Edit reminder: [cyan]cck reminder init[/cyan]")
        console.print("  2. Install hook: [cyan]cck hook install --use-reminder[/cyan]")


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
@click.option('--with-history', is_flag=True,
              help='Record file changes to history database')
def watch(path: str, output: str, interval: int, with_history: bool):
    """Watch for changes and auto-sync CLAUDE.md.

    User-written content outside the auto-generated markers is preserved.

    Examples:

        cck watch                    # Watch current dir
        cck watch ./myproject        # Watch specific dir
        cck watch --interval 60      # Check every 60 seconds
        cck watch --with-history     # Also record changes to history DB
    """
    import time
    import hashlib

    project_path = Path(path).resolve()
    output_path = project_path / output if not Path(output).is_absolute() else Path(output)

    # Load config and init history DB if needed
    config = load_config(project_path)
    db_conn = None
    if with_history:
        db_path = project_path / config['history']['db_path']
        db_conn = init_db(db_path)
        console.print(f"[dim]History DB: {db_path}[/dim]")

    console.print(f"[bold blue]Watching:[/] {project_path}")
    console.print(f"[dim]Interval: {interval}s, Output: {output_path}[/dim]")
    if with_history:
        console.print("[dim]Recording file changes to history[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    # Get exclude patterns from config
    exclude_patterns = set(config['watch']['exclude'])

    def should_ignore(filepath: Path) -> bool:
        """Check if file should be ignored."""
        for pattern in exclude_patterns:
            if pattern in filepath.parts or str(filepath).endswith(pattern):
                return True
        return False

    def get_file_states(p: Path) -> dict:
        """Get dict of file paths to mtimes."""
        states = {}
        try:
            for f in p.rglob('*'):
                if should_ignore(f):
                    continue
                if f.is_file():
                    rel_path = str(f.relative_to(p))
                    states[rel_path] = f.stat().st_mtime
        except Exception:
            pass
        return states

    last_states = {}

    try:
        while True:
            current_states = get_file_states(project_path)

            # Detect changes
            changes = []
            for path_str, mtime in current_states.items():
                if path_str not in last_states:
                    changes.append(('created', path_str))
                elif last_states[path_str] != mtime:
                    changes.append(('modified', path_str))

            for path_str in last_states:
                if path_str not in current_states:
                    changes.append(('deleted', path_str))

            if changes:
                console.print(f"[yellow]Changes detected: {len(changes)} files[/yellow]")

                # Record to history DB
                if db_conn:
                    for event_type, file_path in changes:
                        snippet = None
                        if event_type != 'deleted':
                            try:
                                full_path = project_path / file_path
                                with open(full_path) as f:
                                    snippet = f.read(200)
                            except Exception:
                                pass
                        log_file_change(db_conn, event_type, file_path, snippet)
                        console.print(f"  [dim]{event_type}: {file_path}[/dim]")

                    # Cleanup old entries
                    cleanup_old_entries(db_conn, config['history']['max_entries'])

                # Sync CLAUDE.md
                context = scan_project(project_path)
                new_content = generate_claude_md(context)

                existing_content = ""
                if output_path.exists():
                    existing_content = output_path.read_text()
                final_content = merge_with_existing(existing_content, new_content)

                output_path.write_text(final_content)
                console.print(f"[green]Synced:[/] {output_path}")
                last_states = current_states

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

# Hook script template (history mode - reads from SQLite DB)
HOOK_SCRIPT_HISTORY = '''#!/usr/bin/env python3
"""CCK User Prompt Submit Hook - Reads history from SQLite database.

Generated by: cck hook install --use-history
Docs: https://github.com/takawasi/claude-context-keeper

This hook reads file change history from .claude/cck_history.sqlite
and outputs recent operations for context injection each turn.

Requires: cck watch --with-history running in background
"""
import sys
import sqlite3
from pathlib import Path

def find_project_root() -> Path:
    """Find project root by looking for common markers."""
    cwd = Path.cwd()
    markers = ['.git', 'package.json', 'pyproject.toml', 'Cargo.toml', 'go.mod']
    for p in [cwd] + list(cwd.parents):
        if any((p / m).exists() for m in markers):
            return p
    return cwd

def get_history(root: Path, limit: int = 20) -> str:
    """Read history from SQLite database."""
    db_path = root / '.claude' / 'cck_history.sqlite'

    if not db_path.exists():
        return f"[CCK] {root.name} - No history DB (run: cck watch --with-history)"

    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Get recent file changes
        cursor = conn.execute(
            'SELECT timestamp, event_type, file_path FROM file_changes ORDER BY timestamp DESC LIMIT ?',
            (limit,)
        )
        changes = cursor.fetchall()
        conn.close()

        if not changes:
            return f"[CCK] {root.name} - No recent changes"

        lines = [f"[CCK] {root.name} - Recent changes:"]
        event_map = {'created': '+', 'modified': '~', 'deleted': '-'}
        for row in changes:
            ts = row['timestamp'][11:19]  # HH:MM:SS
            symbol = event_map.get(row['event_type'], '?')
            lines.append(f"  {ts} {symbol} {row['file_path']}")

        return '\\n'.join(lines)

    except Exception as e:
        return f"[CCK] {root.name} - History error: {e}"

if __name__ == "__main__":
    try:
        root = find_project_root()
        history = get_history(root)
        sys.stdout.write(history)
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
@click.option('--use-history', is_flag=True,
              help='Use history mode (reads from SQLite DB)')
def hook_install(is_global: bool, use_reminder: bool, use_history: bool):
    """Install CCK hook for UserPromptSubmit.

    This injects brief project context on every turn, not just session start.

    Three modes available:
    - Default: Auto-detects project type and generates context
    - --use-reminder: Reads from .claude/reminder.md (fully customizable)
    - --use-history: Reads file change history from SQLite (CB-style)

    Examples:

        cck hook install                  # Auto-detect mode
        cck hook install --use-reminder   # Read reminder.md
        cck hook install --use-history    # Read from history DB (CB-style)
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
    if use_history:
        hook_path.write_text(HOOK_SCRIPT_HISTORY)
        mode_desc = "history mode (SQLite DB)"
    elif use_reminder:
        hook_path.write_text(HOOK_SCRIPT_REMINDER)
        mode_desc = "reminder.md mode"
    else:
        hook_path.write_text(HOOK_SCRIPT)
        mode_desc = "auto-detect mode"

    hook_path.chmod(0o755)

    console.print(f"[bold green]Hook installed:[/] {hook_path}")
    console.print(f"[dim]Mode: {mode_desc}[/dim]")

    if use_history:
        console.print("[dim]Start file watcher: cck watch --with-history[/dim]")
    elif use_reminder:
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
