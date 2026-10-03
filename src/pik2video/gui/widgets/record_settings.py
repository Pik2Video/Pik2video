# src/pik2video/gui/widgets/record_settings.py


from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


# ────────FPS Switcher────────
class FpsSwitcher(QWidget):
    def __init__(self, values, initial):
        super().__init__()

        self.values = values
        self.index = values.index(initial)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(40)   # фиксированная ширина кнопки
        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(40)   # фиксированная ширина кнопки
        self.label = QLabel(str(self.values[self.index]))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedWidth(30)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.label)
        layout.addWidget(self.btn_next)

        self.btn_prev.clicked.connect(self.prev)
        self.btn_next.clicked.connect(self.next)

        self._update_buttons()

    def prev(self):
        if self.index > 0:
            self.index -= 1
            self._refresh()

    def next(self):
        if self.index < len(self.values) - 1:
            self.index += 1
            self._refresh()

    def _refresh(self):
        self.label.setText(str(self.values[self.index]))
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < len(self.values) - 1)

    def get(self):
        return self.values[self.index]

    def set(self, value):
        if value in self.values:
            self.index = self.values.index(value)
            self._refresh()
