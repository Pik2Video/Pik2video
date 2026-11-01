# src/pik2video/gui/editor/tools/format.py
"""
Инструмент выбора формата видео.

Отвечает только за:
- показ кнопки с текущим форматом
- выпадающее меню с вариантами
- публикацию сигнала при смене

Не знает:
- про EditorState
- про FFmpeg
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QHBoxLayout, QMenu, QPushButton, QWidget

logger = logging.getLogger(__name__)


ALLOWED_FORMATS = ["MP4", "MKV", "AVI", "MOV", "GIF"]

class FormatTool(QWidget):
    """Кнопка-меню для выбора формата."""

    valueChanged = Signal(str)

    def __init__(self, initial: str = "MP4", parent=None):
        super().__init__(parent)
        self._formats = list(ALLOWED_FORMATS)                       # текущий список форматов
        self._current = initial if initial in self._formats else self._formats[0]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btn = QPushButton(self._current)
        self._btn.setFixedSize(106, 26)

        self._btn.setFocusPolicy(Qt.NoFocus)
        self._btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
                padding: 4px 8px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton::menu-indicator { image: none; }
        """)

        self._menu = QMenu(self)
        self._menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
            }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #3a3a3a; }
        """)

        self._rebuild_menu()                                        # строим меню по текущему списку
        self._btn.setMenu(self._menu)
        layout.addWidget(self._btn)

    def _rebuild_menu(self):
        """Перестроить меню по self._formats."""
        self._menu.clear()
        for fmt in self._formats:
            action = QAction(fmt, self)
            action.triggered.connect(lambda checked=False, f=fmt: self.set_value(f))
            self._menu.addAction(action)

    def set_formats(self, formats: list, current: str):
        """Заменить список форматов (например, при переключении видео ↔ аудио)."""
        self._formats = list(formats)
        self._current = current if current in self._formats else self._formats[0]
        self._btn.setText(self._current)
        self._rebuild_menu()

    def get_value(self) -> str:
        return self._current

    def set_value(self, fmt: str):
        if fmt not in self._formats:
            return
        if self._current == fmt:
            return
        self._current = fmt
        self._btn.setText(fmt)
        logger.debug(f"Формат: {fmt}")
        self.valueChanged.emit(fmt)