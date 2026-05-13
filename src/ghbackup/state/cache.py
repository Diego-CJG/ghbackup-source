"""Cache SQLite de hashes y metadata por archivo.

Tabla `files`:
    path             TEXT PRIMARY KEY  -- ruta relativa al source root (posix)
    sha256           TEXT NOT NULL
    size_bytes       INTEGER NOT NULL
    mtime_utc        TEXT NOT NULL
    last_seen_commit TEXT
    last_push_tag    TEXT
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass

from ghbackup.state.paths import cache_path, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path             TEXT PRIMARY KEY,
    sha256           TEXT NOT NULL,
    size_bytes       INTEGER NOT NULL,
    mtime_utc        TEXT NOT NULL,
    last_seen_commit TEXT,
    last_push_tag    TEXT
);
CREATE INDEX IF NOT EXISTS idx_files_sha ON files(sha256);
"""


@dataclass
class CacheEntry:
    path: str
    sha256: str
    size_bytes: int
    mtime_utc: str
    last_seen_commit: str | None = None
    last_push_tag: str | None = None


def _connect() -> sqlite3.Connection:
    ensure_dirs()
    conn = sqlite3.connect(str(cache_path()))
    conn.executescript(SCHEMA)
    return conn


def get_all() -> dict[str, CacheEntry]:
    """Devuelve un dict path → CacheEntry de todo el cache."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT path, sha256, size_bytes, mtime_utc, last_seen_commit, last_push_tag FROM files"
        ).fetchall()
    return {r[0]: CacheEntry(*r) for r in rows}


def upsert_many(entries: Iterable[CacheEntry]) -> None:
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO files(path, sha256, size_bytes, mtime_utc, last_seen_commit, last_push_tag)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                sha256=excluded.sha256,
                size_bytes=excluded.size_bytes,
                mtime_utc=excluded.mtime_utc,
                last_seen_commit=excluded.last_seen_commit,
                last_push_tag=excluded.last_push_tag
            """,
            [
                (
                    e.path,
                    e.sha256,
                    e.size_bytes,
                    e.mtime_utc,
                    e.last_seen_commit,
                    e.last_push_tag,
                )
                for e in entries
            ],
        )
        conn.commit()


def delete_many(paths: Iterable[str]) -> None:
    with _connect() as conn:
        conn.executemany("DELETE FROM files WHERE path = ?", [(p,) for p in paths])
        conn.commit()


def wipe() -> None:
    """Borra todo el contenido del cache (usado por `verify --rebuild`)."""
    with _connect() as conn:
        conn.execute("DELETE FROM files")
        conn.commit()


def cache_file_exists() -> bool:
    return cache_path().exists()
