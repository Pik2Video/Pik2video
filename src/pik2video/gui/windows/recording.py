# src/pik2video/gui/windows/recording.py
"""
Окно записи — контейнер для сессий CaptureSession.

Отвечает только за:
- показ сессии записи (video / screen)
- обработку закрытия окна
- уведомление о состоянии редактора

Не знает:
- про IDLE-экран (удалён)
- про настройки приложения
- про финализацию (окна после Стоп)
"""

import logging

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QMainWindow, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QEvent

from ..common.utils import keep_window_inside_screen, bottom_right_position
from ..common.dialogs import confirm
from ..common.close_policy import (
    CloseAction,
    CloseContext,
    ClosePolicy,
    CloseRule,
    evaluate_close,
)

logger = logging.getLogger(__name__)


class RecordingWindow(QMainWindow):
    """Окно с активной сессией записи."""

    window_state_changed = Signal(Qt.WindowStates, Qt.WindowStates)

    def __init__(self, controller):
        super().__init__()

        self.controller = controller
        #self.translator = controller.get_translator()
        self._editor_visible = False

        # ── Базовые флаги окна ──
        self.setWindowFlag(Qt.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.setAttribute(Qt.WA_QuitOnClose, True)
        self.setFixedSize(430, 80)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #282828;
            }
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 5px;
                color: #e6e6e6;
                padding: 0px 0px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QPushButton:disabled {
                color: rgba(255, 255, 255, 80);
                background-color: #2a2a2a;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)

        self.root_layout = QVBoxLayout(central)
        self.root_layout.setContentsMargins(1, 1, 1, 1)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.addWidget(self.container)

        self.current_session = None
        self._positioned = False

    # ── Служебные ──

    def showEvent(self, event):
        """При первом показе — расположить в правом нижнем углу."""
        super().showEvent(event)
        if not self._positioned:
            self._position_window()
            self._positioned = True

    def _position_window(self):
        """Позиционировать окно в правом нижнем углу экрана."""
        screen = self.screen().availableGeometry()
        pos = bottom_right_position(self, screen, margin=117)
        self.move(pos)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            self.window_state_changed.emit(event.oldState(), self.windowState())
        super().changeEvent(event)

    def set_screen(self, widget: QWidget):
        """Удалить старый экран, поставить новый."""
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self.container_layout.addWidget(widget)
        keep_window_inside_screen(self, margin=20)

    def set_editor_visible(self, visible: bool):
        """Уведомление: редактор открыт / скрыт."""
        self._editor_visible = visible

    # ── Показ сессий ──

    def show_video_session(self, controller):
        """Показать видео-сессию записи."""
        from src.pik2video.gui.capture.sessions import VideoCaptureSession

        session = VideoCaptureSession(controller)
        session.back_requested.connect(controller.cancel_session)
        self.current_session = session

        session.start_requested.connect(controller.start_recording)
        session.stop_requested.connect(controller.stop_recording)
        session.cancel_requested.connect(controller.cancel_session)

        session.time_update_requested.connect(controller.update_time)
        session.ram_update_requested.connect(controller.update_ram)
        session.shots_update_requested.connect(controller.update_shots)

        controller.time_updated.connect(session.set_time)
        controller.ram_updated.connect(session.set_ram)
        controller.shots_updated.connect(session.set_shots)

        self.set_screen(session)
        self.setFixedSize(430, 80)

    def show_screen_session(self, controller):
        """Показать screen-сессию записи."""
        from src.pik2video.gui.capture.sessions import ScreenCaptureSession

        session = ScreenCaptureSession(controller)
        session.back_requested.connect(controller.cancel_session)
        self.current_session = session

        session.start_requested.connect(controller.start_recording)
        session.stop_requested.connect(controller.stop_recording)
        session.cancel_requested.connect(controller.cancel_session)

        session.time_update_requested.connect(controller.update_time)
        session.ram_update_requested.connect(controller.update_ram)
        session.shots_update_requested.connect(controller.update_shots)

        controller.time_updated.connect(session.set_time)
        controller.ram_updated.connect(session.set_ram)
        controller.shots_updated.connect(session.set_shots)

        self.set_screen(session)
        self.setFixedSize(430, 80)
        keep_window_inside_screen(self)

    # ── Закрытие ──

    def _pick_policy(self) -> ClosePolicy:
        """Выбрать политику закрытия по текущему состоянию."""
        from src.pik2video.application.state_machine import AppState

        state = self.controller.state_manager.get_state()

        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN, AppState.WAITING):
            return ClosePolicy.CANCEL_PREPARING
        if state == AppState.RECORDING:
            return ClosePolicy.CONFIRM_IF_RECORDING
        if self.controller.has_active_session_data():
            return ClosePolicy.CONFIRM_IF_DATA
        if self._editor_visible:
            return ClosePolicy.HIDE_IF_EDITOR_OPEN
        return ClosePolicy.ALLOW

    def _make_context(self) -> CloseContext:
        """Собрать факты о состоянии для close_policy."""
        return CloseContext(
            is_recording=self.controller.is_recording(),
            is_preparing=self.controller.is_preparing(),
            has_data=self.controller.has_active_session_data(),
            editor_visible=self._editor_visible,
        )

    def _ask(self, rule: CloseRule) -> bool:
        """Мост между политикой и QMessageBox."""
        translator = self.controller.get_translator()
        return confirm(
            self,
            rule.text,
            title=rule.title,
            translator=translator,
            yes_label=rule.yes_label,
            no_label=rule.no_label,
        )

    def closeEvent(self, event):
        """Обработка закрытия окна через close_policy."""
        logger.debug("RecordingWindow: closeEvent")

        policy = self._pick_policy()
        ctx = self._make_context()
        action = evaluate_close(policy, ctx, ask=self._ask)

        logger.debug(f"close_policy: policy={policy.name}, action={action.name}")

        if action == CloseAction.CLOSE:
            event.accept()

        elif action == CloseAction.HIDE:
            logger.debug("Скрываем окно, приложение продолжает работу")
            self.hide()
            event.ignore()

        elif action == CloseAction.STOP_RECORDING:
            logger.debug("Останавливаем запись → редактор откроется автоматически")
            self.controller.stop_recording()
            event.ignore()

        elif action == CloseAction.DISCARD_AND_CLOSE:
            logger.debug("Удаляем данные сессии и закрываемся")
            self.controller.discard_session()
            event.accept()

        elif action == CloseAction.CANCEL_PREPARING_AND_CLOSE:
            logger.debug("Отменяем подготовку и закрываемся")
            self.controller.cancel_session()
            event.accept()

        else:  # CANCEL
            event.ignore()