# src/pik2video/gui/editor/tools/__init__.py
"""
Инструменты редактора.

Каждый инструмент — отдельный виджет, отвечающий только за свой параметр.
"""

from .bitrate import BitrateTool
from .format import FormatTool
from .resolution import ResolutionTool
from .rotation import RotationTool
from .speed import SpeedTool

__all__ = [
    "BitrateTool",
    "FormatTool",
    "ResolutionTool",
    "RotationTool",
    "SpeedTool",
]
