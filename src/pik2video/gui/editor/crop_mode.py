# src/pik2video/gui/editor/crop_mode.py
"""
Контроллер режима настройки кадра (пресеты).

Отвечает за:
- переключение видимости панели пресетов в TopBar
- уведомление подписчиков о входе/выходе из режима

Кнопка режима — в TopBar (btn_crop). Не блокирует интерфейс:
пользователь может играть, ставить метки, работать с зонами и т.д.

Не знает:
- как применяется обрезка
- про EditorState
- про PlayerWidget и PresetFrame (это отдельный слой)
"""

import logging

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class CropModeController(QObject):
    """Управляет режимом настройки кадра."""

    mode_opened = Signal()
    mode_closed = Signal()

    def __init__(self, editor_window, parent=None):
        super().__init__(parent)
        self._editor = editor_window
        self._active = False

    def is_active(self) -> bool:
        return self._active

    def toggle(self, checked: bool = None):
        """Переключить режим. `checked` приходит от checkable-кнопки TopBar."""
        if self._active:
            self.close()
        else:
            self.open()

    def open(self):
        if self._active:
            return
        if not self._editor.state.has_videos():
            logger.debug("Пресеты: нет видео — режим не включается")
            if hasattr(self._editor.top_bar, "btn_crop"):
                self._editor.top_bar.btn_crop.blockSignals(True)
                self._editor.top_bar.btn_crop.setChecked(False)
                self._editor.top_bar.btn_crop.blockSignals(False)
            return

        self._active = True
        self._editor.top_bar.show_presets(True)
        logger.debug("Режим пресетов открыт")
        self.mode_opened.emit()

    def close(self):
        if not self._active:
            return
        self._active = False
        self._editor.top_bar.show_presets(False)
        if hasattr(self._editor.top_bar, "btn_crop"):
            self._editor.top_bar.btn_crop.blockSignals(True)
            self._editor.top_bar.btn_crop.setChecked(False)
            self._editor.top_bar.btn_crop.blockSignals(False)
        logger.debug("Режим пресетов закрыт")
        self.mode_closed.emit()
