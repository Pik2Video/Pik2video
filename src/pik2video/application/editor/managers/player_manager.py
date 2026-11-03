# src/pik2video/application/editor/managers/player_manager.py
"""
Менеджер плеера — обёртка над QMediaPlayer.

Отвечает за:
- работу с видео- и аудио-плеерами (QMediaPlayer, QAudioOutput, QVideoSink)
- синхронизацию аудио с видео (audio_offset, trim, linked_mode)
- логику loop (через loop_start_resolver)
- play_until_first_frame (play → pause после 1-го кадра)
- публикацию сигналов: position_changed, duration_changed, video_frame_ready,
  playback_state_changed, meta_data_ready

Не знает:
- про GUI (пиксели, виджеты)
- про state (метки, cut — это снаружи)
- про ffmpeg

Раньше жил как gui/editor/player/engine.py (PlayerEngine).
"""

import logging

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QImage
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

logger = logging.getLogger(__name__)

DEFAULT_FPS = 30.0


class PlayerManager(QObject):
    """Работа с медиа (QMediaPlayer) и синхронизация аудио/видео."""

    position_changed = Signal(float)
    duration_changed = Signal(float)
    audio_duration_changed = Signal(float)
    playback_state_changed = Signal(bool)   # True = играет, False = пауза
    video_frame_ready = Signal(QImage)
    meta_data_ready = Signal(int, int, float)   # width, height, fps

    def __init__(self, parent=None):
        super().__init__(parent)

        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._audio_player = QMediaPlayer(self)
        self._audio_player_out = QAudioOutput(self)
        self._audio_player.setAudioOutput(self._audio_player_out)

        self._video_sink = QVideoSink(self)
        self._player.setVideoOutput(self._video_sink)
        self._video_sink.videoFrameChanged.connect(self._on_video_frame)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.metaDataChanged.connect(self._on_meta_data_changed)

        self._audio_player.positionChanged.connect(self._on_audio_position_changed)
        self._audio_player.durationChanged.connect(self._on_audio_duration_changed)
        self._audio_player.playbackStateChanged.connect(self._on_state_changed)

        self._mode = "video"
        self._linked_mode = True
        self._loop_enabled = False

        self._trim_start = 0.0
        self._trim_end = 0.0
        self._audio_trim_start = 0.0
        self._audio_trim_end = 0.0
        self._audio_offset = 0.0

        self._video_volume = 1.0
        self._audio_volume = 1.0
        self._video_fps = DEFAULT_FPS
        self._pause_on_next_frame = False       # play → pause после 1-го кадра
        self.suppress_cut_skip = False          # блокировать cut-skip во время внутренних seek
        self._restore_volume_after = None       # сохранить громкость на время play_until_first_frame
        self._restore_rate_after = None         # сохранить playbackRate на время play_until_first_frame
        self._loop_start_resolver = None        # fn(default_sec) -> start_sec

    # ── API ──

    def set_mode(self, mode: str):
        self._mode = mode

    def set_linked_mode(self, linked: bool):
        self._linked_mode = linked
        if not linked and self._mode == "video":
            self._audio_player.pause()
        elif not linked and self._mode == "audio":
            self._player.pause()

    def set_loop(self, enabled: bool):
        self._loop_enabled = enabled

    def is_loop_enabled(self) -> bool:
        return self._loop_enabled

    def set_loop_start_resolver(self, fn):
        """fn(default_start_sec) -> start_sec. Вызывается при loop."""
        self._loop_start_resolver = fn

    def set_trim_range(self, start: float, end: float):
        self._trim_start = max(0.0, start)
        self._trim_end = max(start, end)
        self._apply_audio_volume()

    def set_audio_trim_range(self, start: float, end: float):
        self._audio_trim_start = max(0.0, start)
        self._audio_trim_end = max(start, end)
        self._apply_audio_volume()

    def set_audio_offset(self, offset: float):
        self._audio_offset = max(0.0, offset)
        self._sync_audio_to_video()
        self._apply_audio_volume()

    def set_playback_rate(self, rate: float):
        self._player.setPlaybackRate(rate)
        self._audio_player.setPlaybackRate(rate)

    def set_video_volume(self, vol: float):
        self._video_volume = max(0.0, min(1.0, vol))
        self._audio_output.setVolume(self._video_volume)

    def set_audio_volume(self, vol: float):
        self._audio_volume = max(0.0, min(1.0, vol))
        self._apply_audio_volume()

    def load_video(self, path: str):
        """Загрузить видео. Только setSource — без play/pause/seek.

        Раньше здесь было play()/pause()/setPosition(0) подряд — на 4K-файлах
        это блокировало главный поток на 30-40 сек (ждёт мьютекс FFmpeg-плагина).
        Первый кадр — через play_until_first_frame (из window.py).
        """
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(path))

    def unload_video(self):
        self._player.stop()
        self._player.setSource(QUrl())

    def load_audio(self, path: str):
        self._audio_player.stop()
        self._audio_player.setSource(QUrl())
        self._audio_player.setSource(QUrl.fromLocalFile(path))
        self._apply_audio_volume()

    def unload_audio(self):
        self._audio_player.stop()
        self._audio_player.setSource(QUrl())

    def has_video(self) -> bool:
        return self._player.source().isValid()

    def has_audio(self) -> bool:
        return self._audio_player.source().isValid()

    def play_until_first_frame(self, timeout_ms: int = 500):
        """Play → pause сразу после первого кадра. Для показа превью.

        Звук глушится на время показа (иначе слышно «мгновенное воспроизведение»).
        Пауза — ровно на 1-м кадре (быстрый старт), fallback — по таймеру 500мс
        (4K/битый файл). На 4K окно «мелькания» до 500мс, но без звука.
        """
        if not self.has_video():
            return
        self._pause_on_next_frame = True
        # Скорость 0.01x: кадр почти не сдвигается за время ожидания.
        # Мелькания нет. Звука тоже (0.5мс аудио = тишина).
        self._restore_rate_after = self._player.playbackRate()
        try:
            self._player.setPlaybackRate(0.01)
        except RuntimeError:
            self._restore_rate_after = None
        try:
            self._player.play()
        except RuntimeError:
            self._pause_on_next_frame = False
            self._restore_rate_now()
            return
        QTimer.singleShot(timeout_ms, self._fallback_pause_if_waiting)

    def _fallback_pause_if_waiting(self):
        if self._pause_on_next_frame:
            self._pause_on_next_frame = False
            try:
                self._player.pause()
            except RuntimeError:
                pass
            self._restore_rate_now()

    def _restore_rate_now(self):
        """Восстановить playbackRate после play_until_first_frame."""
        if self._restore_rate_after is not None:
            try:
                self._player.setPlaybackRate(self._restore_rate_after)
            except RuntimeError:
                pass
            self._restore_rate_after = None

    def get_position(self) -> float:
        return self._active_player().position() / 1000.0

    def get_duration(self) -> float:
        return self._active_player().duration() / 1000.0

    def get_video_fps(self) -> float:
        return self._video_fps

    def is_playing(self) -> bool:
        return self._active_player().playbackState() == QMediaPlayer.PlayingState

    def play(self):
        if not self.has_video() and not self.has_audio():
            return
        active = self._active_player()
        pos = active.position() / 1000.0
        trim_start, trim_end = self._trim_for(active)

        if trim_end > 0 and (pos < trim_start or pos >= trim_end - 0.05):
            active.setPosition(int(trim_start * 1000))

        if self._mode == "video":
            self._player.play()
            if self._linked_mode and self.has_audio():
                self._sync_audio_to_video()
            self._apply_audio_volume()
        else:
            self._audio_player.play()
            self._apply_audio_volume()

    def pause(self):
        self._player.pause()
        self._audio_player.pause()

    def seek(self, seconds: float):
        active = self._active_player()
        # Если duration ещё не известен (файл грузится) — setPosition игнорируется.
        if active.duration() <= 0:
            return
        active.setPosition(int(seconds * 1000))
        if self._mode == "video" and self.has_audio():
            self._sync_audio_to_video()
        self._apply_audio_volume()

    def seek_for_preview(self, seconds: float):
        if self._player.duration() > 0:
            self._player.setPosition(int(seconds * 1000))

    # ── Internal ──

    def _active_player(self):
        return self._player if self._mode == "video" else self._audio_player

    def _trim_for(self, player):
        if player is self._player:
            return self._trim_start, self._trim_end
        return self._audio_trim_start, self._audio_trim_end

    def _on_video_frame(self, frame):
        if frame is None or not frame.isValid():
            return
        image = frame.toImage()
        if not image.isNull():
            self.video_frame_ready.emit(image)

        # Ждём первый кадр → пауза + восстановление скорости
        if self._pause_on_next_frame:
            self._pause_on_next_frame = False
            try:
                self._player.pause()
            except RuntimeError:
                pass
            self._restore_rate_now()

    def _on_position_changed(self, ms: int):
        if self._mode != "video":
            return
        self._process_position(ms, self._player)
        self._sync_audio_to_video()
        self._apply_audio_volume()

    def _on_audio_position_changed(self, ms: int):
        if self._mode == "audio":
            self._process_position(ms, self._audio_player)
            return
        self._apply_audio_volume()

    def _process_position(self, ms: int, player):
        seconds = ms / 1000.0
        trim_start, trim_end = self._trim_for(player)

        if trim_end > 0 and seconds >= trim_end and player.playbackState() == QMediaPlayer.PlayingState:
            if self._loop_enabled:
                loop_start = trim_start
                if self._loop_start_resolver is not None:
                    loop_start = self._loop_start_resolver(trim_start)
                player.setPosition(int(loop_start * 1000))
                if player is self._player and self.has_audio():
                    self._sync_audio_to_video()
                return
            else:
                player.pause()
                player.setPosition(int(trim_end * 1000))
                self.position_changed.emit(trim_end)
                return

        self.position_changed.emit(seconds)

    def _on_duration_changed(self, ms: int):
        self.duration_changed.emit(ms / 1000.0)

    def _on_audio_duration_changed(self, ms: int):
        self.audio_duration_changed.emit(ms / 1000.0)

    def _on_state_changed(self, state):
        # Сигнал о play/pause — только от АКТИВНОГО плеера.
        # Иначе при завершении аудио (видео ещё играет) кнопка дёргается.
        sender = self.sender()
        if self._mode == "video" and sender is self._audio_player:
            return
        if self._mode == "audio" and sender is self._player:
            return
        self.playback_state_changed.emit(state == QMediaPlayer.PlayingState)

    def _on_meta_data_changed(self):
        meta = self._player.metaData()
        if not meta:
            return
        from PySide6.QtMultimedia import QMediaMetaData
        resolution = meta.value(QMediaMetaData.Key.Resolution)
        w, h = (0, 0)
        if resolution is not None and not resolution.isEmpty():
            w, h = resolution.width(), resolution.height()

        fps = meta.value(QMediaMetaData.Key.VideoFrameRate)
        if fps is not None and float(fps) > 0:
            self._video_fps = float(fps)

        self.meta_data_ready.emit(w, h, self._video_fps)

    def _sync_audio_to_video(self):
        if not self._linked_mode or not self.has_audio():
            return
        video_pos = self._player.position() / 1000.0
        audio_pos = video_pos - self._audio_offset
        video_playing = self._player.playbackState() == QMediaPlayer.PlayingState

        if audio_pos < 0:
            if self._audio_player.playbackState() == QMediaPlayer.PlayingState:
                self._audio_player.pause()
            self._audio_player.setPosition(0)
            return

        audio_dur = self._audio_player.duration() / 1000.0

        # Аудио уже закончилось, а видео продолжается → не рестартить
        if audio_dur > 0 and video_pos - self._audio_offset >= audio_dur - 0.05:
            if self._audio_player.playbackState() == QMediaPlayer.PlayingState:
                self._audio_player.pause()
            return

        if audio_dur > 0 and audio_pos > audio_dur:
            audio_pos = audio_dur

        actual = self._audio_player.position() / 1000.0
        if abs(actual - audio_pos) > 0.3:
            self._audio_player.setPosition(int(audio_pos * 1000))

        if video_playing and self._audio_player.playbackState() != QMediaPlayer.PlayingState:
            self._audio_player.play()
        elif not video_playing and self._audio_player.playbackState() == QMediaPlayer.PlayingState:
            self._audio_player.pause()

    def _apply_audio_volume(self):
        if not self.has_audio():
            return
        if not self._linked_mode:
            vol = self._audio_volume if self._mode == "audio" else 0.0
            self._audio_player_out.setVolume(vol)
            return
        if self._mode == "audio":
            self._audio_player_out.setVolume(self._audio_volume)
            return
        if self._audio_trim_end <= 0:
            self._audio_player_out.setVolume(self._audio_volume)
            return
        pos = self._player.position() / 1000.0
        start_on_video = self._audio_offset + self._audio_trim_start
        end_on_video = self._audio_offset + self._audio_trim_end
        if start_on_video <= pos <= end_on_video:
            self._audio_player_out.setVolume(self._audio_volume)
        else:
            self._audio_player_out.setVolume(0.0)
