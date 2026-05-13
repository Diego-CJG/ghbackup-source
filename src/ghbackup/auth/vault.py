"""Vault del PAT: lectura/escritura del archivo cifrado en %APPDATA%.

El archivo vault.enc contiene unicamente el PAT cifrado con AES-GCM,
con el salt y nonce embebidos. Nunca persiste la master password.

Seguridad adicional:
- Rate limiting: maximo 5 intentos fallidos -> lockout 60 segundos (via lockout.py).
- Deteccion de vault corrupto: distingue archivo corrupto de password incorrecta.
"""

from __future__ import annotations

from cryptography.exceptions import InvalidTag

from ghbackup.auth import crypto
from ghbackup.auth.lockout import (
    check_lockout,
    record_failure,
    record_success,
)
from ghbackup.state.paths import vault_path


class VaultError(Exception):
    """Error generico de operaciones sobre el vault."""


class InvalidMasterPassword(VaultError):
    """Master password incorrecta."""


class VaultCorrupted(VaultError):
    """El archivo vault.enc esta danado o fue manipulado.

    Solucion: correr `ghbackup config reset` y luego `ghbackup setup`.
    """


def vault_exists() -> bool:
    return vault_path().exists()


def check_vault_integrity() -> None:
    """Verifica que el vault existe y tiene un tamano minimo valido.

    Lanza VaultCorrupted si el archivo esta truncado o danado estructuralmente.
    No verifica el contenido cifrado (eso requiere la master password).
    """
    path = vault_path()
    if not path.exists():
        raise VaultError("No existe vault.enc. Corre `ghbackup setup` primero.")
    min_size = crypto.SALT_SIZE_BYTES + crypto.NONCE_SIZE_BYTES + 16  # tag AES-GCM
    size = path.stat().st_size
    if size < min_size:
        raise VaultCorrupted(
            f"El archivo vault.enc esta corrupto (tamano {size}B < minimo {min_size}B). "
            "Corre `ghbackup config reset` para empezar de nuevo."
        )


def write_token(token: str, master_password: str) -> None:
    """Cifra el token con la master password y lo guarda en disco."""
    if not token:
        raise VaultError("Token vacio")
    if not master_password:
        raise VaultError("Master password vacia")
    blob = crypto.encrypt(token.encode("utf-8"), master_password)
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob.to_bytes())
    tmp.replace(path)
    record_success()


def read_token(master_password: str) -> str:
    """Descifra y devuelve el token.

    Lanza:
    - VaultError: si no existe vault.enc.
    - VaultCorrupted: si el archivo esta estructuralmente danado.
    - LockoutError: si hay demasiados intentos fallidos recientes.
    - InvalidMasterPassword: si la password es incorrecta.
    """
    check_lockout()
    check_vault_integrity()

    raw = vault_path().read_bytes()
    try:
        blob = crypto.EncryptedBlob.from_bytes(raw)
    except ValueError as exc:
        raise VaultCorrupted(
            "El archivo vault.enc esta corrupto y no puede parsearse. "
            "Corre `ghbackup config reset` para empezar de nuevo."
        ) from exc

    try:
        plaintext = crypto.decrypt(blob, master_password)
    except InvalidTag as exc:
        record_failure()
        raise InvalidMasterPassword("Master password incorrecta.") from exc

    record_success()
    return plaintext.decode("utf-8")


def rotate_token(new_token: str, master_password: str) -> None:
    """Reemplaza el token verificando primero la master password actual."""
    read_token(master_password)
    write_token(new_token, master_password)


def delete_vault() -> None:
    """Elimina el vault. Usado en `config reset`. La operacion es irreversible."""
    path = vault_path()
    if path.exists():
        path.unlink()
