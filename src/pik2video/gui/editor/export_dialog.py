# src/pik2video/gui/editor/export_dialog.py
"""
Диалог прогресса экспорта.

Отвечает только за:
- показ прогресс-бара
- кнопку «Отмена»
- показ результата (успех / ошибка)
- кнопку «Показать в Finder» после успеха

Не знает:
- про FFmpeg
- про EditorState
- про ExportService
"""

import logging
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QProgressBar, QPushButton
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class ExportDialog(QDialog):
    """Модальное окно прогресса экспорта."""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setModal(True)
        self.setWindowTitle("Экспорт")
        self.setFixedWidth(420)
        self.setMinimumHeight(180)

        self._output_path = None
        self._is_done = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ── Заголовок ──
        self.title_label = QLabel("Экспорт видео")
        self.title_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(self.title_label)

        # ── Статус ──
        self.status_label = QLabel("Обработка...")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.status_label)

        # ── Прогресс-бар ──
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #2a2a2a;
                text-align: center;
                color: #e0e0e0;
                height: 20px;
            }
            QProgressBar::chunk {
                background: #3a7a3a;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        # ── Кнопки ──
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Отмена")
        self.btn_cancel.setFixedWidth(110)
        self.btn_cancel.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_reveal = QPushButton("Показать в Finder")
        self.btn_reveal.setFixedWidth(160)
        self.btn_reveal.setVisible(False)
        self.btn_reveal.setStyleSheet("""
            QPushButton {
                background-color: #2a5a7a;
                border: 1px solid #3a7a9a;
                border-radius: 4px;
                color: white;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #3a7a9a; }
            QPushButton:pressed { background-color: #1a4a6a; }
        """)
        self.btn_reveal.clicked.connect(self._on_reveal_clicked)

        self.btn_close = QPushButton("Закрыть")
        self.btn_close.setFixedWidth(110)
        self.btn_close.setVisible(False)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
                padding: 6px 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)
        self.btn_close.clicked.connect(self.accept)

        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_reveal)
        btn_layout.addWidget(self.btn_close)
        btn_layout.addStretch()

        layout.addLayout(btn_layout)

    # ── Публичный API ──

    def set_progress(self, percent: int):
        self.progress_bar.setValue(percent)

    def show_success(self, output_path: str):
        self._is_done = True
        self._output_path = output_path

        self.title_label.setText("Экспорт завершён")
        self.title_label.setStyleSheet("color: #5fbf5f;")
        self.status_label.setText(Path(output_path).name)
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        self.progress_bar.setValue(100)

        self.btn_cancel.setVisible(False)
        self.btn_reveal.setVisible(True)
        self.btn_close.setVisible(True)

    def show_error(self, message: str):
        self._is_done = True

        self.title_label.setText("Ошибка экспорта")
        self.title_label.setStyleSheet("color: #ff6b6b;")
        self.status_label.setText(message)
        self.status_label.setStyleSheet("color: #d0a0a0; font-size: 11px;")

        self.btn_cancel.setVisible(False)
        self.btn_close.setVisible(True)

    def set_cancelling(self):
        self.status_label.setText("Отмена...")
        self.btn_cancel.setEnabled(False)

    # ── События ──

    def _on_cancel_clicked(self):
        if self._is_done:
            return
        self.cancel_requested.emit()

    def _on_reveal_clicked(self):
        if not self._output_path:
            return
        path = Path(self._output_path)
        try:
            subprocess.run(["open", "-R", str(path)], check=False)
        except Exception as e:
            logger.warning(f"Не удалось открыть Finder: {e}")

    def closeEvent(self, event):
        if not self._is_done:
            self.cancel_requested.emit()
        super().closeEvent(event)