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

from ...common.styles import BOTTOM_PANEL_QSS

logger = logging.getLogger(__name__)

DROP_AREA_WIDTH = 108
BOTTOM_PANEL_HEIGHT = 44
EXPORT_NAME_WIDTH = 220


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
        self.setObjectName("bottomPanel")
        self.setStyleSheet(BOTTOM_PANEL_QSS)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 0, 2)
        layout.setSpacing(8)

        # ── Блок экспорта ──
        self.export_block = QWidget()
        self.export_block.setObjectName("exportBlock")
        export_layout = QHBoxLayout(self.export_block)
        export_layout.setContentsMargins(8, 2, 4, 2)
        export_layout.setSpacing(6)

        # Поле имени + расширение
        self.export_name_label = QLabel("имя файла")
        self.export_name_label.setStyleSheet(
            "color: #888; font-size: 11px; "
            "background: transparent; border: none;"
        )

        self.export_name_frame = QFrame()
        self.export_name_frame.setObjectName("exportNameFrame")
        self.export_name_frame.setFixedWidth(EXPORT_NAME_WIDTH)
        name_layout = QHBoxLayout(self.export_name_frame)
        name_layout.setContentsMargins(6, 5, 6, 5)
        name_layout.setSpacing(0)

        self.export_name_input = QLineEdit()
        self.export_name_input.setFrame(False)
        self.export_name_input.setEnabled(False)
        self.export_name_input.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
        self.export_path_value.setObjectName("exportPathValue")
        self.export_path_value.setFlat(True)
        self.export_path_value.setCursor(Qt.PointingHandCursor)
        self.export_path_value.clicked.connect(self.export_path_clicked.emit)

        # Кнопка «Экспорт»
        self.btn_export = QPushButton("Экспорт")
        self.btn_export.setObjectName("btnExport")
        self.btn_export.setFixedHeight(24)
        self.btn_export.setFixedWidth(100)
        self.btn_export.clicked.connect(self.export_clicked.emit)
        self.btn_export.setEnabled(False)

        export_layout.addWidget(self.export_name_frame, stretch=0)
        export_layout.addWidget(self.export_name_label, stretch=0)
        export_layout.addStretch(1)
        export_layout.addWidget(self.export_path_value, stretch=0)
        export_layout.addSpacing(12)
        export_layout.addWidget(self.btn_export, stretch=0)

        layout.addWidget(self.export_block, stretch=1)

        # ── Clear-блок (dashed) ──
        self.clear_frame = QFrame()
        self.clear_frame.setObjectName("clearFrame")
        self.clear_frame.setFixedWidth(DROP_AREA_WIDTH)
        clear_layout = QVBoxLayout(self.clear_frame)
        clear_layout.setContentsMargins(6, 6, 6, 6)
        clear_layout.setSpacing(0)

        self.btn_clear = QPushButton("Очистить")
        self.btn_clear.setObjectName("btnClear")
        self.btn_clear.setFixedHeight(24)
        self.btn_clear.clicked.connect(self.clear_clicked.emit)

        clear_layout.addStretch()
        clear_layout.addWidget(self.btn_clear)

        layout.addWidget(self.clear_frame, stretch=0)

        self.set_clear_enabled(False)
        self.set_export_path("")
        self.set_editing_enabled(False)

    # ── Публичный API ──

    def set_export_enabled(self, enabled: bool):
        self.btn_export.setEnabled(enabled)

    def set_export_text(self, text: str):
        self.btn_export.setText(text)

    def set_export_filename(self, stem: str, ext: str):
        if stem:
            self.export_name_input.setPlaceholderText("")
            self.export_name_input.blockSignals(True)
            self.export_name_input.setText(stem)
            self.export_name_input.blockSignals(False)
            self.export_ext_label.setText(ext)
        else:
            self.export_name_input.setPlaceholderText("output_m.d_hh.mm.ss")
            self.export_name_input.blockSignals(True)
            self.export_name_input.setText("")
            self.export_name_input.blockSignals(False)
            self.export_ext_label.setText("")

    def set_export_path(self, path: str):
        self.export_path_value.setText(path)

    def set_editing_enabled(self, enabled: bool):
        """Включить/выключить поля ввода: имя файла, путь экспорта."""
        self.export_name_input.setEnabled(enabled)
        self.export_path_value.setEnabled(enabled)

    def set_clear_enabled(self, enabled: bool):
        self.btn_clear.setEnabled(enabled)
