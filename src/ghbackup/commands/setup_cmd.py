"""Subcomando `setup`: wizard interactivo de primera conexión.

Guía al usuario paso a paso:
  1. Definir master password
  2. Generar PAT en GitHub (instrucciones)
  3. Ingresar token y validar
  4. Listar repos disponibles y elegir destino (o crear nuevo, siempre privado)
  5. Definir carpeta source local
  6. Elegir nombre de rama (default: nombre de la carpeta)
  7. Confirmar y persistir
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import click

from ghbackup.auth import vault
from ghbackup.auth import recovery
from ghbackup.github_io import client as gh_client
from ghbackup.logging_.dual_logger import log_event
from ghbackup.state import config as cfg_store
from ghbackup.state.paths import ensure_dirs
from ghbackup.ui import prompts
from ghbackup.ui.colors import error, header, info, success, warn, dim


_INSTRUCTIONS = """\
Para conectar este ejecutable con tu cuenta de GitHub necesitamos un Personal
Access Token (PAT) de tipo fine-grained. Seguí estos pasos:

  1. Abrí en el navegador:
       https://github.com/settings/personal-access-tokens/new

  2. Token name: por ejemplo  "ghbackup - <esta PC>"
     Expiration:  90 days (recomendado) o "No expiration" si preferís.
     Description: opcional ("ejecutable de respaldo a GitHub").

  3. Repository access:
       - Si querés que pueda CREAR el repo de respaldo:
            -> "All repositories"  (permitirá crearlo)
       - Si ya tenés un repo creado al que querés conectarte:
            -> "Only select repositories"  y elegí ese repo

  4. Permissions (Repository permissions):
       - Contents:        Read and write   (obligatorio)
       - Metadata:        Read-only        (obligatorio)
       - Administration:  Read and write   (sólo si vas a crear repos desde el .exe)

  5. Hacé click en "Generate token" y copialo (es la única vez que se muestra).

  6. Volvé acá y pegalo cuando te lo pida (no se mostrará al tipear).
"""


def _validate_master_password(value: str) -> bool | str:
    if len(value) < 12:
        return "La master password debe tener al menos 12 caracteres."
    return True


@click.command("setup")
def setup() -> None:
    """Wizard de primera conexión con GitHub."""
    header("ghbackup — Setup inicial")
    ensure_dirs()

    if cfg_store.exists() and vault.vault_exists():
        if not prompts.ask_confirm(
            "Ya existe una configuración previa. ¿Querés sobreescribirla?",
            default=False,
        ):
            warn("Setup cancelado.")
            return

    # --- Paso 1: master password ---
    header("Paso 1/7 — Master password")
    info(
        "Esta master password protege tu token de GitHub.\n"
        "Se usa AES-256-GCM con derivación PBKDF2 (600 000 iteraciones).\n"
        "Si la olvidás, vas a tener que regenerar el token en GitHub.\n"
    )
    mp1 = prompts.ask_password("Master password (mínimo 12 caracteres):")
    check = _validate_master_password(mp1)
    if check is not True:
        error(str(check))
        return
    mp2 = prompts.ask_password("Repetí la master password:")
    if mp1 != mp2:
        error("Las master passwords no coinciden. Abortando.")
        return

    # --- Paso 2: instrucciones para el PAT ---
    header("Paso 2/7 — Generar un Personal Access Token en GitHub")
    info(_INSTRUCTIONS)
    prompts.ask_confirm("¿Generaste el token y lo tenés en el portapapeles?", default=True)

    # --- Paso 3: ingresar token y validar ---
    header("Paso 3/7 — Validar token")
    while True:
        token = prompts.ask_password("Pegá el token (no se mostrará):").strip()
        if not token:
            error("Token vacío.")
            continue
        try:
            conn = gh_client.test_connection(token)
        except gh_client.GitHubError as exc:
            error(str(exc))
            if not prompts.ask_confirm("¿Querés probar con otro token?", default=True):
                return
            continue
        success(
            f"Conexión OK. Autenticado como: {conn.login}"
            + (f" ({conn.name})" if conn.name else "")
        )
        break

    # --- Paso 4: elegir o crear repo destino ---
    header("Paso 4/7 — Elegir repositorio destino (siempre privado)")
    dim("Listando repositorios donde tenés permiso de escritura...")
    try:
        repos = gh_client.list_writable_repos(token)
    except gh_client.GitHubError as exc:
        error(str(exc))
        return

    private_repos = [r for r in repos if r.private]
    repo_choice = prompts.ask_choice(
        "¿Qué querés hacer?",
        choices=[
            "Crear un repositorio nuevo (privado)",
            f"Conectar a uno existente ({len(private_repos)} repos privados disponibles)",
        ],
    )

    if repo_choice.startswith("Crear"):
        new_name = prompts.ask_text(
            "Nombre del nuevo repositorio (sin owner):",
            default="ghbackup-respaldos",
        )
        try:
            repo = gh_client.create_private_repo(token, new_name)
        except gh_client.GitHubError as exc:
            error(str(exc))
            return
        success(f"Repositorio creado: {repo.full_name} (privado)")
    else:
        if not private_repos:
            error("No tenés repos privados disponibles. Volvé a correr setup y creá uno nuevo.")
            return
        choice = prompts.ask_choice(
            "Elegí el repo destino:",
            choices=[r.full_name for r in private_repos],
        )
        repo = next(r for r in private_repos if r.full_name == choice)
        success(f"Conectado a: {repo.full_name}")

    info(f"  URL: {repo.html_url}")

    # --- Paso 5: carpeta source ---
    header("Paso 5/7 — Carpeta source a respaldar")
    while True:
        src_str = prompts.ask_text(
            "Ruta absoluta de la carpeta a respaldar (ej: C:\\Proyectos\\MiCarpeta):"
        )
        src = Path(src_str.strip().strip('"')).expanduser()
        if not src.exists() or not src.is_dir():
            error(f"La ruta no existe o no es una carpeta: {src}")
            if not prompts.ask_confirm("¿Probar otra ruta?", default=True):
                return
            continue
        break
    info(f"Carpeta source: {src.resolve()}")

    # --- Paso 6: nombre de rama ---
    header("Paso 6/7 — Nombre de la rama en el repo")
    default_branch_name = _slugify(src.name) or "main-backup"
    branch = prompts.ask_text(
        "Nombre de la rama (Enter para usar el sugerido):",
        default=default_branch_name,
    ).strip() or default_branch_name

    # --- Paso 7: confirmar y guardar ---
    header("Paso 7/7 — Confirmar y guardar configuración")
    info(
        f"  Cuenta GitHub : {conn.login}\n"
        f"  Repositorio   : {repo.full_name}  (privado)\n"
        f"  Rama          : {branch}\n"
        f"  Carpeta source: {src.resolve()}\n"
    )
    if not prompts.ask_confirm("¿Confirmás y guardo la configuración?", default=True):
        warn("Setup cancelado por el usuario.")
        return

    # Persistir token cifrado
    vault.write_token(token, mp1)

    # Persistir config
    now = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    cfg = cfg_store.Config(
        source_folder=str(src.resolve()),
        repo_owner=repo.owner.login,
        repo_name=repo.name,
        repo_full_name=repo.full_name,
        repo_html_url=repo.html_url,
        branch=branch,
        github_login=conn.login,
        created_at_utc=now,
        updated_at_utc=now,
    )
    cfg_store.save(cfg)

    # Crear branch en el repo si no existe (sin commit nuevo: lo lanzamos en el primer push)
    try:
        from ghbackup.github_io import push as push_io  # lazy import

        push_io.ensure_branch(repo, branch)
    except Exception as exc:  # noqa: BLE001
        warn(f"Advertencia: no se pudo asegurar el branch ahora: {exc}")

    # Generar recovery codes
    codes = recovery.generate_codes()
    recovery.save_codes(codes)

    success("\n✅ Setup completo.")
    warn("\n" + "=" * 60)
    warn("  RECOVERY CODES — guardá estos codigos en un lugar seguro")
    warn("  Cada uno es de uso unico. Sirven si olvidás la master password.")
    warn("=" * 60)
    for i, code in enumerate(codes, start=1):
        info(f"  {i:2d}.  {code}")
    warn("=" * 60)
    warn("  Imprimelos o guardalos en tu gestor de contraseñas AHORA.")
    warn("  No se volvera a mostrar este listado.")
    warn("=" * 60 + "\n")
    prompts.ask_confirm("Confirmo que guarde los recovery codes.", default=True)

    log_event("setup_complete", branch=branch, extra={"repo": repo.full_name, "login": conn.login})
    success("Ahora podés correr:  ghbackup push")


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9\-_]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s
