"""Tests for project scanner."""

import tempfile
from pathlib import Path

from cck.scanner import scan_project


def test_detect_python_project():
    """Detect Python project from pyproject.toml."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (path / "main.py").write_text("print('hello')")

        context = scan_project(path)

        assert context["project_type"] == "python"
        assert "Python" in context["languages"]
        assert "main.py" in context["entry_points"]


def test_detect_node_project():
    """Detect Node.js project from package.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "package.json").write_text('{"name": "test", "scripts": {"build": "tsc"}}')
        (path / "index.js").write_text("console.log('hello')")

        context = scan_project(path)

        assert context["project_type"] == "node"
        assert "JavaScript/TypeScript" in context["languages"]
        assert "npm run build" in context["build_commands"]


def test_find_key_files():
    """Find key files like README and Dockerfile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "README.md").write_text("# Test")
        (path / "Dockerfile").write_text("FROM python:3.12")

        context = scan_project(path)

        key_paths = [kf["path"] for kf in context["key_files"]]
        assert "README.md" in key_paths
        assert "Dockerfile" in key_paths


def test_build_structure():
    """Build directory structure tree."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "src").mkdir()
        (path / "src" / "main.py").write_text("")
        (path / "tests").mkdir()
        (path / "tests" / "test_main.py").write_text("")

        context = scan_project(path)

        assert "src/" in context["structure"]
        assert any("tests/" in line for line in context["structure"])


def test_ignore_venv():
    """Ignore .venv directory in entry point detection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir)
        (path / "pyproject.toml").write_text("[project]\nname = 'test'")
        (path / "main.py").write_text("print('hello')")

        # Create .venv with a main.py that should be ignored
        venv = path / ".venv" / "lib" / "python3" / "site-packages" / "pkg"
        venv.mkdir(parents=True)
        (venv / "main.py").write_text("# should be ignored")

        context = scan_project(path)

        # Only project's main.py should be found
        assert context["entry_points"] == ["main.py"]
