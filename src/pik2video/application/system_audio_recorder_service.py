# src/pik2video/application/system_audio_recorder_service.py
"""
Сервис записи системного звука на macOS через pysysaudio (ScreenCaptureKit).

Отвечает за:
- запись системного звука в WAV-файл
- проверку разрешения на запись экрана
- корректную остановку

Не знает:
- про микрофон, видео, ffmpeg
- про GUI (только публикует события)
"""

import logging
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from pysysaudio import SystemAudioRecorder
    PYSYSAUDIO_AVAILABLE = True
except ImportError as e:
    logger.warning(f"pysysaudio не установлен — запись системного звука недоступна: {e}")
    PYSYSAUDIO_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

class SystemAudioRecorderService:
    """
    Запись системного звука в WAV через pysysaudio.

    Требует разрешения «Запись экрана» в системных настройках macOS.
    """

    def __init__(self):
        self._recorder = None                       # SystemAudioRecorder из pysysaudio
        self._is_recording = False
        self._start_time = 0.0
        self._output_path: Optional[Path] = None
        self._current_level = 0.0                   # текущий уровень (обновляется в фоне)
        self._level_thread = None                   # поток чтения stream()

    # ---------------- API ----------------

    def is_available(self) -> bool:
        return PYSYSAUDIO_AVAILABLE                # доступна ли библиотека

    def check_permission(self) -> bool:
        """Проверить разрешение на запись экрана (нужно для системного звука)."""
        if not PYSYSAUDIO_AVAILABLE:
            return False
        try:
            return bool(SystemAudioRecorder.check_permission())   # True если разрешено
        except Exception as e:
            logger.error(f"Ошибка проверки разрешения: {e}")
            return False

    def start_recording(self, session_dir: Path, sample_rate: int = 48000, channels: int = 2) -> bool:
        """Начать запись системного звука в session_dir/system_audio.wav."""
        if not PYSYSAUDIO_AVAILABLE:
            logger.error("pysysaudio не установлен — запись невозможна")
            return False
        if self._is_recording:
            logger.warning("Запись системного звука уже идёт")
            return False

        try:
            output_file = session_dir / "system_audio.wav"       # имя файла фиксируем

            fmt = "numpy" if NUMPY_AVAILABLE else "bytes"        # numpy, если доступен
            recorder = SystemAudioRecorder(sample_rate=sample_rate, channels=channels, format=fmt)
            recorder.start_recording(str(output_file))           # запускаем запись

            self._recorder = recorder
            self._output_path = output_file
            self._start_time = time.time()
            self._is_recording = True                             # флаг ДО старта потока

            self._current_level = 0.0                             # сбрасываем уровень
            self._level_thread = threading.Thread(                # поток для чтения уровня
                target=self._read_levels_loop, daemon=True
            )
            self._level_thread.start()                            # старт фонового чтения

            self._recorder = recorder
            self._output_path = output_file
            self._start_time = time.time()
            self._is_recording = True

            logger.info(f"Запись системного звука началась: {output_file}")
            return True

        except Exception as e:
            logger.exception(f"Ошибка запуска записи системного звука: {e}")
            self._cleanup()
            return False

    def stop_recording(self) -> bool:
        """Остановить запись."""
        if not self._is_recording:
            return False

        try:
            if self._recorder is not None:
                self._recorder.stop_recording()                  # останавливаем запись
        except Exception as e:
            logger.warning(f"Ошибка остановки system recorder: {e}")

        if self._level_thread is not None and self._level_thread.is_alive():
            self._level_thread.join(timeout=0.5)                  # ждём завершения чтения уровня
        self._level_thread = None
        self._current_level = 0.0                                 # сбрасываем уровень

        self._is_recording = False
        logger.info(f"Запись системного звука остановлена: {self._output_path}")
        self._cleanup()
        return True

    def get_elapsed_time(self) -> float:
        """Длительность текущей записи в секундах."""
        if not self._is_recording:
            return 0.0
        return time.time() - self._start_time

    def poll_level(self) -> float:
        """Уровень сигнала, обновляемый в фоне (0.0 … 1.0)."""
        return self._current_level

    def _read_levels_loop(self):
        """Читать поток pysysaudio и обновлять текущий уровень."""
        try:
            for chunk in self._recorder.stream(timeout=0.05):     # блокирующее чтение с таймаутом
                if not self._is_recording:
                    break                                          # выходим при остановке записи
                try:
                    self._current_level = self._compute_level(chunk)
                except Exception as e:
                    logger.debug(f"Ошибка расчёта уровня system: {e}")
        except Exception as e:
            logger.debug(f"Поток чтения уровня system завершён: {e}")
        finally:
            self._current_level = 0.0                             # сбрасываем при выходе

    @staticmethod
    def _compute_level(chunk) -> float:
        """Считать RMS из чанка (numpy или bytes) → 0.0 … 1.0."""
        if NUMPY_AVAILABLE and hasattr(chunk, "size"):
            if chunk.size == 0:
                return 0.0
            rms = float(np.sqrt(np.mean(np.square(chunk.astype(np.float32)))))
        else:
            import array
            samples = array.array("f")
            samples.frombytes(bytes(chunk))
            if len(samples) == 0:
                return 0.0
            sum_sq = 0.0
            for s in samples:
                sum_sq += s * s
            rms = (sum_sq / len(samples)) ** 0.5

        return min(1.0, rms * 5.0)                                # эмпирический множитель для видимости

    # ---------------- Внутренние ----------------

    def _cleanup(self):
        self._recorder = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording