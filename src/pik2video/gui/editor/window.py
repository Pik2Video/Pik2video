# src/pik2video/gui/editor/window.py
"""
Окно редактора видео.

Каркас разметки из пяти зон:
1. Верхняя полоска — кнопки
2. Панель функций — левая колонка
3. Нижняя панель — Готово / Удалить / Экспорт
4. Зона загрузки файлов — правая колонка
5. Мультиплеер — центр
"""

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QLabel, QSizePolicy, QApplication, QPushButton,
    QFileDialog, QMessageBox
)

from PySide6.QtCore import Qt, QPoint, QUrl, Signal
from PySide6.QtGui import QCloseEvent


from .state import EditorState
from .drop_zone import DropZone
from .video_files_panel import VideoFilesPanel
from .player import PlayerWidget
from .timeline import TimelineWidget
from .tools_panel import ToolsPanel
from .export_dialog import ExportDialog
from .frame_preview import FramePreview

logger = logging.getLogger(__name__)

# Зазор между зонами в пикселях
GAP = 4

# Размеры зон
TOP_BAR_HEIGHT = 32

TOOLS_PANEL_WIDTH = 200

DROP_AREA_WIDTH = 108
DROP_VIDEO_RATIO = 2   # верхняя часть — 2/3
DROP_AUDIO_RATIO = 1   # нижняя часть — 1/3

BOTTOM_PANEL_HEIGHT = 44
EXPORT_NAME_WIDTH = 130

# Доля экрана, которую занимает окно при старте
WINDOW_SCREEN_RATIO = 0.88

# Разрешённые расширения
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac"}


class Zone(QFrame):
    """Отладочный блок зоны — рамка с подписью по центру."""

    def __init__(self, title: str, color: str = "#2a2a2a", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border: 1px solid #444;
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        label.setWordWrap(True)
        layout.addWidget(label)

class _DimOverlayWindow(QWidget):
    """Top-level затемнение поверх редактора (кроме топбара). Клик — сигнал."""

    clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

    def paintEvent(self, event):
        from PySide6.QtGui import QPainter, QColor
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 140))

    def mousePressEvent(self, event):
        self.clicked.emit()


class _RecordMenuWindow(QWidget):
    """Top-level окно с кнопками записи."""

    record_video_clicked = Signal()
    record_screen_clicked = Signal()
    record_audio_clicked = Signal()

    def __init__(self):
        super().__init__(
            None,
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                padding: 4px 12px;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """

        self.btn_video = QPushButton("запись видео")
        self.btn_video.setFixedHeight(26)
        self.btn_video.setStyleSheet(btn_style)
        self.btn_video.clicked.connect(self.record_video_clicked.emit)

        self.btn_screen = QPushButton("скрин запись")
        self.btn_screen.setFixedHeight(26)
        self.btn_screen.setStyleSheet(btn_style)
        self.btn_screen.clicked.connect(self.record_screen_clicked.emit)

        self.btn_audio = QPushButton("запись звука")
        self.btn_audio.setFixedHeight(26)
        self.btn_audio.setStyleSheet(btn_style)
        self.btn_audio.clicked.connect(self.record_audio_clicked.emit)

        layout.addWidget(self.btn_video)
        layout.addWidget(self.btn_screen)
        layout.addWidget(self.btn_audio)


class EditorWindow(QMainWindow):
    record_video_requested = Signal()
    record_screen_requested = Signal()
    record_audio_requested = Signal()
    closed = Signal()

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.state = EditorState(self)

        from .export_service import ExportService
        self.export_service = ExportService(self)
        self.export_service.export_started.connect(self._on_export_started)
        self.export_service.export_progress.connect(self._on_export_progress)
        self.export_service.export_finished.connect(self._on_export_finished)

        self._export_dialog = None
        self._frame_preview = FramePreview()

        # Top-level окна для меню записи
        self._dim_window = _DimOverlayWindow()
        self._dim_window.clicked.connect(self._close_record_menu)

        self._menu_window = _RecordMenuWindow()
        self._menu_window.record_video_clicked.connect(self._on_record_video)
        self._menu_window.record_screen_clicked.connect(self._on_record_screen)
        self._menu_window.record_audio_clicked.connect(self._on_record_audio)

        self.setWindowTitle("Редактор")
        self.setMinimumSize(1100, 700)

        self._apply_adaptive_size()
        self._build_ui()

    def _apply_adaptive_size(self):
        """Подгоняет стартовый размер окна под экран: 80% от доступной области."""
        screen = QApplication.primaryScreen()
        if screen is None:
            return

        available = screen.availableGeometry()

        width = int(available.width() * WINDOW_SCREEN_RATIO)
        height = int(available.height() * WINDOW_SCREEN_RATIO)

        # Не меньше минимума
        width = max(width, 1100)
        height = max(height, 700)

        # Не больше доступной области
        width = min(width, available.width())
        height = min(height, available.height())

        self.resize(width, height)



    def _build_top_bar(self) -> QWidget:
        """Верхняя полоска: [⚙️] слева, [⚫ Запись] справа."""
        bar = QWidget()
        bar.setFixedHeight(TOP_BAR_HEIGHT)
        bar.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        btn_toolbar_style = """
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

        self.btn_tools = QPushButton("🛠️")
        self.btn_tools.setFixedSize(28, 24)
        self.btn_tools.setCheckable(True)
        self.btn_tools.setChecked(True)
        self.btn_tools.setStyleSheet(btn_toolbar_style)
        self.btn_tools.clicked.connect(self._on_tools_clicked)
        layout.addWidget(self.btn_tools)

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(28, 24)
        self.btn_settings.setCheckable(True)
        self.btn_settings.setStyleSheet(btn_toolbar_style)
        self.btn_settings.clicked.connect(self._on_settings_clicked)
        layout.addWidget(self.btn_settings)


        layout.addStretch()

        self.btn_record = QPushButton(" ⚫  Запись ")
        self.btn_record.setFixedHeight(24)
        self.btn_record.setCheckable(True)
        self.btn_record.setStyleSheet("""
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
        self.btn_record.toggled.connect(self._on_record_toggled)
        layout.addWidget(self.btn_record)

        return bar

    

    def _build_drop_area(self) -> QWidget:
        """Зона 4: колонка из двух областей — видео (2/3) и аудио (1/3)."""
        container = QWidget()
        container.setFixedWidth(DROP_AREA_WIDTH)
        container.setStyleSheet("background: transparent; border: none;")

        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(GAP)

        # ── Видео-область (список файлов) ──
        self.drop_video = VideoFilesPanel(extensions=VIDEO_EXTENSIONS)
        self.drop_video.file_dropped.connect(self._on_video_dropped)
        self.drop_video.file_selected.connect(self._on_video_selected)
        self.drop_video.delete_requested.connect(self._on_video_delete_requested)
        layout.addWidget(self.drop_video, stretch=DROP_VIDEO_RATIO)

        # ── Аудио-область ──
        self.drop_audio = DropZone(
            icon="🎵",
            label="mp3",
            extensions=AUDIO_EXTENSIONS,
            with_delete_button=True,
        )
        self.drop_audio.file_dropped.connect(self._on_audio_dropped)
        self.drop_audio.delete_requested.connect(self._on_audio_delete_requested)
        layout.addWidget(self.drop_audio, stretch=DROP_AUDIO_RATIO)

        return container


    def _build_bottom_panel(self) -> QWidget:
        """Нижняя панель: приподнятое поле экспорта слева, кнопка «Очистить» справа."""
        panel = QWidget()
        panel.setFixedHeight(BOTTOM_PANEL_HEIGHT)
        panel.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(6, 2, 0, 2)
        layout.setSpacing(8)

        # ── Приподнятое поле: путь + кнопка Экспорт ──
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


        from PySide6.QtWidgets import QLineEdit

        # ── Общий фрейм: имя + расширение ──
        self.export_name_frame = QFrame()
        self.export_name_frame.setFixedWidth(EXPORT_NAME_WIDTH)
        self.export_name_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #555;
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
        self.export_name_input.textChanged.connect(self.state.set_export_filename)

        self.export_ext_label = QLabel("")
        self.export_ext_label.setStyleSheet(
            "color: #666; font-size: 11px; "
            "background: transparent; border: none;"
        )

        name_layout.addWidget(self.export_name_input, stretch=1)
        name_layout.addWidget(self.export_ext_label, stretch=0)

        self.export_path_value = QPushButton("")
        self.export_path_value.setFlat(True)
        self.export_path_value.setCursor(Qt.PointingHandCursor)
        self.export_path_value.clicked.connect(self._on_export_path_clicked)

        self.btn_export = QPushButton("Экспорт")

        self.btn_export.setFixedHeight(24)
        self.btn_export.setFixedWidth(100)
        self.btn_export.clicked.connect(self._on_export_clicked)

        self.btn_export.setStyleSheet("""
            QPushButton {
                background-color: #2a7a2a;
                border: 1px solid #3a9a3a;
                border-radius: 4px;
                color: white;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a9a3a;
            }
            QPushButton:pressed {
                background-color: #1a5a1a;
            }
            QPushButton:disabled {
                background-color: #2a2a2a;
                border: 1px solid #444;
                color: #555;
            }
        """)

        export_layout.addWidget(self.export_name_frame, stretch=0)
        export_layout.addStretch(1)
        export_layout.addWidget(self.export_path_value, stretch=0)
        export_layout.addSpacing(12)
        export_layout.addWidget(self.btn_export, stretch=0)

        layout.addWidget(self.export_block, stretch=1)

        # ── Обёртка для «Очистить» в стиле drop-зоны ──
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
        self.btn_clear.clicked.connect(self._on_clear_clicked)

        clear_layout.addStretch()
        clear_layout.addWidget(self.btn_clear)

        layout.addWidget(self.clear_frame, stretch=0)

        self._update_clear_button()

        self._sync_export_path_field()

        return panel


    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #1e1e1e;")
        self.setCentralWidget(central)

        # ── Корневой вертикальный layout ──
        root = QVBoxLayout(central)
        root.setContentsMargins(GAP, GAP, GAP, GAP)
        root.setSpacing(GAP)

        # ── 1. Верхняя полоска ──
        self.top_bar = self._build_top_bar()
        root.addWidget(self.top_bar)

        # ── Середина: горизонтальный layout ──
        middle = QHBoxLayout()
        middle.setContentsMargins(0, 0, 0, 0)
        middle.setSpacing(GAP)

        # 2. Панель функций (слева, во всю высоту)
        self.tools_panel = ToolsPanel(self.state, self.controller)
        self.tools_panel.setFixedWidth(TOOLS_PANEL_WIDTH)
        middle.addWidget(self.tools_panel)

        # Правая сторона: вертикальный layout
        right_side = QVBoxLayout()
        right_side.setContentsMargins(0, 0, 0, 0)
        right_side.setSpacing(GAP)

        # Верхняя часть правой стороны: 5 + 4
        upper = QHBoxLayout()
        upper.setContentsMargins(0, 0, 0, 0)
        upper.setSpacing(GAP)

        # 5. Мультиплеер (плеер + таймлайн)
        mx_container = QWidget()
        mx_container.setStyleSheet("background: transparent; border: none;")
        mx_layout = QVBoxLayout(mx_container)
        mx_layout.setContentsMargins(0, 0, 0, 0)
        mx_layout.setSpacing(GAP)

        self.multiplexer = PlayerWidget()
        mx_layout.addWidget(self.multiplexer, stretch=1)

        self.timeline = TimelineWidget()
        mx_layout.addWidget(self.timeline, stretch=0)

        upper.addWidget(mx_container, stretch=1)

        # 4. Зона загрузки файлов (фиксированная ширина)
        self.drop_area = self._build_drop_area()
        upper.addWidget(self.drop_area, stretch=0)

        right_side.addLayout(upper, stretch=1)

        # 3. Нижняя панель (под зоной 4, но не под зоной 2)
        self.bottom_panel = self._build_bottom_panel()
        right_side.addWidget(self.bottom_panel, stretch=0)

        middle.addLayout(right_side, stretch=1)

        root.addLayout(middle, stretch=1)

        # ── Связи между EditorState и виджетами ──
        self.state.videos_changed.connect(self._on_videos_changed)
        self.state.active_video_changed.connect(self._on_active_video_changed)
        self.state.video_loaded.connect(self._on_video_loaded)
        self.state.video_unloaded.connect(self._on_video_unloaded)
        self.state.position_changed.connect(self.timeline.set_position)
        self.state.trim_changed.connect(self.timeline.set_trim)

        # ── Плеер → EditorState ──
        self.multiplexer.position_changed.connect(self.state.set_position)
        self.multiplexer.duration_changed.connect(self._on_duration_changed)

        self.state.trim_changed.connect(self.multiplexer.set_trim_range)

        self.timeline.seek_requested.connect(self.multiplexer.set_position)
        self.timeline.trim_changed.connect(self.state.set_trim)

        self.timeline.marker_drag_started.connect(self._on_marker_drag_started)
        self.timeline.marker_dragged.connect(self._on_marker_dragged)
        self.timeline.marker_drag_finished.connect(self._on_marker_drag_finished)

        self.btn_export.setEnabled(self.state.has_videos())

        

    def _on_video_dropped(self, path: str):
        """Файл принят в списке видео."""
        logger.info(f"Видео принято: {path}")
        self.state.add_video_file(path, duration=0.0)

    def _on_video_selected(self, index: int):
        """Пользователь кликнул по файлу в списке."""
        self.state.set_active_video(index)

    def _on_audio_dropped(self, path: str):
        """Файл принят в зоне аудио."""
        logger.info(f"Аудио принято: {path}")
        self.state.set_audio_file(path, duration=0.0)
        self.drop_audio.show_audio(path)
        self._update_clear_button()

    def _on_video_delete_requested(self):
        """Удаление активного видео с подтверждением."""
        from src.pik2video.gui.common.dialogs import confirm

        if not self.state.has_videos():
            return

        if not confirm(self, "Удалить активный видеофайл?\n\nВсе настройки для него будут потеряны."):
            return

        path = self.state.get_video_path()
        self.state.remove_active_video()

        self._delete_draft_if_needed(path)

    def _on_audio_delete_requested(self):
        """Удаление аудио с подтверждением."""
        from src.pik2video.gui.common.dialogs import confirm

        if not self.state.has_audio():
            return

        if not confirm(self, "Удалить аудиофайл?"):
            return

        self.state.clear_audio()
        self._update_clear_button()

    def _update_clear_button(self):
        """Обновить вид кнопки «Очистить»: активна, если есть файлы."""
        has_files = self.state.has_videos() or self.state.has_audio()
        self.btn_clear.setEnabled(has_files)

        if has_files:
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

    def _on_clear_clicked(self):
        """Сбросить загруженные файлы с подтверждением."""
        from src.pik2video.gui.common.dialogs import confirm

        if not (self.state.has_videos() or self.state.has_audio()):
            return

        if not confirm(self, "Очистить редактор?\n\nВсе загруженные файлы будут удалены."):
            return

        logger.info("Очистка редактора")

        for path in self.state.get_video_files():
            self._delete_draft_if_needed(path)

        self.state.clear_video()
        self.state.clear_audio()

        self.drop_audio.show_empty(icon="🎵", label="mp3")
    def _delete_draft_if_needed(self, path: str):
        """Удалить файл с диска, если он лежит в папке черновиков."""
        if not path or not self.controller:
            return
        try:
            drafts_dir = self.controller.get_drafts_dir()
            file_path = Path(path)
            if file_path.parent == drafts_dir and file_path.exists():
                file_path.unlink()
                logger.info(f"Черновик удалён: {path}")
        except Exception as e:
            logger.warning(f"Не удалось удалить черновик {path}: {e}")


    def _on_export_clicked(self):
        """Запустить экспорт через FFmpeg с показом прогресса."""
        if not self.state.has_videos():
            QMessageBox.warning(self, "Экспорт", "Нет активного видеофайла.")
            return

        if self.export_service.is_running():
            QMessageBox.information(self, "Экспорт", "Экспорт уже идёт.")
            return

        self.btn_export.setEnabled(False)
        self.btn_export.setText("Экспорт...")

        self._export_dialog = ExportDialog(self)
        self._export_dialog.cancel_requested.connect(self._on_export_cancel)
        self._export_dialog.show()

        self.export_service.start_export(self.state)

    def _on_export_cancel(self):
        """Пользователь нажал «Отмена» в диалоге."""
        if self._export_dialog:
            self._export_dialog.set_cancelling()
        self.export_service.cancel()

    def _on_export_started(self):
        logger.info("Экспорт: старт")

    def _on_export_progress(self, percent: int):
        if self._export_dialog:
            self._export_dialog.set_progress(percent)

    def _on_export_finished(self, success: bool, message: str):
        """Экспорт завершён."""
        self.btn_export.setEnabled(True)
        self.btn_export.setText("Экспорт")

        if not self._export_dialog:
            return

        if success:
            self._export_dialog.show_success(message)
        else:
            self._export_dialog.show_error(message)


    def _on_video_loaded(self, path: str):
        """EditorState сообщил, что активный файл сменился → отдаём плееру."""
        self.multiplexer.load_video(path)
        self._sync_export_name_field()

    def _on_video_unloaded(self):
        """EditorState сообщил, что список пуст → плеер в placeholder."""
        self.multiplexer.unload_video()
        self.timeline.set_duration(0.0)
        self.timeline.set_position(0.0)
        self.timeline.set_trim(0.0, 0.0)
        self._sync_export_name_field()

    def _on_duration_changed(self, seconds: float):
        """Плеер сообщил длительность → обновляем таймлайн и EditorState."""
        self.state.update_active_duration(seconds)
        self.timeline.set_duration(seconds)

    def _on_videos_changed(self):
        """EditorState сообщил, что состав списка изменился."""
        self.drop_video.set_files(
            self.state.get_video_files(),
            self.state.get_active_index(),
        )
        self.btn_export.setEnabled(self.state.has_videos())
        self._update_clear_button()

    def _sync_export_name_field(self):
        """Обновляет поле имени и расширение по активному файлу."""
        has_file = self.state.has_videos()

        if has_file:
            path = self.state.get_video_path()
            from pathlib import Path
            stem = Path(path).stem
            ext = Path(path).suffix.upper()

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
            self.state.set_export_filename(stem)

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
            self.state.set_export_filename("")

            self.export_ext_label.setText("")

    def _sync_export_path_field(self):
        """Обновить отображение пути экспорта."""
        path = self.state.get_export_path()
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

    def _on_export_path_clicked(self):
        """Открыть диалог выбора папки экспорта."""
        current = self.state.get_export_path() or str(Path.home() / "Desktop")

        folder = QFileDialog.getExistingDirectory(
            self,
            "Выберите папку для экспорта",
            current,
        )
        if not folder:
            return

        self.state.set_export_path(folder)
        self._sync_export_path_field()
        logger.info(f"Путь экспорта выбран: {folder}")

    

    def _on_active_video_changed(self, path: str):
        """EditorState сообщил, что активный файл сменился."""
        self.drop_video.set_active(self.state.get_active_index())
        self._sync_export_name_field()

    def load_file(self, path: str):
        """Загрузить файл в редактор извне."""
        logger.info(f"Редактор загружает файл: {path}")
        self.state.add_video_file(path, duration=0.0)

    def _on_marker_dragged(self, seconds: float, x_local: int):
        """Перетаскивание маркера — показать превью кадра."""
        pixmap = self.multiplexer.get_last_frame()
        if pixmap is None:
            return

        global_pos = self.timeline.mapToGlobal(QPoint(x_local, 0))
        self._frame_preview.show_frame(pixmap, global_pos.x(), global_pos.y())

    def _on_marker_drag_started(self):
        """Начало перетаскивания — включить кэш кадров."""
        self.multiplexer.set_keep_frames(True)

    def _on_marker_drag_finished(self):
        self._frame_preview.hide_preview()
        self.multiplexer.set_keep_frames(False)

    def _on_tools_clicked(self):
        self.tools_panel.show_tools()
        self.btn_tools.setChecked(True)
        self.btn_settings.setChecked(False)

    def _on_settings_clicked(self):
        self.tools_panel.show_settings()
        self.btn_settings.setChecked(True)
        self.btn_tools.setChecked(False)

    # ── Плавающее меню записи ──
    def _on_record_toggled(self, checked: bool):
        if checked:
            self._open_record_menu()
        else:
            self._close_record_menu()


    def _open_record_menu(self):
        """Показать затемнение и меню."""
        # Геометрия редактора на экране
        editor_top_left = self.mapToGlobal(QPoint(0, 0))
        top_bar_h = self.top_bar.height()

        # ── Затемнение: от низа топбара до низа редактора ──
        self._dim_window.setGeometry(
            editor_top_left.x(),
            editor_top_left.y() + top_bar_h,
            self.width(),
            self.height() - top_bar_h,
        )
        self._dim_window.show()

        # ── Меню: в одну линию с кнопкой «Запись», слева от неё ──
        self._menu_window.adjustSize()
        menu_w = self._menu_window.sizeHint().width()
        menu_h = self._menu_window.sizeHint().height()

        btn_global = self.btn_record.mapToGlobal(QPoint(0, 0))
        menu_x = btn_global.x() - menu_w - 4
        menu_y = btn_global.y() + (self.btn_record.height() - menu_h) // 2

        self._menu_window.move(menu_x, menu_y)
        self._menu_window.show()

        self.btn_settings.setEnabled(False)

    def _close_record_menu(self):
        """Скрыть затемнение и меню."""
        self._dim_window.hide()
        self._menu_window.hide()
        self.btn_settings.setEnabled(True)

        self.btn_record.blockSignals(True)
        self.btn_record.setChecked(False)
        self.btn_record.blockSignals(False)
    # ── Кнопки меню ──

    def _on_record_video(self):
        self._close_record_menu()
        self.record_video_requested.emit()

    def _on_record_screen(self):
        self._close_record_menu()
        self.record_screen_requested.emit()

    def _on_record_audio(self):
        self._close_record_menu()
        self.record_audio_requested.emit()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._menu_window.isVisible():
            self._close_record_menu()

    def moveEvent(self, event):
        super().moveEvent(event)
        if self._menu_window.isVisible():
            self._close_record_menu()

    def closeEvent(self, event: QCloseEvent):
        """Перед закрытием: остановить всё и удалить окно."""

        # Закрываем top-level окна
        try:
            self._dim_window.hide()
            self._dim_window.deleteLater()
        except Exception:
            pass
        try:
            self._menu_window.hide()
            self._menu_window.deleteLater()
        except Exception:
            pass

        # 1. Экспорт
        if self.export_service.is_running():
            if self._export_dialog and not self._export_dialog._is_done:
                from src.pik2video.gui.common.dialogs import confirm
                if not confirm(
                    self,
                    "Идёт экспорт видео.\n\nПрервать экспорт и закрыть редактор?"
                ):
                    event.ignore()
                    return
            self.export_service.cancel()

        # 2. Плеер
        try:
            self.multiplexer._player.stop()
            self.multiplexer._player.setSource(QUrl())
        except Exception as e:
            logger.warning(f"Не удалось остановить плеер: {e}")

        # 3. Всплывающие окна
        try:
            self.multiplexer._volume_control._popup.hide()
            self.multiplexer._volume_control._popup.deleteLater()
        except Exception:
            pass
        try:
            self._frame_preview.hide_preview()
            self._frame_preview.deleteLater()
        except Exception:
            pass

        logger.info("Редактор скрыт (не уничтожен)")
        self.closed.emit()
        super().closeEvent(event)

