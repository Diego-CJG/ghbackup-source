"""Tests unitarios para ghbackup.scanner.diff (compute_delta)."""

import pytest

from ghbackup.scanner.diff import DeltaReport, compute_delta
from ghbackup.scanner.hasher import sha256_of_bytes
from ghbackup.state.cache import CacheEntry


@pytest.fixture(autouse=True)
def patch_cache(monkeypatch):
    """Por defecto, cache vacío. Tests individuales pueden sobreescribir con monkeypatch."""
    monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: {})


def _make_entry(path: str, content: bytes) -> CacheEntry:
    return CacheEntry(
        path=path,
        sha256=sha256_of_bytes(content),
        size_bytes=len(content),
        mtime_utc="2026-01-01T00:00:00Z",
    )


class TestNewFiles:
    def test_single_new_file(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"hello")
        report = compute_delta(tmp_path)
        assert len(report.new) == 1
        assert report.new[0].rel_path == "file.txt"

    def test_multiple_new_files(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"aaa")
        (tmp_path / "b.txt").write_bytes(b"bbb")
        report = compute_delta(tmp_path)
        paths = {c.rel_path for c in report.new}
        assert paths == {"a.txt", "b.txt"}

    def test_new_file_in_subdir(self, tmp_path):
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "nested.txt").write_bytes(b"nested")
        report = compute_delta(tmp_path)
        assert len(report.new) == 1
        assert report.new[0].rel_path == "sub/nested.txt"

    def test_new_file_sha256_matches(self, tmp_path):
        content = b"specific content"
        (tmp_path / "file.txt").write_bytes(content)
        report = compute_delta(tmp_path)
        assert report.new[0].sha256 == sha256_of_bytes(content)

    def test_new_file_size_matches(self, tmp_path):
        content = b"exactly ten!"
        (tmp_path / "file.txt").write_bytes(content)
        report = compute_delta(tmp_path)
        assert report.new[0].size_bytes == len(content)


class TestModifiedFiles:
    def test_modified_file_detected(self, tmp_path, monkeypatch):
        content_new = b"new content"
        (tmp_path / "file.txt").write_bytes(content_new)
        cache = {"file.txt": _make_entry("file.txt", b"old content")}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert len(report.modified) == 1
        assert report.modified[0].rel_path == "file.txt"

    def test_modified_file_has_old_sha(self, tmp_path, monkeypatch):
        old_content = b"old"
        new_content = b"new"
        (tmp_path / "file.txt").write_bytes(new_content)
        cache = {"file.txt": _make_entry("file.txt", old_content)}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.modified[0].old_sha256 == sha256_of_bytes(old_content)
        assert report.modified[0].sha256 == sha256_of_bytes(new_content)


class TestUnchangedFiles:
    def test_unchanged_file_not_in_changes(self, tmp_path, monkeypatch):
        content = b"same content"
        (tmp_path / "file.txt").write_bytes(content)
        cache = {"file.txt": _make_entry("file.txt", content)}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.unchanged_count == 1
        assert not report.has_changes()
        assert report.new == []
        assert report.modified == []

    def test_unchanged_count_multiple(self, tmp_path, monkeypatch):
        for name in ("a.txt", "b.txt", "c.txt"):
            content = name.encode()
            (tmp_path / name).write_bytes(content)
        cache = {n: _make_entry(n, n.encode()) for n in ("a.txt", "b.txt", "c.txt")}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.unchanged_count == 3
        assert not report.has_changes()


class TestDeletedFiles:
    def test_deleted_file_detected(self, tmp_path, monkeypatch):
        cache = {"deleted.txt": _make_entry("deleted.txt", b"content")}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert len(report.deleted) == 1
        assert report.deleted[0].path == "deleted.txt"

    def test_deleted_file_not_in_new(self, tmp_path, monkeypatch):
        cache = {"deleted.txt": _make_entry("deleted.txt", b"content")}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.new == []

    def test_multiple_deleted_files(self, tmp_path, monkeypatch):
        cache = {
            "del1.txt": _make_entry("del1.txt", b"aaa"),
            "del2.txt": _make_entry("del2.txt", b"bbb"),
        }
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert len(report.deleted) == 2


class TestRenamedFiles:
    def test_rename_detected(self, tmp_path, monkeypatch):
        content = b"same content"
        (tmp_path / "new_name.txt").write_bytes(content)
        cache = {"old_name.txt": _make_entry("old_name.txt", content)}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert len(report.renamed) == 1
        assert report.renamed[0].rel_path == "new_name.txt"
        assert report.renamed[0].old_rel_path == "old_name.txt"

    def test_rename_not_counted_as_deleted(self, tmp_path, monkeypatch):
        content = b"same content"
        (tmp_path / "new_name.txt").write_bytes(content)
        cache = {"old_name.txt": _make_entry("old_name.txt", content)}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.deleted == []

    def test_rename_not_counted_as_new(self, tmp_path, monkeypatch):
        content = b"same content"
        (tmp_path / "new_name.txt").write_bytes(content)
        cache = {"old_name.txt": _make_entry("old_name.txt", content)}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.new == []

    def test_different_content_not_rename(self, tmp_path, monkeypatch):
        """Archivo nuevo con contenido distinto al borrado → no es rename."""
        (tmp_path / "new_file.txt").write_bytes(b"different content")
        cache = {"old_file.txt": _make_entry("old_file.txt", b"original content")}
        monkeypatch.setattr("ghbackup.scanner.diff.get_all", lambda: cache)
        report = compute_delta(tmp_path)
        assert report.renamed == []
        assert len(report.new) == 1
        assert len(report.deleted) == 1


class TestDeltaReportHelpers:
    def test_has_changes_false_when_empty(self):
        report = DeltaReport()
        assert not report.has_changes()

    def test_has_changes_true_with_new(self):
        from pathlib import Path

        from ghbackup.scanner.diff import FileChange

        report = DeltaReport(new=[FileChange("f.txt", Path("f.txt"), "sha", 5, "2026Z")])
        assert report.has_changes()

    def test_total_upload_bytes(self, tmp_path, monkeypatch):
        (tmp_path / "a.txt").write_bytes(b"hello")  # 5 bytes
        (tmp_path / "b.txt").write_bytes(b"world!")  # 6 bytes
        report = compute_delta(tmp_path)
        assert report.total_upload_bytes() == 11

    def test_summary_dict_keys(self, tmp_path):
        report = compute_delta(tmp_path)
        d = report.summary_dict()
        assert set(d.keys()) == {"modified", "new", "renamed", "deleted", "unchanged"}

    def test_empty_directory_no_changes(self, tmp_path):
        report = compute_delta(tmp_path)
        assert not report.has_changes()
        assert report.unchanged_count == 0
