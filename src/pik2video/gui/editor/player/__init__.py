# src/pik2video/gui/editor/player/__init__.py
"""
Пакет плеера редактора.

Содержит:
- PlayerWidget — мультиплеер: видео, аудио, управление
- VideoSurface — поверхность отрисовки кадра
- PresetFrame — оверлей рабочей зоны кадра
- VolumeControl — контроль громкости
"""

from .surface import PresetFrame, VideoSurface
from .volume import VolumeControl
from .widget import PlayerWidget

__all__ = [
    "PlayerWidget",
    "PresetFrame",
    "VideoSurface",
    "VolumeControl",
]
