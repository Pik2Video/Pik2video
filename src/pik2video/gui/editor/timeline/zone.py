# src/pik2video/gui/editor/timeline_zone.py
"""
Зона таймлайнов с общим ползунком.

Отвечает за:
- размещение видео- и аудио-дорожек в одной вертикальной зоне
- отрисовку единого ползунка поверх обеих дорожек
- обработку перетаскивания ползунка мышью

Ширина дорожек пропорциональна их длительностям относительно max(video, audio).
Ползунок один, позиция общая — из активного плеера.

Не знает:
- про плеер (получает позицию через set_position)
- про EditorState
- про экспорт
"""

import logging

from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from .seek_bar import SeekBar

logger = logging.getLogger(__name__)

CURSOR_COLOR = "#8b1a1a"          # тёмно-красный — цвет ползунка
CURSOR_WIDTH = 2                  # толщина линии в пикселях
CURSOR_HIT_WIDTH = 8              # ширина области захвата мыши вокруг линии
TRACK_MARGIN = 10                 # отступ дорожек от краёв виджета (совпадает с timeline.py)


class CursorOverlay(QWidget):
    """Прозрачный виджет поверх зоны. Только рисует ползунок — мышь не ловит."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)   # клики проходят насквозь

        self._duration = 0.0
        self._position = 0.0
        self._x_start = TRACK_MARGIN
        self._x_end = TRACK_MARGIN

    def set_range(self, x_start: int, x_end: int, duration: float):
        self._x_start = max(0, x_start)
        self._x_end = max(self._x_start, x_end)
        self._duration = max(0.0, duration)
        self.update()

    def set_position(self, seconds: float):
        self._position = max(0.0, seconds)
        self.update()

    def _cursor_x(self) -> int:
        if self._duration <= 0 or self._x_end <= self._x_start:
            return self._x_start
        ratio = max(0.0, min(1.0, self._position / self._duration))
        return int(self._x_start + (self._x_end - self._x_start) * ratio)

    def paintEvent(self, event):
        if self._duration <= 0 or self.width() <= 0:
            return
        x = self._cursor_x()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(CURSOR_COLOR), CURSOR_WIDTH)
        painter.setPen(pen)
        painter.drawLine(x, 0, x, self.height())


class TimelineZone(QWidget):
    """Зона таймлайнов: две дорожки + общий ползунок."""

    seek_requested = Signal(float)       # клик по полосе — разовый seek
    scrub_started = Signal()             # пользователь начал тянуть ползунок
    scrub_dragged = Signal(float, int)   # секунды, x-локальный — во время drag (для превью)
    scrub_finished = Signal()            # пользователь отпустил ползунок

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent; border: none;")

        self._video_dur = 0.0
        self._audio_dur = 0.0
        self._audio_offset = 0.0          # сдвиг аудио-дорожки (сек)
        self._video_offset = 0.0          # сдвиг видео-дорожки (сек)
        self._position = 0.0
        self._active_mode = "video"       # "video" | "audio" — определяет рабочую область
        self._linked_mode = True          # True = обе дорожки + seekbar; False = только активная
        self._w_video = 0                 # ширина видео-дорожки
        self._w_audio = 0                 # ширина аудио-дорожки

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Обёртка видео-дорожки: [spacer_left][timeline][stretch] ──
        self.video_row = QWidget()
        self.video_row.setStyleSheet("background: transparent; border: none;")
        vtl = QHBoxLayout(self.video_row)
        vtl.setContentsMargins(0, 0, 0, 0)
        vtl.setSpacing(0)
        self._video_layout = vtl
        self._video_spacer = QWidget()
        self._video_spacer.setFixedWidth(0)
        self._video_spacer.setStyleSheet("background: transparent; border: none;")
        vtl.addWidget(self._video_spacer, stretch=0)
        vtl.addStretch(1)
        layout.addWidget(self.video_row, stretch=0)

        # ── Обёртка аудио-дорожки: [spacer_left][timeline][stretch] ──
        self.audio_row = QWidget()
        self.audio_row.setStyleSheet("background: transparent; border: none;")
        atl = QHBoxLayout(self.audio_row)
        atl.setContentsMargins(0, 0, 0, 0)
        atl.setSpacing(0)
        self._audio_layout = atl
        self._audio_spacer = QWidget()
        self._audio_spacer.setFixedWidth(0)
        self._audio_spacer.setStyleSheet("background: transparent; border: none;")
        atl.addWidget(self._audio_spacer, stretch=0)
        atl.addStretch(1)
        layout.addWidget(self.audio_row, stretch=0)

        # ── Overlay с ползунком (создаём поверх, но geometry зададим в resize) ──
        self.cursor = CursorOverlay(self)
        self.cursor.hide()                # покажем после первой отрисовки

        # ── Полоска-скраббер между дорожками ──
        self.seek_bar = SeekBar()
        self.seek_bar.clicked_position.connect(self.seek_requested.emit)         # клик → разовый seek
        self.seek_bar.scrub_started.connect(self.scrub_started.emit)
        self.seek_bar.scrub_dragged.connect(self.scrub_dragged.emit)             # drag → превью (throttle)
        self.seek_bar.scrub_finished.connect(self.scrub_finished.emit)
        layout.insertWidget(layout.count() - 1, self.seek_bar, stretch=0)   # перед cursor

    # ── API ──

    def set_video_timeline(self, widget: QWidget):
        """Вставить видео-таймлайн после спейсера: [spacer][timeline][stretch]."""
        self._video_layout.insertWidget(1, widget, stretch=0)
        self._video_widget_ref = widget

    def set_audio_timeline(self, widget: QWidget):
        """Вставить аудио-таймлайн после спейсера: [spacer][timeline][stretch]."""
        self._audio_layout.insertWidget(1, widget, stretch=0)
        self._audio_widget_ref = widget

    def set_durations(self, video_dur: float, audio_dur: float):
        """Обновить длительности и пересчитать пропорции дорожек."""
        self._video_dur = max(0.0, video_dur)
        self._audio_dur = max(0.0, audio_dur)
        self._update_widths()

    def set_position(self, seconds: float):
        """Обновить позицию ползунка и скраббера."""
        self._position = max(0.0, seconds)
        self.cursor.set_position(seconds)
        self.seek_bar.set_position(seconds)

    def set_audio_offset(self, offset: float):
        """Задать сдвиг аудио-дорожки (сек)."""
        self._audio_offset = max(0.0, offset)
        self._update_widths()

    def set_video_offset(self, offset: float):
        """Задать сдвиг видео-дорожки (сек)."""
        self._video_offset = max(0.0, offset)
        self._update_widths()

    def set_linked_mode(self, linked: bool):
        """Включить/выключить связку дорожек. False = компактный режим (только активная)."""
        linked = bool(linked)
        if self._linked_mode == linked:
            return
        self._linked_mode = linked
        self._update_visibility()
        self._update_widths()

    def _update_visibility(self):
        """Управление видимостью дорожек и seekbar по режиму связки."""
        if self._linked_mode:
            self.video_row.show()
            self.audio_row.show()
            self.seek_bar.show()
        else:
            self.video_row.setVisible(self._active_mode == "video")
            self.audio_row.setVisible(self._active_mode == "audio")
            self.seek_bar.hide()

    def set_active_mode(self, mode: str):
        """Переключить режим ползунка: "video" или "audio"."""
        if mode not in ("video", "audio") or mode == self._active_mode:
            return
        self._active_mode = mode
        if not self._linked_mode:
            self._update_visibility()       # переключить видимую дорожку в компактном режиме
        self._update_widths()

    # ── Пересчёт ширин ──

    def _max_duration(self) -> float:
        """Общая длительность: max(конец видео, конец аудио) с учётом сдвигов."""
        end_video = self._video_dur + self._video_offset
        end_audio = self._audio_dur + self._audio_offset
        return max(end_video, end_audio)

    def _update_widths(self):
        """Обе дорожки одной ширины. Внутри — пропорциональное заполнение."""
        total = self.width()
        if total <= 0:
            return

        max_d = self._max_duration()
        usable = total - 2 * TRACK_MARGIN

        if not self._linked_mode:
            # Компактный режим: только активная дорожка на всю ширину, без offset
            w_video = total
            w_audio = total
            off_video_px = 0
            off_audio_px = 0
        elif max_d <= 0:
            # Пусто — обе дорожки на всю ширину (заглушки), без спейсеров
            w_video = total
            w_audio = total
            off_video_px = 0
            off_audio_px = 0
        else:
            if self._video_dur > 0:
                w_video = 2 * TRACK_MARGIN + int(usable * (self._video_dur / max_d))
            else:
                w_video = total
            if self._audio_dur > 0:
                w_audio = 2 * TRACK_MARGIN + int(usable * (self._audio_dur / max_d))
            else:
                w_audio = total

            off_video_px = int(usable * (self._video_offset / max_d)) if self._video_dur > 0 else 0
            off_audio_px = int(usable * (self._audio_offset / max_d)) if self._audio_dur > 0 else 0

        self._w_video = w_video
        self._w_audio = w_audio

        self._apply_width(self.video_row, self._video_layout, w_video)
        self._apply_width(self.audio_row, self._audio_layout, w_audio)

        self._video_spacer.setFixedWidth(off_video_px)
        self._audio_spacer.setFixedWidth(off_audio_px)

        self._update_cursor_range()

    def _update_cursor_range(self):
        """Пересчитать рабочую область ползунка в зависимости от активного режима."""
        W = self.width()
        if W <= 0:
            return

        max_d = self._max_duration()

        if not self._linked_mode:
            # Компактный режим: ползунок по всей ширине, шкала = активный файл
            if self._active_mode == "audio":
                dur = self._audio_dur
            else:
                dur = self._video_dur
            self.cursor.set_range(TRACK_MARGIN, W - TRACK_MARGIN, dur)
            self.cursor.set_position(self._position)
            # SeekBar скрыт — его обновлять не нужно, но зададим корректный диапазон на будущее
            self.seek_bar.set_range(TRACK_MARGIN, W - TRACK_MARGIN, dur)
            self.seek_bar.set_position(self._position)
            return

        if max_d <= 0:
            # Пусто — seek bar на всю ширину, ползунок невидим (duration 0)
            self.cursor.set_range(TRACK_MARGIN, W - TRACK_MARGIN, 0.0)
            self.cursor.set_position(0.0)
            self.seek_bar.set_range(TRACK_MARGIN, W - TRACK_MARGIN, 0.0)
            self.seek_bar.set_position(0.0)
            return

        if self._active_mode == "audio" and self._audio_dur > 0 and self._w_audio > 0:
            # область — только аудио-дорожка, с учётом её сдвига
            usable = W - 2 * TRACK_MARGIN
            off_audio_px = int(usable * (self._audio_offset / max_d))
            x_start = off_audio_px + TRACK_MARGIN
            x_end = off_audio_px + self._w_audio - TRACK_MARGIN
            dur = self._audio_dur
        else:
            # область — вся зона (режим video)
            x_start = TRACK_MARGIN
            x_end = W - TRACK_MARGIN
            dur = max_d

        self.cursor.set_range(x_start, x_end, dur)
        self.cursor.set_position(self._position)
        # SeekBar — всегда на всю ширину зоны, не зависит от режима
        self.seek_bar.set_range(TRACK_MARGIN, W - TRACK_MARGIN, max_d)
        self.seek_bar.set_position(self._position)

    def _apply_width(self, row: QWidget, layout: QHBoxLayout, width: int):
        """Задать фиксированную ширину дорожке (не спейсеру)."""
        ref = getattr(self, "_video_widget_ref", None) if row is self.video_row else getattr(self, "_audio_widget_ref", None)
        if ref is not None:
            ref.setFixedWidth(max(1, width))

    # ── Layout / resize ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.cursor.setGeometry(0, 0, self.width(), self.height())
        self.cursor.raise_()
        self.cursor.show()
        self._update_widths()

    def showEvent(self, event):
        super().showEvent(event)
        self.cursor.setGeometry(0, 0, self.width(), self.height())
        self.cursor.raise_()
        self.cursor.show()
        self._update_widths()