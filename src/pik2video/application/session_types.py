#src/pik2video/application/session_types.py

from enum import Enum


class SessionType(Enum):
    VIDEO = "video"
    SCREEN = "screen"
    AUDIO = "audio"    # сессия записи только звука
