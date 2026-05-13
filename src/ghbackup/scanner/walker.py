"""Walker recursivo del source folder con filtros aplicados."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pathspec


@dataclass
class ScannedFile:
    rel_path: str  # ruta relativa al source root, en formato posix
    abs_path: Path
    size_bytes: int
    mtime_utc: str  # ISO 8601


def walk(source_root: Path, ignore_spec: pathspec.PathSpec) -> Iterator[ScannedFile]:  # type: ignore[type-arg]
    """Genera ScannedFile para cada archivo (no carpeta) dentro del source root."""
    source_root = source_root.resolve()
    for dirpath, dirnames, filenames in os.walk(source_root):
        # filtrar subdirectorios ignorados in-place (poda)
        kept_dirs: list[str] = []
        for d in dirnames:
            rel_dir = (
                str(Path(dirpath, d).resolve().relative_to(source_root)).replace("\\", "/") + "/"
            )
            if not ignore_spec.match_file(rel_dir):
                kept_dirs.append(d)
        dirnames[:] = kept_dirs

        for name in filenames:
            abs_p = Path(dirpath) / name
            try:
                rel = str(abs_p.resolve().relative_to(source_root)).replace("\\", "/")
            except ValueError:
                # fuera del root (improbable, pero defensive)
                continue
            if ignore_spec.match_file(rel):
                continue
            try:
                stat = abs_p.stat()
            except OSError:
                continue
            mtime_dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            yield ScannedFile(
                rel_path=rel,
                abs_path=abs_p,
                size_bytes=stat.st_size,
                mtime_utc=mtime_dt.isoformat(timespec="seconds").replace("+00:00", "Z"),
            )
