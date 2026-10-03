# src/pik2video/gui/common/tooltip.py

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPushButton

# глобальный флаг: включены ли подсказки в приложении
_tooltips_enabled = True

def set_tooltips_enabled(enabled: bool):
    """Включить или выключить показ всех подсказок."""
    global _tooltips_enabled
    _tooltips_enabled = bool(enabled)


def is_tooltips_enabled() -> bool:
    """Текущее состояние флага подсказок."""
    return _tooltips_enabled


class CustomToolTip(QLabel):
    """
    Кастомный тултип, который не исчезает при изменении фокуса или нажатии клавиш.
    """
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet("""
            QLabel {
                background-color: #2a2a2a;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }
        """)
        self.setFont(QFont("Arial", 10))
        self.hide()
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.hide)

    def show_text(self, text: str, global_pos: QPoint, duration_ms: int = 3000):
        """Показать тултип в указанной глобальной позиции."""
        self.setText(text)
        self.adjustSize()
        # Смещаем, чтобы не перекрывать курсор
        pos = global_pos + QPoint(15, 15)
        self.move(pos)
        self.show()
        self._hide_timer.start(duration_ms)

    def hide_tip(self):
        """Скрыть подсказку и остановить таймер."""
        self._hide_timer.stop()
        self.hide()




class TooltipButton(QPushButton):
    """Кнопка, которая показывает CustomToolTip при наведении."""

    def __init__(self, text: str = "", tooltip_text: str = "", parent=None):
        super().__init__(text, parent)
        self._tooltip_text = tooltip_text
        self._tooltip = None

    def set_tooltip(self, text: str):
        """Обновить текст подсказки (аналог setToolTip)."""
        self._tooltip_text = text

    def enterEvent(self, event):
        """Курсор навёлся на кнопку."""
        super().enterEvent(event)

        # если подсказки отключены в настройках — ничего не показываем
        if not _tooltips_enabled:
            return

        if not self._tooltip_text:
            return



        if self._tooltip is None:
            self._tooltip = CustomToolTip()

        # вычисляем глобальную позицию нижнего левого угла кнопки
        global_pos = self.mapToGlobal(self.rect().bottomLeft())

        # показываем подсказку
        self._tooltip.show_text(self._tooltip_text, global_pos)

    def leaveEvent(self, event):
        """Курсор ушёл с кнопки."""
        super().leaveEvent(event)
        if self._tooltip:
            self._tooltip.hide_tip()
