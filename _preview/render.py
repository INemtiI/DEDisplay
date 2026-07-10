"""Оффскрин-рендер тулбара и переключателя страниц в каллиграфическом режиме
для визуальной проверки порта дизайна. Запуск:
    QT_QPA_PLATFORM=offscreen python _preview/render.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor
from PySide6.QtCore import QPointF

from overlay import config
from overlay.toolbar import Toolbar
from overlay.page_switcher import PageSwitcher

app = QApplication(sys.argv)
OUT = os.path.dirname(os.path.abspath(__file__))


def grab(widget, name, bg="#3a3f47", elapsed=5.0, hover_checked=True):
    widget.set_style(config.STYLE_CALLIGRAPHY)
    # заставить «дыхание»/прорисовку быть завершёнными
    widget._anim_start = time.monotonic() - elapsed
    # у выбранных/наведённых кнопок показать завиток (в оффскрине таймеры не тикают)
    if hover_checked:
        for attr in ("_ornate_buttons", "_page_buttons"):
            for b in getattr(widget, attr, []):
                if b.isCheckable() and b.isChecked():
                    b._hover_progress = 1.0
        for well in getattr(widget, "_color_wells", []):
            if well._selected:
                well._progress = 1.0
    widget.adjustSize()
    w, h = widget.width(), widget.height()
    pm = widget.grab()
    img = QImage(w, h, QImage.Format_ARGB32)
    img.fill(QColor(bg))
    p = QPainter(img)
    p.drawPixmap(0, 0, pm)
    p.end()
    path = os.path.join(OUT, name)
    img.save(path)
    print(f"{name}: {w}x{h}")


tb = Toolbar()
grab(tb, "toolbar_callig.png")

ps = PageSwitcher()
ps.set_pages(5, 0)
grab(ps, "pageswitcher_callig.png")

# также мид-прорисовка тулбара (эффект «рисования тушью»)
tb2 = Toolbar()
grab(tb2, "toolbar_drawing.png", elapsed=0.55, hover_checked=False)

print("done")
