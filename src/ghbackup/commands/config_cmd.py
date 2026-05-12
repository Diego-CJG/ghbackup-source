"""Subcomando `config`: ver/editar configuración."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import click

from ghbackup.auth import vault
from ghbackup.github_io import client as gh_client
from ghbackup.logging_.dual_logger import log_event
from ghbackup.state import config as cfg_store
from ghbackup.ui import prompts
from ghbackup.ui.colors import error, header, info, success, warn


@click.group("config", invoke_without_command=True)
@click.pass_context
def config(ctx: click.Context) -> None:
    """Gestiona la configuración del ejecutable."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(show)


@config.command("show")
def show() -> None:
    """Muestra la configuración actual (sin secretos)."""
    header("ghbackup — Configuración actual")
    if not cfg_store.exists():
        info("No hay configuración. Corré `ghbackup setup` primero.")
        return
    cfg = cfg_store.load()
    info(f"  Cuenta GitHub  : {cfg.github_login}")
    info(f"  Repositorio    : {cfg.repo_full_name}")
    info(f"  Rama           : {cfg.branch}")
    info(f"  Carpeta source : {cfg.source_folder}")
    info(f"  Creado en      : {cfg.created_at_utc}")
    info(f"  Actualizado en : {cfg.updated_at_utc}")
    info(f"  Vault token    : {'presente' if vault.vault_exists() else 'AUSENTE — corré setup'}")


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_cmd(key: str, value: str) -> None:
    """Cambia un valor del config (source_folder, branch)."""
    ALLOWED = {"source_folder", "branch"}
    if key not in ALLOWED:
        error(f"Clave no editable directamente: {key}. Editables: {sorted(ALLOWED)}")
        return
    cfg = cfg_store.load()
    if key == "source_folder":
        p = Path(value).expanduser()
        if not p.exists() or not p.is_dir():
            error(f"La ruta no existe o no es una carpeta: {p}")
            return
        cfg.source_folder = str(p.resolve())
    elif key == "branch":
        cfg.branch = value.strip()
    cfg.updated_at_utc = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cfg_store.save(cfg)
    success(f"✅ {key} actualizado.")
    log_event("config_changed", extra={"key": key})


@config.command("rotate-token")
def rotate_token() -> None:
    """Reemplaza el PAT preservando la master password."""
    if not vault.vault_exists():
        error("No hay vault. Corré `ghbackup setup` primero.")
        return
    master_pw = prompts.ask_password("Master password actual:")
    try:
        _ = vault.read_token(master_pw)
    except vault.InvalidMasterPassword:
        error("Master password incorrecta.")
        return
    new_token = prompts.ask_password("Pegá el nuevo PAT (no se mostrará):")
    try:
        conn = gh_client.test_connection(new_token)
    except gh_client.GitHubError as exc:
        error(str(exc))
        return
    vault.rotate_token(new_token, master_pw)
    success(f"✅ Token rotado. Autenticado como: {conn.login}")
    log_event("token_rotated", extra={"login": conn.login})


@config.command("reset")
def reset() -> None:
    """Elimina toda la configuración y el vault (irreversible)."""
    if not prompts.ask_confirm(
        "Esto borrará el config.json y el vault.enc. ¿Continuar?", default=False
    ):
        warn("Cancelado.")
        return
    cfg_store.reset()
    vault.delete_vault()
    success("✅ Configuración y vault eliminados. Corré `ghbackup setup` para volver a empezar.")
