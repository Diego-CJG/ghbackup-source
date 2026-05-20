"""Motor de detección de cambios contra el cache local.

Output: un DeltaReport con cinco categorías:
- modified: misma ruta, distinto SHA-256
- new:      ruta nueva (no estaba en cache) y SHA-256 no coincide con ningún rename
- renamed:  archivo desaparecido en cache cuyo SHA-256 aparece en una ruta nueva
- deleted:  ruta del cache que ya no existe en disco
- unchanged: ruta del cache cuyo SHA-256 sigue siendo el mismo
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ghbackup.scanner.hasher import sha256_of_file
from ghbackup.scanner.ignore import build_spec
from ghbackup.scanner.walker import ScannedFile, walk
from ghbackup.state.cache import CacheEntry, get_all
from ghbackup.ui.colors import dim


@dataclass
class FileChange:
    rel_path: str
    abs_path: Path
    sha256: str
    size_bytes: int
    mtime_utc: str
    old_sha256: str | None = None  # solo para modified
    old_rel_path: str | None = None  # solo para renamed


@dataclass
class DeltaReport:
    modified: list[FileChange] = field(default_factory=list)
    new: list[FileChange] = field(default_factory=list)
    renamed: list[FileChange] = field(default_factory=list)
    deleted: list[CacheEntry] = field(default_factory=list)
    unchanged_count: int = 0

    def has_changes(self) -> bool:
        return bool(self.modified or self.new or self.renamed or self.deleted)

    def total_upload_bytes(self) -> int:
        return sum(c.size_bytes for c in self.modified + self.new + self.renamed)

    def summary_dict(self) -> dict[str, int]:
        return {
            "modified": len(self.modified),
            "new": len(self.new),
            "renamed": len(self.renamed),
            "deleted": len(self.deleted),
            "unchanged": self.unchanged_count,
        }


def compute_delta(source_root: Path, *, verbose: bool = False) -> DeltaReport:
    """Camina el source, calcula hashes, compara contra cache, devuelve un DeltaReport."""
    cached = get_all()  # path → CacheEntry
    spec = build_spec(source_root)

    report = DeltaReport()
    seen_paths: set[str] = set()
    new_candidates: list[FileChange] = []

    for sf in walk(source_root, spec):
        seen_paths.add(sf.rel_path)
        if verbose and sf.size_bytes > 50 * 1024 * 1024:
            dim(f"  hashing {sf.rel_path} ({sf.size_bytes // 1024 // 1024} MB)...")
        digest = sha256_of_file(sf.abs_path)

        old = cached.get(sf.rel_path)
        if old is None:
            new_candidates.append(_to_change(sf, digest))
        elif old.sha256 == digest:
            report.unchanged_count += 1
        else:
            report.modified.append(_to_change(sf, digest, old_sha256=old.sha256))

    # Determinar borrados (paths en cache que no estaban en el walk)
    cache_paths = set(cached.keys())
    deleted_paths = cache_paths - seen_paths
    deleted_entries = [cached[p] for p in deleted_paths]

    # Detección de renombres: si un nuevo archivo tiene el SHA-256 de un borrado, es rename
    deleted_by_sha: dict[str, list[CacheEntry]] = {}
    for e in deleted_entries:
        deleted_by_sha.setdefault(e.sha256, []).append(e)

    truly_new: list[FileChange] = []
    matched_deletions: set[str] = set()
    for cand in new_candidates:
        bucket = deleted_by_sha.get(cand.sha256, [])
        # filtrar las ya matcheadas
        bucket = [e for e in bucket if e.path not in matched_deletions]
        if bucket:
            origin = bucket[0]
            matched_deletions.add(origin.path)
            cand.old_rel_path = origin.path
            report.renamed.append(cand)
        else:
            truly_new.append(cand)
    report.new = truly_new

    # Lo que no fue matcheado como rename queda como deleted real
    report.deleted = [e for e in deleted_entries if e.path not in matched_deletions]

    return report


def _to_change(sf: ScannedFile, digest: str, *, old_sha256: str | None = None) -> FileChange:
    return FileChange(
        rel_path=sf.rel_path,
        abs_path=sf.abs_path,
        sha256=digest,
        size_bytes=sf.size_bytes,
        mtime_utc=sf.mtime_utc,
        old_sha256=old_sha256,
    )
