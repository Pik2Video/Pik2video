# managers/recording_manager.py
"""
Менеджер процесса записи.
Отвечает за запуск/остановку записи, таймеры обновления GUI, авто-стоп, задержку перед стартом.
"""

import logging
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal


from ..session_types import SessionType
from ..state_machine import AppState
from ..recording_service import RecordingService
from .settings_manager import SettingsManager
from .state_manager import StateManager
from .session_manager import SessionManager
from src.pik2video.utils import format_time, format_size

logger = logging.getLogger(__name__)


class RecordingManager(QObject):
    """
    Управляет процессом записи:
    - запуск и остановка через RecordingService
    - обновление времени, RAM, кадров через таймеры
    - авто-остановка по таймеру
    - задержка перед стартом
    """

    # Сигналы для GUI (проксируются из контроллера)
    time_updated = Signal(str)
    ram_updated = Signal(str)
    shots_updated = Signal(int)

    def __init__(
        self,
        settings_manager: SettingsManager,
        state_manager: StateManager,
        session_manager: SessionManager,
        recording_service: RecordingService
    ):
        super().__init__()
        self._settings = settings_manager
        self._state = state_manager
        self._session = session_manager
        self._recording = recording_service

        # Таймеры для обновления GUI
        self._time_timer = QTimer(self)
        self._time_timer.timeout.connect(self.update_time)
        self._ram_timer = QTimer(self)
        self._ram_timer.timeout.connect(self.update_ram)
        self._shots_timer = QTimer(self)
        self._shots_timer.timeout.connect(self.update_shots)

        # Таймер авто-стопа
        self._auto_stop_timer = QTimer(self)
        self._auto_stop_timer.setSingleShot(True)
        self._auto_stop_timer.timeout.connect(self.stop_recording)

        # Флаг для предотвращения повторных вызовов
        self._is_processing = False

    # ---------- Публичные методы ----------

    def start_recording(self) -> bool:
        """
        Начать процесс записи (с задержкой или без).
        Возвращает True, если запись успешно инициирована.
        """
        if self._is_processing:
            logger.warning("Уже выполняется операция записи")
            return False

        # Проверка возможности старта
        region = self._session.get_region()
        if not self._state.can_start_recording(region is not None):
            logger.warning("Нельзя начать запись: регион не задан или состояние не PREPARING")
            return False

        # Переход в WAITING
        if not self._state.start_recording():
            logger.warning("StateManager запретил переход в WAITING")
            return False

        self._is_processing = True

        # Создаём сессию
        session_dir = self._session.create_session()

        # Получаем задержку
        delay = self._get_start_delay()

        if delay > 0:
            logger.debug(f"Задержка {delay} сек перед записью")
            QTimer.singleShot(delay * 1000, lambda: self._begin_recording(session_dir))
        else:
            self._begin_recording(session_dir)

        return True

    def stop_recording(self) -> bool:
        """
        Остановить запись и перейти в REVIEW.
        """
        if self._is_processing:
            # Если ещё не начали, отменяем
            self._is_processing = False
            # Возвращаемся в PREPARING, если запись не началась
            if self._state.get_state() == AppState.WAITING:
                self._state.cancel_preparing()
                self._session.clear_runtime()
                return True

        if not self._state.can_stop_recording():
            logger.warning("Нельзя остановить запись в текущем состоянии")
            return False

        # Останавливаем таймеры обновления
        self._stop_update_timers()
        self._auto_stop_timer.stop()

        # Останавливаем запись через сервис
        self._recording.stop_recording()

        # Переход в REVIEW
        self._state.stop_recording()
        logger.debug("Запись остановлена, переход в REVIEW")
        return True

    def get_elapsed_time(self) -> float:
        """Вернуть длительность текущей записи в секундах."""
        start = self._session.get_start_time()
        if not start:
            return 0.0
        return time.time() - start

    def get_session_size(self) -> int:
        """Вернуть размер сессии."""
        return self._session.get_total_size()

    def get_frame_count(self) -> int:
        """Вернуть количество кадров (для screen)."""
        if self._session.get_session_type() == SessionType.SCREEN:
            return self._recording.get_frame_count()
        return 0

    # ---------- Внутренние методы ----------

    def _get_start_delay(self) -> int:
        """Получить задержку для текущего типа сессии."""
        session_type = self._session.get_session_type()
        if session_type == SessionType.VIDEO:
            return self._settings.get_record_start_delay()
        elif session_type == SessionType.SCREEN:
            return self._settings.get_screen_start_delay()
        return self._settings.get_record_start_delay()

    def _begin_recording(self, session_dir: Path):
        """
        Фактическое начало записи (вызывается после задержки).
        """
        if self._state.get_state() != AppState.WAITING:
            logger.warning("Запись была отменена до начала")
            self._is_processing = False
            return

        if not self._state.begin_recording():
            logger.warning("Не удалось перейти в RECORDING")
            self._is_processing = False
            return

        logger.debug("Запись началась (RECORDING)")

        # Сохраняем время старта
        self._session.set_start_time(time.time())

        # Сбрасываем сигналы GUI
        self.time_updated.emit("TIME: 00:00:00")
        self.ram_updated.emit("RAM: 0 KB")
        self.shots_updated.emit(0)

        # Запускаем запись через сервис
        self._recording.start_recording(
            session_dir=session_dir,
            region=self._session.get_region(),
            session_type=self._session.get_session_type()
        )

        # Запускаем таймеры обновления
        self._start_update_timers()

        # Авто-стоп, если задан
        timer = self._get_current_timer()
        if timer > 0:
            self._auto_stop_timer.start(timer * 1000)

        self._is_processing = False

    def _get_current_timer(self) -> int:
        """Вернуть значение таймера для текущего типа сессии."""
        session_type = self._session.get_session_type()
        if session_type == SessionType.VIDEO:
            return self._settings.get_record_timer()
        else:
            return self._settings.get_screen_timer()

    # ---------- Обновление GUI ----------

    def _start_update_timers(self):
        """Запустить таймеры обновления времени, RAM, кадров."""
        self._time_timer.start(1000)
        self._ram_timer.start(1000)
        self._shots_timer.start(1000)

    def _stop_update_timers(self):
        """Остановить таймеры обновления."""
        self._time_timer.stop()
        self._ram_timer.stop()
        self._shots_timer.stop()

    def update_time(self):
        elapsed = self.get_elapsed_time()
        formatted = format_time(elapsed, "TIME:")
        self.time_updated.emit(formatted)

    def update_ram(self):
        size_bytes = self.get_session_size()
        formatted = format_size(size_bytes)
        self.ram_updated.emit(f"RAM: {formatted}")

    def update_shots(self):
        shots = self.get_frame_count()
        self.shots_updated.emit(shots)

    # ---------- Сброс ----------

    def clear(self):
        """Сбросить состояние менеджера (остановить всё)."""
        self._stop_update_timers()
        self._auto_stop_timer.stop()
        self._is_processing = False