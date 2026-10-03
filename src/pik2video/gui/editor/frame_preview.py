# src/pik2video/gui/editor/frame_preview.py
"""
Всплывающее превью кадра над маркером таймлайна.

Отвечает только за:
- показ миниатюры кадра
- позиционирование над курсором

Не знает:
- про плеер
- про EditorState
"""

import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


WIDTH = 180
HEIGHT = 102
OFFSET_Y = 14
PADDING = 2


class FramePreview(QWidget):
    """Всплывающее окно с миниатюрой кадра."""

    def __init__(self, parent=None):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(WIDTH, HEIGHT)
        self.setStyleSheet("""
            QWidget {
                background-color: #000;
                border: 1px solid #d4a843;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(PADDING, PADDING, PADDING, PADDING)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setStyleSheet("background: #000; border: none;")
        layout.addWidget(self._label)

    def show_frame(self, pixmap, global_x: int, global_y: int):
        """Показать кадр с центрированием по x и смещением вверх от y."""
        if pixmap is None or pixmap.isNull():
            return

        scaled = pixmap.scaled(
            WIDTH - 2 * PADDING,
            HEIGHT - 2 * PADDING,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self._label.setPixmap(scaled)

        x = global_x - WIDTH // 2
        y = global_y - HEIGHT - OFFSET_Y

        # Не вылезать за экран
        screen = QApplication.primaryScreen().availableGeometry()
        if x < screen.left():
            x = screen.left() + 4
        if x + WIDTH > screen.right():
            x = screen.right() - WIDTH - 4
        if y < screen.top():
            y = global_y + OFFSET_Y

        self.move(QPoint(x, y))
        self.show()
        self.raise_()

    def hide_preview(self):
        self.hide()
