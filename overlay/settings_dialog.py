"""Диалог настройки биндов: захват новых комбинаций, сброс к умолчаниям."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from . import config, keymap

# --- Qt Key -> Win32 VK-код (только для глобальных биндов) ---
_QT_TO_VK: dict[int, int] = {}
for _ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    _QT_TO_VK[getattr(Qt, f"Key_{_ch}")] = ord(_ch)
for _i in range(1, 25):
    _QT_TO_VK[getattr(Qt, f"Key_F{_i}")] = 0x6F + _i  # VK_F1..VK_F24
_QT_TO_VK.update(
    {
        Qt.Key_Left: 0x25,
        Qt.Key_Up: 0x26,
        Qt.Key_Right: 0x27,
        Qt.Key_Down: 0x28,
        Qt.Key_Space: 0x20,
        Qt.Key_Escape: 0x1B,
        Qt.Key_Tab: 0x09,
        Qt.Key_Return: 0x0D,
        Qt.Key_Enter: 0x0D,
        Qt.Key_Backspace: 0x08,
        Qt.Key_Delete: 0x2E,
        Qt.Key_Insert: 0x2D,
        Qt.Key_Home: 0x24,
        Qt.Key_End: 0x23,
        Qt.Key_PageUp: 0x21,
        Qt.Key_PageDown: 0x22,
        Qt.Key_BracketLeft: 0xDB,
        Qt.Key_BracketRight: 0xDD,
    }
)

_MODIFIER_KEYS = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta}

_KEY_NAMES = {
    Qt.Key_Left: "Left",
    Qt.Key_Right: "Right",
    Qt.Key_Up: "Up",
    Qt.Key_Down: "Down",
    Qt.Key_Space: "Space",
    Qt.Key_Escape: "Esc",
    Qt.Key_Tab: "Tab",
    Qt.Key_Return: "Return",
    Qt.Key_Enter: "Enter",
    Qt.Key_Backspace: "Backspace",
    Qt.Key_Delete: "Delete",
    Qt.Key_Insert: "Insert",
    Qt.Key_Home: "Home",
    Qt.Key_End: "End",
    Qt.Key_PageUp: "PgUp",
    Qt.Key_PageDown: "PgDown",
    Qt.Key_BracketLeft: "[",
    Qt.Key_BracketRight: "]",
}
for _i in range(1, 25):
    _KEY_NAMES[getattr(Qt, f"Key_F{_i}")] = f"F{_i}"


def _key_display_name(key: int) -> str:
    if key in _KEY_NAMES:
        return _KEY_NAMES[key]
    if Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9:
        return chr(key)
    return QKeySequence(key).toString() or "?"


def _format_qt_text(mods: Qt.KeyboardModifier, key: int) -> str:
    parts = []
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    parts.append(_key_display_name(key))
    return "+".join(parts)


def _qt_modifiers_to_global(mods: Qt.KeyboardModifier) -> int:
    mod = 0
    if mods & Qt.ControlModifier:
        mod |= keymap.MOD_CONTROL
    if mods & Qt.AltModifier:
        mod |= keymap.MOD_ALT
    if mods & Qt.ShiftModifier:
        mod |= keymap.MOD_SHIFT
    return mod


class _ActionRow(QWidget):
    def __init__(self, action: keymap.Action, on_change, on_reset, parent=None):
        super().__init__(parent)
        self.action = action

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(action.label)
        label.setMinimumWidth(220)
        layout.addWidget(label, 1)

        self.key_label = QLabel()
        self.key_label.setMinimumWidth(150)
        self.key_label.setAlignment(Qt.AlignCenter)
        self.key_label.setStyleSheet(
            f"background-color: rgba(255,255,255,18); color: {config.TOOLBAR_TEXT}; "
            "border-radius: 6px; padding: 4px 8px;"
        )
        layout.addWidget(self.key_label)

        self.change_btn = QPushButton("Изменить")
        self.change_btn.clicked.connect(lambda: on_change(action.id))
        layout.addWidget(self.change_btn)

        self.reset_btn = QPushButton("Сбросить")
        self.reset_btn.clicked.connect(lambda: on_reset(action.id))
        layout.addWidget(self.reset_btn)

        self.set_text(keymap.current_qt_text(action.id))

    def set_text(self, text: str) -> None:
        self.key_label.setText(text)
        self.reset_btn.setEnabled(text != self.action.default_qt)

    def set_capturing(self, capturing: bool) -> None:
        self.change_btn.setText("Нажмите клавиши… (Esc — отмена)" if capturing else "Изменить")


class SettingsDialog(QDialog):
    """Окно настройки биндов. Живо применяет изменения к canvas/hotkeys."""

    def __init__(self, canvas, hotkeys, parent=None):
        super().__init__(parent)
        self.canvas = canvas
        self.hotkeys = hotkeys
        self._rows: dict[str, _ActionRow] = {}
        self._capturing_action_id: str | None = None

        self.setWindowTitle("DEDisplay — настройки клавиш")
        self.resize(560, 640)
        self.setStyleSheet(
            f"""
            QDialog, QScrollArea, QScrollArea > QWidget > QWidget {{
                background-color: #1c1c20;
            }}
            QLabel {{ color: {config.TOOLBAR_TEXT}; background-color: transparent; }}
            QPushButton {{
                background-color: rgba(255,255,255,18);
                color: {config.TOOLBAR_TEXT};
                border: none;
                border-radius: 6px;
                padding: 5px 10px;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,35); }}
            QPushButton:disabled {{ color: rgba(240,240,240,80); }}
            QScrollArea {{ border: none; }}
            """
        )

        outer = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(6)

        last_group = None
        for action in keymap.all_actions():
            if action.group != last_group:
                header = QLabel(action.group)
                header.setStyleSheet(
                    f"color: {config.TOOLBAR_ACCENT}; font-weight: bold; margin-top: 8px;"
                )
                content_layout.addWidget(header)
                last_group = action.group
            row = _ActionRow(action, self._on_change_clicked, self._on_reset_clicked)
            self._rows[action.id] = row
            content_layout.addWidget(row)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        reset_all_btn = QPushButton("Сбросить всё к умолчаниям")
        reset_all_btn.clicked.connect(self._reset_all)
        bottom.addWidget(reset_all_btn)
        bottom.addStretch(1)
        close_btn = QPushButton("Закрыть")
        close_btn.clicked.connect(self.close)
        bottom.addWidget(close_btn)
        outer.addLayout(bottom)

        QApplication.instance().installEventFilter(self)

    # --- открытие из трея ---
    def open_and_raise(self) -> None:
        self._cancel_capture()
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:
        self._cancel_capture()
        super().closeEvent(event)

    # --- захват новой комбинации ---
    def eventFilter(self, obj, event):
        if self._capturing_action_id is not None and event.type() == QEvent.KeyPress:
            self._handle_capture_key(event)
            return True
        return super().eventFilter(obj, event)

    def _on_change_clicked(self, action_id: str) -> None:
        if self._capturing_action_id == action_id:
            self._cancel_capture()
            return
        self._cancel_capture()
        self._capturing_action_id = action_id
        self._rows[action_id].set_capturing(True)

    def _cancel_capture(self) -> None:
        if self._capturing_action_id is not None:
            self._rows[self._capturing_action_id].set_capturing(False)
            self._capturing_action_id = None

    def _finish_capture(self, action_id: str, text: str) -> None:
        self._rows[action_id].set_capturing(False)
        self._rows[action_id].set_text(text)
        self._capturing_action_id = None

    def _handle_capture_key(self, event) -> None:
        key = event.key()
        if key in _MODIFIER_KEYS:
            return  # ждём основную клавишу
        mods = event.modifiers()
        if key == Qt.Key_Escape and mods == Qt.NoModifier:
            self._cancel_capture()
            return
        action_id = self._capturing_action_id
        action = keymap.get_action(action_id)
        if action.is_global:
            self._try_apply_global(action, mods, key)
        else:
            self._try_apply_local(action, mods, key)

    def _try_apply_local(self, action: keymap.Action, mods: Qt.KeyboardModifier, key: int) -> None:
        text = _format_qt_text(mods, key)
        conflict = keymap.find_local_conflict(text, action.id)
        if conflict is not None:
            self._cancel_capture()
            QMessageBox.warning(
                self, "Комбинация занята", f"«{text}» уже используется действием «{conflict.label}»."
            )
            return
        keymap.set_local_override(action.id, text)
        self.canvas.rebind_local(action.id, text)
        self._finish_capture(action.id, text)

    def _try_apply_global(self, action: keymap.Action, mods: Qt.KeyboardModifier, key: int) -> None:
        vk = _QT_TO_VK.get(key)
        mod = _qt_modifiers_to_global(mods)
        if vk is None:
            self._cancel_capture()
            QMessageBox.warning(self, "Неподдерживаемая клавиша", "Эту клавишу нельзя использовать для глобального бинда.")
            return
        if mod == 0:
            self._cancel_capture()
            QMessageBox.warning(
                self, "Нужен модификатор", "Глобальный бинд должен содержать Ctrl, Alt или Shift."
            )
            return
        conflict = keymap.find_global_conflict(mod, vk, action.id)
        if conflict is not None:
            self._cancel_capture()
            QMessageBox.warning(
                self, "Комбинация занята", f"Уже используется действием «{conflict.label}»."
            )
            return
        text = _format_qt_text(mods, key)
        old_mod, old_vk = keymap.current_global_mod_vk(action.id)
        ok = self.hotkeys.register_one(action.id, mod | keymap.MOD_NOREPEAT, vk)
        if not ok:
            self.hotkeys.register_one(action.id, old_mod | keymap.MOD_NOREPEAT, old_vk)
            self._cancel_capture()
            QMessageBox.warning(self, "Не удалось назначить", f"«{text}» уже занята другой программой.")
            return
        keymap.set_global_override(action.id, text, mod, vk)
        self._finish_capture(action.id, text)

    # --- сброс ---
    def _on_reset_clicked(self, action_id: str) -> None:
        self._cancel_capture()
        action = keymap.get_action(action_id)
        keymap.clear_override(action_id)
        if action.is_global:
            self.hotkeys.register_one(action_id, action.default_mod | keymap.MOD_NOREPEAT, action.default_vk)
        else:
            self.canvas.rebind_local(action_id, action.default_qt)
        self._rows[action_id].set_text(action.default_qt)

    def _reset_all(self) -> None:
        self._cancel_capture()
        keymap.clear_all()
        for action in keymap.GLOBAL_ACTIONS:
            self.hotkeys.register_one(action.id, action.default_mod | keymap.MOD_NOREPEAT, action.default_vk)
        for action in keymap.LOCAL_ACTIONS:
            self.canvas.rebind_local(action.id, action.default_qt)
        for action in keymap.all_actions():
            self._rows[action.id].set_text(action.default_qt)
