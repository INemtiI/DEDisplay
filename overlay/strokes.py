"""Модель данных: штрихи, страницы и менеджер страниц (всё в памяти)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor

from . import config

UNDO_LIMIT = 50


class Stroke:
    """Один нарисованный штрих: ломаная линия с цветом, толщиной и нажатием
    пера в каждой точке (для мыши нажатие всегда 1.0 — толщина не меняется)."""

    __slots__ = ("points", "pressures", "color", "width")

    def __init__(self, points: list[QPointF], color: QColor, width: float, pressures: list[float] | None = None):
        self.points = points
        self.pressures = pressures if pressures is not None else [1.0] * len(points)
        self.color = QColor(color)
        self.width = width

    def add_point(self, point: QPointF, pressure: float = 1.0) -> None:
        self.points.append(point)
        self.pressures.append(pressure)

    def copy(self) -> "Stroke":
        return Stroke([QPointF(p) for p in self.points], QColor(self.color), self.width, list(self.pressures))

    def translate(self, dx: float, dy: float) -> None:
        self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]

    def bounding_rect(self) -> QRectF:
        if not self.points:
            return QRectF()
        xs = [p.x() for p in self.points]
        ys = [p.y() for p in self.points]
        pad = self.width / 2 + config.ERASER_HIT_PADDING
        return QRectF(min(xs) - pad, min(ys) - pad, max(xs) - min(xs) + 2 * pad, max(ys) - min(ys) + 2 * pad)

    def hit_test(self, pos: QPointF, extra_padding: float = 0.0) -> bool:
        """Проверяет, попадает ли точка в допуск от штриха (для ластика/move)."""
        if not self.bounding_rect().adjusted(-extra_padding, -extra_padding, extra_padding, extra_padding).contains(pos):
            return False
        tolerance = self.width / 2 + config.ERASER_HIT_PADDING + extra_padding
        if len(self.points) == 1:
            return _dist(pos, self.points[0]) <= tolerance
        for a, b in zip(self.points, self.points[1:]):
            if _point_segment_distance(pos, a, b) <= tolerance:
                return True
        return False


def _dist(p: QPointF, q: QPointF) -> float:
    return ((p.x() - q.x()) ** 2 + (p.y() - q.y()) ** 2) ** 0.5


def _point_segment_distance(p: QPointF, a: QPointF, b: QPointF) -> float:
    ax, ay = a.x(), a.y()
    bx, by = b.x(), b.y()
    px, py = p.x(), p.y()
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    if length_sq == 0:
        return _dist(p, a)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    proj = QPointF(ax + t * dx, ay + t * dy)
    return _dist(p, proj)


class Page:
    """Одна рабочая область: список штрихов + история для undo/redo."""

    def __init__(self):
        self.strokes: list[Stroke] = []
        self._undo_stack: list[list[Stroke]] = []
        self._redo_stack: list[list[Stroke]] = []

    def snapshot(self) -> None:
        """Сохраняет текущее состояние в undo-стек перед деструктивной операцией."""
        self._undo_stack.append([s.copy() for s in self.strokes])
        if len(self._undo_stack) > UNDO_LIMIT:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        self._redo_stack.append([s.copy() for s in self.strokes])
        self.strokes = self._undo_stack.pop()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        self._undo_stack.append([s.copy() for s in self.strokes])
        self.strokes = self._redo_stack.pop()
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)


class PageManager:
    """Держит все страницы сессии и текущий индекс. Ничего не пишет на диск."""

    def __init__(self, initial_count: int = config.INITIAL_PAGE_COUNT):
        self.pages: list[Page] = [Page() for _ in range(initial_count)]
        self.current_index: int = 0

    @property
    def current_page(self) -> Page:
        return self.pages[self.current_index]

    @property
    def count(self) -> int:
        return len(self.pages)

    def add_page(self) -> int:
        self.pages.append(Page())
        self.current_index = len(self.pages) - 1
        return self.current_index

    def switch_to(self, index: int) -> bool:
        if 0 <= index < len(self.pages):
            self.current_index = index
            return True
        return False

    def next_page(self) -> int:
        self.current_index = (self.current_index + 1) % len(self.pages)
        return self.current_index

    def prev_page(self) -> int:
        self.current_index = (self.current_index - 1) % len(self.pages)
        return self.current_index
