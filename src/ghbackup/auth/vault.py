"""Vault del PAT: lectura/escritura del archivo cifrado en %APPDATA%.

El archivo vault.enc contiene únicamente el PAT cifrado con AES-GCM,
con el salt y nonce embebidos. Nunca persiste la master password.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidTag

from ghbackup.auth import crypto
from ghbackup.state.paths import vault_path


class VaultError(Exception):
    """Error genérico de operaciones sobre el vault."""


class InvalidMasterPassword(VaultError):
    """Master password incorrecta (o vault corrupto)."""


def vault_exists() -> bool:
    return vault_path().exists()


def write_token(token: str, master_password: str) -> None:
    """Cifra el token con la master password y lo guarda en disco."""
    if not token:
        raise VaultError("Token vacío")
    if not master_password:
        raise VaultError("Master password vacía")
    blob = crypto.encrypt(token.encode("utf-8"), master_password)
    path = vault_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(blob.to_bytes())
    tmp.replace(path)


def read_token(master_password: str) -> str:
    """Descifra y devuelve el token. Lanza InvalidMasterPassword si la pass es errónea."""
    path = vault_path()
    if not path.exists():
        raise VaultError("No existe vault.enc. Corré `ghbackup setup` primero.")
    blob = crypto.EncryptedBlob.from_bytes(path.read_bytes())
    try:
        plaintext = crypto.decrypt(blob, master_password)
    except InvalidTag as exc:
        raise InvalidMasterPassword("Master password incorrecta o vault corrupto.") from exc
    return plaintext.decode("utf-8")


def rotate_token(new_token: str, master_password: str) -> None:
    """Reemplaza el token preservando la misma master password."""
    write_token(new_token, master_password)


def delete_vault() -> None:
    """Elimina el vault. Usado en `config reset`. La operación es irreversible."""
    path = vault_path()
    if path.exists():
        path.unlink()
