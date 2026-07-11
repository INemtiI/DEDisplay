"""Плавающая минималистичная панель инструментов (всегда кликабельна)."""

from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QSlider, QWidget

from . import calligraphy, config
from .ornate_button import OrnateButton

# монохромные глифы (без emoji-варианта), чтобы текст рисовался золотой тушью
_TOOL_LABELS = {
    config.TOOL_PEN: "✎",   # карандаш
    config.TOOL_ERASER: "⌫",  # стереть
    config.TOOL_MOVE: "✥",   # перемещение
}

# отступы содержимого панели
_CLASSIC_MARGINS = (14, 10, 14, 10)
_CALLIG_PAD = 12  # зазор между рамкой и кнопками


class InkSeparator(QWidget):
    """Разделитель: тонкая линия в классике, рукописный штрих в каллиграфии."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._style = config.STYLE_CLASSIC
        self.setFixedWidth(10)

    def set_style(self, style: str) -> None:
        self._style = style
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self._style == config.STYLE_CALLIGRAPHY:
            h = rect.height() * 0.7
            dr = QRectF(rect.center().x() - 5, rect.center().y() - h / 2, 10, h)
            calligraphy.draw_divider(painter, dr)
        else:
            painter.setPen(QColor(255, 255, 255, 40))
            cx = rect.center().x()
            painter.drawLine(cx, rect.y() + 6, cx, rect.bottom() - 6)


class ColorWell(QPushButton):
    """Чернильница: цветной блик + рукописное золотое кольцо при выборе/наведении."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self._color = color
        self._style = config.STYLE_CLASSIC
        self._selected = False
        self._progress = 0.0
        self.setCheckable(True)
        self.setFixedSize(22, 22)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._on_tick)

    def color(self) -> QColor:
        return self._color

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.setChecked(selected)
        if self._style == config.STYLE_CALLIGRAPHY:
            self.update()

    def set_style(self, style: str) -> None:
        self._style = style
        if style == config.STYLE_CALLIGRAPHY:
            self.setStyleSheet("background: transparent; border: none;")
            self._timer.start()
        else:
            self._timer.stop()
            self._progress = 0.0
        self.update()

    def _on_tick(self) -> None:
        target = 1.0 if (self._selected or self.underMouse()) else 0.0
        self._progress += (target - self._progress) * 0.28
        if abs(target - self._progress) < 0.002:
            self._progress = target
        self.update()

    def paintEvent(self, event) -> None:
        if self._style != config.STYLE_CALLIGRAPHY:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        # органичная капля туши выбранного цвета
        blob = min(rect.width(), rect.height()) * (0.5 if self._selected or self.underMouse() else 0.46)
        center = rect.center()
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawEllipse(center, blob / 2, blob / 2 * 0.92)
        # рукописное кольцо
        ring_rect = rect.adjusted(1, 1, -1, -1)
        progress = max(self._progress, 1.0 if self._selected else 0.0)
        calligraphy.draw_well_ring(painter, ring_rect, progress)


def _slider_stylesheet(style: str) -> str:
    if style != config.STYLE_CALLIGRAPHY:
        return ""
    return f"""
        QSlider::groove:horizontal {{
            background: rgba(210,169,94,40); height: 2px; border-radius: 1px;
        }}
        QSlider::sub-page:horizontal {{
            background: rgba(210,169,94,140); height: 2px; border-radius: 1px;
        }}
        QSlider::handle:horizontal {{
            background: {calligraphy.GOLD_BRIGHT}; width: 13px; height: 13px;
            margin: -6px 0; border-radius: 6px; border: 1px solid {calligraphy.GOLD};
        }}
    """


class Toolbar(QWidget):
    tool_selected = Signal(str)
    color_selected = Signal(QColor)
    brush_width_changed = Signal(float)
    undo_requested = Signal()
    redo_requested = Signal()
    copy_requested = Signal()
    paste_requested = Signal()
    clear_page_requested = Signal()
    add_page_requested = Signal()
    toggle_draw_mode_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._style = config.STYLE_CLASSIC
        self._selected_color = config.DEFAULT_COLOR
        self._color_wells: list[ColorWell] = []
        self._tool_buttons: dict[str, QPushButton] = {}
        self._ornate_buttons: list[OrnateButton] = []
        self._separators: list[InkSeparator] = []
        self._drag_offset = None
        self._anim_start = time.monotonic()
        self._glow = 0.0                 # текущая яркость «фонарика» 0..1
        self._mouse_local = None         # позиция курсора в координатах панели

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(33)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        self._build_ui()
        self._position()

    # Активная зона «приближения» курсора вокруг панели (px).
    _GLOW_MARGIN = 70

    def _on_anim_tick(self) -> None:
        self._update_glow()
        self.update()

    def _update_glow(self) -> None:
        local = self.mapFromGlobal(QCursor.pos())
        self._mouse_local = QPointF(local)
        r = self.rect()
        if r.contains(local):
            target = 1.0
        else:
            dx = max(r.left() - local.x(), 0, local.x() - r.right())
            dy = max(r.top() - local.y(), 0, local.y() - r.bottom())
            dist = math.hypot(dx, dy)
            target = max(0.0, 1.0 - dist / self._GLOW_MARGIN)
        self._glow += (target - self._glow) * 0.18
        if abs(target - self._glow) < 0.004:
            self._glow = target

    def _add_separator(self, layout) -> None:
        sep = InkSeparator()
        self._separators.append(sep)
        layout.addWidget(sep)

    def _build_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(*_CLASSIC_MARGINS)
        layout.setSpacing(8)

        self.draw_toggle_btn = OrnateButton("● Рисование", tier="full")
        self.draw_toggle_btn.setCheckable(True)
        self.draw_toggle_btn.clicked.connect(self.toggle_draw_mode_requested)
        self._ornate_buttons.append(self.draw_toggle_btn)
        layout.addWidget(self.draw_toggle_btn)
        self._add_separator(layout)

        tool_group = QButtonGroup(self)
        tool_group.setExclusive(True)
        for tool, label in _TOOL_LABELS.items():
            btn = OrnateButton(label, tier="mini")
            btn.setCheckable(True)
            btn.setFixedWidth(36)
            btn.clicked.connect(lambda _checked, t=tool: self.tool_selected.emit(t))
            tool_group.addButton(btn)
            self._tool_buttons[tool] = btn
            self._ornate_buttons.append(btn)
            layout.addWidget(btn)
        self._tool_buttons[config.DEFAULT_TOOL].setChecked(True)
        self._tool_group = tool_group

        self._add_separator(layout)

        for color in config.PALETTE:
            well = ColorWell(color)
            well.clicked.connect(lambda _checked, c=color: self._on_color_clicked(c))
            self._color_wells.append(well)
            layout.addWidget(well)
        self._refresh_color_buttons(config.DEFAULT_COLOR)

        self._add_separator(layout)

        self.width_slider = QSlider(Qt.Horizontal)
        self.width_slider.setMinimum(int(config.MIN_BRUSH_WIDTH))
        self.width_slider.setMaximum(int(config.MAX_BRUSH_WIDTH))
        self.width_slider.setValue(int(config.DEFAULT_BRUSH_WIDTH))
        self.width_slider.setFixedWidth(80)
        self.width_slider.valueChanged.connect(lambda v: self.brush_width_changed.emit(float(v)))
        layout.addWidget(self.width_slider)

        self._add_separator(layout)

        self.undo_btn = OrnateButton("↶", tier="mini")
        self.undo_btn.setEnabled(False)
        self.undo_btn.clicked.connect(self.undo_requested)
        self._ornate_buttons.append(self.undo_btn)
        layout.addWidget(self.undo_btn)

        self.redo_btn = OrnateButton("↷", tier="mini")
        self.redo_btn.setEnabled(False)
        self.redo_btn.clicked.connect(self.redo_requested)
        self._ornate_buttons.append(self.redo_btn)
        layout.addWidget(self.redo_btn)

        self._add_separator(layout)

        self.copy_btn = OrnateButton("⧉", tier="mini")
        self.copy_btn.setToolTip("Копировать выделенное (Ctrl+C)")
        self.copy_btn.setEnabled(False)
        self.copy_btn.clicked.connect(self.copy_requested)
        self._ornate_buttons.append(self.copy_btn)
        layout.addWidget(self.copy_btn)

        self.paste_btn = OrnateButton("⧈", tier="mini")
        self.paste_btn.setToolTip("Вставить (Ctrl+V)")
        self.paste_btn.setEnabled(False)
        self.paste_btn.clicked.connect(self.paste_requested)
        self._ornate_buttons.append(self.paste_btn)
        layout.addWidget(self.paste_btn)

        self._add_separator(layout)

        self.clear_btn = OrnateButton("✕", tier="mini")
        self.clear_btn.clicked.connect(self.clear_page_requested)
        self._ornate_buttons.append(self.clear_btn)
        layout.addWidget(self.clear_btn)

        self._add_separator(layout)

        self.add_page_btn = OrnateButton("+ страница", tier="full")
        self.add_page_btn.clicked.connect(self.add_page_requested)
        self._ornate_buttons.append(self.add_page_btn)
        layout.addWidget(self.add_page_btn)

        self._apply_classic_stylesheet()

    def _apply_classic_stylesheet(self) -> None:
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
        self._selected_color = selected_color
        calligraphy_mode = self._style == config.STYLE_CALLIGRAPHY
        for well in self._color_wells:
            selected = well.color() == selected_color
            well.set_selected(selected)
            if not calligraphy_mode:
                ring = config.TOOLBAR_ACCENT
                border = f"3px solid {ring}" if selected else "1px solid rgba(255,255,255,60)"
                well.setStyleSheet(
                    f"background-color: {well.color().name()}; border-radius: 11px; border: {border};"
                )

    def set_color(self, color: QColor) -> None:
        self._refresh_color_buttons(color)

    def set_style(self, style: str) -> None:
        if style == self._style:
            return
        self._style = style
        for btn in self._ornate_buttons:
            btn.set_style(style)
        for sep in self._separators:
            sep.set_style(style)
        for well in self._color_wells:
            well.set_style(style)
        self.width_slider.setStyleSheet(_slider_stylesheet(style))
        if style == config.STYLE_CLASSIC:
            self._apply_classic_stylesheet()
            self._anim_timer.stop()
            self.layout().setContentsMargins(*_CLASSIC_MARGINS)
        else:
            self.setStyleSheet("")  # каллиграфические кнопки рисуют себя сами
            self._anim_start = time.monotonic()
            self._anim_timer.start()
            self._apply_calligraphy_layout()
        self._refresh_color_buttons(self._selected_color)
        self.adjustSize()
        self._position()
        self.update()

    def _apply_calligraphy_layout(self) -> None:
        layout = self.layout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.activate()
        hint = layout.sizeHint()
        mx, my = calligraphy.layout_margins(
            hint.width(), hint.height(),
            calligraphy.FRAME_LARGE_VIEWBOX, calligraphy.FRAME_LARGE_BOX, pad=_CALLIG_PAD,
        )
        layout.setContentsMargins(mx, my, mx, my)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._style == config.STYLE_CALLIGRAPHY:
            self._anim_start = time.monotonic()  # проиграть прорисовку заново

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())
        if self._style == config.STYLE_CALLIGRAPHY:
            # полупрозрачная тёмно-коричневая заливка внутри рамки + золотой орнамент
            elapsed = time.monotonic() - self._anim_start
            calligraphy.draw_frame_large(painter, rect.adjusted(2, 2, -2, -2), elapsed,
                                         mouse_pos=self._mouse_local, glow=self._glow)
        else:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(28, 28, 32, 220))
            painter.drawRoundedRect(rect, 14, 14)

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

    def set_copy_enabled(self, enabled: bool) -> None:
        self.copy_btn.setEnabled(enabled)

    def set_paste_enabled(self, enabled: bool) -> None:
        self.paste_btn.setEnabled(enabled)
