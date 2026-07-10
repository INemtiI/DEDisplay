"""Кнопка с каллиграфическим оформлением. В классическом режиме — обычная
QPushButton (рендер через QSS). В каллиграфическом — рисует поверх прозрачного
фона рукописный завиток (для кнопок-инструментов) или чернильное кольцо (для
номеров страниц), прорисовывающиеся при наведении/активности, и золотой
serif-italic текст с переходом цвета primary -> accent. Логика/сигналы кнопки
не меняются."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, QTimer
from PySide6.QtGui import QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QPushButton

from . import calligraphy, config

_TIMER_INTERVAL_MS = 33
_HOVER_SMOOTHING = 0.28

# Виды орнамента кнопки
ORN_FLOURISH = "flourish"  # завиток-овал (инструменты, текстовые кнопки)
ORN_RING = "ring"          # чернильное кольцо (номера страниц, «+»)


class OrnateButton(QPushButton):
    def __init__(self, text: str = "", *, tier: str = "full", ornament: str = ORN_FLOURISH, parent=None):
        super().__init__(text, parent)
        self._tier = tier
        self._ornament = ornament
        self._style = config.STYLE_CLASSIC
        self._hover_progress = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(_TIMER_INTERVAL_MS)
        self._timer.timeout.connect(self._on_tick)

    def set_style(self, style: str) -> None:
        if style == self._style:
            return
        self._style = style
        if style == config.STYLE_CALLIGRAPHY:
            self._timer.start()
        else:
            self._timer.stop()
            self._hover_progress = 0.0
        self.update()

    # --- сглаживание наведения ---
    def _on_tick(self) -> None:
        target = self._hover_target()
        self._hover_progress += (target - self._hover_progress) * _HOVER_SMOOTHING
        if abs(target - self._hover_progress) < 0.002:
            self._hover_progress = target
            # активная кнопка держит орнамент — таймер не глушим,
            # иначе не будет плавного схлопывания при снятии активности
        self.update()

    def _hover_target(self) -> float:
        if self.isDown() or self.underMouse():
            return 1.0
        if self.isCheckable() and self.isChecked():
            return 1.0
        return 0.0

    def sizeHint(self) -> QSize:
        base = super().sizeHint()
        if self._style != config.STYLE_CALLIGRAPHY:
            return base
        # крупный serif-шрифт шире исходного — учитываем, иначе текст обрежется
        fm = QFontMetricsF(self._text_font())
        pad_w, pad_h = (30, 16) if self._tier == "full" else (16, 10)
        w = int(fm.horizontalAdvance(self.text())) + pad_w
        h = int(fm.height()) + pad_h
        return QSize(max(base.width(), w), max(base.height(), h))

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if self._style == config.STYLE_CALLIGRAPHY:
            self.update()

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        if self._style == config.STYLE_CALLIGRAPHY:
            self.update()

    # --- отрисовка ---
    def paintEvent(self, event) -> None:
        if self._style != config.STYLE_CALLIGRAPHY:
            super().paintEvent(event)
            return
        self._paint_calligraphy()

    def _paint_calligraphy(self) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        dim = 1.0 if self.isEnabled() else 0.4
        hover = self._hover_progress

        if self._ornament == ORN_RING:
            side = min(rect.width(), rect.height())
            ring_rect = QRectF(0, 0, side, side)
            ring_rect.moveCenter(rect.center())
            calligraphy.draw_ring(painter, ring_rect.adjusted(1, 1, -1, -1), hover * dim)
        else:
            calligraphy.draw_flourish(painter, rect.adjusted(2, 3, -2, -3), hover * dim)

        if self.text():
            color = calligraphy.lerp_color(calligraphy.GOLD, calligraphy.GOLD_BRIGHT, hover)
            calligraphy.draw_label(painter, rect, self.text(), self._text_font(), color, dim)

    def _text_font(self) -> QFont:
        if self._tier == "full":
            return calligraphy.make_font(self.font(), italic=True, size_pt=max(self.font().pointSizeF(), 12.0))
        # мелкие кнопки-иконки: символы читаемее без наклона
        return calligraphy.make_font(self.font(), italic=False, size_pt=max(self.font().pointSizeF(), 11.0), bold=True)
