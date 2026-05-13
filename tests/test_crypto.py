"""Tests unitarios para ghbackup.auth.crypto."""

import pytest
from cryptography.exceptions import InvalidTag

from ghbackup.auth.crypto import (
    NONCE_SIZE_BYTES,
    SALT_SIZE_BYTES,
    EncryptedBlob,
    decrypt,
    derive_key,
    encrypt,
)


class TestEncryptDecryptRoundtrip:
    def test_roundtrip_basic(self):
        blob = encrypt(b"hello world", "password123!")
        assert decrypt(blob, "password123!") == b"hello world"

    def test_roundtrip_empty_payload(self):
        blob = encrypt(b"", "password123!")
        assert decrypt(blob, "password123!") == b""

    def test_roundtrip_binary_payload(self):
        data = bytes(range(256))
        blob = encrypt(data, "mi_password_segura")
        assert decrypt(blob, "mi_password_segura") == data

    def test_roundtrip_unicode_password(self):
        blob = encrypt(b"payload", "cóntráseña_ñ_2026!")
        assert decrypt(blob, "cóntráseña_ñ_2026!") == b"payload"

    def test_each_encrypt_produces_unique_ciphertext(self):
        """Dos encripciones del mismo plaintext deben producir ciphertexts distintos (salt/nonce aleatorio)."""
        blob1 = encrypt(b"same", "same_password")
        blob2 = encrypt(b"same", "same_password")
        assert blob1.ciphertext != blob2.ciphertext
        assert blob1.salt != blob2.salt


class TestWrongPassword:
    def test_wrong_password_raises_invalid_tag(self):
        blob = encrypt(b"secret", "correct_password")
        with pytest.raises(InvalidTag):
            decrypt(blob, "wrong_password")

    def test_empty_password_on_decrypt_raises(self):
        blob = encrypt(b"secret", "correct_password")
        with pytest.raises((InvalidTag, ValueError)):
            decrypt(blob, "")

    def test_similar_password_raises(self):
        blob = encrypt(b"secret", "password123")
        with pytest.raises(InvalidTag):
            decrypt(blob, "password124")


class TestTamperingDetection:
    def test_tampered_ciphertext_raises(self):
        blob = encrypt(b"hello", "password")
        tampered_ct = bytes(b ^ 0xFF for b in blob.ciphertext)
        tampered = EncryptedBlob(blob.salt, blob.nonce, tampered_ct)
        with pytest.raises(InvalidTag):
            decrypt(tampered, "password")

    def test_tampered_nonce_raises(self):
        blob = encrypt(b"hello", "password")
        tampered_nonce = bytes(b ^ 0x01 for b in blob.nonce)
        tampered = EncryptedBlob(blob.salt, tampered_nonce, blob.ciphertext)
        with pytest.raises(InvalidTag):
            decrypt(tampered, "password")

    def test_tampered_salt_raises(self):
        """Salt distinto → clave distinta → descifrado falla."""
        blob = encrypt(b"hello", "password")
        tampered_salt = bytes(b ^ 0x01 for b in blob.salt)
        tampered = EncryptedBlob(tampered_salt, blob.nonce, blob.ciphertext)
        with pytest.raises(InvalidTag):
            decrypt(tampered, "password")


class TestSerialization:
    def test_to_bytes_from_bytes_roundtrip(self):
        blob = encrypt(b"test payload", "mypass")
        raw = blob.to_bytes()
        restored = EncryptedBlob.from_bytes(raw)
        assert restored.salt == blob.salt
        assert restored.nonce == blob.nonce
        assert restored.ciphertext == blob.ciphertext

    def test_decrypt_after_serialization(self):
        blob = encrypt(b"roundtrip test", "mypass")
        restored = EncryptedBlob.from_bytes(blob.to_bytes())
        assert decrypt(restored, "mypass") == b"roundtrip test"

    def test_from_bytes_too_short_raises(self):
        with pytest.raises(ValueError, match="corrupto"):
            EncryptedBlob.from_bytes(b"short")

    def test_from_bytes_minimum_valid_length(self):
        """Un blob exactamente del tamaño mínimo no debe lanzar ValueError al parsear."""
        min_size = SALT_SIZE_BYTES + NONCE_SIZE_BYTES + 16
        data = bytes(min_size)
        blob = EncryptedBlob.from_bytes(data)
        assert len(blob.salt) == SALT_SIZE_BYTES
        assert len(blob.nonce) == NONCE_SIZE_BYTES

    def test_to_bytes_length(self):
        blob = encrypt(b"data", "pass")
        raw = blob.to_bytes()
        expected_min = SALT_SIZE_BYTES + NONCE_SIZE_BYTES + 16  # +16 = tag AES-GCM
        assert len(raw) >= expected_min


class TestDeriveKey:
    def test_derive_key_deterministic(self):
        salt = b"0123456789abcdef"
        k1 = derive_key("password", salt)
        k2 = derive_key("password", salt)
        assert k1 == k2

    def test_derive_key_different_salts(self):
        k1 = derive_key("password", b"0123456789abcdef")
        k2 = derive_key("password", b"fedcba9876543210")
        assert k1 != k2

    def test_derive_key_empty_password_raises(self):
        with pytest.raises(ValueError, match="vacía"):
            derive_key("", b"0123456789abcdef")

    def test_derive_key_length(self):
        key = derive_key("password", b"0123456789abcdef")
        assert len(key) == 32  # AES-256
