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
import time
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QCursor
#from PySide6.QtMultimedia import QMediaPlayer                          # аудио-плеер для аудио-онли

from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
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
from src.pik2video.storage.thumbnail_cache import ThumbnailCache

from .panels import BottomPanel
from .crop_mode import CropModeController
from .panels import DropArea
from .export import ExportController
from .player import PlayerWidget
from .record_menu import RecordMenuController
from .state import EditorState
from .timeline import TimelineWidget as NewTimeline, FramePreview
from .thumbnail_loader import ThumbnailLoader
from .panels import ToolsPanel
from .panels import TopBar

logger = logging.getLogger(__name__)

# Зазор между зонами в пикселях
GAP = 4

TOOLS_PANEL_WIDTH = 200

# Доля экрана, которую занимает окно при старте
WINDOW_SCREEN_RATIO = 0.88


class EditorWindow(QMainWindow):
    record_video_requested = Signal()
    record_screen_requested = Signal()
    record_audio_requested = Signal()
    closed = Signal()

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.state = EditorState(self)

        # ── Кэш и загрузчик миниатюр ──
        self._thumbnail_cache = ThumbnailCache(self.controller.get_thumbs_dir())
        self._thumbnail_loader = ThumbnailLoader(self._thumbnail_cache, self)


        self._frame_preview = FramePreview()

        # Мигание рамки и стрелок при активном карандаше
        self._marker_blink_timer = QTimer(self)
        self._marker_blink_timer.setInterval(40)
        self._marker_blink_timer.timeout.connect(self._on_marker_blink_tick)
        self._marker_blink_phase = 1.0
        self._marker_blink_dir = -1

        # ── Контроллеры (создаются после _build_ui) ──
        self.record_menu = None


        self.crop_mode = None


        self.setWindowTitle("Редактор")
        self.setMinimumSize(1100, 700)
        self.setFocusPolicy(Qt.StrongFocus)

        self._apply_adaptive_size()
        self._build_ui()

        # ── Контроллеры (после _build_ui — им нужен top_bar) ──
        self._export_saved_path = None                              # путь к файлу, который был в плеере до экспорта
        self._marker_mode_active = False                             # режим сдвига рамки (перо/маркер)
        self._startup_done = False                                   # флаг: начальная инициализация закончена
        self._prev_had_both = False                                  # было ли оба файла в прошлой проверке
        self._was_playing_before_drag = False                        # играл ли плеер до начала drag метки
        self._last_preview_seek_ms = 0                               # throttle для setPosition при drag
        self._last_scrub_seconds = 0.0                               # финальная позиция после скраба
        self._drag_start_offset = 0.0                                # offset на момент начала drag дорожки
        self._current_dragged_offset = 0.0                           # текущий offset в процессе drag
        self._max_audio_offset = 0.0                                 # макс. сдвиг аудио (= video_dur - audio_dur)
        self._max_video_offset = 0.0                                 # макс. сдвиг видео (= audio_dur - video_dur)

        self.record_menu = RecordMenuController(self)
        self.record_menu.record_video_requested.connect(self.record_video_requested.emit)
        self.record_menu.record_screen_requested.connect(self.record_screen_requested.emit)
        self.record_menu.record_audio_requested.connect(self.record_audio_requested.emit)

        self.crop_mode = CropModeController(self)
        self.export_controller = ExportController(self, self.state)
        self.bottom_panel.export_clicked.connect(self.export_controller.start)
        self.top_bar.record_toggled.connect(self.record_menu.toggle)
        self.top_bar.crop_toggled.connect(self.crop_mode.toggle)               # ⛶ → режим пресетов
        self.crop_mode.mode_opened.connect(self._on_crop_mode_opened)          # режим открылся → оверлей
        self.crop_mode.mode_closed.connect(self._on_crop_mode_closed)          # режим закрылся → скрыть

        self.export_controller.export_started.connect(self._on_export_started)      # остановить плеер перед ffmpeg
        self.export_controller.export_finished.connect(self._on_export_finished)    # вернуть файл в плеер после

        # Восстанавливаем сохранённый список файлов
        self.state.load_persisted_files()
        self._prev_had_both = self.state.has_videos() and self.state.has_audio()
        self._startup_done = True
        self._sync_zoom_ui()                                     # синхронизировать кнопки зума с состоянием

        # Начальная установка громкостей из сохранённых значений
        self.multiplexer.set_video_volume(self.state.get_video_volume())
        self.multiplexer.set_audio_volume(self.state.get_audio_volume())

        # Начальная установка сдвигов дорожек из сохранённых значений
        self.timeline.set_audio_offset(self.state.get_audio_offset())
        self.timeline.set_video_offset(self.state.get_video_offset())
        self.multiplexer.set_audio_offset(self.state.get_audio_offset())

        self._update_timelines_visibility()                    # явно выставить пустое/заполненное состояние
        self.drop_area.set_linked(self.state.get_linked_mode())  # восстановить режим связки из JSON
        self.timeline.set_linked_mode(self.state.get_linked_mode())  # восстановить вид таймлайна
        self.multiplexer.set_linked_mode(self.state.get_linked_mode())     # восстановить режим плеера

    
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

        # ── Зона таймлайнов с общим ползунком ──
        self.timeline = NewTimeline(self.state)
        self.timeline.seek_requested.connect(self.multiplexer.set_position)
        

        upper.addWidget(mx_container, stretch=1)

        self.drop_area = DropArea(self._thumbnail_loader)
        self.drop_area.video_dropped.connect(self._on_video_dropped)
        self.drop_area.video_selected.connect(self._on_video_selected)
        self.drop_area.video_delete_requested.connect(self._on_video_delete_requested)
        self.drop_area.audio_dropped.connect(self._on_audio_dropped)
        self.drop_area.audio_delete_requested.connect(self._on_audio_delete_requested)
        self.drop_area.audio_clicked.connect(self._on_audio_clicked)
        self.drop_area.link_toggled.connect(self.state.set_linked_mode)         # клик по кнопке → состояние
        self.state.linked_mode_changed.connect(self.drop_area.set_linked)       # состояние → обновить кнопку
        self.state.linked_mode_changed.connect(lambda _: self._update_zone_highlight())   # состояние → подсветка
        self.state.linked_mode_changed.connect(self._on_linked_mode_changed_deferred)      # отложенно — избежать зависания
        self.state.linked_mode_changed.connect(self.multiplexer.set_linked_mode)          # состояние → плеер
        upper.addWidget(self.drop_area, stretch=0)

        right_side.addLayout(upper, stretch=1)


        self.bottom_panel = BottomPanel()
        self.bottom_panel.clear_clicked.connect(self._on_clear_clicked)

        self.bottom_panel.export_path_clicked.connect(self._on_export_path_clicked)
        self.bottom_panel.export_name_changed.connect(self.state.set_export_filename)
        

        # Заполнить путь экспорта из состояния
        self._sync_export_path_field()
        self._sync_export_name_field()


        middle.addLayout(right_side, stretch=1)

        root.addLayout(middle, stretch=1)
        root.addWidget(self.timeline, stretch=0)
        root.addWidget(self.bottom_panel, stretch=0)

        # ── Связи между EditorState и виджетами ──
        self.state.videos_changed.connect(self._on_videos_changed)
        self.state.active_video_changed.connect(self._on_active_video_changed)
        self.state.video_loaded.connect(self._on_video_loaded)
        self.state.video_unloaded.connect(self._on_video_unloaded)

        self.state.audio_loaded.connect(self._on_audio_loaded)          # восстановленный аудиофайл → в аудио-зону
        self.state.audio_unloaded.connect(self._on_audio_unloaded)      # сброс аудио → пустая аудио-зона
        self.state.audio_trim_changed.connect(self._on_audio_trim_changed)   # изменения трима → в аудио-таймлайн
        self.state.audio_format_changed.connect(self._on_audio_format_changed) # смена формата → в FormatTool

        self.state.position_changed.connect(self.timeline.set_position)  # позиция → красная линия
#         self.state.trim_changed.connect(self.timeline.set_trim) # ОТКЛЮЧЕНО (старый таймлайн)

        # ── Плеер → EditorState ──
        self.multiplexer.position_changed.connect(self.state.set_position)
        self.multiplexer.position_changed.connect(self._on_player_position_changed)
        self.multiplexer.duration_changed.connect(self._on_duration_changed)
        self.multiplexer.audio_duration_changed.connect(self._on_audio_duration_changed)   # длительность аудио
        self.multiplexer.speed_changed.connect(self.state.set_speed)                       # скорость плеера → экспорт
        self.multiplexer.video_volume_changed.connect(self.state.set_video_volume)         # громкость видео → сохранение
        self.multiplexer.audio_volume_changed.connect(self.state.set_audio_volume)         # громкость аудио → сохранение
        self.multiplexer.source_resolution_changed.connect(self.state.set_source_resolution)
        self.multiplexer.crop_rect_drawn.connect(self._on_crop_rect_drawn)                # ручной rect → в состояние
        self.multiplexer.shift_left_requested.connect(self._on_shift_left)
        self.multiplexer.shift_right_requested.connect(self._on_shift_right)

        self.state.video_limit_reached.connect(self._on_video_limit_reached)               # лимит 3 видео

#         self.state.audio_offset_changed.connect(self.timeline.set_audio_offset)      # сдвиг аудио → таймлайн # ОТКЛЮЧЕНО (старый таймлайн)
        self.state.audio_offset_changed.connect(self.multiplexer.set_audio_offset)         # сдвиг аудио → плеер
#         self.state.video_offset_changed.connect(self.timeline.set_video_offset)      # сдвиг видео → таймлайн # ОТКЛЮЧЕНО (старый таймлайн)

        self.state.trim_changed.connect(self.multiplexer.set_trim_range)               # видео-трим → плеер
        self.state.audio_trim_changed.connect(self.multiplexer.set_audio_trim_range)   # аудио-трим → аудио-плеер


        self.timeline.seek_requested.connect(self.multiplexer.set_position)
#         self.timeline.trim_changed.connect(self._on_video_trim_committed) # ОТКЛЮЧЕНО (старый таймлайн)

#         self.timeline.seek_requested.connect(self.multiplexer.set_position)        # клик по полосе → разовый seek # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.scrub_started.connect(self._on_scrub_started)                # начало drag → пауза плеера # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.scrub_dragged.connect(self._on_scrub_dragged)                # drag → превью кадра # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.scrub_finished.connect(self._on_scrub_finished)              # конец drag → возобновление # ОТКЛЮЧЕНО (старый таймлайн)

#         self.timeline.marker_drag_started.connect(self._on_marker_drag_started) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.marker_dragged.connect(self._on_marker_dragged) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.marker_drag_finished.connect(self._on_marker_drag_finished) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.marker_double_clicked.connect(self._on_marker_double_clicked) # ОТКЛЮЧЕНО (старый таймлайн)

#         self.timeline.marker_drag_started.connect(self._on_marker_drag_started)     # аудио: пауза/возобновление # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.marker_drag_finished.connect(self._on_marker_drag_finished) # ОТКЛЮЧЕНО (старый таймлайн)

        # Drag тела дорожки (сдвиг гостя)
#         self.timeline.track_drag_started.connect(self._on_video_track_started) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.track_dragged.connect(self._on_video_track_dragged) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.track_drag_finished.connect(self._on_video_track_finished) # ОТКЛЮЧЕНО (старый таймлайн)

#         self.timeline.track_drag_started.connect(self._on_audio_track_started) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.track_dragged.connect(self._on_audio_track_dragged) # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.track_drag_finished.connect(self._on_audio_track_finished) # ОТКЛЮЧЕНО (старый таймлайн)

#         self.timeline.trim_changed.connect(self._on_audio_trim_committed)     # финальный трим аудио → в состояние # ОТКЛЮЧЕНО (старый таймлайн)
#         self.timeline.seek_requested.connect(self._on_audio_seek)             # seek по аудио-таймлайну # ОТКЛЮЧЕНО (старый таймлайн)

        self.top_bar.tools_clicked.connect(self.tools_panel.show_tools)
        self.top_bar.settings_clicked.connect(self.tools_panel.show_settings)
        self.top_bar.preset_changed.connect(self.state.set_aspect_preset)
        self.top_bar.zoom_changed.connect(self.state.set_aspect_zoom)          # клик +/− → зум
        self.top_bar.marker_mode_toggled.connect(self._on_marker_mode_toggled)

        self.state.crop_rect_changed.connect(self._on_crop_rect_changed)        # rect из состояния → в плеер
        self.state.settings_changed.connect(self._sync_preset_drawing)         # смена пресета → drawing


    def _on_video_limit_reached(self):
        """Показать сообщение, если пользователь пытается добавить >3 видео."""
        from src.pik2video.gui.common.dialogs import warning
        warning(
            self,
            f"Можно загрузить не больше {self.state.MAX_VIDEO_FILES} видеофайлов.",
            translator=self.controller.get_translator(),
        )

    def _on_video_dropped(self, path: str):
        """Файл принят в списке видео."""
        logger.info(f"Видео принято: {path}")
        self.state.add_video_file(path, duration=0.0)

    def _update_zone_highlight(self):
        """Подсветить зоны по связке и переключить режим ползунка таймлайнов."""
        mode = self.multiplexer.mode
        linked = self.state.get_linked_mode()
        self.drop_area.update_highlight(mode, linked)
        self.timeline.set_active_mode(mode)

    def _on_audio_clicked(self):
        """Клик по аудио-зоне — переключить режим плеера на audio."""
        if self.state.has_audio():
            logger.debug("Клик по аудио-зоне → режим audio")
            QTimer.singleShot(0, lambda: self.multiplexer.set_mode("audio"))
            self._update_zone_highlight()

    def _on_video_selected(self, index: int):
        """Пользователь кликнул по файлу в списке."""
        self.state.set_active_video(index)
        self.multiplexer.set_mode("video")                    # всегда переключаемся в режим video
        self._update_zone_highlight()
        self.drop_area.drop_video.set_dimmed(False)           # принудительно снимаем затемнение
        self.drop_area.set_video_active(index)                # принудительно обновить рамку и кнопку

    def _on_audio_dropped(self, path: str):
        """Файл принят в зоне аудио."""
        logger.info(f"Аудио принято: {path}")
        self.state.set_audio_file(path, duration=0.0)            # state сам сохранит и эмитит audio_loaded
        self.bottom_panel.set_clear_enabled(True)                # с появлением аудио разрешаем очистку

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

        path = self.state.get_audio_path()                       # запомнили путь ДО очистки
        self.state.clear_audio()
        self._delete_draft_if_needed(path)                       # удаляем файл с диска
        self.bottom_panel.set_clear_enabled(self.state.has_videos())

    def _on_clear_clicked(self):
        """Сбросить загруженные файлы с подтверждением."""
        from src.pik2video.gui.common.dialogs import confirm

        if not self.state.has_any_media():                       # очищать нечего, если нет ни видео, ни аудио
            return

        if not confirm(self, "Очистить редактор?\n\nВсе загруженные файлы будут удалены."):
            return

        logger.info("Очистка редактора")

        video_paths = list(self.state.get_video_files())          # запоминаем пути ДО очистки состояния
        audio_path = self.state.get_audio_path()

        self.state.clear_video()                                  # плеер отпускает файлы здесь
        self.state.clear_audio()
        self.state.set_position(0.0)                              # сбросить позицию в state
        self.timeline.set_position(0.0)                     # принудительно сбросить ползунок

        self._update_zone_highlight()                             # снять подсветку (нечего подсвечивать)

        for path in video_paths:                                  # удаляем файлы ПОСЛЕ освобождения плеером
            self._delete_draft_if_needed(path)
        if audio_path:
            self._delete_draft_if_needed(audio_path)

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
        self.multiplexer.set_mode("video")                    # плеер в режим видео
        self.multiplexer.load_video(path)
        self._schedule_jump_to_trim_start()                   # отложенный прыжок на trim_start
        self._refresh_timeline_keyframes()                    # подтягиваем метки для нового файла
        if self.crop_mode.is_active():                        # режим пресетов уже открыт — обновить оверлей
            self.multiplexer.set_preset_visible(True)
            self.multiplexer.set_crop_rect(self.state.get_crop_rect())
            self._sync_preset_drawing()
        self._update_zone_highlight()
        self._sync_export_name_field()

    def _on_video_unloaded(self):
        """EditorState сообщил, что видео больше нет → переключаемся или placeholder."""
        if self.crop_mode.is_active():
            self.crop_mode.close()
        self.multiplexer.unload_video()
        self.timeline.set_duration(0.0)
        self.timeline.set_position(0.0)
        self.timeline.set_trim(0.0, 0.0)
        self.timeline.set_keyframes([])
        self._sync_export_name_field()

        # Если был в видео-режиме и видео не осталось — переключиться на аудио
        if self.multiplexer.mode == "video" and self.state.has_audio():
            logger.debug("Видео удалено — переключаемся на audio")
            self.multiplexer.set_mode("audio")
            self._update_zone_highlight()

        # Если связанных файлов больше нет — сбросить режим связки
        if not (self.state.has_videos() and self.state.has_audio()):
            if self.state.get_linked_mode():
                logger.debug("Остался один файл — режим связки сброшен")
                self.state.set_linked_mode(False)

        self._update_timelines_visibility()


    def _on_audio_loaded(self, path: str):
        """EditorState восстановил аудиофайл → показываем в аудио-зоне."""
        if not self.state.has_videos():
            self.multiplexer.set_mode("audio")                # аудио-онли → режим audio
        self.drop_area.show_audio(path)
        self._update_zone_highlight()                          # имя файла + иконка в аудио-зоне
        self.bottom_panel.set_clear_enabled(True)                # раз файл есть — очистка активна

        self.multiplexer.load_audio(path)                        # общий плеер переключается на страницу аудио

        self._sync_export_name_field()                           # подставляем имя файла и расширение
        self.bottom_panel.set_export_enabled(self.state.has_any_media())       # экспорт разрешён при аудио

        if not self.state.has_videos():                          # аудио-онли — переключаем инструменты
            self.tools_panel.switch_to_audio()

        self._update_timelines_visibility()                      # показать/скрыть таймлайны по наличию медиа


    def _on_audio_unloaded(self):
        """EditorState сообщил, что аудио сброшено → переключаемся или очищаем."""
        self.drop_area.show_audio_empty()
        self.bottom_panel.set_clear_enabled(self.state.has_videos())

        self.multiplexer.unload_audio()

        self.bottom_panel.set_export_enabled(self.state.has_videos())
        self._sync_export_name_field()

        if self.state.has_videos():
            self.tools_panel.switch_to_video()

        # Если был в аудио-режиме и аудио не осталось — переключиться на видео
        if self.multiplexer.mode == "audio" and self.state.has_videos():
            logger.debug("Аудио удалено — переключаемся на video")
            self.multiplexer.set_mode("video")
            self._update_zone_highlight()

        # Если связанных файлов больше нет — сбросить режим связки
        if not (self.state.has_videos() and self.state.has_audio()):
            if self.state.get_linked_mode():
                logger.debug("Остался один файл — режим связки сброшен")
                self.state.set_linked_mode(False)

        self._update_timelines_visibility()


    def _on_audio_trim_changed(self, start: float, end: float):
        """EditorState сообщил новый трим аудио → обновляем аудио-таймлайн."""
        pass # TODO: реализовать после создания визуальных маркеров

    def _on_audio_format_changed(self, fmt: str):
        """EditorState сообщил смену аудио-формата → обновляем FormatTool."""
        self.tools_panel.set_audio_format(fmt)

    def _on_export_started(self):
        """Перед экспортом отпускаем файл плеером — весь CPU уходит на ffmpeg."""
        self._export_saved_path = None                              # что было в плеере до экспорта
        if self.state.has_videos():
            self._export_saved_path = self.state.get_video_path()
            logger.debug(f"Экспорт: освобождаем плеер от {self._export_saved_path}")
            self.multiplexer.unload_video()
        elif self.state.has_audio():
            self._export_saved_path = self.state.get_audio_path()
            logger.debug(f"Экспорт: освобождаем плеер от {self._export_saved_path}")
            self.multiplexer.unload_audio()

    def _on_export_finished(self, success, message):
        """После экспорта возвращаем файл в плеер."""
        if not success or not self._export_saved_path:
            self._export_saved_path = None
            return
        from pathlib import Path
        if not Path(self._export_saved_path).exists():              # пользователь мог удалить файл во время экспорта
            self._export_saved_path = None
            return
        logger.debug(f"Экспорт завершён: возвращаем в плеер {self._export_saved_path}")
        if self.state.has_videos():
            self.multiplexer.load_video(self._export_saved_path)
            v_start, v_end = self.state.get_trim()
            self.multiplexer.set_trim_range(v_start, v_end)                    # восстановить метки видео
            if self.state.has_audio():
                a_start, a_end = self.state.get_audio_trim()
                self.multiplexer.set_audio_trim_range(a_start, a_end)          # восстановить метки аудио
            self.multiplexer.set_position(v_start)                             # курсор на левую метку
        elif self.state.has_audio():
            self.multiplexer.load_audio(self._export_saved_path)
            a_start, a_end = self.state.get_audio_trim()
            self.multiplexer.set_audio_trim_range(a_start, a_end)              # восстановить метки аудио
            self.multiplexer.set_position(a_start)
        self._export_saved_path = None

    def _schedule_jump_to_trim_start(self, attempts: int = 20):
        """Прыжок на trim_start после загрузки видео.

        Плеер грузит duration асинхронно: сразу после load_video() duration == 0.
        Ждём по 50 мс до 1 сек, потом делаем set_position(trim_start).
        """
        if not self.state.has_videos():
            return
        trim_start, _ = self.state.get_trim()
        if trim_start <= 0:
            return
        if self.multiplexer.video_player.duration() > 0:
            self.multiplexer.set_position(trim_start)
        elif attempts > 0:
            QTimer.singleShot(
                50, lambda: self._schedule_jump_to_trim_start(attempts - 1)
            )

    def _on_duration_changed(self, seconds: float):
        """Плеер сообщил длительность видео → обновляем видео-таймлайн и EditorState."""
        if self.state.has_videos():
            self.state.update_active_duration(seconds)           # длительность видео
            idx = self.state.get_active_index()
            if idx >= 0:
                self.timeline.set_track_duration(idx, seconds)
            # Обновить и аудио-дорожку (если она есть)
            if self.state.has_audio() and self.state.get_audio_duration() > 0:
                self.timeline.set_audio_duration(self.state.get_audio_duration())

    def _on_audio_duration_changed(self, seconds: float):
        """Плеер сообщил длительность аудио → обновляем аудио-таймлайн и EditorState."""
        if self.state.has_audio():
            self.state.set_audio_duration(seconds)               # длительность аудио
            self.timeline.set_audio_duration(seconds)

    def _on_videos_changed(self):
        """EditorState сообщил, что состав списка изменился."""
        self.drop_area.set_video_files(
            self.state.get_video_files(),
            self.state.get_active_index(),
        )
        has_any = self.state.has_any_media()
        self.bottom_panel.set_export_enabled(has_any)                # экспорт разрешён и при аудио-онли
        self.bottom_panel.set_editing_enabled(has_any)
        self.bottom_panel.set_clear_enabled(has_any)

        if self.state.has_videos() and not self.state.has_audio():
            self.tools_panel.switch_to_video()                       # видео-инструменты

        self._sync_export_name_field()
        self._update_timelines_visibility()


    def _update_timelines_visibility(self):
        """Перерисовать дорожки на основе состояния."""
        self.timeline.rebuild_tracks(
            self.state.get_video_files(),
            self.state.get_audio_path()
        )
        self._update_track_drag_mode()
        self._update_link_enabled()
        self._maybe_auto_link()

    def _on_linked_mode_changed_deferred(self, linked: bool):
        """Отложенно обновляем TimelineZone, чтобы не зависать на перестройке layout."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda: self.timeline.set_linked_mode(linked))

    def _maybe_auto_link(self):
        """Автоматически включить связку при появлении второго файла."""
        if not self._startup_done:
            return
        current = self.state.has_videos() and self.state.has_audio()
        if current and not self._prev_had_both:
            if not self.state.get_linked_mode():
                logger.debug("Auto-link: оба файла — включаем связку")
                self.state.set_linked_mode(True)
        self._prev_had_both = current

    def _update_link_enabled(self):
        """Кнопка связки доступна только когда есть оба файла."""
        has_both = self.state.has_videos() and self.state.has_audio()
        self.drop_area.set_link_enabled(has_both)


    def _on_scrub_started(self):
        """Начало drag по скрабберу: пауза плеера + кэш кадров."""
        self._was_playing_before_drag = self.multiplexer.begin_trim_drag()
        self.multiplexer.set_keep_frames(True)
        self._last_scrub_seconds = 0.0

    def _on_scrub_dragged(self, seconds: float, x_local: int):
        """Drag по скрабберу: throttled seek для превью + показ кадра."""
        self._last_scrub_seconds = seconds
        now_ms = int(time.time() * 1000)
        if now_ms - self._last_preview_seek_ms >= 200:                # throttle 200 мс (5 fps)
            self.multiplexer.seek_for_preview(seconds)
            self._last_preview_seek_ms = now_ms

        pixmap = self.multiplexer.get_last_frame()
        if pixmap is None:
            return
        global_pos = self.timeline.seek_bar.mapToGlobal(QPoint(x_local, 0))
        self._frame_preview.show_frame(pixmap, global_pos.x(), global_pos.y())

    def _on_scrub_finished(self):
        """Окончание drag: скрыть превью, финальный точный seek, возобновление."""
        self._frame_preview.hide_preview()
        self.multiplexer.set_keep_frames(False)
        self.multiplexer.set_position(self._last_scrub_seconds)       # точная позиция без throttle
        self.multiplexer.end_trim_drag(self._was_playing_before_drag)
        self._was_playing_before_drag = False

    def _update_track_drag_mode(self):
        """Определить, кто гость (короткая дорожка) — её можно тащить."""
        v = self.state.get_video_duration()
        a = self.state.get_audio_duration()
        has_v = self.state.has_videos()
        has_a = self.state.has_audio()

        can_compare = has_v and has_a and v > 0 and a > 0

        video_draggable = can_compare and v < a              # видео — гость
        audio_draggable = can_compare and a < v              # аудио — гость

        self.timeline.set_draggable(video_draggable)
        self.timeline.set_draggable(audio_draggable)

        self._max_video_offset = (a - v) if video_draggable else 0.0
        self._max_audio_offset = (v - a) if audio_draggable else 0.0

    def _on_video_track_started(self):
        self._drag_start_offset = self.state.get_video_offset()
        self._current_dragged_offset = self._drag_start_offset
        self._was_playing_before_drag = self.multiplexer.begin_trim_drag()

    def _on_video_track_dragged(self, delta_sec: float):
        new = max(0.0, min(self._max_video_offset, self._drag_start_offset + delta_sec))
        self._current_dragged_offset = new
        self.timeline.set_video_offset(new)

    def _on_video_track_finished(self):
        self.multiplexer.end_trim_drag(self._was_playing_before_drag)
        self._was_playing_before_drag = False
        self.state.set_video_offset(self._current_dragged_offset)

    def _on_audio_track_started(self):
        self._drag_start_offset = self.state.get_audio_offset()
        self._current_dragged_offset = self._drag_start_offset
        self._was_playing_before_drag = self.multiplexer.begin_trim_drag()

    def _on_audio_track_dragged(self, delta_sec: float):
        new = max(0.0, min(self._max_audio_offset, self._drag_start_offset + delta_sec))
        self._current_dragged_offset = new
        self.timeline.set_audio_offset(new)

    def _on_audio_track_finished(self):
        self.multiplexer.end_trim_drag(self._was_playing_before_drag)
        self._was_playing_before_drag = False
        self.state.set_audio_offset(self._current_dragged_offset)

    def _on_video_trim_committed(self, start: float, end: float):
        """Финальное сохранение метки видео (mouseRelease)."""
        self.state.set_trim(start, end)
        self.state.commit_trim()

    def _on_audio_trim_committed(self, start: float, end: float):
        """Финальное сохранение метки аудио (mouseRelease)."""
        self.state.set_audio_trim(start, end)
        self.state.commit_audio_trim()

    def _on_audio_seek(self, seconds: float):
        """Аудио-таймлайн просит перейти на позицию."""
        self.multiplexer.set_position(seconds)                   # общий плеер переходит на позицию



    def _sync_export_name_field(self):
        """Обновляет поле имени по активному медиа: видео, аудио или ничего."""
        if self.state.has_videos():
            self.bottom_panel.set_editing_enabled(True)
            path = self.state.get_video_path()
            stem = self.state.get_preferred_name(path)
            if not stem and self._is_draft(path):
                stem = Path(path).stem
            if stem:
                ext = Path(path).suffix.upper()
                self.bottom_panel.set_export_filename(stem, ext)
            else:
                self.bottom_panel.set_export_filename("", "")
            return

        if self.state.has_audio():
            self.bottom_panel.set_editing_enabled(True)
            audio_path = self.state.get_audio_path()
            stem = self.state.get_audio_export_filename()
            if not stem and self._is_draft(audio_path):
                stem = Path(audio_path).stem                          # имя из имени черновика
            fmt = self.state.get_audio_format()
            ext = {"WAV": ".WAV", "MP3": ".MP3", "M4A": ".M4A"}.get(fmt, ".WAV")
            if stem:
                self.bottom_panel.set_export_filename(stem, ext)
            else:
                self.bottom_panel.set_export_filename("", "")
            return

        self.bottom_panel.set_editing_enabled(False)
        self.bottom_panel.set_export_filename("", "")


    def _is_draft(self, path: str) -> bool:
        """Файл лежит в папке черновиков?"""
        if not self.controller or not path:
            return False
        try:
            return Path(path).parent == self.controller.get_drafts_dir()
        except Exception:
            return False

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

    def load_file(self, path: str, preferred_name: str = "") -> bool:
        """Загрузить файл в редактор извне. Возвращает True при успехе.

        preferred_name — имя для экспорта (например, из настроек записи).
        """
        logger.info(f"Редактор загружает файл: {path}")

        file_path = Path(path)
        if not file_path.exists():
            logger.error(f"Файл не найден: {path}")
            return False

        video_ext = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}           # допустимые расширения видео
        audio_ext = {".wav", ".m4a", ".mp3", ".aac", ".flac"}          # допустимые расширения аудио
        ext = file_path.suffix.lower()

        try:
            if ext in video_ext:
                self.state.add_video_file(path, duration=0.0, preferred_name=preferred_name)
            elif ext in audio_ext:
                self.state.set_audio_file(path, duration=0.0)          # аудио грузим в аудио-зону
                self.drop_area.show_audio(path)
            else:
                logger.error(f"Неподдерживаемый формат: {ext}")
                return False
        except Exception as e:
            logger.error(f"Ошибка добавления файла: {e}")
            return False

        return True
    
    def _on_marker_dragged(self, seconds: float, x_local: int):
        """Перетаскивание маркера — двигать красную полоску и показывать превью кадра."""
        # Двигаем красную полоску (курсор) и синхронизируем состояние
        self.timeline.set_position(seconds)
        self.state.set_position(seconds)

        now_ms = int(time.time() * 1000)
        if now_ms - self._last_preview_seek_ms >= 200:                # throttle 200 мс (5 fps)
            self.multiplexer.seek_for_preview(seconds)               # попросить декодер новый кадр
            self._last_preview_seek_ms = now_ms

        pixmap = self.multiplexer.get_last_frame()
        if pixmap is None:
            return

        global_pos = self.timeline.mapToGlobal(QPoint(x_local, 0))
        self._frame_preview.show_frame(pixmap, global_pos.x(), global_pos.y())

    def _on_marker_drag_started(self):
        """Начало drag метки: пауза плеера + кэш кадров для превью."""
        self._was_playing_before_drag = self.multiplexer.begin_trim_drag()
        self.multiplexer.set_keep_frames(True)

    def _on_marker_drag_finished(self):
        """Окончание drag: снять превью, вернуть воспроизведение."""
        self._frame_preview.hide_preview()
        self.multiplexer.set_keep_frames(False)
        self.multiplexer.end_trim_drag(self._was_playing_before_drag)
        self._was_playing_before_drag = False

    def _on_marker_double_clicked(self, time_sec: float):
        """Двойной клик на ромбике → всплывающее меню с удалением метки."""
        menu = QMenu(self)
        delete_action = menu.addAction("Удалить метку")
        delete_action.triggered.connect(lambda: self._delete_marker(time_sec))
        menu.exec(QCursor.pos())

    def _delete_marker(self, time_sec: float):
        """Удалить метку, применить состояние предыдущей, обновить таймлайн."""
        logger.debug(f"Удаляем метку {time_sec:.2f}с")
        new_offset, new_zoom = self.state.remove_marker(time_sec)
        self.state.set_offset_x(new_offset)
        self.state.set_aspect_zoom(new_zoom)
        self._refresh_timeline_keyframes()


    # ── Плавающее меню записи ──
    def _on_crop_mode_opened(self):
        """Режим пресетов открылся — показать оверлей и выставить drawing."""
        self.multiplexer.set_preset_visible(True)
        self.multiplexer.set_crop_rect(self.state.get_crop_rect())
        self._sync_preset_drawing()
        self._sync_zoom_ui()
        self._update_shift_buttons()

    def _on_crop_mode_closed(self):
        """Режим пресетов закрылся — скрыть оверлей и сбросить режим маркера."""
        self.multiplexer.set_preset_visible(False)
        self.multiplexer.set_shift_buttons_visible(False)
        self.top_bar.set_marker_mode(False)
        self._marker_mode_active = False

    def _on_crop_rect_changed(self, rect_tuple: tuple):
        """Состояние пересчитало рабочую зону — обновить оверлей и ромбики."""
        self.multiplexer.set_crop_rect(rect_tuple)
        self._sync_preset_drawing()
        self._sync_zoom_ui()
        self._update_shift_buttons()
        self._refresh_timeline_keyframes()  # при смене пресета — перерисовать ромбики

    def _on_crop_rect_drawn(self, qrect):
        """Пользователь нарисовал рабочую зону вручную — отдать в состояние."""
        self.state.set_crop_rect((qrect.x(), qrect.y(), qrect.width(), qrect.height()))

    def _sync_preset_drawing(self):
        """Рисование мыши включено только для пресета 'original' в активном режиме."""
        enabled = (
            self.crop_mode.is_active()
            and self.state.get_aspect_preset() == "original"
            and self.state.has_videos()
        )
        self.multiplexer.set_preset_drawing(enabled)

    def _sync_zoom_ui(self):
        """Синхронизировать активный пресет, зум и canvas AR в плеере."""
        preset = self.state.get_aspect_preset()
        self.top_bar.set_aspect_preset(preset)
        self.top_bar.set_zoom(self.state.get_aspect_zoom())
        self.top_bar.set_zoom_enabled(preset != "original")
        ar = self.state.ASPECT_RATIOS.get(preset)   # None для original
        self.multiplexer.set_canvas_ar(ar)
        # Если пресет original или зум 0 — режим сдвига не имеет смысла, сбрасываем
        if preset == "original":
            if self._marker_mode_active:
                self._marker_mode_active = False
                self.top_bar.set_marker_mode(False)

    def _on_shift_left(self):
        sw, _ = self.state.get_source_resolution()
        step = sw * 0.05
        self.state.set_offset_x(self.state.get_offset_x() - step)

    def _on_shift_right(self):
        sw, _ = self.state.get_source_resolution()
        step = sw * 0.05
        self.state.set_offset_x(self.state.get_offset_x() + step)

    def _on_player_position_changed(self, seconds: float):
        """Динамический сдвиг рамки при движении ползунка."""
        # Если пользователь в режиме редактирования (двигает стрелками) — не перебиваем
        if self._marker_mode_active:
            return
            
        markers = self.state.get_markers()
        if not markers:
            # Если меток нет — рамка возвращается в центр (offset=0)
            self.state.set_offset_x(0.0, save=False)
            return

        # Вычисляем активную метку (ступенчато).
        # Допуск 1 мс — маркеры уже снапнуты к кадрам, больший допуск
        # срабатывал бы на 1-2 кадра раньше.
        active_offset, active_zoom = self.state.get_marker_state_at(seconds)
                
        # Применяем без сохранения в JSON
        self.state.set_offset_x(active_offset, save=False)
        self.state.set_aspect_zoom(active_zoom, save=False)

    def _on_marker_mode_toggled(self, active: bool):
        self._marker_mode_active = active
        self.top_bar.set_presets_enabled(not active)
        self._update_shift_buttons()
        self.multiplexer.set_marker_mode(active)

        if active:
            self._marker_blink_phase = 1.0
            self._marker_blink_dir = -1
            self._marker_blink_timer.start()
        else:
            self._marker_blink_timer.stop()
            self.multiplexer.set_preset_blink_phase(1.0)
            self.multiplexer.set_shift_buttons_blink_phase(1.0)
        
        # Если режим выключили (нажали на 🖍️) — сохраняем метку
        if not active:
            raw_time = self.state.get_position()
            # Снапим к ближайшему кадру: player.position() может вернуть
            # 0.401 вместо 0.400, и сдвиг срабатывает на 1 кадр позже
            fps = self.multiplexer.video_fps or 25.0
            snapped_time = round(raw_time * fps) / fps
            current_offset = self.state.get_offset_x()
            current_zoom = self.state.get_aspect_zoom()
            self.state.add_marker(snapped_time, current_offset, current_zoom)
            logger.debug(
                f"Зафиксирована метка: {snapped_time:.3f}с (raw {raw_time:.3f}), "
                f"сдвиг {current_offset}, зум {current_zoom}"
            )
            self._refresh_timeline_keyframes()

    def _on_marker_blink_tick(self):
        """Один тик мигания: сдвинуть фазу, передать в плеер."""
        self._marker_blink_phase += 0.04 * self._marker_blink_dir
        if self._marker_blink_phase >= 1.0:
            self._marker_blink_phase = 1.0
            self._marker_blink_dir = -1
        elif self._marker_blink_phase <= 0.0:
            self._marker_blink_phase = 0.0
            self._marker_blink_dir = 1
        self.multiplexer.set_preset_blink_phase(self._marker_blink_phase)
        self.multiplexer.set_shift_buttons_blink_phase(self._marker_blink_phase)

    def _update_shift_buttons(self):
        """Показать/скрыть и включить/выключить стрелки сдвига."""
        if not self._marker_mode_active or not self.crop_mode.is_active() or self.state.get_aspect_preset() == "original":
            self.multiplexer.set_shift_buttons_visible(False)
            return

        self.multiplexer.set_shift_buttons_visible(True)

        # Пересчёт активности стрелок: при zoom=0 рамка = ширина источника,
        # сдвигать нечего — обе выключены. При zoom>0 — по краям диапазона.
        sw, _ = self.state.get_source_resolution()
        if sw <= 0:
            return

        _, _, cw, _ = self.state.get_crop_rect()
        max_off = (sw - cw) / 2.0
        off = self.state.get_offset_x()

        can_left = off > -max_off + 0.1
        can_right = off < max_off - 0.1
        self.multiplexer.set_shift_buttons_enabled(can_left, can_right)

    def _refresh_timeline_keyframes(self):
        """Передать времена меток в таймлайн для отрисовки."""
        markers = self.state.get_markers()
        times = [m[0] for m in markers]
        self.timeline.set_keyframes(times)

        sw, _ = self.state.get_source_resolution()
        if sw <= 0:
            return

        _, _, cw, _ = self.state.get_crop_rect()
        max_off = (sw - cw) / 2.0
        off = self.state.get_offset_x()

        can_left = off > -max_off + 0.1
        can_right = off < max_off - 0.1
        self.multiplexer.set_shift_buttons_enabled(can_left, can_right)

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

    def hideEvent(self, event):
        super().hideEvent(event)

    def showEvent(self, event):
        super().showEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.record_menu is not None and self.record_menu.is_open():
            self.record_menu.close()


    def moveEvent(self, event):
        super().moveEvent(event)
        if self.record_menu is not None and self.record_menu.is_open():
            self.record_menu.close()

    def mousePressEvent(self, event):
        """Клик по пустому месту — забрать фокус у активного поля."""
        self.setFocus()
        super().mousePressEvent(event)

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

    def _cleanup_media(self):
        """Остановить плеер, скрыть попапы и превью."""
        if hasattr(self, "_marker_blink_timer") and self._marker_blink_timer.isActive():
            self._marker_blink_timer.stop()
        try:
            self.multiplexer.video_player.stop()
            self.multiplexer.video_player.setSource(QUrl())
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
