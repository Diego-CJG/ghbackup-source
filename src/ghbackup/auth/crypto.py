"""Primitivas criptográficas: derivación de clave (PBKDF2) y cifrado AES-GCM.

Política:
- PBKDF2-HMAC-SHA256, 600 000 iteraciones (recomendación OWASP 2023+).
- Salt aleatorio de 16 bytes.
- Nonce aleatorio de 12 bytes por encriptación.
- AES-256-GCM con tag de autenticación de 16 bytes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

KDF_ITERATIONS = 600_000
KEY_SIZE_BYTES = 32  # AES-256
SALT_SIZE_BYTES = 16
NONCE_SIZE_BYTES = 12


def derive_key(password: str, salt: bytes) -> bytes:
    """Deriva una clave AES-256 desde el master password + salt."""
    if not password:
        raise ValueError("master password vacía")
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=KEY_SIZE_BYTES,
        salt=salt,
        iterations=KDF_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


@dataclass(frozen=True)
class EncryptedBlob:
    """Resultado del cifrado: contiene salt + nonce + ciphertext (con tag)."""

    salt: bytes
    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        """Serialización binaria: [salt(16)] [nonce(12)] [ciphertext...]."""
        return self.salt + self.nonce + self.ciphertext

    @classmethod
    def from_bytes(cls, blob: bytes) -> EncryptedBlob:
        if len(blob) < SALT_SIZE_BYTES + NONCE_SIZE_BYTES + 16:
            raise ValueError("blob cifrado corrupto: demasiado corto")
        salt = blob[:SALT_SIZE_BYTES]
        nonce = blob[SALT_SIZE_BYTES : SALT_SIZE_BYTES + NONCE_SIZE_BYTES]
        ciphertext = blob[SALT_SIZE_BYTES + NONCE_SIZE_BYTES :]
        return cls(salt=salt, nonce=nonce, ciphertext=ciphertext)


def encrypt(plaintext: bytes, password: str) -> EncryptedBlob:
    """Cifra un payload con AES-256-GCM derivando la clave desde el password."""
    salt = os.urandom(SALT_SIZE_BYTES)
    nonce = os.urandom(NONCE_SIZE_BYTES)
    key = derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return EncryptedBlob(salt=salt, nonce=nonce, ciphertext=ciphertext)


def decrypt(blob: EncryptedBlob, password: str) -> bytes:
    """Descifra. Lanza InvalidTag si el password es incorrecto o el blob fue manipulado."""
    key = derive_key(password, blob.salt)
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(blob.nonce, blob.ciphertext, associated_data=None)
