"""Subcomando `log`: muestra el histórico de operaciones (CI/CD)."""

from __future__ import annotations

import json

import click

from ghbackup.state.paths import operations_jsonl_path
from ghbackup.ui.colors import dim, header, info


@click.command("log")
@click.option(
    "--last", "n", default=20, type=int, help="Cantidad de eventos a mostrar (default: 20)."
)
@click.option("--json", "as_json", is_flag=True, help="Imprime las líneas JSON crudas.")
def log(n: int, as_json: bool) -> None:
    """Muestra los últimos N eventos del log de operaciones."""
    header("ghbackup — Histórico de operaciones")
    path = operations_jsonl_path()
    if not path.exists():
        info("No hay registros aún.")
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    tail = lines[-n:]
    if as_json:
        for line in tail:
            print(line)
        return
    for line in tail:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        files = r.get("files", {}) or {}
        summary = (
            f"M:{files.get('modified', 0)} N:{files.get('new', 0)} "
            f"R:{files.get('renamed', 0)} D:{files.get('deleted', 0)}"
        )
        result_icon = "✅" if r.get("result") == "ok" else "❌"
        info(
            f"{r.get('ts', '')}  {result_icon} {r.get('action', ''):<18} "
            f"branch={r.get('branch', '')!s:<14} tag={r.get('tag', '')!s:<22} "
            f"{summary}  commit={r.get('commit', '')[:8]}"
        )
        if r.get("result") != "ok":
            dim(f"   extra: {r.get('extra')}")
