# src/pik2video/gui/editor/seek_bar.py
"""
Тонкая полоска-скраббер между дорожками.

Отвечает только за:
- отрисовку двух тонких серых линий (знак «=»)
- приём мыши: клик — переставить позицию, drag — «скраббинг» с превью кадров
- публикацию сигналов: clicked_position, scrub_started, scrub_dragged, scrub_finished

Не знает:
- про плеер
- про EditorState
- про CursorOverlay
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

BAR_COLOR = "#666666"       # средний серый — цвет линий
BAR_THICKNESS = 1           # толщина одной линии
BAR_GAP = 5                 # расстояние между линиями (даёт «=»)
TRACK_MARGIN = 10           # отступ от краёв, как у дорожек

WIDGET_HEIGHT = 12          # общая высота виджета


class SeekBar(QWidget):
    """Тонкая полоска-скраббер между дорожками."""

    clicked_position = Signal(float)        # одиночный клик — переставить позицию
    scrub_started = Signal()                # начало drag
    scrub_dragged = Signal(float, int)      # секунды, x-локальный — во время drag
    scrub_finished = Signal()               # окончание drag

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(WIDGET_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

        self._duration = 0.0
        self._position = 0.0
        self._x_start = TRACK_MARGIN
        self._x_end = TRACK_MARGIN
        self._dragging = False
        self._scrub_started = False          # был ли реальный drag (а не просто клик)
        self._press_seconds = 0.0            # позиция на момент mousePress (для клика без drag)

    # ── API ──

    def set_range(self, x_start: int, x_end: int, duration: float):
        """Задать рабочую область и длительность."""
        self._x_start = max(0, x_start)
        self._x_end = max(self._x_start, x_end)
        self._duration = max(0.0, duration)
        self.update()

    def set_position(self, seconds: float):
        """Внешнее обновление позиции (курсор) — только для отрисовки."""
        self._position = max(0.0, seconds)
        self.update()

    # ── Мышь ──

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return
        self._dragging = True
        self._scrub_started = False
        self._press_seconds = self._x_to_seconds(event.position().x())

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        if not self._scrub_started:
            self._scrub_started = True
            self.scrub_started.emit()                                # первый тик движения → пауза плеера
        x = event.position().x()
        seconds = self._x_to_seconds(x)
        self._position = seconds
        self.update()
        self.scrub_dragged.emit(seconds, int(x))

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._scrub_started:
            self.scrub_finished.emit()                               # был drag — завершить с паузой/возобновлением
        else:
            self.clicked_position.emit(self._press_seconds)          # был простой клик — разовый seek
        self._dragging = False
        self._scrub_started = False

    def _x_to_seconds(self, x: float) -> float:
        if self._duration <= 0 or self._x_end <= self._x_start:
            return 0.0
        ratio = (x - self._x_start) / (self._x_end - self._x_start)
        ratio = max(0.0, min(1.0, ratio))
        return ratio * self._duration

    # ── Отрисовка ──

    def paintEvent(self, event):
        if self.width() <= 0:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor(BAR_COLOR), BAR_THICKNESS))

        y_top = (self.height() - BAR_GAP) // 2
        y_bottom = y_top + BAR_GAP

        painter.drawLine(self._x_start, y_top, self._x_end, y_top)
        painter.drawLine(self._x_start, y_bottom, self._x_end, y_bottom)