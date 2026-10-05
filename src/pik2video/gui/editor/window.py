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

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QVBoxLayout,
    QWidget,
)

from src.pik2video.gui.common.close_policy import (
    CloseAction,
    CloseContext,
    ClosePolicy,
    CloseRule,
    evaluate_close,
)
from src.pik2video.gui.common.dialogs import confirm

from .bottom_panel import BottomPanel
from .crop_mode import CropModeController
from .drop_area import DropArea
from .export_controller import ExportController
from .frame_preview import FramePreview
from .player import PlayerWidget
from .record_menu import RecordMenuController
from .state import EditorState
from .timeline import TimelineWidget
from .tools_panel import ToolsPanel
from .top_bar import TopBar

logger = logging.getLogger(__name__)

# Зазор между зонами в пикселях
GAP = 4

TOOLS_PANEL_WIDTH = 200

# Доля экрана, которую занимает окно при старте
WINDOW_SCREEN_RATIO = 0.88

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




class EditorWindow(QMainWindow):
    record_video_requested = Signal()
    record_screen_requested = Signal()
    record_audio_requested = Signal()
    closed = Signal()

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.state = EditorState(self)

        self._frame_preview = FramePreview()

        # ── Контроллеры (создаются после _build_ui) ──
        self.record_menu = None
        self.crop_mode = None


        self.setWindowTitle("Редактор")
        self.setMinimumSize(1100, 700)

        self._apply_adaptive_size()
        self._build_ui()

        # ── Контроллеры (после _build_ui — им нужен top_bar) ──
        self.record_menu = RecordMenuController(self)
        self.record_menu.record_video_requested.connect(self.record_video_requested.emit)
        self.record_menu.record_screen_requested.connect(self.record_screen_requested.emit)
        self.record_menu.record_audio_requested.connect(self.record_audio_requested.emit)

        self.crop_mode = CropModeController(self)
        self.export_controller = ExportController(self, self.state)
        self.bottom_panel.export_clicked.connect(self.export_controller.start)
        self.top_bar.record_toggled.connect(self.record_menu.toggle)

        # Восстанавливаем сохранённый список файлов
        self.state.load_persisted_files()

    
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


    def _build_ui(self):
        central = QWidget()
        central.setStyleSheet("background-color: #1e1e1e;")
        self.setCentralWidget(central)

        # ── Корневой вертикальный layout ──
        root = QVBoxLayout(central)
        root.setContentsMargins(GAP, GAP, GAP, GAP)
        root.setSpacing(GAP)

        # ── 1. Верхняя полоска ──
        self.top_bar = TopBar(tools_block_width=TOOLS_PANEL_WIDTH)
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

        self.drop_area = DropArea()
        self.drop_area.video_dropped.connect(self._on_video_dropped)
        self.drop_area.video_selected.connect(self._on_video_selected)
        self.drop_area.video_delete_requested.connect(self._on_video_delete_requested)
        self.drop_area.audio_dropped.connect(self._on_audio_dropped)
        self.drop_area.audio_delete_requested.connect(self._on_audio_delete_requested)
        upper.addWidget(self.drop_area, stretch=0)

        right_side.addLayout(upper, stretch=1)


        self.bottom_panel = BottomPanel()
        self.bottom_panel.clear_clicked.connect(self._on_clear_clicked)

        self.bottom_panel.export_path_clicked.connect(self._on_export_path_clicked)
        self.bottom_panel.export_name_changed.connect(self.state.set_export_filename)
        right_side.addWidget(self.bottom_panel, stretch=0)

        # Заполнить путь экспорта из состояния
        self._sync_export_path_field()
        self._sync_export_name_field()


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
        self.multiplexer.source_resolution_changed.connect(self.state.set_source_resolution)

        self.state.trim_changed.connect(self.multiplexer.set_trim_range)

        self.timeline.seek_requested.connect(self.multiplexer.set_position)
        self.timeline.trim_changed.connect(self.state.set_trim)

        self.timeline.marker_drag_started.connect(self._on_marker_drag_started)
        self.timeline.marker_dragged.connect(self._on_marker_dragged)
        self.timeline.marker_drag_finished.connect(self._on_marker_drag_finished)

        self.top_bar.tools_clicked.connect(self.tools_panel.show_tools)
        self.top_bar.settings_clicked.connect(self.tools_panel.show_settings)
        self.top_bar.preset_changed.connect(self.state.set_aspect_preset)
        self.top_bar.aspect_mode_changed.connect(self.state.set_aspect_mode)

        self.state.settings_changed.connect(self._sync_aspect_preset)
        self.state.settings_changed.connect(self._sync_aspect_mode)


        

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
        self.drop_area.show_audio(path)
        self.bottom_panel.set_clear_enabled(
            self.state.has_videos() or self.state.has_audio()
        )

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
        self.bottom_panel.set_clear_enabled(
            self.state.has_videos() or self.state.has_audio()
        )


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

        self.drop_area.show_audio_empty()

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

    def _on_video_loaded(self, path: str):
        """EditorState сообщил, что активный файл сменился → отдаём плееру."""
        self.multiplexer.load_video(path)
        self._sync_export_name_field()

        # Позиция кнопки зависит от раскладки мультиплеера —
        # даём Qt время пересчитать размеры
        if self.crop_mode is not None:
            QTimer.singleShot(50, self.crop_mode.show_button_if_needed)

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
        self.drop_area.set_video_files(
            self.state.get_video_files(),
            self.state.get_active_index(),
        )
        self.bottom_panel.set_export_enabled(self.state.has_videos())
        self.bottom_panel.set_clear_enabled(
            self.state.has_videos() or self.state.has_audio()
        )

        if self.crop_mode is not None:
            self.crop_mode.show_button_if_needed()

    def _sync_export_name_field(self):
        """Обновляет поле имени и расширение по активному файлу."""
        has_file = self.state.has_videos()

        if has_file:
            path = self.state.get_video_path()
            from pathlib import Path
            stem = Path(path).stem
            ext = Path(path).suffix.upper()

            self.bottom_panel.set_export_filename(stem, ext)
            self.state.set_export_filename(stem)
        else:
            self.bottom_panel.set_export_filename("", "")
            self.state.set_export_filename("")

    def _sync_export_path_field(self):
        """Обновить отображение пути экспорта."""
        path = self.state.get_export_path()
        self.bottom_panel.set_export_path(path)

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
        self.drop_area.set_video_active(self.state.get_active_index())
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


    # ── Плавающее меню записи ──
    def _sync_aspect_preset(self):
        """Передать текущий пресет в плеер."""
        preset = self.state.get_aspect_preset()
        self.multiplexer.set_aspect_preset(preset)

    def _sync_aspect_mode(self):
        """Передать текущий режим (crop/pad) в TopBar."""
        mode = self.state.get_aspect_mode()
        self.top_bar.set_aspect_mode(mode)

    def _pick_policy(self) -> ClosePolicy:
        """Выбрать политику закрытия по текущему состоянию."""
        if self.export_controller.is_running():
            return ClosePolicy.CONFIRM_IF_EXPORTING
        return ClosePolicy.ALLOW

    def _make_context(self) -> CloseContext:
        """Собрать факты о состоянии для close_policy."""
        return CloseContext(
            is_exporting=self.export_controller.is_running(),
        )

    def _ask(self, rule: CloseRule) -> bool:
        """Мост между политикой и QMessageBox."""
        return confirm(
            self,
            rule.text,
            title=rule.title,
            yes_label=rule.yes_label,
            no_label=rule.no_label,
        )


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.record_menu is not None and self.record_menu.is_open():
            self.record_menu.close()
        if self.crop_mode is not None:
            self.crop_mode.reposition()
            self.crop_mode.show_button_if_needed()


    def moveEvent(self, event):
        super().moveEvent(event)
        if self.record_menu is not None and self.record_menu.is_open():
            self.record_menu.close()
        if self.crop_mode is not None:
            self.crop_mode.reposition()

        
    def closeEvent(self, event: QCloseEvent):
        """Перед закрытием: решаем политику, чистим ресурсы."""
        policy = self._pick_policy()
        ctx = self._make_context()
        action = evaluate_close(policy, ctx, ask=self._ask)

        logger.debug(f"EditorWindow close: policy={policy.name}, action={action.name}")

        if action == CloseAction.CANCEL:
            event.ignore()
            return

        if action == CloseAction.CANCEL_EXPORT_AND_CLOSE:
            logger.info("Отменяем экспорт и закрываем редактор")
            self.export_controller.cancel()

        self._cleanup_aux_windows()
        self._cleanup_media()

        logger.info("Редактор скрыт (не уничтожен)")
        self.closed.emit()
        super().closeEvent(event)

    def _cleanup_aux_windows(self):
        """Скрыть и освободить вспомогательные top-level окна."""
        if self.record_menu is not None:
            self.record_menu.hide_windows()
        if self.crop_mode is not None:
            self.crop_mode.hide_windows()

    def _cleanup_media(self):
        """Остановить плеер, скрыть попапы и превью."""
        try:
            self.multiplexer._player.stop()
            self.multiplexer._player.setSource(QUrl())
        except Exception as e:
            logger.warning(f"Не удалось остановить плеер: {e}")

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
