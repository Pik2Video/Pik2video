# test.py — скрипт для DEV тестирования GUI
import sys

from src.pic2vid.app import Application
from src.pic2vid.application.state_machine import AppState
from src.pic2vid.application.session_types import SessionType

# Словарь для выбора состояния и session_type
# ключ — аргумент командной строки
WINDOWS = {
    "idle": (AppState.IDLE, None),
    "prep_video": (AppState.PREPARING_VIDEO, SessionType.VIDEO),
    "prep_screen": (AppState.PREPARING_SCREEN, SessionType.SCREEN),
    "recording_video": (AppState.RECORDING, SessionType.VIDEO),
    "recording_screen": (AppState.RECORDING, SessionType.SCREEN),
    "review_video": (AppState.REVIEW, SessionType.VIDEO),
    "review_screen": (AppState.REVIEW, SessionType.SCREEN),
}

def main():
    # Получаем аргумент командной строки
    state_arg = sys.argv[1] if len(sys.argv) > 1 else "idle"

    if state_arg not in WINDOWS:
        print(f"[DEV] Неизвестное состояние '{state_arg}'. Доступные:")
        for key in WINDOWS.keys():
            print(" -", key)
        state_arg = "idle"

    # Разбираем AppState и SessionType
    state, session_type = WINDOWS[state_arg]

    print(f"[DEV] Запуск состояния: {state_arg} → {state}, session_type={session_type}")

    # Создаём приложение
    app = Application()

    # Устанавливаем DEV состояние напрямую через контроллер
    # Если state требует session_type (PREPARING, RECORDING, REVIEW) — передаём
    app.controller.set_state_dev(state, session_type=session_type)

    # Запуск Qt главного цикла
    app.run()


if __name__ == "__main__":
    main()