# managers/state_manager.py
"""
Менеджер управления состояниями приложения.
Инкапсулирует StateMachine и предоставляет методы для переходов.
"""

import logging
from PySide6.QtCore import QObject, Signal

from ..state_machine import StateMachine, AppState

logger = logging.getLogger(__name__)


class StateManager(QObject):
    """
    Управляет состоянием приложения.
    Все переходы состояний проходят через этот класс.
    Сигнал state_changed пробрасывается наружу.
    """

    state_changed = Signal(AppState)

    def __init__(self):
        super().__init__()
        self._state_machine = StateMachine()
        self._state_machine.state_changed.connect(self._on_state_changed)

    def _on_state_changed(self, state: AppState):
        """Проброс сигнала от машины состояний."""
        logger.debug(f"StateManager: состояние изменено на {state}")
        self.state_changed.emit(state)

    # ---------- Переходы ----------

    def prepare_video(self) -> bool:
        """Переход в PREPARING_VIDEO."""
        return self._state_machine.prepare_video()

    def prepare_screen(self) -> bool:
        """Переход в PREPARING_SCREEN."""
        return self._state_machine.prepare_screen()

    def start_recording(self) -> bool:
        """Переход в WAITING (перед записью)."""
        return self._state_machine.start_recording()

    def begin_recording(self) -> bool:
        """Переход из WAITING в RECORDING (фактическое начало)."""
        return self._state_machine.begin_recording()

    def stop_recording(self) -> bool:
        """Переход в REVIEW."""
        return self._state_machine.stop_recording()

    def cancel_preparing(self) -> bool:
        """Отмена подготовки (возврат в IDLE)."""
        return self._state_machine.cancel_preparing()

    def finalize_session(self) -> bool:
        """Переход в IDLE после сохранения."""
        return self._state_machine.finalize_session()

    def discard_session(self) -> bool:
        """Переход в IDLE после удаления сессии."""
        return self._state_machine.discard_session()

    # ---------- Проверки состояния ----------

    def get_state(self) -> AppState:
        return self._state_machine.get_state()

    def can_start_recording(self, region_defined: bool) -> bool:
        return self._state_machine.can_start_recording(region_defined)

    def can_stop_recording(self) -> bool:
        return self._state_machine.can_stop_recording()

    def can_finalize_session(self) -> bool:
        return self._state_machine.can_finalize_session()

    def can_discard_session(self) -> bool:
        return self._state_machine.can_discard_session()

    def is_recording(self) -> bool:
        state = self.get_state()
        return state in (AppState.WAITING, AppState.RECORDING)

    def is_preparing(self) -> bool:
        state = self.get_state()
        return state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)

    def is_review(self) -> bool:
        return self.get_state() == AppState.REVIEW

    # ---------- DEV метод ----------
    def set_state_dev(self, state: AppState):
        """Только для тестов."""
        self._state_machine.set_state_dev(state)