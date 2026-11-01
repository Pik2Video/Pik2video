# src/pik2video/gui/editor/top_bar.py
"""
Верхняя панель редактора.

Раскладка:
[ [⚙️  🛠️] ⛶  (presets если открыты)   [⚫ Запись] ]

tools_block — компактный блок с рамкой, ширина = ширине ToolsPanel ниже.
btn_crop — отдельная кнопка справа от блока.
presets_panel — выезжает при btn_crop = checked.
"""

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QLabel, QPushButton, QWidget,
)

logger = logging.getLogger(__name__)


TOP_BAR_HEIGHT = 32
TOOLS_BLOCK_WIDTH = 200

PRESETS = [
    ("Оригинал", "original", "Оригинальные пропорции видео. Без обрезки"),
    ("16:9", "16:9", "Горизонтальное видео: YouTube, телевизоры"),
    ("9:16", "9:16", "Вертикальное видео: TikTok, Reels, Shorts"),
    ("1:1",  "1:1", "Квадрат: Instagram-пост, аватар"),
    ("4:5",  "4:5", "Портрет: Instagram-лента, мобильные ленты"),
    ("4:3",  "4:3", "Классическое видео: старые ТВ, презентации"),
]

TOOLBAR_BTN_STYLE = """
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


class TopBar(QWidget):
    """Верхняя полоса редактора."""

    tools_clicked = Signal()
    settings_clicked = Signal()
    crop_toggled = Signal(bool)
    preset_changed = Signal(str)
    zoom_changed = Signal(int)
    marker_mode_toggled = Signal(bool)   # True = режим сдвига рамки активен
    record_toggled = Signal(bool)

    def __init__(self, tools_block_width: int = TOOLS_BLOCK_WIDTH, parent=None):
        super().__init__(parent)
        self._tools_block_width = tools_block_width
        self._current_zoom = 0
        self._zoom_enabled = False

        self.setFixedHeight(TOP_BAR_HEIGHT)
        self.setObjectName("TopBarContainer")
        self.setAttribute(Qt.WA_StyledBackground, True)     # без этого QWidget игнорирует фон из CSS
        self.setStyleSheet("""
            QWidget#TopBarContainer {
                background-color: #333333;
                border: 1px solid #666;
                border-radius: 4px;
            }
        """)

        self._build_ui()


    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 4, 0)         # левый край — вплотную
        layout.setSpacing(6)

        self.tools_block = self._build_tools_block()
        layout.addWidget(self.tools_block)

        self.btn_crop = self._build_crop_button()
        layout.addWidget(self.btn_crop)

        self.presets_panel = self._build_presets_panel()
        layout.addWidget(self.presets_panel)

        layout.addStretch()

        self.btn_record = self._build_record_button()
        layout.addWidget(self.btn_record)


    def _build_tools_block(self) -> QWidget:
        """Компактный блок с двумя кнопками и своей рамкой."""
        block = QWidget()
        block.setFixedWidth(self._tools_block_width)
        block.setObjectName("toolsBlock")
        block.setAttribute(Qt.WA_StyledBackground, True)
        block.setStyleSheet("""
            QWidget#toolsBlock {
                background-color: transparent;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(block)
        layout.setContentsMargins(4, 0, 4, 0)         # внутренние отступы кнопок
        layout.setSpacing(4)

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(28, 22)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setFocusPolicy(Qt.NoFocus)
        self.btn_settings.setStyleSheet(TOOLBAR_BTN_STYLE)
        self.btn_settings.clicked.connect(self._on_settings_btn_clicked)
        layout.addWidget(self.btn_settings)

        layout.addStretch()

        self.btn_tools = QPushButton("🛠️")
        self.btn_tools.setFixedSize(28, 22)
        self.btn_tools.setCheckable(True)
        self.btn_tools.setChecked(True)
        self.btn_tools.setFocusPolicy(Qt.NoFocus)
        self.btn_tools.setStyleSheet(TOOLBAR_BTN_STYLE)
        self.btn_tools.clicked.connect(self._on_tools_btn_clicked)
        layout.addWidget(self.btn_tools)

        return block


    def _build_crop_button(self) -> QPushButton:
        """Кнопка ⛶ — режим настройки кадра. Отдельная, вне tools_block."""
        btn = QPushButton("⛶")
        btn.setFixedSize(28, 22)
        btn.setCheckable(True)
        btn.setFocusPolicy(Qt.NoFocus)
        btn.setStyleSheet(TOOLBAR_BTN_STYLE)
        btn.clicked.connect(self._on_crop_btn_clicked)
        return btn


    def _build_presets_panel(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet("background: transparent; border: none;")
        panel.setVisible(False)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 0, 0, 0)
        layout.setSpacing(6)

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
                border-color: #8a6f2a;
            }
        """

        self._preset_group = QButtonGroup(panel)
        self._preset_group.setExclusive(True)

        self.preset_buttons = {}
        for label, key, tooltip in PRESETS:
            btn = QPushButton(label)
            btn.setFixedHeight(22)
            btn.setCheckable(True)
            btn.setStyleSheet(btn_style)
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setToolTip(tooltip)
            btn.clicked.connect(
                lambda checked=False, k=key: self._on_preset_clicked(k)
            )
            self._preset_group.addButton(btn)
            self.preset_buttons[key] = btn
            layout.addWidget(btn)

        self.preset_buttons["original"].setChecked(True)

        layout.addSpacing(16)
        divider = QLabel("|")
        divider.setStyleSheet(
            "color: #555; font-size: 14px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(divider)
        layout.addSpacing(16)

        zoom_style = """
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
            QPushButton:disabled {
                color: #555;
                background-color: #2a2a2a;
                border-color: #333;
            }
        """

        self.btn_zoom_minus = QPushButton("−")
        self.btn_zoom_minus.setFixedSize(26, 22)
        self.btn_zoom_minus.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_minus.setStyleSheet(zoom_style)
        self.btn_zoom_minus.setToolTip("Уменьшить обрезку")
        self.btn_zoom_minus.clicked.connect(self._on_zoom_minus)
        layout.addWidget(self.btn_zoom_minus)

        self.lbl_zoom = QLabel("x1")
        self.lbl_zoom.setFixedWidth(28)
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )
        layout.addWidget(self.lbl_zoom)

        self.btn_zoom_plus = QPushButton("+")
        self.btn_zoom_plus.setFixedSize(26, 22)
        self.btn_zoom_plus.setFocusPolicy(Qt.NoFocus)
        self.btn_zoom_plus.setStyleSheet(zoom_style)
        self.btn_zoom_plus.setToolTip("Увеличить обрезку (обрезка краёв)")
        self.btn_zoom_plus.clicked.connect(self._on_zoom_plus)
        layout.addWidget(self.btn_zoom_plus)

        layout.addSpacing(12)
        divider2 = QLabel("|")
        divider2.setStyleSheet(
            "color: #555; font-size: 14px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(divider2)
        layout.addSpacing(12)

        self.btn_marker = QPushButton("🖋️")
        self.btn_marker.setFixedSize(30, 22)
        self.btn_marker.setCheckable(True)
        self.btn_marker.setFocusPolicy(Qt.NoFocus)
        self.btn_marker.setStyleSheet(zoom_style)
        self.btn_marker.setToolTip("Режим сдвига рамки")
        self.btn_marker.clicked.connect(self._on_marker_clicked)
        layout.addWidget(self.btn_marker)

        self._update_zoom_buttons()
        return panel


    def _build_record_button(self) -> QPushButton:
        btn = QPushButton(" ⚫  Запись ")
        btn.setFixedHeight(22)
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


    def _on_crop_btn_clicked(self):
        self.crop_toggled.emit(self.btn_crop.isChecked())

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

    def _on_marker_clicked(self):
        active = self.btn_marker.isChecked()
        self.btn_marker.setText("🖍️" if active else "🖋️")
        self.marker_mode_toggled.emit(active)
        self._update_zoom_buttons()

    def set_marker_mode(self, active: bool):
        """Внешняя синхронизация состояния (например, при сбросе пресета)."""
        active = bool(active)
        if self.btn_marker.isChecked() == active:
            return
        self.btn_marker.blockSignals(True)
        self.btn_marker.setChecked(active)
        self.btn_marker.setText("🖍️" if active else "🖋️")
        self.btn_marker.blockSignals(False)

    def _on_zoom_minus(self):
        if self._current_zoom > 0:
            self.zoom_changed.emit(self._current_zoom - 1)

    def _on_zoom_plus(self):
        if self._current_zoom < 4:
            self.zoom_changed.emit(self._current_zoom + 1)


    def set_presets_enabled(self, enabled: bool):
        """Блокировать/разблокировать кнопки пресетов (при активном карандаше)."""
        for btn in self.preset_buttons.values():
            btn.setEnabled(enabled)

    def show_presets(self, visible: bool):
        self.presets_panel.setVisible(visible)

    def set_aspect_preset(self, key: str):
        """Синхронизировать активную кнопку пресета без эмита сигнала."""
        btn = self.preset_buttons.get(key)
        if btn is None:
            return
        btn.blockSignals(True)
        btn.setChecked(True)
        btn.blockSignals(False)

    def set_zoom(self, n: int):
        """Установить уровень зума для отображения (1..5)."""
        self._current_zoom = max(0, min(4, int(n)))
        self.lbl_zoom.setText(f"x{self._current_zoom}")
        self._update_zoom_buttons()

    def set_zoom_enabled(self, enabled: bool):
        """Включить/выключить кнопки зума. Для пресета original — выключено."""
        self._zoom_enabled = bool(enabled)
        self._update_zoom_buttons()

    def _update_zoom_buttons(self):
        # Зум кликабелен только при активном карандаше (метка редактируется)
        marker_active = self.btn_marker.isChecked() if hasattr(self, "btn_marker") else False
        zoom_clickable = self._zoom_enabled and marker_active
        self.btn_zoom_minus.setEnabled(zoom_clickable and self._current_zoom > 0)
        self.btn_zoom_plus.setEnabled(zoom_clickable and self._current_zoom < 4)
        if hasattr(self, "btn_marker"):
            can_shift = self._zoom_enabled
            self.btn_marker.setEnabled(can_shift)
            if not can_shift and self.btn_marker.isChecked():
                self.set_marker_mode(False)
                self.marker_mode_toggled.emit(False)
