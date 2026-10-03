# src/pik2video/gui/editor/state.py
"""
Состояние редактора.

Отвечает только за:
- список видеофайлов и активный индекс
- трим и длительность для каждого файла
- позицию воспроизведения
- публикацию сигналов при изменениях

Не знает:
- про виджеты
- про плеер
- про FFmpeg
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)



class EditorState(QObject):
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

    # ── Экспорт ──
    exporting_started = Signal()
    exporting_finished = Signal(bool)
    settings_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # Список видеофайлов
        self._video_files: list[str] = []
        self._active_index: int = -1
        self._video_durations: dict[str, float] = {}
        self._trims: dict[str, tuple] = {}

        # Аудио
        self._audio_path: Optional[str] = None
        self._audio_duration: float = 0.0

        # Воспроизведение
        self._position: float = 0.0

        self._format: str = "MP4"
        self._resolution: str = "original"
        self._bitrate_mode: str = "auto"
        self._bitrate_value: str = "4M"
        self._rotation: int = 0
        self._speed: float = 1.0

        self._export_filename: str = ""
        self._export_path: str = str(Path.home() / "Desktop" / "output_file")

        # Экспорт
        self._is_exporting: bool = False

    # ── Список видео ──

    def add_video_file(self, path: str, duration: float = 0.0):
        """Добавить видео и сделать его активным."""
        if path not in self._video_files:
            self._video_files.append(path)
            self._video_durations[path] = duration
            self._trims[path] = (0.0, duration)

        self._active_index = self._video_files.index(path)
        self._position = 0.0

        logger.debug(f"Видео добавлено: {path} (всего {len(self._video_files)})")

        self.videos_changed.emit()
        self.active_video_changed.emit(path)
        self.video_loaded.emit(path)
        self.trim_changed.emit(*self._trims[path])

    def remove_active_video(self):
        """Удалить активный файл."""
        if not self._video_files:
            return

        path = self._video_files[self._active_index]
        self._video_files.pop(self._active_index)
        self._video_durations.pop(path, None)
        self._trims.pop(path, None)

        logger.debug(f"Видео удалено: {path} (осталось {len(self._video_files)})")

        if not self._video_files:
            self._active_index = -1
            self._position = 0.0
            self.videos_changed.emit()
            self.video_unloaded.emit()
            return

        # Активируем соседний файл
        if self._active_index >= len(self._video_files):
            self._active_index = len(self._video_files) - 1

        new_path = self._video_files[self._active_index]
        self._position = 0.0

        self.videos_changed.emit()
        self.active_video_changed.emit(new_path)
        self.video_loaded.emit(new_path)
        self.trim_changed.emit(*self._trims[new_path])

    def set_active_video(self, index: int):
        """Сделать файл с этим индексом активным."""
        if index < 0 or index >= len(self._video_files):
            return
        if index == self._active_index:
            return

        self._active_index = index
        path = self._video_files[index]
        self._position = 0.0

        logger.debug(f"Активный файл: {path}")

        self.active_video_changed.emit(path)
        self.video_loaded.emit(path)
        self.trim_changed.emit(*self._trims[path])

    def get_video_files(self) -> list:
        return list(self._video_files)

    def get_active_index(self) -> int:
        return self._active_index

    def has_videos(self) -> bool:
        return len(self._video_files) > 0

    # ── Совместимость (старые имена) ──

    def set_video_file(self, path: str, duration: float = 0.0):
        """Обёртка над add_video_file — старый API."""
        self.add_video_file(path, duration)

    def clear_video(self):
        """Очистить весь список видео."""
        self._video_files.clear()
        self._video_durations.clear()
        self._trims.clear()
        self._active_index = -1
        self._position = 0.0

        self.videos_changed.emit()
        self.video_unloaded.emit()

    def has_video(self) -> bool:
        return self.has_videos()

    def get_video_path(self) -> Optional[str]:
        if self._active_index < 0:
            return None
        return self._video_files[self._active_index]

    def get_video_duration(self) -> float:
        if self._active_index < 0:
            return 0.0
        path = self._video_files[self._active_index]
        return self._video_durations.get(path, 0.0)

    def update_active_duration(self, seconds: float):
        """Обновить длительность активного файла (когда плеер её узнал)."""
        if self._active_index < 0:
            return
        path = self._video_files[self._active_index]
        self._video_durations[path] = seconds
        if self._trims[path] == (0.0, 0.0):
            self._trims[path] = (0.0, seconds)
            self.trim_changed.emit(0.0, seconds)

    # ── Аудио ──

    def set_audio_file(self, path: str, duration: float = 0.0):
        self._audio_path = path
        self._audio_duration = duration
        logger.debug(f"Аудио загружено: {path}")
        self.audio_loaded.emit(path)

    def clear_audio(self):
        self._audio_path = None
        self._audio_duration = 0.0
        self.audio_unloaded.emit()

    def has_audio(self) -> bool:
        return self._audio_path is not None

    def get_audio_path(self) -> Optional[str]:
        return self._audio_path

    def get_audio_duration(self) -> float:
        return self._audio_duration

    # ── Воспроизведение ──

    def set_position(self, seconds: float):
        if self._position != seconds:
            self._position = seconds
            self.position_changed.emit(seconds)

    def get_position(self) -> float:
        return self._position

    # ── Трим (для активного файла) ──

    def set_trim(self, start: float, end: float):
        if self._active_index < 0:
            return

        path = self._video_files[self._active_index]
        duration = self._video_durations.get(path, 0.0)

        start = max(start, 0)
        if end > duration > 0:
            end = duration
        if start >= end:
            return

        self._trims[path] = (start, end)
        self.trim_changed.emit(start, end)

    def get_trim(self) -> tuple:
        if self._active_index < 0:
            return (0.0, 0.0)
        path = self._video_files[self._active_index]
        return self._trims.get(path, (0.0, 0.0))

    def get_trim_for(self, path: str) -> tuple:
        return self._trims.get(path, (0.0, 0.0))


    def get_format(self) -> str:
        return self._format

    def set_format(self, fmt: str):
        if fmt == self._format:
            return
        self._format = fmt
        logger.debug(f"Формат в EditorState: {fmt}")
        self.settings_changed.emit()

    def get_resolution(self) -> str:
        return self._resolution

    def set_resolution(self, value: str):
        if value == self._resolution:
            return
        self._resolution = value
        logger.debug(f"Разрешение в EditorState: {value}")
        self.settings_changed.emit()

    def get_bitrate_mode(self) -> str:
        return self._bitrate_mode

    def get_bitrate_value(self) -> str:
        return self._bitrate_value

    def set_bitrate(self, mode: str, value: str):
        if mode == self._bitrate_mode and value == self._bitrate_value:
            return
        self._bitrate_mode = mode
        self._bitrate_value = value
        logger.debug(f"Битрейт в EditorState: {mode}, {value}")
        self.settings_changed.emit()

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, angle: int):
        if angle == self._rotation:
            return
        self._rotation = angle
        logger.debug(f"Поворот в EditorState: {angle}°")
        self.settings_changed.emit()

    def get_speed(self) -> float:
        return self._speed

    def set_speed(self, value: float):
        if value == self._speed:
            return
        self._speed = value
        logger.debug(f"Скорость в EditorState: {value}x")
        self.settings_changed.emit()

    def get_export_filename(self) -> str:
        return self._export_filename

    def set_export_filename(self, name: str):
        if name == self._export_filename:
            return
        self._export_filename = name
        logger.debug(f"Имя файла в EditorState: {name}")
        self.settings_changed.emit()

    def get_export_path(self) -> str:
        return self._export_path

    def set_export_path(self, path: str):
        if path == self._export_path:
            return
        self._export_path = path
        logger.debug(f"Путь экспорта в EditorState: {path}")
        self.settings_changed.emit()

    # ── Экспорт ──

    def start_exporting(self):
        self._is_exporting = True
        self.exporting_started.emit()

    def finish_exporting(self, success: bool):
        self._is_exporting = False
        self.exporting_finished.emit(success)

    def is_exporting(self) -> bool:
        return self._is_exporting
