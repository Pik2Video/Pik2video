# src/pik2video/gui/editor/thumbnail_loader.py
"""
Асинхронный загрузчик миниатюр.

Отвечает за:
- приём запросов «дай миниатюру для файла X»
- генерацию миниатюры в фоновом потоке (через ThumbnailCache)
- сигнал «готово для X» в UI-поток, когда миниатюра лежит в кэше

Важно: QPixmap в фоне не создаётся. Фоновый поток только генерирует PNG
на диске. UI-поток сам читает PNG, когда придёт сигнал thumbnail_ready.

Не знает:
- про виджеты
- про список файлов
- про состояние редактора
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from src.pik2video.storage.thumbnail_cache import ThumbnailCache

logger = logging.getLogger(__name__)

MAX_PARALLEL = 2                    # не больше двух ffmpeg одновременно


class _ThumbnailTask(QRunnable):
    """Задача в пуле потоков: сгенерировать миниатюру для одного файла."""

    def __init__(self, cache: ThumbnailCache, source_path: str, on_done):
        super().__init__()
        self._cache = cache
        self._source_path = source_path
        self._on_done = on_done                      # callback в UI-поток (эмитит сигнал)
        self.setAutoDelete(True)

    def run(self):
        """Выполняется в фоновом потоке. QPixmap не трогаем."""
        try:
            if not self._cache.has_cached(self._source_path):
                self._cache.generate_file(self._source_path)     # ffmpeg → PNG на диск
        except Exception as e:
            logger.warning(f"Ошибка фоновой генерации {self._source_path}: {e}")
        finally:
            self._on_done(self._source_path)                     # сообщаем UI: «готово»


class ThumbnailLoader(QObject):
    """Пул задач генерации миниатюр + сигнал готовности."""

    thumbnail_ready = Signal(str)               # путь исходного файла

    def __init__(self, cache: ThumbnailCache, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(MAX_PARALLEL)
        self._in_progress: set = set()          # пути, для которых задача уже стоит

    def get_cached_pixmap(self, source_path: str):
        """Загрузить готовую миниатюру из кэша. Только из UI-потока."""
        return self._cache.get_cached_pixmap(source_path)

    def request(self, source_path: str):
        """Поставить задачу. Если кэш есть — сигнал вылетит немедленно."""
        if not source_path:
            return

        if self._cache.has_cached(source_path):
            self.thumbnail_ready.emit(source_path)              # мгновенно
            return

        if source_path in self._in_progress:
            return                                              # уже стоит в очереди

        self._in_progress.add(source_path)
        logger.debug(f"Задача генерации миниатюры: {source_path}")
        task = _ThumbnailTask(self._cache, source_path, self._on_task_done)
        self._pool.start(task)

    def cancel_all(self):
        """Прервать все ожидающие задачи (вызывается при закрытии)."""
        self._pool.clear()                                      # снять из очереди то, что ещё не запустилось
        self._pool.waitForDone(1000)                            # дождаться активных (максимум секунда)
        self._in_progress.clear()

    # ── Внутреннее ──

    def _on_task_done(self, source_path: str):
        """Срабатывает из фонового потока — только эмитим сигнал."""
        self._in_progress.discard(source_path)
        self.thumbnail_ready.emit(source_path)