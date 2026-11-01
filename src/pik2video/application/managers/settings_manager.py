# src/pik2video/application/managers/settings_manager.py
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

from src.pik2video.locale.languages import code_from_display_name
from src.pik2video.locale.translator import Translator

from ..session_types import SessionType
from ..settings_model import SettingsModel

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
        self.translator.set_language(code_from_display_name(current_lang))

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
        self.translator.set_language(code_from_display_name(lang))

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

    def get_auto_hide_editor(self) -> bool:
        return self.settings.global_settings.auto_hide_editor

    def set_auto_hide_editor(self, value: bool):
        self.settings.global_settings.auto_hide_editor = value
        logger.debug(f"Auto-hide editor: {value}")

    def get_show_recording_frame(self) -> bool:
        return self.settings.global_settings.show_recording_frame

    def set_show_recording_frame(self, value: bool):
        self.settings.global_settings.show_recording_frame = value
        logger.debug(f"Show recording frame: {value}")

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


    # ───── Настройки звука (общие для видео/скрина) ─────

    def get_audio_enabled(self, session_type: Optional[SessionType] = None) -> bool:
        if session_type == SessionType.VIDEO:
            return self.settings.record.common.audio_enabled
        elif session_type == SessionType.SCREEN:
            return self.settings.screen.common.audio_enabled
        return self.settings.record.common.audio_enabled

    def set_audio_enabled(self, value: bool, session_type: Optional[SessionType] = None):
        if session_type == SessionType.VIDEO:
            self.settings.record.common.audio_enabled = value
        elif session_type == SessionType.SCREEN:
            self.settings.screen.common.audio_enabled = value
        else:
            self.settings.record.common.audio_enabled = value
            self.settings.screen.common.audio_enabled = value
        logger.debug(f"Audio enabled: {value}")

    def get_audio_sources(self, session_type: Optional[SessionType] = None) -> list:
        if session_type == SessionType.VIDEO:
            return list(self.settings.record.common.audio_sources)
        elif session_type == SessionType.SCREEN:
            return list(self.settings.screen.common.audio_sources)
        elif session_type == SessionType.AUDIO:
            return list(self.settings.audio.sources)
        return list(self.settings.audio.sources)

    def set_audio_sources(self, sources: list, session_type: Optional[SessionType] = None):
        sources = list(sources)
        if session_type == SessionType.VIDEO:
            self.settings.record.common.audio_sources = sources
        elif session_type == SessionType.SCREEN:
            self.settings.screen.common.audio_sources = sources
        elif session_type == SessionType.AUDIO:
            self.settings.audio.sources = sources
        else:
            self.settings.audio.sources = sources
        logger.debug(f"Audio sources: {sources}")

    def get_audio_device(self, session_type: Optional[SessionType] = None) -> str:
        if session_type == SessionType.VIDEO:
            return self.settings.record.common.audio_device
        elif session_type == SessionType.SCREEN:
            return self.settings.screen.common.audio_device
        return self.settings.audio.device

    def set_audio_device(self, device: str, session_type: Optional[SessionType] = None):
        if session_type == SessionType.VIDEO:
            self.settings.record.common.audio_device = device
        elif session_type == SessionType.SCREEN:
            self.settings.screen.common.audio_device = device
        else:
            self.settings.audio.device = device
        logger.debug(f"Audio device: {device}")

    # ───── Настройки чистой аудио-сессии ─────

    def get_audio_timer(self) -> int:
        return self.settings.audio.timer_seconds

    def set_audio_timer(self, seconds: int):
        self.settings.audio.timer_seconds = max(0, seconds)
        logger.debug(f"Audio timer установлен: {seconds} сек")

    def get_audio_start_delay(self) -> int:
        return self.settings.audio.start_delay                    # пауза перед стартом аудио-записи

    def set_audio_start_delay(self, seconds: int):
        self.settings.audio.start_delay = max(0, seconds)
        logger.debug(f"Audio start_delay установлен: {seconds} сек")

    def get_audio_export_filename(self) -> str:
        return self.settings.audio.export_filename                    # имя файла аудио-записи

    def get_audio_sample_rate(self) -> int:
        return self.settings.audio.sample_rate                        # частота дискретизации

    def set_audio_sample_rate(self, value: int):
        if value in (44100, 48000):
            self.settings.audio.sample_rate = value
            logger.debug(f"Audio sample rate: {value}")

    def get_audio_channels(self) -> int:
        return self.settings.audio.channels                           # число каналов

    def set_audio_channels(self, value: int):
        if value in (1, 2):
            self.settings.audio.channels = value
            logger.debug(f"Audio channels: {value}")

    def set_audio_export_filename(self, name: str):
        self.settings.audio.export_filename = name                    # сохранение имени аудио-записи
        logger.debug(f"Audio export filename установлен: {name}")