# src/pik2video/gui/editor/state.py
"""
Обёртка для обратной совместимости.

Реальный код — в application/editor/editor_state.py.
Все импорты `from .state import EditorState` продолжают работать.
"""

from src.pik2video.application.editor.editor_state import EditorState

__all__ = ["EditorState"]
