# src/pic2vid/application/recording_service.py

import time
import threading
from pathlib import Path
from typing import Optional
import cv2

from src.pic2vid.core.video_recorder import VideoRecorder
from src.pic2vid.core.frame_capturer import FrameCapturer
from src.pic2vid.core.video_assembler import VideoAssembler
from .settings_model import SettingsModel
from .session_types import SessionType


class RecordingService:
    """
    Сервис записи. Поддерживает два режима:
    - VIDEO: непрерывная запись напрямую в MP4
    - SCREEN: захват кадров, потом сборка в видео
    """

    def __init__(self, settings: SettingsModel):
        self._settings = settings
        self._session_type: Optional[SessionType] = None

        # Runtime
        self._recorder: Optional[VideoRecorder] = None
        self._capturer: Optional[FrameCapturer] = None
        self._record_thread: Optional[threading.Thread] = None
        #self._timer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._start_time: Optional[float] = None
        self._is_recording: bool = False
        self._session_dir: Optional[Path] = None

    def start_recording(self, session_dir: Path, region: dict, session_type: SessionType) -> bool:
        """Запуск записи в зависимости от типа сессии"""
        
        if self._is_recording:
            return False

        self._validate_region(region)
        self._session_dir = session_dir
        self._session_type = session_type
        self._stop_event.clear()
        self._start_time = time.time()
        self._is_recording = True

        # Запускаем запись в зависимости от типа
        if session_type == SessionType.VIDEO:
            self._start_video_recording(region)
        else:  # SCREEN
            self._start_screen_capture(region)

        return True

    def _quality_to_format(self, quality: str) -> tuple:
        """
        Преобразует качество в (fourcc, extension) для VIDEO режима
        """
        if quality == "Низкое":
            return cv2.VideoWriter_fourcc(*"XVID"), ".avi"
        elif quality == "Высокое":
            return cv2.VideoWriter_fourcc(*"MJPG"), ".avi"
        else:  # "Среднее"
            return cv2.VideoWriter_fourcc(*"mp4v"), ".mp4"

    def _format_to_fourcc(self, video_format: str) -> int:
        """
        Преобразует формат в fourcc для SCREEN режима
        """
        format_map = {
            "MP4": cv2.VideoWriter_fourcc(*"mp4v"),
            "AVI": cv2.VideoWriter_fourcc(*"XVID"),
            "MKV": cv2.VideoWriter_fourcc(*"X264"),
            "MOV": cv2.VideoWriter_fourcc(*"mp4v"),
        }
        return format_map.get(video_format, cv2.VideoWriter_fourcc(*"mp4v"))


    def _start_video_recording(self, region: dict):
        """Запуск непрерывной записи видео с учётом качества"""
        
        quality = self._settings.record.common.quality
        fourcc, extension = self._quality_to_format(quality)
        
        video_path = self._session_dir / f"output{extension}"
        
        self._recorder = VideoRecorder(
            output_path=video_path,
            fps=self._settings.record.fps,
            region=region,
            fourcc=fourcc,
        )
        self._record_thread = threading.Thread(target=self._recorder.start, daemon=True)
        self._record_thread.start()

    def _start_screen_capture(self, region: dict):
        """Запуск серийного захвата кадров (сохраняются PNG)"""
        frames_dir = self._session_dir / "frames"
        
        # Качество для screen режима — пока не используется
        # PNG сохраняется без сжатия, качество всегда максимальное
        # TODO: добавить управление качеством (JPEG с разным уровнем сжатия)
        
        self._capturer = FrameCapturer(
            output_dir=frames_dir,
            shots_per_minute=self._settings.screen.capture_per_minute,
            region=region,
        )
        self._record_thread = threading.Thread(target=self._capturer.start, daemon=True)
        self._record_thread.start()

    def stop_recording(self) -> bool:
        """Остановка записи"""
        
        if not self._is_recording:
            return False

        self._stop_event.set()

        if self._recorder:
            self._recorder.stop()
        
        if self._capturer:
            self._capturer.stop()
            # После остановки capturer'а — собираем видео
            self._assemble_video_from_frames()

        if self._record_thread:
            self._record_thread.join()

        self._cleanup_runtime()
        return True

    def _assemble_video_from_frames(self):
        """Собирает видео из кадров после остановки screen capture"""
        if not self._session_dir:
            return
        
        frames_dir = self._session_dir / "frames"
        #output_path = self._session_dir / "output.mp4"

        # Получаем формат из финальных настроек
        video_format = self._settings.finalize.common.video_format
        fourcc = self._format_to_fourcc(video_format)
        
        # Определяем расширение
        extension = f".{video_format.lower()}"
        output_path = self._session_dir / f"output{extension}"
        
        if frames_dir.exists() and any(frames_dir.glob("*.png")):
            # Получаем формат из настроек (по умолчанию MP4)
            #video_format = self._settings.finalize.common.video_format
            # Для первой версии игнорируем формат — всегда MP4
            # TODO: поддержка других форматов в следующей версии
            
            VideoAssembler.assemble(
                frames_dir=frames_dir,
                output_path=output_path,
                fps=self._settings.finalize.screen.playback_fps,
                fourcc=fourcc,
            )

    def get_elapsed_time(self) -> float:
        """Вернуть прошедшее время записи в секундах"""
        if not self._start_time:
            return 0.0
        return time.time() - self._start_time

    def get_frame_count(self) -> int:
        """Количество кадров (для screen режима)"""
        if self._capturer:
            return self._capturer.get_frame_count()
        return 0

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def _validate_region(self, region: dict):
        x, y, w, h = region.get("left"), region.get("top"), region.get("width"), region.get("height")
        if any(v is None for v in (x, y, w, h)) or w <= 0 or h <= 0:
            raise ValueError("Некорректные координаты области")

    def _cleanup_runtime(self):
        self._recorder = None
        self._capturer = None
        self._record_thread = None
        self._timer_thread = None
        self._start_time = None
        self._stop_event.clear()
        self._is_recording = False
        self._session_dir = None
        # session_type не очищаем — он нужен до конца сессии