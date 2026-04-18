# src/pic2vid/gui/components_settings/finalize_screen_settings.py

from PySide6.QtWidgets import QWidget, QHBoxLayout, QSpinBox
from PySide6.QtCore import Qt, Signal

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
        self.spinbox.setRange(1, 100)
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