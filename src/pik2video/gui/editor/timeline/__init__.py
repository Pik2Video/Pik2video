# src/pik2video/gui/editor/timeline/__init__.py
"""
Пакет таймлайнов редактора (Новая архитектура).
"""

from .track import TrackWidget
from .timeline import TimelineWidget
from .frame_preview import FramePreview

__all__ = [
    "TrackWidget",
    "TimelineWidget",
    "FramePreview",
]
