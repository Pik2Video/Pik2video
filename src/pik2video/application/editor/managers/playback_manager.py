# src/pik2video/application/editor/managers/playback_manager.py
"""
Менеджер состояния воспроизведения.

Отвечает за:
- позицию воспроизведения (set_position / get_position)
- громкости: video_volume, audio_volume
- сдвиги дорожек: audio_offset, video_offset
- режим связки: linked_mode

Сигналы (position_changed, video_volume_changed, audio_volume_changed,
audio_offset_changed, video_offset_changed, linked_mode_changed) эмитятся
через EditorState.

Не знает:
- про GUI
- про QMediaPlayer
- про таймлайн, файлы, экспорт
"""

import logging

logger = logging.getLogger(__name__)


class PlaybackManager:
    """Управляет runtime-состоянием воспроизведения."""

    def __init__(self, state):
        """state — EditorState. Нужен для эмита сигналов и _save_files."""
        self._state = state

        self._position: float = 0.0
        self._video_volume: float = 1.0
        self._audio_volume: float = 1.0
        self._audio_offset: float = 0.0
        self._video_offset: float = 0.0
        self._linked_mode: bool = True

    # ── Позиция ──

    def set_position(self, seconds: float):
        if self._position != seconds:
            self._position = seconds
            self._state.position_changed.emit(seconds)

    def get_position(self) -> float:
        return self._position

    # ── Громкости ──

    def get_video_volume(self) -> float:
        return self._video_volume

    def get_audio_volume(self) -> float:
        return self._audio_volume

    def set_video_volume(self, value: float):
        value = max(0.0, min(1.0, value))
        if self._video_volume == value:
            return
        self._video_volume = value
        self._state._save_files()
        self._state.video_volume_changed.emit(value)

    def set_audio_volume(self, value: float):
        value = max(0.0, min(1.0, value))
        if self._audio_volume == value:
            return
        self._audio_volume = value
        self._state._save_files()
        self._state.audio_volume_changed.emit(value)

    # ── Сдвиги дорожек ──

    def get_audio_offset(self) -> float:
        return self._audio_offset

    def get_video_offset(self) -> float:
        return self._video_offset

    def set_audio_offset(self, value: float):
        value = max(0.0, value)
        if self._audio_offset == value:
            return
        self._audio_offset = value
        self._state._save_files()
        self._state.audio_offset_changed.emit(value)

    def set_video_offset(self, value: float):
        value = max(0.0, value)
        if self._video_offset == value:
            return
        self._video_offset = value
        self._state._save_files()
        self._state.video_offset_changed.emit(value)

    # ── Режим связки ──

    def get_linked_mode(self) -> bool:
        return self._linked_mode

    def set_linked_mode(self, value: bool):
        value = bool(value)
        if self._linked_mode == value:
            return
        self._linked_mode = value
        self._state._save_files()
        self._state.linked_mode_changed.emit(value)

    # ── Персистентность ──

    def get_state_dict(self) -> dict:
        """Для _save_files: сериализация состояния воспроизведения."""
        return {
            "video_volume": self._video_volume,
            "audio_volume": self._audio_volume,
            "audio_offset": self._audio_offset,
            "video_offset": self._video_offset,
            "linked_mode": self._linked_mode,
        }

    def load_state(self, data: dict):
        """Для load_persisted_files: восстановление из JSON."""
        self._video_volume = max(0.0, min(1.0, float(data.get("video_volume", 1.0))))
        self._audio_volume = max(0.0, min(1.0, float(data.get("audio_volume", 1.0))))
        self._audio_offset = max(0.0, float(data.get("audio_offset", 0.0)))
        self._video_offset = max(0.0, float(data.get("video_offset", 0.0)))
        self._linked_mode = bool(data.get("linked_mode", True))
