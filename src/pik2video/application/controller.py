# src/pik2video/application/controller.py
"""
Главный контроллер приложения.
Фасад, который делегирует логику менеджерам.
"""

import logging
from pathlib import Path
from typing import Optional

import psutil
from PySide6.QtCore import QObject, Signal

from .managers.ffmpeg_manager import FFmpegManager
from .managers.recording_manager import RecordingManager
from .managers.session_manager import SessionManager
from .managers.settings_manager import SettingsManager
from .managers.state_manager import StateManager
from .recording_service import RecordingService
from .session_types import SessionType
from .state_machine import AppState

logger = logging.getLogger(__name__)


class AppController(QObject):
    # Сигналы для GUI
    state_changed = Signal(AppState)
    ffmpeg_required = Signal()
    time_updated = Signal(str)
    ram_updated = Signal(str)
    shots_updated = Signal(int)
    audio_level_updated = Signal(float)   # уровень микрофона 0.0 … 1.0
    open_editor_requested = Signal(str)   # путь к файлу
    preparation_started = Signal()        # начало подготовки файла
    preparation_finished = Signal()       # конец подготовки


    def __init__(self, base_tmp_dir: Optional[Path] = None):
        
        super().__init__()

        # ---------- Менеджеры ----------
        self.settings_manager = SettingsManager()
        self.settings_manager.load()

        self.ffmpeg_manager = FFmpegManager()
        self.ffmpeg_manager.ffmpeg_required.connect(self.ffmpeg_required.emit)

        self.state_manager = StateManager()
        self.state_manager.state_changed.connect(self.state_changed.emit)

        tmp_dir = base_tmp_dir or Path(__file__).resolve().parents[3] / "data" / "tmp"    # data/tmp в корне проекта
        self.session_manager = SessionManager(tmp_dir)

        recording_service = RecordingService(self.settings_manager.settings)
        self.recording_manager = RecordingManager(
            settings_manager=self.settings_manager,
            state_manager=self.state_manager,
            session_manager=self.session_manager,
            recording_service=recording_service
        )
        # Пробрасываем сигналы от RecordingManager
        self.recording_manager.time_updated.connect(self.time_updated.emit)
        self.recording_manager.ram_updated.connect(self.ram_updated.emit)
        self.recording_manager.shots_updated.connect(self.shots_updated.emit)
        self.recording_manager.audio_level_updated.connect(self.audio_level_updated.emit)
        self.recording_manager.preparation_started.connect(self.preparation_started.emit)
        self.recording_manager.preparation_finished.connect(self.preparation_finished.emit)

    # =========================================================
    #  Публичные методы (фасад для менеджеров)
    # =========================================================

    # ---------- Состояние и сессия ----------

    def get_session_type(self) -> Optional[SessionType]:
        return self.session_manager.get_session_type()

    def prepare_video(self):
        logger.info("Запрошен PREPARING_VIDEO")

        if not self.ffmpeg_manager.ensure_ffmpeg():
            logger.warning("Нет FFmpeg → остаёмся в IDLE")
            return

        self.session_manager.set_session_type(SessionType.VIDEO)

        if self.state_manager.prepare_video():
            logger.info("Переход в PREPARING_VIDEO выполнен")
        else:
            logger.warning("StateManager запретил переход")
            self.session_manager.set_session_type(None)

    def prepare_screen(self):
        logger.info("Запрошен PREPARING_SCREEN")

        if not self.ffmpeg_manager.ensure_ffmpeg():
            logger.warning("Нет FFmpeg → остаёмся в IDLE")
            return

        self.session_manager.set_session_type(SessionType.SCREEN)

        if self.state_manager.prepare_screen():
            logger.info("Переход в PREPARING_SCREEN выполнен")
        else:
            logger.warning("StateManager запретил переход")
            self.session_manager.set_session_type(None)

    def prepare_audio(self):
        logger.info("Запрошен PREPARING_AUDIO")

        self.session_manager.set_session_type(SessionType.AUDIO)       # тип сессии — только звук

        if self.state_manager.prepare_audio():
            logger.info("Переход в PREPARING_AUDIO выполнен")
        else:
            logger.warning("StateManager запретил переход")
            self.session_manager.set_session_type(None)                # откат типа сессии при неудаче

    def cancel_session(self):
        logger.info("Запрошен CANCEL_SESSION")
        if self.state_manager.cancel_preparing():
            self.session_manager.clear_runtime()
        else:
            logger.warning("Отмена невозможна в текущем состоянии")

    def set_raw_coordinates(self, coords: dict):
        """Установить координаты области записи."""
        try:
            self.session_manager.set_raw_coordinates(coords)
        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")

    def has_active_session_data(self) -> bool:
        return self.session_manager.has_data()

    def get_current_session_file(self):
        """Путь к файлу текущей сессии (видео или аудио в зависимости от типа)."""
        if self.session_manager.get_session_type() == SessionType.AUDIO:
            return self.session_manager.get_audio_path()              # для аудио-сессии берём аудиофайл
        return self.session_manager.get_video_path()

    def get_drafts_dir(self) -> Path:
        """Папка для временных файлов редактора (черновиков)."""
        drafts_dir = Path(__file__).resolve().parents[3] / "data" / "drafts"     # data/drafts в корне проекта
        drafts_dir.mkdir(parents=True, exist_ok=True)
        return drafts_dir

    def get_thumbs_dir(self) -> Path:
        """Папка для кэша миниатюр видеофайлов."""
        thumbs_dir = Path(__file__).resolve().parents[3] / "data" / "thumbs"     # data/thumbs в корне проекта
        thumbs_dir.mkdir(parents=True, exist_ok=True)
        return thumbs_dir


    # ---------- Проверки состояния (прокси для StateManager) ----------

    def is_recording(self) -> bool:
        return self.state_manager.is_recording()

    def is_preparing(self) -> bool:
        return self.state_manager.is_preparing()

    def is_review(self) -> bool:
        return self.state_manager.is_review()

    # ---------- Запись ----------

    def can_start_recording(self) -> bool:
        region = self.session_manager.get_region()
        return self.state_manager.can_start_recording(region is not None)

    def start_recording(self) -> bool:
        return self.recording_manager.start_recording()

    def stop_recording(self) -> bool:
        return self.recording_manager.stop_recording()

    def finalize_recording(self) -> bool:
        """Финализация: merge/mux. Вызывается из StateCoordinator._enter_review."""
        session_type = self.session_manager.get_session_type()
        if session_type in (SessionType.AUDIO, SessionType.VIDEO):
            return self.recording_manager.finalize_recording()
        return True

    def discard_session(self) -> bool:
        logger.info("Запрошен DISCARD_SESSION")
        if not self.state_manager.can_discard_session():
            logger.warning("Нельзя удалить в текущем состоянии")
            return False

        logger.debug("Удаляем временную сессию")
        self.session_manager.cleanup()
        self.session_manager.clear_runtime()
        self.state_manager.discard_session()
        logger.debug("StateManager перевёл в IDLE")
        return True

    # ---------- Получение информации о сессии ----------

    def get_elapsed_time(self) -> float:
        return self.recording_manager.get_elapsed_time()

    def get_session_size(self) -> int:
        return self.recording_manager.get_session_size()

    def get_cpu_usage(self) -> int:
        try:
            return int(psutil.cpu_percent(interval=None))
        except Exception:
            return 0

    # ---------- Прокси для RecordingManager (обновление GUI) ----------
    def update_time(self):
        self.recording_manager.update_time()

    def update_ram(self):
        self.recording_manager.update_ram()

    def update_shots(self):
        self.recording_manager.update_shots()

    # ---------- Прокси для SettingsManager ----------

    def get_translator(self):
        return self.settings_manager.get_translator()

    def save_settings(self):
        self.settings_manager.save()

    def get_language(self):
        return self.settings_manager.get_language()

    def set_language(self, value):
        self.settings_manager.set_language(value)
        self.state_changed.emit(self.state_manager.get_state())

    def get_text_size(self):
        return self.settings_manager.get_text_size()

    def set_text_size(self, value):
        self.settings_manager.set_text_size(value)

    def get_show_tooltips(self):
        return self.settings_manager.get_show_tooltips()

    def set_show_tooltips(self, value):
        self.settings_manager.set_show_tooltips(value)

    def get_always_on_top(self):
        return self.settings_manager.get_always_on_top()

    def set_always_on_top(self, value):
        self.settings_manager.set_always_on_top(value)
        self.state_changed.emit(self.state_manager.get_state())

    def get_preset_vertical(self):
        return self.settings_manager.get_preset_vertical()

    def set_preset_vertical(self, value):
        self.settings_manager.set_preset_vertical(value)

    def get_auto_hide_editor(self) -> bool:
        return self.settings_manager.get_auto_hide_editor()

    def set_auto_hide_editor(self, value: bool):
        self.settings_manager.set_auto_hide_editor(value)

    def get_show_recording_frame(self) -> bool:
        return self.settings_manager.get_show_recording_frame()

    def set_show_recording_frame(self, value: bool):
        self.settings_manager.set_show_recording_frame(value)

    def get_record_fps(self):
        return self.settings_manager.get_record_fps()

    def set_record_fps(self, fps):
        self.settings_manager.set_record_fps(fps)

    def get_record_quality(self):
        return self.settings_manager.get_record_quality()

    def set_record_quality(self, quality):
        self.settings_manager.set_record_quality(quality)

    def get_record_timer(self):
        return self.settings_manager.get_record_timer()

    def set_record_timer(self, seconds):
        self.settings_manager.set_record_timer(seconds)

    def get_screen_fps(self):
        return self.settings_manager.get_screen_fps()

    def set_screen_fps(self, value):
        self.settings_manager.set_screen_fps(value)

    def get_screen_timer(self):
        return self.settings_manager.get_screen_timer()

    # ───── Настройки звука ─────

    def get_audio_enabled(self) -> bool:
        return self.settings_manager.get_audio_enabled(self.session_manager.get_session_type())

    def set_audio_enabled(self, value: bool):
        
        self.settings_manager.set_audio_enabled(value, self.session_manager.get_session_type())

    def get_audio_sources(self) -> list:
        return self.settings_manager.get_audio_sources(self.session_manager.get_session_type())

    def set_audio_sources(self, sources: list):
        self.settings_manager.set_audio_sources(sources, self.session_manager.get_session_type())

    def get_audio_device(self) -> str:
        return self.settings_manager.get_audio_device(self.session_manager.get_session_type())

    def set_audio_device(self, device: str):
        self.settings_manager.set_audio_device(device, self.session_manager.get_session_type())

    def get_audio_timer(self) -> int:
        return self.settings_manager.get_audio_timer()

    def set_audio_timer(self, seconds: int):
        self.settings_manager.set_audio_timer(seconds)

    def get_audio_export_filename(self) -> str:
        return self.settings_manager.get_audio_export_filename()      # геттер для GUI аудио-сессии

    def set_audio_export_filename(self, name: str):
        self.settings_manager.set_audio_export_filename(name)         # сеттер для GUI аудио-сессии

    def get_audio_sample_rate(self) -> int:
        return self.settings_manager.get_audio_sample_rate()

    def set_audio_sample_rate(self, value: int):
        self.settings_manager.set_audio_sample_rate(value)

    def get_audio_channels(self) -> int:
        return self.settings_manager.get_audio_channels()

    def set_audio_channels(self, value: int):
        self.settings_manager.set_audio_channels(value)

    def set_screen_timer(self, seconds):
        self.settings_manager.set_screen_timer(seconds)

    def get_start_delay(self) -> int:
        session_type = self.session_manager.get_session_type()
        if session_type == SessionType.VIDEO:
            return self.settings_manager.get_record_start_delay()
        elif session_type == SessionType.SCREEN:
            return self.settings_manager.get_screen_start_delay()
        elif session_type == SessionType.AUDIO:
            return self.settings_manager.get_audio_start_delay()
        return self.settings_manager.get_record_start_delay()

    def set_start_delay(self, seconds: int):
        session_type = self.session_manager.get_session_type()
        if session_type == SessionType.VIDEO:
            self.settings_manager.set_record_start_delay(seconds)
        elif session_type == SessionType.SCREEN:
            self.settings_manager.set_screen_start_delay(seconds)
        elif session_type == SessionType.AUDIO:
            self.settings_manager.set_audio_start_delay(seconds)
        else:
            self.settings_manager.set_record_start_delay(seconds)
            self.settings_manager.set_screen_start_delay(seconds)

    def get_export_filename(self):
        return self.settings_manager.get_export_filename()

    def set_export_filename(self, name):
        self.settings_manager.set_export_filename(name)


    # =========================================================
    #  Внутренние вспомогательные методы
    # =========================================================

    # ---------- DEV метод (оставлен для тестов) ----------
    def set_state_dev(self, state: AppState, session_type: Optional[SessionType] = None):
        """
        DEV ONLY: эмулирует переходы состояний для тестирования GUI.
        """
        logger.debug(f"Запрос состояния: {state}")
        self.session_manager.clear_runtime()

        if state == AppState.IDLE:
            self.state_manager.set_state_dev(AppState.IDLE)
            self.session_manager.set_session_type(None)
            return

        if session_type is None:
            session_type = SessionType.VIDEO
        self.session_manager.set_session_type(session_type)

        # Подготавливаем регион для эмуляции записи
        # Для аудио регион не нужен — координаты не задаём
        if state in (AppState.RECORDING, AppState.REVIEW) and session_type != SessionType.AUDIO:
            try:
                self.session_manager.set_raw_coordinates({
                    "x1": 0, "y1": 0, "x2": 800, "y2": 600
                })
            except ValueError:
                pass

        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN,
                     AppState.PREPARING_AUDIO,
                     AppState.RECORDING, AppState.REVIEW):
            if session_type == SessionType.AUDIO:
                preparing_state = AppState.PREPARING_AUDIO
            elif session_type == SessionType.VIDEO:
                preparing_state = AppState.PREPARING_VIDEO
            else:
                preparing_state = AppState.PREPARING_SCREEN
            logger.debug(f"→ Эмуляция {preparing_state}")
            self.state_manager.set_state_dev(preparing_state)

        if state in (AppState.RECORDING, AppState.REVIEW):
            logger.debug("→ Эмуляция RECORDING")
            self.state_manager.set_state_dev(AppState.RECORDING)

        if state == AppState.REVIEW:
            logger.debug("→ Эмуляция REVIEW")
            self.state_manager.set_state_dev(AppState.REVIEW)
