"""CLI interface for Claude Context Keeper."""

import click
from pathlib import Path
from rich.console import Console

from .scanner import scan_project
from .generator import generate_claude_md, AUTO_START, AUTO_END

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


if __name__ == '__main__':
    main()
