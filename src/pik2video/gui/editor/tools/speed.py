# src/pik2video/gui/editor/tools/speed.py
"""
Инструмент множителя скорости воспроизведения при экспорте.

Отвечает только за:
- выбор множителя через < >
- публикацию сигнала при смене

Не знает:
- про EditorState
- про FFmpeg
"""
import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

logger = logging.getLogger(__name__)

SPEED_PRESETS = [0.25, 0.5, 1.0, 2.0, 4.0]
DEFAULT_INDEX = 2  # 1.0x

class SpeedTool(QWidget):
    """Кнопки < > с меткой множителя между ними."""
    valueChanged = Signal(float)

    def __init__(self, initial: float = 1.0, parent=None):
        super().__init__(parent)

        if initial in SPEED_PRESETS:
            self._index = SPEED_PRESETS.index(initial)
        else:
            self._index = DEFAULT_INDEX

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { color: #555; background-color: #2a2a2a; }
        """

        self._btn_prev = QPushButton("<")
        self._btn_prev.setFixedSize(26, 24)
        self._btn_prev.setStyleSheet(btn_style)
        self._btn_prev.clicked.connect(self._on_prev)

        self._label = QLabel(self._format(SPEED_PRESETS[self._index]))
        self._label.setFixedWidth(36)
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet(
            "QLabel { color: #ccc; font-size: 11px; "
            "background: transparent; border: none; }"
            "QLabel:disabled { color: #555; }"
        )

        self._btn_next = QPushButton(">")
        self._btn_next.setFixedSize(26, 24)
        self._btn_next.setStyleSheet(btn_style)
        self._btn_next.clicked.connect(self._on_next)

        layout.addWidget(self._btn_prev)
        layout.addSpacing(2)
        layout.addWidget(self._label)
        layout.addSpacing(2)
        layout.addWidget(self._btn_next)

        self._update_buttons()

    def _format(self, value: float) -> str:
        if value == int(value):
            return f"{int(value)}x"
        return f"{value}x"

    def _on_prev(self):
        if self._index > 0:
            self._index -= 1
            self._apply()

    def _on_next(self):
        if self._index < len(SPEED_PRESETS) - 1:
            self._index += 1
            self._apply()

    def _apply(self):
        speed = SPEED_PRESETS[self._index]
        self._label.setText(self._format(speed))
        self._update_buttons()
        logger.debug(f"Скорость экспорта: {speed}x")
        self.valueChanged.emit(speed)

    def _update_buttons(self):
        self._btn_prev.setEnabled(self._index > 0)
        self._btn_next.setEnabled(self._index < len(SPEED_PRESETS) - 1)

    def get_value(self) -> float:
        return SPEED_PRESETS[self._index]

    def set_value(self, speed: float):
        if speed in SPEED_PRESETS:
            self._index = SPEED_PRESETS.index(speed)
            self._label.setText(self._format(speed))
            self._update_buttons()
