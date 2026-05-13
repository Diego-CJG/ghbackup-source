"""Tests unitarios para ghbackup.scanner.hasher."""

import hashlib

import pytest

from ghbackup.scanner.hasher import sha256_of_bytes, sha256_of_file


class TestSha256OfFile:
    def test_known_value(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"hello world")
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert sha256_of_file(f) == expected

    def test_deterministic(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"some content")
        assert sha256_of_file(f) == sha256_of_file(f)

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_bytes(b"")
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_of_file(f) == expected

    def test_different_content_different_hash(self, tmp_path):
        f1 = tmp_path / "a.txt"
        f2 = tmp_path / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")
        assert sha256_of_file(f1) != sha256_of_file(f2)

    def test_binary_file(self, tmp_path):
        data = bytes(range(256)) * 100
        f = tmp_path / "binary.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_of_file(f) == expected

    def test_returns_hex_string(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"test")
        result = sha256_of_file(f)
        assert isinstance(result, str)
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_large_file_streaming(self, tmp_path):
        """Verifica que archivos grandes se lean correctamente en chunks."""
        # 3 MB (mayor que el chunk de 1 MB)
        data = b"x" * (3 * 1024 * 1024)
        f = tmp_path / "large.bin"
        f.write_bytes(data)
        expected = hashlib.sha256(data).hexdigest()
        assert sha256_of_file(f) == expected

    def test_file_not_found_raises(self, tmp_path):
        with pytest.raises((FileNotFoundError, OSError)):
            sha256_of_file(tmp_path / "no_existe.txt")


class TestSha256OfBytes:
    def test_known_value(self):
        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_of_bytes(b"hello") == expected

    def test_empty_bytes(self):
        expected = hashlib.sha256(b"").hexdigest()
        assert sha256_of_bytes(b"") == expected

    def test_returns_hex_string(self):
        result = sha256_of_bytes(b"test")
        assert isinstance(result, str)
        assert len(result) == 64

    def test_consistent_with_file_hash(self, tmp_path):
        """sha256_of_bytes y sha256_of_file deben dar el mismo resultado para el mismo contenido."""
        data = b"consistent check"
        f = tmp_path / "file.txt"
        f.write_bytes(data)
        assert sha256_of_bytes(data) == sha256_of_file(f)
