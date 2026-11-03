# src/pik2video/application/editor/managers/export_settings.py
"""
Настройки экспорта.

Отвечает за:
- формат (MP4/MKV/AVI/MOV/GIF)
- разрешение (original/1080p/720p/480p)
- битрейт (auto/manual + значение)
- поворот (0/90/180/270)
- скорость (0.25x … 4x)
- путь экспорта (куда сохранять)
- состояние экспорта (идёт ли сейчас)

Не знает:
- про GUI
- про QProcess/ffmpeg (это делает ExportService)
- про модели файлов

Сигналы (settings_changed, exporting_started/finished) эмитятся через EditorState.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class ExportSettings:
    """Runtime-настройки экспорта (не переживают перезапуск)."""

    def __init__(self, state):
        """state — EditorState. Нужен для эмита сигналов."""
        self._state = state

        self._format: str = "MP4"
        self._resolution: str = "original"
        self._bitrate_mode: str = "auto"
        self._bitrate_value: str = "4M"
        self._rotation: int = 0
        self._speed: float = 1.0
        self._export_path: str = str(Path.home() / "Desktop" / "output_file")
        self._is_exporting: bool = False

    # ── Формат ──

    def get_format(self) -> str:
        return self._format

    def set_format(self, fmt: str):
        if fmt == self._format:
            return
        self._format = fmt
        logger.debug(f"Формат в ExportSettings: {fmt}")
        self._state.settings_changed.emit()

    # ── Разрешение ──

    def get_resolution(self) -> str:
        return self._resolution

    def set_resolution(self, value: str):
        if value == self._resolution:
            return
        self._resolution = value
        logger.debug(f"Разрешение в ExportSettings: {value}")
        self._state.settings_changed.emit()

    # ── Битрейт ──

    def get_bitrate_mode(self) -> str:
        return self._bitrate_mode

    def get_bitrate_value(self) -> str:
        return self._bitrate_value

    def set_bitrate(self, mode: str, value: str):
        if mode == self._bitrate_mode and value == self._bitrate_value:
            return
        self._bitrate_mode = mode
        self._bitrate_value = value
        logger.debug(f"Битрейт в ExportSettings: {mode}, {value}")
        self._state.settings_changed.emit()

    # ── Поворот ──

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, angle: int):
        if angle == self._rotation:
            return
        self._rotation = angle
        logger.debug(f"Поворот в ExportSettings: {angle}°")
        self._state.settings_changed.emit()

    # ── Скорость ──

    def get_speed(self) -> float:
        return self._speed

    def set_speed(self, value: float):
        if value == self._speed:
            return
        self._speed = value
        logger.debug(f"Скорость в ExportSettings: {value}x")
        self._state.settings_changed.emit()

    # ── Путь экспорта ──

    def get_export_path(self) -> str:
        return self._export_path

    def set_export_path(self, path: str):
        if path == self._export_path:
            return
        self._export_path = path
        logger.debug(f"Путь экспорта в ExportSettings: {path}")
        self._state.settings_changed.emit()

    # ── Состояние экспорта ──

    def start_exporting(self):
        self._is_exporting = True
        self._state.exporting_started.emit()

    def finish_exporting(self, success: bool):
        self._is_exporting = False
        self._state.exporting_finished.emit(success)

    def is_exporting(self) -> bool:
        return self._is_exporting
