# managers/ffmpeg_manager.py
import logging

from PySide6.QtCore import QObject, Signal

from src.pik2video.infrastructure.ffmpeg.ffmpeg_service import FFmpegService

logger = logging.getLogger(__name__)

class FFmpegManager(QObject):
    """
    Менеджер для работы с FFmpeg.
    Отвечает за:
    - проверку наличия FFmpeg в системе
    - кэширование результата проверки
    - генерацию сигнала при отсутствии FFmpeg
    """
    ffmpeg_required = Signal()  # сигнал, который будет передан в контроллер

    def __init__(self):
        super().__init__()
        self.ffmpeg = FFmpegService()
        self._ffmpeg_missing = False
        self._check_on_init()

    def _check_on_init(self):
        """Проверяет FFmpeg при создании и сохраняет результат"""
        self._ffmpeg_missing = not self.ffmpeg.is_installed()
        if self._ffmpeg_missing:
            logger.error("FFmpeg не найден при старте")
        else:
            logger.info("FFmpeg найден при старте")

    def ensure_ffmpeg(self) -> bool:
        """
        Проверяет наличие FFmpeg.
        Если отсутствует, эмитит сигнал и возвращает False.
        """
        if self._ffmpeg_missing:
            logger.error("FFmpeg НЕ найден")
            self.ffmpeg_required.emit()
            return False
        logger.info("FFmpeg найден")
        return True

    def is_ffmpeg_installed(self) -> bool:
        """Возвращает кэшированный результат проверки"""
        return not self._ffmpeg_missing
