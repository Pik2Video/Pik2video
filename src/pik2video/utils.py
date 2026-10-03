# src/pik2video/utils.py

"""
Общие утилиты приложения, не зависящие от конкретных модулей.
Используются в: controller.py, gui/sessions.py и др.
"""


def format_size(size_bytes: int) -> str:
    """Преобразует размер из байтов в читабельный вид."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    
    size_kb = size_bytes / 1024
    if size_kb < 1024:
        return f"{size_kb:.1f} KB"
    
    size_mb = size_kb / 1024
    if size_mb < 1024:
        return f"{size_mb:.2f} MB"
    
    size_gb = size_mb / 1024
    return f"{size_gb:.2f} GB"


def format_time(seconds: float, prefix: str = "TIME:") -> str:
    """Преобразует секунды в формат ЧЧ:ММ:СС с префиксом."""
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    return f"{prefix} {hours:02}:{minutes:02}:{secs:02}"
