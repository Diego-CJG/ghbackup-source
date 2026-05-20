"""Logger dual: una línea JSON estructurada + una fila Markdown legible.

Para CI/CD se parsea el .jsonl; para revisión humana se abre el .md.
Ambos archivos son append-only y nunca se rotan automáticamente
(el usuario puede rotarlos manualmente si crecen demasiado).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from ghbackup.state.paths import (
    ensure_dirs,
    operations_jsonl_path,
    operations_md_path,
)

_MD_HEADER = (
    "| Fecha (UTC)         | Acción           | Rama       | Tag                    "
    "| Archivos (M/N/R/D) | Tamaño   | Resultado |\n"
    "|---------------------|------------------|------------|------------------------"
    "|--------------------|----------|-----------|\n"
)


def _ensure_md_header() -> None:
    path = operations_md_path()
    if not path.exists():
        ensure_dirs()
        path.write_text("# Histórico de operaciones — ghbackup\n\n" + _MD_HEADER, encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _human_size(n_bytes: int) -> str:
    if n_bytes < 1024:
        return f"{n_bytes} B"
    if n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    if n_bytes < 1024 * 1024 * 1024:
        return f"{n_bytes / (1024 * 1024):.2f} MB"
    return f"{n_bytes / (1024 * 1024 * 1024):.2f} GB"


def log_event(
    action: str,
    *,
    result: str = "ok",
    branch: str = "",
    tag: str = "",
    commit: str = "",
    files_summary: dict[str, int] | None = None,
    bytes_total: int = 0,
    duration_ms: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """Escribe el evento en ambos archivos."""
    ensure_dirs()
    _ensure_md_header()

    files_summary = files_summary or {}
    record: dict[str, Any] = {
        "ts": _now_iso(),
        "action": action,
        "result": result,
        "branch": branch,
        "tag": tag,
        "commit": commit,
        "files": files_summary,
        "bytes": bytes_total,
    }
    if duration_ms is not None:
        record["duration_ms"] = duration_ms
    if extra:
        record["extra"] = extra

    with open(operations_jsonl_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    counts = (
        f"{files_summary.get('modified', 0)}M / "
        f"{files_summary.get('new', 0)}N / "
        f"{files_summary.get('renamed', 0)}R / "
        f"{files_summary.get('deleted', 0)}D"
    )
    icon = "✅" if result == "ok" else ("⚠️" if result == "warning" else "❌")
    row = (
        f"| {record['ts'].replace('T', ' ').replace('Z', '')} "
        f"| {action:<16} | {branch[:10]:<10} | {tag[:22]:<22} "
        f"| {counts:<18} | {_human_size(bytes_total):>8} | {icon} {result:<5} |\n"
    )
    with open(operations_md_path(), "a", encoding="utf-8") as f:
        f.write(row)
