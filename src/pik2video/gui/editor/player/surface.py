# src/pik2video/gui/editor/preset_frame.py
"""
Оверлей рабочей зоны кадра и поверхность отрисовки видео.

VideoSurface:
  - при canvas_ar is None (пресет original) — видео целиком, fit в widget
  - при canvas_ar is not None (другие пресеты) — canvas с видео (pad или crop
    в зависимости от текущего crop_rect)

PresetFrame:
  - при canvas_ar is None — затенение вне crop_rect + белая рамка (ручная обрезка)
  - при canvas_ar is not None — только белая рамка по границе canvas

В режиме original ловит мышь для ручного рисования crop_rect.
"""

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt, Signal

from src.pik2video.gui.common.blink_style import (
    lerp_alpha,
    OVERLAY_ALPHA_BRIGHT,
    OVERLAY_ALPHA_DIM,
)
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QWidget


DIM_COLOR = QColor(0, 0, 0, 128)            # затемнение 50%
BORDER_COLOR = QColor(255, 255, 255, 230)   # белая рамка
PREVIEW_COLOR = QColor(212, 168, 67, 220)   # золотистый пунктир во время drag
PREVIEW_FILL = QColor(212, 168, 67, 40)

MIN_DRAW_PX = 5                             # меньше — считаем случайным кликом


def _fit_rect(inner: tuple, outer_w: int, outer_h: int) -> QRect:
    """Прямоугольник AR inner, вписанный в outer. Центрирован."""
    iw, ih = inner
    if iw <= 0 or ih <= 0 or outer_w <= 0 or outer_h <= 0:
        return QRect()
    size = QSize(int(iw), int(ih)).scaled(outer_w, outer_h, Qt.KeepAspectRatio)
    return QRect(
        (outer_w - size.width()) // 2,
        (outer_h - size.height()) // 2,
        size.width(),
        size.height(),
    )


class VideoSurface(QWidget):
    """Отрисовка кадра: при пресете — canvas с видео, при original — fit."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # WA_TranslucentBackground вместо WA_OpaquePaintEvent:
        # иначе полупрозрачный фон вокруг canvas не сработает — под ним
        # окажется чёрный прямоугольник виджета.
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._image: QImage | None = None
        self._crop_rect: tuple = (0.0, 0.0, 0.0, 0.0)   # (x, y, w, h) в координатах источника
        self._source_size: tuple = (0, 0)
        self._canvas_ar: tuple | None = None

    def set_image(self, image: QImage):
        self._image = image
        self.update()

    def clear_image(self):
        self._image = None
        self.update()

    def set_crop_rect(self, rect: tuple, source_size: tuple):
        self._crop_rect = tuple(rect)
        self._source_size = tuple(source_size)
        self.update()

    def set_canvas_ar(self, ar):
        self._canvas_ar = ar
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        # Чисто чёрный фон: граница видео (где оно заканчивается) сливается с фоном,
        # и не создаёт иллюзию "второй рамки".
        painter.fillRect(self.rect(), QColor("#000000"))
        if not self._image:
            return

        sw, sh = self._source_size
        if sw <= 0 or sh <= 0:
            return

        # original: видео целиком, fit в widget
        if self._canvas_ar is None:
            size = QSize(sw, sh).scaled(self.width(), self.height(), Qt.KeepAspectRatio)
            x = (self.width() - size.width()) // 2
            y = (self.height() - size.height()) // 2
            painter.drawImage(QRect(x, y, size.width(), size.height()), self._image)
            return

        cx, cy, cw, ch = self._crop_rect
        if cw <= 0 or ch <= 0:
            return

        # 1. Canvas = AR пресета, вписанный в widget, сдвинутый на offset
        canvas_center = _fit_rect(self._canvas_ar, self.width(), self.height())
        if canvas_center.isNull():
            return

        # Сдвиг рамки в пикселях widget
        scale_canvas = canvas_center.width() / cw
        shift_src = cx - (sw - cw) / 2.0
        shift_px = shift_src * scale_canvas

        # clamp: не даём canvas выйти за widget
        max_cx = self.width() - canvas_center.width() - canvas_center.x()
        min_cx = -canvas_center.x()
        clamped_offset = max(min_cx, min(max_cx, shift_px))

        canvas = QRectF(
            canvas_center.x() + clamped_offset,
            canvas_center.y(),
            canvas_center.width(),
            canvas_center.height(),
        )

        # 2. Масштаб исходного видео относительно canvas
        sx = canvas.width() / cw
        sy = canvas.height() / ch

        # 3. Координаты всего видео на экране (оно может выходить за пределы canvas)
        vx = canvas.x() - cx * sx
        vy = canvas.y() - cy * sy
        vw = sw * sx
        vh = sh * sy

        # 4. Рисуем всё видео (оно может выходить за пределы canvas)
        painter.setClipRect(self.rect())
        painter.drawImage(QRectF(vx, vy, vw, vh), self._image)
        painter.setClipping(False)

        # 5. Затеняем всё, что вне canvas
        w, h = self.width(), self.height()
        DIM = QColor(0, 0, 0, 120)
        painter.fillRect(QRectF(0, 0, w, canvas.top()), DIM)
        painter.fillRect(QRectF(0, canvas.bottom(), w, h - canvas.bottom()), DIM)
        painter.fillRect(QRectF(0, canvas.top(), canvas.left(), canvas.height()), DIM)
        painter.fillRect(QRectF(canvas.right(), canvas.top(), w - canvas.right(), canvas.height()), DIM)

        # 6. Внутри canvas: закрашиваем черным (для полос), затем рисуем видимую часть
        painter.fillRect(canvas, QColor("black"))

        vx0 = max(0.0, cx)
        vy0 = max(0.0, cy)
        vx1 = min(float(sw), cx + cw)
        vy1 = min(float(sh), cy + ch)
        if vx1 <= vx0 or vy1 <= vy0:
            return

        wx0 = (vx0 - cx) * sx
        wy0 = (vy0 - cy) * sy
        ww = (vx1 - vx0) * sx
        wh = (vy1 - vy0) * sy

        painter.setClipRect(canvas)
        painter.drawImage(
            QRectF(canvas.x() + wx0, canvas.y() + wy0, ww, wh),
            self._image,
            QRectF(vx0, vy0, vx1 - vx0, vy1 - vy0),
        )
        painter.setClipping(False)


class PresetFrame(QWidget):
    """Оверлей: затенение вне рабочей зоны (original) или рамка canvas (пресет)."""

    crop_rect_drawn = Signal(QRect)   # QRect в координатах источника

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._crop_rect: tuple = (0.0, 0.0, 0.0, 0.0)
        self._source_size: tuple = (0, 0)
        self._canvas_ar: tuple | None = None
        self._blink_phase: float = 1.0  # 0..1, управляется из EditorWindow при активном карандаше

        self._drawing_enabled = False
        self._dragging = False
        self._drag_start = QPoint()
        self._drag_preview: QRect | None = None

    # ── API ──

    def set_crop_rect(self, rect: tuple, source_size: tuple):
        self._crop_rect = tuple(rect)
        self._source_size = tuple(source_size)
        self.update()

    def set_canvas_ar(self, ar):
        self._canvas_ar = ar
        self.update()

    def set_blink_phase(self, phase: float):
        """Фаза мигания 0..1. 1.0 — яркая (по умолчанию), 0.0 — тусклая."""
        phase = max(0.0, min(1.0, phase))
        if phase != self._blink_phase:
            self._blink_phase = phase
            self.update()

    def _border_pen(self) -> QPen:
        """Цвет рамки с учётом фазы мигания."""
        alpha = lerp_alpha(self._blink_phase, OVERLAY_ALPHA_DIM, OVERLAY_ALPHA_BRIGHT)
        return QPen(QColor(255, 255, 255, alpha), 1)

    def set_drawing_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if self._drawing_enabled == enabled:
            return
        self._drawing_enabled = enabled
        self.setAttribute(Qt.WA_TransparentForMouseEvents, not enabled)
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)
        if not enabled:
            self._dragging = False
            self._drag_preview = None
        self.update()

    # ── Мышь (только при canvas_ar is None — режим original) ──

    def mousePressEvent(self, event):
        if not self._drawing_enabled or self._canvas_ar is not None:
            return
        if event.button() != Qt.LeftButton:
            return
        vr = self._video_rect_on_widget()
        if vr.isNull() or not vr.contains(event.position().toPoint()):
            return
        self._dragging = True
        self._drag_start = event.position().toPoint()
        self._drag_preview = QRect(self._drag_start, self._drag_start)
        self.update()

    def mouseMoveEvent(self, event):
        if not self._dragging:
            return
        vr = self._video_rect_on_widget()
        point = event.position().toPoint()
        if not vr.isNull():
            point.setX(max(vr.left(), min(point.x(), vr.right())))
            point.setY(max(vr.top(), min(point.y(), vr.bottom())))
        self._drag_preview = QRect(self._drag_start, point).normalized()
        self.update()

    def mouseReleaseEvent(self, event):
        if not self._dragging:
            return
        self._dragging = False
        rect_widget = self._drag_preview
        self._drag_preview = None
        self.update()

        if rect_widget is None or rect_widget.width() < MIN_DRAW_PX or rect_widget.height() < MIN_DRAW_PX:
            return

        src_rect = self._widget_rect_to_source(rect_widget)
        if src_rect is not None:
            self.crop_rect_drawn.emit(src_rect)

    # ── Геометрия ──

    def _video_rect_on_widget(self) -> QRect:
        sw, sh = self._source_size
        if sw <= 0 or sh <= 0:
            return QRect()
        return _fit_rect((sw, sh), self.width(), self.height())

    def _widget_rect_to_source(self, rect_widget: QRect) -> QRect | None:
        vr = self._video_rect_on_widget()
        if vr.isNull():
            return None
        sw, sh = self._source_size
        sx = vr.width() / sw
        sy = vr.height() / sh
        if sx <= 0 or sy <= 0:
            return None
        clipped = rect_widget.intersected(vr)
        if clipped.width() < 1 or clipped.height() < 1:
            return None
        x = (clipped.left() - vr.left()) / sx
        y = (clipped.top() - vr.top()) / sy
        w = clipped.width() / sx
        h = clipped.height() / sy
        return QRect(int(x), int(y), int(w), int(h))

    # ── Отрисовка ──

    def paintEvent(self, event):
        # пресет: только рамка по границе canvas, без затенения
        if self._canvas_ar is not None:
            sw, sh = self._source_size
            if sw <= 0 or sh <= 0:
                return
            cx, cy, cw, ch = self._crop_rect
            if cw <= 0 or ch <= 0:
                return

            canvas_center = _fit_rect(self._canvas_ar, self.width(), self.height())
            if canvas_center.isNull():
                return

            # Тот же самый расчёт, что и в VideoSurface, чтобы рамка и видео двигались синхронно
            scale_canvas = canvas_center.width() / cw
            shift_src = cx - (sw - cw) / 2.0
            shift_px = shift_src * scale_canvas

            max_cx = self.width() - canvas_center.width() - canvas_center.x()
            min_cx = -canvas_center.x()
            clamped_offset = max(min_cx, min(max_cx, shift_px))

            canvas = QRectF(
                canvas_center.x() + clamped_offset,
                canvas_center.y(),
                canvas_center.width(),
                canvas_center.height(),
            )
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(self._border_pen())
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(canvas)
            if self._dragging and self._drag_preview is not None:
                painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.DashLine))
                painter.setBrush(PREVIEW_FILL)
                painter.drawRect(self._drag_preview.intersected(canvas.toRect()))
            return

        # original: затенение вне crop_rect + рамка
        sw, sh = self._source_size
        if sw <= 0 or sh <= 0:
            return
        vr = self._video_rect_on_widget()
        if vr.isNull():
            return

        w, h = self.width(), self.height()
        cx, cy, cw, ch = self._crop_rect
        sx = vr.width() / sw
        sy = vr.height() / sh

        rx = vr.left() + cx * sx
        ry = vr.top() + cy * sy
        rw = cw * sx
        rh = ch * sy
        crop_widget = QRectF(rx, ry, rw, rh).intersected(QRectF(vr)).toRect()
        if crop_widget.isNull():
            crop_widget = QRect(vr)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.fillRect(QRect(0, 0, w, crop_widget.top()), DIM_COLOR)
        painter.fillRect(
            QRect(0, crop_widget.bottom() + 1, w, h - crop_widget.bottom() - 1),
            DIM_COLOR,
        )
        painter.fillRect(
            QRect(0, crop_widget.top(), crop_widget.left(), crop_widget.height()),
            DIM_COLOR,
        )
        painter.fillRect(
            QRect(
                crop_widget.right() + 1, crop_widget.top(),
                w - crop_widget.right() - 1, crop_widget.height(),
            ),
            DIM_COLOR,
        )

        painter.setPen(self._border_pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(crop_widget)

        if self._dragging and self._drag_preview is not None and not self._drag_preview.isNull():
            preview = self._drag_preview.intersected(vr)
            if not preview.isNull():
                painter.setPen(QPen(PREVIEW_COLOR, 1, Qt.DashLine))
                painter.setBrush(PREVIEW_FILL)
                painter.drawRect(preview)
