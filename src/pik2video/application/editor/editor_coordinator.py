# src/pik2video/application/editor/editor_coordinator.py
"""
Координатор бизнес-логики редактора.

Отвечает за:
- cut-skip: пропуск вырезанных участков при воспроизведении
- loop: возврат на начало первого видимого
- stop: остановка на конце последнего видимого
- jump to start после загрузки файла / смены активного
- запрос первого кадра (play_until_first_frame)
- сдвиг рамки по меткам зума (offset_x, zoom)

Не знает:
- про виджеты (кнопки, диалоги, меню)
- про пиксели, зум, скролл

Эмитит сигналы для view (window.py) — для будущих шагов:
- preview_frame_ready(x, y) — показать превью кадра при scrub
- preview_hide_requested() — скрыть превью
"""

import logging

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


class EditorCoordinator(QObject):
    """Бизнес-оркестратор редактора."""

    preview_frame_ready = Signal(int, int)
    preview_hide_requested = Signal()

    def __init__(self, state, player_manager, parent=None):
        super().__init__(parent)
        self.state = state
        self.player = player_manager

        # Флаги cut-skip
        self._skip_cut_in_progress = False
        self._pending_jump_to_start = False
        self._cut_stopped_at = None

        # Подписки на плеер
        self.player.position_changed.connect(self.on_player_position_changed)
        self.player.duration_changed.connect(self.on_duration_changed)
        self.player.audio_duration_changed.connect(self.on_audio_duration_changed)
        # Резолверы (resolve_pre_play, resolve_start) передаются в PlayerWidget
        # через window.py — координатор не знает про view.

    # ── Duration ──

    def on_duration_changed(self, seconds: float):
        """Плеер сообщил длительность видео."""
        if self.state.has_videos():
            self.state.update_active_duration(seconds)

        if self._pending_jump_to_start:
            self._do_jump_to_start()

    def on_audio_duration_changed(self, seconds: float):
        """Плеер сообщил длительность аудио."""
        if self.state.has_audio():
            self.state.set_audio_duration(seconds)

    # ── Загрузка видео / jump to start ──

    def on_video_loaded(self):
        """Вызывается из window._on_video_loaded после load_video в плеер.

        Ставит флаг: при ближайшем durationChanged сделаем jump на first_visible.
        Плюс fallback-таймер — если duration уже прошёл до загрузки.
        """
        self._pending_jump_to_start = True
        QTimer.singleShot(300, self._do_jump_to_start)

    def _do_jump_to_start(self):
        """Идемпотентно: прыжок на first_visible + запрос первого кадра."""
        if not self._pending_jump_to_start:
            return
        self._pending_jump_to_start = False
        visible = self.state.get_visible_intervals()
        target = visible[0][0] if visible else 0.0
        self.player.seek(target)
        QTimer.singleShot(80, self._request_first_frame)

    def _request_first_frame(self):
        """play_until_first_frame: play → pause после 1-го кадра."""
        try:
            if not self.player.is_playing():
                self.player.play_until_first_frame(timeout_ms=1500)
        except RuntimeError:
            pass

    # ── Cut-skip / loop / stop ──

    def on_player_position_changed(self, seconds: float):
        """При движении плеера: cut-skip + loop/stop + сдвиг рамки по меткам зума."""
        if self.player.suppress_cut_skip:
            return

        # ── 1. Перескок / loop на cut-участках ──
        if (not self._skip_cut_in_progress
                and self.player.is_playing()):
            if not self.state.is_time_visible(seconds):
                next_time = self.state.next_visible_time(seconds)

                if abs(next_time - seconds) < 0.01:
                    # Хвостовой cut — нет видимого после
                    visible = self.state.get_visible_intervals()
                    if not visible:
                        return

                    # Защита от повторного срабатывания
                    if (self._cut_stopped_at is not None
                            and abs(self._cut_stopped_at - seconds) < 0.5):
                        return

                    if self.player.is_loop_enabled():
                        loop_start = self.resolve_start(0.0)
                        logger.debug(
                            f"[CUT-LOOP] {seconds:.2f} → {loop_start:.2f}"
                        )
                        self._skip_cut_in_progress = True
                        try:
                            self.player.seek(loop_start)
                        finally:
                            self._skip_cut_in_progress = False
                    else:
                        last_end = visible[-1][1]
                        logger.debug(
                            f"[CUT-STOP] {seconds:.2f}: пауза на {last_end:.2f}"
                        )
                        self._skip_cut_in_progress = True
                        self._cut_stopped_at = last_end
                        try:
                            self.player.pause()
                            self.player.seek(last_end)
                        finally:
                            self._skip_cut_in_progress = False
                    return

                logger.debug(f"[CUT-SKIP] {seconds:.2f} → {next_time:.2f}")
                self._skip_cut_in_progress = True
                try:
                    self.player.seek(next_time)
                finally:
                    self._skip_cut_in_progress = False
                return

        # ── 2. Сдвиг рамки по меткам зума (offset_x, zoom) ──
        markers = self.state.get_markers()
        if not markers:
            self.state.set_offset_x(0.0, save=False)
            return

        active_offset, active_zoom = self.state.get_marker_state_at(seconds)
        self.state.set_offset_x(active_offset, save=False)
        self.state.set_aspect_zoom(active_zoom, save=False)

    # ── Резолверы для play / ⏮ / loop ──

    def _first_visible_start(self, default: float) -> float:
        visible = self.state.get_visible_intervals()
        if not visible:
            return default
        return visible[0][0]

    def resolve_pre_play(self, current_sec: float):
        """Перед play: если в cut или на конце видимого — на начало видимого."""
        self._cut_stopped_at = None

        visible = self.state.get_visible_intervals()
        if not visible:
            return None

        if not self.state.is_time_visible(current_sec):
            next_t = self.state.next_visible_time(current_sec)
            if abs(next_t - current_sec) < 0.01:
                return visible[0][0]
            return next_t

        for start, end in visible:
            if start <= current_sec <= end:
                if current_sec >= end - 0.1:
                    return visible[0][0]
                return None

        return None

    def resolve_start(self, default_sec: float) -> float:
        """⏮ и loop: всегда к началу первого видимого."""
        self._cut_stopped_at = None
        visible = self.state.get_visible_intervals()
        result = visible[0][0] if visible else default_sec
        logger.debug(
            f"[RESOLVE-START] default={default_sec:.2f} visible={visible} → {result:.2f}"
        )
        return result
