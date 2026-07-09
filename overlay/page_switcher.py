"""Виджет внизу слева экрана для переключения страниц."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from . import config


class PageSwitcher(QWidget):
    page_selected = Signal(int)
    add_page_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._page_buttons: list[QPushButton] = []
        self._drag_offset = None
        self._user_positioned = False
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(10, 8, 10, 8)
        self._layout.setSpacing(6)

        self.add_btn = QPushButton("+")
        self.add_btn.setFixedSize(26, 26)
        self.add_btn.clicked.connect(self.add_page_requested)
        self._layout.addWidget(self.add_btn)

        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(255,255,255,18);
                color: {config.TOOLBAR_TEXT};
                border: none;
                border-radius: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,35); }}
            QPushButton:checked {{ background-color: {config.TOOLBAR_ACCENT}; color: #111111; }}
            """
        )
        self._position()

    def set_pages(self, count: int, current_index: int) -> None:
        for btn in self._page_buttons:
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._page_buttons.clear()
        self._layout.removeWidget(self.add_btn)

        for i in range(count):
            btn = QPushButton(str(i + 1))
            btn.setCheckable(True)
            btn.setFixedSize(26, 26)
            btn.setChecked(i == current_index)
            btn.clicked.connect(lambda _checked, idx=i: self.page_selected.emit(idx))
            self._layout.addWidget(btn)
            self._page_buttons.append(btn)

        self._layout.addWidget(self.add_btn)
        if not self._user_positioned:
            self._position()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 28, 32, 220))
        painter.drawRoundedRect(self.rect(), 16, 16)

    def _position(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().geometry()
        x = screen.x() + 16
        y = screen.y() + screen.height() - self.height() - 16
        self.move(x, y)

    # --- перетаскивание панели за фон ---
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            self._user_positioned = True
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)
