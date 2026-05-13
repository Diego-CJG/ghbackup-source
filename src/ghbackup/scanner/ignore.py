"""Filtros de exclusión: defaults hard-coded + .backupignore opcional."""

from __future__ import annotations

from pathlib import Path

import pathspec

DEFAULT_PATTERNS = [
    "node_modules/",
    "__pycache__/",
    ".git/",
    ".venv/",
    "venv/",
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "*.tmp",
    "*.swp",
    "~$*",
]


def build_spec(source_root: Path) -> pathspec.PathSpec:  # type: ignore[type-arg]
    """Construye un PathSpec combinando defaults + .backupignore del source root."""
    patterns: list[str] = list(DEFAULT_PATTERNS)
    custom = source_root / ".backupignore"
    if custom.exists():
        patterns.extend(
            line.strip()
            for line in custom.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
    return pathspec.PathSpec.from_lines("gitwildmatch", patterns)


def is_ignored(relative_path: str, spec: pathspec.PathSpec) -> bool:  # type: ignore[type-arg]
    """Devuelve True si la ruta relativa (posix) está cubierta por algún patrón."""
    return spec.match_file(relative_path)
