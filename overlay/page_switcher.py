"""Виджет внизу слева экрана для переключения страниц."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QHBoxLayout, QWidget

from . import calligraphy, config
from .ornate_button import ORN_RING, OrnateButton

_CLASSIC_MARGINS = (10, 8, 10, 8)
_CALLIG_PAD = 10


class PageSwitcher(QWidget):
    page_selected = Signal(int)
    add_page_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._style = config.STYLE_CLASSIC
        self._page_buttons: list[OrnateButton] = []
        self._drag_offset = None
        self._user_positioned = False
        self._anim_start = time.monotonic()

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self.update)

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(*_CLASSIC_MARGINS)
        self._layout.setSpacing(6)

        self.add_btn = OrnateButton("+", tier="full", ornament=ORN_RING)
        self.add_btn.setFixedSize(28, 28)
        self.add_btn.clicked.connect(self.add_page_requested)
        self._layout.addWidget(self.add_btn)

        self._apply_classic_stylesheet()
        self._position()

    def _apply_classic_stylesheet(self) -> None:
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

    def set_pages(self, count: int, current_index: int) -> None:
        for btn in self._page_buttons:
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._page_buttons.clear()
        self._layout.removeWidget(self.add_btn)

        for i in range(count):
            btn = OrnateButton(str(i + 1), tier="mini", ornament=ORN_RING)
            btn.setCheckable(True)
            btn.setFixedSize(28, 28)
            btn.setChecked(i == current_index)
            btn.clicked.connect(lambda _checked, idx=i: self.page_selected.emit(idx))
            btn.set_style(self._style)
            self._layout.addWidget(btn)
            self._page_buttons.append(btn)

        self._layout.addWidget(self.add_btn)
        if self._style == config.STYLE_CALLIGRAPHY:
            self._apply_calligraphy_layout()
        if not self._user_positioned:
            self._position()

    def set_style(self, style: str) -> None:
        if style == self._style:
            return
        self._style = style
        self.add_btn.set_style(style)
        for btn in self._page_buttons:
            btn.set_style(style)
        if style == config.STYLE_CLASSIC:
            self._apply_classic_stylesheet()
            self._anim_timer.stop()
            self._layout.setContentsMargins(*_CLASSIC_MARGINS)
        else:
            self.setStyleSheet("")  # каллиграфические кнопки рисуют себя сами
            self._anim_start = time.monotonic()
            self._anim_timer.start()
            self._apply_calligraphy_layout()
        self.adjustSize()
        self._position()
        self.update()

    def _apply_calligraphy_layout(self) -> None:
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.activate()
        hint = self._layout.sizeHint()
        mx, my = calligraphy.layout_margins(
            hint.width(), hint.height(),
            calligraphy.FRAME_SMALL_VIEWBOX, calligraphy.FRAME_SMALL_BOX, pad=_CALLIG_PAD,
        )
        self._layout.setContentsMargins(mx, my, mx, my)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._style == config.STYLE_CALLIGRAPHY:
            self._anim_start = time.monotonic()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self._style == config.STYLE_CALLIGRAPHY:
            # фон прозрачный — рисуем только золотую рамку и орнамент
            elapsed = time.monotonic() - self._anim_start
            calligraphy.draw_frame_small(painter, rect.adjusted(2, 2, -2, -2), elapsed)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(28, 28, 32, 220))
            painter.drawRoundedRect(rect, 16, 16)

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
