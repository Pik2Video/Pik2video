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
        self._cut_intervals = []           # list[(start, end)] — вырезаемые участки
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

        # Затемнённые cut-участки и метки
        if self.duration > 0:
            self._draw_cut_intervals(painter)
            self._draw_markers(painter)

        painter.setBrush(Qt.NoBrush)   # страховка: рамка не должна заливать содержимое
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self.duration <= 0:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignCenter, "пусто")

    def _draw_frames(self, painter):
        """Нарисовать кадры вдоль дорожки.

        При малой высоте (сжатая дорожка) — рисуем все кадры плотно (полоски).
        При большой высоте (зум) — рисуем МЕНЬШЕ кадров, чтобы они остались
        квадратными и занимали всю высоту. Кадры равномерно выбираются из всего набора.
        """
        w = self.width()
        h = self.height()
        total = len(self._frames)
        if total <= 0 or w <= 0 or h <= 0:
            return

        # Сколько кадров максимум может поместиться при квадратных кадрах высотой h
        max_visible = max(1, w // h)
        visible_count = min(total, max_visible)

        # Равномерная выборка: индексы из всего набора
        if visible_count >= total:
            indices = list(range(total))
        else:
            step = total / visible_count
            indices = [int(i * step) for i in range(visible_count)]

        cell_w = w / visible_count
        frame_w_int = max(1, int(min(cell_w, float(h))))

        for slot, idx in enumerate(indices):
            pixmap = self._frames[idx]
            if pixmap is None or pixmap.isNull():
                continue
            cell_center = (slot + 0.5) * cell_w
            frame_x = int(cell_center - frame_w_int / 2)
            target = QRect(frame_x, 0, frame_w_int, h)
            painter.drawPixmap(target, pixmap, pixmap.rect())

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

    def _draw_markers(self, painter):
        """Нарисовать метки в виде I-beam: линия по центру + стрелки сверху/снизу.

        Верхняя стрелка смотрит вниз (остриё к линии), нижняя — вверх (остриё к линии).
        Стрелки прижаты к краям дорожки. Линия между ними.
        """
        if not self._markers or self.duration <= 0:
            return
        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        from PySide6.QtGui import QPolygonF, QFont
        from PySide6.QtCore import QPointF

        marker_color = QColor("#ffcc00")  # Яркий золотисто-желтый
        line_pen = QPen(marker_color, 2)

        # Размер стрелок (высота треугольника) и полуширина основания
        tri_h = 4
        tri_half_w = 4

        # Линия от y=tri_h до y=h-tri_h (между стрелками). Минимум 1px.
        line_top = tri_h
        line_bottom = max(line_top + 1, h - tri_h)

        # Шрифт — только если хватает высоты (между стрелками хотя бы 12px)
        show_text = (line_bottom - line_top) >= 14
        if show_text:
            font = QFont("Menlo")
            font.setPointSize(min(10, (line_bottom - line_top) // 2))
            font.setBold(True)
            painter.setFont(font)

        for time_sec, kind in self._markers:
            x = int(w * time_sec / self.duration)

            # 1. Центральная линия
            painter.setPen(line_pen)
            painter.drawLine(x, line_top, x, line_bottom)

            # 2. Верхняя стрелка (смотрит вниз: основание вверху, остриё внизу)
            painter.setPen(Qt.NoPen)
            painter.setBrush(marker_color)
            top_poly = QPolygonF([
                QPointF(x - tri_half_w, 0),
                QPointF(x + tri_half_w, 0),
                QPointF(x, tri_h),
            ])
            painter.drawPolygon(top_poly)

            # 3. Нижняя стрелка (смотрит вверх: основание внизу, остриё вверху)
            bottom_poly = QPolygonF([
                QPointF(x - tri_half_w, h),
                QPointF(x + tri_half_w, h),
                QPointF(x, h - tri_h),
            ])
            painter.drawPolygon(bottom_poly)

            # 4. Текст внутри линии (если есть место)
            if show_text:
                painter.setPen(QColor("#000000"))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    painter.drawText(
                        QRect(x - 15 + dx, line_top + dy, 30, line_bottom - line_top),
                        Qt.AlignCenter, kind,
                    )
                painter.setPen(marker_color)
                painter.drawText(
                    QRect(x - 15, line_top, 30, line_bottom - line_top),
                    Qt.AlignCenter, kind,
                )

            # Сброс кисти — иначе следующая drawRect для рамки зальёт дорожку
            painter.setBrush(Qt.NoBrush)
