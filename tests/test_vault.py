"""Tests unitarios para ghbackup.auth.vault."""

import pytest

from ghbackup.auth import crypto
from ghbackup.auth.vault import (
    InvalidMasterPassword,
    VaultCorrupted,
    VaultError,
    check_vault_integrity,
    delete_vault,
    read_token,
    vault_exists,
    write_token,
)


@pytest.fixture(autouse=True)
def patch_vault_path(tmp_path, monkeypatch):
    """Redirige vault_path() a un directorio temporal para todos los tests."""
    vault_file = tmp_path / "vault.enc"
    lockout_file = tmp_path / "lockout.json"

    monkeypatch.setattr("ghbackup.auth.vault.vault_path", lambda: vault_file)
    monkeypatch.setattr("ghbackup.state.paths.vault_path", lambda: vault_file)
    # Redirigir app_dir para que lockout.json también vaya a tmp
    monkeypatch.setattr("ghbackup.auth.lockout._lockout_path", lambda: lockout_file)
    monkeypatch.setattr("ghbackup.state.paths.app_dir", lambda: tmp_path)

    return vault_file


class TestWriteReadToken:
    def test_roundtrip(self, tmp_path):
        write_token("ghp_mytoken_abc123", "masterpassword!")
        assert read_token("masterpassword!") == "ghp_mytoken_abc123"

    def test_token_with_special_chars(self, tmp_path):
        token = "ghp_abc123XYZ!@#special"
        write_token(token, "password")
        assert read_token("password") == token

    def test_overwrite_token(self, tmp_path):
        write_token("token_v1", "password")
        write_token("token_v2", "password")
        assert read_token("password") == "token_v2"

    def test_overwrite_with_new_password(self, tmp_path):
        write_token("token", "old_password")
        write_token("token", "new_password")
        assert read_token("new_password") == "token"
        with pytest.raises(InvalidMasterPassword):
            read_token("old_password")

    def test_vault_file_created(self, patch_vault_path):
        write_token("token", "password")
        assert patch_vault_path.exists()

    def test_vault_file_is_binary(self, patch_vault_path):
        write_token("my_token", "password")
        raw = patch_vault_path.read_bytes()
        # No debe ser texto plano
        assert b"my_token" not in raw


class TestInvalidPassword:
    def test_wrong_password_raises(self, tmp_path):
        write_token("token", "correct_password")
        with pytest.raises(InvalidMasterPassword):
            read_token("wrong_password")

    def test_empty_password_raises(self, tmp_path):
        with pytest.raises(VaultError):
            write_token("token", "")

    def test_empty_token_raises(self, tmp_path):
        with pytest.raises(VaultError):
            write_token("", "password")


class TestVaultNotFound:
    def test_no_vault_raises_vault_error(self):
        with pytest.raises(VaultError, match="setup"):
            read_token("anypassword")

    def test_vault_exists_false_when_missing(self):
        assert not vault_exists()

    def test_vault_exists_true_after_write(self, tmp_path):
        write_token("token", "password")
        assert vault_exists()


class TestVaultCorruption:
    def test_truncated_vault_raises_corrupted(self, patch_vault_path):
        patch_vault_path.write_bytes(b"too short")
        with pytest.raises((VaultCorrupted, VaultError)):
            read_token("anypassword")

    def test_random_bytes_raises(self, patch_vault_path):
        # Archivo de tamaño válido pero contenido basura
        min_size = crypto.SALT_SIZE_BYTES + crypto.NONCE_SIZE_BYTES + 16
        patch_vault_path.write_bytes(bytes(min_size + 10))
        with pytest.raises((InvalidMasterPassword, VaultCorrupted)):
            read_token("anypassword")

    def test_check_integrity_missing_file(self):
        with pytest.raises(VaultError):
            check_vault_integrity()

    def test_check_integrity_truncated_file(self, patch_vault_path):
        patch_vault_path.write_bytes(b"short")
        with pytest.raises(VaultCorrupted):
            check_vault_integrity()

    def test_check_integrity_valid_file(self, tmp_path):
        write_token("token", "password")
        # No debe lanzar excepción
        check_vault_integrity()


class TestDeleteVault:
    def test_delete_existing(self, patch_vault_path):
        write_token("token", "password")
        assert patch_vault_path.exists()
        delete_vault()
        assert not patch_vault_path.exists()

    def test_delete_nonexistent_no_error(self):
        # No debe lanzar excepción si no existe
        delete_vault()
