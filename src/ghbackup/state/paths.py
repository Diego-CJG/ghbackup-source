"""Rutas estándar del estado del ejecutable.

En Windows usamos %APPDATA%\\GitHubBackup\\.
En otros sistemas (por si testeamos en Mac/Linux), usamos ~/.config/GitHubBackup/.
"""
from __future__ import annotations

import os
from pathlib import Path


APP_DIR_NAME = "GitHubBackup"


def app_dir() -> Path:
    """Directorio raíz del estado del ejecutable."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / APP_DIR_NAME
    # Fallback no-Windows (testing)
    return Path.home() / ".config" / APP_DIR_NAME


def config_path() -> Path:
    return app_dir() / "config.json"


def vault_path() -> Path:
    return app_dir() / "vault.enc"


def cache_path() -> Path:
    return app_dir() / "cache.sqlite"


def deletion_manifest_path() -> Path:
    return app_dir() / "deletion_manifest.json"


def logs_dir() -> Path:
    return app_dir() / "logs"


def operations_jsonl_path() -> Path:
    return logs_dir() / "operations.jsonl"


def operations_md_path() -> Path:
    return logs_dir() / "operations.md"


def recovery_codes_path() -> Path:
    return app_dir() / "recovery_codes.json"

def ensure_dirs() -> None:
    """Crea el árbol de directorios si no existe."""
    app_dir().mkdir(parents=True, exist_ok=True)
    logs_dir().mkdir(parents=True, exist_ok=True)
