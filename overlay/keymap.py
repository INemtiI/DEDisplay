"""Реестр всех переназначаемых биндов (глобальных и локальных) + их
пользовательские переопределения, сохраняемые в JSON в %APPDATA%."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from . import config

# --- модификаторы/VK для глобальных хоткеев (Win32 RegisterHotKey) ---
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000

VK_D = 0x44
VK_H = 0x48
VK_Q = 0x51
VK_B = 0x42
VK_SPACE = 0x20
VK_LEFT = 0x25
VK_RIGHT = 0x27
VK_1 = 0x31  # VK_1..VK_5 = 0x31..0x35

# --- идентификаторы действий ---
TOGGLE_DRAW = "toggle_draw"
TOGGLE_UI = "toggle_ui"
TOGGLE_UI_SPACE = "toggle_ui_space"
HIDE_ALL = "hide_all"
QUIT = "quit"
PREV_PAGE = "prev_page"
NEXT_PAGE = "next_page"
PAGE_PREFIX = "page_"  # page_1 .. page_N

GROUP_GLOBAL = "Глобальные"
GROUP_LOCAL = "Инструменты и цвета"


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    group: str
    is_global: bool
    default_qt: str  # для локальных — строка QKeySequence; для глобальных — только для отображения
    default_mod: int = 0  # только для глобальных (без MOD_NOREPEAT)
    default_vk: int = 0  # только для глобальных


GLOBAL_ACTIONS: list[Action] = [
    Action(TOGGLE_DRAW, "Режим рисования / клики", GROUP_GLOBAL, True, "Ctrl+Alt+D", MOD_CONTROL | MOD_ALT, VK_D),
    Action(TOGGLE_UI, "Показать/скрыть панель", GROUP_GLOBAL, True, "Ctrl+Alt+H", MOD_CONTROL | MOD_ALT, VK_H),
    Action(TOGGLE_UI_SPACE, "Показать/скрыть панель (2)", GROUP_GLOBAL, True, "Ctrl+Space", MOD_CONTROL, VK_SPACE),
    Action(HIDE_ALL, "Скрыть всё и выйти из рисования", GROUP_GLOBAL, True, "Ctrl+B", MOD_CONTROL, VK_B),
    Action(QUIT, "Выход", GROUP_GLOBAL, True, "Ctrl+Alt+Q", MOD_CONTROL | MOD_ALT, VK_Q),
    Action(PREV_PAGE, "Предыдущая страница", GROUP_GLOBAL, True, "Ctrl+Alt+Left", MOD_CONTROL | MOD_ALT, VK_LEFT),
    Action(NEXT_PAGE, "Следующая страница", GROUP_GLOBAL, True, "Ctrl+Alt+Right", MOD_CONTROL | MOD_ALT, VK_RIGHT),
]
for _i in range(config.INITIAL_PAGE_COUNT):
    GLOBAL_ACTIONS.append(
        Action(
            f"{PAGE_PREFIX}{_i + 1}",
            f"Страница {_i + 1}",
            GROUP_GLOBAL,
            True,
            f"Ctrl+Alt+{_i + 1}",
            MOD_CONTROL | MOD_ALT,
            VK_1 + _i,
        )
    )

LOCAL_ACTIONS: list[Action] = [
    Action("tool_pen", "Инструмент: карандаш", GROUP_LOCAL, False, "B"),
    Action("tool_eraser", "Инструмент: ластик", GROUP_LOCAL, False, "E"),
    Action("tool_move", "Инструмент: перемещение", GROUP_LOCAL, False, "V"),
    Action("undo", "Отменить", GROUP_LOCAL, False, "Ctrl+Z"),
    Action("redo_primary", "Повторить", GROUP_LOCAL, False, "Ctrl+Y"),
    Action("redo_secondary", "Повторить (доп.)", GROUP_LOCAL, False, "Ctrl+Shift+Z"),
    Action("width_inc", "Толщина кисти +", GROUP_LOCAL, False, "]"),
    Action("width_dec", "Толщина кисти -", GROUP_LOCAL, False, "["),
    Action("color_red", "Цвет: красный", GROUP_LOCAL, False, "R"),
    Action("color_black", "Цвет: чёрный", GROUP_LOCAL, False, "G"),
    Action("color_white", "Цвет: белый", GROUP_LOCAL, False, "W"),
    Action("clear_page", "Очистить страницу", GROUP_LOCAL, False, "Ctrl+E"),
    Action("exit_draw_mode", "Выйти из рисования", GROUP_LOCAL, False, "Esc"),
]

_BY_ID: dict[str, Action] = {a.id: a for a in (*GLOBAL_ACTIONS, *LOCAL_ACTIONS)}


def all_actions() -> list[Action]:
    return [*GLOBAL_ACTIONS, *LOCAL_ACTIONS]


def get_action(action_id: str) -> Action:
    return _BY_ID[action_id]


# --- хранилище переопределений ---
def _config_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "DEDisplay" / "keybinds.json"


_overrides: dict[str, dict] | None = None


def _ensure_loaded() -> dict[str, dict]:
    global _overrides
    if _overrides is None:
        path = _config_path()
        try:
            _overrides = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            _overrides = {}
    return _overrides


def _save() -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_overrides, ensure_ascii=False, indent=2), encoding="utf-8")


def current_qt_text(action_id: str) -> str:
    overrides = _ensure_loaded()
    entry = overrides.get(action_id)
    if entry is not None:
        return entry["qt"]
    return get_action(action_id).default_qt


def current_global_mod_vk(action_id: str) -> tuple[int, int]:
    overrides = _ensure_loaded()
    entry = overrides.get(action_id)
    if entry is not None:
        return entry["mod"], entry["vk"]
    action = get_action(action_id)
    return action.default_mod, action.default_vk


def set_local_override(action_id: str, qt_text: str) -> None:
    overrides = _ensure_loaded()
    overrides[action_id] = {"qt": qt_text}
    _save()


def set_global_override(action_id: str, qt_text: str, mod: int, vk: int) -> None:
    overrides = _ensure_loaded()
    overrides[action_id] = {"qt": qt_text, "mod": mod, "vk": vk}
    _save()


def clear_override(action_id: str) -> None:
    overrides = _ensure_loaded()
    if overrides.pop(action_id, None) is not None:
        _save()


def clear_all() -> None:
    global _overrides
    _overrides = {}
    _save()


def get_global_bindings() -> dict[str, tuple[int, int]]:
    result = {}
    for action in GLOBAL_ACTIONS:
        mod, vk = current_global_mod_vk(action.id)
        result[action.id] = (mod | MOD_NOREPEAT, vk)
    return result


def find_local_conflict(qt_text: str, exclude_id: str) -> Action | None:
    for action in LOCAL_ACTIONS:
        if action.id == exclude_id:
            continue
        if current_qt_text(action.id) == qt_text:
            return action
    return None


def find_global_conflict(mod: int, vk: int, exclude_id: str) -> Action | None:
    for action in GLOBAL_ACTIONS:
        if action.id == exclude_id:
            continue
        cur_mod, cur_vk = current_global_mod_vk(action.id)
        if cur_mod == mod and cur_vk == vk:
            return action
    return None
