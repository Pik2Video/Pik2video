# src/pik2video/gui/capture/overlays.py

import logging

from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.pik2video.gui.common.blink_style import (
    OVERLAY_ALPHA_BRIGHT,
    OVERLAY_ALPHA_DIM,
    lerp_alpha,
)

logger = logging.getLogger(__name__)

''' 
ГРАФИЧЕСКОЕ ОКНО ДЛЯ УСТАНОВКИ КООРДИНАТ
Особенности:
- фиксированный вертикальный прямоугольник 9:16
- левый отступ и вертикальные отступы от краёв экрана
- минималистичный бейдж с размерами (W × H)
- мягкое затемнение фона
- плавное появление (fade-in)
- минимальный размер области при drag
- анимация появления рамки из верхнего левого угла
'''

class CoordinateOverlay(QWidget):
    coords_selected = Signal(dict)
    drag_started = Signal()
    drag_finished = Signal()

    MIN_WIDTH = 50         # минимальная ширина при drag
    MIN_HEIGHT = 50        # минимальная высота при drag

    def __init__(self):
        
        super().__init__()

        self.setFocusPolicy(Qt.NoFocus)

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowDoesNotAcceptFocus  # Не забирает фокус
        )

        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)  # Не активируется при показе

        # Начальная позиция мыши
        self.start_pos = None
        # Прямоугольник (будет задан при showEvent)
        self.current_rect = None

        # Анимация плавного появления (затемнения)
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_in_step)
        self._fade_step = 0.05

        self._blink_phase = 1.0    # 0.0 = тусклая, 1.0 = яркая

    # ПЕРЕДАЧА КООРДИНАТ
    def _emit_current_coords(self):
        """Формирует словарь координат из current_rect и передаёт их"""
        if not self.current_rect:
            logger.warning("current_rect отсутствует")
            return

        rect = self.current_rect
        coords = {
            "x1": rect.left(),
            "y1": rect.top(),
            "x2": rect.right(),
            "y2": rect.bottom(),
        }
        self.coords_selected.emit(coords)

    def set_region(self, coords: dict):
        """Устанавливает область выделения извне (из пресетов)"""
        x1 = coords.get("x1")
        y1 = coords.get("y1")
        x2 = coords.get("x2")
        y2 = coords.get("y2")
        
        if x1 is None or y1 is None or x2 is None or y2 is None:
            logger.error("Ошибка: некорректные координаты")
            return
        
        # Устанавливаем новую рамку
        self.current_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        self.update()


        logger.debug(f"Область обновлена из пресета: {self.current_rect}")

    def set_blink_phase(self, phase: float):
        """Установить фазу мигания рамки (0.0 … 1.0)."""
        self._blink_phase = max(0.0, min(1.0, phase))
        self.update()
    

    # ПОКАЗ ОКНА
    def showEvent(self, event):
        # Старт анимации затемнения
        self.setWindowOpacity(0.0)
        self._fade_timer.start(20)

        super().showEvent(event)

    # АНИМАЦИЯ ПОЯВЛЕНИЯ (ЗАТЕМНЕНИЕ)
    def _fade_in_step(self):
        current_opacity = self.windowOpacity()
        if current_opacity < 1.0:
            self.setWindowOpacity(min(1.0, current_opacity + self._fade_step))
        else:
            self._fade_timer.stop()

    # ОБРАБОТКА МЫШИ
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.start_pos = event.pos()
            self.current_rect = QRect(self.start_pos, self.start_pos)
            self.update()
            self.drag_started.emit()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_rect = QRect(self.start_pos, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start_pos and self.current_rect:
            if (self.current_rect.width() < self.MIN_WIDTH or
                self.current_rect.height() < self.MIN_HEIGHT):
                self.current_rect = None
            else:
                self._emit_current_coords()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.clearFocus()
        self.start_pos = None
        self.update()

        self.drag_finished.emit()

    # ОТРИСОВКА
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.current_rect:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.current_rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

            # ── Рамка вокруг области (с учётом мигания) ──
            alpha = lerp_alpha(self._blink_phase, OVERLAY_ALPHA_DIM, OVERLAY_ALPHA_BRIGHT)
            pen_color = QColor(255, 255, 255, alpha)
            pen = QPen(pen_color, 2)

            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self.current_rect)

            # бейдж с размерами
            width = self.current_rect.width()
            height = self.current_rect.height()
            text = f"{width} × {height}"

            font = QFont("Arial", 12)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            text_rect = metrics.boundingRect(text)
            padding = 6

            label_rect = QRect(
                self.current_rect.left(),
                self.current_rect.top() - text_rect.height() - padding*2,
                text_rect.width() + padding*2,
                text_rect.height() + padding*2
            )

            painter.fillRect(label_rect, QColor(0, 0, 0, 180))
            painter.setPen(QColor("white"))
            painter.drawText(
                label_rect.adjusted(padding, padding, -padding, -padding),
                Qt.AlignLeft | Qt.AlignVCenter,
                text
            )
