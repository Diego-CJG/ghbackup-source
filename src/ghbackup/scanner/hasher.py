"""Cálculo de SHA-256 con lectura por chunks (streaming)."""
from __future__ import annotations

import hashlib
from pathlib import Path

CHUNK_SIZE = 1024 * 1024  # 1 MB


def sha256_of_file(path: Path) -> str:
    """Calcula el SHA-256 hex de un archivo. Streaming, sin cargar todo en RAM."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
