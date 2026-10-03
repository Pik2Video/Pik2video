# src/pik2video/gui/editor/tools/resolution.py
"""
Инструмент выбора разрешения.

Отвечает только за:
- показ кнопки с текущим разрешением
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

# Ключ → отображаемая метка
RESOLUTIONS = {
    "original": "Оригинал",
    "1080p": "1080p",
    "720p": "720p",
    "480p": "480p",
}

class ResolutionTool(QWidget):
    """Кнопка-меню для выбора разрешения."""
    valueChanged = Signal(str)

    def __init__(self, initial: str = "original", parent=None):
        super().__init__(parent)
        self._current = initial if initial in RESOLUTIONS else "original"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btn = QPushButton(RESOLUTIONS[self._current])
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
        for key, label in RESOLUTIONS.items():
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, k=key: self.set_value(k))
            self._menu.addAction(action)

        self._btn.setMenu(self._menu)
        layout.addWidget(self._btn)

    def get_value(self) -> str:
        return self._current

    def set_value(self, value: str):
        if value not in RESOLUTIONS:
            return
        if self._current == value:
            return
        self._current = value
        self._btn.setText(RESOLUTIONS[value])
        logger.debug(f"Разрешение: {value}")
        self.valueChanged.emit(value)
