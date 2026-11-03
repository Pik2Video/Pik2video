# src/pik2video/gui/editor/timeline/timeline.py
import logging
from pathlib import Path

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton

from .track import TrackWidget

ICON_WIDTH = 80
TRACK_ROW_SPACING = 4
PLAYHEAD_GRAB_PX = 6

TRACK_HEIGHT_NORMAL = 12
TRACK_HEIGHT_FOCUS = 50
TRACK_HEIGHT_DIMMED = 8

BASE_HEIGHT = 80
TRACK_MARGINS = 8                  # 4 сверху + 4 снизу (как в layout)

ICON_NORMAL_STYLE = "font-size: 14px; background: transparent; border: none; color: #888;"
ICON_FOCUS_STYLE = "font-size: 14px; background: transparent; border: none; color: #e0e0e0;"


logger = logging.getLogger(__name__)


class ClickableLabel(QLabel):
    """QLabel с mousePressEvent — для иконок дорожек."""

    clicked = Signal()

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PlayheadOverlay(QWidget):
    """Прозрачный слой поверх дорожек — рисует только красную линию."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._x = 0

    def set_x(self, x: int):
        if self._x != x:
            self._x = x
            self.update()

    def paintEvent(self, event):
        if self._x <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#8b1a1a"), 2))
        painter.drawLine(self._x, 0, self._x, self.height())


class TimelineWidget(QWidget):
    """Контейнер дорожек + playhead с drag-перетаскиванием."""

    seek_requested = Signal(float)
    playhead_drag_started = Signal()
    playhead_dragged = Signal(float, int)   # секунды, x-локальный (для превью)
    playhead_drag_finished = Signal()
    active_changed = Signal(str, int)       # "video"/"audio", index
    height_changed = Signal(int)            # идеальная высота таймлайна (для мультиплеера)
    marker_clicked = Signal(str, QPoint)    # клик на карандаш: путь файла, глобальная позиция
    marker_place_requested = Signal(str, float)  # поставить метку: путь файла, секунды
    marker_delete_requested = Signal(str, float) # удалить метку: путь файла, секунды
    marker_drag_started = Signal(str, float)     # начали тащить метку: (path, start_time)
    marker_dragged = Signal(str, float, float)   # тащим: (path, old_time, new_time)
    marker_drag_finished = Signal(str, float)    # отпустили: (path, final_time)
    cut_hide_requested = Signal(str, float, float)     # скрыть cut: (path, start, end)
    cut_restore_requested = Signal(str, float, float)  # восстановить cut: (path, start, end)
    track_drag_finished = Signal(str, float)     # закончили drag дорожки по X: (path, offset_sec)

    def __init__(self, state, thumbnail_loader=None, parent=None):
        super().__init__(parent)
        self.state = state
        self._thumbnail_loader = thumbnail_loader
        if self._thumbnail_loader is not None:
            self._thumbnail_loader.frames_ready.connect(self._on_frames_ready)
        # Метки могут меняться извне (EditorState) — перерисовать дорожки
        self.state.timeline_markers_changed.connect(self._refresh_markers)
        self._tracks = []            # [(track, icon)]
        self._total_duration = 0.0
        self._position = 0.0
        self._playhead_x = 0
        self._dragging_playhead = False
        self._active_video_index = 0
        self._wheel_accumulator = 0                # накопление дельты колеса
        self._wheel_target_path = ""               # путь дорожки под курсором
        self._dragging_marker = None               # (path, current_time) при drag метки
        self._track_offsets = {}                   # path -> визуальный сдвиг в секундах (X-drag)
        self._dragging_track = None                # (path, start_offset, start_global_x)
        self._tool_cursor: QCursor | None = None   # кастомный курсор инструмента метки

        self.setStyleSheet("background-color: #151515; border-top: 1px solid #000;")
        self.setMinimumHeight(80)
        self.setMouseTracking(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)
        layout.addStretch(1)

        self._tracks_container = QWidget()
        self._tracks_container.setStyleSheet("background: transparent;")
        self._tracks_layout = QVBoxLayout(self._tracks_container)
        self._tracks_layout.setContentsMargins(0, 0, 0, 0)
        self._tracks_layout.setSpacing(TRACK_ROW_SPACING)
        layout.addWidget(self._tracks_container)

        layout.addStretch(1)

        # Прозрачный слой поверх — красная линия
        self._playhead_overlay = PlayheadOverlay(self)
        self._playhead_overlay.raise_()

    # ── Пересборка ──

    def rebuild_tracks(self, video_files: list, audio_path: str):
        for i in reversed(range(self._tracks_layout.count())):
            item = self._tracks_layout.takeAt(i)
            if item.widget():
                item.widget().deleteLater()
        self._tracks.clear()

        for idx, path in enumerate(video_files):
            dur = self.state.get_video_duration_for(path)
            self._add_track("video", path, dur, idx)
            # Если длительность уже известна — сразу запросить кадры
            if dur > 0:
                self._request_frames(self._tracks[-1][0], dur)

        if audio_path:
            dur = self.state.get_audio_duration()
            self._add_track("audio", audio_path, dur, 0)
            if dur > 0:
                self._request_frames(self._tracks[-1][0], dur)
            # Восстанавливаем визуальный offset аудио из state
            self._track_offsets[audio_path] = self.state.get_audio_offset()

        # Чистим offset у видео-дорожек (их больше не двигаем)
        video_paths = set(video_files)
        for k in list(self._track_offsets.keys()):
            if k in video_paths:
                del self._track_offsets[k]

        self._recalc_total()
        self._update_playhead()
        self._refresh_markers()
        self._emit_height()

    def _add_track(self, track_type: str, path: str, duration: float, index: int):
        row = QWidget()
        row.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        # Контейнер иконки: иконка слева + stretch + карандаш справа
        icon_container = QWidget()
        icon_container.setFixedWidth(ICON_WIDTH)
        icon_container.setStyleSheet("background: transparent;")
        icon_layout = QHBoxLayout(icon_container)
        icon_layout.setContentsMargins(4, 0, 4, 0)
        icon_layout.setSpacing(0)

        icon_text = "📹" if track_type == "video" else "🎵"
        icon = ClickableLabel(icon_text)
        icon.setFixedWidth(36)
        icon.setStyleSheet(ICON_NORMAL_STYLE)
        icon.clicked.connect(
            lambda k=track_type, i=index: self.active_changed.emit(k, i)
        )
        icon_layout.addWidget(icon, alignment=Qt.AlignVCenter)
        icon_layout.addStretch(1)

        track = TrackWidget(track_type, path, duration)

        # Карандаш — для всех типов дорожек (видео и аудио)
        if track_type in ("video", "audio"):
            marker_btn = QPushButton("🖋")
            marker_btn.setFixedSize(24, 20)
            marker_btn.setCursor(Qt.PointingHandCursor)
            marker_btn.setStyleSheet("""
                QPushButton {
                    background: transparent;
                    border: 1px solid transparent;
                    border-radius: 3px;
                    color: #888;
                    font-size: 12px;
                }
                QPushButton:hover {
                    background: #2a2a2a;
                    border-color: #555;
                    color: #e0e0e0;
                }
                QPushButton:pressed { background: #1a1a1a; }
            """)
            marker_btn.clicked.connect(
                lambda checked=False, p=path, b=marker_btn:
                    self.marker_clicked.emit(p, b.mapToGlobal(QPoint(0, b.height())))
            )
            marker_btn.setVisible(False)  # показывается только у активной
            icon_layout.addWidget(marker_btn, alignment=Qt.AlignVCenter)
            track.marker_btn = marker_btn

        # Spacer между иконкой и дорожкой — сдвигает ТОЛЬКО дорожку при drag,
        # иконка остаётся на месте. Ширина управляется в _update_widths.
        row_spacer = QWidget()
        row_spacer.setFixedWidth(0)
        row_spacer.setStyleSheet("background: transparent;")

        row_layout.addWidget(icon_container, alignment=Qt.AlignVCenter)
        row_layout.addWidget(row_spacer, alignment=Qt.AlignVCenter)
        row_layout.addWidget(track, alignment=Qt.AlignVCenter)
        row_layout.addStretch(1)

        track._row_spacer = row_spacer   # ссылка для управления шириной

        self._tracks_layout.addWidget(row)
        self._tracks.append((track, icon))

        # Восстановить фокус
        if track_type == "video" and index == self._active_video_index:
            track.set_focus(True)
            icon.setStyleSheet(ICON_FOCUS_STYLE)
            if track.marker_btn is not None:
                track.marker_btn.setVisible(True)
        elif track_type == "audio" and not self.state.has_videos():
            track.set_focus(True)
            icon.setStyleSheet(ICON_FOCUS_STYLE)
            if track.marker_btn is not None:
                track.marker_btn.setVisible(True)

    def set_active_video(self, index: int):
        self._active_video_index = index
        for track, icon in self._tracks:
            if track.track_type != "video":
                # Карандаш у аудио и других дорожек — скрываем
                if track.marker_btn is not None:
                    track.marker_btn.setVisible(False)
                continue
            idx = self._index_of_video_path(track.path)
            focused = (idx == index)
            track.set_focus(focused)
            icon.setStyleSheet(ICON_FOCUS_STYLE if focused else ICON_NORMAL_STYLE)
            if track.marker_btn is not None:
                track.marker_btn.setVisible(focused)

    def set_active_audio(self):
        for track, icon in self._tracks:
            if track.track_type == "audio":
                track.set_focus(True)
                icon.setStyleSheet(ICON_FOCUS_STYLE)
                if track.marker_btn is not None:
                    track.marker_btn.setVisible(True)
            else:
                track.set_focus(False)
                icon.setStyleSheet(ICON_NORMAL_STYLE)
                if track.marker_btn is not None:
                    track.marker_btn.setVisible(False)

    def _index_of_video_path(self, path: str) -> int:
        try:
            return self.state.get_video_files().index(path)
        except ValueError:
            return -1

    # ── Кадры для отрисовки на дорожке ──

    @staticmethod
    def _frames_count(duration: float) -> int:
        """Сколько кадров генерировать: от 20 до 100, зависит от длины."""
        if duration <= 0:
            return 0
        return max(20, min(100, int(duration)))

    def _request_frames(self, track, duration: float):
        """Поставить задачу на генерацию кадров для дорожки."""
        if self._thumbnail_loader is None or duration <= 0:
            return
        count = self._frames_count(duration)
        if count > 0:
            self._thumbnail_loader.request_frames(track.path, count, duration)

    def _refresh_markers(self):
        """Передать метки, cut-интервалы и display-интервалы во все дорожки."""
        for track, _ in self._tracks:
            markers = self.state.get_timeline_markers(track.path)
            cuts = self.state.get_cut_intervals(track.path)
            track.set_markers(markers, cuts)

            # display = визуальные интервалы (без скрытых cut).
            # Если весь файл виден (один интервал 0..duration) — передаём пусто
            # (оптимизация: track работает в обычном режиме).
            display = self.state.get_display_intervals(track.path)
            if (len(display) == 1
                    and display[0][0] < 0.01
                    and abs(display[0][1] - track.duration) < 0.01):
                display = []
            track.set_display_intervals(display)

    def _on_frames_ready(self, source_path: str, count: int):
        """Кадры готовы в кэше → загрузить pixmaps и передать в дорожки."""
        if self._thumbnail_loader is None:
            return
        pixmaps = self._thumbnail_loader.get_cached_frames(source_path, count)
        if not pixmaps:
            return
        for track, _ in self._tracks:
            if track.path == source_path:
                track.set_frames(pixmaps)

    # ── Ширины ──

    def set_track_duration(self, index: int, duration: float):
        video_tracks = [t for t, _ in self._tracks if t.track_type == "video"]
        if 0 <= index < len(video_tracks):
            video_tracks[index].set_duration(duration)
            self._recalc_total()
            self._request_frames(video_tracks[index], duration)
            self._refresh_markers()

    def set_audio_duration(self, duration: float):
        for track, _ in self._tracks:
            if track.track_type == "audio":
                track.set_duration(duration)
                self._recalc_total()
                self._request_frames(track, duration)
                self._refresh_markers()
                return

    def _recalc_total(self):
        self._total_duration = max(
            (t.duration for t, _ in self._tracks), default=0.0
        )
        self._update_widths()
        self._update_playhead()

    def _compute_ideal_height(self) -> int:
        """Идеальная высота таймлайна.

        Возвращает ровно столько, сколько нужно дорожкам. Без лишнего «воздуха».
        Не меньше BASE_HEIGHT — для компактного вида с 1-2 дорожками.
        """
        if not self._tracks:
            return BASE_HEIGHT

        sum_heights = sum(t.height() for t, _ in self._tracks)
        n = len(self._tracks)
        gaps = TRACK_ROW_SPACING * max(0, n - 1)
        needed = sum_heights + gaps + TRACK_MARGINS
        return max(BASE_HEIGHT, needed)

    def _emit_height(self):
        self.height_changed.emit(self._compute_ideal_height())

    def _update_widths(self):
        available = self.width() - ICON_WIDTH
        if available <= 0 or not self._tracks:
            return
        if self._total_duration <= 0:
            for track, _ in self._tracks:
                track.setFixedWidth(max(20, available))
            return
        for track, _ in self._tracks:
            ratio = track.duration / self._total_duration if track.duration > 0 else 1.0
            track_px = max(20, int(ratio * available))
            track.setFixedWidth(track_px)

            # Сдвиг через spacer: только дорожка, иконка на месте.
            offset_sec = self._track_offsets.get(track.path, 0.0)
            offset_px = int((offset_sec / self._total_duration) * available) if self._total_duration > 0 else 0
            max_offset_px = max(0, available - track_px)
            offset_px = max(0, min(offset_px, max_offset_px))

            spacer = getattr(track, "_row_spacer", None)
            if spacer is not None:
                spacer.setFixedWidth(offset_px)

        # Ползунок следует за дорожкой при её сдвиге
        self._update_playhead()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._playhead_overlay.resize(self.size())
        self._playhead_overlay.raise_()
        self._update_widths()
        self._update_playhead()

    # ── Playhead ──

    def set_position(self, seconds: float):
        self._position = max(0.0, seconds)
        self._update_playhead()

    def _update_playhead(self):
        """Позиция playhead в координатах ТАЙМЛАЙНА.

        self._position — секунды плеера (от 0 активного видео).
        Реальная позиция на таймлайне = offset активного видео + position.
        При сдвинутой дорожке это даёт правильное положение.
        """
        if self._total_duration <= 0:
            self._playhead_x = 0
            self._playhead_overlay.set_x(self._playhead_x)
            return

        available = self.width() - ICON_WIDTH
        if available <= 0:
            self._playhead_x = 0
            self._playhead_overlay.set_x(self._playhead_x)
            return

        # Offset активного видео (в секундах таймлайна)
        active_path = self.state.get_video_path() if self.state else None
        active_offset = self._track_offsets.get(active_path, 0.0) if active_path else 0.0

        timeline_pos = active_offset + self._position
        ratio = max(0.0, min(1.0, timeline_pos / self._total_duration))
        self._playhead_x = int(ICON_WIDTH + ratio * available)
        self._playhead_overlay.set_x(self._playhead_x)

    def _x_to_seconds(self, x: float) -> float:
        available = self.width() - ICON_WIDTH
        if available <= 0 or self._total_duration <= 0:
            return 0.0
        x_rel = max(0.0, min(available, x - ICON_WIDTH))
        return (x_rel / available) * self._total_duration

    def _is_near_playhead(self, x: float) -> bool:
        if self._total_duration <= 0:
            return False
        return abs(x - self._playhead_x) <= PLAYHEAD_GRAB_PX

    # ── Определение дорожки под курсором ──

    # Hit-box расширение по Y: тонкая дорожка (12px) + spacing (4px) —
    # без запаса легко промахнуться между или чуть выше/ниже.
    HIT_PADDING_Y = 8

    def _track_at(self, global_pos: QPoint):
        """Найти TrackWidget по глобальной координате курсора (или None).

        Hit-box расширен по Y (HIT_PADDING_Y) — чтобы клик рядом с дорожкой
        тоже попадал в неё. По X — точное совпадение с шириной дорожки.
        """
        for track, _ in self._tracks:
            local = track.mapFromGlobal(global_pos)
            if (0 <= local.x() <= track.width()
                    and -self.HIT_PADDING_Y <= local.y() <= track.height() + self.HIT_PADDING_Y):
                return track
        return None

    def debug_tracks_geometry(self):
        """Диагностика: вывести геометрию всех дорожек в лог."""
        for track, _ in self._tracks:
            logger.debug(
                f"[MARKER] track={Path(track.path).name} "
                f"geom={track.geometry()} visible={track.isVisible()}"
            )

    def _time_at_track(self, track, global_pos: QPoint) -> float:
        """Перевести глобальную X в секунды внутри указанной дорожки."""
        if track is None or track.duration <= 0 or track.width() <= 0:
            return 0.0
        local = track.mapFromGlobal(global_pos)
        ratio = max(0.0, min(1.0, local.x() / track.width()))
        return ratio * track.duration

    def _track_duration(self, path: str) -> float:
        for t, _ in self._tracks:
            if t.path == path:
                return t.duration
        return 0.0

    def _track_for_x_drag_at(self, global_pos: QPoint):
        """Найти дорожку, которую можно тащить по X. Возвращает (track, local_x) или None.

        Тащим ТОЛЬКО аудио-дорожку. Видео-дорожки по X не двигаем — иначе
        ломается единая координатная система playhead (плеер и таймлайн
        начинают работать в разных системах).

        Не тащим:
        - видео (любой длины)
        - если клик на метке
        - если клик на playhead
        """
        track = self._track_at(global_pos)
        if track is None or track.duration <= 0:
            return None
        # Только аудио
        if track.track_type != "audio":
            return None
        # Не тащим, если кликнули на метку
        if self._marker_at(global_pos) is not None:
            return None
        local = track.mapFromGlobal(global_pos)
        return track, local.x()

    def _marker_at(self, global_pos: QPoint):
        """Найти метку под курсором. Возвращает (path, time_sec) или None."""
        track = self._track_at(global_pos)
        if track is None or track.duration <= 0 or track.width() <= 0:
            return None

        local = track.mapFromGlobal(global_pos)
        local_x = local.x()

        markers = self.state.get_timeline_markers(track.path)
        for time_sec, _kind in markers:
            marker_x = int(track.width() * time_sec / track.duration)
            # Допуск в пикселях для попадания по метке
            if abs(local_x - marker_x) <= 6:
                return track.path, time_sec
        return None

    def _cut_at(self, global_pos: QPoint):
        """Найти видимый (не скрытый) cut под курсором.

        Работает только когда display_intervals пуст (всё в реальных координатах).
        Если display задан (есть скрытые cut) — все cut визуально подтянуты,
        кликнуть на них нельзя.
        """
        track = self._track_at(global_pos)
        if track is None or track.duration <= 0 or track.width() <= 0:
            return None

        # Если есть скрытые cut — cut визуально отсутствуют
        display = self.state.get_display_intervals(track.path)
        if len(display) > 1:
            return None

        cuts = self.state.get_cut_intervals(track.path)
        if not cuts:
            return None

        local = track.mapFromGlobal(global_pos)
        local_x = local.x()

        for cs, ce in cuts:
            x_start = track.width() * cs / track.duration
            x_end = track.width() * ce / track.duration
            if x_start <= local_x <= x_end:
                return track.path, cs, ce
        return None

    def _gap_at(self, global_pos: QPoint):
        """Найти красную чёрточку (разрез) под курсором.

        Работает только когда display_intervals задан (есть скрытые cut).
        Возвращает (path, real_start, real_end) — реальные границы скрытого cut.
        """
        track = self._track_at(global_pos)
        if track is None or track.duration <= 0 or track.width() <= 0:
            return None

        display = self.state.get_display_intervals(track.path)
        if len(display) < 2:
            return None

        local = track.mapFromGlobal(global_pos)
        local_x = local.x()

        disp_dur = sum(e - s for s, e in display)
        if disp_dur <= 0:
            return None

        # Чёрточки между фрагментами: accumulated позиция
        accumulated = 0.0
        for i, (s_seg, e_seg) in enumerate(display[:-1]):
            accumulated += e_seg - s_seg
            x = track.width() * accumulated / disp_dur
            if abs(local_x - x) <= 6:
                # Реальные границы скрытого cut: конец текущего видимого - начало следующего
                next_start = display[i + 1][0]
                return track.path, e_seg, next_start
        return None

    def contextMenuEvent(self, event):
        """Правый клик на метке — удалить. В остальных местах — стандартное меню."""
        if self._tool_cursor is not None:
            return super().contextMenuEvent(event)

        marker = self._marker_at(event.globalPos())
        if marker is not None:
            path, time_sec = marker
            self.marker_delete_requested.emit(path, time_sec)
            event.accept()
            return

        super().contextMenuEvent(event)

    # ── Инструменты меток (курсоры) ──

    @staticmethod
    def _make_tool_cursor(kind: str) -> QCursor:
        """Нарисовать курсор с символом инструмента (белый текст + чёрная обводка)."""
        size = 28
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Menlo", 16)
        font.setBold(True)
        painter.setFont(font)

        text = kind
        rect = pixmap.rect()
        # Обводка: рисуем текст 4 раза со смещением, потом белым сверху
        painter.setPen(QColor(0, 0, 0))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
            painter.drawText(rect.adjusted(dx, dy, dx, dy), Qt.AlignCenter, text)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(rect, Qt.AlignCenter, text)
        painter.end()

        # Hot-spot: нижний левый угол — «точка прицела»
        return QCursor(pixmap, 2, size - 2)

    def make_tool_cursor(self, kind: str) -> QCursor:
        """Публичный фасад для _make_tool_cursor — используется меню."""
        return self._make_tool_cursor(kind)

    def set_tool_cursor(self, kind: str | None):
        """Установить курсор инструмента. None — вернуть обычный курсор."""
        if kind in ("[", "]", "]["):
            self._tool_cursor = self._make_tool_cursor(kind)
            self.setCursor(self._tool_cursor)
        else:
            self._tool_cursor = None
            self.setCursor(Qt.ArrowCursor)

    def has_active_tool(self) -> bool:
        return self._tool_cursor is not None

    # ── Мышь ──

    def mouseMoveEvent(self, event):
        x = event.position().x()

        # Приоритет 0: drag дорожки по X
        if self._dragging_track is not None:
            path, start_offset, start_x = self._dragging_track
            delta_x = event.globalPosition().toPoint().x() - start_x
            available = self.width() - ICON_WIDTH
            if available > 0 and self._total_duration > 0:
                delta_sec = (delta_x / available) * self._total_duration
                new_offset = max(0.0, start_offset + delta_sec)
                # Ограничение: дорожка не должна уходить за правый край
                max_offset = max(0.0, self._total_duration - self._track_duration(path))
                new_offset = min(new_offset, max_offset)
                self._track_offsets[path] = new_offset
                self._update_widths()
                self.update()
            return

        # Приоритет 1: drag метки
        if self._dragging_marker is not None:
            path, old_time = self._dragging_marker
            # Ищем дорожку по сохранённому path, не по hit-box (курсор может уйти по Y)
            track = None
            for t, _ in self._tracks:
                if t.path == path:
                    track = t
                    break
            if track is not None and track.width() > 0:
                local = track.mapFromGlobal(event.globalPosition().toPoint())
                # Разрешаем тащить даже если курсор вышел за пределы дорожки по Y,
                # но не выше/ниже разумного (иначе X-координата теряет смысл)
                x_clamped = max(0, min(track.width(), local.x()))
                ratio = x_clamped / track.width()
                new_time = ratio * track.duration
                if abs(new_time - old_time) > 0.001:
                    self.marker_dragged.emit(path, old_time, new_time)
                    self._dragging_marker = (path, new_time)
            return

        # Приоритет 2: drag playhead
        if self._dragging_playhead:
            seconds = self._x_to_seconds(x)
            self.set_position(seconds)
            self.seek_requested.emit(seconds)
            self.playhead_dragged.emit(seconds, int(x))
            return

        # Приоритет 3: активный инструмент — курсор не трогаем
        if self._tool_cursor is not None:
            return

        # Приоритет 4: hover на метке или playhead
        marker = self._marker_at(event.globalPosition().toPoint())
        if marker is not None:
            self.setCursor(Qt.SizeHorCursor)
            return

        if self._is_near_playhead(x):
            self.setCursor(Qt.PointingHandCursor)
            return

        # Hover над короткой дорожкой → рука (можно тащить по X)
        target = self._track_for_x_drag_at(event.globalPosition().toPoint())
        if target is not None:
            self.setCursor(Qt.OpenHandCursor)
            return

        self.setCursor(Qt.ArrowCursor)

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)

        # Приоритет 1: активный инструмент метки — клик ставит метку на дорожке
        if self._tool_cursor is not None:
            track = self._track_at(event.globalPosition().toPoint())
            if track is not None:
                seconds = self._time_at_track(track, event.globalPosition().toPoint())
                self.marker_place_requested.emit(track.path, seconds)
            event.accept()
            return

        # Приоритет 2: клик на метке → drag метки
        marker = self._marker_at(event.globalPosition().toPoint())
        if marker is not None:
            path, time_sec = marker
            self._dragging_marker = (path, time_sec)
            self.setCursor(Qt.SizeHorCursor)
            self.marker_drag_started.emit(path, time_sec)
            event.accept()
            return

        # Приоритет 3: drag дорожки по X (только короткой, не на playhead)
        if not self._is_near_playhead(event.position().x()):
            target = self._track_for_x_drag_at(event.globalPosition().toPoint())
            if target is not None:
                track, _ = target
                start_offset = self._track_offsets.get(track.path, 0.0)
                self._dragging_track = (
                    track.path, start_offset,
                    event.globalPosition().toPoint().x()
                )
                self.setCursor(Qt.ClosedHandCursor)
                event.accept()
                return

        # Приоритет 4: drag playhead
        if self._is_near_playhead(event.position().x()):
            self._dragging_playhead = True
            self.setCursor(Qt.SizeHorCursor)
            self.playhead_drag_started.emit()

    def mouseReleaseEvent(self, event):
        if self._dragging_track is not None:
            path, _, _ = self._dragging_track
            self._dragging_track = None
            self.setCursor(Qt.ArrowCursor)
            final_offset = self._track_offsets.get(path, 0.0)
            self.track_drag_finished.emit(path, final_offset)
            return

        if self._dragging_marker is not None:
            path, final_time = self._dragging_marker
            self._dragging_marker = None
            self.setCursor(Qt.ArrowCursor)
            self.marker_drag_finished.emit(path, final_time)
            return

        if self._dragging_playhead:
            self._dragging_playhead = False
            self.setCursor(Qt.ArrowCursor)
            self.playhead_drag_finished.emit()

    # Порог накопления дельты, чтобы один тик колеса = одно срабатывание.
    # На macOS трекпад шлёт малые дельты (1-30), поэтому без накопления
    # зум срабатывает от лёгкого касания.
    WHEEL_THRESHOLD = 120

    def wheelEvent(self, event):
        """Колесо на дорожке — зум с накоплением дельты (фикс чувствительности)."""
        # Определяем дорожку под курсором
        target_track = self._track_at(event.globalPosition().toPoint())
        if target_track is None:
            return super().wheelEvent(event)

        # Зум только для активной видео-дорожки. Аудио и неактивные — не зумим.
        if not target_track.is_focused() or target_track.track_type != "video":
            return super().wheelEvent(event)

        delta = event.angleDelta().y()
        if delta == 0:
            return super().wheelEvent(event)

        # Сброс накопителя, если курсор ушёл на другую дорожку
        if target_track.path != self._wheel_target_path:
            self._wheel_accumulator = 0
            self._wheel_target_path = target_track.path

        self._wheel_accumulator += delta

        # Срабатываем только когда накопилось на полный «тик» колеса
        if abs(self._wheel_accumulator) < self.WHEEL_THRESHOLD:
            event.accept()
            return

        direction = 1 if self._wheel_accumulator > 0 else -1
        self._wheel_accumulator = 0

        # Уже в фокусе — зум наружу; ещё нет — зум внутрь
        if direction > 0 and target_track.height() < TRACK_HEIGHT_FOCUS:
            target_track.set_height_by_zoom(TRACK_HEIGHT_FOCUS)
            for track, _ in self._tracks:
                if track is not target_track:
                    track.set_height_by_zoom(TRACK_HEIGHT_DIMMED)
            self._emit_height()
        elif direction < 0 and target_track.height() > TRACK_HEIGHT_NORMAL:
            target_track.set_height_by_zoom(TRACK_HEIGHT_NORMAL)
            for track, _ in self._tracks:
                if track is not target_track:
                    track.set_height_by_zoom(TRACK_HEIGHT_NORMAL)
            self._emit_height()

        event.accept()

    def leaveEvent(self, event):
        if (not self._dragging_playhead
                and self._dragging_marker is None
                and self._dragging_track is None):
            if self._tool_cursor is not None:
                self.setCursor(self._tool_cursor)
            else:
                self.setCursor(Qt.ArrowCursor)
        super().leaveEvent(event)

    # ── Совместимость ──

    def set_duration(self, seconds: float):
        if seconds > 0:
            self._total_duration = seconds
            self._update_widths()
            self._update_playhead()

    def set_empty(self, value: bool): pass
    def set_keyframes(self, times: list): pass
    def set_active_mode(self, mode: str): pass
    def set_audio_offset(self, offset: float): pass
    def set_video_offset(self, offset: float): pass
    def set_trim(self, start: float, end: float): pass
    def set_audio_trim(self, start: float, end: float): pass
    def set_durations(self, video_dur: float, audio_dur: float): pass
    def set_linked_mode(self, linked: bool): pass
    def set_draggable(self, value: bool): pass
    def set_source(self, path: str, duration: float): pass
    def clear(self): pass
