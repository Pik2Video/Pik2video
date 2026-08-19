# src/pik2video/gui/utils.py

from PySide6.QtCore import Qt, QPoint, QRect
from PySide6.QtWidgets import QApplication, QWidget


# ───────── Позиционирование ─────────
def bottom_right_position(window, screen_geometry: QRect, margin: int = 0) -> QPoint:
    x = screen_geometry.right() - window.width() - margin
    y = screen_geometry.bottom() - window.height() - margin
    return QPoint(x, y)


def center_relative_to(parent_geometry: QRect, window) -> QPoint:
    x = parent_geometry.x() + (parent_geometry.width() - window.width()) // 2
    y = parent_geometry.y() + (parent_geometry.height() - window.height()) // 2
    return QPoint(x, y)


def center_to_parent(window, parent) -> QPoint:
    parent_geom = parent.frameGeometry()
    return center_relative_to(parent_geom, window)


def fullscreen_geometry(screen) -> QRect:
    return screen.geometry()


# ───────── Поднятие окна и фокус ─────────
def bring_window_to_front(window):
    #window.show()
    window.raise_()
    window.activateWindow()

def keep_window_inside_screen(window, margin=120):
    """
    Перемещает окно внутрь видимого экрана, если оно выходит за границы.
    margin — отступ от краёв в пикселях.
    """
    screen = window.screen().availableGeometry()
    x = max(screen.left() + margin, min(window.x(), screen.right() - window.width() - margin))
    y = max(screen.top() + margin, min(window.y(), screen.bottom() - window.height() - margin))
    window.move(x, y)

