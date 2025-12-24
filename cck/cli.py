"""CLI interface for Claude Context Keeper."""

import click
from pathlib import Path
from rich.console import Console

from .scanner import scan_project
from .generator import generate_claude_md

console = Console()


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
@click.option('--append', is_flag=True, help='Append to existing CLAUDE.md')
def sync(path: str, output: str, dry_run: bool, append: bool):
    """Scan codebase and generate/update CLAUDE.md.

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
    content = generate_claude_md(context)

    if dry_run:
        console.print("\n[bold yellow]--- Preview (dry-run) ---[/]\n")
        console.print(content)
        console.print("\n[bold yellow]--- End Preview ---[/]")
        return

    # Write to file
    mode = 'a' if append else 'w'
    existing = ""
    if append and output_path.exists():
        existing = output_path.read_text() + "\n\n---\n\n"

    output_path.write_text(existing + content)
    console.print(f"[bold green]Written:[/] {output_path}")


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
                content = generate_claude_md(context)
                output_path.write_text(content)
                console.print(f"[green]Synced:[/] {output_path}")
                last_hash = current_hash

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("\n[dim]Watch stopped[/dim]")


if __name__ == '__main__':
    main()
