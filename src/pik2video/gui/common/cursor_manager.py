# src/pik2video/gui/common/cursor_manager.py
"""
Единый менеджер курсора для прозрачных окон без фокуса.

Проблема macOS:
- setCursor не применяется на окнах без key window;
- QApplication.setOverrideCursor() тоже не работает для окон с
  Qt.WindowDoesNotAcceptFocus (macOS не шлёт cursorUpdate такому окну);
- topLevelAt() не видит прозрачные окна.

Решение: NSCursor через PyObjC — системный курсор, применяется глобально.
Вызываем NSCursor.<shape>().set() на каждом tick (30 Гц), потому что
система сбрасывает курсор при движении мыши.

Приоритет:
1. Мышь над _blocked (окно пресетов, окно записи) → обычный Arrow.
2. Мышь над зарегистрированным окном (_watched) → спросить cursor_for_position.
3. Иначе → Arrow.
"""

import logging

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)


# NSCursor доступен только на macOS. Импорт безопасен на других ОС.
try:
    from AppKit import NSCursor
    NSCURSOR_AVAILABLE = True
except ImportError:
    NSCURSOR_AVAILABLE = False
    logger.warning("NSCursor недоступен — курсор будет работать через Qt override")


DEFAULT_INTERVAL_MS = 33   # ~30 Гц


# Сопоставление Qt CursorShape → NSCursor метод
_NS_CURSOR_MAP = {
    Qt.ArrowCursor:       "arrowCursor",
    Qt.CrossCursor:       "crosshairCursor",
    Qt.OpenHandCursor:    "openHandCursor",
    Qt.ClosedHandCursor:  "closedHandCursor",
    Qt.PointingHandCursor:"pointingHandCursor",
    Qt.IBeamCursor:       "IBeamCursor",
    Qt.SizeAllCursor:     "openHandCursor",
    Qt.BlankCursor:       "arrowCursor",
}


class CursorManager(QObject):
    """Управляет курсором для окон, которым нужен нестандартный вид.

    Зарегистрированное окно должно реализовать:
        cursor_for_position(pos: QPoint) -> Qt.CursorShape | None
    где pos — координаты в системе этого окна.
    """

    def __init__(self, parent=None, interval_ms: int = DEFAULT_INTERVAL_MS):
        super().__init__(parent)
        self._interval_ms = interval_ms
        self._current_shape: Qt.CursorShape | None = None
        # Текущий применённый NSCursor — чтобы не вызывать .set() каждый tick зря
        self._current_ns_name: str | None = None

        self._watched: dict[int, QWidget] = {}
        self._blocked: list[QWidget] = []

        self._timer = QTimer(self)
        self._timer.setInterval(self._interval_ms)
        self._timer.timeout.connect(self._tick)

    # ── API ──

    def register(self, widget: QWidget):
        self._watched[id(widget)] = widget
        if not self._timer.isActive():
            self._timer.start()
        logger.debug(f"CursorManager: register {widget.__class__.__name__}")

    def unregister(self, widget: QWidget):
        self._watched.pop(id(widget), None)
        if not self._watched:
            self._timer.stop()
            self._apply(Qt.ArrowCursor)
            self._current_shape = None
            self._current_ns_name = None
        logger.debug(f"CursorManager: unregister {widget.__class__.__name__}")

    def block(self, widget: QWidget):
        if widget not in self._blocked:
            self._blocked.append(widget)
            logger.debug(f"CursorManager: block {widget.__class__.__name__}")

    def unblock(self, widget: QWidget):
        if widget in self._blocked:
            self._blocked.remove(widget)

    def shutdown(self):
        self._timer.stop()
        self._apply(Qt.ArrowCursor)
        self._watched.clear()
        self._blocked.clear()

    # ── Внутреннее ──

    def _tick(self):
        if not self._watched:
            return

        # Модальный диалог (настройки, подтверждения, ошибки) перекрывает всё —
        # курсор всегда стрелка. Работает глобально для всех модальных окон,
        # не требует регистрации в _blocked.
        if QApplication.activeModalWidget() is not None:
            self._apply(Qt.ArrowCursor)
            return

        pos = QCursor.pos()

        # 1. Блокирующие окна — стрелка.
        # frameGeometry() включает title bar (крестик/свернуть) — иначе над
        # ним geometry() не сработает и курсор возьмётся из оверлея под окном.
        for b in self._blocked:
            try:
                if b.isVisible() and b.frameGeometry().contains(pos):
                    self._apply(Qt.ArrowCursor)
                    return
            except RuntimeError:
                continue

        # 2. Зарегистрированные окна — спросить курсор
        for w in list(self._watched.values()):
            try:
                if w.isVisible() and w.frameGeometry().contains(pos):
                    local = w.mapFromGlobal(pos)
                    handler = getattr(w, "cursor_for_position", None)
                    if handler is None:
                        continue
                    shape = handler(local)
                    if shape is None:
                        continue
                    self._apply(shape)
                    return
            except RuntimeError:
                continue

        # 3. Вне окон — стрелка
        self._apply(Qt.ArrowCursor)

    def _apply(self, shape: Qt.CursorShape):
        """Применить курсор. На macOS — через NSCursor (глобально),
        плюс QApplication.setOverrideCursor как fallback."""
        if self._current_shape == shape:
            # NSCursor сбрасывается системой при движении мыши — продолжаем
            # вызывать .set() каждый tick, даже если shape не изменился.
            if NSCURSOR_AVAILABLE:
                self._apply_ns_cursor(shape, force=True)
            return

        # shape изменился
        if NSCURSOR_AVAILABLE:
            self._apply_ns_cursor(shape, force=True)
        else:
            # fallback на Qt override
            if self._current_shape is None:
                QApplication.setOverrideCursor(shape)
            else:
                QApplication.changeOverrideCursor(shape)
        self._current_shape = shape

    def _apply_ns_cursor(self, shape: Qt.CursorShape, force: bool = False):
        name = _NS_CURSOR_MAP.get(shape)
        if not name:
            return
        if not force and self._current_ns_name == name:
            return
        try:
            getattr(NSCursor, name)().set()
            self._current_ns_name = name
        except Exception as e:
            logger.debug(f"NSCursor.{name}().set() упал: {e}")
