# src/pik2video/gui/common/styles/__init__.py
"""
Единый центр QSS приложения.

Импорт: from src.pik2video.gui.common.styles import DIALOG_QSS, BOTTOM_PANEL_QSS

Каждая константа применяется на своём корневом виджете через
self.setStyleSheet(CONSTANT). Внутри — objectName-изоляция для контейнеров,
чтобы не задеть дочерние контролы (QLineEdit, QSpinBox и т.п.).
"""

from .dialogs import DIALOG_QSS
from .editor import (
    BOTTOM_PANEL_QSS,
    DROP_AREA_QSS,
    EDITOR_WINDOW_QSS,
    PLAYER_QSS,
    RECORD_MENU_QSS,
    TOOL_BUTTON_QSS,
    TOOLS_PANEL_QSS,
    TOP_BAR_QSS,
    VOLUME_QSS,
)
from .recording import (
    CAPTURE_PANEL_QSS,
    PRESET_WINDOW_QSS,
    RECORDING_WINDOW_QSS,
)

__all__ = [
    # dialogs
    "DIALOG_QSS",
    # editor
    "EDITOR_WINDOW_QSS",
    "TOP_BAR_QSS",
    "TOOLS_PANEL_QSS",
    "BOTTOM_PANEL_QSS",
    "PLAYER_QSS",
    "VOLUME_QSS",
    "DROP_AREA_QSS",
    "TOOL_BUTTON_QSS",
    "RECORD_MENU_QSS",
    # recording
    "RECORDING_WINDOW_QSS",
    "CAPTURE_PANEL_QSS",
    "PRESET_WINDOW_QSS",
]
