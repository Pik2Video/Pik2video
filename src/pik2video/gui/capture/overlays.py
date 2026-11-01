# src/pik2video/gui/capture/overlays.py

import logging

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from src.pik2video.gui.common.blink_style import (
    OVERLAY_ALPHA_BRIGHT,
    OVERLAY_ALPHA_DIM,
    lerp_alpha,
)

logger = logging.getLogger(__name__)


class CoordinateOverlay(QWidget):
    """
    Оверлей выбора области записи.

    Поведение курсора:
    - fullscreen (пресет «весь экран») — крестик, рисование новой области;
    - курсор внутри пресета — рука, перетаскивание пресета;
    - курсор снаружи пресета — крестик, рисование новой области.
    """

    coords_selected = Signal(dict)      # рисование — пресет сбрасывается
    region_moved = Signal(dict)         # перетаскивание — пресет остаётся
    drag_started = Signal()
    drag_finished = Signal()
    invalid_coords = Signal()           # пустой клик — координаты не изменены

    MIN_WIDTH = 50
    MIN_HEIGHT = 50

    def __init__(self):
        super().__init__()

        self.setFocusPolicy(Qt.NoFocus)
        self.setMouseTracking(True)   # mouseMoveEvent работает без зажатой кнопки

        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.Window |
            Qt.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        # Текущий прямоугольник (может быть в процессе рисования)
        self.current_rect: QRect | None = None
        # Последний валидный прямоугольник (пресет или ручная зона)
        self._saved_rect: QRect | None = None

        # Состояние drag: None | "drawing" | "region"
        self._dragging: str | None = None
        # Начальная точка рисования (для "drawing")
        self.start_pos: QPoint | None = None
        # Начальная точка перетаскивания (для "region")
        self._drag_start: QPoint = QPoint()
        # Исходный прямоугольник на момент начала перетаскивания
        self._drag_rect_origin: QRect = QRect()

        # Анимация плавного появления
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_in_step)
        self._fade_step = 0.05

        self._blink_phase = 1.0

    # ─────────────────────────────────────────
    # Сигналы наружу
    # ─────────────────────────────────────────

    def _emit_current_coords(self):
        if not self.current_rect:
            logger.warning("current_rect отсутствует")
            return
        r = self.current_rect
        coords = {
            "x1": r.left(),
            "y1": r.top(),
            "x2": r.right(),
            "y2": r.bottom(),
        }
        self.coords_selected.emit(coords)

    def set_region(self, coords: dict):
        """Установить область извне (из пресета)."""
        x1 = coords.get("x1")
        y1 = coords.get("y1")
        x2 = coords.get("x2")
        y2 = coords.get("y2")

        if x1 is None or y1 is None or x2 is None or y2 is None:
            logger.error("Ошибка: некорректные координаты")
            return

        self.current_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        self._saved_rect = QRect(self.current_rect)
        self.update()

        logger.debug(f"Область обновлена из пресета: {self.current_rect}")

    def set_blink_phase(self, phase: float):
        self._blink_phase = max(0.0, min(1.0, phase))
        self.update()

    # ─────────────────────────────────────────
    # Показ окна
    # ─────────────────────────────────────────

    def showEvent(self, event):
        self.setWindowOpacity(0.0)
        self._fade_timer.start(20)
        super().showEvent(event)

    def _fade_in_step(self):
        current_opacity = self.windowOpacity()
        if current_opacity < 1.0:
            self.setWindowOpacity(min(1.0, current_opacity + self._fade_step))
        else:
            self._fade_timer.stop()

    # ─────────────────────────────────────────
    # Вспомогательные проверки
    # ─────────────────────────────────────────

    def _is_full_screen(self) -> bool:
        """True, если рабочая зона = весь виджет (= весь экран)."""
        if self._saved_rect is None:
            return True
        return self._saved_rect == self.rect()

    def _point_inside(self, pos: QPoint) -> bool:
        """Точка внутри последнего валидного прямоугольника."""
        if self._saved_rect is None:
            return False
        return self._saved_rect.contains(pos)

    def _clamp_rect(self, rect: QRect) -> QRect:
        """Ограничить прямоугольник границами виджета (без изменения размера)."""
        r = self.rect()
        max_x = r.width() - rect.width()
        max_y = r.height() - rect.height()
        x = max(0, min(rect.left(), max_x))
        y = max(0, min(rect.top(), max_y))
        return QRect(x, y, rect.width(), rect.height())

    def cursor_for_position(self, pos: QPoint) -> Qt.CursorShape:
        """Какой курсор нужен для точки pos. Вызывается из CursorManager.

        Логика:
        - drag пресета → ClosedHand (сжатая рука);
        - drag рисования → Cross;
        - fullscreen → Cross (рисовать новую область);
        - внутри пресета → OpenHand (перетаскивать);
        - снаружи → Cross (рисовать новую область).
        """
        if self._dragging == "region":
            return Qt.ClosedHandCursor
        if self._dragging == "drawing":
            return Qt.CrossCursor
        if self._is_full_screen():
            return Qt.CrossCursor
        if self._point_inside(pos):
            return Qt.OpenHandCursor
        return Qt.CrossCursor

    # ─────────────────────────────────────────
    # Мышь
    # ─────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        pos = event.pos()

        if self._is_full_screen() or not self._point_inside(pos):
            # Рисование новой области
            self._dragging = "drawing"
            self.start_pos = pos
            self.current_rect = QRect(pos, pos)
        else:
            # Перетаскивание пресета
            self._dragging = "region"
            self._drag_start = pos
            self._drag_rect_origin = QRect(self._saved_rect)

        self.drag_started.emit()
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.pos()

        if self._dragging == "region":
            delta = pos - self._drag_start
            new_rect = self._drag_rect_origin.translated(delta)
            new_rect = self._clamp_rect(new_rect)
            self.current_rect = new_rect
            self.update()
            return

        if self._dragging == "drawing":
            self.current_rect = QRect(self.start_pos, pos).normalized()
            self.update()
            return

        # Нет drag — курсор обновляется через CursorManager

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return

        if self._dragging == "drawing":
            if self.start_pos and self.current_rect:
                if (self.current_rect.width() < self.MIN_WIDTH or
                        self.current_rect.height() < self.MIN_HEIGHT):
                    self.current_rect = QRect(self._saved_rect) if self._saved_rect else None
                    self.invalid_coords.emit()
                else:
                    self._saved_rect = QRect(self.current_rect)
                    self._emit_current_coords()
            self.start_pos = None

        elif self._dragging == "region":
            if (self.current_rect and
                    self.current_rect.width() >= self.MIN_WIDTH and
                    self.current_rect.height() >= self.MIN_HEIGHT):
                self._saved_rect = QRect(self.current_rect)
                self._emit_region_moved()
            else:
                self.current_rect = QRect(self._saved_rect) if self._saved_rect else None
                self.invalid_coords.emit()

        self._dragging = None
        self.clearFocus()
        self.update()
        self.drag_finished.emit()

    def _emit_region_moved(self):
        if not self.current_rect:
            return
        r = self.current_rect
        coords = {
            "x1": r.left(),
            "y1": r.top(),
            "x2": r.right(),
            "y2": r.bottom(),
        }
        self.region_moved.emit(coords)


    # ─────────────────────────────────────────
    # Отрисовка
    # ─────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if not self.current_rect:
            return

        painter.setCompositionMode(QPainter.CompositionMode_Clear)
        painter.fillRect(self.current_rect, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        alpha = lerp_alpha(self._blink_phase, OVERLAY_ALPHA_DIM, OVERLAY_ALPHA_BRIGHT)
        pen_color = QColor(255, 255, 255, alpha)
        pen = QPen(pen_color, 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(self.current_rect)

        # Бейдж с размерами
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
            self.current_rect.top() - text_rect.height() - padding * 2,
            text_rect.width() + padding * 2,
            text_rect.height() + padding * 2,
        )

        painter.fillRect(label_rect, QColor(0, 0, 0, 180))
        painter.setPen(QColor("white"))
        painter.drawText(
            label_rect.adjusted(padding, padding, -padding, -padding),
            Qt.AlignLeft | Qt.AlignVCenter,
            text,
        )


class RecordingFrame(QWidget):
    """Серебристая рамка вокруг области захвата во время записи.

    Отдельное top-level окно. Создаётся один раз (прогрев при старте),
    потом только show()/hide() — без setWindowFlags в цепочке START,
    чтобы запись стартовала мгновенно.

    Не перехватывает клики (WindowTransparentForInput), не забирает фокус,
    не скрывается при деактивации приложения (Qt.Window, не Qt.Tool).
    """

    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.Window
            | Qt.WindowStaysOnTopHint
            | Qt.WindowDoesNotAcceptFocus
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._region: dict | None = None

    def set_region(self, region: dict):
        if not region:
            self._region = None
            return
        self._region = dict(region)

        padding = 2
        self.setGeometry(
            int(region["left"]) - padding,
            int(region["top"]) - padding,
            int(region["width"]) + 2 * padding,
            int(region["height"]) + 2 * padding,
        )
        self.update()

    def paintEvent(self, event):
        if not self._region:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(192, 192, 192, 230), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        padding = 2
        rect = QRect(
            padding,
            padding,
            max(0, self.width() - 2 * padding),
            max(0, self.height() - 2 * padding),
        )
        painter.drawRect(rect)
