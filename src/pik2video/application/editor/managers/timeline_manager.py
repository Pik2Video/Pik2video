# src/pik2video/application/editor/managers/timeline_manager.py
"""
Менеджер таймлайна.

Отвечает за:
- метки таймлайна ([, ], ][)
- cut-интервалы (что вырезается из воспроизведения/экспорта)
- visible-интервалы (что видно, с учётом скрытых cut)
- скрытие/восстановление cut (визуальная подтяжка)
- конвертации visual_sec ↔ real_sec (для отрисовки и кликов)

Сигналы (timeline_markers_changed) и сохранение (_save_files) — через EditorState.

Не знает:
- про GUI (пиксели, виджеты, зум)
- про QMediaPlayer
- про ffmpeg
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TimelineManager:
    """Управляет временны́ми интервалами: метками, cut, visible."""

    def __init__(self, state):
        """state — EditorState. Нужен для эмита сигналов, save_files и запросов пути/длительности."""
        self._state = state
        self._timeline_markers: dict[str, list[tuple[float, str]]] = {}
        self._hidden_cuts: dict[str, list[tuple[float, float]]] = {}

    # ── Метки таймлайна ([, ], ][) ──

    def add_timeline_marker(self, time_sec: float, kind: str) -> bool:
        """Добавить метку на дорожку активного видео.

        kind: "[" — открыть, "]" — закрыть, "][" — вставка.
        Возвращает True, если метка создана (или уже была на этом месте).
        """
        if kind not in ("[", "]", "]["):
            logger.warning(f"Неизвестный тип метки: {kind}")
            return False
        path = self._state.get_video_path()
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
                self._state._save_files()
                self._state.timeline_markers_changed.emit()
                return True

        self._timeline_markers[path].append((time_sec, kind))
        self._timeline_markers[path].sort(key=lambda x: x[0])
        self._state._save_files()
        self._state.timeline_markers_changed.emit()
        logger.debug(f"Метка таймлайна: {kind} @ {time_sec:.2f}с на {path}")
        return True

    def get_timeline_markers(self, path: Optional[str] = None) -> list:
        """Список [(time_sec, kind), ...] для указанного пути (или активного видео)."""
        if path is None:
            path = self._state.get_video_path()
        if not path:
            return []
        return list(self._timeline_markers.get(path, []))

    def remove_timeline_marker(self, time_sec: float, kind: Optional[str] = None) -> bool:
        """Удалить метку на позиции time_sec (опционально — только заданного типа)."""
        path = self._state.get_video_path()
        if not path or path not in self._timeline_markers:
            return False
        markers = self._timeline_markers[path]
        for i, (t, k) in enumerate(markers):
            if abs(t - time_sec) < 0.001:
                if kind is None or k == kind:
                    markers.pop(i)
                    if not markers:
                        del self._timeline_markers[path]
                    self._state._save_files()
                    self._state.timeline_markers_changed.emit()
                    return True
        return False

    def move_timeline_marker(self, old_time: float, new_time: float, save: bool = False) -> bool:
        """Переместить метку с old_time на new_time. save=True — записать в JSON.

        Возвращает True, если перемещение выполнено.
        Не двигает, если new_time занято другой меткой или метки на old_time нет.
        """
        path = self._state.get_video_path()
        if not path or path not in self._timeline_markers:
            return False

        markers = self._timeline_markers[path]

        idx = None
        for i, (t, _k) in enumerate(markers):
            if abs(t - old_time) < 0.001:
                idx = i
                break
        if idx is None:
            return False

        for i, (t2, _k) in enumerate(markers):
            if i != idx and abs(t2 - new_time) < 0.001:
                return False

        new_time = max(0.0, new_time)
        duration = self._state.get_video_duration_for(path)
        if duration > 0:
            new_time = min(new_time, duration)

        t, kind = markers[idx]
        markers[idx] = (new_time, kind)
        markers.sort(key=lambda x: x[0])

        if save:
            self._state._save_files()
        self._state.timeline_markers_changed.emit()
        return True

    def clear_timeline_markers(self, path: Optional[str] = None):
        """Очистить метки таймлайна для пути (или активного видео)."""
        if path is None:
            path = self._state.get_video_path()
        if path and path in self._timeline_markers:
            del self._timeline_markers[path]
            self._state._save_files()
            self._state.timeline_markers_changed.emit()

    # ── Cut / visible ──

    def get_cut_intervals(self, path: Optional[str] = None) -> list:
        """[start, end] интервалы, которые вырезаются метками.

        Правила:
        - ] режет влево: от ближайшей [ слева (или от 0) до себя.
        - [ режет вправо: от себя до ближайшей ] справа (или до duration).
        - ][ не режет — только разделяет для вставки.
        Пересекающиеся интервалы объединяются.
        """
        if path is None:
            path = self._state.get_video_path()
        if not path:
            return []
        markers = self._timeline_markers.get(path, [])
        if not markers:
            return []

        duration = self._state.get_video_duration_for(path)
        if duration <= 0:
            return []

        left_markers = [t for t, k in markers if k == "["]
        right_markers = [t for t, k in markers if k == "]"]

        cuts = []
        for t, k in markers:
            if k == "]":
                left_bound = 0.0
                for lt in left_markers:
                    if lt < t and lt > left_bound:
                        left_bound = lt
                cuts.append((left_bound, t))
            elif k == "[":
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
            path = self._state.get_video_path()
        duration = self._state.get_video_duration_for(path) if path else 0.0
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
            path = self._state.get_video_path()
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
        """
        if path is None:
            path = self._state.get_video_path()
        duration = self._state.get_video_duration_for(path) if path else 0.0
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

    def hide_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        """Скрыть cut-участок визуально (подтянуть)."""
        if path is None:
            path = self._state.get_video_path()
        if not path:
            return False
        if path not in self._hidden_cuts:
            self._hidden_cuts[path] = []
        for hs, he in self._hidden_cuts[path]:
            if abs(hs - start) < 0.01 and abs(he - end) < 0.01:
                return False
        self._hidden_cuts[path].append((start, end))
        self._hidden_cuts[path].sort()
        self._state._save_files()
        self._state.timeline_markers_changed.emit()
        logger.debug(f"Скрыт cut: [{start:.2f}, {end:.2f}] на {path}")
        return True

    def restore_cut(self, start: float, end: float, path: Optional[str] = None) -> bool:
        """Восстановить скрытый cut-участок."""
        if path is None:
            path = self._state.get_video_path()
        if not path or path not in self._hidden_cuts:
            return False
        markers = self._hidden_cuts[path]
        for i, (hs, he) in enumerate(markers):
            if abs(hs - start) < 0.01 and abs(he - end) < 0.01:
                markers.pop(i)
                if not markers:
                    del self._hidden_cuts[path]
                self._state._save_files()
                self._state.timeline_markers_changed.emit()
                logger.debug(f"Восстановлен cut: [{start:.2f}, {end:.2f}]")
                return True
        return False

    # ── Конвертации visual ↔ real ──

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
        if real_sec < display[0][0]:
            return 0.0
        return accumulated

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

    # ── Персистентность (для _save_files / load_persisted_files) ──

    def get_timeline_markers_dict(self) -> dict:
        """Сериализация меток таймлайна для JSON."""
        return {
            k: [[float(t), str(kind)] for t, kind in v]
            for k, v in self._timeline_markers.items()
        }

    def get_hidden_cuts_dict(self) -> dict:
        """Сериализация скрытых cut для JSON."""
        return {
            k: [[float(s), float(e)] for s, e in v]
            for k, v in self._hidden_cuts.items()
        }

    def load_timeline_markers(self, raw: dict):
        """Восстановление меток таймлайна из JSON."""
        self._timeline_markers = {}
        for path_key, lst in raw.items():
            normalized = []
            for item in lst:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    t = float(item[0])
                    kind = str(item[1])
                    if kind in ("[", "]", "]["):
                        normalized.append((t, kind))
            if normalized:
                self._timeline_markers[path_key] = sorted(normalized, key=lambda x: x[0])

    def load_hidden_cuts(self, raw: dict):
        """Восстановление скрытых cut из JSON."""
        self._hidden_cuts = {}
        for path_key, lst in raw.items():
            normalized = []
            for item in lst:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    normalized.append((float(item[0]), float(item[1])))
            if normalized:
                self._hidden_cuts[path_key] = sorted(normalized)

    def clear(self):
        """Полный сброс при clear_video."""
        self._timeline_markers.clear()
        self._hidden_cuts.clear()

    def remove_for(self, path: str):
        """Удалить данные для конкретного пути (при удалении видео)."""
        self._timeline_markers.pop(path, None)
        self._hidden_cuts.pop(path, None)
