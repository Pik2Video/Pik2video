# src/pik2video/application/audio_recorder_service.py
"""
Сервис записи звука на macOS через PyObjC + AVAudioRecorder.

Отвечает за:
- запись микрофона в WAV-файл
- публикацию уровня сигнала (dBFS → 0.0 … 1.0) через callback
- корректное освобождение ресурсов

Не знает:
- про видео, скриншоты, ffmpeg
- про GUI (только callback уровня)
"""

import logging
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    import AVFoundation
    from Foundation import NSURL
    PYOBJC_AVAILABLE = True
except ImportError as e:
    logger.warning(f"PyObjC не установлен — запись звука недоступна: {e}")
    PYOBJC_AVAILABLE = False


class AudioRecorderService:
    """
    Запись микрофона в WAV через AVAudioRecorder.

    Один экземпляр — одна запись. После stop_recording повторный
    start_recording создаёт новый файл и новый recorder.
    """

    def __init__(self, level_callback: Optional[Callable[[float], None]] = None):
        self._level_callback = level_callback      # функция для передачи уровня в UI
        self._recorder = None                      # AVAudioRecorder
        self._is_recording = False
        self._start_time = 0.0
        self._output_path: Optional[Path] = None

    # ---------------- API ----------------

    def is_available(self) -> bool:
        return PYOBJC_AVAILABLE

    def start_recording(self, session_dir: Path, sample_rate: int = 48000, channels: int = 2) -> bool:
        """Начать запись микрофона в WAV внутри session_dir."""
        if not PYOBJC_AVAILABLE:
            logger.error("PyObjC не установлен — запись невозможна")
            return False
        if self._is_recording:
            logger.warning("Запись уже идёт")
            return False

        try:
            output_file = session_dir / "audio.wav"                # имя файла фиксируем
            url = NSURL.fileURLWithPath_(str(output_file))         # URL для AVAudioRecorder

            settings = {
                AVFoundation.AVFormatIDKey: AVFoundation.kAudioFormatLinearPCM,  # WAV = LinearPCM
                AVFoundation.AVSampleRateKey: float(sample_rate),                # частота из настроек
                AVFoundation.AVNumberOfChannelsKey: channels,                    # каналы из настроек
                AVFoundation.AVLinearPCMBitDepthKey: 16,                         # 16 бит
                AVFoundation.AVLinearPCMIsFloatKey: False,                       # целочисленные сэмплы
                AVFoundation.AVLinearPCMIsBigEndianKey: False,                   # little-endian для WAV
            }

            result = AVFoundation.AVAudioRecorder.alloc().initWithURL_settings_error_(
                url,
                settings,
                None,
            )
            recorder = result[0] if isinstance(result, tuple) else result       # PyObjC отдаёт (obj, error)
            if recorder is None:
                logger.error("Не удалось создать AVAudioRecorder")
                return False

            recorder.setMeteringEnabled_(True)                                  # включаем измерение уровня

            if not recorder.record():                                           # запускаем запись
                logger.error("AVAudioRecorder.record() вернул False")
                return False

            self._recorder = recorder
            self._output_path = output_file
            self._start_time = time.time()
            self._is_recording = True

            logger.info(f"Аудио-запись началась: {output_file}")
            return True

        except Exception as e:
            logger.exception(f"Ошибка запуска аудио-записи: {e}")
            self._cleanup()
            return False

    def stop_recording(self) -> bool:
        """Остановить запись."""
        if not self._is_recording:
            return False
        try:
            if self._recorder is not None:
                self._recorder.stop()                                          # останавливаем запись
        except Exception as e:
            logger.warning(f"Ошибка остановки recorder: {e}")

        self._is_recording = False
        logger.info(f"Аудио-запись остановлена: {self._output_path}")
        self._cleanup()
        return True

    def get_elapsed_time(self) -> float:
        """Длительность текущей записи в секундах."""
        if not self._is_recording:
            return 0.0
        return time.time() - self._start_time

    def poll_level(self) -> float:
        """
        Опросить текущий уровень сигнала.
        Возвращает значение 0.0 … 1.0. Вызывать раз в 50–100 мс.
        """
        if not self._is_recording or self._recorder is None:
            return 0.0
        try:
            self._recorder.updateMeters()                                      # обновить показания
            db = self._recorder.averagePowerForChannel_(0)                     # средняя мощность в dBFS
            return self._db_to_level(db)
        except Exception as e:
            logger.debug(f"Ошибка опроса уровня: {e}")
            return 0.0

    # ---------------- Внутренние ----------------

    @staticmethod
    def _db_to_level(db: float) -> float:
        """
        Перевести dBFS (-160 … 0) в линейный уровень 0.0 … 1.0.
        Диапазон -60 … 0 дБ растягивается на 0 … 1.
        """
        if db <= -60.0:
            return 0.0
        if db >= 0.0:
            return 1.0
        return (db + 60.0) / 60.0

    def _cleanup(self):
        """Освободить ссылку на recorder."""
        self._recorder = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording