# src/pik2video/gui/widgets/finalize_screen_settings.py

from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSpinBox, QWidget

from .screen_settings import CleanSpinBox


class PlaybackFpsInput(QWidget):
    """
    FPS итогового видео, собранного из скриншотов.

    Ограничения:
    1–100
    """

    valueChanged = Signal(int)

    def __init__(self, initial: int = 10):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.spinbox = CleanSpinBox()
        self.spinbox.setRange(1, 1000)
        self.spinbox.setValue(initial)
        self.spinbox.setMinimumWidth(60)
        self.spinbox.setAlignment(Qt.AlignCenter)
        
        # скрываем стрелки
        self.spinbox.setButtonSymbols(QSpinBox.NoButtons)

        # сигнал наружу
        self.spinbox.valueChanged.connect(self.valueChanged.emit)

        layout.addWidget(self.spinbox)

    def get(self) -> int:
        """Возвращает текущее значение."""
        return self.spinbox.value()

    def set(self, value: int):
        """Устанавливает значение."""
        self.spinbox.setValue(value)


class SpeedPresetSelector(QWidget):
    """
    Пресеты скорости: кнопки < > и метка [1x] между ними.
    Не связан с FPS — просто выбирает множитель.
    """

    valueChanged = Signal(float)  # множитель

    PRESETS: ClassVar[list] = [0.25, 0.5, 1.0, 2.0, 4.0]

    def __init__(self):
        super().__init__()
        self._current_index = 2  # 1.0x по умолчанию

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedSize(28, 24)
        self.btn_prev.clicked.connect(self._prev)

        self.speed_label = QLabel("1x")
        self.speed_label.setAlignment(Qt.AlignCenter)
        self.speed_label.setFixedWidth(40)
        self.speed_label.setStyleSheet("color: #e0e0e0; font-size: 12px;")

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedSize(28, 24)
        self.btn_next.clicked.connect(self._next)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.speed_label)
        layout.addWidget(self.btn_next)
        layout.addStretch()

        self._update_buttons()

    def _prev(self):
        if self._current_index > 0:
            self._current_index -= 1
            self._apply()

    def _next(self):
        if self._current_index < len(self.PRESETS) - 1:
            self._current_index += 1
            self._apply()

    def _apply(self):
        multiplier = self.PRESETS[self._current_index]
        self.speed_label.setText(f"[{multiplier}x]")
        self._update_buttons()
        self.valueChanged.emit(multiplier)

    def _update_buttons(self):
        self.btn_prev.setEnabled(self._current_index > 0)
        self.btn_next.setEnabled(self._current_index < len(self.PRESETS) - 1)

    def get_multiplier(self) -> float:
        return self.PRESETS[self._current_index]
