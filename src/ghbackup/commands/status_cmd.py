"""Subcomando `status`: dry-run del push, no sube nada."""

from __future__ import annotations

from pathlib import Path

import click

from ghbackup.scanner.diff import compute_delta
from ghbackup.state import config as cfg_store
from ghbackup.ui.colors import dim, error, header, info, success


@click.command("status")
def status() -> None:
    """Muestra qué cambió en la carpeta source desde el último push, sin subir nada."""
    header("ghbackup — Status")
    if not cfg_store.exists():
        error("No hay configuración. Corré `ghbackup setup` primero.")
        return
    cfg = cfg_store.load()
    source_root = Path(cfg.source_folder)
    if not source_root.exists():
        error(f"La carpeta source no existe: {source_root}")
        return

    dim("Escaneando y comparando contra cache local...")
    report = compute_delta(source_root, verbose=False)
    if not report.has_changes():
        success("✅ No hay cambios pendientes. Todo está sincronizado.")
        return

    info("\nCambios pendientes:")
    info(f"  Modificados: {len(report.modified)}")
    for c in report.modified:
        info(f"    [M] {c.rel_path}")
    info(f"  Nuevos     : {len(report.new)}")
    for c in report.new:
        info(f"    [N] {c.rel_path}")
    info(f"  Renombres  : {len(report.renamed)}")
    for c in report.renamed:
        info(f"    [R] {c.old_rel_path} → {c.rel_path}")
    info(f"  Borrados   : {len(report.deleted)}")
    for e in report.deleted:
        info(f"    [D] {e.path}")

    mb = report.total_upload_bytes() / (1024 * 1024)
    info(f"\nTotal a subir si pushearas ahora: {mb:.2f} MB")
