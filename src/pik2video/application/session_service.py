# src/pik2video/application/session_service.py
from pathlib import Path
from typing import Optional
from src.pik2video.storage.session_storage import SessionStorage

class SessionService:
    """
    Управление сессиями: создание, экспорт, очистка.
    """
    def __init__(self, base_tmp_dir: Path):
        
        self.storage = SessionStorage(base_tmp_dir)

    def create_session(self) -> Path:
        return self.storage.create_session()

    def has_data(self) -> bool:
        return self.storage.has_data()

    def get_total_size(self) -> int:
        return self.storage.get_total_size()

    def get_frame_count(self) -> int:
        """Возвращает количество кадров в сессии"""
        return self.storage.get_frame_count()

    def export_session(self, target_dir: Path, filename: str, extension: str = ".mp4") -> Optional[Path]:
        """
        Экспортирует видео.
        
        Args:
            target_dir: папка для сохранения
            filename: имя файла (без расширения)
        
        Returns:
            Путь к финальному файлу или None
        """
        return self.storage.export_video(target_dir, filename, extension)

    def cleanup(self):
        self.storage.cleanup()
