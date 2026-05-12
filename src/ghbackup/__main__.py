"""Entrypoint del ejecutable.

Cuando se compila con PyInstaller --onefile, este es el archivo que arranca.
"""
from __future__ import annotations

import sys
import traceback

from colorama import init as colorama_init

from ghbackup.cli import build_cli
from ghbackup.ui.colors import error


def main() -> int:
    colorama_init(autoreset=True)
    try:
        cli = build_cli()
        cli(standalone_mode=False)
        return 0
    except KeyboardInterrupt:
        error("\nOperación cancelada por el usuario.")
        return 130
    except SystemExit as exc:
        return int(exc.code) if exc.code is not None else 0
    except Exception as exc:  # noqa: BLE001
        error(f"Error inesperado: {exc}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
