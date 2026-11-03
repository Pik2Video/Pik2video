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


class _FramesTask(QRunnable):
    """Задача в пуле потоков: сгенерировать N кадров для дорожки таймлайна."""

    def __init__(self, cache: ThumbnailCache, source_path: str,
                 count: int, duration: float, on_done):
        super().__init__()
        self._cache = cache
        self._source_path = source_path
        self._count = count
        self._duration = duration
        self._on_done = on_done
        self.setAutoDelete(True)

    def run(self):
        try:
            if not self._cache.has_frames(self._source_path, self._count):
                self._cache.generate_frames(
                    self._source_path, self._count, self._duration
                )
        except Exception as e:
            logger.warning(f"Ошибка фоновой генерации кадров {self._source_path}: {e}")
        finally:
            self._on_done(self._source_path, self._count)


class ThumbnailLoader(QObject):
    """Пул задач генерации миниатюр + сигнал готовности."""

    thumbnail_ready = Signal(str)               # путь исходного файла
    frames_ready = Signal(str, int)             # путь файла, число кадров

    def __init__(self, cache: ThumbnailCache, parent=None):
        super().__init__(parent)
        self._cache = cache
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(MAX_PARALLEL)
        self._in_progress: set = set()          # пути, для которых задача уже стоит
        self._frames_in_progress: set = set()   # (путь, count) кадров в очереди

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

    def get_cached_frames(self, source_path: str, count: int):
        """Загрузить готовые кадры из кэша. Только из UI-потока.
        Возвращает пустой список, если кадров ещё нет.
        """
        return self._cache.get_frame_pixmaps(source_path, count)

    def request_frames(self, source_path: str, count: int, duration: float):
        """Поставить задачу на генерацию кадров. Если кэш есть — сигнал сразу."""
        if not source_path or count <= 0 or duration <= 0:
            return

        key = (source_path, count)
        if self._cache.has_frames(source_path, count):
            self.frames_ready.emit(source_path, count)
            return

        if key in self._frames_in_progress:
            return

        self._frames_in_progress.add(key)
        logger.debug(f"Задача генерации кадров: {source_path} ({count} шт.)")
        task = _FramesTask(
            self._cache, source_path, count, duration, self._on_frames_done
        )
        self._pool.start(task)

    def cancel_all(self):
        """Прервать все ожидающие задачи (вызывается при закрытии)."""
        self._pool.clear()
        self._pool.waitForDone(1000)
        self._in_progress.clear()
        self._frames_in_progress.clear()

    # ── Внутреннее ──

    def _on_task_done(self, source_path: str):
        """Срабатывает из фонового потока — только эмитим сигнал."""
        self._in_progress.discard(source_path)
        self.thumbnail_ready.emit(source_path)

    def _on_frames_done(self, source_path: str, count: int):
        self._frames_in_progress.discard((source_path, count))
        self.frames_ready.emit(source_path, count)