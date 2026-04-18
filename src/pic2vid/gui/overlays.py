# src/pic2vid/gui/overlays.py

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QFont



''' 
ГРАФИЧЕСКОЕ ОКНО ДЛЯ УСТАНОВКИ КООРДИНАТ
Особенности:
- фиксированный вертикальный прямоугольник 9:16
- левый отступ и вертикальные отступы от краёв экрана
- минималистичный бейдж с размерами (W × H)
- мягкое затемнение фона
- плавное появление (fade-in)
- минимальный размер области при drag
'''

class CoordinateOverlay(QWidget):
    coords_selected = Signal(dict)

    FIXED_WIDTH = 540      # ширина прямоугольника
    FIXED_HEIGHT = 960     # высота прямоугольника
    LEFT_MARGIN = 180      # отступ слева
    VERTICAL_MARGIN = 80   # отступ сверху и снизу
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

        # Анимация плавного появления
        #self.setWindowOpacity(0.0)
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._fade_in_step)
        self._fade_step = 0.05

    # ПЕРЕДАЧА КООРДИНАТ (единая точка логики)
    def _emit_current_coords(self):
        """
        Формирует словарь координат из current_rect
        и передаёт их в CaptureSession через callback.
        """

        #print("[Overlay] Попытка отправить координаты")

        if not self.current_rect:
            print("[Overlay] current_rect отсутствует")
            return

        rect = self.current_rect

        coords = {
            "x1": rect.left(),
            "y1": rect.top(),
            "x2": rect.right(),
            "y2": rect.bottom(),
        }

        self.coords_selected.emit(coords)

    # ПОКАЗ ОКНА
    def showEvent(self, event):

        #print("[Overlay] showEvent вызван")

        # Получаем размеры экрана
        screen_geometry = self.screen().geometry()
        screen_width = screen_geometry.width()
        screen_height = screen_geometry.height()

        # Вычисляем доступную высоту с отступами
        available_height = screen_height - 2 * self.VERTICAL_MARGIN
        height = min(self.FIXED_HEIGHT, available_height)

        # Ширина через соотношение сторон 9:16
        ratio = 9 / 16
        width = int(height * ratio)
        width = min(width, screen_width - 2 * self.LEFT_MARGIN)  # проверка по ширине

        # Позиция прямоугольника
        x = self.LEFT_MARGIN
        y = self.VERTICAL_MARGIN + (available_height - height) // 2

        if not self.current_rect:
            self.current_rect = QRect(x, y, width, height)

            print("[Overlay] Начальная рамка захвата создана:", self.current_rect)

            # СРАЗУ передаём координаты стартовой рамки
            self._emit_current_coords()

        # Старт плавного появления
        self.setWindowOpacity(0.0)
        self._fade_timer.start(20)

        super().showEvent(event)

    # АНИМАЦИЯ ПОЯВЛЕНИЯ
    def _fade_in_step(self):
        current_opacity = self.windowOpacity()
        if current_opacity < 1.0:
            self.setWindowOpacity(min(1.0, current_opacity + self._fade_step))
        else:
            self._fade_timer.stop()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.setAttribute(Qt.WA_TransparentForMouseEvents, False)  # ловим мышь
            self.start_pos = event.pos()
            self.current_rect = QRect(self.start_pos, self.start_pos)
            self.update()

    def mouseMoveEvent(self, event):
        if self.start_pos:
            self.current_rect = QRect(self.start_pos, event.pos()).normalized()
            self.update()

    def mouseReleaseEvent(self, event):
        if self.start_pos and self.current_rect:
            #rect = self.current_rect

            # проверка минимального размера области
            if (self.current_rect.width() < self.MIN_WIDTH or
                self.current_rect.height() < self.MIN_HEIGHT):
                self.current_rect = None
                self.start_pos = None
                self.update()
                return

            # Передача координат через единый метод
            self._emit_current_coords()

        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)   # пропускаем клики
        self.clearFocus()
        self.start_pos = None

    def paintEvent(self, event):
        painter = QPainter(self)

        # мягкое затемнение всего экрана
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self.current_rect:
            # прозрачная область для выделения
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.fillRect(self.current_rect, Qt.transparent)

            # рамка выделения
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            pen = QPen(QColor("yellow"))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(self.current_rect)

            # минималистичный бейдж с размерами
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

            # фон под текст
            painter.fillRect(label_rect, QColor(0, 0, 0, 180))
            # текст
            painter.setPen(QColor("white"))
            painter.drawText(
                label_rect.adjusted(padding, padding, -padding, -padding),
                Qt.AlignLeft | Qt.AlignVCenter,
                text
            )


