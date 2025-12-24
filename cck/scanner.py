"""Project scanner - Extract context from codebase."""

from pathlib import Path
from typing import Dict, List, Any
import json
import tomllib


def scan_project(path: Path) -> Dict[str, Any]:
    """Scan project directory and extract context.

    Returns dict with:
        - project_type: python/node/go/rust/unknown
        - languages: list of detected languages
        - entry_points: main files
        - test_patterns: test file patterns
        - build_commands: detected build/test commands
        - structure: directory tree (key folders)
        - key_files: important files with purposes
        - conventions: detected naming/style conventions
    """
    context = {
        'project_name': path.name,
        'project_type': 'unknown',
        'languages': [],
        'entry_points': [],
        'test_patterns': [],
        'build_commands': [],
        'structure': [],
        'key_files': [],
        'conventions': [],
    }

    # Detect project type and languages
    _detect_project_type(path, context)

    # Find entry points
    _find_entry_points(path, context)

    # Find test patterns
    _find_test_patterns(path, context)

    # Extract build commands
    _extract_build_commands(path, context)

    # Build directory structure
    _build_structure(path, context)

    # Find key files
    _find_key_files(path, context)

    # Detect conventions
    _detect_conventions(path, context)

    return context


def _detect_project_type(path: Path, context: Dict):
    """Detect project type from config files."""
    type_indicators = {
        'pyproject.toml': ('python', 'Python'),
        'setup.py': ('python', 'Python'),
        'requirements.txt': ('python', 'Python'),
        'package.json': ('node', 'JavaScript/TypeScript'),
        'go.mod': ('go', 'Go'),
        'Cargo.toml': ('rust', 'Rust'),
        'composer.json': ('php', 'PHP'),
        'Gemfile': ('ruby', 'Ruby'),
    }

    for file, (ptype, lang) in type_indicators.items():
        if (path / file).exists():
            context['project_type'] = ptype
            if lang not in context['languages']:
                context['languages'].append(lang)

    # Check for TypeScript
    if (path / 'tsconfig.json').exists():
        if 'TypeScript' not in context['languages']:
            context['languages'].append('TypeScript')


def _find_entry_points(path: Path, context: Dict):
    """Find main entry point files."""
    ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.tox', 'dist', 'build', 'site-packages'}

    entry_patterns = {
        'python': ['main.py', 'app.py', 'cli.py', '__main__.py', 'run.py'],
        'node': ['index.js', 'index.ts', 'main.js', 'main.ts', 'app.js', 'app.ts', 'server.js', 'server.ts'],
        'go': ['main.go', 'cmd/main.go'],
        'rust': ['src/main.rs', 'src/lib.rs'],
    }

    patterns = entry_patterns.get(context['project_type'], [])

    for pattern in patterns:
        candidates = list(path.rglob(pattern))
        for candidate in candidates[:3]:  # Limit to 3
            # Skip ignored directories
            if any(ignored in candidate.parts for ignored in ignore_dirs):
                continue
            rel_path = candidate.relative_to(path)
            if str(rel_path) not in context['entry_points']:
                context['entry_points'].append(str(rel_path))


def _find_test_patterns(path: Path, context: Dict):
    """Detect test file patterns."""
    test_patterns = {
        'python': ['test_*.py', '*_test.py', 'tests/*.py'],
        'node': ['*.test.js', '*.test.ts', '*.spec.js', '*.spec.ts', '__tests__/*.js'],
        'go': ['*_test.go'],
        'rust': ['tests/*.rs'],
    }

    patterns = test_patterns.get(context['project_type'], [])

    for pattern in patterns:
        if list(path.rglob(pattern)):
            if pattern not in context['test_patterns']:
                context['test_patterns'].append(pattern)


def _extract_build_commands(path: Path, context: Dict):
    """Extract build/test commands from config files."""
    # Python: pyproject.toml
    pyproject = path / 'pyproject.toml'
    if pyproject.exists():
        try:
            with open(pyproject, 'rb') as f:
                data = tomllib.load(f)
            scripts = data.get('project', {}).get('scripts', {})
            for name in scripts:
                context['build_commands'].append(f"{name} (pyproject.toml)")

            # Common Python commands
            context['build_commands'].extend([
                'pip install -e .',
                'pytest',
            ])
        except Exception:
            pass

    # Node: package.json
    package_json = path / 'package.json'
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text())
            scripts = data.get('scripts', {})
            for name, cmd in scripts.items():
                context['build_commands'].append(f"npm run {name}")
        except Exception:
            pass

    # Makefile
    makefile = path / 'Makefile'
    if makefile.exists():
        try:
            content = makefile.read_text()
            for line in content.split('\n'):
                if line and not line.startswith('\t') and ':' in line:
                    target = line.split(':')[0].strip()
                    if target and not target.startswith('.'):
                        context['build_commands'].append(f"make {target}")
        except Exception:
            pass


def _build_structure(path: Path, context: Dict, max_depth: int = 2):
    """Build directory structure tree."""
    ignore = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', '.tox', 'dist', 'build', '.pytest_cache'}

    def _tree(p: Path, depth: int = 0) -> List[str]:
        if depth > max_depth:
            return []
        lines = []
        try:
            items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name))
            for item in items:
                if item.name in ignore or item.name.startswith('.'):
                    continue
                indent = '  ' * depth
                if item.is_dir():
                    lines.append(f"{indent}{item.name}/")
                    lines.extend(_tree(item, depth + 1))
                else:
                    lines.append(f"{indent}{item.name}")
        except PermissionError:
            pass
        return lines

    context['structure'] = _tree(path)[:50]  # Limit lines


def _find_key_files(path: Path, context: Dict):
    """Find important files and their purposes."""
    key_file_patterns = {
        'README.md': 'Project documentation',
        'CLAUDE.md': 'Claude Code context (existing)',
        'pyproject.toml': 'Python project config',
        'package.json': 'Node.js project config',
        'Makefile': 'Build automation',
        '.env.example': 'Environment variables template',
        'docker-compose.yml': 'Docker services',
        'Dockerfile': 'Container definition',
    }

    for pattern, purpose in key_file_patterns.items():
        if (path / pattern).exists():
            context['key_files'].append({
                'path': pattern,
                'purpose': purpose,
            })


def _detect_conventions(path: Path, context: Dict):
    """Detect naming and style conventions."""
    conventions = []

    # Check for linter configs
    linter_configs = {
        '.pylintrc': 'Pylint',
        'pyproject.toml': 'Ruff/Black (check toml)',
        '.eslintrc.js': 'ESLint',
        '.eslintrc.json': 'ESLint',
        '.prettierrc': 'Prettier',
    }

    for file, linter in linter_configs.items():
        if (path / file).exists():
            conventions.append(f"{linter} configured")

    # Detect naming patterns in Python files
    if context['project_type'] == 'python':
        py_files = list(path.rglob('*.py'))[:20]
        snake_case = 0
        for py_file in py_files:
            if '_' in py_file.stem and py_file.stem.islower():
                snake_case += 1
        if snake_case > len(py_files) * 0.5:
            conventions.append('snake_case file naming')

    context['conventions'] = conventions
