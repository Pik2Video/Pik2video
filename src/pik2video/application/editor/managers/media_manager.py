# src/pik2video/application/editor/managers/media_manager.py
"""
Менеджер медиа редактора.

Отвечает за:
- список видеофайлов и активный индекс
- длительности каждого видео
- тримы (обрезки) каждого видео
- имена экспорта (preferred_names)

Сигналы (videos_changed, active_video_changed, video_loaded, video_unloaded,
trim_changed, video_limit_reached) эмитятся через EditorState —
GUI подписан на state, менеджер меняет данные.

Не знает:
- про GUI (пиксели, виджеты)
- про QMediaPlayer
- про ffmpeg

Фаза A1: только видео. Аудио — следующим шагом (A2).
"""

import logging

logger = logging.getLogger(__name__)


class MediaManager:
    """Управляет медиа-содержимым редактора (видео + аудио)."""

    MAX_VIDEO_FILES = 3   # лимит видеофайлов (раньше был в EditorState)

    def __init__(self, state):
        """state — EditorState. Нужен для эмита сигналов."""
        self._state = state

        # Видео
        self._video_files: list[str] = []
        self._active_index: int = -1
        self._video_durations: dict[str, float] = {}
        self._trims: dict[str, tuple] = {}
        # Ссылка на общий словарь state (используется и для видео, и для аудио).
        # После A2 — полностью во владении MediaManager.
        self._preferred_names = state._preferred_names

        # Аудио
        self._audio_path: str | None = None
        self._audio_duration: float = 0.0
        self._audio_trim: tuple = (0.0, 0.0)
        self._audio_format: str = "WAV"

    # ── Список видео ──

    def add_video_file(self, path: str, duration: float = 0.0, preferred_name: str = ""):
        """Добавить видео и сделать его активным."""
        is_new = path not in self._video_files
        if is_new and len(self._video_files) >= self.MAX_VIDEO_FILES:
            logger.warning(
                f"Лимит видеофайлов достигнут ({self.MAX_VIDEO_FILES}) — отклонено: {path}"
            )
            self._state.video_limit_reached.emit()
            return

        if is_new:
            self._video_files.append(path)
            self._video_durations[path] = duration
            self._trims[path] = (0.0, duration)

        if preferred_name:
            self._preferred_names[path] = preferred_name

        self._active_index = self._video_files.index(path)
        self._state.set_position(0.0)
        self._state._presets.reset_for_new_video()

        logger.debug(f"Видео добавлено: {path} (всего {len(self._video_files)})")

        self._state.videos_changed.emit()
        self._state.active_video_changed.emit(path)
        self._state.video_loaded.emit(path)
        self._state.trim_changed.emit(*self._trims[path])

    def remove_active_video(self):
        """Удалить активный файл."""
        if not self._video_files:
            return

        path = self._video_files[self._active_index]
        self._video_files.pop(self._active_index)
        self._video_durations.pop(path, None)
        self._trims.pop(path, None)
        self._preferred_names.pop(path, None)
        self._state._presets.remove_markers_for(path)
        self._state._timeline.remove_for(path)

        logger.debug(f"Видео удалено: {path} (осталось {len(self._video_files)})")

        if not self._video_files:
            self._active_index = -1
            self._state.set_position(0.0)
            self._state.videos_changed.emit()
            self._state.video_unloaded.emit()
            return

        if self._active_index >= len(self._video_files):
            self._active_index = len(self._video_files) - 1

        new_path = self._video_files[self._active_index]
        self._state.set_position(0.0)

        self._state.videos_changed.emit()
        self._state.active_video_changed.emit(new_path)
        self._state.video_loaded.emit(new_path)
        self._state.trim_changed.emit(*self._trims[new_path])

    def set_active_video(self, index: int):
        """Сделать файл с этим индексом активным."""
        if index < 0 or index >= len(self._video_files):
            return
        if index == self._active_index:
            return

        self._active_index = index
        path = self._video_files[index]
        self._state.set_position(0.0)

        logger.debug(f"Активный файл: {path}")

        self._state.active_video_changed.emit(path)
        self._state.video_loaded.emit(path)
        self._state.trim_changed.emit(*self._trims[path])

    def get_video_files(self) -> list:
        return list(self._video_files)

    def get_active_index(self) -> int:
        return self._active_index

    def has_videos(self) -> bool:
        return len(self._video_files) > 0

    def set_video_file(self, path: str, duration: float = 0.0):
        """Обёртка над add_video_file — старый API."""
        self.add_video_file(path, duration)

    def clear_video(self):
        """Очистить весь список видео."""
        self._video_files.clear()
        self._video_durations.clear()
        self._trims.clear()
        self._preferred_names.clear()
        self._state._timeline.clear()
        self._active_index = -1
        self._state.set_position(0.0)
        self._state.set_video_offset(0.0)
        self._state._presets.clear()

        self._state.videos_changed.emit()
        self._state.video_unloaded.emit()
        self._state.video_offset_changed.emit(0.0)

    def has_video(self) -> bool:
        return self.has_videos()

    def get_video_path(self) -> str | None:
        if self._active_index < 0:
            return None
        return self._video_files[self._active_index]

    def get_preferred_name(self, path: str) -> str:
        """Имя экспорта, заданное для файла, или пустая строка."""
        return self._preferred_names.get(path, "")

    def get_video_duration(self) -> float:
        if self._active_index < 0:
            return 0.0
        path = self._video_files[self._active_index]
        return self._video_durations.get(path, 0.0)

    def get_video_duration_for(self, path: str) -> float:
        """Длительность конкретного видео по пути (0.0 если не загружено)."""
        return self._video_durations.get(path, 0.0)

    def update_active_duration(self, seconds: float):
        """Обновить длительность активного файла (когда плеер её узнал)."""
        if self._active_index < 0:
            return
        path = self._video_files[self._active_index]
        self._video_durations[path] = seconds
        if self._trims[path] == (0.0, 0.0):
            self._trims[path] = (0.0, seconds)
            self._state.trim_changed.emit(0.0, seconds)

    # ── Тримы (для активного файла) ──

    def set_trim(self, start: float, end: float):
        if self._active_index < 0:
            return

        path = self._video_files[self._active_index]
        duration = self._video_durations.get(path, 0.0)

        start = max(start, 0)
        if end > duration > 0:
            end = duration
        if start >= end:
            return

        self._trims[path] = (start, end)
        self._state.trim_changed.emit(start, end)

    def commit_trim(self):
        """Финальное сохранение метки видео — вызывается на mouseRelease."""
        if self._active_index < 0:
            return
        self._state._save_files()

    def get_trim(self) -> tuple:
        if self._active_index < 0:
            return (0.0, 0.0)
        path = self._video_files[self._active_index]
        return self._trims.get(path, (0.0, 0.0))

    def get_trim_for(self, path: str) -> tuple:
        return self._trims.get(path, (0.0, 0.0))

    # ── Имена экспорта ──

    def get_export_filename(self) -> str:
        """Имя экспорта для активного файла, или пусто."""
        if self._active_index < 0:
            return ""
        path = self._video_files[self._active_index]
        return self._preferred_names.get(path, "")

    def set_export_filename(self, name: str):
        """Запомнить имя экспорта для активного файла."""
        if self._active_index < 0:
            return
        path = self._video_files[self._active_index]
        if self._preferred_names.get(path, "") == name:
            return
        self._preferred_names[path] = name
        logger.debug(f"Имя экспорта для {path}: {name}")
        self._state._save_files()
        self._state.settings_changed.emit()

    # ── Аудио ──

    def set_audio_file(self, path: str, duration: float = 0.0):
        self._audio_path = path
        self._audio_duration = duration
        self._audio_trim = (0.0, duration)
        logger.debug(f"Аудио загружено: {path}")
        self._state._save_files()
        self._state.settings_changed.emit()
        self._state.audio_loaded.emit(path)

    def clear_audio(self):
        self._audio_path = None
        self._audio_duration = 0.0
        self._audio_trim = (0.0, 0.0)
        self._state.set_audio_offset(0.0)
        self._state.set_position(0.0)
        self._state._save_files()
        self._state.settings_changed.emit()
        self._state.audio_unloaded.emit()
        self._state.audio_offset_changed.emit(0.0)

    def has_audio(self) -> bool:
        return self._audio_path is not None

    def has_any_media(self) -> bool:
        """Есть ли в редакторе хоть что-то: видео или аудио."""
        return self.has_videos() or self.has_audio()

    def get_audio_path(self) -> str | None:
        return self._audio_path

    def get_audio_duration(self) -> float:
        return self._audio_duration

    def set_audio_duration(self, duration: float):
        if duration <= 0:
            return
        self._audio_duration = duration
        if self._audio_trim == (0.0, 0.0):
            self._audio_trim = (0.0, duration)
            self._state.audio_trim_changed.emit(0.0, duration)

    def set_audio_trim(self, start: float, end: float):
        if not self._audio_path:
            return
        duration = self._audio_duration
        start = max(0.0, start)
        if end > duration > 0:
            end = duration
        if start >= end:
            return
        if self._audio_trim == (start, end):
            return
        self._audio_trim = (start, end)
        self._state.audio_trim_changed.emit(start, end)

    def commit_audio_trim(self):
        if not self._audio_path:
            return
        self._state._save_files()

    def get_audio_trim(self) -> tuple:
        return self._audio_trim

    def set_audio_format(self, fmt: str):
        if fmt not in ("WAV", "MP3", "M4A"):
            return
        if fmt == self._audio_format:
            return
        self._audio_format = fmt
        self._state._save_files()
        self._state.audio_format_changed.emit(fmt)

    def get_audio_export_filename(self) -> str:
        if not self._audio_path:
            return ""
        return self._preferred_names.get(self._audio_path, "")

    def set_audio_export_filename(self, name: str):
        if not self._audio_path:
            return
        if self._preferred_names.get(self._audio_path, "") == name:
            return
        self._preferred_names[self._audio_path] = name
        self._state._save_files()
        self._state.settings_changed.emit()

    def get_audio_format(self) -> str:
        return self._audio_format

    # ── Персистентность (для _save_files / load_persisted_files) ──

    def get_video_files_list(self) -> list:
        return list(self._video_files)

    def get_active_index_for_save(self) -> int:
        return self._active_index

    def get_preferred_names_dict(self) -> dict:
        return dict(self._preferred_names)

    def get_trims_dict(self) -> dict:
        return {p: list(t) for p, t in self._trims.items()}

    def load_video_files(self, files: list, active_index: int, saved_trims: dict, saved_names: dict):
        """Восстановление видео из JSON."""
        from pathlib import Path
        for path in files:
            if not Path(path).exists():
                logger.debug(f"Файл исчез, пропускаем: {path}")
                continue
            if path in self._video_files:
                continue

            self._video_files.append(path)
            self._video_durations[path] = 0.0

            saved = saved_trims.get(path)
            if isinstance(saved, (list, tuple)) and len(saved) == 2:
                self._trims[path] = (float(saved[0]), float(saved[1]))
            else:
                self._trims[path] = (0.0, 0.0)

            name = saved_names.get(path, "")
            if name:
                self._preferred_names[path] = name

        if not self._video_files:
            return

        if active_index < 0 or active_index >= len(self._video_files):
            active_index = len(self._video_files) - 1
        self._active_index = active_index

    def get_audio_state_dict(self) -> dict:
        """Для _save_files: сериализация аудио-состояния."""
        return {
            "audio_path": self._audio_path or "",
            "audio_trim": list(self._audio_trim),
            "audio_format": self._audio_format,
        }

    def load_audio_state(self, data: dict) -> bool:
        """Для load_persisted_files: восстановление аудио из JSON.

        Возвращает True, если аудио восстановлено и нужно эмитить сигналы.
        """
        from pathlib import Path
        saved_audio = data.get("audio_path", "")
        if not saved_audio or not Path(saved_audio).exists():
            return False

        self._audio_path = saved_audio
        saved_trim = data.get("audio_trim", [0.0, 0.0])
        if isinstance(saved_trim, (list, tuple)) and len(saved_trim) == 2:
            self._audio_trim = (float(saved_trim[0]), float(saved_trim[1]))
        saved_format = data.get("audio_format", "WAV")
        if saved_format in ("WAV", "MP3", "M4A"):
            self._audio_format = saved_format
        return True
