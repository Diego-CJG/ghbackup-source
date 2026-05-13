"""Subcomando `verify`: diagnóstico de consistencia cache ↔ local ↔ repo."""

from __future__ import annotations

from pathlib import Path

import click

from ghbackup.auth import vault
from ghbackup.github_io import client as gh_client
from ghbackup.github_io import pull as gh_pull
from ghbackup.scanner.diff import compute_delta
from ghbackup.state import cache as cache_store
from ghbackup.state import config as cfg_store
from ghbackup.ui import prompts
from ghbackup.ui.colors import dim, error, header, info, success, warn


@click.command("verify")
@click.option("--rebuild", is_flag=True, help="Borra el cache y vuelve a calcularlo desde cero.")
def verify(rebuild: bool) -> None:
    """Recalcula hashes y compara cache ↔ filesystem ↔ repo."""
    header("ghbackup — Verify")
    if not cfg_store.exists():
        error("No hay configuración.")
        return
    cfg = cfg_store.load()
    source_root = Path(cfg.source_folder)
    if not source_root.exists():
        error(f"Source no existe: {source_root}")
        return

    if rebuild:
        if not prompts.ask_confirm(
            "Esto borra el cache local y vuelve a hashear toda la carpeta source. ¿Continuar?",
            default=False,
        ):
            warn("Cancelado.")
            return
        cache_store.wipe()
        success("Cache local vaciado.")

    dim("Comparando filesystem local contra cache...")
    report = compute_delta(source_root, verbose=True)
    info(f"  Sin cambios respecto al cache: {report.unchanged_count}")
    info(f"  Modificados: {len(report.modified)}")
    info(f"  Nuevos: {len(report.new)}")
    info(f"  Renombres: {len(report.renamed)}")
    info(f"  Borrados (en cache, no en filesystem): {len(report.deleted)}")

    # Comparación contra repo
    if not vault.vault_exists():
        warn("No hay vault. No puedo comparar contra el repo.")
        return
    master_pw = prompts.ask_password("Master password (Enter para saltar comparación con repo):")
    if not master_pw:
        return
    try:
        token = vault.read_token(master_pw)
    except vault.InvalidMasterPassword:
        error("Master password incorrecta.")
        return

    repo = gh_client.get_repo(token, cfg.repo_full_name)
    try:
        head_sha = repo.get_branch(cfg.branch).commit.sha
    except Exception as exc:  # noqa: BLE001
        warn(f"No se pudo leer el branch remoto: {exc}")
        return

    remote_files = set(gh_pull.list_files_in_commit(repo, head_sha))
    # Compose del estado local a partir del cache actualizado tras compute_delta
    all_local = set(cache_store.get_all().keys()) | {
        c.rel_path for c in report.new + report.modified + report.renamed
    }
    only_local = all_local - remote_files
    only_remote = remote_files - all_local
    info(f"\n  Archivos solo locales (sin pushear aún): {len(only_local)}")
    for p in sorted(only_local)[:20]:
        info(f"    + {p}")
    info(f"  Archivos solo en repo (posibles borrados locales): {len(only_remote)}")
    for p in sorted(only_remote)[:20]:
        info(f"    - {p}")

    success("\n✅ Verify completo.")
