# src/pik2video/gui/widgets/setting_row.py

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget


CONTROL_COLUMN_WIDTH = 240   # ширина правой колонки (контрол центр)


class DashedLine(QWidget):
    """Тонкая пунктирная линия между текстом и контролом."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor("#555"), 1, Qt.DashLine)
        pen.setDashPattern([3, 4])
        painter.setPen(pen)
        y = self.height() // 2
        painter.drawLine(0, y, self.width(), y)


class SettingRow(QWidget):
    """Строка: текст (слева) — пунктир — контрол (в колонке 240, выравнивание задаётся)."""

    def __init__(self, text: str, control: QWidget, align=Qt.AlignCenter):
        super().__init__()
        self.setObjectName("settingRow")
        self.setStyleSheet(
            "QWidget#settingRow { background: transparent; border: none; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(8)

        self.label = QLabel(text)
        self.label.setStyleSheet(
            "background: transparent; border: none; "
            "color: #ddd; font-size: 12px;"
        )
        self.label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.label, stretch=0)

        self.dashed_line = DashedLine()
        layout.addWidget(self.dashed_line, stretch=1)

        ctrl_container = QWidget()
        ctrl_container.setObjectName("ctrlContainer")
        ctrl_container.setStyleSheet(
            "QWidget#ctrlContainer { background: transparent; border: none; }"
        )
        ctrl_container.setFixedWidth(CONTROL_COLUMN_WIDTH)
        ctrl_layout = QHBoxLayout(ctrl_container)
        ctrl_layout.setContentsMargins(0, 0, 0, 0)
        ctrl_layout.setAlignment(align)
        ctrl_layout.addWidget(control)
        layout.addWidget(ctrl_container, stretch=0)

        self.control = control

    def setText(self, text: str):
        if hasattr(self, 'label'):
            self.label.setText(text)
