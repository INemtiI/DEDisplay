"""Глобальные хоткеи через WinAPI RegisterHotKey + перехват WM_HOTKEY в Qt."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Signal

WM_HOTKEY = 0x0312


class HotkeyManager(QObject, QAbstractNativeEventFilter):
    """Регистрирует глобальные хоткеи и эмиттит имя сработавшего бинда."""

    hotkey_triggered = Signal(str)

    def __init__(self, parent=None):
        QObject.__init__(self, parent)
        QAbstractNativeEventFilter.__init__(self)
        self._id_to_name: dict[int, str] = {}
        self._name_to_id: dict[str, int] = {}
        self._next_id = 1
        self._available = sys.platform == "win32"

    def register_all(self, bindings: dict[str, tuple[int, int]]) -> list[str]:
        """Регистрирует все бинды, возвращает имена тех, что не удалось занять."""
        failed: list[str] = []
        if not self._available:
            return list(bindings.keys())
        for name, (modifiers, vk) in bindings.items():
            if not self.register_one(name, modifiers, vk):
                failed.append(name)
        return failed

    def register_one(self, name: str, modifiers: int, vk: int) -> bool:
        """Регистрирует один бинд под именем `name` (переопределяя прежний)."""
        if not self._available:
            return False
        self.unregister(name)
        user32 = ctypes.windll.user32
        hotkey_id = self._next_id
        self._next_id += 1
        if user32.RegisterHotKey(None, hotkey_id, modifiers, vk):
            self._id_to_name[hotkey_id] = name
            self._name_to_id[name] = hotkey_id
            return True
        return False

    def unregister(self, name: str) -> None:
        """Снимает регистрацию одного бинда по имени, если он был зарегистрирован."""
        hotkey_id = self._name_to_id.pop(name, None)
        if hotkey_id is None:
            return
        if self._available:
            ctypes.windll.user32.UnregisterHotKey(None, hotkey_id)
        self._id_to_name.pop(hotkey_id, None)

    def unregister_all(self) -> None:
        if not self._available:
            return
        user32 = ctypes.windll.user32
        for hotkey_id in list(self._id_to_name):
            user32.UnregisterHotKey(None, hotkey_id)
        self._id_to_name.clear()
        self._name_to_id.clear()

    def nativeEventFilter(self, event_type, message):
        if self._available and int(message):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                name = self._id_to_name.get(msg.wParam)
                if name:
                    self.hotkey_triggered.emit(name)
        return False, 0
