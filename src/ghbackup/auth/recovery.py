"""Recovery codes para recuperacion de acceso cuando se olvida la master password.

Politica:
- 8 codigos de un solo uso generados durante el setup.
- Formato: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (5 grupos de 5 chars).
- Charset sin ambiguos: A-Z2-9 (sin 0, 1, I, O para evitar confusion visual).
- Almacenamiento: solo SHA-256 de cada codigo, nunca el texto plano.
- Al usar un codigo: se marca como usado (no puede reutilizarse).
- Efecto: borra vault.enc y lockout.json, guia al usuario a `ghbackup setup`.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from ghbackup.state.paths import recovery_codes_path


CODE_COUNT = 8
GROUP_SIZE = 5
GROUP_COUNT = 5
# 32 chars sin 0, 1, I, O para evitar confusion al leer/tipear
CHARSET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_codes() -> list[str]:
    """Genera CODE_COUNT recovery codes nuevos con formato XXXXX-XXXXX-XXXXX-XXXXX-XXXXX."""
    codes = []
    for _ in range(CODE_COUNT):
        groups = [
            "".join(secrets.choice(CHARSET) for _ in range(GROUP_SIZE))
            for _ in range(GROUP_COUNT)
        ]
        codes.append("-".join(groups))
    return codes


def normalize(code: str) -> str:
    """Normaliza un codigo: uppercase, elimina guiones y espacios."""
    return code.upper().replace("-", "").replace(" ", "")


def _hash(normalized: str) -> str:
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def save_codes(codes: list[str]) -> None:
    """Guarda los hashes SHA-256 de los codigos. El texto plano no se persiste."""
    entries = [{"hash": _hash(normalize(c)), "used": False} for c in codes]
    path = recovery_codes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"codes": entries}, indent=2), encoding="utf-8")


def validate_and_consume(code: str) -> bool:
    """Valida un codigo y lo marca como usado si es correcto.

    Devuelve True si el codigo era valido y no habia sido usado.
    Devuelve False si es invalido o ya fue usado.
    """
    path = recovery_codes_path()
    if not path.exists():
        return False
    data = json.loads(path.read_text(encoding="utf-8"))
    normalized = normalize(code)
    code_hash = _hash(normalized)

    for entry in data["codes"]:
        if entry["hash"] == code_hash and not entry["used"]:
            entry["used"] = True
            path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return True
    return False


def remaining_count() -> int:
    """Cuantos codigos validos (no usados) quedan."""
    path = recovery_codes_path()
    if not path.exists():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    return sum(1 for e in data["codes"] if not e["used"])


def codes_exist() -> bool:
    """True si existe el archivo de recovery codes."""
    return recovery_codes_path().exists()


def delete_codes() -> None:
    """Elimina el archivo de recovery codes. Usado en config reset."""
    path = recovery_codes_path()
    if path.exists():
        path.unlink()
