# scripts/dev/test_states.py
"""
DEV-инструмент: запуск приложения в конкретном состоянии GUI.

Позволяет быстро проверить, как выглядит интерфейс в разных состояниях,
не проходя весь путь записи целиком.

Команды:
    python scripts/dev/test_states.py idle
    python scripts/dev/test_states.py prep_video
    python scripts/dev/test_states.py prep_screen
    python scripts/dev/test_states.py prep_audio
    python scripts/dev/test_states.py recording_video
    python scripts/dev/test_states.py recording_screen
    python scripts/dev/test_states.py recording_audio
    python scripts/dev/test_states.py review_video
    python scripts/dev/test_states.py review_screen
    python scripts/dev/test_states.py review_audio

Без аргументов запускается состояние idle.

В dev-режиме:
- окна закрываются без диалогов подтверждения;
- при закрытии редактора приложение завершается.
"""

import sys

from src.pik2video.app import Application
from src.pik2video.application.state_machine import AppState
from src.pik2video.application.session_types import SessionType
from src.pik2video.gui.common.close_policy import set_dev_mode


# Словарь доступных состояний.
# ключ — аргумент командной строки
# значение — (AppState, SessionType или None)
WINDOWS = {
    "idle":             (AppState.IDLE,             None),
    "prep_video":       (AppState.PREPARING_VIDEO,  SessionType.VIDEO),
    "prep_screen":      (AppState.PREPARING_SCREEN, SessionType.SCREEN),
    "prep_audio":       (AppState.PREPARING_AUDIO,  SessionType.AUDIO),
    "recording_video":  (AppState.RECORDING,        SessionType.VIDEO),
    "recording_screen": (AppState.RECORDING,        SessionType.SCREEN),
    "recording_audio":  (AppState.RECORDING,        SessionType.AUDIO),
    "review_video":     (AppState.REVIEW,           SessionType.VIDEO),
    "review_screen":    (AppState.REVIEW,           SessionType.SCREEN),
    "review_audio":     (AppState.REVIEW,           SessionType.AUDIO),
}


def _print_available():
    """Показать список доступных состояний."""
    print("[DEV] Доступные состояния:")
    for key in WINDOWS:
        print(" -", key)


def main():
    # Получаем аргумент командной строки
    state_arg = sys.argv[1] if len(sys.argv) > 1 else "idle"

    if state_arg not in WINDOWS:
        print(f"[DEV] Неизвестное состояние '{state_arg}'.")
        _print_available()
        state_arg = "idle"

    state, session_type = WINDOWS[state_arg]

    print(f"[DEV] Запуск состояния: {state_arg} → {state}, session_type={session_type}")

    # DEV-режим: закрытие окон без подтверждений
    set_dev_mode(True)

    # Создаём приложение
    app = Application()

    # Устанавливаем состояние напрямую через контроллер
    app.controller.set_state_dev(state, session_type=session_type)

    # Для не-IDLE состояний показываем окно записи,
    # потому что в обычном флоу его показывает кнопка в редакторе.
    if state_arg != "idle":
        app.main_window.show()
        app.main_window.raise_()

    # В dev-режиме закрытие редактора завершает приложение.
    if app._editor_window is not None:
        app._editor_window.closed.connect(app.qt_app.quit)

    # Запуск Qt главного цикла
    app.run()


if __name__ == "__main__":
    main()