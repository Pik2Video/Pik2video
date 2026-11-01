# src/pik2video/gui/editor/audio_timeline.py
"""
Аудио-таймлайн с waveform.

Отвечает только за:
- загрузку формы волны из WAV-файла
- отрисовку полосы, waveform, маркеров и курсора
- приём мыши (перетаскивание маркеров, клик по полосе)
- публикацию сигналов при изменениях

Отличия от видеотаймлайна:
- зелёная палитра вместо серой
- waveform внутри полосы (для WAV-файлов)
- для остальных форматов — плоская полоса

Не знает:
- про плеер
- про EditorState
- про экспорт
"""

import array
import logging
import wave
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


TRACK_BG = "#2a2a2a"                 # фон полосы
TRIM_BG = "#1e3a1e"                  # подсветка обрезки (тёмно-зелёный)
WAVEFORM_COLOR = "#4a9a4a"           # цвет столбиков waveform
WAVEFORM_BG_COLOR = "#3a7a3a"        # цвет waveform внутри обрезки
CURSOR_COLOR = "#e0e0e0"             # цвет курсора
MARKER_COLOR = "#d4a843"             # цвет маркеров (жёлтый, как у видео)

WAVEFORM_BLOCKS = 800                # число столбиков waveform на весь файл


class AudioTimelineWidget(QWidget):
    """Аудио-таймлайн с waveform для WAV-файлов."""

    trim_changed = Signal(float, float)   # start, end
    seek_requested = Signal(float)        # секунды
    marker_drag_started = Signal()
    marker_dragged = Signal(float, int)   # секунды, x-локальный
    marker_drag_finished = Signal()
    track_drag_started = Signal()         # начало drag за тело дорожки
    track_dragged = Signal(float)         # delta в секундах (относительно press)
    track_drag_finished = Signal()        # конец drag дорожки

    HEIGHT = 42
    TRACK_HEIGHT = 14                     # чуть толще видео-полосы, чтобы waveform читался
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
        self._waveform = None              # список 0.0..1.0 или None
        self._waveform_path = ""           # путь, для которого загружен waveform
        self._dragging = None
        self._draggable = False            # можно ли тащить тело дорожки
        self._drag_start_global_x = 0.0    # глобальная X в момент press

    # ---------------- API ----------------

    def set_draggable(self, value: bool):
        """Разрешить/запретить перетаскивание тела дорожки."""
        self._draggable = bool(value)

    # ---------------- API ----------------

    def set_source(self, path: str, duration: float = 0.0):
        """Загрузить waveform из файла. Длительность придёт позже от плеера."""
        self._load_waveform(path)                              # сначала waveform
        if duration > 0:
            self.set_duration(duration)                        # длительность, если известна
            
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

    def clear(self):
        """Сбросить таймлайн (нет аудио)."""
        self._duration = 0.0
        self._position = 0.0
        self._trim_start = 0.0
        self._trim_end = 0.0
        self._waveform = None
        self._waveform_path = ""
        self._is_empty = True
        self.update()

    # ---------------- Waveform ----------------

    def _load_waveform(self, path: str):
        """Загрузить waveform из WAV. Для не-WAV — None (плоская полоса)."""
        if not path or path == self._waveform_path:
            return                                  # уже загружено или путь пуст

        self._waveform_path = path
        self._waveform = None

        if Path(path).suffix.lower() != ".wav":
            logger.debug(f"Waveform: формат не WAV, плоская полоса")
            return

        try:
            peaks = self._read_wav_peaks(path)
            if peaks:
                self._waveform = peaks
                logger.debug(f"Waveform: загружено {len(peaks)} блоков")
        except Exception as e:
            logger.warning(f"Не удалось загрузить waveform: {e}")

    @staticmethod
    def _read_wav_peaks(path: str):
        """Прочитать WAV и вернуть список пиков по блокам (0.0 … 1.0)."""
        with wave.open(path, "rb") as w:
            n_frames = w.getnframes()
            n_channels = w.getnchannels()
            sampwidth = w.getsampwidth()

            if n_frames <= 0:
                return None

            raw = w.readframes(n_frames)                # все сэмплы одним куском

            if sampwidth == 2:
                fmt = "h"
            elif sampwidth == 1:
                fmt = "b"
            elif sampwidth == 4:
                fmt = "i"
            else:
                return None                             # 24-bit и прочие — пока не поддерживаем

            samples = array.array(fmt, raw)

            # если стерео — берём только левый канал (каждый второй сэмпл)
            if n_channels == 2:
                samples = samples[::2]

            total = len(samples)
            if total == 0:
                return None

            block_size = max(1, total // WAVEFORM_BLOCKS)
            peaks = []
            for i in range(WAVEFORM_BLOCKS):
                start = i * block_size
                end = min(start + block_size, total)
                if start >= total:
                    peaks.append(0.0)
                    continue
                peak = 0
                for j in range(start, end):
                    v = samples[j]
                    if v < 0:
                        v = -v
                    if v > peak:
                        peak = v
                peaks.append(peak)

            max_peak = max(peaks) if peaks else 0
            if max_peak > 0:
                peaks = [p / max_peak for p in peaks]
            return peaks

    # ---------------- Геометрия ----------------

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

    # ---------------- События мыши ----------------

    def mousePressEvent(self, event):
        if self._is_empty:
            return
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
        """Курсор покинул виджет — вернуть обычную стрелку."""
        self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

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

    # ---------------- Отрисовка ----------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track = self._track_rect()

        if self._is_empty:
            # тусклая заглушка
            painter.fillRect(track, QColor("#181818"))
            pen = QPen(QColor("#333"), 1, Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(track)
            painter.setPen(QColor("#555"))
            painter.setFont(QFont("Arial", 10))
            painter.drawText(track, Qt.AlignCenter, "аудио")
            return

        painter.fillRect(track, QColor(TRACK_BG))

        if self._duration <= 0:
            return

        x_start = self._seconds_to_x(self._trim_start)
        x_end = self._seconds_to_x(self._trim_end)

        # Полоса обрезки — подсветка всей области
        trim_rect = QRectF(x_start, track.top(), x_end - x_start, track.height())
        painter.fillRect(trim_rect, QColor(TRIM_BG))

        # Waveform или плоская полоса
        if self._waveform:
            self._draw_waveform(painter, track, x_start, x_end)
        else:
            mid_y = track.center().y()
            painter.setPen(QPen(QColor("#555"), 2))
            painter.drawLine(
                QPointF(track.left(), mid_y),
                QPointF(track.right(), mid_y),
            )

        # Маркеры
        self._draw_marker(painter, x_start, track)
        self._draw_marker(painter, x_end, track)

    def _draw_waveform(self, painter, track, x_start, x_end):
        """Нарисовать waveform: столбики от центра полосы."""
        peaks = self._waveform
        n = len(peaks)
        if n == 0:
            return

        track_width = track.width()
        if track_width <= 0:
            return

        bar_width = track_width / n
        center_y = track.center().y()
        half_height = track.height() / 2 - 1

        painter.setPen(Qt.NoPen)

        for i, peak in enumerate(peaks):
            x = track.left() + i * bar_width
            h = peak * half_height
            if h < 1:
                h = 1

            # цвет: зелёный внутри обрезки, приглушённый вне
            if x_start <= x <= x_end:
                color = QColor(WAVEFORM_BG_COLOR)
            else:
                color = QColor("#2a4a2a")

            painter.setBrush(QBrush(color))
            painter.drawRect(QRectF(x, center_y - h, max(1, bar_width - 0.5), h * 2))

    def _draw_marker(self, painter, x, track):
        painter.setPen(QPen(QColor(MARKER_COLOR), 2))
        painter.drawLine(
            QPointF(x, track.top() - 6),
            QPointF(x, track.bottom() + 6),
        )

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