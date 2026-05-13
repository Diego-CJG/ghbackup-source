"""Subcomando `schedule`: crear/listar/borrar Tareas Programadas de Windows.

Importante:
  - En modo programado el .exe no puede pedir la master password interactiva.
  - Soluciones soportadas:
      a) `--master-pass-env <VAR>`: la tarea pasa el nombre de una env var
         (cargada en el contexto de la tarea programada). Recomendado.
      b) Modo "headless con Credential Manager": fuera de scope de esta versión
         inicial; se documenta como futura mejora.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import click

from ghbackup.logging_.dual_logger import log_event
from ghbackup.ui import prompts
from ghbackup.ui.colors import dim, error, header, info, success, warn

TASK_NAME = "ghbackup_auto_push"


def _exe_path() -> str:
    """Devuelve la ruta al ejecutable a usar (frozen .exe o python -m ghbackup)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    # Fallback dev: python -m ghbackup
    return f'"{sys.executable}" -m ghbackup'


@click.group("schedule")
def schedule() -> None:
    """Crea, lista o quita una Tarea Programada de Windows para push automático."""


@schedule.command("create")
@click.option(
    "--every",
    type=click.Choice(["daily", "hours", "logon"], case_sensitive=False),
    default="daily",
    help="Frecuencia: daily | hours | logon",
)
@click.option("--at", "at_time", default="19:00", help="Hora para daily (HH:MM). Default 19:00.")
@click.option("--interval", default=4, type=int, help="Cada cuántas horas para 'hours'.")
@click.option("--master-pass-env", default="GHBACKUP_MASTER", help="Env var con master password.")
def create_schedule(every: str, at_time: str, interval: int, master_pass_env: str) -> None:
    """Crea una tarea programada que corre `ghbackup push --yes`."""
    header("ghbackup — Crear tarea programada")
    if not _on_windows():
        error("Este comando solo funciona en Windows.")
        return

    exe = _exe_path()
    tr = f"{exe} push --yes --no-prompt-name --master-pass-env {master_pass_env}"

    cmd: list[str]
    if every == "daily":
        cmd = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/SC",
            "DAILY",
            "/ST",
            at_time,
            "/TR",
            tr,
        ]
    elif every == "hours":
        cmd = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/SC",
            "HOURLY",
            "/MO",
            str(interval),
            "/TR",
            tr,
        ]
    else:  # logon
        cmd = [
            "schtasks",
            "/Create",
            "/F",
            "/TN",
            TASK_NAME,
            "/SC",
            "ONLOGON",
            "/TR",
            tr,
        ]

    info("Comando a ejecutar:\n  " + " ".join(cmd))
    if not prompts.ask_confirm("¿Confirmás crear la tarea?", default=True):
        warn("Cancelado.")
        return

    warn(
        f"\nIMPORTANTE: para que la tarea funcione, la variable de entorno "
        f"`{master_pass_env}` debe estar definida en el contexto de Windows con "
        "tu master password. Crear esa env var es un paso manual por seguridad."
    )

    try:
        res = subprocess.run(cmd, check=True, capture_output=True, text=True)
        info(res.stdout)
    except subprocess.CalledProcessError as exc:
        error(f"schtasks falló: {exc.stderr or exc.stdout}")
        return

    success(f"✅ Tarea '{TASK_NAME}' creada.")
    log_event("schedule_created", extra={"every": every, "at": at_time, "interval": interval})


@schedule.command("list")
def list_schedule() -> None:
    """Lista la tarea programada de ghbackup (si existe)."""
    if not _on_windows():
        error("Solo en Windows.")
        return
    try:
        res = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME, "/V", "/FO", "LIST"],
            capture_output=True,
            text=True,
            check=True,
        )
        print(res.stdout)
    except subprocess.CalledProcessError:
        dim("(no hay tarea ghbackup registrada)")


@schedule.command("remove")
def remove_schedule() -> None:
    """Elimina la tarea programada."""
    if not _on_windows():
        error("Solo en Windows.")
        return
    if not prompts.ask_confirm(f"¿Borrar la tarea '{TASK_NAME}'?", default=False):
        return
    try:
        subprocess.run(
            ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"],
            check=True,
            capture_output=True,
            text=True,
        )
        success("✅ Tarea eliminada.")
    except subprocess.CalledProcessError as exc:
        error(f"schtasks falló: {exc.stderr or exc.stdout}")


def _on_windows() -> bool:
    return sys.platform.startswith("win") and shutil.which("schtasks") is not None
