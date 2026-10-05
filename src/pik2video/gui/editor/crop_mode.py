# src/pik2video/gui/editor/crop_mode.py
"""
Режим обрезки кадра.

Отвечает за:
- квадратную кнопку ⛶ в углу мультиплеера
- прозрачный overlay для закрытия режима по клику
- показ/скрытие панели пресетов через top_bar

Не знает:
- как применяется обрезка
- про EditorState
"""

import logging

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


class _CropModeButton(QWidget):
    """Top-level квадратная кнопка в углу мультиплеера."""

    clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(36, 36)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 6px;
            }
            QWidget:hover {
                background-color: #3a3a3a;
                border-color: #d4a843;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._label = QLabel("⛶")
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "color: #e0e0e0; font-size: 20px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self._label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class _CropCloseOverlay(QWidget):
    """Прозрачный top-level overlay — ловит клики вне панели/кнопки."""

    clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def mousePressEvent(self, event):
        self.clicked.emit()


class CropModeController(QObject):
    """Управляет режимом обрезки кадра."""

    mode_opened = Signal()
    mode_closed = Signal()

    def __init__(self, editor_window, parent=None):
        super().__init__(parent)
        self._editor = editor_window

        self._button = _CropModeButton()
        self._button.clicked.connect(self.toggle)

        self._overlay = _CropCloseOverlay()
        self._overlay.clicked.connect(self.close)

        self._active = False

    # ── Публичный API ──

    def is_active(self) -> bool:
        return self._active

    def toggle(self):
        if self._active:
            self.close()
        else:
            self.open()

    def open(self):
        editor = self._editor
        if not editor.state.has_videos():
            return

        self._active = True

        # Панель пресетов через top_bar
        editor.top_bar.show_presets(True)

        # Overlay — под топбаром
        editor_global = editor.mapToGlobal(QPoint(0, 0))
        top_bar_h = editor.top_bar.height()
        self._overlay.setGeometry(
            editor_global.x(),
            editor_global.y() + top_bar_h,
            editor.width(),
            editor.height() - top_bar_h,
        )
        self._overlay.show()
        self._overlay.raise_()

        # Кнопка поверх
        self._position_button()
        self._button.show()
        self._button.raise_()

        editor.top_bar.btn_settings.setEnabled(False)

        self.mode_opened.emit()

    def close(self):
        if not self._active:
            return

        self._active = False

        self._editor.top_bar.show_presets(False)
        self._overlay.hide()
        self._editor.top_bar.btn_settings.setEnabled(True)

        self.mode_closed.emit()

    def show_button_if_needed(self):
        """Показать/скрыть кнопку ⛶ в зависимости от наличия видео."""
        if self._editor.state.has_videos():
            self._position_button()
            self._button.show()
            self._button.raise_()
        else:
            self._button.hide()
            if self._active:
                self.close()

    def reposition(self):
        """Пересчитать позицию кнопки."""
        if self._button.isVisible():
            self._position_button()

    def hide_windows(self):
        """Скрыть окна при закрытии редактора."""
        for w in (self._button, self._overlay):
            try:
                w.hide()
                w.deleteLater()
            except Exception:
                pass

    def hide_button(self):
        """Скрыть кнопку кадра (например, при сворачивании редактора)."""
        self._button.hide()
        if self._active:
            self._overlay.hide()

    def show_button(self):
        """Показать кнопку кадра обратно."""
        if self._editor.state.has_videos():
            self._position_button()
            self._button.show()
            if self._active:
                # При возврате редактора восстанавливаем overlay
                editor_global = self._editor.mapToGlobal(QPoint(0, 0))
                top_bar_h = self._editor.top_bar.height()
                self._overlay.setGeometry(
                    editor_global.x(),
                    editor_global.y() + top_bar_h,
                    self._editor.width(),
                    self._editor.height() - top_bar_h,
                )
                self._overlay.show()

    # ── Внутренние ──

    def _position_button(self):
        try:
            container = self._editor.multiplexer
            container_global = container.mapToGlobal(QPoint(0, 0))
            x = container_global.x() + 8
            y = container_global.y() + 8
            self._button.move(x, y)
        except Exception as e:
            logger.warning(f"Не удалось позиционировать кнопку кадра: {e}")
