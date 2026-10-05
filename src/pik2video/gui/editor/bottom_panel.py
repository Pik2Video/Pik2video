# src/pik2video/gui/editor/bottom_panel.py
"""
Нижняя панель редактора (зона 3).

Содержит:
- поле имени файла
- путь экспорта (кнопка)
- кнопку «Экспорт»
- кнопку «Очистить» в dashed-рамке

Публикует сигналы наружу.
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)

DROP_AREA_WIDTH = 108
BOTTOM_PANEL_HEIGHT = 44
EXPORT_NAME_WIDTH = 130


class BottomPanel(QWidget):
    """Нижняя панель: экспорт + очистка."""

    export_clicked = Signal()
    clear_clicked = Signal()
    export_path_clicked = Signal()
    export_name_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.setFixedHeight(BOTTOM_PANEL_HEIGHT)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 0, 2)
        layout.setSpacing(8)

        # ── Блок экспорта ──
        self.export_block = QWidget()
        self.export_block.setStyleSheet("""
            QWidget {
                background-color: #383838;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)
        export_layout = QHBoxLayout(self.export_block)
        export_layout.setContentsMargins(8, 2, 4, 2)
        export_layout.setSpacing(6)

        # Поле имени + расширение
        self.export_name_frame = QFrame()
        self.export_name_frame.setFixedWidth(EXPORT_NAME_WIDTH)
        self.export_name_frame.setStyleSheet("""
            QFrame {
                background-color: #1e1e1e;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)
        name_layout = QHBoxLayout(self.export_name_frame)
        name_layout.setContentsMargins(6, 2, 6, 2)
        name_layout.setSpacing(0)

        self.export_name_input = QLineEdit()
        self.export_name_input.setFrame(False)
        self.export_name_input.setPlaceholderText("имя файла")
        self.export_name_input.setEnabled(False)
        self.export_name_input.setStyleSheet("""
            QLineEdit {
                background: transparent;
                border: none;
                color: #e0e0e0;
                font-size: 11px;
                padding: 0px;
            }
            QLineEdit:disabled {
                color: #555;
                background: transparent;
            }
        """)
        self.export_name_input.textChanged.connect(self.export_name_changed.emit)

        self.export_ext_label = QLabel("")
        self.export_ext_label.setStyleSheet(
            "color: #666; font-size: 11px; "
            "background: transparent; border: none;"
        )

        name_layout.addWidget(self.export_name_input, stretch=1)
        name_layout.addWidget(self.export_ext_label, stretch=0)

        # Путь экспорта
        self.export_path_value = QPushButton("")
        self.export_path_value.setFlat(True)
        self.export_path_value.setCursor(Qt.PointingHandCursor)
        self.export_path_value.clicked.connect(self.export_path_clicked.emit)

        # Кнопка «Экспорт»
        self.btn_export = QPushButton("Экспорт")
        self.btn_export.setFixedHeight(24)
        self.btn_export.setFixedWidth(100)
        self.btn_export.clicked.connect(self.export_clicked.emit)
        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #2a7a2a;
                border: 1px solid #3a9a3a;
                border-radius: 4px;
                color: white;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #3a9a3a; }
            QPushButton:pressed { background-color: #1a5a1a; }
            QPushButton:disabled {
                background-color: #2a2a2a;
                border: 1px solid #444;
                color: #555;
            }
        """)
        self.btn_export.setEnabled(False)

        export_layout.addWidget(self.export_name_frame, stretch=0)
        export_layout.addStretch(1)
        export_layout.addWidget(self.export_path_value, stretch=0)
        export_layout.addSpacing(12)
        export_layout.addWidget(self.btn_export, stretch=0)

        layout.addWidget(self.export_block, stretch=1)

        # ── Clear-блок (dashed) ──
        self.clear_frame = QFrame()
        self.clear_frame.setFixedWidth(DROP_AREA_WIDTH)
        self.clear_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 2px dashed #555;
                border-radius: 6px;
            }
        """)
        clear_layout = QVBoxLayout(self.clear_frame)
        clear_layout.setContentsMargins(6, 6, 6, 6)
        clear_layout.setSpacing(0)

        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.clicked.connect(self.clear_clicked.emit)

        clear_layout.addStretch()
        clear_layout.addWidget(self.btn_clear)

        layout.addWidget(self.clear_frame, stretch=0)

        self.set_clear_enabled(False)
        self.set_export_path("")

    # ── Публичный API ──

    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)

    def set_export_text(self, text: str):
        self.btn_export.setText(text)

    def set_export_filename(self, stem: str, ext: str):
        if stem:
            self.export_name_frame.setStyleSheet("""
                QFrame {
                    background-color: #2a2a2a;
                    border: 1px solid #555;
                    border-radius: 4px;
                }
            """)
            self.export_name_input.setEnabled(True)
            self.export_name_input.blockSignals(True)
            self.export_name_input.setText(stem)
            self.export_name_input.blockSignals(False)
            self.export_ext_label.setText(ext)
            self.export_ext_label.setStyleSheet(
                "color: #666; font-size: 11px; "
                "background: transparent; border: none;"
            )
        else:
            self.export_name_frame.setStyleSheet("""
                QFrame {
                    background-color: #1e1e1e;
                    border: 1px solid #444;
                    border-radius: 4px;
                }
            """)
            self.export_name_input.setEnabled(False)
            self.export_name_input.blockSignals(True)
            self.export_name_input.setText("")
            self.export_name_input.blockSignals(False)
            self.export_ext_label.setText("")

    def set_export_path(self, path: str):
        self.export_path_value.setText(path)
        self.export_path_value.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #5fbfbf;
                font-size: 13px;
                text-align: right;
                padding: 6px 10px;
            }
            QPushButton:hover {
                color: #7fd8d8;
            }
        """)

    def set_clear_enabled(self, enabled: bool):
        self.btn_clear.setEnabled(enabled)
        if enabled:
            self.btn_clear.setStyleSheet("""
                QPushButton {
                    background-color: #5a1a1a;
                    border: 1px solid #7a2a2a;
                    border-radius: 4px;
                    color: #e0c0c0;
                    font-size: 10px;
                }
                QPushButton:hover { background-color: #7a2a2a; }
                QPushButton:pressed { background-color: #3a0a0a; }
            """)
        else:
            self.btn_clear.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a;
                    border: 1px solid #444;
                    border-radius: 4px;
                    color: #666;
                    font-size: 10px;
                }
            """)
