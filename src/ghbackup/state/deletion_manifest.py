"""Manifiesto de archivos borrados localmente.

Política (acordada con el usuario):
- Cuando detectamos que un archivo fue borrado localmente, lo agregamos al manifiesto.
- En cada push, proponemos restaurar los hasta 5 archivos borrados más recientes
  cuya `deleted_at_utc` esté dentro de los últimos 30 días.
- Si el usuario los restaura, marcamos `restored=True`.
- Pasados los 30 días, no se proponen más automáticamente (pero quedan en el manifiesto).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

from ghbackup.state.paths import deletion_manifest_path, ensure_dirs


@dataclass
class DeletionEntry:
    path: str
    sha256: str
    deleted_at_utc: str
    last_known_in_commit: str | None = None
    last_known_in_tag: str | None = None
    restored: bool = False
    proposed_at_utc: str | None = None


@dataclass
class DeletionManifest:
    entries: list[DeletionEntry] = field(default_factory=list)

    def add(self, entry: DeletionEntry) -> None:
        # si el path ya está y no fue restaurado, refrescamos timestamp
        for existing in self.entries:
            if existing.path == entry.path and not existing.restored:
                existing.deleted_at_utc = entry.deleted_at_utc
                existing.sha256 = entry.sha256
                existing.last_known_in_commit = entry.last_known_in_commit
                existing.last_known_in_tag = entry.last_known_in_tag
                return
        self.entries.append(entry)

    def mark_restored(self, path: str) -> None:
        for e in self.entries:
            if e.path == path and not e.restored:
                e.restored = True
                return

    def recent_candidates(self, limit: int = 5, days: int = 30) -> list[DeletionEntry]:
        """Devuelve hasta `limit` entradas no restauradas borradas en los últimos `days` días."""
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        candidates: list[DeletionEntry] = []
        for e in self.entries:
            if e.restored:
                continue
            try:
                dt = datetime.fromisoformat(e.deleted_at_utc.replace("Z", "+00:00"))
            except ValueError:
                continue
            if dt >= threshold:
                candidates.append(e)
        # más recientes primero
        candidates.sort(key=lambda x: x.deleted_at_utc, reverse=True)
        return candidates[:limit]


def load() -> DeletionManifest:
    path = deletion_manifest_path()
    if not path.exists():
        return DeletionManifest()
    raw = json.loads(path.read_text(encoding="utf-8"))
    entries = [DeletionEntry(**e) for e in raw.get("entries", [])]
    return DeletionManifest(entries=entries)


def save(manifest: DeletionManifest) -> None:
    ensure_dirs()
    payload = {"entries": [asdict(e) for e in manifest.entries]}
    tmp = deletion_manifest_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(deletion_manifest_path())


def append_deletions(
    deletions: Iterable[tuple[str, str]],
    last_commit: str | None,
    last_tag: str | None,
) -> DeletionManifest:
    """Helper: agrega varias deleciones al manifiesto y lo persiste."""
    manifest = load()
    now_utc = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    for path, sha in deletions:
        manifest.add(
            DeletionEntry(
                path=path,
                sha256=sha,
                deleted_at_utc=now_utc,
                last_known_in_commit=last_commit,
                last_known_in_tag=last_tag,
            )
        )
    save(manifest)
    return manifest
