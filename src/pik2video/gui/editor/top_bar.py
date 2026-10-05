# src/pik2video/gui/editor/top_bar.py
"""
Верхняя панель редактора.

Содержит:
- блок с кнопками ⚙️ / 🛠️ (слева)
- панель пресетов кадра (по центру, скрыта по умолчанию)
- кнопку «⚫ Запись» (справа)

Публикует сигналы:
- tools_clicked / settings_clicked
- preset_changed
- record_toggled
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget
)

logger = logging.getLogger(__name__)


TOP_BAR_HEIGHT = 32
TOOLS_BLOCK_WIDTH = 200

PRESETS = [
    ("Ориг", "original"),
    ("16:9", "16:9"),
    ("9:16", "9:16"),
    ("1:1",  "1:1"),
    ("4:5",  "4:5"),
    ("4:3",  "4:3"),
]


class TopBar(QWidget):
    """Верхняя полоска редактора."""

    tools_clicked = Signal()
    settings_clicked = Signal()
    preset_changed = Signal(str)
    aspect_mode_changed = Signal(str)
    record_toggled = Signal(bool)

    def __init__(self, tools_block_width: int = TOOLS_BLOCK_WIDTH, parent=None):
        super().__init__(parent)
        self._tools_block_width = tools_block_width

        self.setFixedHeight(TOP_BAR_HEIGHT)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 4px;
            }
        """)

        self._build_ui()

    # ── Сборка ──

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 4, 2)
        layout.setSpacing(4)

        self.tools_block = self._build_tools_block()
        layout.addWidget(self.tools_block)
        layout.addStretch()

        self.presets_panel = self._build_presets_panel()
        layout.addWidget(self.presets_panel)
        layout.addStretch()

        self.btn_record = self._build_record_button()
        layout.addWidget(self.btn_record)

    def _build_tools_block(self) -> QWidget:
        block = QWidget()
        block.setFixedWidth(self._tools_block_width)
        block.setStyleSheet("""
            QWidget {
                background: transparent;
                border: 1px solid #555;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                border-bottom-left-radius: 0px;
                border-bottom-right-radius: 0px;
            }
        """)

        layout = QHBoxLayout(block)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:checked {
                background-color: #5a5a5a;
                border-color: #888;
            }
        """

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(28, 24)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setStyleSheet(btn_style)
        self.btn_settings.clicked.connect(self._on_settings_btn_clicked)
        layout.addWidget(self.btn_settings)

        layout.addStretch()

        self.btn_tools = QPushButton("🛠️")
        self.btn_tools.setFixedSize(28, 24)
        self.btn_tools.setCheckable(True)
        self.btn_tools.setChecked(True)
        self.btn_tools.setStyleSheet(btn_style)
        self.btn_tools.clicked.connect(self._on_tools_btn_clicked)
        layout.addWidget(self.btn_tools)

        return block

    def _build_presets_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent; border: none;")
        panel.setVisible(False)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 2px 10px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:checked {
                background-color: #5a5a5a;
                border-color: #d4a843;
            }
        """

        self._preset_group = QButtonGroup(panel)
        self._preset_group.setExclusive(True)

        self.preset_buttons = {}
        for label, key in PRESETS:
            btn = QPushButton(label)
            btn.setFixedHeight(24)
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.clicked.connect(
                lambda checked=False, k=key: self._on_preset_clicked(k)
            )
            self._preset_group.addButton(btn)
            self.preset_buttons[key] = btn
            layout.addWidget(btn)

        self.preset_buttons["original"].setChecked(True)

        # ── Разделитель ──
        layout.addSpacing(16)
        divider = QLabel("|")
        divider.setStyleSheet(
            "color: #555; font-size: 14px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(divider)
        layout.addSpacing(16)

        # ── Режим: crop / pad ──
        mode_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 2px 8px;
                font-size: 13px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:checked {
                background-color: #5a5a5a;
                border-color: #d4a843;
            }
        """

        self._mode_group = QButtonGroup(panel)
        self._mode_group.setExclusive(True)

        self.btn_crop = QPushButton("✂️")
        self.btn_crop.setFixedSize(30, 24)
        self.btn_crop.setCheckable(True)
        #self.btn_crop.setChecked(True)

        self.btn_crop.setStyleSheet(mode_style)
        self.btn_crop.setFocusPolicy(Qt.NoFocus)
        self.btn_crop.setToolTip("Обрезать по краям")
        self.btn_crop.clicked.connect(lambda: self._on_mode_clicked("crop"))
        self._mode_group.addButton(self.btn_crop)
        layout.addWidget(self.btn_crop)

        self.btn_pad = QPushButton("⬛")
        self.btn_pad.setFixedSize(30, 24)
        self.btn_pad.setCheckable(True)
        self.btn_pad.setChecked(True)
        self.btn_pad.setStyleSheet(mode_style)
        self.btn_pad.setFocusPolicy(Qt.NoFocus)
        self.btn_pad.setToolTip("Дополнить фоном")
        self.btn_pad.clicked.connect(lambda: self._on_mode_clicked("pad"))
        self._mode_group.addButton(self.btn_pad)
        layout.addWidget(self.btn_pad)

        return panel

    def _build_record_button(self) -> QPushButton:
        btn = QPushButton(" ⚫  Запись ")
        btn.setFixedHeight(24)
        btn.setCheckable(True)
        btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 2px 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:checked {
                background-color: #5a5a5a;
                border-color: #888;
            }
        """)
        btn.toggled.connect(self.record_toggled.emit)
        return btn

    # ── Обработчики ──

    def _on_tools_btn_clicked(self):
        self.btn_tools.setChecked(True)
        self.btn_settings.setChecked(False)
        self.tools_clicked.emit()

    def _on_settings_btn_clicked(self):
        self.btn_settings.setChecked(True)
        self.btn_tools.setChecked(False)
        self.settings_clicked.emit()

    def _on_preset_clicked(self, key: str):
        logger.debug(f"Пресет выбран: {key}")
        self.preset_changed.emit(key)

    def _on_mode_clicked(self, mode: str):
        logger.debug(f"Режим кадра: {mode}")
        self.aspect_mode_changed.emit(mode)

    # ── Управление панелью пресетов ──

    def show_presets(self, visible: bool):
        self.presets_panel.setVisible(visible)

    def set_aspect_mode(self, mode: str):
        """Синхронизировать активную кнопку режима с состоянием."""
        if mode == "crop":
            self.btn_crop.setChecked(True)
        elif mode == "pad":
            self.btn_pad.setChecked(True)
