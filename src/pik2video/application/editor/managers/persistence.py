# src/pik2video/application/editor/managers/persistence.py
"""
Сохранение и восстановление состояния редактора.

Отвечает за:
- запись JSON в ~/.pik2video/editor_files.json
- чтение и восстановление состояния менеджеров при старте
- эмит сигналов через EditorState (GUI подписан на state)

Знает про ВСЕ менеджеры (media, presets, timeline, playback) — это
единственное место, где они «встречаются» для сериализации.

Не знает:
- про GUI (пиксели, виджеты)
- про QMediaPlayer
- про ffmpeg
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class Persistence:
    """Загрузка/сохранение состояния редактора в JSON."""

    def __init__(self, state):
        """state — EditorState. Нужен для доступа к менеджерам и эмита сигналов."""
        self._state = state
        self._persist_path = Path.home() / ".pik2video" / "editor_files.json"
        self._loading = False

    def save(self):
        """Сохранить состояние редактора в JSON."""
        if self._loading:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "files": self._state._media.get_video_files_list(),
                "active_index": self._state._media.get_active_index_for_save(),
                "preferred_names": dict(self._state._preferred_names),
                "video_trims": self._state._media.get_trims_dict(),
                **self._state._media.get_audio_state_dict(),
                **self._state._playback.get_state_dict(),
                "offset_x": self._state._presets.get_offset_x_for_save(),
                "markers": self._state._presets.get_markers_dict(),
                "timeline_markers": self._state._timeline.get_timeline_markers_dict(),
                "hidden_cuts": self._state._timeline.get_hidden_cuts_dict(),
            }
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Не удалось сохранить список файлов: {e}")

    def load(self):
        """Загрузить сохранённое состояние редактора при старте."""
        if not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось прочитать список файлов: {e}")
            return

        saved_names = data.get("preferred_names", {})
        saved_trims = data.get("video_trims", {})

        # Восстановление менеджеров
        self._state._playback.load_state(data)
        self._state._presets.set_offset_x_from_load(float(data.get("offset_x", 0.0)))
        self._state._presets.load_markers(data.get("markers", {}))
        self._state._timeline.load_hidden_cuts(data.get("hidden_cuts", {}))
        self._state._timeline.load_timeline_markers(data.get("timeline_markers", {}))

        self._loading = True
        try:
            # Восстановление видео
            self._state._media.load_video_files(
                files=data.get("files", []),
                active_index=data.get("active_index", -1),
                saved_trims=saved_trims,
                saved_names=saved_names,
            )

            if self._state._media.has_videos():
                active_path = self._state._media.get_video_path()
                self._state.videos_changed.emit()
                self._state.active_video_changed.emit(active_path)
                self._state.video_loaded.emit(active_path)
                self._state.trim_changed.emit(*self._state._media.get_trim())
                logger.info(
                    f"Восстановлено видео: {len(self._state._media.get_video_files())}"
                )

            # Восстановление аудио
            if self._state._media.load_audio_state(data):
                audio_path = self._state._media.get_audio_path()
                audio_trim = self._state._media.get_audio_trim()
                self._state.audio_loaded.emit(audio_path)
                self._state.audio_trim_changed.emit(*audio_trim)
                logger.info(f"Восстановлено аудио: {audio_path}, метки {audio_trim}")

        finally:
            self._loading = False
