# src/pic2vid/core/frame_capturer.py

import time
import threading
from pathlib import Path
from typing import Optional
import mss
import numpy as np
from PIL import Image

class FrameCapturer:
    """
    Серийный захват экрана для screen capture режима.
    
    Отвечает за:
    - захват кадров с заданным интервалом (кадры в минуту)
    - сохранение кадров во временную папку как PNG
    - подсчёт количества кадров
    """
    
    def __init__(self, output_dir: Path, shots_per_minute: int, region: dict):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # интервал между кадрами в секундах
        self.interval = 60.0 / shots_per_minute
        self.region = region
        
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_count = 0
    
    def start(self):
        """Запуск захвата (блокирующий, вызывать в отдельном потоке)"""
        if self._running:
            raise RuntimeError("Захват уже запущен")
        
        self._running = True
        self._capture_loop()
    
    def stop(self):
        """Остановка захвата"""
        self._running = False
        self._stop_event.set()
        
        if self._thread:
            self._thread.join()
    
    def get_frame_count(self) -> int:
        """Количество захваченных кадров"""
        return self._frame_count
    
    def _capture_loop(self):
        """Основной цикл захвата кадров"""
        next_capture_time = time.time()
        
        with mss.mss() as sct:
            while self._running:
                now = time.time()
                
                # Ждём до следующего кадра
                if now < next_capture_time:
                    time.sleep(next_capture_time - now)
                
                if not self._running:
                    break
                
                # Захват кадра
                screenshot = sct.grab(self.region)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Сохраняем
                frame_path = self.output_dir / f"frame_{self._frame_count:06d}.png"
                img.save(frame_path)
                
                self._frame_count += 1
                next_capture_time += self.interval
    
    def is_running(self) -> bool:
        return self._running