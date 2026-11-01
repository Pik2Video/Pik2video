# src/pik2video/infrastructure/logging/logger_setup.py
"""
Настройка логирования приложения.

- Пишет в консоль (если она есть) и в файл.
- В dev-режиме: логи в <проект>/logs/.
- В собранном .app (macOS): логи в ~/Library/Logs/Pik2Video/.
- Файлы ротуются по размеру, старые удаляются.
- Уровни для консоли и файла независимы.
- Имена логгеров сокращаются до 2 последних частей.
"""

import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path


# ─── Константы ───
APP_NAME = "Pik2Video"

LOG_FORMAT = "%(asctime)s.%(msecs)03d | %(levelname)-8s | %(shortname)-30s | %(message)s"
DATE_FORMAT = "%H:%M:%S"

MAX_BYTES = 10 * 1024 * 1024   # 10 МБ на файл
BACKUP_COUNT = 10              # хранить 10 старых файлов

NOISY_LOGGERS = (
    "PySide6",
    "PIL",
    "urllib3",
    "requests",
    "watchdog",
    "objc",
    "pysysaudio",
    "AVFoundation",
    "Quartz",
    "Foundation",
    "CoreFoundation",
)


class ShortNameFormatter(logging.Formatter):
    """Форматтер, который сокращает имя логгера до 2 последних частей."""

    def format(self, record: logging.LogRecord) -> str:
        parts = record.name.split(".")
        if len(parts) > 2:
            record.shortname = ".".join(parts[-2:])
        else:
            record.shortname = record.name
        return super().format(record)


def _get_log_dir() -> Path:
    """Определить папку для логов в зависимости от режима работы."""
    if getattr(sys, "frozen", False):
        # Собранное приложение — пишем в системную папку логов
        if sys.platform == "darwin":
            log_dir = Path.home() / "Library" / "Logs" / APP_NAME
        elif sys.platform == "win32":
            log_dir = Path.home() / "AppData" / "Local" / APP_NAME / "logs"
        else:
            log_dir = Path.home() / ".local" / "state" / APP_NAME / "logs"
    else:
        # Dev-режим — пишем в корень проекта
        project_root = Path(__file__).resolve().parents[4]
        log_dir = project_root / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logging(debug_mode: bool = False, log_to_file: bool = True) -> None:
    """
    Настройка логирования для всего приложения.

    Args:
        debug_mode: если True — уровень DEBUG для консоли и файла.
        log_to_file: если True — писать в файл с ротацией.
    """
    level = logging.DEBUG if debug_mode else logging.INFO

    formatter = ShortNameFormatter(LOG_FORMAT, DATE_FORMAT)
    handlers: list[logging.Handler] = []

    # ─── Консоль ───
    # sys.stdout может быть None в --windowed сборке PyInstaller
    if sys.stdout is not None:
        console = logging.StreamHandler(sys.stdout)
        console.setLevel(level)
        console.setFormatter(formatter)
        handlers.append(console)

    # ─── Файл ───
    log_file = None
    if log_to_file:
        log_dir = _get_log_dir()
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"pik2video_{today}.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)

    # ─── Корневой логгер ───
    # force=True важен при перезапуске (run.py): сбрасывает предыдущую конфигурацию
    logging.basicConfig(level=logging.DEBUG, handlers=handlers, force=True)

    # ─── Тишина для шумных библиотек ───
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # ─── Приветствие ───
    logger = logging.getLogger(f"{APP_NAME}.startup")
    logger.info("=" * 70)
    logger.info("Сессия запущена: %s", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Режим DEBUG: %s", debug_mode)
    if log_file:
        logger.info("Файл логов: %s", log_file)
    logger.info("Python: %s, платформа: %s", sys.version.split()[0], sys.platform)
    logger.info("=" * 70)