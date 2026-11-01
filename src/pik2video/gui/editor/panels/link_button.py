# src/pik2video/gui/editor/link_button.py
"""
Кнопка связи видео+аудио.

Размещается между drop-зонами в DropArea, на всю ширину.
Два состояния:
- linked (по умолчанию): 🔗, золотистый фон — видео и аудио связаны
- unlinked: ⛓️‍💥, тёмно-серый — режим работы с одним файлом

Не знает:
- про EditorState
- про логику плеера
"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QPushButton


LINKED_ICON = "🔗"
UNLINKED_ICON = "⛓️‍💥"

LINKED_BG = "#2e2818"
LINKED_BORDER = "#8a6f2a"
LINKED_COLOR = "#b89a50"
LINKED_HOVER = "#3e3520"

UNLINKED_BG = "#2a2a2a"
UNLINKED_BORDER = "#444"
UNLINKED_COLOR = "#888"
UNLINKED_HOVER = "#3a3a3a"

DISABLED_BG = "#1f1f1f"
DISABLED_BORDER = "#333"
DISABLED_COLOR = "#444"

WIDGET_HEIGHT = 22


class LinkButton(QPushButton):
    """Кнопка-переключатель режима связки видео и аудио."""

    state_toggled = Signal(bool)   # True = linked, False = unlinked

    def __init__(self, linked: bool = True, parent=None):
        super().__init__(parent)
        self.setFixedHeight(WIDGET_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)

        self._linked = bool(linked)
        self._apply_style()
        self.clicked.connect(self._on_click)

    def is_linked(self) -> bool:
        return self._linked

    def set_linked(self, value: bool):
        if self._linked == bool(value):
            return
        self._linked = bool(value)
        self._apply_style()

    def _on_click(self):
        self._linked = not self._linked
        self._apply_style()
        self.state_toggled.emit(self._linked)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        self._apply_style()

    def _apply_style(self):
        if not self.isEnabled():
            bg, border, color, hover = DISABLED_BG, DISABLED_BORDER, DISABLED_COLOR, DISABLED_BG
            icon = UNLINKED_ICON
        elif self._linked:
            bg, border, color, hover = LINKED_BG, LINKED_BORDER, LINKED_COLOR, LINKED_HOVER
            icon = LINKED_ICON
        else:
            bg, border, color, hover = UNLINKED_BG, UNLINKED_BORDER, UNLINKED_COLOR, UNLINKED_HOVER
            icon = UNLINKED_ICON

        self.setText(icon)
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                color: {color};
                font-size: 13px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {hover};
            }}
        """)