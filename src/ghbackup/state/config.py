"""Configuración persistente (sin secretos) en config.json."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from ghbackup.state.paths import config_path, ensure_dirs


@dataclass
class Config:
    """Configuración del ejecutable.

    NO contiene el token. El PAT vive cifrado en vault.enc.
    """

    source_folder: str = ""
    repo_owner: str = ""
    repo_name: str = ""
    branch: str = ""
    repo_full_name: str = ""  # owner/repo
    repo_html_url: str = ""
    github_login: str = ""  # último login validado
    created_at_utc: str = ""
    updated_at_utc: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def exists() -> bool:
    return config_path().exists()


def load() -> Config:
    """Lee config.json. Si no existe, devuelve un Config vacío."""
    path = config_path()
    if not path.exists():
        return Config()
    data = json.loads(path.read_text(encoding="utf-8"))
    return Config(**{k: v for k, v in data.items() if k in Config.__dataclass_fields__})


def save(cfg: Config) -> None:
    ensure_dirs()
    tmp = config_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(config_path())


def reset() -> None:
    """Borra el config.json (usado en `config reset`)."""
    p = config_path()
    if p.exists():
        p.unlink()
