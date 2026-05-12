"""Definición de la CLI con click."""
from __future__ import annotations

import click

from ghbackup.version import __version__


@click.group(invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="ghbackup")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """ghbackup - Respaldo diferencial interactivo a GitHub.

    Si es la primera vez, corre `ghbackup setup`.
    Luego usá `ghbackup push` cuando quieras respaldar.
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


def build_cli() -> click.Group:
    """Importa y registra todos los subcomandos.

    Los comandos se importan acá (lazy) para que el .exe arranque rápido
    incluso cuando se llama solo a --help.
    """
    from ghbackup.commands import (
        config_cmd,
        log_cmd,
        push_cmd,
        restore_cmd,
        schedule_cmd,
        setup_cmd,
        status_cmd,
        verify_cmd,
    )

    cli.add_command(setup_cmd.setup)
    cli.add_command(push_cmd.push)
    cli.add_command(status_cmd.status)
    cli.add_command(restore_cmd.restore)
    cli.add_command(log_cmd.log)
    cli.add_command(config_cmd.config)
    cli.add_command(verify_cmd.verify)
    cli.add_command(schedule_cmd.schedule)
    return cli
