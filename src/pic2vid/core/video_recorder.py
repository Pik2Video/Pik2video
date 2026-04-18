# src/pic2vid/core/video_recorder.py
import threading
import time
from pathlib import Path
import mss
import cv2
import numpy as np
from typing import Optional

class VideoRecorder:
    """
    Низкоуровневый модуль записи видео с экрана.

    Отвечает ТОЛЬКО за:
    - захват кадров экрана
    - кодирование видео
    - запись в файл

    НЕ управляет потоками и НЕ знает о GUI.
    """
    def __init__(self, output_path: Path, fps: int, region: dict, fourcc: Optional[int] = None):
        self.output_path = output_path  # Путь для сохранения финального файла
        self.fps = fps
        self.region = region
        self.fourcc = fourcc
        self._writer: Optional[cv2.VideoWriter] = None
        self.running: bool = False

    def start(self):
        """
        Запуск записи видео.
        Метод блокирующий — должен вызываться из отдельного потока.
        """
        if self.running:
            raise RuntimeError("Запись уже запущена")

        self._init_writer()
        self.running = True
        self._record_loop()

    def stop(self):
        """Остановка записи"""
        self.running = False

    # ===== ВНУТРЕННЯЯ ЛОГИКА =====
    def _init_writer(self):
        """Подготовка VideoWriter для сохранения видео"""
        width = self.region["width"]
        height = self.region["height"]

        fourcc = self.fourcc or cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(
            str(self.output_path),
            fourcc,
            self.fps,
            (width, height),
            True,
        )

        if not self._writer.isOpened():
            raise RuntimeError("Не удалось создать VideoWriter")

    def _record_loop(self):
        """
        Основной цикл захвата кадров.
        Работает до тех пор, пока running == True.
        """
        frame_interval = 1.0 / self.fps
        next_frame_time = time.time()

        with mss.mss() as sct:
            while self.running:
                now = time.time()
                if now < next_frame_time:
                    time.sleep(next_frame_time - now)

                frame = np.array(sct.grab(self.region))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

                self._writer.write(frame)
                next_frame_time += frame_interval

        self._release()

    def _release(self):
        """Корректное освобождение ресурсов"""
        if self._writer:
            self._writer.release()
            self._writer = None