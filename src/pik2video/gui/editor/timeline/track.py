# src/pik2video/gui/editor/timeline/track.py
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

TRACK_HEIGHT_NORMAL = 12
TRACK_HEIGHT_FOCUS = 60
TRACK_HEIGHT_DIMMED = 8

class TrackWidget(QWidget):
    """Одна дорожка (видео или аудио)."""
    
    seek_requested = Signal(float) # клик по дорожке -> секунды
    
    def __init__(self, track_type: str, path: str = "", duration: float = 0.0, parent=None):
        super().__init__(parent)
        self.track_type = track_type
        self.path = path
        self.duration = duration
        
        self._is_focused = False
        self._is_dimmed = False
        self._current_height = TRACK_HEIGHT_NORMAL
        self.setFixedHeight(self._current_height)
        self.setMouseTracking(True)

    def set_focus(self, focused: bool):
        self._is_focused = focused
        self._is_dimmed = False
        self._current_height = TRACK_HEIGHT_FOCUS if focused else TRACK_HEIGHT_NORMAL
        self.setFixedHeight(self._current_height)
        self.update()

    def set_dimmed(self, dimmed: bool):
        self._is_dimmed = dimmed
        self._is_focused = False
        self._current_height = TRACK_HEIGHT_DIMMED if dimmed else TRACK_HEIGHT_NORMAL
        self.setFixedHeight(self._current_height)
        self.update()

    def set_duration(self, duration: float):
        self.duration = max(0.0, duration)
        self.update()

    def _x_to_seconds(self, x: float) -> float:
        if self.width() <= 0 or self.duration <= 0:
            return 0.0
        ratio = max(0.0, min(1.0, x / self.width()))
        return ratio * self.duration

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.duration > 0:
            seconds = self._x_to_seconds(event.position().x())
            self.seek_requested.emit(seconds)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Фон дорожки
        if self.track_type == "video":
            bg_color = QColor("#3a3a3a")
            border_color = QColor("#555555")
        else:
            bg_color = QColor("#1e3a1e") # Зеленоватый для аудио
            border_color = QColor("#2a5a2a")

        if self._is_dimmed:
            bg_color = QColor("#1a1a1a")
            border_color = QColor("#333333")

        painter.fillRect(self.rect(), bg_color)
        painter.setPen(QPen(border_color, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        # Если дорожка не загружена, показываем тусклую заглушку
        if self.duration <= 0:
            painter.setPen(QColor("#555555"))
            painter.drawText(self.rect(), Qt.AlignCenter, "пусто")
            return

        # Пока просто заливка, миниатюры добавим позже
        if self._is_focused:
            painter.setPen(QColor("#888888"))
            painter.drawText(self.rect(), Qt.AlignCenter, f"{self.path.split('/')[-1]} ({self.duration:.1f}с)")
