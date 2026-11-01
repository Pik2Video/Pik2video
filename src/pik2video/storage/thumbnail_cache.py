# src/pik2video/storage/thumbnail_cache.py
"""
Кэш миниатюр для видеофайлов.

Отвечает за:
- хранение PNG-миниатюр на диске
- генерацию миниатюр через ffmpeg, если их нет в кэше
- инвалидацию кэша при изменении исходного файла

Ключ кэша — sha1 от абсолютного пути и mtime исходного файла.
Если файл заменили — mtime меняется, ключ другой, миниатюра пересоздаётся.

Не знает:
- про виджеты (не трогает QPixmap из фонового потока)
- про состояние редактора
- про список файлов
"""

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)

FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
THUMB_SIZE = 128                  # длинная сторона миниатюры в пикселях
THUMBNAIL_SEEK = 1.0              # секунда, с которой брать кадр
GENERATION_TIMEOUT = 10           # таймаут ffmpeg в секундах

CACHE_SIZE_LIMIT = 50 * 1024 * 1024       # 50 МБ — порог, после которого чистим кэш
CACHE_CLEAN_TARGET = 0.8                   # чистим до 80% от лимита (40 МБ)


class ThumbnailCache:
    """Кэш миниатюр на диске."""

    def __init__(self, cache_dir: Path):
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        logger.debug(f"ThumbnailCache: папка кэша {self._cache_dir}")

    # ── Ключ кэша ──

    def _cache_key(self, source_path: str) -> str:
        """sha1 от пути и mtime — меняется при замене файла."""
        p = Path(source_path)
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0
        raw = f"{p.resolve()}|{mtime}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _cache_path(self, source_path: str) -> Path:
        """Путь к PNG-файлу в кэше."""
        return self._cache_dir / f"{self._cache_key(source_path)}.png"

    # ── Публичный API ──

    def has_cached(self, source_path: str) -> bool:
        """Есть ли готовая миниатюра в кэше."""
        return self._cache_path(source_path).exists()

    def get_cached_pixmap(self, source_path: str) -> Optional[QPixmap]:
        """Загрузить готовую миниатюру из кэша. Только из UI-потока."""
        cache_file = self._cache_path(source_path)
        if not cache_file.exists():
            return None

        pixmap = QPixmap(str(cache_file))
        if pixmap.isNull():
            logger.warning(f"Повреждённый кэш, удаляю: {cache_file}")
            try:
                cache_file.unlink()
            except OSError:
                pass
            return None

        return pixmap

    def _enforce_size_limit(self):
        """Если папка кэша больше лимита — удалить самые старые PNG до 80% лимита."""
        try:
            files = list(self._cache_dir.glob("*.png"))
            total_size = sum(f.stat().st_size for f in files)
            if total_size <= CACHE_SIZE_LIMIT:
                return

            target = int(CACHE_SIZE_LIMIT * CACHE_CLEAN_TARGET)
            logger.info(
                f"Кэш миниатюр {total_size // (1024 * 1024)} МБ — превышает лимит, чистим до {target // (1024 * 1024)} МБ"
            )

            files.sort(key=lambda f: f.stat().st_mtime)            # сначала самые старые
            deleted = 0
            for f in files:
                if total_size <= target:
                    break
                try:
                    size = f.stat().st_size
                    f.unlink()
                    total_size -= size
                    deleted += 1
                except OSError as e:
                    logger.warning(f"Не удалось удалить {f.name}: {e}")

            logger.info(f"Удалено старых миниатюр: {deleted}")
        except Exception as e:
            logger.warning(f"Ошибка очистки кэша: {e}")

    def generate_file(self, source_path: str) -> bool:
        """
        Запустить ffmpeg и сохранить PNG в кэш.
        Возвращает True, если файл создан успешно.
        Вызывается из фонового потока — QPixmap не трогаем.
        """
        source = Path(source_path)
        if not source.exists():
            logger.warning(f"Исходный файл не найден: {source_path}")
            return False

        self._enforce_size_limit()                                 # проверить лимит и подчистить старые

        cache_file = self._cache_path(source_path)
        if cache_file.exists():
            return True                                   # кто-то уже сгенерировал

        try:
            result = subprocess.run(
                [
                    FFMPEG_BIN,
                    "-loglevel", "quiet",
                    "-ss", str(THUMBNAIL_SEEK),
                    "-i", source_path,
                    "-vframes", "1",
                    "-vf", f"scale={THUMB_SIZE}:{THUMB_SIZE}:force_original_aspect_ratio=decrease",
                    "-y",
                    str(cache_file),
                ],
                capture_output=True,
                check=False,
                timeout=GENERATION_TIMEOUT,
            )

            if result.returncode != 0 or not cache_file.exists():
                logger.warning(
                    f"ffmpeg не смог создать миниатюру для {source_path}: "
                    f"код {result.returncode}"
                )
                return False

            logger.debug(f"Миниатюра создана: {cache_file.name}")
            return True

        except subprocess.TimeoutExpired:
            logger.warning(f"Таймаут генерации миниатюры: {source_path}")
            try:
                cache_file.unlink(missing_ok=True)
            except OSError:
                pass
            return False
        except Exception as e:
            logger.warning(f"Ошибка генерации миниатюры для {source_path}: {e}")
            return False

    def clear(self):
        """Удалить все миниатюры из кэша."""
        try:
            count = 0
            for png in self._cache_dir.glob("*.png"):
                png.unlink(missing_ok=True)
                count += 1
            logger.info(f"Кэш миниатюр очищен: {count} файлов")
        except Exception as e:
            logger.warning(f"Ошибка очистки кэша миниатюр: {e}")