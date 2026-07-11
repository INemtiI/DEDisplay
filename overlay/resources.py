"""Резолвер путей к ресурсам — работает и из исходников, и из PyInstaller-бандла."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(name: str) -> Path:
    """Абсолютный путь к ресурсу `name`.

    В обычном запуске — относительно корня проекта. В собранном --onefile exe
    PyInstaller распаковывает вложенные файлы во временную папку `sys._MEIPASS`.
    """
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        return Path(base) / name
    # overlay/resources.py -> корень проекта на уровень выше
    return Path(__file__).resolve().parent.parent / name
