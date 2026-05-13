"""Helpers de prompts interactivos (questionary)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import questionary


def ask_text(message: str, default: str = "", validate: Any = None) -> str:
    return str(questionary.text(message, default=default, validate=validate).unsafe_ask())


def ask_password(message: str) -> str:
    return str(questionary.password(message).unsafe_ask())


def ask_confirm(message: str, default: bool = True) -> bool:
    return bool(questionary.confirm(message, default=default).unsafe_ask())


def ask_choice(message: str, choices: Iterable[str], default: str | None = None) -> str:
    return str(questionary.select(message, choices=list(choices), default=default).unsafe_ask())


def ask_checkbox(message: str, choices: Iterable[str]) -> list[str]:
    return list(questionary.checkbox(message, choices=list(choices)).unsafe_ask())


def ask_summary_action() -> str:
    """Prompt usado tras mostrar el resumen de cambios antes del push.

    Devuelve uno de: 'yes' | 'no' | 'detail' | 'select'.
    """
    answer = questionary.select(
        "¿Qué hacés con estos cambios?",
        choices=[
            questionary.Choice("[Y] Subir todo", value="yes"),
            questionary.Choice("[D] Ver detalle archivo por archivo", value="detail"),
            questionary.Choice("[S] Seleccionar manualmente cuáles incluir", value="select"),
            questionary.Choice("[N] Cancelar y no subir nada", value="no"),
        ],
    ).unsafe_ask()
    return str(answer)
