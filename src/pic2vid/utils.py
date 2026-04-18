# src/pic2vid/utils.py
import os
import uuid
import time                                               

def format_size(size_bytes: int) -> str:
    """Форматирует размер в байтах в человекочитаемый вид"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    else:
        return f"{size_bytes / (1024 * 1024):.1f} MB"

def format_timer(seconds):                                # Форматирование секунд в удобный временной формат hh:mm:ss
    seconds = int(seconds)
    hours = seconds // 3600                               # Целочисленное деление на часы
    minutes = (seconds % 3600) // 60                      # Минуты из остатка часов
    secs = seconds % 60                                   # Остаточные секунды
    return f'{hours:02}:{minutes:02}:{secs:02}'           # Форматируем строку с ведущими нулями

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def generate_unique_filename(prefix="capture"):
    unique_id = uuid.uuid4().hex[:8]
    return f"{prefix}_{unique_id}"
