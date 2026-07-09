"""Прозрачный полноэкранный оверлей: рисование, ластик, перемещение штрихов."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys

from PySide6.QtCore import QEvent, Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QWidget

from . import config, keymap
from .strokes import PageManager, Stroke


def _pressure_width_factor(pressure: float) -> float:
    return config.PRESSURE_MIN_FACTOR + (1 - config.PRESSURE_MIN_FACTOR) * pressure


_CURSORS = {
    config.TOOL_PEN: Qt.CrossCursor,
    config.TOOL_ERASER: Qt.PointingHandCursor,
    config.TOOL_MOVE: Qt.SizeAllCursor,
}

# Qt's WA_TransparentForMouseEvents не всегда надёжно переприменяется "на лету"
# для уже показанного полноэкранного frameless-окна на Windows, поэтому
# click-through дополнительно принудительно выставляется через WinAPI.
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SWP_FRAMECHANGED = 0x0020


class OverlayCanvas(QWidget):
    history_changed = Signal(bool, bool)  # can_undo, can_redo
    draw_mode_changed = Signal(bool)
    tool_changed = Signal(str)
    color_changed = Signal(QColor)
    brush_width_changed = Signal(float)

    def __init__(self, page_manager: PageManager, parent=None):
        super().__init__(parent)
        self.page_manager = page_manager

        self.tool = config.DEFAULT_TOOL
        self.color = QColor(config.DEFAULT_COLOR)
        self.brush_width = config.DEFAULT_BRUSH_WIDTH
        self.draw_mode = False

        self._current_stroke: Stroke | None = None
        self._drag_last_pos: QPointF | None = None
        self._pointer_down = False

        # --- выделение области и групповое перемещение (инструмент Move) ---
        self._selected_strokes: list[Stroke] = []
        self._select_start: QPointF | None = None
        self._select_current: QPointF | None = None
        self._moving_selection = False

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.StrongFocus)

        screen = QGuiApplication.primaryScreen()
        self.setGeometry(screen.geometry())

        self._shortcuts: dict[str, QShortcut] = {}
        self._setup_shortcuts()
        self._update_cursor()
        self._apply_click_through(True)

    def _apply_click_through(self, click_through: bool) -> None:
        """Принудительно выставляет/снимает WS_EX_TRANSPARENT напрямую через WinAPI."""
        if sys.platform != "win32":
            return
        user32 = ctypes.windll.user32
        user32.GetWindowLongW.restype = ctypes.c_long
        user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.SetWindowLongW.restype = ctypes.c_long
        user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            ctypes.c_uint,
        ]

        hwnd = wintypes.HWND(int(self.winId()))
        style = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        if click_through:
            style |= _WS_EX_LAYERED | _WS_EX_TRANSPARENT
        else:
            style = (style | _WS_EX_LAYERED) & ~_WS_EX_TRANSPARENT
        user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, style)
        # без SWP_FRAMECHANGED Windows может не применить новый extended style
        # немедленно для уже показанного окна
        user32.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE | _SWP_FRAMECHANGED,
        )

    # --- настройка локальных шорткатов (активны только в фокусе, т.е. в draw mode) ---
    def _setup_shortcuts(self) -> None:
        slots = {
            "tool_pen": lambda: self.set_tool(config.TOOL_PEN),
            "tool_eraser": lambda: self.set_tool(config.TOOL_ERASER),
            "tool_move": lambda: self.set_tool(config.TOOL_MOVE),
            "undo": self.undo,
            "redo_primary": self.redo,
            "redo_secondary": self.redo,
            "width_inc": self.increase_brush_width,
            "width_dec": self.decrease_brush_width,
            "color_red": lambda: self.set_color(config.COLOR_RED),
            "color_black": lambda: self.set_color(config.COLOR_BLACK),
            "color_white": lambda: self.set_color(config.COLOR_WHITE),
            "clear_page": self.clear_page,
            "exit_draw_mode": lambda: self.set_draw_mode(False),
        }
        for action in keymap.LOCAL_ACTIONS:
            sc = QShortcut(QKeySequence(keymap.current_qt_text(action.id)), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(slots[action.id])
            self._shortcuts[action.id] = sc

    def rebind_local(self, action_id: str, qt_text: str) -> None:
        """Переназначает локальный шорткат "на лету" (без пересоздания QShortcut)."""
        sc = self._shortcuts.get(action_id)
        if sc is not None:
            sc.setKey(QKeySequence(qt_text))

    # --- режим рисование / click-through ---
    def set_draw_mode(self, enabled: bool) -> None:
        self.draw_mode = enabled
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        self._apply_click_through(not enabled)
        if enabled:
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.OtherFocusReason)
        self.draw_mode_changed.emit(enabled)

    def toggle_draw_mode(self) -> None:
        self.set_draw_mode(not self.draw_mode)

    # --- инструменты ---
    def set_tool(self, tool: str) -> None:
        self.tool = tool
        self._current_stroke = None
        self._drag_last_pos = None
        self._clear_selection()
        self._update_cursor()
        self.tool_changed.emit(tool)

    def set_color(self, color: QColor) -> None:
        self.color = QColor(color)
        self.color_changed.emit(self.color)

    def set_brush_width(self, width: float) -> None:
        self.brush_width = max(config.MIN_BRUSH_WIDTH, min(config.MAX_BRUSH_WIDTH, width))
        self.brush_width_changed.emit(self.brush_width)

    def increase_brush_width(self) -> None:
        self.set_brush_width(self.brush_width + config.BRUSH_WIDTH_STEP)

    def decrease_brush_width(self) -> None:
        self.set_brush_width(self.brush_width - config.BRUSH_WIDTH_STEP)

    def _update_cursor(self) -> None:
        self.setCursor(QCursor(_CURSORS.get(self.tool, Qt.ArrowCursor)))

    # --- страницы ---
    def set_page(self, index: int) -> None:
        if self.page_manager.switch_to(index):
            self._current_stroke = None
            self._drag_last_pos = None
            self._clear_selection()
            self.update()
            self._emit_history()

    # --- undo/redo ---
    def undo(self) -> None:
        if self.page_manager.current_page.undo():
            self.update()
        self._emit_history()

    def redo(self) -> None:
        if self.page_manager.current_page.redo():
            self.update()
        self._emit_history()

    def _emit_history(self) -> None:
        page = self.page_manager.current_page
        self.history_changed.emit(page.can_undo, page.can_redo)

    def clear_page(self) -> None:
        page = self.page_manager.current_page
        if not page.strokes:
            return
        page.snapshot()
        page.strokes.clear()
        self._current_stroke = None
        self._drag_last_pos = None
        self._clear_selection()
        self._emit_history()
        self.update()

    def _clear_selection(self) -> None:
        self._selected_strokes = []
        self._select_start = None
        self._select_current = None
        self._moving_selection = False

    # --- общая логика указателя (мышь и перо планшета) ---
    def _begin_stroke(self, pos: QPointF, pressure: float) -> None:
        if self.tool == config.TOOL_PEN:
            self._current_stroke = Stroke([pos], self.color, self.brush_width, [pressure])
        elif self.tool == config.TOOL_ERASER:
            self._erase_at(pos)
        elif self.tool == config.TOOL_MOVE:
            self._start_move(pos)
        self.update()

    def _continue_stroke(self, pos: QPointF, pressure: float) -> None:
        if self.tool == config.TOOL_PEN and self._current_stroke is not None:
            self._current_stroke.add_point(pos, pressure)
            self.update()
        elif self.tool == config.TOOL_ERASER:
            self._erase_at(pos)
        elif self.tool == config.TOOL_MOVE:
            if self._moving_selection and self._drag_last_pos is not None:
                dx = pos.x() - self._drag_last_pos.x()
                dy = pos.y() - self._drag_last_pos.y()
                for stroke in self._selected_strokes:
                    stroke.translate(dx, dy)
                self._drag_last_pos = pos
                self.update()
            elif self._select_start is not None:
                self._select_current = pos
                self.update()

    def _end_stroke(self) -> None:
        if self.tool == config.TOOL_PEN and self._current_stroke is not None:
            page = self.page_manager.current_page
            page.snapshot()
            page.strokes.append(self._current_stroke)
            self._current_stroke = None
            self._emit_history()
            self.update()
        elif self.tool == config.TOOL_MOVE:
            if self._moving_selection:
                self._moving_selection = False
                self._drag_last_pos = None
                self._emit_history()
            elif self._select_start is not None:
                self._finish_selection_rect()

    # --- события мыши (нажатие всегда полное — 1.0) ---
    def mousePressEvent(self, event) -> None:
        if not self.draw_mode:
            return
        self._pointer_down = True
        self._begin_stroke(event.position(), 1.0)

    def mouseMoveEvent(self, event) -> None:
        if not self.draw_mode or not self._pointer_down:
            return
        self._continue_stroke(event.position(), 1.0)

    def mouseReleaseEvent(self, event) -> None:
        if not self.draw_mode:
            return
        self._pointer_down = False
        self._end_stroke()

    # --- события пера графического планшета (реальное нажатие 0..1) ---
    def tabletEvent(self, event) -> None:
        if not self.draw_mode:
            return
        event_type = event.type()
        if event_type == QEvent.TabletPress:
            self._pointer_down = True
            self._begin_stroke(event.position(), event.pressure())
        elif event_type == QEvent.TabletMove:
            if self._pointer_down:
                self._continue_stroke(event.position(), event.pressure())
        elif event_type == QEvent.TabletRelease:
            self._pointer_down = False
            self._end_stroke()
        event.accept()

    def _erase_at(self, pos: QPointF) -> None:
        page = self.page_manager.current_page
        hit_index = None
        for i, stroke in enumerate(page.strokes):
            if stroke.hit_test(pos):
                hit_index = i
                break
        if hit_index is None:
            return
        page.snapshot()
        del page.strokes[hit_index]
        self._emit_history()
        self.update()

    def _start_move(self, pos: QPointF) -> None:
        page = self.page_manager.current_page
        if any(stroke.hit_test(pos) for stroke in self._selected_strokes):
            page.snapshot()
            self._moving_selection = True
            self._drag_last_pos = pos
            return
        for stroke in reversed(page.strokes):
            if stroke.hit_test(pos):
                self._selected_strokes = [stroke]
                page.snapshot()
                self._moving_selection = True
                self._drag_last_pos = pos
                self.update()
                return
        self._selected_strokes = []
        self._select_start = pos
        self._select_current = pos

    def _finish_selection_rect(self) -> None:
        rect = QRectF(self._select_start, self._select_current).normalized()
        self._select_start = None
        self._select_current = None
        page = self.page_manager.current_page
        self._selected_strokes = [s for s in page.strokes if rect.intersects(s.bounding_rect())]
        self.update()

    # --- отрисовка ---
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        # У layered-окна (WA_TranslucentBackground на Windows использует
        # UpdateLayeredWindow) полностью прозрачные (alpha=0) пиксели сами по
        # себе не получают клики мыши — это НЕ зависит от WS_EX_TRANSPARENT.
        # Поэтому заливаем весь фон почти невидимым alpha=1, чтобы окно везде
        # считалось "непрозрачным" для хит-теста, но визуально не отличалось
        # от полностью прозрачного.
        painter.fillRect(self.rect(), QColor(0, 0, 0, 1))
        for stroke in self.page_manager.current_page.strokes:
            self._draw_stroke(painter, stroke)
        if self._current_stroke is not None:
            self._draw_stroke(painter, self._current_stroke)
        if self.tool == config.TOOL_MOVE:
            self._draw_selection(painter)
        painter.end()

    def _draw_selection(self, painter: QPainter) -> None:
        pen = QPen(QColor(config.TOOLBAR_ACCENT), 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for stroke in self._selected_strokes:
            painter.drawRect(stroke.bounding_rect())
        if self._select_start is not None and self._select_current is not None:
            rect = QRectF(self._select_start, self._select_current).normalized()
            fill_color = QColor(config.TOOLBAR_ACCENT)
            fill_color.setAlpha(40)
            painter.fillRect(rect, fill_color)
            painter.setPen(pen)
            painter.drawRect(rect)

    @staticmethod
    def _draw_stroke(painter: QPainter, stroke: Stroke) -> None:
        if len(stroke.points) == 1:
            width = stroke.width * _pressure_width_factor(stroke.pressures[0])
            painter.setPen(QPen(stroke.color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPoint(stroke.points[0])
            return
        # рисуем сегментами, чтобы толщина линии плавно менялась вместе с
        # нажатием пера вдоль штриха (для мыши нажатие всегда 1.0, толщина
        # получается постоянной, как и раньше)
        for i in range(len(stroke.points) - 1):
            pressure = (stroke.pressures[i] + stroke.pressures[i + 1]) / 2
            width = stroke.width * _pressure_width_factor(pressure)
            painter.setPen(QPen(stroke.color, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawLine(stroke.points[i], stroke.points[i + 1])
