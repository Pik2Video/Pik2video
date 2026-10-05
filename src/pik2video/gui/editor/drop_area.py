# src/pik2video/gui/editor/drop_area.py
"""
Правая колонка редактора (зона 4).

Содержит:
- панель со списком видеофайлов (VideoFilesPanel)
- drop-зону для аудиофайлов (DropZone)

Публикует сигналы наружу.
"""

import logging

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from .drop_zone import DropZone
from .video_files_panel import VideoFilesPanel

logger = logging.getLogger(__name__)

DROP_AREA_WIDTH = 108
DROP_VIDEO_RATIO = 2
DROP_AUDIO_RATIO = 1
GAP = 4

VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


class DropArea(QWidget):
    """Колонка из двух зон: видео (2/3) и аудио (1/3)."""

    video_dropped = Signal(str)
    video_selected = Signal(int)
    video_delete_requested = Signal()
    audio_dropped = Signal(str)
    audio_delete_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setFixedWidth(DROP_AREA_WIDTH)
        self.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)

        self.drop_video = VideoFilesPanel(extensions=VIDEO_EXTENSIONS)
        self.drop_video.file_dropped.connect(self.video_dropped.emit)
        self.drop_video.file_selected.connect(self.video_selected.emit)
        self.drop_video.delete_requested.connect(self.video_delete_requested.emit)
        layout.addWidget(self.drop_video, stretch=DROP_VIDEO_RATIO)

        self.drop_audio = DropZone(
            icon="🎵",
            label="mp3",
            extensions=AUDIO_EXTENSIONS,
            with_delete_button=True,
        )
        self.drop_audio.file_dropped.connect(self.audio_dropped.emit)
        self.drop_audio.delete_requested.connect(self.audio_delete_requested.emit)
        layout.addWidget(self.drop_audio, stretch=DROP_AUDIO_RATIO)

    # ── Публичный API ──

    def set_video_files(self, files: list, active_index: int):
        self.drop_video.set_files(files, active_index)

    def set_video_active(self, active_index: int):
        self.drop_video.set_active(active_index)

    def show_audio(self, path: str):
        self.drop_audio.show_audio(path)

    def show_audio_empty(self):
        self.drop_audio.show_empty(icon="🎵", label="mp3")
