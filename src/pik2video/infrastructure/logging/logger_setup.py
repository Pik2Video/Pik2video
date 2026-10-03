# src/pik2video/infrastructure/logging/logger_setup.py

import logging
import sys
from datetime import datetime
from pathlib import Path


def setup_logging(debug_mode: bool = False, log_to_file: bool = True):
    """
    Настройка логирования для всего приложения.
    
    Аргументы:
        debug_mode: если True, показываем DEBUG сообщения
        log_to_file: если True, сохраняем в файл
    """
    
    level = logging.DEBUG if debug_mode else logging.INFO
    
    # Создаём папку для логов (в корне проекта, не в src)
    if log_to_file:
        # Идём наверх: src/pik2video/infrastructure/logging/ -> корень проекта
        project_root = Path(__file__).resolve().parents[4]  # 4 шага наверх
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)
        
        today = datetime.now().strftime("%Y-%m-%d")
        log_file = log_dir / f"pik2video_{today}.log"
    
    # Формат сообщения
    log_format = '%(asctime)s | %(levelname)-8s | %(name)-35s | %(message)s'
    date_format = '%H:%M:%S'
    
    # Обработчики
    handlers = []
    
    # Вывод в консоль
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format, date_format))
    handlers.append(console_handler)
    
    # Вывод в файл
    if log_to_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(log_format, date_format))
        handlers.append(file_handler)
    
    # Настройка корневого логгера
    logging.basicConfig(
        level=level,
        handlers=handlers
    )
    
    # Тишина для шумных библиотек
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    
    # Приветствие
    logger = logging.getLogger("Pik2Video")
    logger.info("=" * 60)
    logger.info("Логирование настроено")
    logger.info(f"Режим DEBUG: {debug_mode}")
    if log_to_file:
        logger.info(f"Файл логов: {log_file}")
    logger.info("=" * 60)
