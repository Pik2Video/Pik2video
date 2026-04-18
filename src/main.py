# src/main.py
from src.pic2vid.app import Application

def main():
    app = Application()      # ─── Создаём QApplication ───
    app.run()                # ───   Запуск цикла Qt    ───

if __name__ == "__main__":
    main()