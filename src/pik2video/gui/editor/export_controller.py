# src/pik2video/gui/editor/export_controller.py
"""
Контроллер экспорта.

Отвечает за:
- запуск ExportService
- показ диалога прогресса
- обработку отмены
- показ результата (успех / ошибка)

Не знает:
- про layout редактора
- про другие зоны
"""

import logging

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QMessageBox

from .export_dialog import ExportDialog
from .export_service import ExportService
from .state import EditorState

logger = logging.getLogger(__name__)


class ExportController(QObject):
    """Управляет процессом экспорта."""

    export_started = Signal()
    export_progress = Signal(int)
    export_finished = Signal(bool, str)

    def __init__(self, editor_window, state: EditorState, parent=None):
        super().__init__(parent)
        self._editor = editor_window
        self._state = state

        self._service = ExportService(self)
        self._service.export_started.connect(self._on_started)
        self._service.export_progress.connect(self._on_progress)
        self._service.export_finished.connect(self._on_finished)

        self._dialog = None

    # ── Публичный API ──

    def is_running(self) -> bool:
        return self._service.is_running()

    def start(self):
        """Запустить экспорт с показом прогресса."""
        if not self._state.has_videos():
            QMessageBox.warning(self._editor, "Экспорт", "Нет активного видеофайла.")
            return

        if self._service.is_running():
            QMessageBox.information(self._editor, "Экспорт", "Экспорт уже идёт.")
            return

        self._editor.bottom_panel.set_export_enabled(False)
        self._editor.bottom_panel.set_export_text("Экспорт...")

        self._dialog = ExportDialog(self._editor)
        self._dialog.cancel_requested.connect(self._on_cancel)
        self._dialog.show()

        self._service.start_export(self._state)

    def cancel(self):
        """Прервать текущий экспорт."""
        if self._dialog is not None:
            self._dialog.set_cancelling()
        self._service.cancel()

    # ── Обработчики ──

    def _on_cancel(self):
        self.cancel()

    def _on_started(self):
        logger.info("Экспорт: старт")
        self.export_started.emit()

    def _on_progress(self, percent: int):
        if self._dialog is not None:
            self._dialog.set_progress(percent)
        self.export_progress.emit(percent)

    def _on_finished(self, success: bool, message: str):
        self._editor.bottom_panel.set_export_enabled(True)
        self._editor.bottom_panel.set_export_text("Экспорт")

        if self._dialog is None:
            return

        if success:
            self._dialog.show_success(message)
        else:
            self._dialog.show_error(message)

        self.export_finished.emit(success, message)
