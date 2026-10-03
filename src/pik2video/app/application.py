# src/pik2video/app/application.py
"""
Главный класс приложения.

Отвечает только за:
- создание QApplication
- создание AppController и RecordingWindow
- создание менеджеров (BlinkManager, WindowManager, StateCoordinator)
- создание и показ EditorWindow
- связывание сигналов между ними
- запуск главного цикла Qt
"""

import logging

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import QApplication

from src.pik2video.application.controller import AppController

# импортируем управление подсказками
from src.pik2video.gui.common.tooltip import is_tooltips_enabled, set_tooltips_enabled
from src.pik2video.gui.windows.ffmpeg_missing import FFmpegMissingDialog
from src.pik2video.gui.windows.recording import RecordingWindow

from .blink_manager import BlinkManager
from .state_coordinator import StateCoordinator
from .window_manager import WindowManager

logger = logging.getLogger(__name__)

class _TooltipEventFilter(QObject):
    """Фильтр, отключающий стандартные Qt-подсказки, когда они выключены в настройках."""

    def eventFilter(self, obj, event):
        if event.type() == QEvent.ToolTip and not is_tooltips_enabled():
            return True  # отменяем показ подсказки
        return super().eventFilter(obj, event)


class Application:
    def __init__(self):
        # ── Qt ──
        self.qt_app = QApplication.instance() or QApplication([])

        # 🆕 Включаем постоянные tooltip'ы
        # QApplication.setAttribute(Qt.ApplicationAttribute.AA_AlwaysShowToolTips, True)

        # ── Контроллер ──
        self.controller = AppController()

        # применяем сохранённую настройку подсказок
        set_tooltips_enabled(self.controller.get_show_tooltips())

        # ставим фильтр на QApplication — перехватываем стандартные Qt-подсказки
        self._tooltip_filter = _TooltipEventFilter()
        self.qt_app.installEventFilter(self._tooltip_filter)

        self.main_window = RecordingWindow(self.controller)

        # ── Менеджеры ──
        self.blink_manager = BlinkManager()
        self.window_manager = WindowManager(
            qt_app=self.qt_app,
            main_window=self.main_window,
            controller=self.controller,
        )
        self.state_coordinator = StateCoordinator(
            controller=self.controller,
            main_window=self.main_window,
            window_manager=self.window_manager,
            blink_manager=self.blink_manager,
        )

        # ── Связывание сигналов ──
        self.controller.state_changed.connect(self.state_coordinator.on_state_changed)
        self.controller.ffmpeg_required.connect(self._on_ffmpeg_missing)

        self.main_window.window_state_changed.connect(
            self.state_coordinator.on_main_window_state_changed
        )

        self.controller.open_editor_requested.connect(self._open_editor_with_file)
        self._editor_window = None
        self._editor_hidden_for_record = False
        self.controller.state_changed.connect(self._on_state_changed_editor_visibility)

        # ── Always on top at startup ──
        if self.controller.get_always_on_top():
            self.main_window.setWindowFlags(
                self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
            )

        # При запуске сразу открываем редактор (IDLE остаётся скрытым)
        self._open_editor()

    # ---------------- FFmpeg ----------------

    def _on_ffmpeg_missing(self):
        logger.error("FFmpeg не найден → показываем диалог")
        dialog = FFmpegMissingDialog(self.main_window, controller=self.controller)
        dialog.exec()

    # ---------------- Editor ----------------

    def _open_editor(self):
        from src.pik2video.gui.editor.window import EditorWindow

        if self._editor_window is None:
            self._editor_window = EditorWindow(controller=self.controller)
            self._editor_window.record_video_requested.connect(self._on_start_video)
            self._editor_window.record_screen_requested.connect(self._on_start_screen)
            self._editor_window.record_audio_requested.connect(self._on_start_audio)
            self._editor_window.closed.connect(self._on_editor_closed)

        self.main_window.set_editor_visible(True)
        self.main_window.hide()
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    def _on_start_video(self):
        """Кнопка «запись видео» в редакторе → показать IDLE + начать подготовку."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.controller.prepare_video()

    def _on_start_screen(self):
        """Кнопка «скрин запись» в редакторе → показать IDLE + начать подготовку."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.controller.prepare_screen()

    def _on_start_audio(self):
        """Кнопка «запись звука» — пока заглушка."""
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self._editor_window,
            "Запись звука",
            "Функция появится в следующих версиях."
        )

    def _on_state_changed_editor_visibility(self, state):
        """Скрыть/показать редактор в зависимости от состояния."""
        from src.pik2video.application.state_machine import AppState

        # Скрытие — только при реальном переходе в PREPARING
        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
            if not self.controller.get_auto_hide_editor():
                return
            if self._editor_window is None or not self._editor_window.isVisible():
                return
            self._editor_window.hide()
            self._editor_hidden_for_record = True
            logger.info("Редактор скрыт для записи")
            return

        # Восстановление — при возврате в IDLE
        if state == AppState.IDLE:
            if not self._editor_hidden_for_record:
                return
            self._editor_hidden_for_record = False
            if self._editor_window is not None:
                self._editor_window.show()
                self._editor_window.raise_()
                self._editor_window.activateWindow()
            logger.info("Редактор восстановлен после записи")
            return

    
    def _on_editor_closed(self):
        """Редактор закрыт. Если окно записи не видно — выходим."""
        logger.info("Редактор закрыт")
        self.main_window.set_editor_visible(False)

        # Если окно записи открыто — приложение продолжает работу
        if self.main_window.isVisible():
            logger.debug("Окно записи видно → приложение продолжает работу")
            return

        # Больше видимых окон нет — закрываем приложение
        logger.info("Все окна закрыты — выходим")
        self.qt_app.quit()

    def _open_editor_with_file(self, path: str):
        from src.pik2video.gui.editor.window import EditorWindow

        if self._editor_window is None:
            self._editor_window = EditorWindow(controller=self.controller)
            self._editor_window.record_video_requested.connect(self._on_start_video)
            self._editor_window.record_screen_requested.connect(self._on_start_screen)
            self._editor_window.record_audio_requested.connect(self._on_start_audio)
            self._editor_window.closed.connect(self._on_editor_closed)

        self._editor_window.load_file(path)
        self.main_window.set_editor_visible(True)
        self.main_window.hide()
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()


    # ---------------- Run ----------------

    def run(self):
        self.qt_app.exec()
