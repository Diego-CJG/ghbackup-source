"""Subcomando `push`: detecta deltas, propone restauraciones, sube atómicamente."""
from __future__ import annotations

import time
from pathlib import Path

import click

from ghbackup.auth import vault
from ghbackup.github_io import client as gh_client
from ghbackup.github_io import pull as gh_pull
from ghbackup.github_io import push as gh_push
from ghbackup.logging_.dual_logger import log_event
from ghbackup.scanner.diff import DeltaReport, FileChange, compute_delta
from ghbackup.state import cache as cache_store
from ghbackup.state import config as cfg_store
from ghbackup.state import deletion_manifest as dm
from ghbackup.state.cache import CacheEntry
from ghbackup.ui import prompts
from ghbackup.ui.colors import dim, error, header, info, success, warn


MAX_FILE_BYTES = 100 * 1024 * 1024  # 100 MB (límite GitHub para blobs vía API)


@click.command("push")
@click.option("--name", "version_name", default=None, help="Nombre custom de la versión (tag).")
@click.option("--yes", "auto_yes", is_flag=True, help="Confirma todo automáticamente (sin prompts).")
@click.option("--no-prompt-name", is_flag=True, help="No pregunta nombre, usa el auto.")
@click.option("--master-pass-env", default=None, help="Variable de entorno con la master password (uso programado).")
def push(version_name: str | None, auto_yes: bool, no_prompt_name: bool, master_pass_env: str | None) -> None:
    """Detecta cambios en la carpeta source y los respalda a GitHub."""
    header("ghbackup — Push")

    # 1. Cargar config
    if not cfg_store.exists():
        error("No hay configuración. Corré `ghbackup setup` primero.")
        return
    cfg = cfg_store.load()
    if not cfg.repo_full_name or not cfg.source_folder:
        error("Configuración incompleta. Corré `ghbackup setup` nuevamente.")
        return

    # 2. Desbloquear vault
    master_pw = _resolve_master_password(master_pass_env)
    if master_pw is None:
        return
    try:
        token = vault.read_token(master_pw)
    except vault.InvalidMasterPassword:
        error("Master password incorrecta.")
        return

    # 3. Test de conexión
    try:
        conn = gh_client.test_connection(token)
    except gh_client.GitHubError as exc:
        error(str(exc))
        log_event("push_failed", result="error", extra={"reason": str(exc)})
        return

    info(f"Conectado a GitHub como: {conn.login}")
    info(f"Repositorio destino    : {cfg.repo_full_name}  (rama: {cfg.branch})")
    info(f"Carpeta source         : {cfg.source_folder}\n")

    if not auto_yes and not prompts.ask_confirm("¿Procedo a escanear la carpeta source?", default=True):
        warn("Push cancelado.")
        return

    # 4. Escanear
    source_root = Path(cfg.source_folder)
    if not source_root.exists():
        error(f"La carpeta source no existe: {source_root}")
        log_event("push_failed", result="error", extra={"reason": "source_missing"})
        return

    start_ts = time.monotonic()
    dim("Escaneando archivos y calculando SHA-256...")
    report = compute_delta(source_root, verbose=True)

    # 5. Detectar archivos demasiado grandes
    oversized: list[FileChange] = []
    for bucket in (report.modified, report.new, report.renamed):
        for ch in list(bucket):
            if ch.size_bytes > MAX_FILE_BYTES:
                oversized.append(ch)
                bucket.remove(ch)
    if oversized:
        warn(f"\n⚠️  {len(oversized)} archivos exceden el límite de GitHub (100 MB) y NO serán subidos:")
        for ch in oversized:
            warn(f"   - {ch.rel_path} ({ch.size_bytes // 1024 // 1024} MB)")

    # 6. Mostrar resumen
    _print_summary(report)
    if not report.has_changes():
        success("✅ No hay cambios para subir. Todo está sincronizado.")
        log_event("push", result="ok", branch=cfg.branch, files_summary=report.summary_dict())
        return

    # 7. Detectar drift remoto: archivos en el repo que ya no están localmente (borrados)
    repo = gh_client.get_repo(token, cfg.repo_full_name)
    try:
        head_sha = repo.get_branch(cfg.branch).commit.sha
        remote_files = set(gh_pull.list_files_in_commit(repo, head_sha))
    except Exception:
        remote_files = set()

    local_paths = {e.path for e in cache_store.get_all().values()} | {
        c.rel_path for c in report.modified + report.new + report.renamed
    }
    locally_missing = remote_files - local_paths

    # 8. Ofrecer restaurar últimos 5 borrados del último mes
    manifest = dm.load()
    candidates = manifest.recent_candidates(limit=5, days=30)
    restored_now: list[str] = []
    if candidates and not auto_yes:
        warn(f"\nHay {len(candidates)} archivos borrados localmente en los últimos 30 días.")
        info("¿Querés restaurar alguno antes de pushear?")
        for i, c in enumerate(candidates, start=1):
            choice = prompts.ask_choice(
                f"  [{i}/{len(candidates)}] {c.path} (borrado: {c.deleted_at_utc})",
                choices=["Saltar", "Restaurar desde el repo"],
            )
            if choice.startswith("Restaurar"):
                try:
                    sha_to_use = c.last_known_in_commit or head_sha
                    data = gh_pull.download_file_at_commit(repo, sha_to_use, c.path)
                    target = source_root / Path(c.path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    manifest.mark_restored(c.path)
                    restored_now.append(c.path)
                    success(f"    ✅ Restaurado: {c.path}")
                except Exception as exc:  # noqa: BLE001
                    error(f"    ❌ No se pudo restaurar {c.path}: {exc}")
        dm.save(manifest)
        if restored_now:
            info("Re-escaneando tras restauración...")
            report = compute_delta(source_root, verbose=False)

    # 9. Confirmación
    action = "yes" if auto_yes else _confirm_or_select(report)
    if action == "no":
        warn("Push cancelado por el usuario.")
        log_event("push", result="cancelled", branch=cfg.branch, files_summary=report.summary_dict())
        return

    # 10. Nombre de versión (tag)
    if version_name:
        tag_name = gh_push.sanitize_tag(version_name)
    elif no_prompt_name or auto_yes:
        tag_name = gh_push.auto_tag_name(source_root)
    else:
        default = gh_push.auto_tag_name(source_root)
        raw = prompts.ask_text(
            f"Nombre de esta versión (Enter para usar '{default}'):",
            default="",
        ).strip()
        tag_name = gh_push.sanitize_tag(raw) if raw else default
    tag_name = gh_push.ensure_unique_tag(repo, tag_name)
    info(f"Tag de esta versión: {tag_name}")

    # 11. Construir listas para push atómico
    upserts = [(c.rel_path, c.abs_path) for c in report.modified + report.new]
    renames = [(c.old_rel_path or "", c.rel_path, c.abs_path) for c in report.renamed]
    local_deletions = [e.path for e in report.deleted]

    # 12. Confirmación final
    if not auto_yes:
        if not prompts.ask_confirm(
            f"Confirmás subir {len(upserts)} archivos (+{len(renames)} renames) "
            f"como tag '{tag_name}'?",
            default=True,
        ):
            warn("Push cancelado.")
            return

    # 13. Push atómico
    commit_message = f"{tag_name} | {conn.login} | versión generada por ghbackup"
    try:
        dim("Subiendo blobs y creando commit + tag...")
        result = gh_push.atomic_push(
            repo,
            cfg.branch,
            upserts=upserts,
            renames=renames,
            local_deletions=local_deletions,
            commit_message=commit_message,
            tag_name=tag_name,
            tag_message=commit_message,
        )
    except Exception as exc:  # noqa: BLE001
        error(f"❌ Push falló: {exc}")
        log_event(
            "push_failed",
            result="error",
            branch=cfg.branch,
            files_summary=report.summary_dict(),
            extra={"reason": str(exc)},
        )
        return

    success("\n✅ Push completado.")
    info(f"  Commit: {result.commit_sha[:10]}  →  {result.commit_url}")
    info(f"  Tag   : {result.tag_name}        →  {result.tag_url}")

    # 14. Actualizar cache local
    new_entries: list[CacheEntry] = []
    for ch in report.modified + report.new:
        new_entries.append(
            CacheEntry(
                path=ch.rel_path,
                sha256=ch.sha256,
                size_bytes=ch.size_bytes,
                mtime_utc=ch.mtime_utc,
                last_seen_commit=result.commit_sha,
                last_push_tag=tag_name,
            )
        )
    for ch in report.renamed:
        new_entries.append(
            CacheEntry(
                path=ch.rel_path,
                sha256=ch.sha256,
                size_bytes=ch.size_bytes,
                mtime_utc=ch.mtime_utc,
                last_seen_commit=result.commit_sha,
                last_push_tag=tag_name,
            )
        )
        # eliminar la entrada vieja del cache (path renombrado)
        if ch.old_rel_path:
            cache_store.delete_many([ch.old_rel_path])
    cache_store.upsert_many(new_entries)

    # 15. Registrar borrados en manifiesto (sin tocar el repo)
    if report.deleted:
        dm.append_deletions(
            [(e.path, e.sha256) for e in report.deleted],
            last_commit=result.commit_sha,
            last_tag=tag_name,
        )
        cache_store.delete_many([e.path for e in report.deleted])

    # 16. Log final
    duration_ms = int((time.monotonic() - start_ts) * 1000)
    log_event(
        "push",
        result="ok",
        branch=cfg.branch,
        tag=tag_name,
        commit=result.commit_sha,
        files_summary=report.summary_dict(),
        bytes_total=result.bytes_uploaded,
        duration_ms=duration_ms,
        extra={"restored_during_push": restored_now} if restored_now else None,
    )


def _resolve_master_password(env_var: str | None) -> str | None:
    if env_var:
        import os

        val = os.environ.get(env_var)
        if not val:
            error(f"La variable de entorno {env_var} está vacía o no existe.")
            return None
        return val
    return prompts.ask_password("Master password:")


def _print_summary(report: DeltaReport) -> None:
    info("\nResumen de cambios detectados:")
    info(f"  • Modificados : {len(report.modified)}")
    info(f"  • Nuevos      : {len(report.new)}")
    info(f"  • Renombres   : {len(report.renamed)}")
    info(f"  • Borrados    : {len(report.deleted)}   (NO se borran del repo)")
    info(f"  • Sin cambios : {report.unchanged_count}")
    mb = report.total_upload_bytes() / (1024 * 1024)
    info(f"  Total a subir : {mb:.2f} MB")


def _confirm_or_select(report: DeltaReport) -> str:
    action = prompts.ask_summary_action()
    if action == "detail":
        _print_detail(report)
        return _confirm_or_select(report)
    if action == "select":
        _interactive_select(report)
        return "yes" if report.has_changes() else "no"
    return action


def _print_detail(report: DeltaReport) -> None:
    info("\n--- Detalle ---")
    for ch in report.modified:
        info(f"  [M] {ch.rel_path}  ({ch.size_bytes} B)  sha:{ch.sha256[:10]}")
    for ch in report.new:
        info(f"  [N] {ch.rel_path}  ({ch.size_bytes} B)  sha:{ch.sha256[:10]}")
    for ch in report.renamed:
        info(f"  [R] {ch.old_rel_path}  →  {ch.rel_path}")
    for e in report.deleted:
        info(f"  [D] {e.path}  (último sha:{e.sha256[:10]})")


def _interactive_select(report: DeltaReport) -> None:
    """Permite al usuario deseleccionar archivos del push."""
    all_changes = [("M", c) for c in report.modified] + [("N", c) for c in report.new] + [("R", c) for c in report.renamed]
    if not all_changes:
        return
    labels = [f"[{kind}] {c.rel_path}" for kind, c in all_changes]
    selected = prompts.ask_checkbox(
        "Seleccioná los archivos que SÍ querés subir (espacio para marcar):",
        choices=labels,
    )
    selected_set = set(selected)
    new_mod, new_new, new_ren = [], [], []
    for (kind, c), label in zip(all_changes, labels):
        if label in selected_set:
            if kind == "M":
                new_mod.append(c)
            elif kind == "N":
                new_new.append(c)
            elif kind == "R":
                new_ren.append(c)
    report.modified = new_mod
    report.new = new_new
    report.renamed = new_ren
