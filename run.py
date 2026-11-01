# run.py
"""
DEV-режим: запуск приложения с автоперезапуском при изменении файлов.

Отслеживает изменения в src/ и перезапускает процесс.
Игнорирует __pycache__, .pyc, логи и временные файлы.
"""

import os
import sys
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# Что отслеживать
WATCH_DIR = Path(__file__).parent / "src"
WATCH_EXTENSIONS = {".py"}

# Что игнорировать
IGNORE_PARTS = {"__pycache__", ".pytest_cache", ".mypy_cache"}


class ReloadHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.is_directory:
            return

        path = Path(event.src_path)

        if path.suffix not in WATCH_EXTENSIONS:
            return

        if any(part in IGNORE_PARTS for part in path.parts):
            return

        print(f"[reload] {path.name} изменён → перезапуск...")
        os.execl(sys.executable, sys.executable, *sys.argv)


def main():
    observer = Observer()
    observer.schedule(ReloadHandler(), path=str(WATCH_DIR), recursive=True)
    observer.start()

    try:
        from src.main import main as app_main
        app_main()
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    main()