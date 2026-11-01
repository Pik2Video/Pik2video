# managers/recording_manager.py
"""
Менеджер процесса записи.
Отвечает за запуск/остановку записи, таймеры обновления GUI, авто-стоп, задержку перед стартом.
"""

import logging
import time
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from src.pik2video.utils import format_size, format_time

from ..audio_recorder_service import AudioRecorderService       # сервис записи звука через AVAudioRecorder

from ..recording_service import RecordingService
from ..system_audio_recorder_service import SystemAudioRecorderService  # системный звук через pysysaudio

from ..session_types import SessionType
from ..state_machine import AppState
from .session_manager import SessionManager
from .settings_manager import SettingsManager
from .state_manager import StateManager

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
    audio_level_updated = Signal(float)                          # уровень сигнала микрофона 0.0 … 1.0
    preparation_started = Signal()                               # начало подготовки файла (merge/mux)
    preparation_finished = Signal()                              # конец подготовки

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

        self._audio_recorder = AudioRecorderService()             # сервис записи микрофона
        self._system_audio_recorder = SystemAudioRecorderService() # сервис записи системного звука
        self._level_timer = QTimer(self)                          # таймер опроса уровня сигнала
        self._level_timer.setInterval(80)                         # ~12 раз в секунду для отзывчивости
        self._level_timer.timeout.connect(self._poll_audio_level)

        self._sync_offset = 0.0                                       # смещение старта звука относительно видео

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
        is_audio = self._session.get_session_type() == SessionType.AUDIO           # аудио-сессии регион не нужен
        region_defined = is_audio or (self._session.get_region() is not None)
        if not self._state.can_start_recording(region_defined):
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
            if self._state.get_state() == AppState.COUNTDOWN:
                self._state.cancel_preparing()
                self._session.clear_runtime()
                return True

        if not self._state.can_stop_recording():
            logger.warning("Нельзя остановить запись в текущем состоянии")
            return False

        # Останавливаем таймеры обновления
        self._stop_update_timers()
        self._auto_stop_timer.stop()
        self._level_timer.stop()                                  # останавливаем опрос уровня
        self._audio_recorder.stop_recording()                     # останавливаем запись микрофона (если шла)
        self._system_audio_recorder.stop_recording()              # останавливаем запись системного звука (если шла)

        session_type = self._session.get_session_type()

        if session_type != SessionType.AUDIO:
            self._recording.stop_recording()                      # останавливаем видео-запись

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
        if self._state.get_state() != AppState.COUNTDOWN:
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
        # self.shots_updated.emit(0)


        session_type = self._session.get_session_type()

        if session_type == SessionType.AUDIO:
            sources = self._settings.get_audio_sources(SessionType.AUDIO)   # ["mic"], ["system"], ["mic","system"]
            logger.info(f"Источники звука: {sources}")
            self._start_audio_capture(session_dir, sources)                 # запускаем аудио-сервисы


        else:
            t_before = time.monotonic()                                   # монотонные часы, не wall clock

            self._recording.start_recording(
                session_dir=session_dir,
                region=self._session.get_region(),
                session_type=session_type
            )
            # start_recording блокирует до фактического захвата первого кадра в C++
            t_video_done = time.monotonic()

            if session_type == SessionType.VIDEO:
                sources = self._settings.get_audio_sources(SessionType.VIDEO)
                if sources:
                    logger.info(f"Параллельная запись звука: {sources}")
                    self._start_audio_capture(session_dir, sources)
                    t_audio_done = time.monotonic()

                    delta = t_audio_done - t_video_done                   # реальная разница стартов
                    self._sync_offset = max(0.0, delta)                   # только положительная (аудио позже видео)
                    logger.warning(
                        f"[SYNC] видео стартовало за {t_video_done - t_before:.3f} сек, "
                        f"аудио — через {delta:.3f} сек после видео"
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
        elif session_type == SessionType.SCREEN:
            return self._settings.get_screen_timer()
        elif session_type == SessionType.AUDIO:
            return self._settings.get_audio_timer()                   # отдельный таймер для аудио-сессии
        return 0

    # ---------- Обновление GUI ----------

    def _start_update_timers(self):
        """Запустить таймеры обновления времени, RAM, кадров."""
        self._time_timer.start(1000)
        self._ram_timer.start(1000)
        # Счётчик кадров имеет смысл только для SCREEN-сценария
        if self._session.get_session_type() == SessionType.SCREEN:
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
        if self._session.get_session_type() == SessionType.AUDIO:
            formatted = format_size(size_bytes)
            self.ram_updated.emit(f"Размер: {formatted}")             # для аудио — размер файла
        else:
            formatted = self._format_ram(size_bytes)
            self.ram_updated.emit(f"RAM: {formatted}")

    @staticmethod
    def _format_ram(size_bytes: int) -> str:
        """Формат RAM: 0.1 GB → 9.9 GB → 99 GB → 101 GB (минимум 0.1 GB)."""
        size_gb = size_bytes / (1024 ** 3)
        if size_gb < 0.1:
            return "0.1 GB"
        if size_gb < 10:
            return f"{size_gb:.1f} GB"
        return f"{int(size_gb)} GB"

    def update_shots(self):
        shots = self.get_frame_count()
        self.shots_updated.emit(shots)

    def _poll_audio_level(self):
        """Опросить уровни микрофона и системного звука, взять максимум."""
        mic = self._audio_recorder.poll_level() if self._audio_recorder.is_recording else 0.0
        sys = self._system_audio_recorder.poll_level() if self._system_audio_recorder.is_recording else 0.0
        self.audio_level_updated.emit(max(mic, sys))               # индикатор реагирует на громкий источник

    def _start_audio_capture(self, session_dir: Path, sources: list):
        """Запустить микрофон и/или системный звук для указанных источников."""
        rate = self._settings.get_audio_sample_rate()                   # частота из настроек
        channels = self._settings.get_audio_channels()                  # каналы из настроек

        if "mic" in sources:
            if not self._audio_recorder.start_recording(session_dir, rate, channels):
                logger.error("Не удалось запустить запись микрофона")

        if "system" in sources:
            if not self._system_audio_recorder.start_recording(session_dir, rate, channels):
                logger.error("Не удалось запустить запись системного звука")

        if self._audio_recorder.is_recording or self._system_audio_recorder.is_recording:
            self._level_timer.start()                                   # уровень — от любого активного источника

    def finalize_recording(self) -> bool:
        """
        Финализация записи. Вызывается из StateCoordinator._enter_review.
        Показывает «Подготовка файла» в UI, делает merge, возвращает True при успехе.
        """
        import shutil
        import subprocess

        session_dir = self._session.get_session_dir()
        if not session_dir:
            return False

        self.preparation_started.emit()                          # показать «Подготовка файла» в UI
        QApplication.processEvents()                             # форсировать перерисовку

        session_type = self._session.get_session_type()
        ok = True

        mic_path = session_dir / "audio.wav"                            # файл микрофона
        sys_path = session_dir / "system_audio.wav"                     # файл системного звука

        has_mic = mic_path.exists() and mic_path.stat().st_size > 44
        has_sys = sys_path.exists() and sys_path.stat().st_size > 44

        logger.info(f"Микширование: mic={has_mic}, system={has_sys}")

        if has_mic and has_sys:
            ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
            mixed_path = session_dir / "mixed.wav"
            try:
                rate = self._settings.get_audio_sample_rate()
                channels = self._settings.get_audio_channels()
                subprocess.run(
                    [
                        ffmpeg, "-y",
                        "-i", str(mic_path),
                        "-i", str(sys_path),
                        "-filter_complex", "amix=inputs=2:duration=longest:normalize=0",
                        "-ar", str(rate),
                        "-ac", str(channels),
                        str(mixed_path),
                    ],
                    check=True,
                    capture_output=True,
                    timeout=30,
                )
                mic_path.unlink()
                sys_path.unlink()
                mixed_path.rename(mic_path)
                logger.info("Микширование завершено → audio.wav")
            except Exception as e:
                logger.error(f"Ошибка микширования: {e}")

        elif has_sys and not has_mic:
            sys_path.rename(mic_path)                                   # только системный → в audio.wav
            logger.info("Только системный звук → audio.wav")

        # Ресемплинг audio.wav до целевого формата (если не совпадает).
        # pysysaudio/ScreenCaptureKit всегда отдаёт 48000Hz/2ch независимо от параметров.
        self._ensure_audio_format(mic_path)

        # Для VIDEO — муксим видео и звук в один MP4
        if session_type == SessionType.VIDEO:
            ok = self._merge_video_with_audio(session_dir)

        self.preparation_finished.emit()
        return ok

    def _ensure_audio_format(self, path: Path):
        """Привести WAV к целевым sample_rate/channels из настроек, если не совпадает."""
        import shutil
        import subprocess
        import wave

        if not path.exists() or path.stat().st_size <= 44:
            return

        rate = self._settings.get_audio_sample_rate()
        channels = self._settings.get_audio_channels()

        try:
            with wave.open(str(path), "rb") as w:
                actual_rate = w.getframerate()
                actual_channels = w.getnchannels()
        except Exception as e:
            logger.warning(f"Не удалось прочитать WAV {path}: {e}")
            return

        if actual_rate == rate and actual_channels == channels:
            return

        logger.info(
            f"Ресемплинг: {actual_rate}Hz/{actual_channels}ch → {rate}Hz/{channels}ch"
        )
        ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        tmp = path.with_name(path.stem + "_tmp" + path.suffix)
        try:
            subprocess.run(
                [
                    ffmpeg, "-y",
                    "-i", str(path),
                    "-ar", str(rate),
                    "-ac", str(channels),
                    str(tmp),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            path.unlink()
            tmp.rename(path)
            logger.info("Ресемплинг завершён")
        except Exception as e:
            logger.error(f"Ошибка ресемплинга: {e}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass

    def _merge_video_with_audio(self, session_dir) -> bool:
        """Собрать video.mp4 + audio.wav в output.mp4 со звуковой дорожкой."""
        import shutil
        import subprocess

        video_path = self._session.get_video_path()                     # C++ пишет в output.mp4
        audio_path = session_dir / "audio.wav"

        if not video_path or not video_path.exists():
            logger.warning("Видео-файл не найден — пропускаем склейку")
            return False

        if not audio_path.exists() or audio_path.stat().st_size <= 44:
            logger.info("Аудио-дорожки нет — оставляем видео без звука")
            return True



        ffmpeg = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
        merged_path = session_dir / "merged.mp4"

        offset = getattr(self, "_sync_offset", 0.0)                 # смещение старта звука относительно видео
        if offset < 0:
            offset = 0.0
        logger.info(f"[SYNC] применяем itsoffset={offset:.3f} сек")

        try:
            subprocess.run(
                [
                    ffmpeg, "-y",
                    "-i", str(video_path),
                    "-itsoffset", f"{offset:.3f}",                  # сдвигаем аудио вперёд по таймлайну
                    "-i", str(audio_path),
                    "-c:v", "copy",                                 # видео не перекодируем
                    "-af", "aresample=async=1:first_pts=0",         # подгоняем аудио под длину видео
                    "-c:a", "aac", "-b:a", "192k",                  # звук → AAC
                    "-shortest",
                    str(merged_path),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )



            video_path.unlink()                                     # удаляем исходники
            audio_path.unlink()
            merged_path.rename(video_path)                          # результат → в имя видео
            logger.info("Видео и звук собраны → output.mp4")
            return True
        except Exception as e:
            logger.error(f"Ошибка сборки видео+звук: {e}")
            return False

    # ---------- Сброс ----------

    def clear(self):
        """Сбросить состояние менеджера (остановить всё)."""
        self._stop_update_timers()
        self._auto_stop_timer.stop()
        self._level_timer.stop()                                   # останавливаем опрос уровня звука
        self._is_processing = False