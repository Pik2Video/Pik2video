# src/pik2video/gui/editor/video_files_panel.py
"""
Панель списка видеофайлов в зоне загрузки.

Отвечает только за:
- приём drag-and-drop видео
- отображение списка файлов в столбик
- выделение активного файла
- публикацию сигналов при drop и клике

Не знает:
- что делать с файлом после drop
- про плеер и EditorState
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QWidget,
    QFileIconProvider, QPushButton
)

from PySide6.QtCore import Qt, Signal, QFileInfo
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)


BG_NORMAL = "#2a2a2a"
BG_HOVER = "#3d3d3d"
BG_ACTIVE = "#4a4a4a"
BORDER_NORMAL = "#555"
BORDER_HOVER = "#7a7a7a"
BORDER_ACTIVE = "#888"

ITEM_ICON_SIZE = 40
ITEM_HEIGHT = 68


class VideoFileItem(QFrame):
    """Один файл в списке: иконка + имя. Клик — активация."""

    clicked = Signal(int)

    def __init__(self, index: int, path: str, is_active: bool, parent=None):
        super().__init__(parent)
        self._index = index
        self._path = path
        self._is_active = is_active

        self.setFixedHeight(ITEM_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignCenter)

        # Иконка (превью первого кадра)
        self._icon_label = QLabel()
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setFixedHeight(ITEM_ICON_SIZE)
        self._icon_label.setStyleSheet("background: transparent; border: none;")

        pixmap = self._extract_thumbnail(path, ITEM_ICON_SIZE * 2)
        if pixmap.isNull():
            provider = QFileIconProvider()
            icon = provider.icon(QFileInfo(path))
            pixmap = icon.pixmap(ITEM_ICON_SIZE, ITEM_ICON_SIZE)
        else:
            pixmap = pixmap.scaled(
                ITEM_ICON_SIZE, ITEM_ICON_SIZE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

        if not pixmap.isNull():
            self._icon_label.setPixmap(pixmap)

        # Имя файла
        self._name_label = QLabel(self._short_name(path))
        self._name_label.setAlignment(Qt.AlignCenter)
        self._name_label.setWordWrap(True)
        self._name_label.setStyleSheet(
            "color: #ccc; font-size: 9px; background: transparent; border: none;"
        )
        self._name_label.setToolTip(str(path))

        layout.addWidget(self._icon_label)
        layout.addWidget(self._name_label)

        self._apply_style()

    # ── Стиль ──

    def _apply_style(self):
        if self._is_active:
            bg = BG_ACTIVE
            border = BORDER_ACTIVE
        else:
            bg = BG_NORMAL
            border = BORDER_NORMAL

        self.setStyleSheet(f"""
            VideoFileItem {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
        """)

    def set_active(self, active: bool):
        if self._is_active != active:
            self._is_active = active
            self._apply_style()

    # ── События ──

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._index)

    # ── Утилиты ──

    @staticmethod
    def _short_name(path: str) -> str:
        name = Path(path).name
        if len(name) > 14:
            name = name[:11] + "..."
        return name

    @staticmethod
    def _extract_thumbnail(path: str, size: int) -> QPixmap:
        import shutil
        import subprocess

        ffmpeg_bin = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

        try:
            result = subprocess.run(
                [
                    ffmpeg_bin,
                    "-loglevel", "quiet",
                    "-ss", "1.0",
                    "-i", path,
                    "-vframes", "1",
                    "-vf", f"scale={size}:{size}:force_original_aspect_ratio=decrease",
                    "-f", "image2pipe",
                    "-vcodec", "png",
                    "-",
                ],
                capture_output=True,
                timeout=5,
            )

            if result.returncode != 0 or not result.stdout:
                return QPixmap()
            pixmap = QPixmap()
            if not pixmap.loadFromData(result.stdout):
                return QPixmap()
            return pixmap
        except Exception:
            return QPixmap()


class VideoFilesPanel(QFrame):
    """Панель со списком видеофайлов + приём drag-and-drop."""

    file_dropped = Signal(str)
    file_selected = Signal(int)
    delete_requested = Signal()

    def __init__(self, extensions: set, parent=None):
        super().__init__(parent)
        self._extensions = extensions
        self._is_hovered = False

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        # ── Layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Область со списком
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

        # Placeholder (когда файлов нет)
        self._placeholder = QLabel("📹\nвидео")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet(
            "color: #888; font-size: 11px; background: transparent; border: none;"
        )

        root.addWidget(self._placeholder, stretch=1)
        root.addWidget(self._scroll, stretch=1)
        self._scroll.hide()

        # ── Кнопка «Удалить» ──
        self._btn_delete = QPushButton("удалить")
        self._btn_delete.setFixedHeight(24)
        self._btn_delete.setToolTip("Удалить активный файл")
        self._btn_delete.clicked.connect(self.delete_requested.emit)
        root.addWidget(self._btn_delete, stretch=0)

        self._items: list = []
        self._apply_style()
        self._update_delete_button()

    # ── Стиль ──

    def _apply_style(self):
        bg = BG_HOVER if self._is_hovered else BG_NORMAL
        border = BORDER_HOVER if self._is_hovered else BORDER_NORMAL

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

    # ── Публичный API ──

    def set_files(self, files: list, active_index: int):
        """Перестроить список файлов."""
        # Удаляем старые элементы
        for item in self._items:
            item.setParent(None)
            item.deleteLater()
        self._items.clear()

        if not files:
            self._placeholder.show()
            self._scroll.hide()
            self._update_delete_button()
            return

        self._placeholder.hide()
        self._scroll.show()

        for i, path in enumerate(files):
            item = VideoFileItem(i, path, is_active=(i == active_index))
            item.clicked.connect(self.file_selected.emit)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)
            self._items.append(item)

        self._update_delete_button()

    def _update_delete_button(self):
        """Включить/выключить кнопку удаления и обновить цвет."""
        enabled = len(self._items) > 0
        self._btn_delete.setEnabled(enabled)

        if enabled:
            self._btn_delete.setStyleSheet("""
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
            self._btn_delete.setStyleSheet("""
                QPushButton {
                    background-color: #2a2a2a;
                    border: 1px solid #444;
                    border-radius: 4px;
                    color: #666;
                    font-size: 10px;
                }
            """)

    def set_active(self, active_index: int):
        """Обновить подсветку активного элемента."""
        for i, item in enumerate(self._items):
            item.set_active(i == active_index)

    # ── Drag-and-drop ──

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