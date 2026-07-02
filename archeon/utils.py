"""Small shared utilities for Archeon."""

from pathlib import Path


def project_root() -> Path:
    """Return the repository root for this checkout."""
    return Path(__file__).resolve().parents[1]


def format_path(path: Path) -> str:
    """Return a readable path for CLI output."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
