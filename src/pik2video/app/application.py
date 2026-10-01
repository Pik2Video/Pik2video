# src/pik2video/app/application.py
"""
Главный класс приложения.

Отвечает только за:
- создание QApplication
- создание AppController и MainWindow
- создание менеджеров (BlinkManager, WindowManager, StateCoordinator)
- связывание сигналов между ними
- запуск главного цикла Qt
"""

import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QObject, QEvent

from src.pik2video.application.controller import AppController
from src.pik2video.gui.windows.main import MainWindow
from src.pik2video.gui.windows.ffmpeg_missing import FFmpegMissingDialog
from src.pik2video.gui.common.utils import bottom_right_position

# импортируем управление подсказками
from src.pik2video.gui.common.tooltip import set_tooltips_enabled, is_tooltips_enabled


from .blink_manager import BlinkManager
from .window_manager import WindowManager
from .state_coordinator import StateCoordinator

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


        # ── Главное окно ──
        self.main_window = MainWindow(self.controller)

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

        self.main_window.start_video_requested.connect(self.controller.prepare_video)
        self.main_window.start_screen_requested.connect(self.controller.prepare_screen)
        self.main_window.settings_requested.connect(self.window_manager.open_app_settings)

        self.main_window.editor_requested.connect(self._open_editor)
        self.controller.open_editor_requested.connect(self._open_editor_with_file)
        self._editor_window = None

        # ── Always on top at startup ──
        if self.controller.get_always_on_top():
            self.main_window.setWindowFlags(
                self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
            )
            self.main_window.show()

        self._position_main_window()
        self.main_window.show()

    # ---------------- Positioning ----------------

    def _position_main_window(self):
        screen = self.main_window.screen().availableGeometry()
        pos = bottom_right_position(self.main_window, screen, margin=117)
        self.main_window.move(pos)

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
            self._editor_window.record_requested.connect(self._on_editor_record_requested)
            self._editor_window.closed.connect(self._on_editor_closed)

        self.main_window.set_editor_visible(True)
        self.main_window.hide()
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    def _on_editor_record_requested(self):
        """Кнопка «Запись» в редакторе → показать IDLE поверх."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _on_editor_closed(self):
        """Редактор скрыт → показать IDLE, разблокировать кнопку."""
        self.main_window.set_editor_visible(False)
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _open_editor_with_file(self, path: str):
        from src.pik2video.gui.editor.window import EditorWindow

        if self._editor_window is None:
            self._editor_window = EditorWindow(controller=self.controller)
            self._editor_window.record_requested.connect(self._on_editor_record_requested)
            self._editor_window.closed.connect(self._on_editor_closed)

        self._editor_window.load_file(path)
        self.main_window.set_editor_visible(True)
        self.main_window.hide()
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    def _open_editor_with_file(self, path: str):
        """Открыть редактор и загрузить в него файл."""
        from src.pik2video.gui.editor.window import EditorWindow

        if self._editor_window is None:
            self._editor_window = EditorWindow(controller=self.controller)

        self._editor_window.load_file(path)
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

    # ---------------- Run ----------------

    def run(self):
        self.qt_app.exec()