# src/pik2video/application/editor/managers/preset_manager.py
"""
Менеджер пресетов кадра.

Отвечает за:
- пресет кадра (original / 16:9 / 9:16 / 1:1 / 4:5 / 4:3)
- зум (0..4)
- горизонтальный сдвиг рамки (offset_x)
- пересчёт рабочей зоны (crop_rect)
- разрешение источника (нужно для расчётов пресета)
- метки ключевых кадров (ромбики для зума во времени)

Сигналы (crop_rect_changed, settings_changed) эмитятся через EditorState —
GUI подписан на state, менеджер лишь меняет данные.

Не знает:
- про GUI (пиксели, виджеты)
- про ffmpeg
"""

import logging

logger = logging.getLogger(__name__)


class PresetManager:
    """Управляет пресетом кадра, зумом и метками ключевых кадров."""

    def __init__(self, state):
        """state — EditorState. Нужен для эмита сигналов и доступа к ASPECT_RATIOS."""
        self._state = state

        self._aspect_preset: str = "original"
        self._aspect_zoom: int = 0
        self._offset_x: float = 0.0
        self._crop_rect: tuple = (0, 0, 0, 0)
        self._source_resolution: tuple = (0, 0)
        # path -> [(time, offset_x, zoom, preset), ...]
        self._markers: dict[str, list[tuple[float, float, int, str]]] = {}

    # ── Source resolution ──

    def get_source_resolution(self) -> tuple:
        return self._source_resolution

    def set_source_resolution(self, width: int, height: int):
        if width <= 0 or height <= 0:
            return
        if (width, height) == self._source_resolution:
            return
        self._source_resolution = (width, height)
        logger.debug(f"Разрешение источника: {width}×{height}")
        self._recompute_crop_rect()
        self._state.settings_changed.emit()

    # ── Preset ──

    def get_aspect_preset(self) -> str:
        return self._aspect_preset

    def set_aspect_preset(self, value: str):
        if value not in self._state.ASPECT_RATIOS:
            return
        if value == self._aspect_preset:
            return
        self._aspect_preset = value
        self._aspect_zoom = 0                     # новый пресет — без обрезки
        self._offset_x = 0.0                      # и без сдвига
        logger.debug(f"Пресет кадра: {value}")
        self._recompute_crop_rect()
        self._state._save_files()
        self._state.settings_changed.emit()

    # ── Zoom ──

    def get_aspect_zoom(self) -> int:
        return self._aspect_zoom

    def set_aspect_zoom(self, zoom: int, save: bool = True):
        """save=False — не сохранять в файл (для воспроизведения по меткам)."""
        if self._aspect_preset == "original":
            return
        zoom = max(0, min(4, int(zoom)))
        if zoom == self._aspect_zoom:
            return
        self._aspect_zoom = zoom
        logger.debug(f"Зум кадра: x{zoom}")
        self._recompute_crop_rect()
        if save:
            self._state._save_files()
            self._state.settings_changed.emit()

    # ── Crop rect ──

    def get_crop_rect(self) -> tuple:
        return self._crop_rect

    def get_crop_info(self) -> tuple:
        """(cw, ch, cx_base, cy) — размеры и базовый центр без учёта offset_x."""
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
            self._state.crop_rect_changed.emit(new_rect)

    # ── Offset X ──

    def get_offset_x(self) -> float:
        return self._offset_x

    def set_offset_x(self, value: float, save: bool = True):
        """Сдвиг рамки работает только если рамка уже источника (cw < sw)."""
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
            self._state._save_files()
            self._state.settings_changed.emit()

    # ── Вычисления ──

    def compute_crop_for(self, zoom: int, offset_x: float) -> tuple:
        """(cx, cy, cw, ch) при заданных zoom и offset_x, без изменения состояния.

        Используется в экспорте при сегментации по меткам.
        """
        sw, sh = self._source_resolution
        if sw <= 0 or sh <= 0:
            return (0.0, 0.0, 0.0, 0.0)

        preset = self._aspect_preset
        ratios = self._state.ASPECT_RATIOS
        if preset == "original" or preset not in ratios or ratios[preset] is None:
            return (0.0, 0.0, float(sw), float(sh))

        pw, ph = ratios[preset]
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
        ratios = self._state.ASPECT_RATIOS
        if preset == "original" or preset not in ratios or ratios[preset] is None:
            new_rect = (0.0, 0.0, float(sw), float(sh))
        else:
            pw, ph = ratios[preset]
            fit_scale = min(pw / sw, ph / sh)
            fill_scale = max(pw / sw, ph / sh)
            t = self._aspect_zoom / 4.0
            K = fit_scale + (fill_scale - fit_scale) * t
            cw = pw / K
            ch = ph / K

            # Защита: если рамка шире источника — сдвигать нечего.
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
            self._state.crop_rect_changed.emit(new_rect)

    # ── Метки ключевых кадров ──

    def add_marker(self, time_sec: float, offset_x: float, zoom: int = 0):
        """Добавить/обновить метку ключевого кадра для активного видео.

        Метка привязана к текущему пресету кадра: при смене пресета ромбики
        скрываются, метки не срабатывают при воспроизведении и экспорте.
        """
        path = self._state.get_video_path()
        if not path:
            return

        current_preset = self._aspect_preset

        if path not in self._markers:
            self._markers[path] = []

        # Если метка на этом кадре уже есть — обновляем её.
        # Допуск 1 мс: метки снапнуты к кадрам.
        for i, (t, _off, _z, _p) in enumerate(self._markers[path]):
            if abs(t - time_sec) < 0.001:
                self._markers[path][i] = (time_sec, offset_x, zoom, current_preset)
                self._state._save_files()
                self._state.settings_changed.emit()
                return

        self._markers[path].append((time_sec, offset_x, zoom, current_preset))
        self._markers[path].sort(key=lambda x: x[0])
        self._state._save_files()
        self._state.settings_changed.emit()
        logger.debug(f"Добавлена метка: {time_sec:.2f}с, offset_x={offset_x:.1f}")

    def get_markers(self) -> list:
        """Метки активного видео для текущего пресета: [(time, offset_x, zoom, preset), ...]."""
        path = self._state.get_video_path()
        if not path:
            return []
        return [m for m in self._markers.get(path, []) if m[3] == self._aspect_preset]

    def has_zoom_markers(self) -> bool:
        """Есть ли у активного видео метки с зумом != 0 для текущего пресета.

        Избавляет внешний код от unpack кортежа метки — если формат изменится,
        править нужно только здесь.
        """
        return any(m[2] != 0 for m in self.get_markers())

    def get_marker_state_at(self, time_sec: float) -> tuple:
        """(offset_x, zoom) для метки, действующей в указанное время (ступенчато)."""
        path = self._state.get_video_path()
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
        """offset_x метки, действующей в указанное время (ступенчато)."""
        path = self._state.get_video_path()
        if not path or path not in self._markers or not self._markers[path]:
            return 0.0

        active_offset = 0.0
        for t, off in self._markers[path]:
            if t <= time_sec + 0.05:
                active_offset = off
            else:
                break
        return active_offset

    def remove_marker(self, time_sec: float) -> tuple:
        """Удалить метку по времени. Вернуть (offset_x, zoom) предыдущей по времени.

        - меток не осталось → (0.0, 0)
        - иначе → состояние (offset_x, zoom) предыдущей по времени метки
        - если удалили самую первую → состояние первой оставшейся
        """
        path = self._state.get_video_path()
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
                new_offset, new_zoom = 0.0, 0
                for m in markers:
                    if m[3] == self._aspect_preset:
                        new_offset, new_zoom = m[1], m[2]
                        break

        self._state._save_files()
        self._state.settings_changed.emit()
        logger.debug(
            f"Удалена метка {time_sec:.2f}с, новый offset_x={new_offset:.1f}, zoom={new_zoom}"
        )
        return (new_offset, new_zoom)

    # ── Вспомогательные (для EditorState) ──

    def remove_markers_for(self, path: str):
        """Удалить все метки зума для конкретного файла (при удалении видео)."""
        self._markers.pop(path, None)

    def reset_for_new_video(self):
        """При добавлении нового видео — пресет original, зум 0."""
        self._aspect_preset = "original"
        self._aspect_zoom = 0

    def clear(self):
        """Сбросить всё при clear_video (видео удалено полностью)."""
        self._source_resolution = (0, 0)
        self._crop_rect = (0, 0, 0, 0)
        self._aspect_preset = "original"
        self._aspect_zoom = 0
        self._offset_x = 0.0
        self._markers.clear()

    def get_markers_dict(self) -> dict:
        """Для _save_files: сериализация меток."""
        return {k: list(v) for k, v in self._markers.items()}

    def get_offset_x_for_save(self) -> float:
        return self._offset_x

    def load_markers(self, raw: dict):
        """Для load_persisted_files: загрузка меток из JSON."""
        self._markers = {}
        for path_key, lst in raw.items():
            normalized = []
            for m in lst:
                if len(m) >= 4:
                    normalized.append((float(m[0]), float(m[1]), int(m[2]), str(m[3])))
                elif len(m) == 3:
                    normalized.append((float(m[0]), float(m[1]), int(m[2]), "original"))
                elif len(m) == 2:
                    normalized.append((float(m[0]), float(m[1]), 0, "original"))
            self._markers[path_key] = sorted(normalized, key=lambda x: x[0])

    def set_offset_x_from_load(self, value: float):
        """Для load_persisted_files: восстановление offset_x без эмита."""
        self._offset_x = value
