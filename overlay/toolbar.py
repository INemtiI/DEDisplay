"""Плавающая минималистичная панель инструментов (всегда кликабельна)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QPushButton, QSlider, QWidget

from . import config

_TOOL_LABELS = {
    config.TOOL_PEN: "✏",  # ✏
    config.TOOL_ERASER: "⌫",  # ⌫
    config.TOOL_MOVE: "✋",  # ✋
}


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setStyleSheet("color: rgba(255,255,255,40);")
    return line


class Toolbar(QWidget):
    tool_selected = Signal(str)
    color_selected = Signal(QColor)
    brush_width_changed = Signal(float)
    undo_requested = Signal()
    redo_requested = Signal()
    clear_page_requested = Signal()
    add_page_requested = Signal()
    toggle_draw_mode_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._color_buttons: list[tuple[QColor, QPushButton]] = []
        self._tool_buttons: dict[str, QPushButton] = {}
        self._drag_offset = None
        self._build_ui()
        self._position()

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)

        self.draw_toggle_btn = QPushButton("● Рисование")
        self.draw_toggle_btn.setCheckable(True)
        self.draw_toggle_btn.clicked.connect(self.toggle_draw_mode_requested)
        layout.addWidget(self.draw_toggle_btn)
        layout.addWidget(_separator())

        tool_group = QButtonGroup(self)
        tool_group.setExclusive(True)
        for tool, label in _TOOL_LABELS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setFixedWidth(34)
            btn.clicked.connect(lambda _checked, t=tool: self.tool_selected.emit(t))
            tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            layout.addWidget(btn)
        self._tool_buttons[config.DEFAULT_TOOL].setChecked(True)
        self._tool_group = tool_group

        layout.addWidget(_separator())

        for color in config.PALETTE:
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(20, 20)
            btn.clicked.connect(lambda _checked, c=color: self._on_color_clicked(c))
            self._color_buttons.append((color, btn))
            layout.addWidget(btn)
        self._refresh_color_buttons(config.DEFAULT_COLOR)

        layout.addWidget(_separator())

        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setMinimum(int(config.MIN_BRUSH_WIDTH))
        self.width_slider.setMaximum(int(config.MAX_BRUSH_WIDTH))
        self.width_slider.setValue(int(config.DEFAULT_BRUSH_WIDTH))
        self.width_slider.setFixedWidth(80)
        self.width_slider.valueChanged.connect(lambda v: self.brush_width_changed.emit(float(v)))
        layout.addWidget(self.width_slider)

        layout.addWidget(_separator())

        self.undo_btn = QPushButton("↶")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_requested)
        layout.addWidget(self.undo_btn)

        self.redo_btn = QPushButton("↷")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo_requested)
        layout.addWidget(self.redo_btn)

        layout.addWidget(_separator())

        self.clear_btn = QPushButton("🗑")
        self.clear_btn.clicked.connect(self.clear_page_requested)
        layout.addWidget(self.clear_btn)

        layout.addWidget(_separator())

        self.add_page_btn = QPushButton("+ страница")
        self.add_page_btn.clicked.connect(self.add_page_requested)
        layout.addWidget(self.add_page_btn)

        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: rgba(255,255,255,18);
                color: {config.TOOLBAR_TEXT};
                border: none;
                border-radius: 6px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{ background-color: rgba(255,255,255,35); }}
            QPushButton:checked {{ background-color: {config.TOOLBAR_ACCENT}; color: #111111; }}
            QPushButton:disabled {{ color: rgba(240,240,240,80); }}
            """
        )

    def _on_color_clicked(self, color: QColor) -> None:
        self._refresh_color_buttons(color)
        self.color_selected.emit(color)

    def _refresh_color_buttons(self, selected_color: QColor) -> None:
        # цвет фона задаётся инлайн-стилем на каждой кнопке, поэтому подсветку
        # выбранного цвета нужно перерисовывать вручную через border, а не
        # полагаться на QPushButton:checked из общего стиля панели
        for c, btn in self._color_buttons:
            selected = c == selected_color
            btn.setChecked(selected)
            border = f"3px solid {config.TOOLBAR_ACCENT}" if selected else "1px solid rgba(255,255,255,60)"
            btn.setStyleSheet(
                f"background-color: {c.name()}; border-radius: 10px; border: {border};"
            )

    def set_color(self, color: QColor) -> None:
        self._refresh_color_buttons(color)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(28, 28, 32, 220))
        painter.drawRoundedRect(self.rect(), 14, 14)

    def _position(self) -> None:
        self.adjustSize()
        screen = QGuiApplication.primaryScreen().geometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + 16
        self.move(x, y)

    # --- перетаскивание панели за фон (клик по кнопкам её не запускает,
    # т.к. они сами обрабатывают mousePress/Release) ---
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.LeftButton and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    # --- внешняя синхронизация состояния ---
    def set_tool(self, tool: str) -> None:
        btn = self._tool_buttons.get(tool)
        if btn is not None:
            btn.setChecked(True)

    def set_draw_mode(self, enabled: bool) -> None:
        self.draw_toggle_btn.setChecked(enabled)
        self.draw_toggle_btn.setText(
            "● Рисование" if enabled
            else "○ Клики проходят"
        )

    def set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self.undo_btn.setEnabled(can_undo)
        self.redo_btn.setEnabled(can_redo)
