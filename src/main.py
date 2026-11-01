# src/main.py
import sys

from src.pik2video.app import Application
from src.pik2video.infrastructure.logging import setup_logging


def main():
    # DEBUG включается флагом --debug
    debug_mode = "--debug" in sys.argv

    # Инициализируем логирование ДО всего остального
    setup_logging(debug_mode=debug_mode, log_to_file=True)
    
    app = Application()      # ─── Создаём QApplication ───
    app.run()                # ───   Запуск цикла Qt    ───


if __name__ == "__main__":
    main()
