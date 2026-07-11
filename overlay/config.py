"""Константы и настройки по умолчанию для DEDisplay."""

from PySide6.QtGui import QColor

# --- Страницы ---
INITIAL_PAGE_COUNT = 5

# --- Инструменты ---
TOOL_PEN = "pen"
TOOL_ERASER = "eraser"
TOOL_MOVE = "move"

DEFAULT_TOOL = TOOL_PEN
DEFAULT_BRUSH_WIDTH = 4.0
MIN_BRUSH_WIDTH = 1.0
MAX_BRUSH_WIDTH = 24.0
BRUSH_WIDTH_STEP = 2.0

# При рисовании пером графического планшета толщина линии меняется от нажатия:
# на самом лёгком нажатии линия рисуется с этой долей от выбранной толщины,
# на полном нажатии — с полной толщиной. Для мыши нажатие всегда 1.0.
PRESSURE_MIN_FACTOR = 0.15

ERASER_HIT_PADDING = 6.0  # доп. допуск в пикселях для попадания ластиком по штриху

# --- Выделение / изменение размера / буфер обмена (инструмент "перемещение") ---
SELECTION_HANDLE_SIZE = 8.0  # сторона квадратной ручки-маркера на рамке выделения
SELECTION_HANDLE_HIT = 11.0  # радиус захвата ручки при клике (в пикселях)
PASTE_OFFSET = 24.0  # смещение вставленной копии, чтобы её было видно поверх оригинала

COLOR_RED = QColor("#ff5c5c")
COLOR_BLACK = QColor("#1a1a1a")
COLOR_WHITE = QColor("#f5f5f5")

PALETTE = [
    COLOR_RED,
    COLOR_BLACK,
    COLOR_WHITE,
    QColor("#5cd65c"),  # зелёный
    QColor("#5c9dff"),  # синий
    QColor("#ffd75c"),  # жёлтый
    QColor("#c15cff"),  # фиолетовый
]
DEFAULT_COLOR = COLOR_RED

# --- Стиль ---
TOOLBAR_BG = "rgba(28, 28, 32, 220)"
TOOLBAR_ACCENT = "#5c9dff"
TOOLBAR_TEXT = "#f0f0f0"

# --- Темы оформления ---
STYLE_CLASSIC = "classic"
STYLE_CALLIGRAPHY = "calligraphy"
DEFAULT_STYLE = STYLE_CLASSIC

# Биндинги по умолчанию и их пользовательские переопределения — см. overlay/keymap.py
