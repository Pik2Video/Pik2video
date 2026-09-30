# src/pik2video/gui/editor/tools/bitrate.py
"""
Инструмент выбора битрейта.

Отвечает только за:
- выбор режима: авто / вручную
- ввод значения вручную
- публикацию сигнала при смене

Не знает:
- про EditorState
- про FFmpeg
"""

import logging

from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QMenu, QLineEdit
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction

logger = logging.getLogger(__name__)


class BitrateTool(QWidget):
    """Режим битрейта + значение."""

    valueChanged = Signal(str, str)  # mode, value

    def __init__(self, mode: str = "auto", value: str = "4M", parent=None):
        super().__init__(parent)
        self._mode = mode if mode in ("auto", "manual") else "auto"
        self._value = value

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        #layout.addStretch()

        self._btn_mode = QPushButton("Авто" if self._mode == "auto" else "Вручную")
        self._btn_mode.setFixedSize(76, 26)

        self._btn_mode.setFocusPolicy(Qt.NoFocus)
        self._btn_mode.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
                padding: 2px 4px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton::menu-indicator { image: none; }
        """)

        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
            }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #3a3a3a; }
        """)
        for key, label in [("auto", "Авто"), ("manual", "Вручную")]:
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, k=key: self._set_mode(k))
            menu.addAction(action)
        self._btn_mode.setMenu(menu)

        self._input_value = QLineEdit(self._value)
        self._input_value.setFixedSize(28, 26)
        self._input_value.setAlignment(Qt.AlignCenter)
        self._input_value.setStyleSheet("""
            QLineEdit {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
                padding: 0px;
            }
        """)
        self._input_value.setVisible(self._mode == "manual")
        self._input_value.textChanged.connect(self._on_value_changed)

        if self._mode == "auto":
            self._btn_mode.setFixedSize(106, 26)

        layout.addWidget(self._btn_mode)
        layout.addWidget(self._input_value)

    def _set_mode(self, mode: str):
        if mode not in ("auto", "manual"):
            return
        self._mode = mode
        if mode == "auto":
            self._btn_mode.setText("Авто")
            self._btn_mode.setFixedSize(106, 26)
            self._input_value.setVisible(False)
        else:
            self._btn_mode.setText("Вручную")
            self._btn_mode.setFixedSize(76, 26)
            self._input_value.setVisible(True)
        logger.debug(f"Битрейт режим: {mode}")
        self.valueChanged.emit(self._mode, self._value)

    def _on_value_changed(self, text: str):
        self._value = text
        self.valueChanged.emit(self._mode, self._value)

    def get_mode(self) -> str:
        return self._mode

    def get_value(self) -> str:
        return self._value