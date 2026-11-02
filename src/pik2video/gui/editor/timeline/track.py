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
        self.setFixedHeight(self._current_height)

        # События мыши идут в родителя (TimelineWidget)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_focus(self, focused: bool):
        if self._is_focused == focused:
            return
        self._is_focused = focused
        self.update()

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

        painter.setPen(QPen(border_color, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self.duration <= 0:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignCenter, "пусто")

    def _draw_frames(self, painter):
        """Нарисовать N кадров вдоль дорожки. Каждый кадр центрирован в своей ячейке."""
        w = self.width()
        h = self.height()
        n = len(self._frames)
        if n <= 0 or w <= 0 or h <= 0:
            return

        cell_w = w / n
        # Ширина кадра: не больше ячейки и не больше высоты (чтобы кадр был квадратным)
        frame_w = min(cell_w, float(h))
        frame_w_int = max(1, int(frame_w))

        for i, pixmap in enumerate(self._frames):
            if pixmap is None or pixmap.isNull():
                continue
            cell_center = (i + 0.5) * cell_w
            frame_x = int(cell_center - frame_w_int / 2)
            target = QRect(frame_x, 0, frame_w_int, h)
            painter.drawPixmap(target, pixmap, pixmap.rect())
