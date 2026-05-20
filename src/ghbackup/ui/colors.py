"""Helpers de impresión con colores (colorama)."""

from __future__ import annotations

from colorama import Fore, Style


def info(msg: str) -> None:
    print(f"{Fore.CYAN}{msg}{Style.RESET_ALL}")


def success(msg: str) -> None:
    print(f"{Fore.GREEN}{msg}{Style.RESET_ALL}")


def warn(msg: str) -> None:
    print(f"{Fore.YELLOW}{msg}{Style.RESET_ALL}")


def error(msg: str) -> None:
    print(f"{Fore.RED}{msg}{Style.RESET_ALL}")


def header(msg: str) -> None:
    bar = "=" * max(len(msg), 60)
    print(f"\n{Fore.MAGENTA}{Style.BRIGHT}{bar}\n{msg}\n{bar}{Style.RESET_ALL}")


def dim(msg: str) -> None:
    print(f"{Style.DIM}{msg}{Style.RESET_ALL}")
