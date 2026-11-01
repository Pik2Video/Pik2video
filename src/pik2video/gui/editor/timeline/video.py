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
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
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
    track_drag_started = Signal()         # начало drag за тело дорожки
    track_dragged = Signal(float)         # delta в секундах (относительно press)
    track_drag_finished = Signal()        # конец drag дорожки
    marker_double_clicked = Signal(float) # двойной клик на ромбике: время метки

    HEIGHT = 42
    TRACK_HEIGHT = 8
    MARKER_GRAB_PX = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(self.HEIGHT)
        self.setMouseTracking(True)
        # курсор управляется динамически в mouseMoveEvent

        self._duration = 0.0
        self._position = 0.0
        self._trim_start = 0.0
        self._trim_end = 0.0
        self._is_empty = True            # пока файл не загружен — заглушка

        self._dragging = None  # 'start' | 'end' | 'cursor' | 'track' | None
        self._draggable = False
        self._drag_start_global_x = 0.0
        self._keyframe_times: list[float] = []  # список времен меток для отрисовки ромбиков
        self._hovered_keyframe: float | None = None  # время ромбика, над которым курсор

    # ── Публичный API ──

    def set_draggable(self, value: bool):
        """Разрешить/запретить перетаскивание тела дорожки."""
        self._draggable = bool(value)

    def set_empty(self, value: bool):
        """Пустое состояние — тусклая заглушка без реакции на мышь."""
        if self._is_empty == value:
            return
        self._is_empty = bool(value)
        if self._is_empty:
            self._dragging = None
            self.setCursor(Qt.ArrowCursor)
        self.update()

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

    def set_keyframes(self, times: list[float]):
        """Обновить список времен ключевых кадров для отрисовки."""
        self._keyframe_times = sorted(times)
        if self._hovered_keyframe is not None:
            still_exists = any(abs(t - self._hovered_keyframe) < 0.001 for t in self._keyframe_times)
            if not still_exists:
                self._hovered_keyframe = None
        self.update()

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
        if self._is_empty:
            return
        if event.button() != Qt.LeftButton or self._duration <= 0:
            return

        x = event.position().x()

        # 3.1 Проверяем клик по ключевому кадру (ромбику)
        for t in self._keyframe_times:
            kx = self._seconds_to_x(t)
            if abs(x - kx) <= 8:  # зона клика 8 пикселей
                self.seek_requested.emit(t)
                return  # Прерываем обработку, чтобы не начать перетаскивание метки трима

        x_start = self._seconds_to_x(self._trim_start)
        x_end = self._seconds_to_x(self._trim_end)

        if abs(x - x_start) <= self.MARKER_GRAB_PX:
            self._dragging = "start"
            self.marker_drag_started.emit()
        elif abs(x - x_end) <= self.MARKER_GRAB_PX:
            self._dragging = "end"
            self.marker_drag_started.emit()
        elif self._draggable:
            self._dragging = "track"
            self._drag_start_global_x = event.globalPosition().x()
            self.setCursor(Qt.ClosedHandCursor)
            self.track_drag_started.emit()
        # клик вне меток и не по draggable — ползунок управляется только скраббером

    def mouseMoveEvent(self, event):
        if self._is_empty:
            self.setCursor(Qt.ArrowCursor)
            return
        x = event.position().x()

        # Курсор: над меткой — ↔, иначе — обычная стрелка
        if self._dragging is None and self._duration > 0:
            x_start = self._seconds_to_x(self._trim_start)
            x_end = self._seconds_to_x(self._trim_end)
            near_start = abs(x - x_start) <= self.MARKER_GRAB_PX
            near_end = abs(x - x_end) <= self.MARKER_GRAB_PX
            if near_start or near_end:
                self.setCursor(Qt.SizeHorCursor)
            elif self._draggable:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

        # hover над ромбиком (подсветка)
        if self._dragging is None and self._duration > 0:
            hovered = None
            for t in self._keyframe_times:
                kx = self._seconds_to_x(t)
                if abs(x - kx) <= 8:
                    hovered = t
                    break
            if hovered != self._hovered_keyframe:
                self._hovered_keyframe = hovered
                self.update()

        if self._dragging is None or self._duration <= 0:
            return

        if self._dragging == "track":
            delta_px = event.globalPosition().x() - self._drag_start_global_x
            track_width = max(1, self.width() - 2 * 10)          # TRACK_MARGIN
            delta_sec = delta_px * self._duration / track_width
            self.track_dragged.emit(delta_sec)
            return

        seconds = self._x_to_seconds(x)

        if self._dragging == "start":
            if seconds < self._trim_end - 0.1:
                self._trim_start = max(0.0, seconds)
                self.update()
                self.marker_dragged.emit(self._trim_start, int(x))
        elif self._dragging == "end":
            if seconds > self._trim_start + 0.1:
                self._trim_end = min(self._duration, seconds)
                self.update()
                self.marker_dragged.emit(self._trim_end, int(x))

    def leaveEvent(self, event):
        """Курсор покинул виджет — вернуть обычную стрелку и сбросить hover."""
        self.setCursor(Qt.ArrowCursor)
        if self._hovered_keyframe is not None:
            self._hovered_keyframe = None
            self.update()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        """Двойной клик на ромбике → сигнал marker_double_clicked."""
        if self._is_empty or event.button() != Qt.LeftButton or self._duration <= 0:
            return super().mouseDoubleClickEvent(event)

        x = event.position().x()
        for t in self._keyframe_times:
            kx = self._seconds_to_x(t)
            if abs(x - kx) <= 8:
                self.marker_double_clicked.emit(t)
                return
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event):
        if self._is_empty:
            return
        dragged = self._dragging
        self._dragging = None
        if dragged in ("start", "end"):
            self.trim_changed.emit(self._trim_start, self._trim_end)   # финальный — один раз
            target = self._trim_start if dragged == "start" else self._trim_end
            self.seek_requested.emit(target)                           # один seek
            self.marker_drag_finished.emit()
        elif dragged == "track":
            self.setCursor(Qt.OpenHandCursor if self._draggable else Qt.ArrowCursor)
            self.track_drag_finished.emit()

    # ── Отрисовка ──

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        if self._is_empty:
            painter.fillRect(track, QColor("#181818"))
            pen = QPen(QColor("#333"), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(track)
            painter.setPen(QColor("#555"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(track, Qt.AlignCenter, "видео")
            return

        if self._duration <= 0:
            painter.fillRect(track, QColor(TRACK_BG))
            return

        painter.fillRect(track, QColor(TRACK_BG))

        x_start = self._seconds_to_x(self._trim_start)
        x_end = self._seconds_to_x(self._trim_end)
        trim_rect = QRectF(x_start, track.top(), x_end - x_start, track.height())
        painter.fillRect(trim_rect, QColor(TRIM_BG))

        self._draw_marker(painter, x_start, track)
        self._draw_marker(painter, x_end, track)

        # 4.1 Рисуем ключевые кадры
        for t in self._keyframe_times:
            kx = self._seconds_to_x(t)
            self._draw_keyframe(painter, kx, track, t)

    def _draw_keyframe(self, painter, x, track, time_sec: float):
        """Нарисовать ромбик ключевого кадра. При hover — ярче."""
        cy = track.center().y()
        size = 6
        diamond = QPolygonF([
            QPointF(x, cy - size),
            QPointF(x + size, cy),
            QPointF(x, cy + size),
            QPointF(x - size, cy),
        ])
        is_hovered = (
            self._hovered_keyframe is not None
            and abs(time_sec - self._hovered_keyframe) < 0.001
        )
        fill_color = "#ffb84d" if is_hovered else "#ff8c00"
        painter.setPen(QPen(QColor("#222222"), 1))
        painter.setBrush(QBrush(QColor(fill_color)))
        painter.drawPolygon(diamond)

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
