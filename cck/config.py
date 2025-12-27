"""CCK Configuration management."""

from pathlib import Path
from typing import Dict, Any, Optional
import yaml

DEFAULT_CONFIG = {
    'version': 1,
    'watch': {
        'enabled': False,
        'paths': ['.'],
        'exclude': [
            '.git',
            'node_modules',
            '__pycache__',
            '.venv',
            'venv',
            '.claude/cck_history.sqlite',
        ],
    },
    'history': {
        'enabled': False,
        'db_path': '.claude/cck_history.sqlite',
        'max_entries': 50,
        'track': {
            'file_changes': True,
            'tool_operations': False,  # Requires Claude Code hooks integration
        },
    },
    'reminder': {
        'source': 'auto',  # 'auto' | 'history' | 'file'
        'file_path': '.claude/reminder.md',
        'history_limit': 20,
        'format': 'compact',  # 'compact' | 'detailed'
    },
}

CONFIG_TEMPLATE_MINIMAL = """# CCK Configuration
# See: https://github.com/takawasi/claude-context-keeper

version: 1

reminder:
  source: file
  file_path: .claude/reminder.md
"""

CONFIG_TEMPLATE_CB_STYLE = """# CCK Configuration (CB-style workflow)
# Recommended for long sessions with complex projects
# See: https://github.com/takawasi/claude-context-keeper

version: 1

watch:
  enabled: true
  paths:
    - .  # Monitor entire project
  exclude:
    - .git
    - node_modules
    - __pycache__
    - .venv
    - venv

history:
  enabled: true
  db_path: .claude/cck_history.sqlite
  max_entries: 50
  track:
    file_changes: true

reminder:
  source: history
  history_limit: 20
  format: compact
"""


def find_config_path(project_root: Path) -> Optional[Path]:
    """Find CCK config file in project."""
    candidates = [
        project_root / '.claude' / 'cck.yaml',
        project_root / '.claude' / 'cck.yml',
        project_root / 'cck.yaml',
        project_root / 'cck.yml',
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def load_config(project_root: Path) -> Dict[str, Any]:
    """Load CCK config, falling back to defaults."""
    config_path = find_config_path(project_root)

    if config_path is None:
        return DEFAULT_CONFIG.copy()

    try:
        with open(config_path) as f:
            user_config = yaml.safe_load(f) or {}

        # Merge with defaults
        return deep_merge(DEFAULT_CONFIG, user_config)
    except Exception:
        return DEFAULT_CONFIG.copy()


def deep_merge(base: Dict, override: Dict) -> Dict:
    """Deep merge two dicts, override takes precedence."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def save_config(project_root: Path, config_content: str, in_claude_dir: bool = True) -> Path:
    """Save config file to project."""
    if in_claude_dir:
        config_dir = project_root / '.claude'
        config_dir.mkdir(parents=True, exist_ok=True)
        config_path = config_dir / 'cck.yaml'
    else:
        config_path = project_root / 'cck.yaml'

    config_path.write_text(config_content)
    return config_path
