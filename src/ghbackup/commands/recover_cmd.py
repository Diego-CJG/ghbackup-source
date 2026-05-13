"""Subcomando `config recover`: recuperacion de acceso con recovery code.

Cuando el usuario olvida la master password, puede usar uno de los recovery
codes generados durante el setup para hacer un reset guiado:
  1. Valida el recovery code contra los hashes almacenados.
  2. Marca el codigo como usado (no puede reutilizarse).
  3. Elimina vault.enc y lockout.json.
  4. Informa que debe correr `ghbackup setup` para reconfigurar.
"""
from __future__ import annotations

import click

from ghbackup.auth import recovery
from ghbackup.auth.lockout import record_success as lockout_reset
from ghbackup.auth import vault
from ghbackup.logging_.dual_logger import log_event
from ghbackup.ui import prompts
from ghbackup.ui.colors import error, header, info, success, warn


@click.command("recover")
def recover() -> None:
    """Recupera el acceso usando un recovery code (olvido de master password)."""
    header("ghbackup - Recuperacion de acceso")

    if not recovery.codes_exist():
        error(
            "No hay recovery codes almacenados. "
            "Posiblemente el setup fue realizado con una version anterior. "
            "Regenera el PAT en github.com y corre `ghbackup setup` de nuevo."
        )
        return

    remaining = recovery.remaining_count()
    if remaining == 0:
        warn("Todos los recovery codes ya fueron utilizados.")
        info("Regenera el PAT en github.com y corre `ghbackup setup` de nuevo.")
        return

    info(
        f"Tenes {remaining} recovery code(s) disponibles. "
        "Ingresa uno de los codigos que guardaste durante el setup. "
        "Formato: XXXXX-XXXXX-XXXXX-XXXXX-XXXXX (guiones opcionales)"
    )
    warn(
        "ATENCION: al usar un recovery code se eliminara el vault actual. "
        "Vas a necesitar generar un nuevo PAT en github.com para reconfigurar."
    )

    if not prompts.ask_confirm("Continuar con la recuperacion?", default=False):
        warn("Operacion cancelada.")
        return

    code = prompts.ask_text("Recovery code:").strip()
    if not code:
        error("No ingresaste ningun codigo.")
        return

    if not recovery.validate_and_consume(code):
        error(
            "Codigo invalido o ya utilizado. "
            f"Codigos restantes: {recovery.remaining_count()}"
        )
        log_event("recover_failed", result="error", extra={"reason": "invalid_code"})
        return

    # Codigo valido: limpiar vault y lockout
    vault.delete_vault()
    lockout_reset()

    log_event("recover_used", result="ok", extra={"codes_remaining": recovery.remaining_count()})

    success("Recovery code valido. Vault eliminado correctamente.")
    info(
        "Pasos para recuperar el acceso: "
        "1. Ve a https://github.com/settings/personal-access-tokens/new "
        "2. Genera un nuevo PAT con los mismos permisos. "
        "3. Corre: ghbackup setup "
        "(Tu historial en GitHub se preserva - solo se reconfigura la conexion local)"
    )
    remaining_after = recovery.remaining_count()
    if remaining_after > 0:
        warn(f"Te quedan {remaining_after} recovery code(s) disponibles. Guardalos en un lugar seguro.")
    else:
        warn("Usaste todos los recovery codes. Despues del setup se generaran nuevos codigos.")
