# src/pik2video/application/editor/editor_state.py
"""
Состояние редактора — фасад с сигналами и делегатами.

Реальная логика — в компонентах (application/editor/managers/):
- MediaManager        — видео, аудио, тримы, имена экспорта
- PresetManager       — пресет кадра, зум, crop, метки зума
- TimelineManager     — метки таймлайна, cut, visible, конвертации
- PlaybackManager     — позиция, громкости, сдвиги, linked_mode
- ExportSettings      — формат, разрешение, битрейт, скорость, путь
- Persistence         — сохранение/загрузка состояния редактора в JSON

EditorState делегирует все публичные методы компонентам.
Через state эмитятся сигналы (GUI подписан на state).
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.pik2video.application.editor.managers.preset_manager import PresetManager
from src.pik2video.application.editor.managers.timeline_manager import TimelineManager
from src.pik2video.application.editor.managers.export_settings import ExportSettings
from src.pik2video.application.editor.managers.media_manager import MediaManager
from src.pik2video.application.editor.managers.playback_manager import PlaybackManager
from src.pik2video.application.editor.managers.persistence import Persistence

logger = logging.getLogger(__name__)


class EditorState(QObject):
    MAX_VIDEO_FILES = MediaManager.MAX_VIDEO_FILES   # алиас (используется в GUI)

    ASPECT_RATIOS = {                       # пресеты кадра: ключ → (pw, ph) или None
        "original": None,
        "16:9": (16, 9),
        "9:16": (9, 16),
        "1:1": (1, 1),
        "4:5": (4, 5),
        "4:3": (4, 3),
    }

    # ── Список файлов ──
    videos_changed = Signal()               # состав списка изменился
    active_video_changed = Signal(str)      # путь нового активного

    # ── Совместимость с прежним API ──
    video_loaded = Signal(str)              # активный файл загружен
    video_unloaded = Signal()               # список пуст

    # ── Аудио ──
    audio_loaded = Signal(str)
    audio_unloaded = Signal()

    # ── Воспроизведение ──
    position_changed = Signal(float)

    # ── Трим ──
    trim_changed = Signal(float, float)
    audio_trim_changed = Signal(float, float)
    audio_format_changed = Signal(str)
    crop_rect_changed = Signal(tuple)

    # ── Экспорт ──
    exporting_started = Signal()
    exporting_finished = Signal(bool)
    settings_changed = Signal()

    video_volume_changed = Signal(float)
    audio_volume_changed = Signal(float)

    audio_offset_changed = Signal(float)
    video_offset_changed = Signal(float)

    video_limit_reached = Signal()
    linked_mode_changed = Signal(bool)
    timeline_markers_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Общий словарь имён экспорта (видео + аудио). MediaManager берёт ссылку.
        self._preferred_names: dict[str, str] = {}

        # Менеджеры
        self._presets = PresetManager(self)
        self._timeline = TimelineManager(self)
        self._export_settings = ExportSettings(self)
        self._media = MediaManager(self)
        self._playback = PlaybackManager(self)

        # ── Персистентность ──
        self._persistence = Persistence(self)
        self.videos_changed.connect(self._save_files)

    # ── Media (делегаты в MediaManager) ──

    def add_video_file(self, path: str, duration: float = 0.0, preferred_name: str = ""):
        self._media.add_video_file(path, duration, preferred_name)

    def remove_active_video(self):
        self._media.remove_active_video()

    def set_active_video(self, index: int):
        self._media.set_active_video(index)

    def get_video_files(self) -> list:
        return self._media.get_video_files()

    def get_active_index(self) -> int:
        return self._media.get_active_index()

    def has_videos(self) -> bool:
        return self._media.has_videos()

    def set_video_file(self, path: str, duration: float = 0.0):
        self._media.set_video_file(path, duration)

    def clear_video(self):
        self._media.clear_video()

    def has_video(self) -> bool:
        return self._media.has_video()

    def has_any_media(self) -> bool:
        return self._media.has_any_media()

    def get_video_path(self) -> Optional[str]:
        return self._media.get_video_path()

    def get_preferred_name(self, path: str) -> str:
        return self._media.get_preferred_name(path)

    def get_video_duration(self) -> float:
        return self._media.get_video_duration()

    def get_video_duration_for(self, path: str) -> float:
        return self._media.get_video_duration_for(path)

    def update_active_duration(self, seconds: float):
        self._media.update_active_duration(seconds)

    def set_trim(self, start: float, end: float):
        self._media.set_trim(start, end)

    def commit_trim(self):
        self._media.commit_trim()

    def get_trim(self) -> tuple:
        return self._media.get_trim()

    def get_trim_for(self, path: str) -> tuple:
        return self._media.get_trim_for(path)

    def get_export_filename(self) -> str:
        return self._media.get_export_filename()

    def set_export_filename(self, name: str):
        self._media.set_export_filename(name)

    # ── Аудио (делегаты в MediaManager) ──

    def set_audio_file(self, path: str, duration: float = 0.0):
        self._media.set_audio_file(path, duration)

    def clear_audio(self):
        self._media.clear_audio()

    def has_audio(self) -> bool:
        return self._media.has_audio()

    def get_audio_path(self) -> Optional[str]:
        return self._media.get_audio_path()

    def get_audio_duration(self) -> float:
        return self._media.get_audio_duration()

    def set_audio_duration(self, duration: float):
        self._media.set_audio_duration(duration)

    def set_audio_trim(self, start: float, end: float):
        self._media.set_audio_trim(start, end)

    def commit_audio_trim(self):
        self._media.commit_audio_trim()

    def get_audio_trim(self) -> tuple:
        return self._media.get_audio_trim()

    def set_audio_format(self, fmt: str):
        self._media.set_audio_format(fmt)

    def get_audio_export_filename(self) -> str:
        return self._media.get_audio_export_filename()

    def set_audio_export_filename(self, name: str):
        self._media.set_audio_export_filename(name)

    def get_audio_format(self) -> str:
        return self._media.get_audio_format()

    # ── Preset (делегаты в PresetManager) ──

    def get_aspect_preset(self) -> str:
        return self._presets.get_aspect_preset()

    def set_aspect_preset(self, value: str):
        self._presets.set_aspect_preset(value)

    def get_aspect_zoom(self) -> int:
        return self._presets.get_aspect_zoom()

    def set_aspect_zoom(self, zoom: int, save: bool = True):
        self._presets.set_aspect_zoom(zoom, save)

    def get_crop_rect(self) -> tuple:
        return self._presets.get_crop_rect()

    def get_crop_info(self) -> tuple:
        return self._presets.get_crop_info()

    def set_crop_rect(self, rect: tuple):
        self._presets.set_crop_rect(rect)

    def get_offset_x(self) -> float:
        return self._presets.get_offset_x()

    def set_offset_x(self, value: float, save: bool = True):
        self._presets.set_offset_x(value, save)

    def compute_crop_for(self, zoom: int, offset_x: float) -> tuple:
        return self._presets.compute_crop_for(zoom, offset_x)

    def set_source_resolution(self, width: int, height: int):
        self._presets.set_source_resolution(width, height)

    def get_source_resolution(self) -> tuple:
        return self._presets.get_source_resolution()

    def add_marker(self, time_sec: float, offset_x: float, zoom: int = 0):
        self._presets.add_marker(time_sec, offset_x, zoom)

    def get_markers(self) -> list:
        return self._presets.get_markers()

    def has_zoom_markers(self) -> bool:
        return self._presets.has_zoom_markers()

    def get_marker_state_at(self, time_sec: float) -> tuple:
        return self._presets.get_marker_state_at(time_sec)

    def get_marker_offset_at(self, time_sec: float) -> float:
        return self._presets.get_marker_offset_at(time_sec)

    def remove_marker(self, time_sec: float) -> tuple:
        return self._presets.remove_marker(time_sec)

    # ── ExportSettings (делегаты в ExportSettings) ──

    def get_format(self) -> str:
        return self._export_settings.get_format()

    def set_format(self, fmt: str):
        self._export_settings.set_format(fmt)

    def get_resolution(self) -> str:
        return self._export_settings.get_resolution()

    def set_resolution(self, value: str):
        self._export_settings.set_resolution(value)

    def get_bitrate_mode(self) -> str:
        return self._export_settings.get_bitrate_mode()

    def get_bitrate_value(self) -> str:
        return self._export_settings.get_bitrate_value()

    def set_bitrate(self, mode: str, value: str):
        self._export_settings.set_bitrate(mode, value)

    def get_rotation(self) -> int:
        return self._export_settings.get_rotation()

    def set_rotation(self, angle: int):
        self._export_settings.set_rotation(angle)

    def get_speed(self) -> float:
        return self._export_settings.get_speed()

    def set_speed(self, value: float):
        self._export_settings.set_speed(value)

    def get_export_path(self) -> str:
        return self._export_settings.get_export_path()

    def set_export_path(self, path: str):
        self._export_settings.set_export_path(path)

    def start_exporting(self):
        self._export_settings.start_exporting()

    def finish_exporting(self, success: bool):
        self._export_settings.finish_exporting(success)

    def is_exporting(self) -> bool:
        return self._export_settings.is_exporting()

    # ── Playback (делегаты в PlaybackManager) ──

    def set_position(self, seconds: float):
        self._playback.set_position(seconds)

    def get_position(self) -> float:
        return self._playback.get_position()

    def get_video_volume(self) -> float:
        return self._playback.get_video_volume()

    def get_audio_volume(self) -> float:
        return self._playback.get_audio_volume()

    def set_video_volume(self, value: float):
        self._playback.set_video_volume(value)

    def set_audio_volume(self, value: float):
        self._playback.set_audio_volume(value)

    def get_audio_offset(self) -> float:
        return self._playback.get_audio_offset()

    def get_video_offset(self) -> float:
        return self._playback.get_video_offset()

    def set_audio_offset(self, value: float):
        self._playback.set_audio_offset(value)

    def set_video_offset(self, value: float):
        self._playback.set_video_offset(value)

    def get_linked_mode(self) -> bool:
        return self._playback.get_linked_mode()

    def set_linked_mode(self, value: bool):
        self._playback.set_linked_mode(value)

    # ── Timeline: метки таймлайна (делегаты в TimelineManager) ──

    def add_timeline_marker(self, time_sec: float, kind: str) -> bool:
        return self._timeline.add_timeline_marker(time_sec, kind)

    def get_timeline_markers(self, path: Optional[str] = None) -> list:
        return self._timeline.get_timeline_markers(path)

    def remove_timeline_marker(self, time_sec: float, kind: Optional[str] = None) -> bool:
        return self._timeline.remove_timeline_marker(time_sec, kind)

    def move_timeline_marker(self, old_time: float, new_time: float, save: bool = False) -> bool:
        return self._timeline.move_timeline_marker(old_time, new_time, save)

    def clear_timeline_markers(self, path: Optional[str] = None):
        return self._timeline.clear_timeline_markers(path)

    # ── Timeline: cut / visible / конвертации (делегаты в TimelineManager) ──

    def get_cut_intervals(self, path: Optional[str] = None) -> list:
        return self._timeline.get_cut_intervals(path)

    def get_visible_intervals(self, path: Optional[str] = None) -> list:
        return self._timeline.get_visible_intervals(path)

    def get_hidden_cuts(self, path: Optional[str] = None) -> list:
        return self._timeline.get_hidden_cuts(path)

    def get_display_intervals(self, path: Optional[str] = None) -> list:
        return self._timeline.get_display_intervals(path)

    def get_display_duration(self, path: Optional[str] = None) -> float:
        return self._timeline.get_display_duration(path)

    def visual_to_real(self, visual_sec: float, path: Optional[str] = None) -> float:
        return self._timeline.visual_to_real(visual_sec, path)

    def real_to_visual(self, real_sec: float, path: Optional[str] = None) -> float:
        return self._timeline.real_to_visual(real_sec, path)

    def hide_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        return self._timeline.hide_cut(start, end, path)

    def restore_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        return self._timeline.restore_cut(start, end, path)

    def is_time_visible(self, time_sec: float, path: Optional[str] = None) -> bool:
        return self._timeline.is_time_visible(time_sec, path)

    def next_visible_time(self, time_sec: float, path: Optional[str] = None) -> float:
        return self._timeline.next_visible_time(time_sec, path)

    # ── Персистентность ──

    def _save_files(self):
        """Делегат в Persistence."""
        self._persistence.save()

    def load_persisted_files(self):
        """Делегат в Persistence."""
        self._persistence.load()
