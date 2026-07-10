"""Хранение выбранного стиля оформления в JSON в %APPDATA%."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import config


def _config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "DEDisplay" / "style.json"


def load_style() -> str:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
        style = data.get("style")
    except (OSError, ValueError):
        style = None
    if style not in (config.STYLE_CLASSIC, config.STYLE_CALLIGRAPHY):
        return config.DEFAULT_STYLE
    return style


def save_style(style: str) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"style": style}, ensure_ascii=False, indent=2), encoding="utf-8")
