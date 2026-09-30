# src/pik2video/gui/editor/tools/rotation.py
"""
Инструмент выбора поворота видео.

Отвечает только за:
- показ кнопки с текущим углом
- выпадающее меню
- публикацию сигнала при смене

Не знает:
- про EditorState
- про FFmpeg
"""

import logging

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QMenu
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)


ANGLES = {
    0: "0°",
    90: "90°",
    180: "180°",
    270: "270°",
}


class RotationTool(QWidget):
    """Кнопка-меню для выбора угла поворота."""

    valueChanged = Signal(int)

    def __init__(self, initial: int = 0, parent=None):
        super().__init__(parent)
        self._current = initial if initial in ANGLES else 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._btn = QPushButton(ANGLES[self._current])
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
        for angle, label in ANGLES.items():
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, a=angle: self.set_value(a))
            self._menu.addAction(action)

        self._btn.setMenu(self._menu)
        layout.addWidget(self._btn)

    def get_value(self) -> int:
        return self._current

    def set_value(self, angle: int):
        if angle not in ANGLES:
            return
        if self._current == angle:
            return
        self._current = angle
        self._btn.setText(ANGLES[angle])
        logger.debug(f"Поворот: {angle}°")
        self.valueChanged.emit(angle)