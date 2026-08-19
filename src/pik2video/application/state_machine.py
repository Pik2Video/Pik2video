# src/pik2video/application/state_machine.py

from enum import Enum, auto


class AppState(Enum):
    IDLE = auto()
    PREPARING_VIDEO = auto()
    PREPARING_SCREEN = auto()
    WAITING = auto()      # 🆕 отсчёт перед стартом
    RECORDING = auto()
    REVIEW = auto()


class StateMachine:
    """
    Управление состояниями приложения.

    Отвечает только за:
    - хранение текущего состояния
    - проверку допустимых переходов
    """

    def __init__(self):
        
        self._state: AppState = AppState.IDLE

    # ---------------------------------------
    # ================BASIC==================
    # ---------------------------------------

    def get_state(self) -> AppState:
        return self._state

    def _set_state(self, new_state: AppState):
        self._state = new_state

    # ---------------------------------------
    # ==========TRANSITIONS FROM IDLE========
    # ---------------------------------------

    def can_prepare_video(self) -> bool:
        return self._state == AppState.IDLE

    def prepare_video(self) -> bool:
        if not self.can_prepare_video():
            return False
        self._set_state(AppState.PREPARING_VIDEO)
        return True

    def can_prepare_screen(self) -> bool:
        return self._state == AppState.IDLE

    def prepare_screen(self) -> bool:
        if not self.can_prepare_screen():
            return False
        self._set_state(AppState.PREPARING_SCREEN)
        return True

    # ----------------------------------------
    # ========TRANSITIONS TO RECORDING========
    # ----------------------------------------

    def can_start_recording(self, region_defined: bool) -> bool:
        return (
            self._state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)
            and region_defined
        )

    def start_recording(self) -> bool:
        if self._state not in (
            AppState.PREPARING_VIDEO,
            AppState.PREPARING_SCREEN,
        ):
            return False

        self._set_state(AppState.WAITING)
        return True

    def begin_recording(self) -> bool:
        """Переход из WAITING в RECORDING (после задержки)"""
        if self._state != AppState.WAITING:
            return False
        self._set_state(AppState.RECORDING)
        return True

    # ---------------------------------------
    # =============STOP RECORDING============
    # ---------------------------------------

    def can_stop_recording(self) -> bool:
        return self._state in (AppState.RECORDING, AppState.WAITING)

    def stop_recording(self) -> bool:
        if not self.can_stop_recording():
            return False

        self._set_state(AppState.REVIEW)
        return True

    # --------------------------------------
    # ==============FINALIZATION=============
    # ---------------------------------------

    def can_finalize_session(self) -> bool:
        return self._state == AppState.REVIEW

    def finalize_session(self) -> bool:
        if not self.can_finalize_session():
            return False

        self._set_state(AppState.IDLE)
        return True

    def can_discard_session(self) -> bool:
        return self._state == AppState.REVIEW

    def discard_session(self) -> bool:
        if not self.can_discard_session():
            return False

        self._set_state(AppState.IDLE)
        return True

    # -------------------------------------------------
    # CANCEL PREPARING (если пользователь закрыл окно)
    # -------------------------------------------------

    def can_cancel_preparing(self) -> bool:
        return self._state in (
            AppState.PREPARING_VIDEO,
            AppState.PREPARING_SCREEN,
            AppState.WAITING,
        )

    def cancel_preparing(self) -> bool:
        if not self.can_cancel_preparing():
            return False

        self._set_state(AppState.IDLE)
        return True

    # -------------------------------------------------
    # ================ DEV / Testing only =============
    # -------------------------------------------------
    def set_state_dev(self, state: AppState):
        """Установить состояние напрямую (только для разработки)"""
        self._state = state