# src/pik2video/gui/editor/timeline/track.py
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

TRACK_HEIGHT_NORMAL = 12
TRACK_HEIGHT_DIMMED = 8

VIDEO_BG = "#3a3a3a"
VIDEO_BORDER = "#555555"
VIDEO_BG_FOCUS = "#4a4a4a"
VIDEO_BORDER_FOCUS = "#8a6f2a"

AUDIO_BG = "#1e3a1e"
AUDIO_BORDER = "#2a5a2a"
AUDIO_BG_FOCUS = "#2a5a2a"
AUDIO_BORDER_FOCUS = "#8a6f2a"

DIMMED_BG = "#1a1a1a"
DIMMED_BORDER = "#333333"


class TrackWidget(QWidget):
    """Одна дорожка. Только отрисовка — мышь ловит TimelineWidget."""

    def __init__(self, track_type: str, path: str = "", duration: float = 0.0, parent=None):
        super().__init__(parent)
        self.track_type = track_type
        self.path = path
        self.duration = duration

        self._is_focused = False
        self._is_dimmed = False
        self._current_height = TRACK_HEIGHT_NORMAL
        self._frames = []                  # list[QPixmap] для отрисовки превью
        self._markers = []                 # list[(time, kind)] — метки на дорожке
        self._cut_intervals = []           # list[(start, end)] — вырезаемые участки (для затемнения)
        self._display_intervals = []       # list[(s, e)] — видимые (после скрытия cut); пусто = всё видимо
        self.marker_btn = None             # QPushButton карандаша (для видео, назначается извне)
        self.setFixedHeight(self._current_height)

        # События мыши идут в родителя (TimelineWidget)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_focus(self, focused: bool):
        if self._is_focused == focused:
            return
        self._is_focused = focused
        self.update()

    def is_focused(self) -> bool:
        """Активна ли дорожка (клик по иконке)."""
        return self._is_focused

    def set_dimmed(self, dimmed: bool):
        if self._is_dimmed == dimmed:
            return
        self._is_dimmed = dimmed
        self.update()

    def set_duration(self, duration: float):
        self.duration = max(0.0, duration)
        self.update()

    def set_frames(self, frames: list):
        """Установить список кадров (QPixmap) для отрисовки на дорожке."""
        self._frames = frames or []
        self.update()

    def set_markers(self, markers: list, cut_intervals: list):
        """Установить метки и вырезаемые интервалы для отрисовки.

        markers — [(time_sec, kind), ...], kind ∈ {"[", "]", "]["}
        cut_intervals — [(start, end), ...] — затемняемые участки
        """
        self._markers = list(markers or [])
        self._cut_intervals = list(cut_intervals or [])
        self.update()

    def set_display_intervals(self, intervals: list):
        """Установить видимые интервалы (после скрытия cut). Пусто = всё видимо.

        intervals — [(s, e), ...] в реальных секундах файла.
        Используется для отрисовки: кадры и метки подтягиваются, на месте
        разрезов рисуются красные чёрточки.
        """
        self._display_intervals = list(intervals or [])
        self.update()

    def _display_duration(self) -> float:
        """Визуальная длина: сумма display_intervals, или duration если не заданы."""
        if not self._display_intervals:
            return self.duration
        return sum(e - s for s, e in self._display_intervals)

    def _real_to_x(self, real_sec: float) -> float:
        """Реальное время → X на дорожке (по визуальным интервалам)."""
        w = self.width()
        if w <= 0:
            return 0.0
        if not self._display_intervals:
            if self.duration <= 0:
                return 0.0
            return w * real_sec / self.duration

        disp_dur = self._display_duration()
        if disp_dur <= 0:
            return 0.0

        accumulated = 0.0
        for s, e in self._display_intervals:
            if real_sec < s - 0.001:
                # В скрытом cut → к началу текущего интервала
                return w * accumulated / disp_dur
            if real_sec <= e + 0.001:
                offset_in_seg = min(real_sec, e) - s
                return w * (accumulated + offset_in_seg) / disp_dur
            accumulated += e - s
        return float(w)

    def set_height_by_zoom(self, height: int):
        """Высота задаётся зумом (следующий этап)."""
        self._current_height = max(6, height)
        self.setFixedHeight(self._current_height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._is_dimmed:
            bg_color = QColor(DIMMED_BG)
            border_color = QColor(DIMMED_BORDER)
        elif self.track_type == "video":
            bg_color = QColor(VIDEO_BG_FOCUS if self._is_focused else VIDEO_BG)
            border_color = QColor(VIDEO_BORDER_FOCUS if self._is_focused else VIDEO_BORDER)
        else:
            bg_color = QColor(AUDIO_BG_FOCUS if self._is_focused else AUDIO_BG)
            border_color = QColor(AUDIO_BORDER_FOCUS if self._is_focused else AUDIO_BORDER)

        painter.fillRect(self.rect(), bg_color)

        # Кадры (если есть) — рисуем поверх фона, до рамки
        if self._frames and self.duration > 0:
            self._draw_frames(painter)

        # Красные чёрточки на месте разрезов (скрытые cut)
        if self._display_intervals:
            self._draw_gap_marks(painter)

        # Затемнённые cut-участки и метки (только если cut не скрыты)
        if self.duration > 0 and not self._display_intervals:
            self._draw_cut_intervals(painter)
        if self.duration > 0:
            self._draw_insertion_gaps(painter, bg_color)
            self._draw_markers(painter)

        painter.setBrush(Qt.NoBrush)   # страховка: рамка не должна заливать содержимое
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self.duration <= 0:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignCenter, "пусто")

    def _draw_frames(self, painter):
        """Нарисовать кадры вдоль дорожки.

        Если _display_intervals заданы — рисуем только видимые фрагменты
        (с подтяжкой: скрытые cut не занимают места).
        Иначе — как раньше, по всей ширине.
        """
        w = self.width()
        h = self.height()
        total = len(self._frames)
        if total <= 0 or w <= 0 or h <= 0 or self.duration <= 0:
            return

        if self._display_intervals:
            # Подтянутый режим: рисуем каждый интервал отдельно
            disp_dur = self._display_duration()
            if disp_dur <= 0:
                return
            for seg_start, seg_end in self._display_intervals:
                x_start = self._real_to_x(seg_start)
                x_end = self._real_to_x(seg_end)
                seg_w = max(1, int(x_end - x_start))
                # Индексы кадров, попадающих в интервал
                i_from = int(seg_start / self.duration * total)
                i_to = min(total, int(seg_end / self.duration * total) + 1)
                seg_frames = self._frames[i_from:i_to]
                if not seg_frames:
                    continue
                self._draw_frames_strip(painter, seg_frames, int(x_start), seg_w, h)
            return

        # Обычный режим: все кадры по всей ширине
        self._draw_frames_strip(painter, self._frames, 0, w, h)

    def _draw_frames_strip(self, painter, frames, x_offset: int, total_w: int, h: int):
        """Вспомогательная: нарисовать полосу кадров в указанной области."""
        total = len(frames)
        if total <= 0 or total_w <= 0:
            return
        max_visible = max(1, total_w // h)
        visible_count = min(total, max_visible)
        if visible_count >= total:
            indices = list(range(total))
        else:
            step = total / visible_count
            indices = [int(i * step) for i in range(visible_count)]
        cell_w = total_w / visible_count
        frame_w_int = max(1, int(min(cell_w, float(h))))
        for slot, idx in enumerate(indices):
            pixmap = frames[idx]
            if pixmap is None or pixmap.isNull():
                continue
            cell_center = (slot + 0.5) * cell_w
            frame_x = x_offset + int(cell_center - frame_w_int / 2)
            painter.drawPixmap(QRect(frame_x, 0, frame_w_int, h), pixmap, pixmap.rect())

    def _draw_gap_marks(self, painter):
        """Нарисовать красные чёрточки в местах разрезов (между фрагментами)."""
        if len(self._display_intervals) < 2 or self.duration <= 0:
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        from PySide6.QtGui import QPen, QColor
        pen = QPen(QColor("#ff3333"), 3)   # яркая красная, 3px
        painter.setPen(pen)

        disp_dur = self._display_duration()
        if disp_dur <= 0:
            return

        # Чёрточки между фрагментами: на стыке конца одного и начала следующего
        accumulated = 0.0
        for i, (s_seg, e_seg) in enumerate(self._display_intervals[:-1]):
            accumulated += e_seg - s_seg
            x = int(w * accumulated / disp_dur)
            # Вертикальная чёрточка по центру высоты
            margin = max(1, h // 6)
            painter.drawLine(x, margin, x, h - margin)

    def _draw_cut_intervals(self, painter):
        """Затемнить вырезаемые участки поверх кадров."""
        if not self._cut_intervals or self.duration <= 0:
            return
        w = self.width()
        if w <= 0:
            return

        for start, end in self._cut_intervals:
            x1 = int(w * start / self.duration)
            x2 = int(w * end / self.duration)
            if x2 <= x1:
                continue
            # Более плотное затемнение + красноватый оттенок для явности
            painter.fillRect(x1, 0, x2 - x1, self.height(), QColor(20, 10, 10, 190))

    def _draw_insertion_gaps(self, painter, bg_color):
        """Закрасить фоном зазоры (разрезы) для меток "]["]."""
        if not self._markers or self.duration <= 0:
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        # Зазор — половина ширины разреза от центра (симметрично)
        # Ограничен сверху (min 6), чтобы при зуме не разрастался слишком сильно
        gap_half = max(3, min(6, int(h * 0.10)))

        painter.setPen(Qt.NoPen)
        painter.setBrush(bg_color)
        for time_sec, kind in self._markers:
            if kind != "][":
                continue
            x = int(w * time_sec / self.duration)
            painter.drawRect(x - gap_half, 0, gap_half * 2, h)
        painter.setBrush(Qt.NoBrush)

    def _draw_markers(self, painter):
        """Нарисовать метки в виде скобок.

        Для "]" и "[" — одна скобка на позиции.
        Для "][" — ДВЕ скобки, разделённые зазором (разрез дорожки).
        Размер стрелок динамический — растёт вместе с высотой дорожки (зумом).
        """
        if not self._markers or self.duration <= 0:
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        from PySide6.QtGui import QPolygonF
        from PySide6.QtCore import QPointF

        marker_color = QColor("#ffcc00")  # Яркий золотисто-желтый
        line_pen = QPen(marker_color, 2)

        # Динамический размер стрелок
        tri_h = max(4, min(10, int(h * 0.25)))
        tri_half_w = max(3, min(8, int(h * 0.20)))

        # Линия заходит внутрь треугольников (на 1px), чтобы стык был монолитным
        line_top = max(0, tri_h - 1)
        line_bottom = min(h, h - tri_h + 1)

        # Зазор для меток "][" — половина ширины разреза
        # Синхронизировано с _draw_insertion_gaps
        gap_half = max(3, min(6, int(h * 0.10)))

        def draw_single_bracket(cx: int, kind: str):
            """Нарисовать одну скобку на позиции cx: "]" — левая, "[" — правая."""
            # Линия
            painter.setPen(line_pen)
            painter.drawLine(cx, line_top, cx, line_bottom)

            # Стрелки
            painter.setPen(Qt.NoPen)
            painter.setBrush(marker_color)

            if kind == "]":
                # Левая половина стрелок
                x_left_end = cx + 1
                painter.drawPolygon(QPolygonF([
                    QPointF(cx - tri_half_w, 0),
                    QPointF(x_left_end, 0),
                    QPointF(x_left_end, tri_h),
                ]))
                painter.drawPolygon(QPolygonF([
                    QPointF(cx - tri_half_w, h),
                    QPointF(x_left_end, h),
                    QPointF(x_left_end, h - tri_h),
                ]))
            elif kind == "[":
                # Правая половина стрелок
                x_right_start = cx - 1
                painter.drawPolygon(QPolygonF([
                    QPointF(x_right_start, 0),
                    QPointF(cx + tri_half_w, 0),
                    QPointF(x_right_start, tri_h),
                ]))
                painter.drawPolygon(QPolygonF([
                    QPointF(x_right_start, h),
                    QPointF(cx + tri_half_w, h),
                    QPointF(x_right_start, h - tri_h),
                ]))

            painter.setBrush(Qt.NoBrush)

        for time_sec, kind in self._markers:
            x = int(w * time_sec / self.duration)

            if kind == "][":
                # Две скобки с зазором
                draw_single_bracket(x - gap_half, "]")
                draw_single_bracket(x + gap_half, "[")
            elif kind == "]":
                draw_single_bracket(x, "]")
            elif kind == "[":
                draw_single_bracket(x, "[")

            painter.setBrush(Qt.NoBrush)
