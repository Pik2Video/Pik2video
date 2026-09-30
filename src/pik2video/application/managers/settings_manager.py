# managers/settings_manager.py
"""
Менеджер настроек приложения.

Отвечает за:
- загрузку и сохранение настроек в JSON
- доступ ко всем параметрам через геттеры и сеттеры
- управление переводчиком (Translator) в зависимости от языка
- хранение и обновление настроек для видео, экрана, финализации и глобальных
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject

from ..settings_model import SettingsModel
from src.pik2video.locale.translator import Translator
from ..session_types import SessionType

logger = logging.getLogger(__name__)


class SettingsManager(QObject):
    """
    Менеджер настроек.
    Содержит объект SettingsModel и Translator.
    Предоставляет методы для чтения/записи любых настроек.
    """

    def __init__(self):
        super().__init__()
        # Загружаем модель настроек
        self.settings = SettingsModel()
        self.settings.load_from_file()

        # Создаём переводчик и устанавливаем язык из настроек
        self.translator = Translator()
        current_lang = self.settings.global_settings.language
        lang_code = "ru" if current_lang == "Русский" else "en"
        self.translator.set_language(lang_code)

        logger.debug("SettingsManager инициализирован")

    # ---------- Сохранение и загрузка ----------

    def save(self):
        """Сохранить текущие настройки в файл"""
        self.settings.save_to_file()
        logger.info("Настройки сохранены")

    def load(self):
        """Перезагрузить настройки из файла (если нужно)"""
        self.settings.load_from_file()
        logger.info("Настройки перезагружены")

    # ---------- Доступ к переводчику ----------

    def get_translator(self):
        """Вернуть объект Translator для использования в GUI"""
        return self.translator

    # ---------- Вспомогательный метод для языка ----------

    def _apply_language(self):
        """Применить текущий язык из настроек к Translator"""
        lang = self.settings.global_settings.language
        lang_code = "ru" if lang == "Русский" else "en"
        self.translator.set_language(lang_code)

    # ---------- Глобальные настройки ----------

    def get_language(self) -> str:
        return self.settings.global_settings.language

    def set_language(self, value: str):
        self.settings.global_settings.language = value
        self._apply_language()
        logger.debug(f"Язык установлен: {value}")

    def get_text_size(self) -> int:
        return self.settings.global_settings.text_size

    def set_text_size(self, value: int):
        self.settings.global_settings.text_size = value
        logger.debug(f"Размер текста установлен: {value}")

    def get_show_tooltips(self) -> bool:
        return self.settings.global_settings.show_tooltips

    def set_show_tooltips(self, value: bool):
        self.settings.global_settings.show_tooltips = value
        logger.debug(f"Подсказки: {value}")

    def get_always_on_top(self) -> bool:
        return self.settings.global_settings.always_on_top

    def set_always_on_top(self, value: bool):
        self.settings.global_settings.always_on_top = value
        logger.debug(f"Всегда в топе: {value}")

    def get_preset_vertical(self) -> bool:
        return self.settings.global_settings.preset_vertical

    def set_preset_vertical(self, value: bool):
        self.settings.global_settings.preset_vertical = value
        logger.debug(f"Preset вертикальный: {value}")

    # ---------- Настройки записи видео (Record) ----------

    def get_record_fps(self) -> int:
        return self.settings.record.fps

    def set_record_fps(self, fps: int):
        self.settings.record.fps = fps
        logger.debug(f"Record FPS установлен: {fps}")

    def get_record_quality(self) -> str:
        return self.settings.record.common.quality

    def set_record_quality(self, quality: str):
        self.settings.record.common.quality = quality
        logger.debug(f"Record качество установлено: {quality}")

    def get_record_timer(self) -> int:
        return self.settings.record.common.timer_seconds

    def set_record_timer(self, seconds: int):
        self.settings.record.common.timer_seconds = max(0, seconds)
        logger.debug(f"Record таймер установлен: {seconds} сек")

    # ---------- Настройки захвата экрана (Screen) ----------

    def get_screen_fps(self) -> int:
        return self.settings.screen.capture_fps

    def set_screen_fps(self, value: int):
        if 1 <= value <= 1000:
            self.settings.screen.capture_fps = value
            logger.debug(f"Screen capture_fps установлено: {value}")

    def get_screen_timer(self) -> int:
        return self.settings.screen.common.timer_seconds

    def set_screen_timer(self, seconds: int):
        self.settings.screen.common.timer_seconds = max(0, seconds)
        logger.debug(f"Screen таймер установлен: {seconds} сек")

    # ---------- Общие настройки (для обоих режимов) ----------

    def get_start_delay(self, session_type: Optional[SessionType] = None) -> int:
        """
        Получить задержку перед стартом для указанного типа сессии.
        Если тип не указан — возвращает значение для VIDEO (как дефолт).
        """
        if session_type == SessionType.VIDEO:
            return self.settings.record.common.start_delay
        elif session_type == SessionType.SCREEN:
            return self.settings.screen.common.start_delay
        # Если тип не передан или None — берём из record (как основной)
        return self.settings.record.common.start_delay

    def set_start_delay(self, seconds: int, session_type: Optional[SessionType] = None):
        """
        Установить задержку перед стартом.
        Если тип не указан — устанавливает в оба режима.
        """
        seconds = max(0, seconds)
        if session_type == SessionType.VIDEO:
            self.settings.record.common.start_delay = seconds
            logger.debug(f"Record start_delay установлен: {seconds} сек")
        elif session_type == SessionType.SCREEN:
            self.settings.screen.common.start_delay = seconds
            logger.debug(f"Screen start_delay установлен: {seconds} сек")
        else:
            # Устанавливаем в оба
            self.settings.record.common.start_delay = seconds
            self.settings.screen.common.start_delay = seconds
            logger.debug(f"start_delay установлен: {seconds} сек (оба типа)")

    # ---------- Настройки финализации (Finalize) ----------

    def get_export_filename(self) -> str:
        return self.settings.finalize.common.export_filename

    def set_export_filename(self, name: str):
        self.settings.finalize.common.export_filename = name
        logger.debug(f"Export filename установлен: {name}")

    def get_export_path(self) -> str:
        path = self.settings.finalize.common.export_path
        if not path:
            path = str(Path.home() / "Desktop")
        return path

    def set_export_path(self, path: str):
        self.settings.finalize.common.export_path = path
        logger.debug(f"Export path установлен: {path}")

    def get_video_format(self) -> str:
        return self.settings.finalize.common.video_format

    def set_video_format(self, fmt: str):
        allowed = ["MP4", "MKV", "AVI", "MOV", "GIF"]
        if fmt not in allowed:
            fmt = "MP4"
        self.settings.finalize.common.video_format = fmt
        logger.debug(f"Video format установлен: {fmt}")

    def get_resolution(self) -> str:
        return self.settings.finalize.common.resolution

    def set_resolution(self, value: str):
        allowed = ["original", "1080p", "720p", "480p"]
        if value in allowed:
            self.settings.finalize.common.resolution = value
            logger.debug(f"Resolution установлен: {value}")

    def get_bitrate_mode(self) -> str:
        return self.settings.finalize.common.bitrate_mode

    def get_bitrate_value(self) -> str:
        return self.settings.finalize.common.bitrate_value

    def set_bitrate(self, mode: str, value: str):
        self.settings.finalize.common.bitrate_mode = mode
        self.settings.finalize.common.bitrate_value = value
        logger.debug(f"Bitrate установлен: {mode}, {value}")

    def get_rotation(self) -> int:
        return self.settings.finalize.common.rotation

    def set_rotation(self, angle: int):
        if angle in (0, 90, 180, 270):
            self.settings.finalize.common.rotation = angle
            logger.debug(f"Rotation установлен: {angle}°")

    def get_screen_finalize_fps(self) -> int:
        return self.settings.finalize.screen.playback_fps

    def set_screen_finalize_fps(self, fps: int):
        if 1 <= fps <= 100:
            self.settings.finalize.screen.playback_fps = fps
            logger.debug(f"Screen finalize FPS установлен: {fps}")

    def get_speed_multiplier(self) -> float:
        return self.settings.finalize.screen.speed_multiplier

    def set_speed_multiplier(self, multiplier: float):
        self.settings.finalize.screen.speed_multiplier = multiplier
        logger.debug(f"Speed multiplier установлен: {multiplier}x")

    
    # ---------- Обёртки для start_delay (чтобы не передавать session_type каждый раз) ----------

    def get_record_start_delay(self) -> int:
        return self.settings.record.common.start_delay

    def set_record_start_delay(self, seconds: int):
        self.settings.record.common.start_delay = max(0, seconds)
        logger.debug(f"Record start_delay установлен: {seconds} сек")

    def get_screen_start_delay(self) -> int:
        return self.settings.screen.common.start_delay

    def set_screen_start_delay(self, seconds: int):
        self.settings.screen.common.start_delay = max(0, seconds)
        logger.debug(f"Screen start_delay установлен: {seconds} сек")