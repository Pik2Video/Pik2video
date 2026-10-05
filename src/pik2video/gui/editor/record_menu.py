# src/pik2video/gui/editor/record_menu.py
"""
Меню записи — top-level окно с затемнением.

Отвечает за:
- затемнение области под топбаром при открытом меню
- показ кнопок «запись видео / скрин запись / запись звука»
- публикацию сигналов о выборе

Не знает:
- что делать после выбора (это EditorWindow)
"""

import logging

from PySide6.QtCore import QObject, QPoint, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

logger = logging.getLogger(__name__)


class _DimOverlayWindow(QWidget):
    """Top-level затемнение под топбаром. Клик — сигнал."""

    clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

    def mousePressEvent(self, event):
        self.clicked.emit()


class _RecordMenuWindow(QWidget):
    """Top-level меню с тремя кнопками записи."""

    record_video_clicked = Signal()
    record_screen_clicked = Signal()
    record_audio_clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 2px solid #b8892e;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 2px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """

        self.btn_video = QPushButton("запись видео")
        self.btn_video.setFixedHeight(24)
        self.btn_video.setStyleSheet(btn_style)
        self.btn_video.clicked.connect(self.record_video_clicked.emit)

        self.btn_screen = QPushButton("скрин запись")
        self.btn_screen.setFixedHeight(24)
        self.btn_screen.setStyleSheet(btn_style)
        self.btn_screen.clicked.connect(self.record_screen_clicked.emit)

        self.btn_audio = QPushButton("запись звука")
        self.btn_audio.setFixedHeight(24)
        self.btn_audio.setStyleSheet(btn_style)
        self.btn_audio.clicked.connect(self.record_audio_clicked.emit)

        layout.addWidget(self.btn_video)
        layout.addWidget(self.btn_screen)
        layout.addWidget(self.btn_audio)


class RecordMenuController(QObject):
    """Управляет открытием/закрытием меню записи."""

    record_video_requested = Signal()
    record_screen_requested = Signal()
    record_audio_requested = Signal()

    def __init__(self, editor_window, parent=None):
        super().__init__(parent)
        self._editor = editor_window

        self._dim_window = _DimOverlayWindow()
        self._dim_window.clicked.connect(self.close)

        self._menu_window = _RecordMenuWindow()
        self._menu_window.record_video_clicked.connect(self._on_video)
        self._menu_window.record_screen_clicked.connect(self._on_screen)
        self._menu_window.record_audio_clicked.connect(self._on_audio)

    # ── Публичный API ──

    def is_open(self) -> bool:
        return self._menu_window.isVisible()

    def toggle(self, checked: bool):
        if checked:
            self.open()
        else:
            self.close()

    def open(self):
        if self._menu_window.isVisible():
            return

        editor = self._editor
        top_bar = editor.top_bar
        top_bar_h = top_bar.height()

        editor_global = editor.mapToGlobal(QPoint(0, 0))
        self._dim_window.setGeometry(
            editor_global.x(),
            editor_global.y() + top_bar_h,
            editor.width(),
            editor.height() - top_bar_h,
        )
        self._dim_window.show()

        self._menu_window.adjustSize()
        menu_w = self._menu_window.sizeHint().width()
        menu_h = self._menu_window.sizeHint().height()

        btn_global = top_bar.btn_record.mapToGlobal(QPoint(0, 0))
        menu_x = btn_global.x() - menu_w - 4
        menu_y = btn_global.y() + (top_bar.btn_record.height() - menu_h) // 2

        self._menu_window.move(menu_x, menu_y)
        self._menu_window.show()

        top_bar.btn_settings.setEnabled(False)

    def close(self):
        self._dim_window.hide()
        self._menu_window.hide()

        top_bar = self._editor.top_bar
        top_bar.btn_settings.setEnabled(True)

        top_bar.btn_record.blockSignals(True)
        top_bar.btn_record.setChecked(False)
        top_bar.btn_record.blockSignals(False)

    def hide_windows(self):
        """Скрыть и освободить top-level окна при закрытии редактора."""
        for w in (self._dim_window, self._menu_window):
            try:
                w.hide()
                w.deleteLater()
            except Exception:
                pass

    # ── Обработчики ──

    def _on_video(self):
        self.close()
        self.record_video_requested.emit()

    def _on_screen(self):
        self.close()
        self.record_screen_requested.emit()

    def _on_audio(self):
        self.close()
        self.record_audio_requested.emit()
