# src/pik2video/gui/editor/timeline/timeline.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel

from .track import TrackWidget

ICON_WIDTH = 40
TRACK_ROW_SPACING = 4
PLAYHEAD_GRAB_PX = 6

ICON_NORMAL_STYLE = "font-size: 14px; background: transparent; border: none; color: #888;"
ICON_FOCUS_STYLE = "font-size: 14px; background: transparent; border: none; color: #e0e0e0;"


class ClickableLabel(QLabel):
    """QLabel с mousePressEvent — для иконок дорожек."""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PlayheadOverlay(QWidget):
    """Прозрачный слой поверх дорожек — рисует только красную линию."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._x = 0

    def set_x(self, x: int):
        if self._x != x:
            self._x = x
            self.update()

    def paintEvent(self, event):
        if self._x <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#8b1a1a"), 2))
        painter.drawLine(self._x, 0, self._x, self.height())


class TimelineWidget(QWidget):
    """Контейнер дорожек + playhead с drag-перетаскиванием."""

    seek_requested = Signal(float)
    playhead_drag_started = Signal()
    playhead_dragged = Signal(float, int)   # секунды, x-локальный (для превью)
    playhead_drag_finished = Signal()
    active_changed = Signal(str, int)       # "video"/"audio", index

    def __init__(self, state, thumbnail_loader=None, parent=None):
        super().__init__(parent)
        self.state = state
        self._thumbnail_loader = thumbnail_loader
        if self._thumbnail_loader is not None:
            self._thumbnail_loader.frames_ready.connect(self._on_frames_ready)
        self._tracks = []            # [(track, icon)]
        self._total_duration = 0.0
        self._position = 0.0
        self._playhead_x = 0
        self._dragging_playhead = False
        self._active_video_index = 0

        self.setStyleSheet("background-color: #151515; border-top: 1px solid #000;")
        self.setMinimumHeight(80)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)
        layout.addStretch(1)

        self._tracks_container = QWidget()
        self._tracks_container.setStyleSheet("background: transparent;")
        self._tracks_layout = QVBoxLayout(self._tracks_container)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(TRACK_ROW_SPACING)
        layout.addWidget(self._tracks_container)

        layout.addStretch(1)

        # Прозрачный слой поверх — красная линия
        self._playhead_overlay = PlayheadOverlay(self)
        self._playhead_overlay.raise_()

    # ── Пересборка ──

    def rebuild_tracks(self, video_files: list, audio_path: str):
        for i in reversed(range(self._tracks_layout.count())):
            item = self._tracks_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        self._tracks.clear()

        for idx, path in enumerate(video_files):
            dur = self.state.get_video_duration_for(path)
            self._add_track("video", path, dur, idx)
            # Если длительность уже известна — сразу запросить кадры
            if dur > 0:
                self._request_frames(self._tracks[-1][0], dur)

        if audio_path:
            dur = self.state.get_audio_duration()
            self._add_track("audio", audio_path, dur, 0)
            if dur > 0:
                self._request_frames(self._tracks[-1][0], dur)

        self._recalc_total()
        self._update_playhead()

    def _add_track(self, track_type: str, path: str, duration: float, index: int):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        icon_text = "📹" if track_type == "video" else "🎵"
        icon = ClickableLabel(icon_text)
        icon.setFixedWidth(ICON_WIDTH)
        icon.setStyleSheet(ICON_NORMAL_STYLE)
        icon.clicked.connect(
            lambda k=track_type, i=index: self.active_changed.emit(k, i)
        )
        row_layout.addWidget(icon, alignment=Qt.AlignVCenter)

        track = TrackWidget(track_type, path, duration)
        row_layout.addWidget(track, alignment=Qt.AlignVCenter)
        row_layout.addStretch(1)

        self._tracks_layout.addWidget(row)
        self._tracks.append((track, icon))

        # Восстановить фокус
        if track_type == "video" and index == self._active_video_index:
            track.set_focus(True)
            icon.setStyleSheet(ICON_FOCUS_STYLE)
        elif track_type == "audio" and not self.state.has_videos():
            track.set_focus(True)
            icon.setStyleSheet(ICON_FOCUS_STYLE)

    def set_active_video(self, index: int):
        self._active_video_index = index
        for track, icon in self._tracks:
            if track.track_type != "video":
                continue
            idx = self._index_of_video_path(track.path)
            focused = (idx == index)
            track.set_focus(focused)
            icon.setStyleSheet(ICON_FOCUS_STYLE if focused else ICON_NORMAL_STYLE)

    def set_active_audio(self):
        for track, icon in self._tracks:
            if track.track_type == "audio":
                track.set_focus(True)
                icon.setStyleSheet(ICON_FOCUS_STYLE)
            else:
                track.set_focus(False)
                icon.setStyleSheet(ICON_NORMAL_STYLE)

    def _index_of_video_path(self, path: str) -> int:
        try:
            return self.state.get_video_files().index(path)
        except ValueError:
            return -1

    # ── Кадры для отрисовки на дорожке ──

    @staticmethod
    def _frames_count(duration: float) -> int:
        """Сколько кадров генерировать: от 20 до 100, зависит от длины."""
        if duration <= 0:
            return 0
        return max(20, min(100, int(duration)))

    def _request_frames(self, track, duration: float):
        """Поставить задачу на генерацию кадров для дорожки."""
        if self._thumbnail_loader is None or duration <= 0:
            return
        count = self._frames_count(duration)
        if count > 0:
            self._thumbnail_loader.request_frames(track.path, count, duration)

    def _on_frames_ready(self, source_path: str, count: int):
        """Кадры готовы в кэше → загрузить pixmaps и передать в дорожки."""
        if self._thumbnail_loader is None:
            return
        pixmaps = self._thumbnail_loader.get_cached_frames(source_path, count)
        if not pixmaps:
            return
        for track, _ in self._tracks:
            if track.path == source_path:
                track.set_frames(pixmaps)

    # ── Ширины ──

    def set_track_duration(self, index: int, duration: float):
        video_tracks = [t for t, _ in self._tracks if t.track_type == "video"]
        if 0 <= index < len(video_tracks):
            video_tracks[index].set_duration(duration)
            self._recalc_total()
            self._request_frames(video_tracks[index], duration)

    def set_audio_duration(self, duration: float):
        for track, _ in self._tracks:
            if track.track_type == "audio":
                track.set_duration(duration)
                self._recalc_total()
                self._request_frames(track, duration)
                return

    def _recalc_total(self):
        self._total_duration = max(
            (t.duration for t, _ in self._tracks), default=0.0
        )
        self._update_widths()
        self._update_playhead()

    def _update_widths(self):
        available = self.width() - ICON_WIDTH
        if available <= 0 or not self._tracks:
            return
        if self._total_duration <= 0:
            for track, _ in self._tracks:
                track.setFixedWidth(max(20, available))
            return
        for track, _ in self._tracks:
            ratio = track.duration / self._total_duration if track.duration > 0 else 1.0
            track.setFixedWidth(max(20, int(ratio * available)))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._playhead_overlay.resize(self.size())
        self._playhead_overlay.raise_()
        self._update_widths()
        self._update_playhead()

    # ── Playhead ──

    def set_position(self, seconds: float):
        self._position = max(0.0, seconds)
        self._update_playhead()

    def _update_playhead(self):
        if self._total_duration <= 0:
            self._playhead_x = 0
        else:
            available = self.width() - ICON_WIDTH
            if available <= 0:
                self._playhead_x = 0
            else:
                ratio = max(0.0, min(1.0, self._position / self._total_duration))
                self._playhead_x = int(ICON_WIDTH + ratio * available)
        self._playhead_overlay.set_x(self._playhead_x)

    def _x_to_seconds(self, x: float) -> float:
        available = self.width() - ICON_WIDTH
        if available <= 0 or self._total_duration <= 0:
            return 0.0
        x_rel = max(0.0, min(available, x - ICON_WIDTH))
        return (x_rel / available) * self._total_duration

    def _is_near_playhead(self, x: float) -> bool:
        if self._total_duration <= 0:
            return False
        return abs(x - self._playhead_x) <= PLAYHEAD_GRAB_PX

    # ── Мышь ──

    def mouseMoveEvent(self, event):
        x = event.position().x()

        if self._dragging_playhead:
            seconds = self._x_to_seconds(x)
            self.set_position(seconds)
            self.seek_requested.emit(seconds)
            self.playhead_dragged.emit(seconds, int(x))
            return

        if self._is_near_playhead(x):
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self._is_near_playhead(event.position().x()):
            self._dragging_playhead = True
            self.setCursor(Qt.SizeHorCursor)
            self.playhead_drag_started.emit()

    def mouseReleaseEvent(self, event):
        if self._dragging_playhead:
            self._dragging_playhead = False
            self.setCursor(Qt.ArrowCursor)
            self.playhead_drag_finished.emit()

    def leaveEvent(self, event):
        if not self._dragging_playhead:
            self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    # ── Совместимость ──

    def set_duration(self, seconds: float):
        if seconds > 0:
            self._total_duration = seconds
            self._update_widths()
            self._update_playhead()

    def set_empty(self, value: bool): pass
    def set_keyframes(self, times: list): pass
    def set_active_mode(self, mode: str): pass
    def set_audio_offset(self, offset: float): pass
    def set_video_offset(self, offset: float): pass
    def set_trim(self, start: float, end: float): pass
    def set_audio_trim(self, start: float, end: float): pass
    def set_durations(self, video_dur: float, audio_dur: float): pass
    def set_linked_mode(self, linked: bool): pass
    def set_draggable(self, value: bool): pass
    def set_source(self, path: str, duration: float): pass
    def clear(self): pass
