# src/pik2video/gui/overlays.py

import logging

from PySide6.QtWidgets import QWidget, QRubberBand
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont

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

    #FIXED_WIDTH = 540      # ширина прямоугольника
    #FIXED_HEIGHT = 960     # высота прямоугольника
    #LEFT_MARGIN = 180      # отступ слева
    #VERTICAL_MARGIN = 80   # отступ сверху и снизу
    MIN_WIDTH = 50         # минимальная ширина при drag
    MIN_HEIGHT = 50        # минимальная высота при drag
    
    # 🆕 НАСТРОЙКИ АНИМАЦИИ (ЗДЕСЬ МЕНЯТЬ)
    ANIMATION_START_MARGIN = 50      # отступ от краёв (пиксели)
    ANIMATION_END_WIDTH_PERCENT = 88  # ← ширина 60% от ширины экрана
    ANIMATION_END_HEIGHT_PERCENT = 70 # ← высота 50% от высоты экрана
    ANIMATION_SPEED = 18             # скорость анимации



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

        # 🆕 АНИМАЦИЯ ПОЯВЛЕНИЯ РАМКИ
        self._anim_rect = None          # текущий анимированный прямоугольник
        self._target_rect = None        # целевой прямоугольник (конечный)
        self._anim_timer = QTimer(self)
        self._anim_timer.timeout.connect(self._update_animation)
        
        # Создаём резиновую рамку
        self.rubber_band = QRubberBand(QRubberBand.Rectangle, self)
        self.rubber_band.hide()

    # 🆕 МЕТОД ДЛЯ АНИМАЦИИ ПОЯВЛЕНИЯ РАМКИ
    def start_frame_animation(self, target_rect):
        """
        Запускает анимацию появления рамки.
        Рамка начинает рисоваться из верхнего левого угла с отступом ANIMATION_START_MARGIN
        и растёт до целевого размера.
        """
        screen = self.screen().geometry()
        
        start_x = screen.left() + self.ANIMATION_START_MARGIN
        start_y = screen.top() + self.ANIMATION_START_MARGIN
        
        end_width = int(screen.width() * self.ANIMATION_END_WIDTH_PERCENT / 100)
        end_height = int(screen.height() * self.ANIMATION_END_HEIGHT_PERCENT / 100)
        
        self._target_rect = QRect(start_x, start_y, end_width, end_height)
        self._anim_rect = QRect(start_x, start_y, 1, 1)
        
        self.rubber_band.setGeometry(self._anim_rect)
        self.rubber_band.show()
        self._anim_timer.start(self.ANIMATION_SPEED)


    def _update_animation(self):
        """Обновляет анимацию: плавно увеличивает рамку до целевого размера"""
        if not self._anim_rect or not self._target_rect:
            self._anim_timer.stop()
            return
        
        # Текущие координаты
        x1 = self._anim_rect.left()
        y1 = self._anim_rect.top()
        x2 = self._anim_rect.right()
        y2 = self._anim_rect.bottom()
        
        # Целевые координаты
        tx1 = self._target_rect.left()
        ty1 = self._target_rect.top()
        tx2 = self._target_rect.right()
        ty2 = self._target_rect.bottom()
        
        # Плавно приближаемся (скорость 10% за кадр)
        new_x1 = x1 + (tx1 - x1) * 0.15
        new_y1 = y1 + (ty1 - y1) * 0.15
        new_x2 = x2 + (tx2 - x2) * 0.15
        new_y2 = y2 + (ty2 - y2) * 0.15
        
        # Округляем до целых
        new_rect = QRect(
            int(new_x1),
            int(new_y1),
            int(new_x2 - new_x1),
            int(new_y2 - new_y1)
        )
        
        # Обновляем rubber band
        self.rubber_band.setGeometry(new_rect)
        self._anim_rect = new_rect
        
        # Если достигли цели с точностью до 2 пикселей — останавливаем
        if (abs(new_x1 - tx1) < 2 and abs(new_y1 - ty1) < 2 and
            abs(new_x2 - tx2) < 2 and abs(new_y2 - ty2) < 2):
            
            # Устанавливаем финальный прямоугольник
            self.rubber_band.setGeometry(self._target_rect)
            self.current_rect = self._target_rect
            self._anim_timer.stop()
            self._anim_rect = None
            self._target_rect = None
            self.update()

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

        # Останавливаем анимацию
        self._anim_timer.stop()
        self._anim_rect = None
        self._target_rect = None
        
        # Устанавливаем новую рамку
        self.current_rect = QRect(x1, y1, x2 - x1, y2 - y1)
        self.rubber_band.setGeometry(self.current_rect)
        self.rubber_band.show()
        self.update()


        logger.debug(f"Область обновлена из пресета: {self.current_rect}")
    

    # ПОКАЗ ОКНА
    def showEvent(self, event):
        # Старт анимации затемнения
        self.setWindowOpacity(0.0)
        self._fade_timer.start(20)

        super().showEvent(event)
        
        # Запускаем анимацию рамки
        self.start_frame_animation(None)

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
            # Останавливаем анимацию рамки
            self._anim_timer.stop()
            
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            self.start_pos = event.pos()
            self.current_rect = QRect(self.start_pos, self.start_pos)
            self.rubber_band.setGeometry(self.current_rect)
            self.rubber_band.show()
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_rect = QRect(self.start_pos, event.pos()).normalized()
            self.rubber_band.setGeometry(self.current_rect)
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start_pos and self.current_rect:
            if (self.current_rect.width() < self.MIN_WIDTH or
                self.current_rect.height() < self.MIN_HEIGHT):
                self.current_rect = None
                self.start_pos = None
                self.rubber_band.hide()
                self.update()
                return

            self._emit_current_coords()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.clearFocus()
        self.start_pos = None
        self.rubber_band.hide()

    # ОТРИСОВКА
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.current_rect:
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.current_rect, Qt.transparent)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

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