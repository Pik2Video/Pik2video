# src/pik2video/application/editor/editor_state.py
"""
Состояние редактора.

Отвечает только за:
- список видеофайлов и активный индекс
- трим и длительность для каждого файла
- позицию воспроизведения
- публикацию сигналов при изменениях

Не знает:
- про виджеты
- про плеер
- про FFmpeg
"""

import json
import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from src.pik2video.application.editor.managers.preset_manager import PresetManager

logger = logging.getLogger(__name__)



class EditorState(QObject):
    MAX_VIDEO_FILES = 3                     # лимит видеофайлов

    ASPECT_RATIOS = {                       # пресеты кадра: ключ → (pw, ph) или None
        "original": None,
        "16:9": (16, 9),
        "9:16": (9, 16),
        "1:1": (1, 1),
        "4:5": (4, 5),
        "4:3": (4, 3),
    }

    # ── Список файлов ──
    videos_changed = Signal()               # состав списка изменился
    active_video_changed = Signal(str)      # путь нового активного

    # ── Совместимость с прежним API ──
    video_loaded = Signal(str)              # активный файл загружен
    video_unloaded = Signal()               # список пуст

    # ── Аудио ──
    audio_loaded = Signal(str)
    audio_unloaded = Signal()

    # ── Воспроизведение ──
    position_changed = Signal(float)

    # ── Трим ──
    trim_changed = Signal(float, float)

    audio_trim_changed = Signal(float, float)   # отдельный сигнал для трима аудио
    audio_format_changed = Signal(str)           # смена аудио-формата экспорта
    crop_rect_changed = Signal(tuple)            # изменилась рабочая зона (x, y, w, h)

    # ── Экспорт ──
    exporting_started = Signal()
    exporting_finished = Signal(bool)
    settings_changed = Signal()

    video_volume_changed = Signal(float)
    audio_volume_changed = Signal(float)

    audio_offset_changed = Signal(float)     # сдвиг аудио-дорожки (сек)
    video_offset_changed = Signal(float)     # сдвиг видео-дорожки (сек)

    video_limit_reached = Signal()           # попытка добавить >3 видео
    linked_mode_changed = Signal(bool)       # режим связки видео+аудио переключён
    timeline_markers_changed = Signal()      # изменение меток на дорожке таймлайна

    def __init__(self, parent=None):
        super().__init__(parent)

        # Список видеофайлов
        self._video_files: list[str] = []
        self._active_index: int = -1
        self._video_durations: dict[str, float] = {}
        self._trims: dict[str, tuple] = {}
        self._preferred_names: dict[str, str] = {}  # path → желаемое имя экспорта
        self._timeline_markers: dict[str, list[tuple[float, str]]] = {}  # path -> [(time, "["/"]"/"]["), ...]
        self._hidden_cuts: dict[str, list[tuple[float, float]]] = {}      # path -> [(start, end), ...] — скрытые cut

        # Менеджер пресетов кадра (пресет, зум, offset_x, crop_rect, метки зума)
        self._presets = PresetManager(self)

        # Аудио
        self._audio_path: Optional[str] = None
        self._audio_duration: float = 0.0
        self._audio_trim: tuple = (0.0, 0.0)         # трим аудио (start, end), отдельно от видео
        self._audio_format: str = "WAV"              # формат аудио-экспорта: WAV / MP3 / M4A

        # Воспроизведение
        self._position: float = 0.0

        self._format: str = "MP4"
        self._resolution: str = "original"
        self._bitrate_mode: str = "auto"
        self._bitrate_value: str = "4M"
        self._rotation: int = 0
        self._speed: float = 1.0

        self._video_volume: float = 1.0         # громкость видео-плеера 0.0 … 1.0
        self._audio_volume: float = 1.0         # громкость аудио-плеера 0.0 … 1.0

        self._audio_offset: float = 0.0         # сдвиг аудио-дорожки (сек)
        self._video_offset: float = 0.0         # сдвиг видео-дорожки (сек)

        self._linked_mode: bool = True          # видео+аудио связаны (плеер играет оба)

        #self._export_filename: str = ""
        self._export_path: str = str(Path.home() / "Desktop" / "output_file")

        # Экспорт
        self._is_exporting: bool = False

        # ── Персистентность списка файлов ──
        self._persist_path = Path.home() / ".pik2video" / "editor_files.json"
        self._loading = False
        self.videos_changed.connect(self._save_files)

    # ── Список видео ──

    def add_video_file(self, path: str, duration: float = 0.0, preferred_name: str = ""):
        """Добавить видео и сделать его активным.

        preferred_name — имя для экспорта (например, из настроек записи).
        Если пусто — редактор возьмёт имя из самого файла.
        """
        is_new = path not in self._video_files
        if is_new and len(self._video_files) >= self.MAX_VIDEO_FILES:
            logger.warning(
                f"Лимит видеофайлов достигнут ({self.MAX_VIDEO_FILES}) — отклонено: {path}"
            )
            self.video_limit_reached.emit()
            return

        if is_new:
            self._video_files.append(path)
            self._video_durations[path] = duration
            self._trims[path] = (0.0, duration)

        if preferred_name:
            self._preferred_names[path] = preferred_name

        self._active_index = self._video_files.index(path)
        self._position = 0.0
        self._presets.reset_for_new_video()   # новое видео — пресет original, зум 0

        logger.debug(f"Видео добавлено: {path} (всего {len(self._video_files)})")

        self.videos_changed.emit()
        self.active_video_changed.emit(path)
        self.video_loaded.emit(path)
        self.trim_changed.emit(*self._trims[path])

    def remove_active_video(self):
        """Удалить активный файл."""
        if not self._video_files:
            return

        path = self._video_files[self._active_index]
        self._video_files.pop(self._active_index)
        self._video_durations.pop(path, None)
        self._trims.pop(path, None)
        self._preferred_names.pop(path, None)
        self._presets.remove_markers_for(path)
        self._timeline_markers.pop(path, None)
        self._hidden_cuts.pop(path, None)

        logger.debug(f"Видео удалено: {path} (осталось {len(self._video_files)})")

        if not self._video_files:
            self._active_index = -1
            self._position = 0.0
            self.videos_changed.emit()
            self.video_unloaded.emit()
            return

        # Активируем соседний файл
        if self._active_index >= len(self._video_files):
            self._active_index = len(self._video_files) - 1

        new_path = self._video_files[self._active_index]
        self._position = 0.0

        self.videos_changed.emit()
        self.active_video_changed.emit(new_path)
        self.video_loaded.emit(new_path)
        self.trim_changed.emit(*self._trims[new_path])

    def set_active_video(self, index: int):
        """Сделать файл с этим индексом активным."""
        if index < 0 or index >= len(self._video_files):
            return
        if index == self._active_index:
            return

        self._active_index = index
        path = self._video_files[index]
        self._position = 0.0

        logger.debug(f"Активный файл: {path}")

        self.active_video_changed.emit(path)
        self.video_loaded.emit(path)
        self.trim_changed.emit(*self._trims[path])

    def get_video_files(self) -> list:
        return list(self._video_files)

    def get_active_index(self) -> int:
        return self._active_index

    def has_videos(self) -> bool:
        return len(self._video_files) > 0

    # ── Совместимость (старые имена) ──

    def set_video_file(self, path: str, duration: float = 0.0):
        """Обёртка над add_video_file — старый API."""
        self.add_video_file(path, duration)

    def clear_video(self):
        """Очистить весь список видео."""
        self._video_files.clear()
        self._video_durations.clear()
        self._trims.clear()
        self._preferred_names.clear()
        self._timeline_markers.clear()
        self._hidden_cuts.clear()
        self._active_index = -1
        self._position = 0.0
        self._video_offset = 0.0
        self._presets.clear()

        self.videos_changed.emit()
        self.video_unloaded.emit()
        self.video_offset_changed.emit(0.0)   # сообщить подписчикам сброс сдвига

    def has_video(self) -> bool:
        return self.has_videos()

    def has_any_media(self) -> bool:
        """Есть ли в редакторе хоть что-то: видео или аудио."""
        return self.has_videos() or self.has_audio()                # используется для «оживления» UI редактора

    def get_video_path(self) -> Optional[str]:
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
            self.trim_changed.emit(0.0, seconds)

    # ── Аудио ──

    def set_audio_file(self, path: str, duration: float = 0.0):
        self._audio_path = path
        self._audio_duration = duration
        self._audio_trim = (0.0, duration)           # новый файл — трим на всю длину
        logger.debug(f"Аудио загружено: {path}")
        self._save_files()                                     # сохраняем аудио-путь вместе с видео
        self.settings_changed.emit()                           # уведомляем UI (инструменты переключатся)
        self.audio_loaded.emit(path)

    def clear_audio(self):
        self._audio_path = None
        self._audio_duration = 0.0
        self._audio_trim = (0.0, 0.0)                # сбрасываем трим
        self._audio_offset = 0.0                     # сбрасываем сдвиг
        self._position = 0.0
        self._save_files()                                     # сохраняем удаление аудио-пути в JSON
        self.settings_changed.emit()                           # уведомляем UI (сбросить инструменты)
        self.audio_unloaded.emit()
        self.audio_offset_changed.emit(0.0)                    # сообщить подписчикам сброс сдвига

    def has_audio(self) -> bool:
        return self._audio_path is not None

    def get_audio_path(self) -> Optional[str]:
        return self._audio_path

    def get_audio_duration(self) -> float:
        return self._audio_duration

    def set_audio_duration(self, duration: float):
        """Обновить длительность аудио (когда плеер её узнал)."""
        if duration <= 0:
            return
        self._audio_duration = duration
        if self._audio_trim == (0.0, 0.0):                    # если трим не задан — ставим на всю длину
            self._audio_trim = (0.0, duration)
            self.audio_trim_changed.emit(0.0, duration)

    def set_audio_trim(self, start: float, end: float):
        """Установить трим аудио (в секундах)."""
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
        self.audio_trim_changed.emit(start, end)      # живое обновление UI, без записи на диск

    def commit_audio_trim(self):
        """Финальное сохранение метки аудио — вызывается на mouseRelease."""
        if not self._audio_path:
            return
        self._save_files()

    def get_audio_trim(self) -> tuple:
        """Трим аудио (start, end)."""
        return self._audio_trim

    def set_audio_format(self, fmt: str):
        """Установить формат аудио-экспорта (WAV / MP3 / M4A)."""
        if fmt not in ("WAV", "MP3", "M4A"):
            return
        if fmt == self._audio_format:
            return
        self._audio_format = fmt
        self._save_files()
        self.audio_format_changed.emit(fmt)

    def get_audio_export_filename(self) -> str:
        """Имя экспорта для аудиофайла, или пусто."""
        if not self._audio_path:
            return ""
        return self._preferred_names.get(self._audio_path, "")     # переиспользуем _preferred_names

    def set_audio_export_filename(self, name: str):
        """Запомнить имя экспорта для аудиофайла."""
        if not self._audio_path:
            return
        if self._preferred_names.get(self._audio_path, "") == name:
            return
        self._preferred_names[self._audio_path] = name
        self._save_files()
        self.settings_changed.emit()

    def get_audio_format(self) -> str:
        """Текущий формат аудио-экспорта."""
        return self._audio_format

    # ── Воспроизведение ──

    def set_position(self, seconds: float):
        if self._position != seconds:
            self._position = seconds
            self.position_changed.emit(seconds)

    def get_position(self) -> float:
        return self._position

    # ── Трим (для активного файла) ──

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
        self.trim_changed.emit(start, end)            # живое обновление UI, без записи на диск

    def commit_trim(self):
        """Финальное сохранение метки видео — вызывается на mouseRelease."""
        if self._active_index < 0:
            return
        self._save_files()

    def get_trim(self) -> tuple:
        if self._active_index < 0:
            return (0.0, 0.0)
        path = self._video_files[self._active_index]
        return self._trims.get(path, (0.0, 0.0))

    def get_trim_for(self, path: str) -> tuple:
        return self._trims.get(path, (0.0, 0.0))


    def get_format(self) -> str:
        return self._format

    def set_format(self, fmt: str):
        if fmt == self._format:
            return
        self._format = fmt
        logger.debug(f"Формат в EditorState: {fmt}")
        self.settings_changed.emit()

    def get_resolution(self) -> str:
        return self._resolution

    def set_resolution(self, value: str):
        if value == self._resolution:
            return
        self._resolution = value
        logger.debug(f"Разрешение в EditorState: {value}")
        self.settings_changed.emit()

    def set_source_resolution(self, width: int, height: int):
        self._presets.set_source_resolution(width, height)

    def get_source_resolution(self) -> tuple:
        return self._presets.get_source_resolution()

    def get_bitrate_mode(self) -> str:
        return self._bitrate_mode

    def get_bitrate_value(self) -> str:
        return self._bitrate_value

    def set_bitrate(self, mode: str, value: str):
        if mode == self._bitrate_mode and value == self._bitrate_value:
            return
        self._bitrate_mode = mode
        self._bitrate_value = value
        logger.debug(f"Битрейт в EditorState: {mode}, {value}")
        self.settings_changed.emit()

    def get_rotation(self) -> int:
        return self._rotation

    def set_rotation(self, angle: int):
        if angle == self._rotation:
            return
        self._rotation = angle
        logger.debug(f"Поворот в EditorState: {angle}°")
        self.settings_changed.emit()

    def get_speed(self) -> float:
        return self._speed

    def get_aspect_preset(self) -> str:
        return self._presets.get_aspect_preset()

    def set_aspect_preset(self, value: str):
        self._presets.set_aspect_preset(value)

    def get_aspect_zoom(self) -> int:
        return self._presets.get_aspect_zoom()

    def set_aspect_zoom(self, zoom: int, save: bool = True):
        self._presets.set_aspect_zoom(zoom, save)

    def get_crop_rect(self) -> tuple:
        return self._presets.get_crop_rect()

    def get_crop_info(self) -> tuple:
        return self._presets.get_crop_info()

    def set_crop_rect(self, rect: tuple):
        self._presets.set_crop_rect(rect)

    def get_offset_x(self) -> float:
        return self._presets.get_offset_x()

    def set_offset_x(self, value: float, save: bool = True):
        self._presets.set_offset_x(value, save)

    def compute_crop_for(self, zoom: int, offset_x: float) -> tuple:
        return self._presets.compute_crop_for(zoom, offset_x)

    def set_speed(self, value: float):
        if value == self._speed:
            return
        self._speed = value
        logger.debug(f"Скорость в EditorState: {value}x")
        self.settings_changed.emit()

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
        self._save_files()
        self.settings_changed.emit()

    def get_video_volume(self) -> float:
        return self._video_volume

    def get_audio_volume(self) -> float:
        return self._audio_volume

    def set_video_volume(self, value: float):
        value = max(0.0, min(1.0, value))
        if self._video_volume == value:
            return
        self._video_volume = value
        self._save_files()
        self.video_volume_changed.emit(value)

    def set_audio_volume(self, value: float):
        value = max(0.0, min(1.0, value))
        if self._audio_volume == value:
            return
        self._audio_volume = value
        self._save_files()
        self.audio_volume_changed.emit(value)

    def get_audio_offset(self) -> float:
        return self._audio_offset

    def get_video_offset(self) -> float:
        return self._video_offset

    def set_audio_offset(self, value: float):
        value = max(0.0, value)
        if self._audio_offset == value:
            return
        self._audio_offset = value
        self._save_files()
        self.audio_offset_changed.emit(value)

    def set_video_offset(self, value: float):
        value = max(0.0, value)
        if self._video_offset == value:
            return
        self._video_offset = value
        self._save_files()
        self.video_offset_changed.emit(value)

    def get_linked_mode(self) -> bool:
        return self._linked_mode

    def set_linked_mode(self, value: bool):
        value = bool(value)
        if self._linked_mode == value:
            return
        self._linked_mode = value
        self._save_files()
        self.linked_mode_changed.emit(value)

    def get_export_path(self) -> str:
        return self._export_path

    def set_export_path(self, path: str):
        if path == self._export_path:
            return
        self._export_path = path
        logger.debug(f"Путь экспорта в EditorState: {path}")
        self.settings_changed.emit()

    # ── Экспорт ──

    def start_exporting(self):
        self._is_exporting = True
        self.exporting_started.emit()

    def finish_exporting(self, success: bool):
        self._is_exporting = False
        self.exporting_finished.emit(success)

    def is_exporting(self) -> bool:
        return self._is_exporting


    # ── Персистентность ──

    def add_marker(self, time_sec: float, offset_x: float, zoom: int = 0):
        self._presets.add_marker(time_sec, offset_x, zoom)

    def get_markers(self) -> list:
        return self._presets.get_markers()

    def has_zoom_markers(self) -> bool:
        return self._presets.has_zoom_markers()

    def get_marker_state_at(self, time_sec: float) -> tuple:
        return self._presets.get_marker_state_at(time_sec)

    def get_marker_offset_at(self, time_sec: float) -> float:
        return self._presets.get_marker_offset_at(time_sec)

    def remove_marker(self, time_sec: float) -> tuple:
        return self._presets.remove_marker(time_sec)

    def add_timeline_marker(self, time_sec: float, kind: str) -> bool:
        """Добавить метку на дорожку активного видео.

        kind: "[" — открыть, "]" — закрыть, "][" — вставка.
        Возвращает True, если метка создана (или уже была на этом месте).
        """
        if kind not in ("[", "]", "]["):
            logger.warning(f"Неизвестный тип метки: {kind}")
            return False
        path = self.get_video_path()
        if not path:
            return False

        if path not in self._timeline_markers:
            self._timeline_markers[path] = []

        # Если на этой позиции уже есть метка — заменить её на новую
        for i, (t, k) in enumerate(self._timeline_markers[path]):
            if abs(t - time_sec) < 0.001:
                if k == kind:
                    return True  # уже такая же
                self._timeline_markers[path][i] = (time_sec, kind)
                self._timeline_markers[path].sort(key=lambda x: x[0])
                self._save_files()
                self.timeline_markers_changed.emit()
                return True

        self._timeline_markers[path].append((time_sec, kind))
        self._timeline_markers[path].sort(key=lambda x: x[0])
        self._save_files()
        self.timeline_markers_changed.emit()
        logger.debug(f"Метка таймлайна: {kind} @ {time_sec:.2f}с на {path}")
        return True

    def get_timeline_markers(self, path: Optional[str] = None) -> list:
        """Список [(time_sec, kind), ...] для указанного пути (или активного видео)."""
        if path is None:
            path = self.get_video_path()
        if not path:
            return []
        return list(self._timeline_markers.get(path, []))

    def remove_timeline_marker(self, time_sec: float, kind: Optional[str] = None) -> bool:
        """Удалить метку на позиции time_sec (опционально — только заданного типа)."""
        path = self.get_video_path()
        if not path or path not in self._timeline_markers:
            return False
        markers = self._timeline_markers[path]
        for i, (t, k) in enumerate(markers):
            if abs(t - time_sec) < 0.001:
                if kind is None or k == kind:
                    markers.pop(i)
                    if not markers:
                        del self._timeline_markers[path]
                    self._save_files()
                    self.timeline_markers_changed.emit()
                    return True
        return False

    def get_cut_intervals(self, path: Optional[str] = None) -> list:
        """Вычислить [start, end] интервалы, которые вырезаются метками.

        Правила:
        - `]` режет влево: от ближайшей `[` слева (или от 0) до себя.
        - `[` режет вправо: от себя до ближайшей `]` справа (или до duration).
        - `][` не режет — только разделяет для вставки.
        Пересекающиеся интервалы объединяются.
        """
        if path is None:
            path = self.get_video_path()
        if not path:
            return []
        markers = self._timeline_markers.get(path, [])
        if not markers:
            return []

        duration = self.get_video_duration_for(path)
        if duration <= 0:
            return []

        left_markers = [t for t, k in markers if k == "["]
        right_markers = [t for t, k in markers if k == "]"]

        cuts = []
        for t, k in markers:
            if k == "]":
                # Ближайшая [ строго левее t (или 0)
                left_bound = 0.0
                for lt in left_markers:
                    if lt < t and lt > left_bound:
                        left_bound = lt
                cuts.append((left_bound, t))
            elif k == "[":
                # Ближайшая ] строго правее t (или duration)
                right_bound = duration
                for rt in right_markers:
                    if rt > t and rt < right_bound:
                        right_bound = rt
                cuts.append((t, right_bound))

        if not cuts:
            return []

        cuts.sort()
        merged = [cuts[0]]
        for start, end in cuts[1:]:
            last_start, last_end = merged[-1]
            if start <= last_end:
                merged[-1] = (last_start, max(last_end, end))
            else:
                merged.append((start, end))
        return merged

    def get_visible_intervals(self, path: Optional[str] = None) -> list:
        """Видимые [start, end] интервалы — дополнение cut до [0, duration]."""
        if path is None:
            path = self.get_video_path()
        duration = self.get_video_duration_for(path) if path else 0.0
        if duration <= 0:
            return []

        cuts = self.get_cut_intervals(path)
        if not cuts:
            return [(0.0, duration)]

        visible = []
        prev_end = 0.0
        for cs, ce in cuts:
            if cs > prev_end + 0.001:
                visible.append((prev_end, cs))
            prev_end = max(prev_end, ce)
        if prev_end < duration - 0.001:
            visible.append((prev_end, duration))
        return visible

    # ── Скрытые cut-участки (визуально подтянуты) ──

    def get_hidden_cuts(self, path: Optional[str] = None) -> list:
        """Список скрытых cut-участков [(start, end), ...] для файла."""
        if path is None:
            path = self.get_video_path()
        if not path:
            return []
        return list(self._hidden_cuts.get(path, []))

    def _actual_hidden_cuts(self, path: str) -> list:
        """Hidden-участки, которые реально находятся внутри актуальных cut.

        При удалении метки cut исчезает — hidden тоже перестаёт действовать.
        """
        hidden = self._hidden_cuts.get(path, [])
        if not hidden:
            return []
        cuts = self.get_cut_intervals(path)
        if not cuts:
            return []
        result = []
        for hs, he in hidden:
            for cs, ce in cuts:
                if hs >= cs - 0.001 and he <= ce + 0.001:
                    result.append((hs, he))
                    break
        return result

    def get_display_intervals(self, path: Optional[str] = None) -> list:
        """Интервалы для ОТРИСОВКИ (видимые + cut-не скрытые), с учётом скрытия.

        Скрытые cut вырезаются (подтягиваются), остальное — встык.
        Используется для визуального таймлайна.
        """
        if path is None:
            path = self.get_video_path()
        duration = self.get_video_duration_for(path) if path else 0.0
        if duration <= 0:
            return []

        hidden = self._actual_hidden_cuts(path)
        if not hidden:
            return [(0.0, duration)]

        hidden.sort()
        result = []
        prev = 0.0
        for hs, he in hidden:
            if hs > prev + 0.001:
                result.append((prev, hs))
            prev = max(prev, he)
        if prev < duration - 0.001:
            result.append((prev, duration))
        return result

    def get_display_duration(self, path: Optional[str] = None) -> float:
        """Визуальная длина дорожки (после скрытия cut)."""
        return sum(e - s for s, e in self.get_display_intervals(path))

    def visual_to_real(self, visual_sec: float, path: Optional[str] = None) -> float:
        """Визуальная позиция → реальная (в файле)."""
        display = self.get_display_intervals(path)
        if not display:
            return visual_sec

        accumulated = 0.0
        for start, end in display:
            seg_len = end - start
            if accumulated + seg_len >= visual_sec:
                return start + (visual_sec - accumulated)
            accumulated += seg_len
        # За концом — прижимаем к концу последнего
        return display[-1][1]

    def real_to_visual(self, real_sec: float, path: Optional[str] = None) -> float:
        """Реальная (в файле) позиция → визуальная."""
        display = self.get_display_intervals(path)
        if not display:
            return real_sec

        accumulated = 0.0
        for start, end in display:
            if start - 0.001 <= real_sec <= end + 0.001:
                return accumulated + (real_sec - start)
            accumulated += end - start
        # В скрытом cut → к ближайшей границе
        if real_sec < display[0][0]:
            return 0.0
        return accumulated

    def hide_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        """Скрыть cut-участок визуально (подтянуть)."""
        if path is None:
            path = self.get_video_path()
        if not path:
            return False
        if path not in self._hidden_cuts:
            self._hidden_cuts[path] = []
        # Проверка: уже скрыт?
        for hs, he in self._hidden_cuts[path]:
            if abs(hs - start) < 0.01 and abs(he - end) < 0.01:
                return False
        self._hidden_cuts[path].append((start, end))
        self._hidden_cuts[path].sort()
        self._save_files()
        self.timeline_markers_changed.emit()   # перерисовать дорожки
        logger.debug(f"Скрыт cut: [{start:.2f}, {end:.2f}] на {path}")
        return True

    def restore_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        """Восстановить скрытый cut-участок."""
        if path is None:
            path = self.get_video_path()
        if not path or path not in self._hidden_cuts:
            return False
        markers = self._hidden_cuts[path]
        for i, (hs, he) in enumerate(markers):
            if abs(hs - start) < 0.01 and abs(he - end) < 0.01:
                markers.pop(i)
                if not markers:
                    del self._hidden_cuts[path]
                self._save_files()
                self.timeline_markers_changed.emit()   # перерисовать дорожки
                logger.debug(f"Восстановлен cut: [{start:.2f}, {end:.2f}]")
                return True
        return False

    def is_time_visible(self, time_sec: float, path: Optional[str] = None) -> bool:
        """Попадает ли время в видимый (не вырезанный) участок."""
        for start, end in self.get_visible_intervals(path):
            if start <= time_sec <= end:
                return True
        return False

    def next_visible_time(self, time_sec: float, path: Optional[str] = None) -> float:
        """Если time_sec в cut-участке — вернуть начало следующего видимого."""
        if self.is_time_visible(time_sec, path):
            return time_sec
        for start, _end in self.get_visible_intervals(path):
            if start > time_sec:
                return start
        return time_sec

    def move_timeline_marker(self, old_time: float, new_time: float, save: bool = False) -> bool:
        """Переместить метку с old_time на new_time. save=True — записать в JSON.

        Возвращает True, если перемещение выполнено.
        Не двигает, если new_time занято другой меткой или метки на old_time нет.
        """
        path = self.get_video_path()
        if not path or path not in self._timeline_markers:
            return False

        markers = self._timeline_markers[path]

        # Найти индекс метки на old_time
        idx = None
        for i, (t, _k) in enumerate(markers):
            if abs(t - old_time) < 0.001:
                idx = i
                break
        if idx is None:
            return False

        # Проверка: new_time не занято другой меткой
        for i, (t2, _k) in enumerate(markers):
            if i != idx and abs(t2 - new_time) < 0.001:
                return False

        # Клэмп по длительности
        new_time = max(0.0, new_time)
        duration = self.get_video_duration_for(path)
        if duration > 0:
            new_time = min(new_time, duration)

        t, kind = markers[idx]
        markers[idx] = (new_time, kind)
        markers.sort(key=lambda x: x[0])

        if save:
            self._save_files()
        self.timeline_markers_changed.emit()
        return True

    def clear_timeline_markers(self, path: Optional[str] = None):
        """Очистить метки таймлайна для пути (или активного видео)."""
        if path is None:
            path = self.get_video_path()
        if path and path in self._timeline_markers:
            del self._timeline_markers[path]
            self._save_files()
            self.timeline_markers_changed.emit()

    def _save_files(self):
        """Сохранить список файлов и имена экспорта в JSON."""
        if self._loading:
            return
        try:
            self._persist_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "files": list(self._video_files),
                "active_index": self._active_index,
                "preferred_names": dict(self._preferred_names),
                "video_trims": {p: list(t) for p, t in self._trims.items()},   # тримы каждого видео
                "audio_path": self._audio_path or "",              # путь к аудиофайлу (пусто = нет аудио)
                "audio_trim": list(self._audio_trim),              # трим аудио сохраняем как список
                "audio_format": self._audio_format,                # формат аудио-экспорта
                "video_volume": self._video_volume,                # громкость видео-плеера
                "audio_volume": self._audio_volume,                # громкость аудио-плеера
                "audio_offset": self._audio_offset,                # сдвиг аудио-дорожки
                "video_offset": self._video_offset,                # сдвиг видео-дорожки
                "linked_mode": self._linked_mode,                  # видео+аудио связаны
                "offset_x": self._presets.get_offset_x_for_save(),                        # сдвиг рамки кадра от центра
                "markers": self._presets.get_markers_dict(),  # метки ключевых кадров (пресеты)
                "timeline_markers": {                                        # метки таймлайна: [t, kind]
                    k: [[float(t), str(kind)] for t, kind in v]
                    for k, v in self._timeline_markers.items()
                },
                "hidden_cuts": {                                             # скрытые cut-участки: [[s, e], ...]
                    k: [[float(s), float(e)] for s, e in v]
                    for k, v in self._hidden_cuts.items()
                },
            }
            with open(self._persist_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # logger.debug(f"Список файлов сохранён: {len(self._video_files)} шт.")   # спамит при каждой смене — закомментировано
        except Exception as e:
            logger.warning(f"Не удалось сохранить список файлов: {e}")

    def load_persisted_files(self):
        """Загрузить сохранённый список файлов при старте редактора."""
        if not self._persist_path.exists():
            return

        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось прочитать список файлов: {e}")
            return

        saved_names = data.get("preferred_names", {})
        saved_trims = data.get("video_trims", {})           # тримы каждого видео из прошлого запуска
        saved_audio = data.get("audio_path", "")            # путь к сохранённому аудиофайлу

        self._video_volume = max(0.0, min(1.0, float(data.get("video_volume", 1.0))))
        self._audio_volume = max(0.0, min(1.0, float(data.get("audio_volume", 1.0))))
        self._audio_offset = max(0.0, float(data.get("audio_offset", 0.0)))
        self._video_offset = max(0.0, float(data.get("video_offset", 0.0)))
        self._linked_mode = bool(data.get("linked_mode", True))
        self._presets.set_offset_x_from_load(float(data.get("offset_x", 0.0)))
        markers_raw = data.get("markers", {})
        self._presets.load_markers(markers_raw)

        # Восстановление скрытых cut-участков
        hc_raw = data.get("hidden_cuts", {})
        self._hidden_cuts = {}
        for path_key, lst in hc_raw.items():
            normalized = []
            for item in lst:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    normalized.append((float(item[0]), float(item[1])))
            if normalized:
                self._hidden_cuts[path_key] = sorted(normalized)

        # Восстановление меток таймлайна
        tm_raw = data.get("timeline_markers", {})
        self._timeline_markers = {}
        for path_key, lst in tm_raw.items():
            normalized = []
            for item in lst:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    t = float(item[0])
                    kind = str(item[1])
                    if kind in ("[", "]", "]["):
                        normalized.append((t, kind))
            if normalized:
                self._timeline_markers[path_key] = sorted(normalized, key=lambda x: x[0])

        self._loading = True
        try:
            for path in data.get("files", []):
                if not Path(path).exists():
                    logger.debug(f"Файл исчез, пропускаем: {path}")
                    continue
                if path in self._video_files:
                    continue

                self._video_files.append(path)
                self._video_durations[path] = 0.0

                saved = saved_trims.get(path)                # восстановить трим, если был
                if isinstance(saved, (list, tuple)) and len(saved) == 2:
                    self._trims[path] = (float(saved[0]), float(saved[1]))
                else:
                    self._trims[path] = (0.0, 0.0)

                name = saved_names.get(path, "")
                if name:
                    self._preferred_names[path] = name

            # Восстановление видео — только если есть что восстанавливать
            if self._video_files:
                saved_idx = data.get("active_index", len(self._video_files) - 1)
                if saved_idx < 0 or saved_idx >= len(self._video_files):
                    saved_idx = len(self._video_files) - 1
                self._active_index = saved_idx

                active_path = self._video_files[self._active_index]

                self.videos_changed.emit()
                self.active_video_changed.emit(active_path)
                self.video_loaded.emit(active_path)
                self.trim_changed.emit(*self._trims[active_path])

                logger.info(f"Восстановлено видео: {len(self._video_files)}")

            # Восстановление аудио — независимо от наличия видео
            if saved_audio and Path(saved_audio).exists():
                self._audio_path = saved_audio
                saved_trim = data.get("audio_trim", [0.0, 0.0])
                if isinstance(saved_trim, (list, tuple)) and len(saved_trim) == 2:
                    self._audio_trim = (float(saved_trim[0]), float(saved_trim[1]))
                saved_format = data.get("audio_format", "WAV")
                if saved_format in ("WAV", "MP3", "M4A"):
                    self._audio_format = saved_format
                self.audio_loaded.emit(saved_audio)
                self.audio_trim_changed.emit(*self._audio_trim)   # сообщить плееру и таймлайну о метках
                logger.info(f"Восстановлено аудио: {saved_audio}, метки {self._audio_trim}")

        finally:
            self._loading = False