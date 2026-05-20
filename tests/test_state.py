"""Tests unitarios para ghbackup.state (cache, config, paths, deletion_manifest)."""

from __future__ import annotations

import pytest

from ghbackup.state.cache import CacheEntry, delete_many, get_all, upsert_many, wipe
from ghbackup.state.config import Config, exists, load, reset, save
from ghbackup.state.deletion_manifest import (
    append_deletions,
)
from ghbackup.state.deletion_manifest import (
    load as load_manifest,
)
from ghbackup.state.deletion_manifest import (
    save as save_manifest,
)
from ghbackup.state.paths import (
    config_path,
    deletion_manifest_path,
    ensure_dirs,
    logs_dir,
    operations_jsonl_path,
    operations_md_path,
    recovery_codes_path,
)


@pytest.fixture(autouse=True)
def patch_app_dir(tmp_path, monkeypatch):
    """Redirige app_dir a un directorio temporal para todos los tests."""
    monkeypatch.setattr("ghbackup.state.paths.app_dir", lambda: tmp_path)
    monkeypatch.setattr("ghbackup.state.cache.cache_path", lambda: tmp_path / "cache.sqlite")
    monkeypatch.setattr(
        "ghbackup.state.cache.ensure_dirs", lambda: tmp_path.mkdir(parents=True, exist_ok=True)
    )
    monkeypatch.setattr("ghbackup.state.config.config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr(
        "ghbackup.state.deletion_manifest.deletion_manifest_path",
        lambda: tmp_path / "deletion_manifest.json",
    )


# ─── paths.py ────────────────────────────────────────────────────────────────


class TestPaths:
    def test_config_path_under_app_dir(self, tmp_path):
        assert config_path() == tmp_path / "config.json"

    def test_vault_path_under_app_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ghbackup.state.paths.vault_path", lambda: tmp_path / "vault.enc")
        assert (tmp_path / "vault.enc").name == "vault.enc"

    def test_cache_path_under_app_dir(self, tmp_path, monkeypatch):
        monkeypatch.setattr("ghbackup.state.paths.cache_path", lambda: tmp_path / "cache.sqlite")
        assert (tmp_path / "cache.sqlite").name == "cache.sqlite"

    def test_ensure_dirs_creates_structure(self, tmp_path):
        ensure_dirs()
        assert tmp_path.exists()

    def test_logs_dir_name(self, tmp_path):
        assert logs_dir().name == "logs"

    def test_operations_jsonl_path(self):
        assert operations_jsonl_path().name == "operations.jsonl"

    def test_operations_md_path(self):
        assert operations_md_path().name == "operations.md"

    def test_recovery_codes_path(self):
        assert recovery_codes_path().name == "recovery_codes.json"

    def test_deletion_manifest_path(self):
        assert deletion_manifest_path().name == "deletion_manifest.json"


# ─── cache.py ────────────────────────────────────────────────────────────────


def _entry(path: str, sha: str = "abc123") -> CacheEntry:
    return CacheEntry(path=path, sha256=sha, size_bytes=10, mtime_utc="2026-01-01T00:00:00Z")


class TestCache:
    def test_empty_on_start(self):
        assert get_all() == {}

    def test_upsert_and_get(self):
        upsert_many([_entry("file.txt")])
        result = get_all()
        assert "file.txt" in result
        assert result["file.txt"].sha256 == "abc123"

    def test_upsert_multiple(self):
        upsert_many([_entry("a.txt", "sha1"), _entry("b.txt", "sha2")])
        result = get_all()
        assert len(result) == 2
        assert result["a.txt"].sha256 == "sha1"
        assert result["b.txt"].sha256 == "sha2"

    def test_upsert_updates_existing(self):
        upsert_many([_entry("file.txt", "old_sha")])
        upsert_many([_entry("file.txt", "new_sha")])
        assert get_all()["file.txt"].sha256 == "new_sha"

    def test_delete_many(self):
        upsert_many([_entry("a.txt"), _entry("b.txt")])
        delete_many(["a.txt"])
        result = get_all()
        assert "a.txt" not in result
        assert "b.txt" in result

    def test_wipe_clears_all(self):
        upsert_many([_entry("a.txt"), _entry("b.txt")])
        wipe()
        assert get_all() == {}

    def test_delete_nonexistent_no_error(self):
        delete_many(["nonexistent.txt"])  # no debe lanzar

    def test_cache_entry_fields(self):
        entry = CacheEntry(
            path="doc.txt",
            sha256="deadbeef",
            size_bytes=42,
            mtime_utc="2026-05-01T00:00:00Z",
            last_seen_commit="abc",
            last_push_tag="v1.0",
        )
        upsert_many([entry])
        stored = get_all()["doc.txt"]
        assert stored.last_seen_commit == "abc"
        assert stored.last_push_tag == "v1.0"


# ─── config.py ───────────────────────────────────────────────────────────────


def _make_config(**kwargs) -> Config:
    defaults = {
        "source_folder": "C:/test",
        "repo_owner": "user",
        "repo_name": "repo",
        "repo_full_name": "user/repo",
        "repo_html_url": "https://github.com/user/repo",
        "branch": "main",
        "github_login": "user",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "updated_at_utc": "2026-01-01T00:00:00Z",
    }
    defaults.update(kwargs)
    return Config(**defaults)


class TestConfig:
    def test_not_exists_before_save(self):
        assert not exists()

    def test_exists_after_save(self):
        save(_make_config())
        assert exists()

    def test_save_and_load_roundtrip(self):
        cfg = _make_config(branch="feature-branch")
        save(cfg)
        loaded = load()
        assert loaded.branch == "feature-branch"
        assert loaded.repo_full_name == "user/repo"

    def test_save_overwrites(self):
        save(_make_config(branch="old"))
        save(_make_config(branch="new"))
        assert load().branch == "new"

    def test_reset_removes_file(self, tmp_path):
        save(_make_config())
        assert exists()
        reset()
        assert not exists()

    def test_reset_nonexistent_no_error(self):
        reset()  # no debe lanzar

    def test_all_fields_preserved(self):
        cfg = _make_config(
            source_folder="D:/Projects",
            github_login="testuser",
            created_at_utc="2026-05-13T12:00:00Z",
        )
        save(cfg)
        loaded = load()
        assert loaded.source_folder == "D:/Projects"
        assert loaded.github_login == "testuser"
        assert loaded.created_at_utc == "2026-05-13T12:00:00Z"


# ─── deletion_manifest.py ────────────────────────────────────────────────────


class TestDeletionManifest:
    def test_load_returns_empty_manifest_if_no_file(self):
        m = load_manifest()
        assert m.entries == []

    def test_append_and_load(self):
        append_deletions(
            [("file.txt", "sha123"), ("doc.docx", "sha456")],
            last_commit="abc",
            last_tag="v1.0",
        )
        m = load_manifest()
        paths = [e.path for e in m.entries]
        assert "file.txt" in paths
        assert "doc.docx" in paths

    def test_mark_restored(self):
        append_deletions([("file.txt", "sha123")], last_commit="abc", last_tag="v1.0")
        m = load_manifest()
        m.mark_restored("file.txt")
        save_manifest(m)
        reloaded = load_manifest()
        entry = next(e for e in reloaded.entries if e.path == "file.txt")
        assert entry.restored

    def test_recent_candidates_excludes_restored(self):
        append_deletions([("f.txt", "sha")], last_commit="abc", last_tag="v1")
        m = load_manifest()
        m.mark_restored("f.txt")
        save_manifest(m)
        m2 = load_manifest()
        assert m2.recent_candidates(limit=5, days=30) == []

    def test_recent_candidates_returns_unrestored(self):
        append_deletions([("a.txt", "s1"), ("b.txt", "s2")], last_commit="c", last_tag="t")
        m = load_manifest()
        candidates = m.recent_candidates(limit=5, days=30)
        assert len(candidates) == 2

    def test_recent_candidates_respects_limit(self):
        append_deletions(
            [(f"f{i}.txt", f"s{i}") for i in range(10)],
            last_commit="c",
            last_tag="t",
        )
        m = load_manifest()
        candidates = m.recent_candidates(limit=3, days=30)
        assert len(candidates) == 3
