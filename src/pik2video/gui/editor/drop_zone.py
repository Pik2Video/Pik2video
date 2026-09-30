# src/pik2video/gui/editor/drop_zone.py
"""
Drop-зона для приёма файлов drag-and-drop.

Отвечает только за:
- проверку расширения по белому списку
- визуальную подсветку при наведении правильного файла
- публикацию сигнала при успешном drop

Не знает:
- что делать с файлом после drop
- про плеер, EditorState
"""

import logging
import shutil
import subprocess
from pathlib import Path

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QFileIconProvider, QPushButton, QWidget
from PySide6.QtCore import Qt, Signal, QFileInfo
from PySide6.QtGui import QPixmap

logger = logging.getLogger(__name__)


# Цвета
BG_NORMAL = "#2a2a2a"
BG_HOVER = "#3d3d3d"
BORDER_NORMAL = "#555"
BORDER_HOVER = "#7a7a7a"

# Размер иконки файла в пикселях
FILE_ICON_SIZE = 60

# Отступ от начала, на котором берём кадр (сек). Первый кадр часто чёрный.
THUMBNAIL_SEEK = 1.0

# Путь к ffmpeg
FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
class DropZone(QFrame):
    """Зона приёма одного типа файлов. Опционально — с кнопкой удаления внизу."""

    file_dropped = Signal(str)
    delete_requested = Signal()

    def __init__(self, icon: str, label: str, extensions: set,
                 with_delete_button: bool = False, parent=None):
        super().__init__(parent)
        self._extensions = extensions
        self._is_hovered = False
        self._has_file = False

        self.setAcceptDrops(True)
        self.setFrameShape(QFrame.NoFrame)

        # ── Layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(6, 6, 6, 6)
        root.setSpacing(4)

        # ── Контент (иконка + подпись) ──
        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(4)
        content_layout.setAlignment(Qt.AlignCenter)

        self._icon_label = QLabel(icon)
        self._icon_label.setAlignment(Qt.AlignCenter)
        self._icon_label.setStyleSheet(
            "font-size: 28px; background: transparent; border: none;"
        )

        self._text_label = QLabel(label)
        self._text_label.setAlignment(Qt.AlignCenter)
        self._text_label.setWordWrap(True)
        self._text_label.setStyleSheet(
            "color: #888; font-size: 11px; background: transparent; border: none;"
        )

        content_layout.addWidget(self._icon_label)
        content_layout.addWidget(self._text_label)

        root.addWidget(content, stretch=1)

        # ── Опциональная кнопка удаления ──
        self._btn_delete = None
        if with_delete_button:
            self._btn_delete = QPushButton("удалить")
            self._btn_delete.setFixedHeight(24)
            self._btn_delete.setToolTip("Удалить файл")
            self._btn_delete.clicked.connect(self.delete_requested.emit)
            root.addWidget(self._btn_delete, stretch=0)
            self._update_delete_button()

        self._apply_style()

    # ── Стиль ──

    def _apply_style(self):
        if self._is_hovered:
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

    def _update_delete_button(self):
        if self._btn_delete is None:
            return

        self._btn_delete.setEnabled(self._has_file)

        if self._has_file:
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

    # ── Логика ──

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

    # ── События ──

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
        logger.info(f"Файл принят в {self.__class__.__name__}: {path}")
        self.file_dropped.emit(path)

    # ── Внешний вид после загрузки ──

    def show_video(self, path: str):
        """Показать thumbnail видео + имя файла."""
        pixmap = self._extract_video_thumbnail(path, FILE_ICON_SIZE * 2)

        if not pixmap.isNull():
            scaled = pixmap.scaled(
                FILE_ICON_SIZE, FILE_ICON_SIZE,
                Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
            self._icon_label.setPixmap(scaled)
        else:
            self._show_system_icon(path)

        self._text_label.setText(Path(path).name)
        self._text_label.setStyleSheet(
            "color: #a0c0ff; font-size: 10px; background: transparent; border: none;"
        )
        self._has_file = True
        self._update_delete_button()

    def show_audio(self, path: str):
        """Показать системную иконку аудио + имя файла."""
        self._show_system_icon(path)
        self._text_label.setText(Path(path).name)
        self._text_label.setStyleSheet(
            "color: #a0c0ff; font-size: 10px; background: transparent; border: none;"
        )
        self._has_file = True
        self._update_delete_button()

    def _show_system_icon(self, path: str):
        provider = QFileIconProvider()
        icon = provider.icon(QFileInfo(path))
        pixmap = icon.pixmap(FILE_ICON_SIZE, FILE_ICON_SIZE)

        if not pixmap.isNull():
            self._icon_label.setPixmap(pixmap)
        else:
            self._icon_label.clear()
            self._icon_label.setText("📄")

    def _extract_video_thumbnail(self, path: str, size: int) -> QPixmap:
        try:
            result = subprocess.run(
                [
                    FFMPEG_BIN,
                    "-loglevel", "quiet",
                    "-ss", str(THUMBNAIL_SEEK),
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

    def show_empty(self, icon: str, label: str):
        """Вернуть зону в пустое состояние."""
        self._icon_label.clear()
        self._icon_label.setText(icon)
        self._text_label.setText(label)
        self._text_label.setStyleSheet(
            "color: #888; font-size: 11px; background: transparent; border: none;"
        )
        self._has_file = False
        self._update_delete_button()