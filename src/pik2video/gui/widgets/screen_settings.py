# src/pik2video/gui/widgets/screen_settings.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QSpinBox, QWidget


class CleanSpinBox(QSpinBox):
    """SpinBox который выделяет всё число при фокусе."""

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.lineEdit().selectAll()


# ──────── Capture Per Minute Input ────────
class CapturePerMinuteInput(QWidget):
    """
    Виджет для выбора количества кадров в минуту (1–100)
    для режима захвата экрана.
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
        self.spinbox.setButtonSymbols(QSpinBox.NoButtons)

        self.spinbox.valueChanged.connect(self.valueChanged.emit)

        layout.addWidget(self.spinbox)

    def get(self) -> int:
        """Возвращает текущее значение."""
        return self.spinbox.value()

    def set(self, value: int):
        """Устанавливает значение."""
        self.spinbox.setValue(value)
