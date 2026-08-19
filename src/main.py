# src/main.py
from src.pik2video.app import Application

def main():
    app = Application()      # ─── Создаём QApplication ───
    app.run()                # ───   Запуск цикла Qt    ───


if __name__ == "__main__":
    main()