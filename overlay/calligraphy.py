"""Каллиграфический стиль оформления: рукописная золотая тушь на тёмном
пергаменте — прорисовывающиеся штрихом рамки-росчерки, чернильные брызги,
мерцающие искры и живое «дыхание» орнамента.

Портировано из веб-прототипа (components/ink-ornaments.tsx): геометрия рамок,
завитков, колец и искр взята из тех же SVG-path данных, а эффекты —
«живая кисть» (turbulence), прорисовка штриха (stroke-dashoffset),
дыхание и всплеск брызг — воспроизведены средствами QPainter.

Соответствие вебу:
  * FlourishFrame   -> FRAME_LARGE   (рамка тулбара)
  * SmallFrame      -> FRAME_SMALL   (рамка панели страниц)
  * HoverFlourish   -> FLOURISH      (завиток кнопки при наведении)
  * InkRing         -> RING          (кольцо номера страницы)
  * InkDivider      -> DIVIDER       (рукописный разделитель)
  * Sparkle         -> SPARKLE       (искра)
  * чернильное кольцо чернильницы -> WELL_RING
"""

from __future__ import annotations

import math
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPainterPath,
    QPen,
    QRadialGradient,
    QTransform,
)

# --- Палитра (из globals.css :root — «мистическая каллиграфия») ---
INK_BG = "#17110c"        # база пергамента панели
PARCHMENT = "#1c150e"     # чуть светлее — заливка
GOLD = "#d2a95e"          # --primary: основная тушь
GOLD_BRIGHT = "#f1e0af"   # --accent: при наведении/активности
GOLD_DIM = "#a68c62"      # --muted-foreground: приглушённый
GOLD_TEXT = "#ead9b5"     # --foreground

# Обратная совместимость со старыми именами (используются в toolbar/page_switcher)
GOLD_PRIMARY = GOLD
GOLD_HIGHLIGHT = GOLD_BRIGHT
PARCHMENT_BG = PARCHMENT

# --- Полу-прозрачная заливка внутри рамки (для читаемости текста) ---
FILL_BROWN = "#241608"    # тёмно-коричневый фон панели под текстом
FILL_ALPHA = 0.82         # базовая непрозрачность заливки (читается и на тёмном фоне)
# «Фонарик»: тёплая подсветка у курсора — осветляет фон совсем немного
GLOW_TINT = "#c79a5a"     # цвет света
GLOW_ALPHA = 0.15         # пиковая непрозрачность подсветки (в центре)
GLOW_RADIUS = 130.0       # радиус пятна света, px

# --- Анимационные константы ---
DRAW_DURATION = 1.6       # с — длительность прорисовки одного штриха
DRAW_STAGGER = 0.08       # с — задержка между соседними штрихами рамки
BREATHE_PERIOD = 5.0      # с — период «дыхания» орнамента
SPARKLE_PERIOD = 2.6      # с — период мерцания искры


# ---------------------------------------------------------------------------
#  Разбор SVG-path (поддерживаются команды M и C — как в исходных данных)
# ---------------------------------------------------------------------------
_TOKEN_RE = re.compile(r"([MC])([^MC]*)")
_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def parse_svg_path(d: str) -> QPainterPath:
    path = QPainterPath()
    for cmd, argstr in _TOKEN_RE.findall(d):
        nums = [float(n) for n in _NUM_RE.findall(argstr)]
        if cmd == "M":
            path.moveTo(nums[0], nums[1])
        elif cmd == "C":
            for i in range(0, len(nums), 6):
                x1, y1, x2, y2, x, y = nums[i : i + 6]
                path.cubicTo(x1, y1, x2, y2, x, y)
    return path


# ---------------------------------------------------------------------------
#  Геометрия орнаментов (viewBox + список path-строк + брызги)
# ---------------------------------------------------------------------------

# Большая рамка тулбара (FlourishFrame). viewBox="-40 -10 908 180"
_FRAME_LARGE_VIEWBOX = (-40.0, -10.0, 908.0, 180.0)
_FRAME_LARGE_D = [
    "M60 34 C 140 18, 220 22, 290 30 C 312 33, 328 25, 336 16 C 344 25, 358 33, 378 29 "
    "C 394 26, 406 25, 414 25 C 422 25, 434 26, 450 29 C 470 33, 484 25, 492 16 "
    "C 500 25, 516 33, 538 30 C 608 22, 688 18, 768 34",
    "M60 126 C 140 142, 220 138, 290 130 C 312 127, 328 135, 336 144 C 344 135, 358 127, 378 131 "
    "C 394 134, 406 135, 414 135 C 422 135, 434 134, 450 131 C 470 127, 484 135, 492 144 "
    "C 500 135, 516 127, 538 130 C 608 138, 688 142, 768 126",
    "M60 34 C 40 66, 40 94, 60 126",
    "M768 34 C 788 66, 788 94, 768 126",
    "M60 34 C 42 20, 26 24, 28 40 C 29 50, 44 50, 42 38 C 41 31, 33 32, 35 38",
    "M768 34 C 786 20, 802 24, 800 40 C 801 50, 786 50, 788 38 C 789 31, 797 32, 795 38",
    "M60 126 C 42 140, 26 136, 28 120 C 29 110, 44 110, 42 122 C 41 129, 33 130, 35 122",
    "M768 126 C 786 140, 802 136, 800 120 C 801 110, 786 110, 788 122 C 789 129, 797 130, 795 122",
    "M28 40 C 4 22, -16 16, -26 36 C -30 45, -22 52, -14 48",
    "M800 40 C 824 22, 844 16, 854 36 C 858 45, 850 52, 842 48",
    "M28 120 C 4 138, -16 144, -26 124 C -30 115, -22 108, -14 112",
    "M800 120 C 824 138, 844 144, 854 124 C 858 115, 850 108, 842 112",
    "M400 16 C 392 8, 380 10, 382 18 C 384 25, 396 24, 398 17 C 400 10, 412 8, 420 14 C 426 19, 418 26, 412 22",
    "M400 144 C 392 152, 380 150, 382 142 C 384 135, 396 136, 398 143 C 400 150, 412 152, 420 146 C 426 141, 418 134, 412 138",
]
_FRAME_LARGE_SPLATS = [
    (-30.0, 24.0, 2.0), (-18.0, 58.0, 1.3), (858.0, 24.0, 2.0), (846.0, 58.0, 1.3),
    (-30.0, 136.0, 2.0), (858.0, 136.0, 2.0), (401.0, 4.0, 1.4), (401.0, 156.0, 1.4),
]
# Основной прямоугольник рамки (без выносных росчерков) — по нему считаем отступы.
_FRAME_LARGE_BOX = (60.0, 34.0, 708.0, 92.0)
# Позиции искр (в координатах viewBox) и их фазовые сдвиги.
_FRAME_LARGE_SPARKLES = [(150.0, 8.0, 0.4), (712.0, 12.0, 1.6), (300.0, 150.0, 2.4)]

# Малая рамка панели страниц (SmallFrame). viewBox="-28 -4 556 108"
_FRAME_SMALL_VIEWBOX = (-28.0, -4.0, 556.0, 108.0)
_FRAME_SMALL_D = [
    "M40 22 C 100 12, 180 14, 250 20 C 270 22, 284 16, 292 10 C 300 16, 314 22, 334 20 C 380 16, 420 14, 460 22",
    "M40 78 C 100 88, 180 86, 250 80 C 270 78, 284 84, 292 90 C 300 84, 314 78, 334 80 C 380 84, 420 86, 460 78",
    "M40 22 C 26 42, 26 58, 40 78",
    "M460 22 C 474 42, 474 58, 460 78",
    "M40 22 C 26 12, 14 16, 16 28 C 17 36, 28 36, 26 27",
    "M460 22 C 474 12, 486 16, 484 28 C 483 36, 472 36, 474 27",
    "M40 78 C 26 88, 14 84, 16 72 C 17 64, 28 64, 26 73",
    "M460 78 C 474 88, 486 84, 484 72 C 483 64, 472 64, 474 73",
    "M16 28 C -2 16, -16 14, -22 28 C -25 35, -18 40, -12 36",
    "M484 28 C 502 16, 516 14, 522 28 C 525 35, 518 40, 512 36",
]
_FRAME_SMALL_SPLATS = [
    (-26.0, 20.0, 1.7), (526.0, 20.0, 1.7), (292.0, 2.0, 1.2), (292.0, 98.0, 1.2),
]
_FRAME_SMALL_BOX = (40.0, 22.0, 420.0, 56.0)
_FRAME_SMALL_SPARKLES = [(452.0, 6.0, 1.0), (48.0, 92.0, 2.2)]

# Завиток кнопки при наведении (HoverFlourish). viewBox="-18 -4 176 48"
_FLOURISH_VIEWBOX = (-18.0, -4.0, 176.0, 48.0)
_FLOURISH_D = [
    "M18 6 C 50 0, 90 0, 122 6 C 134 9, 138 16, 134 24 C 128 34, 112 38, 70 38 C 28 38, 12 34, 6 24 C 2 16, 6 9, 18 6",
    "M6 22 C -6 14, -14 18, -12 26 C -11 32, -3 31, -4 25",
    "M134 22 C 146 14, 154 18, 152 26 C 151 32, 143 31, 144 25",
]
_FLOURISH_SPLATS = [(-14.0, 18.0, 1.6), (154.0, 18.0, 1.6), (70.0, -2.0, 1.2)]

# Чернильное кольцо номера страницы (InkRing). viewBox="0 0 48 48"
_RING_VIEWBOX = (0.0, 0.0, 48.0, 48.0)
_RING_D = [
    "M24 5 C 36 3, 44 12, 43 24 C 42 37, 34 44, 23 43 C 11 42, 4 34, 5 23 C 6 11, 14 6, 24 5",
    "M43 24 C 50 20, 54 24, 51 29 C 49 32, 45 30, 46 27",
]
_RING_SPLATS = [(53.0, 31.0, 1.3)]

# Рукописный разделитель (InkDivider). viewBox="0 0 10 40"
_DIVIDER_VIEWBOX = (0.0, 0.0, 10.0, 40.0)
_DIVIDER_D = ["M5 3 C 7 10, 3 14, 5 20 C 7 26, 3 30, 5 37"]
_DIVIDER_SPLATS = [(5.0, 1.5, 1.2), (5.0, 38.5, 1.2)]

# Искра (Sparkle). viewBox="0 0 12 12"
_SPARKLE_VIEWBOX = (0.0, 0.0, 12.0, 12.0)
_SPARKLE_D = (
    "M6 0 C 6.6 3.6, 8.4 5.4, 12 6 C 8.4 6.6, 6.6 8.4, 6 12 "
    "C 5.4 8.4, 3.6 6.6, 0 6 C 3.6 5.4, 5.4 3.6, 6 0"
)

# Кольцо вокруг выбранной чернильницы. viewBox="0 0 36 36"
_WELL_VIEWBOX = (0.0, 0.0, 36.0, 36.0)
_WELL_D = ["M18 4 C 27 3, 33 9, 32 18 C 31 27, 25 32, 17 32 C 9 31, 4 26, 4 17 C 5 9, 10 5, 18 4"]

# Пропорции основного прямоугольника рамок внутри viewBox — для расчёта отступов
# панели так, чтобы кнопки оказались ровно внутри рамки (см. layout_margins).
FRAME_LARGE_BOX = _FRAME_LARGE_BOX
FRAME_LARGE_VIEWBOX = _FRAME_LARGE_VIEWBOX
FRAME_SMALL_BOX = _FRAME_SMALL_BOX
FRAME_SMALL_VIEWBOX = _FRAME_SMALL_VIEWBOX

# Разобранные пути (кэш)
_FRAME_LARGE_PATHS = [parse_svg_path(d) for d in _FRAME_LARGE_D]
_FRAME_SMALL_PATHS = [parse_svg_path(d) for d in _FRAME_SMALL_D]
_FLOURISH_PATHS = [parse_svg_path(d) for d in _FLOURISH_D]
_RING_PATHS = [parse_svg_path(d) for d in _RING_D]
_DIVIDER_PATHS = [parse_svg_path(d) for d in _DIVIDER_D]
_SPARKLE_PATH = parse_svg_path(_SPARKLE_D)
_WELL_PATHS = [parse_svg_path(d) for d in _WELL_D]


# ---------------------------------------------------------------------------
#  Трансформации viewBox -> целевой прямоугольник
# ---------------------------------------------------------------------------
def _stretch_transform(viewbox, dst: QRectF) -> QTransform:
    """Растяжение без сохранения пропорций (preserveAspectRatio="none")."""
    vx, vy, vw, vh = viewbox
    sx = dst.width() / vw
    sy = dst.height() / vh
    return QTransform(sx, 0, 0, sy, dst.x() - sx * vx, dst.y() - sy * vy)


def _fit_transform(viewbox, dst: QRectF) -> QTransform:
    """Вписывание с сохранением пропорций, по центру."""
    vx, vy, vw, vh = viewbox
    s = min(dst.width() / vw, dst.height() / vh)
    tx = dst.x() + (dst.width() - s * vw) / 2.0 - s * vx
    ty = dst.y() + (dst.height() - s * vh) / 2.0 - s * vy
    return QTransform(s, 0, 0, s, tx, ty)


# ---------------------------------------------------------------------------
#  «Живая кисть»: лёгкое рукотворное искажение штриха (аналог feTurbulence)
# ---------------------------------------------------------------------------
def _wobble(path: QPainterPath, amp: float, seed: float) -> QPainterPath:
    length = path.length()
    if length < 2.0 or amp <= 0.0:
        return path
    n = max(6, int(length / 3.0))
    out = QPainterPath()
    for i in range(n + 1):
        t = i / n
        pt = path.pointAtPercent(t)
        x, y = pt.x(), pt.y()
        # плавный псевдошум из синусов — детерминированный, «рукописный»
        nx = math.sin(x * 0.045 + y * 0.06 + seed) * math.cos(y * 0.05 - seed * 1.7)
        ny = math.cos(x * 0.05 - y * 0.035 + seed * 2.3) * math.sin(x * 0.055 + seed)
        # затухание к концам, чтобы стыки штрихов не расходились
        fade = math.sin(math.pi * t)
        p = QPointF(x + nx * amp * fade, y + ny * amp * fade)
        if i == 0:
            out.moveTo(p)
        else:
            out.lineTo(p)
    return out


def _partial(path: QPainterPath, progress: float) -> QPainterPath:
    """Часть пути от начала до доли progress его длины (эффект прорисовки)."""
    if progress >= 0.999:
        return path
    if progress <= 0.001:
        return QPainterPath()
    length = path.length()
    n = max(2, int(length / 2.0))
    steps = max(1, int(n * progress))
    out = QPainterPath()
    out.moveTo(path.pointAtPercent(0.0))
    for i in range(1, steps + 1):
        t = min((i / n), progress)
        out.lineTo(path.pointAtPercent(t))
    return out


# --- кэш подготовленной (смасштабированной + искажённой) геометрии ---
_GEO_CACHE: dict = {}
_GEO_CACHE_LIMIT = 64


def _prepare(kind: str, base_paths, viewbox, dst: QRectF, stretch: bool, amp: float):
    key = (kind, round(dst.width(), 1), round(dst.height(), 1), round(dst.x(), 1), round(dst.y(), 1))
    cached = _GEO_CACHE.get(key)
    if cached is not None:
        return cached
    transform = _stretch_transform(viewbox, dst) if stretch else _fit_transform(viewbox, dst)
    prepared = []
    for idx, p in enumerate(base_paths):
        mapped = transform.map(p)
        prepared.append(_wobble(mapped, amp, seed=idx * 1.37 + 0.5))
    if len(_GEO_CACHE) > _GEO_CACHE_LIMIT:
        _GEO_CACHE.clear()
    _GEO_CACHE[key] = prepared
    return prepared


# ---------------------------------------------------------------------------
#  Низкоуровневая отрисовка штрихов и брызг
# ---------------------------------------------------------------------------
def _pen(color_hex: str, width: float, alpha: float) -> QPen:
    color = QColor(color_hex)
    color.setAlphaF(max(0.0, min(1.0, alpha)))
    pen = QPen(color)
    pen.setWidthF(width)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    return pen


def _stroke(painter, paths, progresses, pen: QPen) -> None:
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    for path, prog in zip(paths, progresses):
        if prog <= 0.001:
            continue
        painter.drawPath(_partial(path, prog))


def _draw_splats(painter, splats, transform: QTransform, scale: float, color_hex: str,
                 opacity: float, pop: float) -> None:
    if opacity <= 0.01 or pop <= 0.01:
        return
    painter.setPen(Qt.NoPen)
    color = QColor(color_hex)
    color.setAlphaF(max(0.0, min(1.0, opacity)))
    painter.setBrush(color)
    for cx, cy, r in splats:
        pt = transform.map(QPointF(cx, cy))
        rr = max(r * scale * pop, 0.5)
        painter.drawEllipse(pt, rr, rr)


# ---------------------------------------------------------------------------
#  Публичные функции отрисовки
# ---------------------------------------------------------------------------
def _stagger_progress(elapsed: float | None, index: int) -> float:
    """Прогресс прорисовки штриха index: None => уже прорисован полностью."""
    if elapsed is None:
        return 1.0
    local = elapsed - index * DRAW_STAGGER
    if local <= 0.0:
        return 0.0
    return min(local / DRAW_DURATION, 1.0)


def _breathe_opacity(elapsed: float | None) -> float:
    if elapsed is None:
        return 1.0
    phase = (elapsed % BREATHE_PERIOD) / BREATHE_PERIOD
    return 0.75 + 0.25 * (0.5 - 0.5 * math.cos(phase * 2 * math.pi))


# Индексы штрихов рамки, образующих её основной замкнутый контур:
# верхняя кромка, правая сторона, нижняя кромка, левая сторона (см. *_D выше —
# порядок одинаков для большой и малой рамки). Нижнюю и левую разворачиваем,
# чтобы контур шёл единым обходом по часовой стрелке.
_FILL_BOUNDARY = (0, 3, 1, 2)


def _frame_fill_path(paths) -> QPainterPath:
    """Замкнутый путь, повторяющий волнистую форму обводки — по нему рисуется
    заливка, чтобы она идеально вписывалась в рамку, а не была прямоугольником.
    Строится из тех же искажённых `paths`, поэтому граница совпадает с обводкой."""
    top, right, bottom, left = (paths[i] for i in _FILL_BOUNDARY)
    path = QPainterPath()
    path.addPath(top)                      # верх: слева → направо
    path.connectPath(right)                # правая сторона: сверху → вниз
    path.connectPath(bottom.toReversed())  # низ: справа → налево
    path.connectPath(left.toReversed())    # левая сторона: снизу → вверх
    path.closeSubpath()
    return path


def _draw_fill(painter, path: QPainterPath, mouse_pos, glow: float, intro: float) -> None:
    """Тёмно-коричневая полупрозрачная заливка + тёплая подсветка-«фонарик» у курсора."""
    painter.save()
    painter.setPen(Qt.NoPen)
    base = QColor(FILL_BROWN)
    base.setAlphaF(FILL_ALPHA * intro)
    painter.fillPath(path, base)
    # «фонарик»: мягкое радиальное осветление у позиции мыши, обрезанное рамкой
    if mouse_pos is not None and glow > 0.01:
        painter.setClipPath(path)
        grad = QRadialGradient(QPointF(mouse_pos), GLOW_RADIUS)
        c0 = QColor(GLOW_TINT)
        c0.setAlphaF(GLOW_ALPHA * glow * intro)
        c1 = QColor(GLOW_TINT)
        c1.setAlphaF(0.0)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, c1)
        painter.setBrush(grad)
        painter.drawPath(path)
    painter.restore()


def _draw_frame(painter, base_paths, viewbox, box, splats, sparkles, dst: QRectF,
                elapsed: float | None, amp: float,
                mouse_pos=None, glow: float = 0.0) -> None:
    paths = _prepare("frame" + str(id(base_paths)), base_paths, viewbox, dst, True, amp)
    transform = _stretch_transform(viewbox, dst)
    scale = min(dst.width() / viewbox[2], dst.height() / viewbox[3])

    progresses = [_stagger_progress(elapsed, i) for i in range(len(paths))]
    all_drawn = all(p >= 0.999 for p in progresses)
    breathe = _breathe_opacity(elapsed) if all_drawn else 1.0

    # заливка по форме обводки — проявляется вместе с прорисовкой рамки
    intro = 1.0 if elapsed is None else max(0.0, min(1.0, elapsed / DRAW_DURATION))
    _draw_fill(painter, _frame_fill_path(paths), mouse_pos, glow, intro)

    # тень туши (широкий бледный штрих) + основной штрих (полностью непрозрачный)
    _stroke(painter, paths, progresses, _pen(GOLD, 4.4, 0.18 * breathe))
    _stroke(painter, paths, progresses, _pen(GOLD, 1.8, 1.0))

    # брызги проявляются после того, как рамка прорисована
    splat_pop = 1.0 if all_drawn else 0.0
    _draw_splats(painter, splats, transform, scale, GOLD, 0.6 * breathe, splat_pop)

    # искры
    if all_drawn:
        for sx, sy, delay in sparkles:
            center = transform.map(QPointF(sx, sy))
            phase = (((elapsed or 0.0) + delay) % SPARKLE_PERIOD) / SPARKLE_PERIOD
            draw_sparkle(painter, center, 5.0, phase)


def draw_frame_large(painter, dst: QRectF, elapsed: float | None,
                     mouse_pos=None, glow: float = 0.0) -> None:
    _draw_frame(painter, _FRAME_LARGE_PATHS, _FRAME_LARGE_VIEWBOX, _FRAME_LARGE_BOX,
                _FRAME_LARGE_SPLATS, _FRAME_LARGE_SPARKLES, dst, elapsed, amp=2.2,
                mouse_pos=mouse_pos, glow=glow)


def draw_frame_small(painter, dst: QRectF, elapsed: float | None,
                     mouse_pos=None, glow: float = 0.0) -> None:
    _draw_frame(painter, _FRAME_SMALL_PATHS, _FRAME_SMALL_VIEWBOX, _FRAME_SMALL_BOX,
                _FRAME_SMALL_SPLATS, _FRAME_SMALL_SPARKLES, dst, elapsed, amp=1.8,
                mouse_pos=mouse_pos, glow=glow)


def draw_flourish(painter, dst: QRectF, progress: float, color_hex: str = GOLD_BRIGHT) -> None:
    """Завиток кнопки: прорисовывается по мере progress (наведение)."""
    if progress <= 0.01:
        return
    paths = _prepare("flourish", _FLOURISH_PATHS, _FLOURISH_VIEWBOX, dst, True, amp=1.4)
    progresses = [min(progress, 1.0)] * len(paths)
    _stroke(painter, paths, progresses, _pen(color_hex, 1.6, 0.95 * min(progress * 1.4, 1.0)))
    transform = _stretch_transform(_FLOURISH_VIEWBOX, dst)
    scale = min(dst.width() / _FLOURISH_VIEWBOX[2], dst.height() / _FLOURISH_VIEWBOX[3])
    pop = max(0.0, (progress - 0.55) / 0.45)
    _draw_splats(painter, _FLOURISH_SPLATS, transform, scale, color_hex, 0.9, pop)


def draw_ring(painter, dst: QRectF, progress: float, color_hex: str = GOLD_BRIGHT) -> None:
    """Чернильное кольцо номера страницы."""
    if progress <= 0.01:
        return
    paths = _prepare("ring", _RING_PATHS, _RING_VIEWBOX, dst, False, amp=0.9)
    # хвостик-завиток прорисовывается с небольшой задержкой
    progresses = [min(progress, 1.0), max(0.0, min((progress - 0.35) / 0.65, 1.0))]
    _stroke(painter, paths, progresses, _pen(color_hex, 1.8, 0.95 * min(progress * 1.4, 1.0)))
    transform = _fit_transform(_RING_VIEWBOX, dst)
    scale = min(dst.width() / _RING_VIEWBOX[2], dst.height() / _RING_VIEWBOX[3])
    pop = max(0.0, (progress - 0.55) / 0.45)
    _draw_splats(painter, _RING_SPLATS, transform, scale, color_hex, 0.95, pop)


def draw_divider(painter, dst: QRectF) -> None:
    """Рукописный вертикальный разделитель."""
    paths = _prepare("divider", _DIVIDER_PATHS, _DIVIDER_VIEWBOX, dst, False, amp=0.5)
    _stroke(painter, paths, [1.0] * len(paths), _pen(GOLD, 1.4, 0.45))
    transform = _fit_transform(_DIVIDER_VIEWBOX, dst)
    scale = min(dst.width() / _DIVIDER_VIEWBOX[2], dst.height() / _DIVIDER_VIEWBOX[3])
    _draw_splats(painter, _DIVIDER_SPLATS, transform, scale, GOLD, 0.5, 1.0)


def draw_sparkle(painter, center: QPointF, size: float, phase: float) -> None:
    """Мерцающая четырёхлучевая искра (phase 0..1)."""
    tw = 0.5 - 0.5 * math.cos(phase * 2 * math.pi)  # 0..1
    opacity = 0.25 + 0.75 * tw
    scale = (0.8 + 0.3 * tw) * (size / 12.0)
    painter.save()
    painter.translate(center)
    painter.scale(scale, scale)
    painter.translate(-6.0, -6.0)  # центр viewBox 12x12
    color = QColor(GOLD_BRIGHT)
    color.setAlphaF(opacity)
    painter.setPen(Qt.NoPen)
    painter.setBrush(color)
    painter.drawPath(_SPARKLE_PATH)
    painter.restore()


def draw_well_ring(painter, dst: QRectF, progress: float) -> None:
    """Рукописное кольцо вокруг выбранной/наведённой чернильницы."""
    if progress <= 0.01:
        return
    paths = _prepare("well", _WELL_PATHS, _WELL_VIEWBOX, dst, False, amp=0.7)
    _stroke(painter, paths, [min(progress, 1.0)], _pen(GOLD_BRIGHT, 1.6, min(progress * 1.4, 1.0)))


# ---------------------------------------------------------------------------
#  Текст (золотой serif italic с мягкой тенью для читаемости поверх экрана)
# ---------------------------------------------------------------------------
def make_font(base: QFont, *, italic: bool, size_pt: float, bold: bool = False) -> QFont:
    font = QFont(base)
    font.setFamilies(["Cormorant Garamond", "Cormorant", "Georgia", "Times New Roman", "serif"])
    font.setItalic(italic)
    font.setBold(bold)
    font.setPointSizeF(size_pt)
    return font


def lerp_color(a_hex: str, b_hex: str, t: float) -> QColor:
    a, b = QColor(a_hex), QColor(b_hex)
    t = max(0.0, min(1.0, t))
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
    )


def draw_label(painter, rect: QRectF, text: str, font: QFont, color: QColor, dim: float = 1.0) -> None:
    if not text:
        return
    painter.save()
    painter.setFont(font)
    fm = QFontMetricsF(font)
    tw = fm.horizontalAdvance(text)
    x = rect.x() + (rect.width() - tw) / 2.0
    y = rect.y() + (rect.height() + fm.ascent() - fm.descent()) / 2.0

    path = QPainterPath()
    path.addText(x, y, font, text)

    shadow = QColor(0, 0, 0, int(120 * dim))
    painter.translate(0, 1.2)
    painter.fillPath(path, shadow)
    painter.translate(0, -1.2)

    col = QColor(color)
    if dim < 1.0:
        col.setAlphaF(dim)
    painter.fillPath(path, col)
    painter.restore()


# ---------------------------------------------------------------------------
#  Расчёт отступов панели, чтобы её содержимое оказалось внутри рамки
# ---------------------------------------------------------------------------
def layout_margins(content_w: float, content_h: float, viewbox, box, pad: float) -> tuple[int, int]:
    """По естественному размеру содержимого (content_w x content_h) считает
    симметричные отступы (mx, my) так, чтобы основной прямоугольник рамки
    охватил содержимое с зазором pad, а выносные росчерки поместились внутри
    виджета (рамка рисуется на весь виджет)."""
    vx, vy, vw, vh = viewbox
    bx, by, bw, bh = box
    fw_frac = bw / vw
    fh_frac = bh / vh
    x_off_frac = (bx - vx) / vw
    y_off_frac = (by - vy) / vh

    total_w = (content_w + 2 * pad) / fw_frac
    total_h = (content_h + 2 * pad) / fh_frac
    mx = round(x_off_frac * total_w + pad)
    my = round(y_off_frac * total_h + pad)
    return int(mx), int(my)
