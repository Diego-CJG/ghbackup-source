"""Subcomando `restore`: tres modos (--file, --tag, --date)."""
from __future__ import annotations

from pathlib import Path

import click

from ghbackup.auth import vault
from ghbackup.github_io import client as gh_client
from ghbackup.github_io import pull as gh_pull
from ghbackup.logging_.dual_logger import log_event
from ghbackup.state import config as cfg_store
from ghbackup.state import deletion_manifest as dm
from ghbackup.ui import prompts
from ghbackup.ui.colors import dim, error, header, info, success, warn


@click.command("restore")
@click.option("--file", "file_path", default=None, help="Ruta relativa del archivo a restaurar.")
@click.option("--tag", "tag_name", default=None, help="Tag (versión) a restaurar completamente.")
@click.option("--date", "date_str", default=None, help="Fecha YYYY-MM-DD: restaura el estado a esa fecha.")
@click.option("--out", "out_path", default=None, help="Ruta de destino (override de la original).")
def restore(file_path: str | None, tag_name: str | None, date_str: str | None, out_path: str | None) -> None:
    """Restaura archivos desde GitHub al filesystem local."""
    header("ghbackup — Restore")

    modes_provided = sum(1 for x in (file_path, tag_name, date_str) if x)
    if modes_provided == 0:
        error("Especificá uno de los modos: --file <ruta> | --tag <nombre> | --date YYYY-MM-DD")
        return
    if modes_provided > 1:
        error("Solo podés especificar un modo a la vez.")
        return

    if not cfg_store.exists():
        error("No hay configuración. Corré `ghbackup setup` primero.")
        return
    cfg = cfg_store.load()

    master_pw = prompts.ask_password("Master password:")
    try:
        token = vault.read_token(master_pw)
    except vault.InvalidMasterPassword:
        error("Master password incorrecta.")
        return

    repo = gh_client.get_repo(token, cfg.repo_full_name)
    source_root = Path(cfg.source_folder)

    if file_path:
        _restore_by_file(repo, cfg.branch, source_root, file_path, out_path)
    elif tag_name:
        _restore_by_tag(repo, source_root, tag_name)
    elif date_str:
        _restore_by_date(repo, cfg.branch, source_root, date_str)


def _restore_by_file(repo, branch: str, source_root: Path, rel_path: str, out_path: str | None) -> None:
    info(f"Buscando versiones de: {rel_path}")
    try:
        versions = gh_pull.list_versions_of_file(repo, branch, rel_path)
    except gh_client.GitHubError as exc:
        error(str(exc))
        return
    if not versions:
        error("No se encontraron versiones de ese archivo en el repositorio.")
        return

    info(f"Se encontraron {len(versions)} versiones:")
    labels = [
        f"{i+1}. {v.commit_date_utc}  {v.tag or '(sin tag)':<25}  {v.commit_sha[:8]}  {v.message_first_line[:50]}"
        for i, v in enumerate(versions)
    ]
    choice = prompts.ask_choice("Elegí la versión a descargar:", choices=labels)
    idx = labels.index(choice)
    version = versions[idx]

    try:
        data = gh_pull.download_file_at_commit(repo, version.commit_sha, rel_path)
    except gh_client.GitHubError as exc:
        error(str(exc))
        return

    target = Path(out_path) if out_path else source_root / Path(rel_path)
    _safe_write(target, data)
    success(f"✅ Restaurado: {target}")
    # Marcar como restaurado en el manifest si correspondía
    manifest = dm.load()
    manifest.mark_restored(rel_path)
    dm.save(manifest)

    log_event(
        "restore",
        result="ok",
        branch=branch,
        commit=version.commit_sha,
        tag=version.tag or "",
        files_summary={"new": 1},
        bytes_total=len(data),
        extra={"mode": "file", "path": rel_path},
    )


def _restore_by_tag(repo, source_root: Path, tag_name: str) -> None:
    info(f"Buscando tag: {tag_name}")
    try:
        ref = repo.get_git_ref(f"tags/{tag_name}")
    except Exception as exc:  # noqa: BLE001
        error(f"Tag no encontrado: {tag_name} ({exc})")
        return

    # Si es annotated tag, ref.object.sha apunta al tag object; resolvemos al commit
    target_sha = ref.object.sha
    try:
        tag_obj = repo.get_git_tag(target_sha)
        commit_sha = tag_obj.object.sha
    except Exception:
        commit_sha = target_sha

    files = gh_pull.list_files_in_commit(repo, commit_sha)
    if not prompts.ask_confirm(
        f"El tag '{tag_name}' contiene {len(files)} archivos. ¿Descargarlos todos?",
        default=False,
    ):
        warn("Restore cancelado.")
        return

    bytes_total = 0
    for f in files:
        dim(f"  -> {f}")
        try:
            data = gh_pull.download_file_at_commit(repo, commit_sha, f)
        except gh_client.GitHubError as exc:
            error(f"     no se pudo descargar: {exc}")
            continue
        target = source_root / Path(f)
        bytes_total += len(data)
        if target.exists():
            action = prompts.ask_choice(
                f"     '{f}' ya existe localmente. ¿Qué hacés?",
                choices=["Sobrescribir", "Saltar", "Backup local y sobrescribir"],
            )
            if action == "Saltar":
                continue
            if action.startswith("Backup"):
                backup = target.with_suffix(target.suffix + ".bak")
                target.rename(backup)
        _safe_write(target, data)
    success(f"✅ Restore por tag completado: {tag_name}")

    log_event(
        "restore",
        result="ok",
        commit=commit_sha,
        tag=tag_name,
        files_summary={"new": len(files)},
        bytes_total=bytes_total,
        extra={"mode": "tag"},
    )


def _restore_by_date(repo, branch: str, source_root: Path, date_str: str) -> None:
    info(f"Buscando el último commit en '{branch}' anterior a {date_str}...")
    try:
        commit_sha = gh_pull.find_commit_by_date(repo, branch, date_str)
    except gh_client.GitHubError as exc:
        error(str(exc))
        return
    info(f"Commit objetivo: {commit_sha[:10]}")
    # Reutilizamos la lógica de --tag, simulando un tag virtual
    files = gh_pull.list_files_in_commit(repo, commit_sha)
    if not prompts.ask_confirm(
        f"Ese commit contiene {len(files)} archivos. ¿Restaurar el snapshot completo?",
        default=False,
    ):
        warn("Restore cancelado.")
        return
    bytes_total = 0
    for f in files:
        try:
            data = gh_pull.download_file_at_commit(repo, commit_sha, f)
        except gh_client.GitHubError as exc:
            error(f"  no se pudo descargar {f}: {exc}")
            continue
        target = source_root / Path(f)
        bytes_total += len(data)
        if target.exists():
            action = prompts.ask_choice(
                f"  '{f}' ya existe. ¿Qué hacés?",
                choices=["Sobrescribir", "Saltar", "Backup local y sobrescribir"],
            )
            if action == "Saltar":
                continue
            if action.startswith("Backup"):
                backup = target.with_suffix(target.suffix + ".bak")
                target.rename(backup)
        _safe_write(target, data)
    success("✅ Restore por fecha completado.")
    log_event(
        "restore",
        result="ok",
        branch=branch,
        commit=commit_sha,
        files_summary={"new": len(files)},
        bytes_total=bytes_total,
        extra={"mode": "date", "date": date_str},
    )


def _safe_write(target: Path, data: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
