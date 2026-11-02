# src/pik2video/gui/editor/timeline/timeline.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from .track import TrackWidget

ICON_WIDTH = 40
TRACK_ROW_SPACING = 4


class TimelineWidget(QWidget):
    """Контейнер дорожек с центрированием и пропорциональной шириной."""

    seek_requested = Signal(float)

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self._tracks = []           # список (track, icon, row)
        self._total_duration = 0.0
        self._position = 0.0

        self.setStyleSheet("background-color: #151515; border-top: 1px solid #000;")
        self.setMinimumHeight(80)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        # Stretch сверху — центрирует блок дорожек
        layout.addStretch(1)

        self._tracks_container = QWidget()
        self._tracks_container.setStyleSheet("background: transparent;")
        self._tracks_layout = QVBoxLayout(self._tracks_container)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(TRACK_ROW_SPACING)
        layout.addWidget(self._tracks_container)

        # Stretch снизу
        layout.addStretch(1)

    def rebuild_tracks(self, video_files: list, audio_path: str):
        """Пересобрать дорожки: видео → аудио."""
        # Очистка
        for i in reversed(range(self._tracks_layout.count())):
            item = self._tracks_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        self._tracks.clear()

        # Длительности из EditorState
        for path in video_files:
            dur = self.state.get_video_duration_for(path)
            self._add_track("video", path, dur)
        if audio_path:
            dur = self.state.get_audio_duration()
            self._add_track("audio", audio_path, dur)

        self._recalc_total()

    def _add_track(self, track_type: str, path: str, duration: float = 0.0):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        icon = QLabel("📹" if track_type == "video" else "🎵")
        icon.setFixedWidth(ICON_WIDTH)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 14px; background: transparent; border: none;")
        row_layout.addWidget(icon, alignment=Qt.AlignVCenter)

        track = TrackWidget(track_type, path, duration)
        track.seek_requested.connect(self.seek_requested.emit)
        row_layout.addWidget(track, alignment=Qt.AlignVCenter)

        row_layout.addStretch(1)

        self._tracks_layout.addWidget(row)
        self._tracks.append((track, icon, row))

    def set_track_duration(self, index: int, duration: float):
        """Установить длительность конкретной дорожки по индексу."""
        if 0 <= index < len(self._tracks):
            track, _, _ = self._tracks[index]
            track.set_duration(duration)
            self._recalc_total()

    def set_audio_duration(self, duration: float):
        """Установить длительность аудио-дорожки (всегда последняя)."""
        if self._tracks:
            track, _, _ = self._tracks[-1]
            if track.track_type == "audio":
                track.set_duration(duration)
                self._recalc_total()

    def _recalc_total(self):
        self._total_duration = max(
            (t.duration for t, _, _ in self._tracks), default=0.0
        )
        self._update_widths()

    def _update_widths(self):
        available = self.width() - ICON_WIDTH
        if available <= 0 or not self._tracks:
            return
        if self._total_duration <= 0:
            for track, _, _ in self._tracks:
                track.setFixedWidth(max(20, available))
            return
        for track, _, _ in self._tracks:
            ratio = track.duration / self._total_duration if track.duration > 0 else 1.0
            width = max(20, int(ratio * available))
            track.setFixedWidth(width)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_widths()

    def set_duration(self, seconds: float):
        """Общая длительность (для совместимости) — просто пересчитать ширины."""
        if seconds > 0:
            self._total_duration = seconds
            self._update_widths()

    def set_position(self, seconds: float):
        self._position = max(0.0, seconds)
        self.update()

    # ── Заглушки для window.py ──

    def set_empty(self, value: bool):
        pass

    def set_keyframes(self, times: list):
        pass

    def set_active_mode(self, mode: str):
        pass

    def set_audio_offset(self, offset: float):
        pass

    def set_video_offset(self, offset: float):
        pass

    def set_trim(self, start: float, end: float):
        pass

    def set_audio_trim(self, start: float, end: float):
        pass

    def set_durations(self, video_dur: float, audio_dur: float):
        pass

    def set_linked_mode(self, linked: bool):
        pass

    def set_draggable(self, value: bool):
        pass

    def set_source(self, path: str, duration: float):
        pass

    def clear(self):
        pass

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._total_duration <= 0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor("#8b1a1a"), 2)
        painter.setPen(pen)

        # Позиция: слева от дорожки — иконка (ICON_WIDTH). Дорожки разной ширины,
        # но x считается по общей длительности и полной доступной ширине.
        available = self.width() - ICON_WIDTH
        if available <= 0:
            return

        ratio = max(0.0, min(1.0, self._position / self._total_duration))
        x = ICON_WIDTH + ratio * available
        painter.drawLine(int(x), 0, int(x), self.height())
