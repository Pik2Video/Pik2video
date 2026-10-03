# src/pik2video/gui/editor/timeline.py
"""
Таймлайн с маркерами трима.

Отвечает только за:
- отрисовку полосы, маркеров и курсора
- приём мыши (перетаскивание маркеров, клик по полосе)
- публикацию сигналов при изменениях

Не знает:
- про плеер
- про EditorState
- про экспорт
"""

import logging

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


# Цвета
TRACK_BG = "#3a3a3a"
TRIM_BG = "#b0b0b0"
CURSOR_COLOR = "#e0e0e0"
MARKER_COLOR = "#d4a843"


class TimelineWidget(QWidget):
    trim_changed = Signal(float, float)   # start, end
    seek_requested = Signal(float)        # секунды
    marker_drag_started = Signal()
    marker_dragged = Signal(float, int)   # секунды, x-локальный
    marker_drag_finished = Signal()

    HEIGHT = 42
    TRACK_HEIGHT = 8
    MARKER_GRAB_PX = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)

        self._duration = 0.0
        self._position = 0.0
        self._trim_start = 0.0
        self._trim_end = 0.0

        self._dragging = None  # 'start' | 'end' | 'cursor' | None

    # ── Публичный API ──

    def set_duration(self, seconds: float):
        self._duration = max(0.0, seconds)
        if self._duration > 0 and self._trim_end > self._duration:
            self._trim_end = self._duration
        self.update()

    def set_position(self, seconds: float):
        self._position = max(0.0, min(seconds, self._duration))
        self.update()

    def set_trim(self, start: float, end: float):
        self._trim_start = max(0.0, start)
        self._trim_end = max(self._trim_start, end)
        self.update()

    def get_trim(self) -> tuple:
        return self._trim_start, self._trim_end

    # ── Координаты ──

    def _track_rect(self) -> QRectF:
        margin = 10
        return QRectF(
            margin,
            (self.height() - self.TRACK_HEIGHT) / 2,
            self.width() - 2 * margin,
            self.TRACK_HEIGHT,
        )

    def _seconds_to_x(self, seconds: float) -> float:
        if self._duration <= 0:
            return self._track_rect().left()
        track = self._track_rect()
        ratio = seconds / self._duration
        return track.left() + ratio * track.width()

    def _x_to_seconds(self, x: float) -> float:
        track = self._track_rect()
        if track.width() <= 0 or self._duration <= 0:
            return 0.0
        ratio = (x - track.left()) / track.width()
        ratio = max(0.0, min(1.0, ratio))
        return ratio * self._duration

    # ── Мышь ──

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return

        x = event.position().x()
        x_start = self._seconds_to_x(self._trim_start)
        x_end = self._seconds_to_x(self._trim_end)

        if abs(x - x_start) <= self.MARKER_GRAB_PX:
            self._dragging = "start"
            self.marker_drag_started.emit()
        elif abs(x - x_end) <= self.MARKER_GRAB_PX:
            self._dragging = "end"
            self.marker_drag_started.emit()
        else:
            self._dragging = "cursor"
            self.seek_requested.emit(self._x_to_seconds(x))

    def mouseMoveEvent(self, event):
        if self._dragging is None or self._duration <= 0:
            return

        x = event.position().x()
        seconds = self._x_to_seconds(x)

        if self._dragging == "start":
            if seconds < self._trim_end - 0.1:
                self._trim_start = max(0.0, seconds)
                self.update()
                self.trim_changed.emit(self._trim_start, self._trim_end)
                self.seek_requested.emit(self._trim_start)
                self.marker_dragged.emit(self._trim_start, int(x))
        elif self._dragging == "end":
            if seconds > self._trim_start + 0.1:
                self._trim_end = min(self._duration, seconds)
                self.update()
                self.trim_changed.emit(self._trim_start, self._trim_end)
                self.seek_requested.emit(self._trim_end)
                self.marker_dragged.emit(self._trim_end, int(x))
        elif self._dragging == "cursor":
            self.seek_requested.emit(seconds)

    def mouseReleaseEvent(self, event):
        was_marker = self._dragging in ("start", "end")
        self._dragging = None
        if was_marker:
            self.marker_drag_finished.emit()

    # ── Отрисовка ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        if self._duration <= 0:
            painter.fillRect(track, QColor(TRACK_BG))
            return

        painter.fillRect(track, QColor(TRACK_BG))

        x_start = self._seconds_to_x(self._trim_start)
        x_end = self._seconds_to_x(self._trim_end)
        trim_rect = QRectF(x_start, track.top(), x_end - x_start, track.height())
        painter.fillRect(trim_rect, QColor(TRIM_BG))

        x_cursor = self._seconds_to_x(self._position)
        painter.setPen(QPen(QColor(CURSOR_COLOR), 2))
        painter.drawLine(
            QPointF(x_cursor, track.top() - 6),
            QPointF(x_cursor, track.bottom() + 6),
        )

        self._draw_marker(painter, x_start, track)
        self._draw_marker(painter, x_end, track)

    def _draw_marker(self, painter, x, track):
        # Вертикальная линия маркера
        painter.setPen(QPen(QColor(MARKER_COLOR), 2))
        painter.drawLine(
            QPointF(x, track.top() - 6),
            QPointF(x, track.bottom() + 6),
        )

        # Треугольники
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(MARKER_COLOR)))

        top_tri = QPolygonF([
            QPointF(x - 4, track.top() - 8),
            QPointF(x + 4, track.top() - 8),
            QPointF(x, track.top() - 2),
        ])
        painter.drawPolygon(top_tri)

        bottom_tri = QPolygonF([
            QPointF(x - 4, track.bottom() + 8),
            QPointF(x + 4, track.bottom() + 8),
            QPointF(x, track.bottom() + 2),
        ])
        painter.drawPolygon(bottom_tri)
