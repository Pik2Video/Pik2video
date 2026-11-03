# src/pik2video/gui/editor/player/widget.py
import logging
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget

from .ui import PlayerUI
from src.pik2video.application.editor.managers.player_manager import PlayerManager
from .surface import PresetFrame

logger = logging.getLogger(__name__)

SPEED_PRESETS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]


class PlayerWidget(PlayerUI):
    """Главный класс плеера: связывает UI и Engine."""
    
    position_changed = Signal(float)
    duration_changed = Signal(float)
    audio_duration_changed = Signal(float)
    speed_changed = Signal(float)
    video_volume_changed = Signal(float)
    audio_volume_changed = Signal(float)
    source_resolution_changed = Signal(int, int)
    crop_rect_drawn = Signal(object)
    shift_left_requested = Signal()
    shift_right_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.engine = PlayerManager(self)
        self._last_frame = None
        self._keep_frames = True
        self._last_source_resolution = (0, 0)
        self._video_volume = 1.0
        self._audio_volume = 1.0
        self._linked_mode = True
        self._marker_mode_active = False
        self._pre_play_resolver = None    # fn(current_sec) -> new_sec | None
        self._suppress_cut_skip = False   # запрет перескока в _on_player_position_changed
        self._start_resolver = None       # fn(default_sec) -> new_sec

        self._speed_index = SPEED_PRESETS.index(1.0)
        self._video_speed_index = SPEED_PRESETS.index(1.0)
        self._audio_speed_index = SPEED_PRESETS.index(1.0)
        self._update_speed_buttons()

        # Подключение UI к Engine
        self._btn_play.clicked.connect(self._toggle_play)
        self._btn_go_start.clicked.connect(self._on_go_to_start)
        self._btn_rewind.clicked.connect(self._on_rewind)
        self._btn_forward.clicked.connect(self._on_forward)
        self._btn_loop.toggled.connect(self.engine.set_loop)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._btn_speed_prev.clicked.connect(self._on_speed_prev)
        self._btn_speed_next.clicked.connect(self._on_speed_next)
        self._volume_control.volume_changed.connect(self._on_volume_changed)

        self._preset_frame.crop_rect_drawn.connect(self.crop_rect_drawn.emit)
        self._btn_shift_left.clicked.connect(self.shift_left_requested.emit)
        self._btn_shift_right.clicked.connect(self.shift_right_requested.emit)

        # Подключение Engine к UI
        self.engine.position_changed.connect(self._on_engine_position)
        self.engine.duration_changed.connect(self._on_engine_duration)
        self.engine.audio_duration_changed.connect(self.audio_duration_changed.emit)
        self.engine.playback_state_changed.connect(self._on_engine_state)
        self.engine.video_frame_ready.connect(self._on_engine_frame)
        self.engine.meta_data_ready.connect(self._on_engine_meta)

        self._show_placeholder()
        self._set_controls_enabled(False)

    # ── Публичные свойства для внешнего мира (window.py) ──

    @property
    def mode(self) -> str:
        """Текущий режим: "video" или "audio"."""
        return self.engine._mode

    @property
    def video_player(self):
        """Внутренний QMediaPlayer для видео (для очистки в _cleanup_media)."""
        return self.engine._player

    @property
    def audio_player(self):
        """Внутренний QMediaPlayer для аудио."""
        return self.engine._audio_player

    @property
    def linked_mode(self) -> bool:
        """Режим связки видео+аудио."""
        return self.engine._linked_mode

    @property
    def video_fps(self) -> float:
        """FPS текущего видео (для покадровой перемотки)."""
        return self.engine.get_video_fps()

    # ── API для EditorWindow ──

    def load_video(self, path: str):
        self._show_player()
        self.engine.load_video(path)
        self._set_controls_enabled(True)

    def unload_video(self):
        self._video_widget.clear_image()
        QTimer.singleShot(0, self._deferred_unload_video)

    def _deferred_unload_video(self):
        try:
            self.engine.unload_video()
        except RuntimeError:
            pass
        self._maybe_reset_ui()

    def load_audio(self, path: str):
        self.engine.load_audio(path)
        self._audio_name.setText(Path(path).name)
        if self.engine._mode == "audio" or not self.engine.has_video():
            self._stack.setCurrentWidget(self._audio_page)
        self._set_controls_enabled(True)

    def unload_audio(self):
        self._audio_name.setText("")
        QTimer.singleShot(0, self._deferred_unload_audio)

    def _deferred_unload_audio(self):
        try:
            self.engine.unload_audio()
        except RuntimeError:
            pass
        self._maybe_reset_ui()

    def set_mode(self, mode: str):
        """Переключить режим. ТОЛЬКО логика + UI. Без QMediaPlayer операций.

        Причина: QMediaPlayer.setPosition() / pause() на macOS блокируют GIL
        при переключении с видео на аудио. Никакие try/except не помогут —
        это C++-блокировка. Поэтому все действия с плеером отложены.
        """
        if self.engine._mode == mode:
            return
        logger.debug(f"[SET-MODE] {self.engine._mode} → {mode}")

        was_playing = False
        try:
            was_playing = self.engine.is_playing()
        except RuntimeError:
            pass

        # Просто меняем режим в движке — без pause/seek.
        self.engine._mode = mode

        # UI: какая страница видна
        if mode == "video":
            if self.engine.has_video():
                self._show_player()
            else:
                self._show_placeholder()
        else:
            if self.engine.has_audio():
                self._stack.setCurrentWidget(self._audio_page)
            else:
                self._show_placeholder()

        self._update_play_button()
        self._apply_volume()

        # Если играло — пауза отложенно (не блокирует UI)
        if was_playing:
            QTimer.singleShot(0, self.engine.pause)

        logger.debug(f"[SET-MODE] done: {mode}")

    def play_until_first_frame(self, timeout_ms: int = 1500):
        """Play → pause после первого кадра (для показа превью)."""
        self.engine.play_until_first_frame(timeout_ms)

    def set_position(self, seconds: float):
        self.engine.seek(seconds)

    def seek_for_preview(self, seconds: float):
        """Двинуть только видео-плеер для получения кадра превью (без звука, без аудио-плеера)."""
        self.engine.seek_for_preview(seconds)

    def set_trim_range(self, start: float, end: float):
        self.engine.set_trim_range(start, end)

    def set_audio_trim_range(self, start: float, end: float):
        self.engine.set_audio_trim_range(start, end)

    def set_audio_offset(self, offset: float):
        self.engine.set_audio_offset(offset)

    def set_linked_mode(self, linked: bool):
        self.engine.set_linked_mode(linked)
        self._apply_volume()

    def set_marker_mode(self, active: bool):
        self._marker_mode_active = active
        if active:
            self.engine.pause()
        self._set_controls_enabled(self.engine.has_video() or self.engine.has_audio())

    def set_pre_play_resolver(self, fn):
        """fn(current_pos_sec) -> new_pos_sec | None. Вызывается перед play()."""
        self._pre_play_resolver = fn

    def set_start_resolver(self, fn):
        """fn(default_start_sec) -> start_sec. Для кнопки ⏮."""
        self._start_resolver = fn

    def set_loop_start_resolver(self, fn):
        """Проброс в engine — resolver для loop."""
        self.engine.set_loop_start_resolver(fn)

    def is_loop_enabled(self) -> bool:
        return self._btn_loop.isChecked()

    def set_preset_blink_phase(self, phase: float):
        self._preset_frame.set_blink_phase(phase)

    def set_shift_buttons_blink_phase(self, phase: float):
        opacity = 0.35 + 0.65 * max(0.0, min(1.0, phase))
        blink_left = getattr(self, "_marker_mode_active", False) and self._btn_shift_left.isEnabled()
        blink_right = getattr(self, "_marker_mode_active", False) and self._btn_shift_right.isEnabled()
        self._shift_left_effect.setOpacity(opacity if blink_left else 1.0)
        self._shift_right_effect.setOpacity(opacity if blink_right else 1.0)

    def set_shift_buttons_visible(self, visible: bool):
        self._btn_shift_left.setVisible(visible)
        self._btn_shift_right.setVisible(visible)
        if visible:
            self._btn_shift_left.raise_()
            self._btn_shift_right.raise_()
            self._relayout_shift_buttons()

    def set_shift_buttons_enabled(self, can_left: bool, can_right: bool):
        self._btn_shift_left.setEnabled(can_left)
        self._btn_shift_right.setEnabled(can_right)

    def set_preset_visible(self, visible: bool):
        if not visible or not self.engine.has_video():
            self._preset_frame.hide()
            return
        self._preset_frame.show()
        self._preset_frame.raise_()

    def set_crop_rect(self, rect: tuple):
        source_size = self._last_source_resolution if hasattr(self, "_last_source_resolution") else (0, 0)
        self._preset_frame.set_crop_rect(rect, source_size)
        self._video_widget.set_crop_rect(rect, source_size)

    def set_canvas_ar(self, ar):
        self._preset_frame.set_canvas_ar(ar)
        self._video_widget.set_canvas_ar(ar)

    def set_preset_drawing(self, enabled: bool):
        self._preset_frame.set_drawing_enabled(enabled)

    def get_position(self) -> float:
        return self.engine.get_position()

    def get_last_frame(self):
        return self._last_frame

    def set_keep_frames(self, value: bool):
        self._keep_frames = value
        if not value:
            self._last_frame = None

    def get_speed(self) -> float:
        return SPEED_PRESETS[self._speed_index]

    def set_video_volume(self, vol: float):
        self.engine.set_video_volume(vol)
        if self.engine._mode == "video":
            self._volume_control.set_volume(vol)

    def set_audio_volume(self, vol: float):
        self.engine.set_audio_volume(vol)
        if self.engine._mode == "audio":
            self._volume_control.set_volume(vol)

    def pause_all(self):
        self.engine.pause()

    def hide_floating(self):
        try:
            self._volume_control._popup.hide()
        except (RuntimeError, AttributeError):
            pass

    # ── Private ──

    def _active_player(self):
        return self.engine._active_player()

    def _trim_for(self, player):
        return self.engine._trim_for(player)

    def _has_video_source(self) -> bool:
        return self.engine.has_video()

    def _has_audio_source(self) -> bool:
        return self.engine.has_audio()

    def _set_controls_enabled(self, enabled: bool):
        self._btn_play.setEnabled(enabled and not getattr(self, "_marker_mode_active", False))
        self._btn_go_start.setEnabled(enabled)
        self._btn_rewind.setEnabled(enabled)
        self._btn_forward.setEnabled(enabled)
        self._btn_loop.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._btn_speed_prev.setEnabled(enabled)
        self._btn_speed_next.setEnabled(enabled)
        self._volume_control.setEnabled(enabled)

    def _maybe_reset_ui(self):
        if self.engine.has_video() or self.engine.has_audio():
            return
        self._show_placeholder()
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self._btn_play.setText("▶")
        self._set_controls_enabled(False)

    def _show_placeholder(self):
        self._stack.setCurrentIndex(0)

    def _show_player(self):
        self._stack.setCurrentIndex(1)

    def _toggle_play(self):
        if self.engine.is_playing():
            self.engine.pause()
            return
        # Даём шанс скорректировать стартовую позицию (cut-зоны)
        if self._pre_play_resolver is not None:
            current = self.engine.get_position()
            new_pos = self._pre_play_resolver(current)
            if new_pos is not None and abs(new_pos - current) > 0.01:
                # Защита от гонки: пока QMediaPlayer применяет seek,
                # position-changed может приходить со старым значением (в cut-зоне).
                # Без защиты — CUT-STOP → pause в момент старта.
                self._suppress_cut_skip = True
                self.engine.seek(new_pos)
                QTimer.singleShot(300, self._clear_suppress_cut_skip)
        self.engine.play()

    def _clear_suppress_cut_skip(self):
        """Снять защиту после того, как QMediaPlayer применил seek."""
        self._suppress_cut_skip = False

    def _update_play_button(self):
        """Обновить иконку play/pause по состоянию движка."""
        self._btn_play.setText("⏸" if self.engine.is_playing() else "▶")

    def begin_trim_drag(self) -> bool:
        """Пауза перед drag метки. Возвращает True, если плеер играл."""
        was_playing = self.engine.is_playing()
        if was_playing:
            self.engine.pause()
        return was_playing

    def end_trim_drag(self, was_playing: bool):
        """Возобновить воспроизведение после drag, если играло до него."""
        if was_playing:
            self.engine.play()

    def _sync_speed_ui(self):
        """Синхронизировать UI скорости с активным плеером. В связке — между обоими."""
        if self._linked_mode:
            self._speed_index = (
                self._video_speed_index if self.engine._mode == "video"
                else self._audio_speed_index
            )
            self._video_speed_index = self._speed_index
            self._audio_speed_index = self._speed_index
        else:
            self._speed_index = (
                self._video_speed_index if self.engine._mode == "video"
                else self._audio_speed_index
            )
        speed = SPEED_PRESETS[self._speed_index]
        self.engine.set_playback_rate(speed)
        self._speed_label.setText(f"{speed}x")
        self._update_speed_buttons()
        self.speed_changed.emit(speed)

    def _on_go_to_start(self):
        active = self._active_player()
        trim_start, trim_end = self._trim_for(active)
        target = trim_start
        if self._start_resolver is not None:
            target = self._start_resolver(trim_start)
        logger.debug(
            f"[GOTO-START] trim=({trim_start:.2f},{trim_end:.2f}) → {target:.2f}"
        )
        self._suppress_cut_skip = True
        try:
            self.engine.seek(target)
        finally:
            self._suppress_cut_skip = False

    def _on_rewind(self):
        active = self._active_player()
        fps = self.engine.get_video_fps()
        frame_ms = int(1000.0 / fps) if fps > 0 else 33
        pos = max(active.position() - frame_ms, 0)
        self.engine.seek(pos / 1000.0)

    def _on_forward(self):
        active = self._active_player()
        fps = self.engine.get_video_fps()
        frame_ms = int(1000.0 / fps) if fps > 0 else 33
        pos = active.position() + frame_ms
        dur = active.duration()
        if dur > 0 and pos > dur:
            pos = dur
        self.engine.seek(pos / 1000.0)

    def _on_slider_moved(self, value: int):
        self.engine.seek(value / 1000.0)
        self._time_label.setText(f"{self._format_time(value)} / {self._format_time(self._active_player().duration())}")

    def _on_slider_released(self):
        self.engine.seek(self._slider.value() / 1000.0)

    def _on_speed_prev(self):
        if self._speed_index > 0:
            self._speed_index -= 1
            self._apply_speed()

    def _on_speed_next(self):
        if self._speed_index < len(SPEED_PRESETS) - 1:
            self._speed_index += 1
            self._apply_speed()

    def _apply_speed(self):
        speed = SPEED_PRESETS[self._speed_index]
        self.engine.set_playback_rate(speed)
        self._speed_label.setText(f"{speed}x")
        self._update_speed_buttons()
        self.speed_changed.emit(speed)

    def _update_speed_buttons(self):
        self._btn_speed_prev.setEnabled(self._speed_index > 0)
        self._btn_speed_next.setEnabled(self._speed_index < len(SPEED_PRESETS) - 1)

    def _on_volume_changed(self, vol: float):
        if self.engine._mode == "video":
            self.engine.set_video_volume(vol)
            self.video_volume_changed.emit(vol)
        else:
            self.engine.set_audio_volume(vol)
            self.audio_volume_changed.emit(vol)

    def _apply_volume(self):
        vol = self._video_volume if self.engine._mode == "video" else self._audio_volume
        self._volume_control.set_volume(vol)

    def _on_engine_position(self, seconds: float):
        self.position_changed.emit(seconds)
        if not self._slider.isSliderDown():
            self._slider.setValue(int(seconds * 1000))
        self._time_label.setText(f"{self._format_time(int(seconds * 1000))} / {self._format_time(self._active_player().duration())}")

    def _on_engine_duration(self, seconds: float):
        self.duration_changed.emit(seconds)
        self._slider.setRange(0, int(seconds * 1000))

    def _on_engine_state(self, is_playing: bool):
        self._btn_play.setText("⏸" if is_playing else "▶")

    def _on_engine_frame(self, image):
        self._video_widget.set_image(image)
        if self._last_source_resolution == (0, 0) and image.width() > 0:
            self._last_source_resolution = (image.width(), image.height())
        if self._keep_frames:
            self._last_frame = QPixmap.fromImage(image)

    def _on_engine_meta(self, w: int, h: int, fps: float):
        if w > 0 and h > 0:
            self._last_source_resolution = (w, h)
            self.source_resolution_changed.emit(w, h)

    def _relayout_shift_buttons(self):
        if not self._btn_shift_left.isVisible():
            return
        w, h = self._video_area.width(), self._video_area.height()
        self._btn_shift_left.move(20, (h - 36) // 2)
        self._btn_shift_right.move(w - 56, (h - 36) // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_shift_buttons()

    @staticmethod
    def _format_time(ms: int) -> str:
        seconds = ms // 1000
        return f"{seconds // 60:02}:{seconds % 60:02}"
