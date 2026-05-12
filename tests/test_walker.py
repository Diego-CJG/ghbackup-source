"""Tests unitarios para ghbackup.scanner.walker e ignore."""
import pytest

from ghbackup.scanner.ignore import build_spec, is_ignored
from ghbackup.scanner.walker import walk


class TestWalker:
    def test_walks_flat_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("hello")
        (tmp_path / "b.txt").write_text("world")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "a.txt" in paths
        assert "b.txt" in paths

    def test_walks_nested_directory(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.txt").write_text("nested")
        (tmp_path / "root.txt").write_text("root")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "root.txt" in paths
        assert "sub/nested.txt" in paths

    def test_empty_directory(self, tmp_path):
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        assert files == []

    def test_scanned_file_fields(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"hello")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        assert len(files) == 1
        sf = files[0]
        assert sf.rel_path == "file.txt"
        assert sf.size_bytes == 5
        assert sf.abs_path == f.resolve()
        assert sf.mtime_utc.endswith("Z")

    def test_ignores_pycache(self, tmp_path):
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "__pycache__" / "mod.pyc").write_bytes(b"x")
        (tmp_path / "normal.txt").write_text("ok")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "normal.txt" in paths
        assert not any("__pycache__" in p for p in paths)

    def test_ignores_git_directory(self, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main")
        (tmp_path / "code.py").write_text("pass")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "code.py" in paths
        assert not any(".git" in p for p in paths)

    def test_ignores_tmp_files(self, tmp_path):
        (tmp_path / "temp.tmp").write_text("temp")
        (tmp_path / "real.txt").write_text("real")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "real.txt" in paths
        assert "temp.tmp" not in paths

    def test_ignores_ds_store(self, tmp_path):
        (tmp_path / ".DS_Store").write_bytes(b"\x00" * 10)
        (tmp_path / "doc.txt").write_text("doc")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "doc.txt" in paths
        assert ".DS_Store" not in paths

    def test_backupignore_excludes_folder(self, tmp_path):
        (tmp_path / ".backupignore").write_text("secret/\n")
        (tmp_path / "secret").mkdir()
        (tmp_path / "secret" / "data.txt").write_text("sensitive")
        (tmp_path / "public.txt").write_text("ok")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "public.txt" in paths
        assert not any("secret" in p for p in paths)

    def test_backupignore_excludes_extension(self, tmp_path):
        (tmp_path / ".backupignore").write_text("*.key\n")
        (tmp_path / "mykey.key").write_text("key_data")
        (tmp_path / "config.json").write_text("{}")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "config.json" in paths
        assert "mykey.key" not in paths

    def test_backupignore_ignores_comments(self, tmp_path):
        (tmp_path / ".backupignore").write_text("# esto es un comentario\nnormal.txt\n")
        (tmp_path / "normal.txt").write_text("excluded")
        (tmp_path / "other.txt").write_text("included")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        paths = {f.rel_path for f in files}
        assert "other.txt" in paths
        assert "normal.txt" not in paths

    def test_mtime_utc_format(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("content")
        spec = build_spec(tmp_path)
        files = list(walk(tmp_path, spec))
        assert len(files) == 1
        mtime = files[0].mtime_utc
        # Debe ser ISO 8601 con Z al final
        assert "T" in mtime
        assert mtime.endswith("Z")


class TestIsIgnored:
    def test_pycache_is_ignored(self, tmp_path):
        spec = build_spec(tmp_path)
        assert is_ignored("__pycache__/module.pyc", spec)

    def test_normal_file_not_ignored(self, tmp_path):
        spec = build_spec(tmp_path)
        assert not is_ignored("document.docx", spec)

    def test_tmp_extension_ignored(self, tmp_path):
        spec = build_spec(tmp_path)
        assert is_ignored("file.tmp", spec)
