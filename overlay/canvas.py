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

# курсоры для ручек изменения размера выделения (по положению ручки на рамке)
_HANDLE_CURSORS = {
    ("l", "t"): Qt.SizeFDiagCursor, ("r", "b"): Qt.SizeFDiagCursor,
    ("r", "t"): Qt.SizeBDiagCursor, ("l", "b"): Qt.SizeBDiagCursor,
    ("c", "t"): Qt.SizeVerCursor, ("c", "b"): Qt.SizeVerCursor,
    ("l", "m"): Qt.SizeHorCursor, ("r", "m"): Qt.SizeHorCursor,
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
    selection_changed = Signal(bool)  # есть ли выделенные штрихи
    clipboard_changed = Signal(bool)  # есть ли что вставлять из буфера

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

        # --- изменение размера выделения за ручку ---
        self._resizing = False
        self._resize_handle: tuple[str, str] | None = None
        self._resize_bounds: QRectF | None = None
        # снимок геометрии на момент начала масштабирования: [(stroke, [точки], ширина)]
        self._resize_orig: list[tuple[Stroke, list[QPointF], float]] = []

        # --- буфер обмена штрихов (живёт на канвасе -> работает между страницами) ---
        self._clipboard: list[Stroke] = []

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
            "delete_selection": self.delete_selection,
            "copy": self.copy_selection,
            "paste": self.paste_clipboard,
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
        self._select_start = None
        self._select_current = None
        self._moving_selection = False
        self._resizing = False
        self._resize_handle = None
        self._resize_orig = []
        self._set_selection([])

    def _set_selection(self, strokes: list[Stroke]) -> None:
        self._selected_strokes = strokes
        self.selection_changed.emit(bool(strokes))

    # --- удаление / буфер обмена выделения ---
    def delete_selection(self) -> None:
        if not self._selected_strokes:
            return
        page = self.page_manager.current_page
        page.snapshot()
        marked = {id(s) for s in self._selected_strokes}
        page.strokes = [s for s in page.strokes if id(s) not in marked]
        self._clear_selection()
        self._emit_history()
        self.update()

    def copy_selection(self) -> None:
        if not self._selected_strokes:
            return
        self._clipboard = [s.copy() for s in self._selected_strokes]
        self.clipboard_changed.emit(True)

    def paste_clipboard(self) -> None:
        if not self._clipboard:
            return
        # выделение видно и редактируется только инструментом "перемещение"
        if self.tool != config.TOOL_MOVE:
            self.set_tool(config.TOOL_MOVE)
        page = self.page_manager.current_page
        page.snapshot()
        pasted: list[Stroke] = []
        for stroke in self._clipboard:
            clone = stroke.copy()
            clone.translate(config.PASTE_OFFSET, config.PASTE_OFFSET)
            page.strokes.append(clone)
            pasted.append(clone)
        self._set_selection(pasted)
        self._emit_history()
        self.update()

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
            if self._resizing:
                self._apply_resize(pos)
            elif self._moving_selection and self._drag_last_pos is not None:
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
            if self._resizing:
                self._resizing = False
                self._resize_handle = None
                self._resize_orig = []
                self._drag_last_pos = None
                self._emit_history()
            elif self._moving_selection:
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
        if not self.draw_mode:
            return
        if not self._pointer_down:
            # без нажатия — подсказываем курсором, что можно потянуть за ручку
            if self.tool == config.TOOL_MOVE:
                self._update_hover_cursor(event.position())
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
        # 1) ручка на рамке выделения -> изменение размера
        if self._selected_strokes:
            handle = self._handle_at(pos)
            if handle is not None:
                self._begin_resize(handle, pos, page)
                return
        # 2) клик по уже выделенному -> перемещение группы
        if any(stroke.hit_test(pos) for stroke in self._selected_strokes):
            page.snapshot()
            self._moving_selection = True
            self._drag_last_pos = pos
            return
        # 3) клик по штриху -> выделить его и двигать
        for stroke in reversed(page.strokes):
            if stroke.hit_test(pos):
                self._set_selection([stroke])
                page.snapshot()
                self._moving_selection = True
                self._drag_last_pos = pos
                self.update()
                return
        # 4) пустое место -> рамка выделения
        self._set_selection([])
        self._select_start = pos
        self._select_current = pos

    def _finish_selection_rect(self) -> None:
        rect = QRectF(self._select_start, self._select_current).normalized()
        self._select_start = None
        self._select_current = None
        page = self.page_manager.current_page
        self._set_selection([s for s in page.strokes if rect.intersects(s.bounding_rect())])
        self.update()

    # --- изменение размера выделения ---
    def _selection_bounds(self) -> QRectF | None:
        if not self._selected_strokes:
            return None
        rect = QRectF(self._selected_strokes[0].bounding_rect())
        for stroke in self._selected_strokes[1:]:
            rect = rect.united(stroke.bounding_rect())
        return rect

    @staticmethod
    def _handle_points(bounds: QRectF) -> dict[tuple[str, str], QPointF]:
        left, right = bounds.left(), bounds.right()
        top, bottom = bounds.top(), bounds.bottom()
        cx, cy = bounds.center().x(), bounds.center().y()
        return {
            ("l", "t"): QPointF(left, top), ("c", "t"): QPointF(cx, top), ("r", "t"): QPointF(right, top),
            ("l", "m"): QPointF(left, cy), ("r", "m"): QPointF(right, cy),
            ("l", "b"): QPointF(left, bottom), ("c", "b"): QPointF(cx, bottom), ("r", "b"): QPointF(right, bottom),
        }

    def _handle_at(self, pos: QPointF) -> tuple[str, str] | None:
        bounds = self._selection_bounds()
        if bounds is None:
            return None
        hit = config.SELECTION_HANDLE_HIT
        for key, pt in self._handle_points(bounds).items():
            if abs(pos.x() - pt.x()) <= hit and abs(pos.y() - pt.y()) <= hit:
                return key
        return None

    def _begin_resize(self, handle: tuple[str, str], pos: QPointF, page) -> None:
        bounds = self._selection_bounds()
        if bounds is None:
            return
        page.snapshot()
        self._resizing = True
        self._resize_handle = handle
        self._resize_bounds = bounds
        self._resize_orig = [(s, [QPointF(p) for p in s.points], s.width) for s in self._selected_strokes]
        self._drag_last_pos = pos

    def _apply_resize(self, pos: QPointF) -> None:
        bounds = self._resize_bounds
        hx, hy = self._resize_handle
        left, right, top, bottom = bounds.left(), bounds.right(), bounds.top(), bounds.bottom()

        # неподвижная сторона (anchor) — противоположная той, что тянем
        if hx == "l":
            ax, moving_x = right, left
        elif hx == "r":
            ax, moving_x = left, right
        else:  # "c" — по горизонтали не масштабируем
            ax, moving_x = left, None
        sx = (pos.x() - ax) / (moving_x - ax) if moving_x is not None and moving_x != ax else 1.0

        if hy == "t":
            ay, moving_y = bottom, top
        elif hy == "b":
            ay, moving_y = top, bottom
        else:  # "m" — по вертикали не масштабируем
            ay, moving_y = top, None
        sy = (pos.y() - ay) / (moving_y - ay) if moving_y is not None and moving_y != ay else 1.0

        # толщину линии тянем пропорционально: для угла — среднее осей, для стороны — по её оси
        if moving_x is not None and moving_y is not None:
            width_factor = (abs(sx) + abs(sy)) / 2
        else:
            width_factor = abs(sx) if moving_x is not None else abs(sy)

        for stroke, orig_points, orig_width in self._resize_orig:
            stroke.points = [QPointF(ax + (p.x() - ax) * sx, ay + (p.y() - ay) * sy) for p in orig_points]
            stroke.width = max(config.MIN_BRUSH_WIDTH, min(config.MAX_BRUSH_WIDTH, orig_width * width_factor))
        self.update()

    def _update_hover_cursor(self, pos: QPointF) -> None:
        handle = self._handle_at(pos) if self._selected_strokes else None
        if handle is not None:
            self.setCursor(QCursor(_HANDLE_CURSORS[handle]))
        else:
            self.setCursor(QCursor(_CURSORS.get(self.tool, Qt.ArrowCursor)))

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
        accent = QColor(config.TOOLBAR_ACCENT)
        pen = QPen(accent, 1, Qt.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        for stroke in self._selected_strokes:
            painter.drawRect(stroke.bounding_rect())

        # активная рамка выделения (протягивание) — без ручек
        if self._select_start is not None and self._select_current is not None:
            rect = QRectF(self._select_start, self._select_current).normalized()
            fill_color = QColor(accent)
            fill_color.setAlpha(40)
            painter.fillRect(rect, fill_color)
            painter.setPen(pen)
            painter.drawRect(rect)
            return

        # общая рамка выделения с ручками изменения размера
        bounds = self._selection_bounds()
        if bounds is not None:
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(bounds)
            half = config.SELECTION_HANDLE_SIZE / 2
            painter.setPen(QPen(accent, 1, Qt.SolidLine))
            painter.setBrush(QColor("#ffffff"))
            for pt in self._handle_points(bounds).values():
                painter.drawRect(QRectF(pt.x() - half, pt.y() - half, 2 * half, 2 * half))

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
