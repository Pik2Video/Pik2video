
import logging

import subprocess
import time
import threading
from pathlib import Path
from typing import Optional
import mss
import numpy as np

from src.pik2video.infrastructure.ffmpeg.ffmpeg_service import FFmpegService

logger = logging.getLogger(__name__)

class FFmpegVideoRecorder:
    """
    Низкоуровневый модуль записи видео с экрана через FFmpeg.
    
    Отвечает ТОЛЬКО за:
    - захват кадров экрана (mss)
    - кодирование видео через FFmpeg (pipe)
    - запись в файл
    
    Преимущества перед VideoRecorder (OpenCV):
    - Аппаратное ускорение (на macOS VideoToolbox)
    - Лучшие кодеки (H.264, H.265)
    - Гибкие настройки качества (CRF)
    - Устойчивость к обрыву записи (MKV контейнер)
    """

    def __init__(
        self,
        output_path: Path,
        fps: int,
        region: dict,
        quality: str = "Среднее",
        fourcc: Optional[str] = None  # оставлен для обратной совместимости
    ):
        self.output_path = output_path
        self.fps = fps
        self.region = region
        self.quality = quality
        
        # FFmpeg процесс
        self._process: Optional[subprocess.Popen] = None
        self._ffmpeg_service = FFmpegService()
        
        # Состояние
        self.running: bool = False
        self._start_time: Optional[float] = None
        self._frame_count: int = 0

    def start(self):
        """
        Запуск записи видео.
        Метод блокирующий — должен вызываться из отдельного потока.
        """
        if self.running:
            raise RuntimeError("Запись уже запущена")

        # Запускаем FFmpeg процесс
        self._start_ffmpeg_process()
        
        # Начинаем захват
        self.running = True
        self._start_time = time.time()
        self._capture_loop()

    def stop(self):
        """Остановка записи"""
        self.running = False

    def get_elapsed_time(self) -> float:
        """Время записи в секундах"""
        if not self._start_time:
            return 0.0
        return time.time() - self._start_time

    def get_frame_count(self) -> int:
        """Количество захваченных кадров"""
        return self._frame_count

    # ===== ВНУТРЕННЯЯ ЛОГИКА =====

    def _start_ffmpeg_process(self):
        """Запуск FFmpeg процесса"""
        
        width = self.region["width"]
        height = self.region["height"]
        
        # Собираем команду FFmpeg
        cmd = self._ffmpeg_service.build_recording_command(
            output_path=self.output_path,
            width=width,
            height=height,
            fps=self.fps,
            quality=self.quality
        )
        
        logger.debug(f"Запуск FFmpeg: {' '.join(cmd)}")
        
        # Запускаем процесс с pipe в stdin
        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
        except Exception as e:
            raise RuntimeError(f"Не удалось запустить FFmpeg: {e}")

    def _capture_loop(self):
        """
        Основной цикл захвата кадров.
        Захватывает экран → отправляет в FFmpeg через stdin.
        """
        frame_interval = 1.0 / self.fps
        next_frame_time = time.time()

        with mss.mss() as sct:
            while self.running:
                now = time.time()
                
                # Соблюдаем частоту кадров
                if now < next_frame_time:
                    sleep_time = next_frame_time - now
                    if sleep_time > 0.001:
                        time.sleep(sleep_time)
                
                if not self.running:
                    break

                # Захват кадра
                screenshot = sct.grab(self.region)
                
                # Конвертация BGRA → BGR (rawvideo формат для FFmpeg)
                frame = np.array(screenshot)
                frame = frame[:, :, :3]  # убираем альфа-канал
                frame = frame[:, :, ::-1]  # BGRA → RGB (FFmpeg ожидает RGB)
                
                # Отправляем кадр в FFmpeg
                try:
                    if self._process and self._process.stdin:
                        self._process.stdin.write(frame.tobytes())
                        self._frame_count += 1
                except BrokenPipeError:
                    logger.error("Ошибка: pipe закрыт")
                    break
                except Exception as e:
                    logger.error(f"Ошибка отправки кадра: {e}")
                    break
                
                next_frame_time += frame_interval

        # Корректное завершение
        self._cleanup()

    def _cleanup(self):
        """Корректное освобождение ресурсов"""
        if self._process:
            try:
                # Закрываем stdin
                if self._process.stdin:
                    self._process.stdin.close()
                
                # Читаем stderr для отладки
                if self._process.stderr:
                    stderr_output = self._process.stderr.read().decode('utf-8', errors='ignore')
                    if stderr_output:
                        logger.debug(f"FFmpeg stderr:\n{stderr_output}")
                
                # Ждём завершения
                self._process.wait(timeout=5)
                logger.debug(f"FFmpeg завершён, returncode={self._process.returncode}")
                
            except subprocess.TimeoutExpired:
                logger.warning("Принудительное завершение FFmpeg")
                self._process.kill()
                self._process.wait()
            except Exception as e:
                logger.error(f"Ошибка при завершении: {e}")
            finally:
                self._process = None