# src/pik2video/core/video_assembler.py

from pathlib import Path
from typing import List
import cv2
import numpy as np

class VideoAssembler:
    """
    Сборка видео из отдельных кадров.
    
    Используется после screen capture для создания
    итогового видео с заданным FPS.
    """
    
    @staticmethod
    def assemble(frames_dir: Path, output_path: Path, fps: int, fourcc: int) -> bool:
        """
        Собирает все PNG кадры из frames_dir в видео.
        
        Args:
            frames_dir: папка с кадрами (frame_000001.png, ...)
            output_path: куда сохранить видео
            fps: кадров в секунду в итоговом видео
        
        Returns:
            True если успешно, False если ошибка
        """
        # Получаем все PNG файлы в правильном порядке
        frame_files = sorted(frames_dir.glob("frame_*.png"))
        
        if not frame_files:
            return False
        
        # Читаем первый кадр, чтобы узнать размер
        first_frame = cv2.imread(str(frame_files[0]))
        if first_frame is None:
            return False
        
        height, width = first_frame.shape[:2]
        
        # Инициализируем VideoWriter
        #fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(output_path),
            fourcc,
            fps,
            (width, height)
        )
        
        if not writer.isOpened():
            return False
        
        # Записываем все кадры
        for frame_path in frame_files:
            frame = cv2.imread(str(frame_path))
            if frame is not None:
                writer.write(frame)
        
        writer.release()
        return True