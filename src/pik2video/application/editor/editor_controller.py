# src/pik2video/application/editor/editor_controller.py
"""
Фасад бизнес-логики редактора.

GUI (EditorWindow) должен звать только методы этого класса,
не зная про EditorState, менеджеры и т.п.

TODO: наполняется поэтапно при переносе логики.
"""

import logging

from PySide6.QtCore import QObject

logger = logging.getLogger(__name__)


class EditorController(QObject):
    """Фасад для GUI. Пока скелет."""

    def __init__(self, parent=None):
        super().__init__(parent)
        logger.debug("EditorController инициализирован (скелет)")
