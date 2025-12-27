# claude-context-keeper (cck)

Auto-generate and maintain CLAUDE.md for Claude Code.

Stop explaining your codebase every session.

## The Problem

Every Claude Code session starts fresh. You re-explain:
- Project structure
- Build commands
- Coding conventions
- Key files

CLAUDE.md solves this, but writing it manually is tedious.

## The Solution

```bash
cck sync
```

Scans your codebase. Generates CLAUDE.md. Done.

## Installation

```bash
pip install claude-context-keeper
```

## Quick Start

### Option 1: Simple (CLAUDE.md only)
```bash
cck sync                # Generate CLAUDE.md
```

### Option 2: With Per-Turn Context (Recommended)
```bash
cck setup               # Interactive configuration
cck watch --with-history &  # Start file watcher (background)
cck hook install --use-history  # Install per-turn hook
```

## Interactive Setup

Let Claude Code configure CCK for you:

```bash
cck setup               # Interactive mode - asks what you want
cck setup --cb-style    # Skip prompts, use full workflow config
cck setup --minimal     # Skip prompts, use minimal config
```

The setup command creates `.claude/cck.yaml` with your preferences.

### CB-Style Configuration (Recommended)

For long coding sessions, we recommend the CB-style workflow:

```yaml
# .claude/cck.yaml
version: 1

watch:
  enabled: true
  paths:
    - .
  exclude:
    - .git
    - node_modules
    - __pycache__

history:
  enabled: true
  db_path: .claude/cck_history.sqlite
  max_entries: 50

reminder:
  source: history
  history_limit: 20
  format: compact
```

This setup:
1. Watches your project for file changes
2. Records changes to a SQLite database
3. Injects recent file history on every turn

## Usage

### Generate CLAUDE.md

```bash
cck sync                    # Generate in current directory
cck sync ./myproject        # Scan specific directory
cck sync --dry-run          # Preview without writing
cck sync --output ctx.md    # Custom output path
```

User-written content outside markers is preserved:
```markdown
# My custom header (preserved)

<!-- CCK:AUTO-START -->
... auto-generated content ...
<!-- CCK:AUTO-END -->

## My custom section (preserved)
```

### Watch Mode

```bash
cck watch                    # Watch and auto-sync CLAUDE.md
cck watch --with-history     # Also record changes to history DB
cck watch --interval 60      # Check every 60 seconds
```

### Show Project Info

```bash
cck info
```

Output:
```
Project Type: python
Languages: Python
Entry Points: main.py, cli.py
Build Commands: pytest, pip install -e .
```

## Per-Turn Context (UserPromptSubmit Hook)

Want context injected every turn instead of just session start?

### Three Modes

| Mode | Command | Source | Best for |
|------|---------|--------|----------|
| Auto-detect | `cck hook install` | Codebase analysis | Quick setup |
| Reminder.md | `cck hook install --use-reminder` | Your .claude/reminder.md | Custom rules |
| **History (CB-style)** | `cck hook install --use-history` | SQLite DB | Long sessions |

### CB-Style Setup (Recommended)

```bash
# 1. Configure
cck setup --cb-style

# 2. Start file watcher (run in background or separate terminal)
cck watch --with-history &

# 3. Install hook
cck hook install --use-history
```

Every turn, Claude Code will see recent file changes:
```
[CCK] myproject - Recent changes:
  15:23:45 ~ src/main.py
  15:22:30 + src/utils/helper.py
  15:20:12 ~ tests/test_main.py
```

### Reminder.md Mode

For fully custom per-turn context:

```bash
cck reminder init           # Create .claude/reminder.md
cck hook install --use-reminder
```

Edit `.claude/reminder.md` to control exactly what gets injected.

### Hook Commands

```bash
cck hook install                  # Auto-detect mode
cck hook install --use-reminder   # Reminder.md mode
cck hook install --use-history    # History mode (CB-style)
cck hook install --global         # Install to ~/.claude/hooks

cck hook status                   # Check installation
cck hook test                     # Preview output
cck hook remove                   # Remove hook
```

## What It Detects

| Category | Examples |
|----------|----------|
| Project Type | Python, Node.js, Go, Rust, PHP, Ruby |
| Languages | Python, JavaScript, TypeScript, Go, Rust |
| Entry Points | main.py, index.js, main.go, src/main.rs |
| Test Patterns | test_*.py, *.test.js, *_test.go |
| Build Commands | from pyproject.toml, package.json, Makefile |
| Key Files | README.md, Dockerfile, docker-compose.yml |
| Conventions | Linter configs, naming patterns |

## Configuration Reference

### Full Config Example

```yaml
# .claude/cck.yaml
version: 1

watch:
  enabled: true
  paths:
    - src/
    - lib/
  exclude:
    - .git
    - node_modules
    - __pycache__
    - .venv

history:
  enabled: true
  db_path: .claude/cck_history.sqlite
  max_entries: 50
  track:
    file_changes: true

reminder:
  source: history  # 'auto' | 'history' | 'file'
  file_path: .claude/reminder.md
  history_limit: 20
  format: compact  # 'compact' | 'detailed'
```

### Config Locations

CCK looks for config in order:
1. `.claude/cck.yaml`
2. `.claude/cck.yml`
3. `cck.yaml`
4. `cck.yml`

## Design Principles

Built from insights across 300+ Claude Code sessions:

**What works in CLAUDE.md:**
- Structure with clear purpose
- Exact copy-paste commands
- Explicit prohibitions

**What doesn't work:**
- Abstract descriptions
- Outdated commands
- Too much detail

## More Tools

See all dev tools: https://takawasi-social.com/en/

## License

MIT
