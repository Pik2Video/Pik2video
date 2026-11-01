# src/pik2video/gui/editor/state.py
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

    def __init__(self, parent=None):
        super().__init__(parent)

        # Список видеофайлов
        self._video_files: list[str] = []
        self._active_index: int = -1
        self._video_durations: dict[str, float] = {}
        self._trims: dict[str, tuple] = {}
        self._preferred_names: dict[str, str] = {}  # path → желаемое имя экспорта
        self._markers: dict[str, list[tuple[float, float]]] = {}  # path -> [(time, offset_x), ...]

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

        self._aspect_preset: str = "original"   # original / 16:9 / 9:16 / 1:1 / 4:5 / 4:3
        self._aspect_zoom: int = 0              # уровень обрезки: 0 = без обрезки, 4 = максимум
        self._offset_x: float = 0.0             # горизонтальный сдвиг рамки от центра (пиксели источника)
        self._crop_rect: tuple = (0, 0, 0, 0)   # (x, y, w, h) в координатах источника; может выходить за границы

        self._video_volume: float = 1.0         # громкость видео-плеера 0.0 … 1.0
        self._audio_volume: float = 1.0         # громкость аудио-плеера 0.0 … 1.0

        self._audio_offset: float = 0.0         # сдвиг аудио-дорожки (сек)
        self._video_offset: float = 0.0         # сдвиг видео-дорожки (сек)

        self._linked_mode: bool = True          # видео+аудио связаны (плеер играет оба)

        #self._export_filename: str = ""
        self._export_path: str = str(Path.home() / "Desktop" / "output_file")

        self._source_resolution: tuple = (0, 0)   # (width, height)
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
        self._aspect_preset = "original"   # новое видео — начинаем с пресета "оригинал"
        self._aspect_zoom = 0

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
        self._markers.pop(path, None)

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
        self._markers.clear()
        self._active_index = -1
        self._position = 0.0
        self._source_resolution = (0, 0)
        self._video_offset = 0.0
        self._crop_rect = (0, 0, 0, 0)

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
        if width <= 0 or height <= 0:
            return
        if (width, height) == self._source_resolution:
            return
        self._source_resolution = (width, height)
        logger.debug(f"Разрешение источника: {width}×{height}")
        self._recompute_crop_rect()
        self.settings_changed.emit()

    def get_source_resolution(self) -> tuple:
        return self._source_resolution

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
        return self._aspect_preset

    def set_aspect_preset(self, value: str):
        if value not in self.ASPECT_RATIOS:
            return
        if value == self._aspect_preset:
            return
        self._aspect_preset = value
        self._aspect_zoom = 0                     # новый пресет — начинаем без обрезки
        self._offset_x = 0.0                      # и без сдвига
        logger.debug(f"Пресет кадра: {value}")
        self._recompute_crop_rect()
        self._save_files()
        self.settings_changed.emit()

    def get_aspect_zoom(self) -> int:
        return self._aspect_zoom

    def set_aspect_zoom(self, zoom: int, save: bool = True):
        """Установить зум. save=False — не сохранять в файл (для воспроизведения по меткам)."""
        if self._aspect_preset == "original":
            return                            # зум не применим для пресета original
        zoom = max(0, min(4, int(zoom)))
        if zoom == self._aspect_zoom:
            return
        self._aspect_zoom = zoom
        logger.debug(f"Зум кадра: x{zoom}")
        self._recompute_crop_rect()
        if save:
            self._save_files()
            self.settings_changed.emit()

    def get_crop_rect(self) -> tuple:
        return self._crop_rect

    def get_crop_info(self) -> tuple:
        """Вернуть (cw, ch, cx_base, cy) — размеры и базовый центр без учета offset_x."""
        cx, cy, cw, ch = self._crop_rect
        return cw, ch, cx - self._offset_x, cy

    def set_crop_rect(self, rect: tuple):
        """Ручная установка рабочей зоны. Работает только при пресете 'original'."""
        if self._aspect_preset != "original":
            return
        sw, sh = self._source_resolution
        if sw <= 0 or sh <= 0:
            return
        x, y, w, h = rect
        x = max(0.0, min(float(x), sw - 1))
        y = max(0.0, min(float(y), sh - 1))
        w = max(1.0, min(float(w), sw - x))
        h = max(1.0, min(float(h), sh - y))
        new_rect = (x, y, w, h)
        if new_rect != self._crop_rect:
            self._crop_rect = new_rect
            self.crop_rect_changed.emit(new_rect)

    def get_offset_x(self) -> float:
        """Горизонтальный сдвиг рамки от центра (пиксели источника)."""
        return self._offset_x

    def set_offset_x(self, value: float, save: bool = True):
        """Установить горизонтальный сдвиг рамки. Работает только если рамка уже
        источника (cw < sw) — иначе сдвигать некуда.
        """
        if self._aspect_preset == "original":
            return
        sw, _ = self._source_resolution
        if sw <= 0:
            return
        _, _, cw, _ = self._crop_rect
        if cw >= sw:
            self._offset_x = 0.0
            return
        max_off = (sw - cw) / 2.0
        new_offset = max(-max_off, min(max_off, float(value)))
        if new_offset == self._offset_x:
            return
        self._offset_x = new_offset
        logger.debug(f"Сдвиг рамки: {self._offset_x:.1f} px")
        self._recompute_crop_rect()
        
        if save:
            self._save_files()
            self.settings_changed.emit()

    def compute_crop_for(self, zoom: int, offset_x: float) -> tuple:
        """Вернуть (cx, cy, cw, ch) при заданных zoom и offset_x, без изменения состояния.

        Используется в экспорте при сегментации по меткам: считает crop_rect
        для конкретного сегмента, не трогая текущее состояние редактора.
        """
        sw, sh = self._source_resolution
        if sw <= 0 or sh <= 0:
            return (0.0, 0.0, 0.0, 0.0)

        preset = self._aspect_preset
        if preset == "original" or preset not in self.ASPECT_RATIOS or self.ASPECT_RATIOS[preset] is None:
            return (0.0, 0.0, float(sw), float(sh))

        pw, ph = self.ASPECT_RATIOS[preset]
        fit_scale = min(pw / sw, ph / sh)
        fill_scale = max(pw / sw, ph / sh)
        t = zoom / 4.0
        K = fit_scale + (fill_scale - fit_scale) * t
        cw = pw / K
        ch = ph / K

        if cw >= sw:
            offset_x = 0.0
        else:
            max_off = (sw - cw) / 2.0
            offset_x = max(-max_off, min(max_off, offset_x))

        cx = (sw - cw) / 2.0 + offset_x
        cy = (sh - ch) / 2.0
        return (cx, cy, cw, ch)

    def _recompute_crop_rect(self):
        """Пересчитать рабочую зону по пресету, зуму и разрешению источника."""
        sw, sh = self._source_resolution
        if sw <= 0 or sh <= 0:
            return

        preset = self._aspect_preset
        if preset == "original" or preset not in self.ASPECT_RATIOS or self.ASPECT_RATIOS[preset] is None:
            new_rect = (0.0, 0.0, float(sw), float(sh))
        else:
            pw, ph = self.ASPECT_RATIOS[preset]
            fit_scale = min(pw / sw, ph / sh)
            fill_scale = max(pw / sw, ph / sh)
            t = self._aspect_zoom / 4.0
            K = fit_scale + (fill_scale - fit_scale) * t
            cw = pw / K
            ch = ph / K

            # Защита: если рамка шире источника — сдвигать нечего, обнуляем offset.
            # Иначе ограничиваем сдвиг так, чтобы рамка не вылезала за края источника.
            if cw >= sw:
                self._offset_x = 0.0
            else:
                max_off = (sw - cw) / 2.0
                self._offset_x = max(-max_off, min(max_off, self._offset_x))

            cx = (sw - cw) / 2.0 + self._offset_x
            cy = (sh - ch) / 2.0
            new_rect = (cx, cy, cw, ch)

        if new_rect != self._crop_rect:
            self._crop_rect = new_rect
            self.crop_rect_changed.emit(new_rect)

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
        """Добавить/обновить метку ключевого кадра для активного видео.

        Метка привязана к пресету кадра (`self._aspect_preset`): при смене пресета
        ромбики скрываются, метки не срабатывают при воспроизведении и экспорте."""
        path = self.get_video_path()
        if not path:
            return
        
        current_preset = self._aspect_preset

        if path not in self._markers:
            self._markers[path] = []
            
        # Если метка на этом кадре уже есть — обновляем её, иначе добавляем.
        # Допуск 1 мс: метки снапнуты к кадрам, соседние кадры не должны слипаться.
        for i, (t, _off, _z, _p) in enumerate(self._markers[path]):
            if abs(t - time_sec) < 0.001:
                self._markers[path][i] = (time_sec, offset_x, zoom, current_preset)
                self._save_files()
                self.settings_changed.emit()
                return
                
        self._markers[path].append((time_sec, offset_x, zoom, current_preset))
        self._markers[path].sort(key=lambda x: x[0])  # сортируем по времени
        self._save_files()
        self.settings_changed.emit()
        logger.debug(f"Добавлена метка: {time_sec:.2f}с, offset_x={offset_x:.1f}")

    def get_markers(self) -> list[tuple[float, float, int, str]]:
        """Метки активного видео для текущего пресета: [(time, offset_x, zoom, preset), ...]

        Метки других пресетов не возвращаются — ромбики скрыты, воспроизведение
        и экспорт их игнорируют, пока пользователь не вернётся к тому пресету.
        """
        path = self.get_video_path()
        if not path:
            return []
        return [m for m in self._markers.get(path, []) if m[3] == self._aspect_preset]

    def get_marker_state_at(self, time_sec: float) -> tuple:
        """Вернуть (offset_x, zoom) для метки, действующей в указанное время (ступенчато)."""
        path = self.get_video_path()
        if not path or path not in self._markers or not self._markers[path]:
            return (0.0, 0)

        active_offset = 0.0
        active_zoom = 0
        for t, off, z, p in self._markers[path]:
            if p != self._aspect_preset:
                continue
            if t <= time_sec + 0.05:
                active_offset = off
                active_zoom = z
            else:
                break
        return (active_offset, active_zoom)

    def get_marker_offset_at(self, time_sec: float) -> float:
        """Получить offset_x для метки, которая действует в указанное время (ступенчато)."""
        path = self.get_video_path()
        if not path or path not in self._markers or not self._markers[path]:
            return 0.0
            
        # Ищем последнюю метку, время которой <= time_sec
        active_offset = 0.0
        for t, off in self._markers[path]:
            if t <= time_sec + 0.05:
                active_offset = off
            else:
                break
        return active_offset

    def remove_marker(self, time_sec: float) -> tuple:
        """Удалить метку активного видео по времени. Вернуть (offset_x, zoom).

        Логика возврата:
        - меток не осталось → (0.0, 0) — центр экрана, без зума
        - иначе → состояние (offset_x, zoom) предыдущей по времени метки
        - если удалили самую первую → состояние первой оставшейся
        """
        path = self.get_video_path()
        if not path or path not in self._markers:
            return (self._offset_x, self._aspect_zoom)

        markers = self._markers[path]
        removed_index = None
        for i, (t, _off, _z, _p) in enumerate(markers):
            if abs(t - time_sec) < 0.001:
                removed_index = i
                break

        if removed_index is None:
            return (self._offset_x, self._aspect_zoom)

        markers.pop(removed_index)

        if not markers:
            new_offset, new_zoom = 0.0, 0
        else:
            prev = None
            for t, off, z, p in markers:
                if p != self._aspect_preset:
                    continue
                if t < time_sec:
                    prev = (t, off, z)
                else:
                    break
            if prev is not None:
                new_offset, new_zoom = prev[1], prev[2]
            else:
                # Первая оставшаяся метка текущего пресета (или 0/0, если такой нет)
                new_offset, new_zoom = 0.0, 0
                for m in markers:
                    if m[3] == self._aspect_preset:
                        new_offset, new_zoom = m[1], m[2]
                        break

        self._save_files()
        self.settings_changed.emit()
        logger.debug(
            f"Удалена метка {time_sec:.2f}с, новый offset_x={new_offset:.1f}, zoom={new_zoom}"
        )
        return (new_offset, new_zoom)

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
                "offset_x": self._offset_x,                        # сдвиг рамки кадра от центра
                "markers": {k: list(v) for k, v in self._markers.items()},  # метки ключевых кадров
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
        self._offset_x = float(data.get("offset_x", 0.0))
        markers_raw = data.get("markers", {})
        self._markers = {}
        for path_key, lst in markers_raw.items():
            normalized = []
            for m in lst:
                if len(m) >= 4:
                    # новый формат с пресетом
                    normalized.append((float(m[0]), float(m[1]), int(m[2]), str(m[3])))
                elif len(m) == 3:
                    # старый без пресета — привязка к "original"
                    normalized.append((float(m[0]), float(m[1]), int(m[2]), "original"))
                elif len(m) == 2:
                    # совсем старый — без зума и пресета
                    normalized.append((float(m[0]), float(m[1]), 0, "original"))
            self._markers[path_key] = sorted(normalized, key=lambda x: x[0])

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