"""Иконка в системном трее с меню управления приложением."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import config


class TrayIcon(QSystemTrayIcon):
    toggle_draw_mode_requested = Signal()
    toggle_ui_requested = Signal()
    settings_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(self._make_icon(), parent)
        self.setToolTip("DEDisplay")

        menu = QMenu()
        self.draw_action = QAction("Режим рисования", menu)
        self.draw_action.setCheckable(True)
        self.draw_action.triggered.connect(lambda: self.toggle_draw_mode_requested.emit())
        menu.addAction(self.draw_action)

        toggle_ui_action = QAction("Показать/скрыть панель", menu)
        toggle_ui_action.triggered.connect(lambda: self.toggle_ui_requested.emit())
        menu.addAction(toggle_ui_action)

        settings_action = QAction("Настройки клавиш…", menu)
        settings_action.triggered.connect(lambda: self.settings_requested.emit())
        menu.addAction(settings_action)

        menu.addSeparator()
        quit_action = QAction("Выход", menu)
        quit_action.triggered.connect(lambda: self.quit_requested.emit())
        menu.addAction(quit_action)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_draw_mode_requested.emit()

    def set_draw_mode(self, enabled: bool) -> None:
        self.draw_action.setChecked(enabled)

    @staticmethod
    def _make_icon() -> QIcon:
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(config.TOOLBAR_ACCENT))
        painter.drawEllipse(4, 4, 56, 56)
        painter.setPen(QPen(QColor("#111111"), 6, Qt.SolidLine, Qt.RoundCap))
        painter.drawLine(20, 44, 44, 20)
        painter.end()
        return QIcon(pixmap)
