# src/pik2video/gui/editor/panels/file_tile.py
import logging
from pathlib import Path

from PySide6.QtCore import QFileInfo, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFileIconProvider, QFrame, QLabel, QPushButton, QVBoxLayout

logger = logging.getLogger(__name__)

BG_NORMAL = "#2a2a2a"
BG_ACTIVE = "#4a4a4a"
BORDER_NORMAL = "#555"
BORDER_ACTIVE = "#8a6f2a"
BG_DIMMED = "#1a1a1a"
BORDER_DIMMED = "#333"

ITEM_ICON_SIZE = 40
ITEM_HEIGHT = 68

class FileTile(QFrame):
    """Универсальная плитка файла: иконка + имя + кнопка удаления."""
    clicked = Signal()
    deleted = Signal()

    def __init__(self, path: str, is_active: bool = False, parent=None):
        super().__init__(parent)
        self._path = path
        self._is_active = is_active
        self._is_dimmed = False

        self.setFixedHeight(ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFixedHeight(ITEM_ICON_SIZE)
        self._icon_label.setStyleSheet("background: transparent; border: none;")

        self._show_system_icon()

        self._name_label = QLabel(self._short_name(path))
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet("color: #ccc; font-size: 9px; background: transparent; border: none;")
        self._name_label.setToolTip(str(path))

        layout.addWidget(self._icon_label)
        layout.addWidget(self._name_label)

        self._delete_btn = QPushButton("🗑️", self)
        self._delete_btn.setFixedSize(18, 18)
        self._delete_btn.setCursor(Qt.PointingHandCursor)
        self._delete_btn.setFocusPolicy(Qt.NoFocus)
        self._delete_btn.setStyleSheet("""
            QPushButton {
                background: rgba(0, 0, 0, 80);
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 10px;
                padding: 0px;
            }
            QPushButton:hover {
                background: rgba(200, 50, 50, 150);
                border: 1px solid rgba(255, 80, 80, 200);
            }
        """)
        self._delete_btn.clicked.connect(self.deleted.emit)
        self._delete_btn.setVisible(is_active)

        self._apply_style()

    def _short_name(self, path: str) -> str:
        name = Path(path).name
        if len(name) > 14:
            name = name[:11] + "..."
        return name

    def _show_system_icon(self):
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(self._path))
        pixmap = icon.pixmap(ITEM_ICON_SIZE, ITEM_ICON_SIZE)
        if not pixmap.isNull():
            self._icon_label.setPixmap(pixmap)

    def _position_delete_btn(self):
        if self._delete_btn is not None:
            self._delete_btn.move(self.width() - 20, 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_delete_btn()

    def _apply_style(self):
        if self._is_active:
            bg, border = BG_ACTIVE, BORDER_ACTIVE
        elif self._is_dimmed:
            bg, border = BG_DIMMED, BORDER_DIMMED
        else:
            bg, border = BG_NORMAL, BORDER_NORMAL

        self.setStyleSheet(f"""
            FileTile {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
        """)

    def set_active(self, active: bool):
        self._is_active = active
        self._apply_style()
        if self._delete_btn is not None:
            self._delete_btn.setVisible(self._is_active and not self._is_dimmed)
            if self._is_active and not self._is_dimmed:
                self._position_delete_btn()
                self._delete_btn.raise_()

    def set_dimmed(self, dimmed: bool):
        self._is_dimmed = dimmed
        self._apply_style()
        if self._delete_btn is not None:
            self._delete_btn.setVisible(self._is_active and not self._is_dimmed)
            if self._is_active and not self._is_dimmed:
                self._position_delete_btn()
                self._delete_btn.raise_()

    def set_thumbnail(self, pixmap: QPixmap):
        if pixmap is None or pixmap.isNull():
            return
        scaled = pixmap.scaled(ITEM_ICON_SIZE, ITEM_ICON_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._icon_label.setPixmap(scaled)

    def get_path(self) -> str:
        return self._path

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
