# src/pik2video/gui/editor/panels/drop_zone.py
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from .file_tile import FileTile

logger = logging.getLogger(__name__)

BG_NORMAL = "#2a2a2a"
BG_HOVER = "#3d3d3d"
BORDER_NORMAL = "#555"
BORDER_HOVER = "#7a7a7a"

class DropZone(QFrame):
    file_dropped = Signal(str)
    delete_requested = Signal()
    clicked = Signal()

    def __init__(self, icon: str, label: str, extensions: set,
                 with_delete_button: bool = False, parent=None):
        super().__init__(parent)
        self._extensions = extensions
        self._is_hovered = False
        self._has_file = False
        self._is_active = False
        self._is_dimmed = False
        self._file_tile = None

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(6, 6, 6, 6)
        self._root_layout.setSpacing(4)

        self._placeholder_widget = QWidget()
        placeholder_layout = QVBoxLayout(self._placeholder_widget)
        placeholder_layout.setContentsMargins(0, 0, 0, 0)
        placeholder_layout.setSpacing(4)
        placeholder_layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel(icon)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._icon_label.setStyleSheet("font-size: 28px; background: transparent; border: none;")

        self._text_label = QLabel(label)
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._text_label.setWordWrap(True)
        self._text_label.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")

        placeholder_layout.addWidget(self._icon_label)
        placeholder_layout.addWidget(self._text_label)

        # Заглушка центрируется, когда файла нет
        self._root_layout.addWidget(self._placeholder_widget, stretch=0, alignment=Qt.AlignCenter)
        # Растяжка, чтобы файл прижимался к верху (как в списке видео)
        self._root_layout.addStretch(1)

        self._apply_style()

    def _apply_style(self):
        if not self._has_file:
            bg = BG_NORMAL
            border = BORDER_NORMAL
        elif self._is_active:
            bg = "#3a3a3a"
            border = "#8a6f2a"
        elif self._is_dimmed:
            bg = "#1a1a1a"
            border = "#2a2a2a"
        elif self._is_hovered:
            bg = BG_HOVER
            border = BORDER_HOVER
        else:
            bg = BG_NORMAL
            border = BORDER_NORMAL

        self.setStyleSheet(f"""
            DropZone {{
                background-color: {bg};
                border: 2px dashed {border};
                border-radius: 6px;
            }}
        """)

    def _set_hovered(self, value: bool):
        if self._is_hovered != value:
            self._is_hovered = value
            self._apply_style()

    def set_active(self, active: bool):
        if self._is_active != active:
            self._is_active = active
            self._apply_style()
            if self._file_tile is not None:
                self._file_tile.set_active(active)

    def set_dimmed(self, dimmed: bool):
        if self._is_dimmed != dimmed:
            self._is_dimmed = dimmed
            self._apply_style()
            if self._file_tile is not None:
                self._file_tile.set_dimmed(dimmed)

    def show_audio(self, path: str):
        self._has_file = True
        self._placeholder_widget.hide()
        
        if self._file_tile is not None:
            self._file_tile.hide()
            self._file_tile.deleteLater()
            self._file_tile = None

        self._file_tile = FileTile(path, is_active=self._is_active)
        self._file_tile.set_dimmed(self._is_dimmed)
        self._file_tile.clicked.connect(self.clicked.emit)
        self._file_tile.deleted.connect(self.delete_requested.emit)
        
        # Вставляем перед растяжкой (растягивается по ширине, прижимается к верху)
        self._root_layout.insertWidget(self._root_layout.count() - 1, self._file_tile)
        
        self._apply_style()

    def show_empty(self, icon: str, label: str):
        self._has_file = False
        if self._file_tile is not None:
            self._file_tile.hide()
            self._file_tile.deleteLater()
            self._file_tile = None
        self._placeholder_widget.show()
        self._icon_label.setText(icon)
        self._text_label.setText(label)
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def _is_valid_path(self, path: str) -> bool:
        if not path:
            return False
        return Path(path).suffix.lower() in self._extensions

    def _first_local_path(self, event) -> str:
        mime = event.mimeData()
        if not mime.hasUrls():
            return ""
        urls = mime.urls()
        if not urls:
            return ""
        return urls[0].toLocalFile()

    def dragEnterEvent(self, event):
        path = self._first_local_path(event)
        if self._is_valid_path(path):
            event.acceptProposedAction()
            self._set_hovered(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        path = self._first_local_path(event)
        if self._is_valid_path(path):
            event.acceptProposedAction()
            self._set_hovered(True)
        else:
            event.ignore()
            self._set_hovered(False)

    def dragLeaveEvent(self, event):
        self._set_hovered(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        path = self._first_local_path(event)
        self._set_hovered(False)
        if not self._is_valid_path(path):
            event.ignore()
            return
        event.acceptProposedAction()
        logger.info(f"Файл принят в зону: {path}")
        self.file_dropped.emit(path)
