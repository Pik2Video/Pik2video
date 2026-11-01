# src/pik2video/gui/editor/timeline/__init__.py
"""
Пакет таймлайнов редактора.

Содержит:
- TimelineWidget — видео-дорожка
- AudioTimelineWidget — аудио-дорожка с waveform
- TimelineZone — общая зона: дорожки + ползунок
- SeekBar — скраббер между дорожками
- FramePreview — всплывающее превью кадра над ползунком
"""

from .audio import AudioTimelineWidget
from .frame_preview import FramePreview
from .seek_bar import SeekBar
from .video import TimelineWidget
from .zone import TimelineZone

__all__ = [
    "AudioTimelineWidget",
    "FramePreview",
    "SeekBar",
    "TimelineWidget",
    "TimelineZone",
]
