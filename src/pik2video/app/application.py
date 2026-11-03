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
from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QTimer, Qt
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

        # ── Контроллер ──
        self.controller = AppController()

        # применяем сохранённую настройку подсказок
        set_tooltips_enabled(self.controller.get_show_tooltips())

        # ставим фильтр на QApplication — перехватываем стандартные Qt-подсказки
        self._tooltip_filter = _TooltipEventFilter()
        self.qt_app.installEventFilter(self._tooltip_filter)

        self.main_window = RecordingWindow(self.controller)
        self.main_window.settings_visibility_changed.connect(self._on_settings_visibility)

        # ── Менеджеры ──
        self.blink_manager = BlinkManager()
        self.window_manager = WindowManager(
            qt_app=self.qt_app,
            main_window=self.main_window,
            controller=self.controller,
        )
        # Прогрев RecordingFrame: первый show() создаёт NSWindow (~50-100 мс).
        # Делаем это при старте, чтобы в момент записи show() был мгновенным.
        QTimer.singleShot(500, self.window_manager.preload_recording_frame)
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

        # При запуске сразу открываем редактор (IDLE остаётся скрытым)
        self._open_editor()

    # ---------------- Settings dialog pause ----------------

    def _on_settings_visibility(self, visible: bool):
        """Пользователь открыл/закрыл диалог настроек записи."""
        if visible:
            self.state_coordinator.pause_preparing_ui()
        else:
            self.state_coordinator.resume_preparing_ui()

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
        """Кнопка «запись звука» в редакторе → открыть окно записи звука."""
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()
        self.controller.prepare_audio()                                # переводим контроллер в PREPARING_AUDIO

    def _on_state_changed_editor_visibility(self, state):
        """Скрыть/показать редактор в зависимости от состояния."""
        from src.pik2video.application.state_machine import AppState

        # Скрытие — только при реальном переходе в PREPARING
        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN, AppState.PREPARING_AUDIO):
            if not self.controller.get_auto_hide_editor():
                return
            # ↑ для аудио автоскрытие редактора работает так же, как для видео и скрина

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
        logger.debug("Редактор закрыт")
        self.main_window.set_editor_visible(False)

        # Если окно записи открыто — приложение продолжает работу
        if self.main_window.isVisible():
            logger.debug("Окно записи видно → приложение продолжает работу")
            return

        # Больше видимых окон нет — закрываем приложение
        logger.debug("Все окна закрыты — выходим")
        self.qt_app.quit()

    def _open_editor_with_file(self, path: str):
        from src.pik2video.application.state_machine import AppState
        from src.pik2video.gui.common.dialogs import error as show_error_dialog
        from src.pik2video.gui.editor.window import EditorWindow

        if self._editor_window is None:
            self._editor_window = EditorWindow(controller=self.controller)
            self._editor_window.record_video_requested.connect(self._on_start_video)
            self._editor_window.record_screen_requested.connect(self._on_start_screen)
            self._editor_window.record_audio_requested.connect(self._on_start_audio)
            self._editor_window.closed.connect(self._on_editor_closed)

        # Имя файла-черновика (my_recording или recording_2026.10.07_14.30.25)
        # становится именем экспорта по умолчанию в редакторе.
        preferred_name = Path(path).stem
        loaded_ok = self._editor_window.load_file(path, preferred_name=preferred_name)

        self.main_window.set_editor_visible(True)
        self.main_window.hide()
        self._editor_window.show()
        self._editor_window.raise_()
        self._editor_window.activateWindow()

        # REVIEW ждёт подтверждения от редактора, чтобы перейти в IDLE
        if self.controller.state_manager.get_state() == AppState.REVIEW:
            if not loaded_ok:
                show_error_dialog(
                    self._editor_window,
                    f"Не удалось загрузить файл.\n\n"
                    f"Запись осталась в черновиках:\n{path}",
                    translator=self.controller.get_translator(),
                )
            self.controller.state_manager.finalize_session()

    # ---------------- Run ----------------

    def run(self):
        self.qt_app.exec()
