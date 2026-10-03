# src/pik2video/storage/session_storage.py

import logging
import shutil
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class SessionStorage:
    """
    Хранилище текущей сессии записи.

    Отвечает ТОЛЬКО за:
    - создание и удаление временного каталога
    - работу с файлами текущей записи
    - подсчёт объёма данных
    - экспорт результата

    НЕ знает:
    - про GUI
    - про состояние приложения
    - про кнопки и сценарии
    """

    def __init__(self, base_tmp_dir: Path):
        self.base_tmp_dir = base_tmp_dir
        self.session_dir: Optional[Path] = None

    # ========== ЖИЗНЕННЫЙ ЦИКЛ СЕССИИ ==========

    def create_session(self) -> Path:
        """Создаёт новый каталог сессии"""
        self.base_tmp_dir.mkdir(parents=True, exist_ok=True)

        session_name = time.strftime("session_%Y%m%d_%H%M%S")
        self.session_dir = self.base_tmp_dir / session_name
        self.session_dir.mkdir()

        return self.session_dir

    def has_active_session(self) -> bool:
        """Есть ли активная сессия"""
        return self.session_dir is not None and self.session_dir.exists()

    # =========== СОСТОЯНИЕ ДАННЫХ ==============

    def has_data(self) -> bool:
        """
        Проверяет, есть ли в сессии какие-либо данные.
        (видео или скриншоты)
        """
        if not self.has_active_session():
            return False

        for item in self.session_dir.iterdir():
            if item.is_file() and item.stat().st_size > 0:
                return True

        return False

    def get_total_size(self) -> int:
        """Возвращает общий размер данных сессии в байтах"""
        if not self.has_active_session():
            return 0

        total = 0
        for item in self.session_dir.rglob("*"):
            if item.is_file():
                total += item.stat().st_size

        return total

    # ============ ДОСТУП К ФАЙЛАМ ==============

    def get_video_path(self) -> Optional[Path]:
        """
        Возвращает путь к видеофайлу в сессии.
        Ищет raw_output.mp4 (новый формат) и output.mp4 (старый).
        """
        if not self.has_active_session():
            return None

        # Ищем любой видеофайл в папке сессии
        video_extensions = ['.mp4', '.mkv', '.avi', '.mov', '.gif']
        
        for item in self.session_dir.iterdir():
            if item.is_file() and item.suffix in video_extensions:
                if item.stat().st_size > 0:  # файл не пустой
                    logger.debug(f"Найден видеофайл: {item}")
                    return item
        
        logger.warning(f"Видеофайл не найден в {self.session_dir}")
        return None

    def get_frame_count(self) -> int:
        """Возвращает количество захваченных кадров (для screen режима)"""
        if not self.has_active_session():
            return 0
        
        frames_dir = self.session_dir / "frames"
        if frames_dir.exists():
            return len(list(frames_dir.glob("frame_*.png")))
        
        # Для видео режима — проверяем наличие output.mp4
        video_path = self.session_dir / "output.mp4"
        if video_path.exists():
            return 1  # видео считается одним "кадром" для статистики
        
        return 0

    # ============ ЭКСПОРТ И ОЧИСТКА ============

    def export_video(self, target_dir: Path, filename: str, extension: str = ".mp4") -> Optional[Path]:
        """
        Экспортирует видео в указанную директорию с заданным именем.
        
        Args:
            target_dir: папка для сохранения
            filename: имя файла (без расширения)
            extension: расширение файла (например .mp4, .avi, .mov)
        
        Returns:
            Путь к финальному файлу или None
        """
        video_path = self.get_video_path()
        if not video_path:
            return None

        target_dir.mkdir(parents=True, exist_ok=True)

        # Пока всегда MP4
        final_name = f"{filename}{extension}"
        final_path = target_dir / final_name

        # Если файл с таким именем уже существует, добавляем суффикс
        counter = 1
        while final_path.exists():
            final_name = f"{filename}_{counter}{extension}"
            final_path = target_dir / final_name
            counter += 1

        video_path.replace(final_path)
        return final_path

    def cleanup(self):
        """Полностью удаляет текущую сессию и все её содержимое"""
        if not self.has_active_session():
            return

        try:
            # Удаляем всю папку рекурсивно (включая все подпапки и файлы)
            shutil.rmtree(self.session_dir)
            logger.debug(f"Удалена папка: {self.session_dir}")
        except Exception as e:
            logger.error(f"Ошибка при удалении {self.session_dir}: {e}")
        
        self.session_dir = None
