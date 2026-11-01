# src/pik2video/gui/editor/panels/video_files_panel.py
import logging
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from .file_tile import FileTile

logger = logging.getLogger(__name__)

BG_NORMAL = "#2a2a2a"
BG_HOVER = "#3d3d3d"
BORDER_NORMAL = "#555"
BORDER_HOVER = "#7a7a7a"

class VideoFilesPanel(QFrame):
    file_dropped = Signal(str)
    file_selected = Signal(int)
    delete_requested = Signal()

    def __init__(self, extensions: set, thumbnail_loader=None, parent=None):
        super().__init__(parent)
        self._extensions = extensions
        self._thumbnail_loader = thumbnail_loader
        self._is_hovered = False
        self._is_active_zone = False
        self._is_dimmed = False

        if self._thumbnail_loader is not None:
            self._thumbnail_loader.thumbnail_ready.connect(self.on_thumbnail_ready)

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                background: #2a2a2a;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background: #555;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0;
            }
        """)

        self._list_container = QWidget()
        self._list_container.setStyleSheet("background: transparent; border: none;")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_container)

        self._placeholder = QLabel("📹\nвидео")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")

        root.addWidget(self._placeholder, stretch=1)
        root.addWidget(self._scroll, stretch=1)
        self._scroll.hide()

        self._items = []
        self._active_index = -1
        self._apply_style()

    def _apply_style(self):
        if not self._items:
            bg, border = BG_NORMAL, BORDER_NORMAL
        elif self._is_active_zone:
            bg, border = "#3a3a3a", "#8a6f2a"
        elif self._is_dimmed:
            bg, border = "#1a1a1a", "#2a2a2a"
        elif self._is_hovered:
            bg, border = BG_HOVER, BORDER_HOVER
        else:
            bg, border = BG_NORMAL, BORDER_NORMAL

        self.setStyleSheet(f"""
            VideoFilesPanel {{
                background-color: {bg};
                border: 2px dashed {border};
                border-radius: 6px;
            }}
        """)

    def _set_hovered(self, value: bool):
        if self._is_hovered != value:
            self._is_hovered = value
            self._apply_style()

    def set_files(self, files: list, active_index: int):
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()
        self._active_index = active_index

        if not files:
            self._placeholder.show()
            self._scroll.hide()
            self._apply_style()
            return

        self._placeholder.hide()
        self._scroll.show()

        for i, path in enumerate(files):
            item = FileTile(path, is_active=(i == active_index))
            item.set_dimmed(self._is_dimmed)
            item.clicked.connect(lambda idx=i: self.file_selected.emit(idx))
            item.deleted.connect(lambda idx=i: self._on_item_delete_requested(idx))
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
            self._items.append(item)
            if self._thumbnail_loader is not None:
                self._thumbnail_loader.request(path)

        self._apply_style()

    def _on_item_delete_requested(self, index: int):
        if index == self._active_index:
            self.delete_requested.emit()

    def set_active(self, active_index: int):
        self._active_index = active_index
        for i, item in enumerate(self._items):
            item.set_active(i == active_index)

    def set_active_zone(self, active: bool):
        if self._is_active_zone != active:
            self._is_active_zone = active
            self._apply_style()

    def set_dimmed(self, dimmed: bool):
        self._is_dimmed = dimmed
        self._apply_style()
        for item in self._items:
            item.set_dimmed(dimmed)
        if not dimmed:
            self.set_active(self._active_index)

    def on_thumbnail_ready(self, source_path: str):
        if self._thumbnail_loader is None:
            return
        pixmap = self._thumbnail_loader.get_cached_pixmap(source_path)
        if pixmap is None or pixmap.isNull():
            return
        for item in self._items:
            if item.get_path() == source_path:
                item.set_thumbnail(pixmap)
                break

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
        logger.info(f"Файл принят в список видео: {path}")
        self.file_dropped.emit(path)
