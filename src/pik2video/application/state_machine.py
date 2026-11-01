# src/pik2video/application/state_machine.py

from enum import Enum, auto

from PySide6.QtCore import QObject, Signal


class AppState(Enum):
    IDLE = auto()
    PREPARING_VIDEO = auto()
    PREPARING_SCREEN = auto()
    PREPARING_AUDIO = auto()    # подготовка к записи только звука
    COUNTDOWN = auto()
    RECORDING = auto()
    REVIEW = auto()


class StateMachine(QObject):
    state_changed = Signal(AppState)

    """
    Управление состояниями приложения.

    Отвечает только за:
    - хранение текущего состояния
    - проверку допустимых переходов
    """

    def __init__(self):
        super().__init__()
        self._state: AppState = AppState.IDLE

    # ---------------------------------------
    # ================BASIC==================
    # ---------------------------------------

    def get_state(self) -> AppState:
        return self._state

    def _set_state(self, new_state: AppState):
        self._state = new_state
        self.state_changed.emit(new_state)

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

    def can_prepare_audio(self) -> bool:
        return self._state == AppState.IDLE              # переход в аудио возможен только из IDLE

    def prepare_audio(self) -> bool:
        if not self.can_prepare_audio():
            return False
        self._set_state(AppState.PREPARING_AUDIO)        # переводим в состояние подготовки аудио
        return True

    # ----------------------------------------
    # ========TRANSITIONS TO RECORDING========
    # ----------------------------------------

    def can_start_recording(self, region_defined: bool) -> bool:
        if self._state == AppState.PREPARING_AUDIO:
            return True                                 # для аудио регион не требуется
        return (
            self._state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)
            and region_defined
        )

    def start_recording(self) -> bool:
        if self._state not in (
            AppState.PREPARING_VIDEO,
            AppState.PREPARING_SCREEN,
            AppState.PREPARING_AUDIO,          # старт записи возможен и из аудио-подготовки
        ):
            return False

        self._set_state(AppState.COUNTDOWN)
        return True

    def begin_recording(self) -> bool:
        """Переход из COUNTDOWN в RECORDING (после задержки)"""
        if self._state != AppState.COUNTDOWN:
            return False
        self._set_state(AppState.RECORDING)
        return True

    # ---------------------------------------
    # =============STOP RECORDING============
    # ---------------------------------------

    def can_stop_recording(self) -> bool:
        return self._state in (AppState.RECORDING, AppState.COUNTDOWN)

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
            AppState.PREPARING_AUDIO,      # отмена возможна и из аудио-подготовки
            AppState.COUNTDOWN,
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
        self.state_changed.emit(state)