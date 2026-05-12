"""Rate limiting de intentos de master password.

Politica:
- Maximo 5 intentos fallidos consecutivos.
- Al alcanzar el limite: lockout de 60 segundos.
- El contador se resetea en el primer intento exitoso.
- Estado persistido en %APPDATA%\\GitHubBackup\\lockout.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from ghbackup.state.paths import app_dir


MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60


def _lockout_path() -> Path:
    return app_dir() / "lockout.json"


def _load() -> dict:
    p = _lockout_path()
    if not p.exists():
        return {"attempts": 0, "locked_until": 0.0}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"attempts": 0, "locked_until": 0.0}


def _save(state: dict) -> None:
    p = _lockout_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def check_lockout() -> None:
    """Lanza LockoutError si el usuario esta en periodo de lockout.

    Debe llamarse ANTES de intentar descifrar el vault.
    """
    state = _load()
    remaining = state.get("locked_until", 0.0) - time.time()
    if remaining > 0:
        raise LockoutError(
            f"Demasiados intentos fallidos. Espera {int(remaining) + 1} segundos antes de reintentar."
        )


def record_failure() -> None:
    """Registra un intento fallido. Si se supera el limite, activa el lockout."""
    state = _load()
    state["attempts"] = state.get("attempts", 0) + 1
    attempts_so_far = state["attempts"]

    if attempts_so_far >= MAX_ATTEMPTS:
        state["locked_until"] = time.time() + LOCKOUT_SECONDS
        state["attempts"] = 0  # reset para el proximo ciclo
        _save(state)
        raise LockoutError(
            f"Demasiados intentos fallidos ({MAX_ATTEMPTS}/{MAX_ATTEMPTS}). "
            f"Espera {LOCKOUT_SECONDS} segundos antes de reintentar."
        )

    remaining = MAX_ATTEMPTS - attempts_so_far
    _save(state)
    # Advertencia cuando quedan 2 intentos o menos
    if remaining <= 2:
        raise AttemptsWarning(
            f"Password incorrecta. Atencion: solo te quedan {remaining} intento(s) "
            f"antes de un bloqueo de {LOCKOUT_SECONDS} segundos."
        )


def record_success() -> None:
    """Resetea el contador tras un intento exitoso."""
    p = _lockout_path()
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def failed_attempts() -> int:
    """Devuelve el numero de intentos fallidos actuales (sin lockout activo)."""
    return _load().get("attempts", 0)


def remaining_attempts() -> int:
    """Devuelve cuantos intentos quedan antes del lockout (0 si ya esta bloqueado)."""
    state = _load()
    if state.get("locked_until", 0.0) > time.time():
        return 0
    return max(0, MAX_ATTEMPTS - state.get("attempts", 0))


class LockoutError(Exception):
    """Se lanza cuando el usuario esta bloqueado por demasiados intentos fallidos."""


class AttemptsWarning(Exception):
    """Advertencia: password incorrecta y quedan pocos intentos antes del lockout."""
