# managers/session_manager.py
"""
Менеджер управления сессией записи.
Отвечает за создание, хранение, очистку и экспорт временной сессии.
Также хранит runtime-данные: координаты, регион, тип сессии, время старта.
"""

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject

from ..session_service import SessionService
from ..session_types import SessionType

logger = logging.getLogger(__name__)


class SessionManager(QObject):
    """
    Управляет временными данными сессии:
    - создание/очистка папки
    - экспорт видео
    - хранение координат, региона, типа сессии, времени старта
    - доступ к размеру и наличию данных
    """

    def __init__(self, base_tmp_dir: Path):
        super().__init__()
        self._session_service = SessionService(base_tmp_dir)

        # Runtime-данные текущей сессии
        self._session_type: Optional[SessionType] = None
        self.raw_coordinates: Optional[dict] = None
        self.region: Optional[dict] = None
        self._start_time: Optional[float] = None   # время начала записи

    # ---------- Управление сессией ----------

    def create_session(self) -> Path:
        """Создать новую временную сессию."""
        return self._session_service.create_session()

    def cleanup(self):
        """Удалить временные файлы сессии."""
        self._session_service.cleanup()

    def export_session(self, target_dir: Path, filename: str, extension: str) -> Optional[Path]:
        """Экспортировать видео в целевую папку."""
        return self._session_service.export_session(target_dir, filename, extension)

    def has_data(self) -> bool:
        """Есть ли данные в сессии."""
        return self._session_service.has_data()

    def get_total_size(self) -> int:
        """Общий размер данных сессии в байтах."""
        return self._session_service.get_total_size()

    def get_video_path(self):
        """Путь к файлу в текущей сессии."""
        return self._session_service.get_video_path()

    

    # ---------- Runtime-данные ----------

    def set_session_type(self, session_type: SessionType):
        self._session_type = session_type

    def get_session_type(self) -> Optional[SessionType]:
        return self._session_type

    def set_raw_coordinates(self, coords: dict):
        """Сохранить сырые координаты и вычислить регион."""
        x1 = coords["x1"]
        y1 = coords["y1"]
        x2 = coords["x2"]
        y2 = coords["y2"]
        if x2 <= x1 or y2 <= y1:
            raise ValueError("Некорректные координаты области")
        self.raw_coordinates = coords
        self.region = {
            "left": x1,
            "top": y1,
            "width": x2 - x1,
            "height": y2 - y1
        }

    def get_region(self) -> Optional[dict]:
        return self.region

    def set_start_time(self, start_time: float):
        self._start_time = start_time

    def get_start_time(self) -> Optional[float]:
        return self._start_time

    def clear_runtime(self):
        """Сбросить все runtime-данные."""
        self._session_type = None
        self.raw_coordinates = None
        self.region = None
        self._start_time = None
