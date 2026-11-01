# src/pik2video/gui/editor/player.py
"""
Мультиплеер — обёртка над QMediaPlayer + QVideoWidget + панель управления.

Отвечает только за:
- воспроизведение видеофайла
- показ первого кадра при загрузке
- публикацию позиции

Не знает:
- про EditorState
- про drop-зоны
- про экспорт
"""

import logging
from pathlib import Path

from PySide6.QtCore import QRect, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QStackedLayout,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .surface import PresetFrame, VideoSurface
from .volume import VolumeControl
from src.pik2video.gui.common.styles import PLAYER_QSS

logger = logging.getLogger(__name__)

# Пресеты скорости воспроизведения
SPEED_PRESETS = [0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0]

# Шаг перемотки в секундах
DEFAULT_FPS = 30.0       # fallback, если FPS видео не удалось получить


class PlayerWidget(QWidget):
    """Плеер с placeholder-страницей и страницей видео."""

    position_changed = Signal(float)        # секунды (видео)
    duration_changed = Signal(float)        # секунды (видео)
    audio_duration_changed = Signal(float)  # секунды (аудио) — отдельно от video
    speed_changed = Signal(float)           # выбранная скорость (для экспорта)
    video_volume_changed = Signal(float)    # громкость видео-плеера (для сохранения)
    audio_volume_changed = Signal(float)    # громкость аудио-плеера (для сохранения)
    source_resolution_changed = Signal(int, int)   # ширина, высота
    crop_rect_drawn = Signal(QRect)                # рабочая зона, нарисованная вручную
    shift_left_requested = Signal()
    shift_right_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # Прозрачный фон: полупрозрачные края VideoSurface должны
        # просвечивать до фона редактора (#1e1e1e в central window.py).
        self.setStyleSheet(PLAYER_QSS)

        # ── Медиа-объекты (до сборки UI) ──
        # ── Видео-плеер (картинка + встроенный звук видео) ──
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        # ── Отдельный плеер для аудиофайла (играет вместе с видео) ──
        self._audio_player = QMediaPlayer(self)
        self._audio_player_out = QAudioOutput(self)
        self._audio_player.setAudioOutput(self._audio_player_out)

        self._mode = "video"                          # текущий активный режим: "video" | "audio"

        self._trim_start = 0.0                # видео-трим
        self._trim_end = 0.0
        self._audio_trim_start = 0.0          # аудио-трим (отдельно)
        self._audio_trim_end = 0.0
        self._audio_offset = 0.0              # сдвиг аудио относительно видео (сек)
        self._saved_video_pos = 0.0           # позиция видео до переключения на audio
        self._linked_mode = True              # True = видео+аудио связаны; False = только активный
        self._marker_mode_active = False      # True = карандаш активен — блокирует transport
        self._loop_enabled = False
        self._last_frame = None
        self._keep_frames = True   # кэшировать кадры
        self._pending_play = False  # идёт seek от кнопки ▶
        self._current_crop_rect: tuple = (0.0, 0.0, 0.0, 0.0)

        self._video_volume = 1.0   # громкость видео-плеера
        self._audio_volume = 1.0   # громкость аудио-плеера
        self._video_fps = DEFAULT_FPS   # для покадровой перемотки; обновится из метаданных


        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("background: transparent;")

        self._placeholder_page = self._build_placeholder()
        self._stack.addWidget(self._placeholder_page)

        self._player_page = self._build_player_page()
        self._stack.addWidget(self._player_page)

        self._audio_page = self._build_audio_page()              # страница для аудио-онли
        self._stack.addWidget(self._audio_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._stack, stretch=1)

        self._controls = self._build_controls()                  # общая панель управления для видео и аудио
        layout.addWidget(self._controls, stretch=0)



        self._video_sink = QVideoSink(self)
        self._player.setVideoOutput(self._video_sink)
        self._video_sink.videoFrameChanged.connect(self._on_video_frame)

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)
        self._player.metaDataChanged.connect(self._on_meta_data_changed)

        self._audio_player.positionChanged.connect(self._on_audio_position_changed)
        self._audio_player.durationChanged.connect(self._on_audio_duration_changed)
        self._audio_player.playbackStateChanged.connect(self._on_audio_state_changed)

        self._show_placeholder()
        self._set_controls_enabled(False)                 # старт без файлов — управление отключено

    def _build_placeholder(self) -> QWidget:
        """Заглушка, когда ничего не загружено."""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel("Загрузите видеофайл")                        # текст-заглушка
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 16px;")
        layout.addWidget(label)

        return page

    # ── Построение UI ──

    def _build_player_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._video_area = QWidget()
        # Прозрачный фон: чёрный (и полупрозрачный) цвет даёт VideoSurface.
        # Иначе глухой чёрный перекроет полупрозрачные края вокруг canvas.
        self._video_area.setStyleSheet("background: transparent;")
        self._video_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._video_area, stretch=1)

        self._video_widget = VideoSurface()
        self._preset_frame = PresetFrame()
        self._preset_frame.hide()

        # Стек поверх: video снизу, пресет-рамка сверху
        stack = QStackedLayout(self._video_area)
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._video_widget)
        stack.addWidget(self._preset_frame)

        self._preset_frame.crop_rect_drawn.connect(self.crop_rect_drawn.emit)

        # Кнопки сдвига рамки (поверх видео)
        self._btn_shift_left = QPushButton("←", self._video_area)
        self._btn_shift_left.setFixedSize(36, 36)
        self._btn_shift_left.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 140);
                color: white;
                border: 1px solid rgba(255, 255, 255, 80);
                border-radius: 18px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: rgba(0, 0, 0, 200); }
            QPushButton:pressed { background-color: rgba(0, 0, 0, 255); }
            QPushButton:disabled { color: #666; border-color: #444; }
        """)
        self._shift_left_effect = QGraphicsOpacityEffect(self._btn_shift_left)
        self._shift_left_effect.setOpacity(1.0)
        self._btn_shift_left.setGraphicsEffect(self._shift_left_effect)
        self._btn_shift_left.clicked.connect(self.shift_left_requested.emit)
        self._btn_shift_left.hide()

        self._btn_shift_right = QPushButton("→", self._video_area)
        self._btn_shift_right.setFixedSize(36, 36)
        self._btn_shift_right.setStyleSheet(self._btn_shift_left.styleSheet())
        self._shift_right_effect = QGraphicsOpacityEffect(self._btn_shift_right)
        self._shift_right_effect.setOpacity(1.0)
        self._btn_shift_right.setGraphicsEffect(self._shift_right_effect)
        self._btn_shift_right.clicked.connect(self.shift_right_requested.emit)
        self._btn_shift_right.hide()

        self._last_source_resolution = (0, 0)
        return page

    def _build_audio_page(self) -> QWidget:
        """Страница для аудио-онли: иконка и имя файла."""
        page = QWidget()
        page.setStyleSheet("background-color: #000;")

        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(0)

        self._audio_icon = QLabel("🎵")                                    # иконка ноты
        self._audio_icon.setAlignment(Qt.AlignCenter)
        self._audio_icon.setStyleSheet("font-size: 64px; background: transparent; border: none;")

        self._audio_name = QLabel("")                                      # имя файла
        self._audio_name.setAlignment(Qt.AlignCenter)
        self._audio_name.setStyleSheet("color: #888; font-size: 13px; background: transparent; border: none;")

        layout.addWidget(self._audio_icon)
        layout.addWidget(self._audio_name)

        return page

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("controlBar")
        bar.setFixedHeight(32)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)

        # Play/Pause
        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(28, 24)
        self._btn_play.clicked.connect(self._toggle_play)

        # В начало (trim start)
        self._btn_go_start = QPushButton("↺")
        self._btn_go_start.setFixedSize(28, 24)
        self._btn_go_start.clicked.connect(self._on_go_to_start)
        layout.addWidget(self._btn_go_start)
        layout.addSpacing(6)

        self._btn_rewind = QPushButton("⏪")
        self._btn_rewind.setFixedSize(28, 24)
        self._btn_rewind.clicked.connect(self._on_rewind)
        layout.addWidget(self._btn_rewind)
        layout.addSpacing(2)
        layout.addWidget(self._btn_play)
        layout.addSpacing(2)

        # Перемотка вперёд
        self._btn_forward = QPushButton("⏩")
        self._btn_forward.setFixedSize(28, 24)
        self._btn_forward.clicked.connect(self._on_forward)
        layout.addWidget(self._btn_forward)
        layout.addSpacing(6)

        # Повтор
        self._btn_loop = QPushButton("🔁")
        self._btn_loop.setObjectName("btnLoop")
        self._btn_loop.setFixedSize(28, 24)
        self._btn_loop.setCheckable(True)
        self._btn_loop.toggled.connect(self._on_loop_toggled)
        layout.addWidget(self._btn_loop)
        layout.addSpacing(8)

        # Время: текущее / общее
        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setFixedWidth(100)
        self._time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._time_label)
        layout.addSpacing(8)

        # Слайдер позиции
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self._slider, stretch=1)
        layout.addSpacing(8)

        # ── Блок скорости воспроизведения ──
        speed_block = QWidget()
        speed_block.setStyleSheet("background: transparent; border: none;")
        speed_layout = QHBoxLayout(speed_block)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)

        self._btn_speed_prev = QPushButton("<")
        self._btn_speed_prev.setObjectName("btnSpeed")
        self._btn_speed_prev.setFixedSize(20, 24)
        self._btn_speed_prev.clicked.connect(self._on_speed_prev)

        self._speed_label = QLabel("1x")
        self._speed_label.setObjectName("speedLabel")
        self._speed_label.setFixedWidth(36)
        self._speed_label.setAlignment(Qt.AlignCenter)

        self._btn_speed_next = QPushButton(">")
        self._btn_speed_next.setObjectName("btnSpeed")
        self._btn_speed_next.setFixedSize(20, 24)
        self._btn_speed_next.clicked.connect(self._on_speed_next)

        speed_layout.addWidget(self._btn_speed_prev)
        speed_layout.addWidget(self._speed_label)
        speed_layout.addWidget(self._btn_speed_next)

        layout.addWidget(speed_block)
        layout.addSpacing(8)

        # ── Громкость ──
        self._volume_control = VolumeControl(initial=1.0)
        self._volume_control.volume_changed.connect(self._on_volume_changed)
        layout.addWidget(self._volume_control)

        self._speed_index = SPEED_PRESETS.index(1.0)
        self._video_speed_index = SPEED_PRESETS.index(1.0)
        self._audio_speed_index = SPEED_PRESETS.index(1.0)
        self._update_speed_buttons()

        return bar

    def load_video(self, path: str):
        """Загрузить видео и показать первый кадр."""
        logger.info(f"Плеер загружает видео: {path}")
        self._set_controls_enabled(True)

        self._player.stop()                                       # остановить старое воспроизведение
        self._player.setSource(QUrl())                            # сбросить источник — старый файл закрывается
        self._player.setSource(QUrl.fromLocalFile(path))          # загрузить новый источник

        if self._mode == "video":
            self._show_player()                                   # показать страницу видео

        self._player.play()                                       # запустить для декодирования первого кадра
        self._player.pause()                                      # сразу пауза — кадр остаётся на экране
        self._player.setPosition(0)                               # встать на нулевую позицию


    def unload_video(self):
        """Остановить и вернуть placeholder. Отложенно — setSource блокирует UI."""
        self._video_widget.clear_image()
        self._trim_start = 0.0
        self._trim_end = 0.0
        self._saved_video_pos = 0.0
        self._video_speed_index = SPEED_PRESETS.index(1.0)      # сброс скорости видео
        if abs(self._player.playbackRate() - 1.0) > 0.01:
            self._player.setPlaybackRate(1.0)
        QTimer.singleShot(0, self._sync_speed_ui)
        QTimer.singleShot(0, self._deferred_unload_video)

    def _deferred_unload_video(self):
        try:
            self._player.stop()
            self._player.setSource(QUrl())
        except RuntimeError:
            pass
        self._maybe_reset_ui()

    def load_audio(self, path: str):
        """Загрузить аудиофайл во второй плеер (звук играет вместе с видео)."""
        logger.info(f"Плеер загружает аудио: {path}")
        self._set_controls_enabled(True)
        self._audio_player.stop()
        self._audio_player.setSource(QUrl())
        self._audio_player.setSource(QUrl.fromLocalFile(path))
        self._audio_name.setText(Path(path).name)

        if self._mode == "audio" or not self._has_video_source():
            self._stack.setCurrentWidget(self._audio_page)

        self._apply_audio_volume()                              # применить текущую громкость

    def unload_audio(self):
        """Остановить аудио-плеер. Отложенно — setSource блокирует UI."""
        self._audio_name.setText("")
        self._audio_trim_start = 0.0
        self._audio_trim_end = 0.0
        self._audio_offset = 0.0
        self._audio_speed_index = SPEED_PRESETS.index(1.0)      # сброс скорости аудио
        if abs(self._audio_player.playbackRate() - 1.0) > 0.01:
            self._audio_player.setPlaybackRate(1.0)
        QTimer.singleShot(0, self._sync_speed_ui)
        QTimer.singleShot(0, self._deferred_unload_audio)

    def _deferred_unload_audio(self):
        try:
            self._audio_player.stop()
            self._audio_player.setSource(QUrl())
        except RuntimeError:
            pass
        self._maybe_reset_ui()

    def _reset_player_ui(self):
        """Сбросить визуальные элементы плеера (слайдер, время, кнопка play)."""
        self._slider.setRange(0, 0)
        self._slider.setValue(0)
        self._time_label.setText("00:00 / 00:00")
        self._btn_play.setText("▶")
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled: bool):
        """Элементы управления. В режиме карандаша блокируется только воспроизведение."""
        self._btn_play.setEnabled(enabled and not self._marker_mode_active)
        self._btn_go_start.setEnabled(enabled)
        self._btn_rewind.setEnabled(enabled)
        self._btn_forward.setEnabled(enabled)
        self._btn_loop.setEnabled(enabled)
        self._slider.setEnabled(enabled)
        self._btn_speed_prev.setEnabled(enabled)
        self._btn_speed_next.setEnabled(enabled)
        self._volume_control.setEnabled(enabled)

    def _maybe_reset_ui(self):
        """Если оба источника пусты — показать заглушку и сбросить UI."""
        if self._has_video_source() or self._has_audio_source():
            return
        self._show_placeholder()
        self._reset_player_ui()

    def _has_video_source(self) -> bool:
        """Есть ли загруженный видео-источник."""
        return self._player.source().isValid()

    def _has_audio_source(self) -> bool:
        """Есть ли загруженный аудио-источник."""
        return self._audio_player.source().isValid()

    def _active_player(self):
        """Плеер, соответствующий текущему режиму."""
        return self._player if self._mode == "video" else self._audio_player

    def set_preset_visible(self, visible: bool):
        """Показать/скрыть оверлей пресета."""
        if not visible or not self._has_video_source():
            self._preset_frame.hide()
            return
        self._preset_frame.show()
        self._preset_frame.raise_()

    def set_crop_rect(self, rect: tuple):
        """Установить рабочую зону (в координатах источника)."""
        self._current_crop_rect = tuple(rect)
        source_size = self._last_source_resolution
        self._preset_frame.set_crop_rect(self._current_crop_rect, source_size)
        self._video_widget.set_crop_rect(self._current_crop_rect, source_size)

    def set_canvas_ar(self, ar):
        """Установить AR canvas. None — режим original (видео целиком)."""
        self._preset_frame.set_canvas_ar(ar)
        self._video_widget.set_canvas_ar(ar)

    def set_preset_drawing(self, enabled: bool):
        """Включить/выключить ручное рисование в оверлее."""
        self._preset_frame.set_drawing_enabled(enabled)

    def set_mode(self, mode: str):
        """Переключить активный режим плеера: "video" или "audio"."""
        if mode not in ("video", "audio"):
            return
        if mode == self._mode:
            return

        logger.debug(f"Плеер: режим → {mode}")

        # Запомнить позицию активного плеера перед переключением
        if self._mode == "video":
            self._saved_video_pos = self._player.position() / 1000.0

        # Guard: pause() на не-Playing плеере на macOS Qt Multimedia может зависнуть
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
        if self._audio_player.playbackState() == QMediaPlayer.PlayingState:
            self._audio_player.pause()

        self._mode = mode

        # Отложить: setPlaybackRate сразу после pause() на macOS может зависнуть
        QTimer.singleShot(0, self._sync_speed_ui)

        if mode == "video":
            if self._has_video_source():
                self._show_player()
                target = self._saved_video_pos
                QTimer.singleShot(0, lambda: self._deferred_seek(self._player, target))
                if self._has_audio_source():
                    QTimer.singleShot(0, self._sync_audio_to_video)
            else:
                self._show_placeholder()
        else:  # audio
            if self._has_audio_source():
                self._stack.setCurrentWidget(self._audio_page)
                # Переставить на левую метку аудио (обычно 0)
                target = self._audio_trim_start
                QTimer.singleShot(0, lambda: self._deferred_seek(self._audio_player, target))
            else:
                self._show_placeholder()

        # Обновить слайдер и метку времени под новый активный плеер
        active = self._active_player()
        dur_ms = active.duration()
        pos_ms = active.position()
        self._slider.setRange(0, dur_ms)
        self._slider.setValue(pos_ms)
        self._time_label.setText(
            f"{self._format_time(pos_ms)} / {self._format_time(dur_ms)}"
        )

        # Обновить ползунок в TimelineZone — эмитим новую позицию
        self.position_changed.emit(pos_ms / 1000.0)

        self._update_play_button()
        self._apply_audio_volume()                                  # пересчитать громкость аудио

        # Обновить отображение кнопки громкости под новый режим
        if mode == "video":
            self._volume_control.set_volume(self._video_volume)
        else:
            self._volume_control.set_volume(self._audio_volume)

    def _deferred_seek(self, player, seconds: float):
        """Безопасный seek: только если у плеера есть duration и позиция реально отличается.

        Вызывается через QTimer.singleShot(0) — чтобы не блокировать UI-поток
        в момент переключений и загрузки медиа (иначе Qt Multimedia залипает).
        """
        try:
            if player.duration() <= 0:
                return
            target = int(max(0.0, seconds) * 1000)
            if abs(player.position() - target) < 50:
                return
            player.setPosition(target)
        except RuntimeError:
            pass

    def seek_for_preview(self, seconds: float):
        """Двинуть только видео-плеер для получения кадра превью (без звука, без аудио-плеера)."""
        if self._player.duration() > 0:
            self._player.setPosition(int(seconds * 1000))

    def set_position(self, seconds: float):
        """Внешняя установка позиции (из таймлайна)."""
        if self._mode == "video":
            if self._player.duration() > 0:
                self._player.setPosition(int(seconds * 1000))
                if self._has_audio_source():
                    self._sync_audio_to_video()                      # с учётом offset
                self._apply_audio_volume()
        else:
            if self._audio_player.duration() > 0:
                self._audio_player.setPosition(int(seconds * 1000))

    def set_trim_range(self, start: float, end: float):
        """Обновить видео-трим. Плеер не выходит за его пределы."""
        self._trim_start = max(0.0, start)
        self._trim_end = max(start, end)
        self._apply_audio_volume()                                # пересчитать громкость аудио

    def set_audio_trim_range(self, start: float, end: float):
        """Обновить аудио-трим. Используется только аудио-плеером."""
        self._audio_trim_start = max(0.0, start)
        self._audio_trim_end = max(start, end)
        self._apply_audio_volume()                                # пересчитать громкость аудио

    def set_audio_offset(self, offset: float):
        """Установить сдвиг аудио относительно видео (сек)."""
        offset = max(0.0, offset)
        if self._audio_offset == offset:
            return
        self._audio_offset = offset
        self._sync_audio_to_video()
        self._apply_audio_volume()

    def _sync_audio_to_video(self):
        """Синхронизировать состояние и позицию аудио-плеера с учётом offset."""
        if not self._linked_mode:
            return                                        # в развязке не синхронизируем
        if not self._has_audio_source():
            return
        video_pos = self._player.position() / 1000.0
        audio_pos = video_pos - self._audio_offset
        video_playing = self._player.playbackState() == QMediaPlayer.PlayingState

        if audio_pos < 0:
            # до начала аудио-дорожки: держим на паузе, позиция 0
            if self._audio_player.playbackState() == QMediaPlayer.PlayingState:
                self._audio_player.pause()
            self._audio_player.setPosition(0)
            return

        audio_dur = self._audio_player.duration() / 1000.0
        if audio_dur > 0 and audio_pos > audio_dur:
            audio_pos = audio_dur

        actual = self._audio_player.position() / 1000.0
        if abs(actual - audio_pos) > 0.3:
            self._audio_player.setPosition(int(audio_pos * 1000))

        if video_playing and self._audio_player.playbackState() != QMediaPlayer.PlayingState:
            self._audio_player.play()
        elif not video_playing and self._audio_player.playbackState() == QMediaPlayer.PlayingState:
            self._audio_player.pause()

    def _trim_for(self, player):
        """Вернуть (start, end) трима для конкретного плеера."""
        if player is self._player:
            return self._trim_start, self._trim_end
        return self._audio_trim_start, self._audio_trim_end

    def get_position(self) -> float:
        return self._player.position() / 1000.0

    def get_duration(self) -> float:
        return self._player.duration() / 1000.0

    def get_last_frame(self):
        """Последний декодированный кадр (QPixmap) или None."""
        return self._last_frame

    def set_keep_frames(self, value: bool):
        """Включить/выключить кэширование кадров."""
        self._keep_frames = value
        if not value:
            self._last_frame = None

    def _relayout_video(self):
        """Обновить оверлей после ресайза. Геометрию виджетов держит QStackedLayout."""
        self._video_widget.update()
        if self._preset_frame.isVisible():
            self._preset_frame.update()

    def _on_video_frame(self, frame):
        """Сохранить последний кадр для превью и передать в VideoSurface."""
        if frame is None or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        
        self._video_widget.set_image(image)
        
        # Если метаданные ещё не пришли — взять размер из первого кадра
        frame_size = (image.width(), image.height())
        if self._last_source_resolution == (0, 0) and frame_size[0] > 0 and frame_size[1] > 0:
            self._last_source_resolution = frame_size
            self._preset_frame.set_crop_rect(self._current_crop_rect, frame_size)
            self._video_widget.set_crop_rect(self._current_crop_rect, frame_size)

        if self._keep_frames:
            self._last_frame = QPixmap.fromImage(image)

    # ── Внутренние слоты ──

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_video()

    def _show_placeholder(self):
        self._stack.setCurrentIndex(0)

    def _show_player(self):
        self._stack.setCurrentIndex(1)

    def set_linked_mode(self, linked: bool):
        """Включить/выключить связку. В развязке играет только активный плеер."""
        linked = bool(linked)
        if self._linked_mode == linked:
            return
        self._linked_mode = linked
        if linked:
            # Синхронизировать скорости: обе = скорость активного
            self._speed_index = (
                self._video_speed_index if self._mode == "video"
                else self._audio_speed_index
            )
            self._video_speed_index = self._speed_index
            self._audio_speed_index = self._speed_index
            speed = SPEED_PRESETS[self._speed_index]
            if abs(self._player.playbackRate() - speed) > 0.01:
                self._player.setPlaybackRate(speed)
            if abs(self._audio_player.playbackRate() - speed) > 0.01:
                self._audio_player.setPlaybackRate(speed)
            self._speed_label.setText(f"{speed}x")
            self._update_speed_buttons()
        else:
            # В развязке второй плеер должен замолчать.
            # Guard: не паузить, если уже не Playing (иначе macOS Qt Multimedia висит).
            if self._mode == "video":
                if self._audio_player.playbackState() == QMediaPlayer.PlayingState:
                    self._audio_player.pause()
            else:
                if self._player.playbackState() == QMediaPlayer.PlayingState:
                    self._player.pause()
        self._apply_audio_volume()

    def begin_trim_drag(self) -> bool:
        """Пауза перед drag метки. Возвращает True, если плеер играл."""
        active = self._active_player()
        if active.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._audio_player.pause()
            return True
        return False

    def end_trim_drag(self, was_playing: bool):
        """Возобновить воспроизведение после drag, если играло до него."""
        if not was_playing:
            return
        if self._mode == "video":
            self._player.play()
            if self._has_audio_source():
                self._audio_player.play()
        else:
            self._audio_player.play()

    def _toggle_play(self):
        if not self._has_video_source() and not self._has_audio_source():
            return
        active = self._active_player()

        if active.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._audio_player.pause()
            return

        pos = active.position() / 1000.0
        tolerance = 0.05
        trim_start, trim_end = self._trim_for(active)         # свой трим для активного плеера

        if trim_end > 0 and (pos < trim_start or pos >= trim_end - tolerance):
            self._pending_play = True
            active.setPosition(int(trim_start * 1000))

        if self._mode == "video":
            self._player.play()
            if self._linked_mode and self._has_audio_source():
                self._sync_audio_to_video()
            self._apply_audio_volume()
        else:
            self._audio_player.play()
            self._apply_audio_volume()

    def _on_position_changed(self, ms: int):
        """Позиция видео-плеера — обрабатывается только в режиме видео."""
        if self._mode != "video":
            return
        self._process_position(ms, self._player)
        self._sync_audio_to_video()                                 # синхронизация аудио с учётом offset
        self._apply_audio_volume()                                  # пересчитать громкость аудио

    def _on_audio_position_changed(self, ms: int):
        """Позиция аудио-плеера. В режиме video управляем только громкостью."""
        if self._mode == "audio":
            self._process_position(ms, self._audio_player)
            return

        self._apply_audio_volume()                                  # режим video: тихо/громко по позиции

    def _process_position(self, ms: int, player):
        """Общая логика обработки позиции для любого плеера."""
        if not self._slider.isSliderDown():
            self._slider.setValue(ms)
        self._time_label.setText(
            f"{self._format_time(ms)} / {self._format_time(player.duration())}"
        )

        seconds = ms / 1000.0
        trim_start, trim_end = self._trim_for(player)         # свой трим для этого плеера

        if self._pending_play:
            if seconds < trim_end - 0.05:
                self._pending_play = False
            else:
                self.position_changed.emit(seconds)
                return

        if (
            trim_end > 0
            and seconds >= trim_end
            and player.playbackState() == QMediaPlayer.PlayingState
        ):
            if self._loop_enabled:
                player.setPosition(int(trim_start * 1000))
                if player is self._player and self._has_audio_source():
                    self._sync_audio_to_video()
                return
            else:
                player.pause()
                player.setPosition(int(trim_end * 1000))
                self.position_changed.emit(trim_end)
                return

        self.position_changed.emit(seconds)

    def _on_duration_changed(self, ms: int):
        """Длительность видео — эмитим всегда (для video_timeline)."""
        self.duration_changed.emit(ms / 1000.0)
        if self._mode == "video":
            self._process_duration_ui(ms, self._player)             # обновить слайдер и время

    def _on_audio_duration_changed(self, ms: int):
        """Длительность аудио — эмитим всегда (для audio_timeline)."""
        self.audio_duration_changed.emit(ms / 1000.0)
        if self._mode == "audio":
            self._process_duration_ui(ms, self._audio_player)       # обновить слайдер и время

    def _process_duration_ui(self, ms: int, player):
        """Обновить слайдер и метку времени под текущий плеер."""
        self._slider.setRange(0, ms)
        self._time_label.setText(
            f"{self._format_time(player.position())} / {self._format_time(ms)}"
        )

    def _on_meta_data_changed(self):
        """Прочитать разрешение из метаданных и эмитить сигнал."""
        meta = self._player.metaData()
        if not meta:
            return

        from PySide6.QtMultimedia import QMediaMetaData
        resolution = meta.value(QMediaMetaData.Key.Resolution)

        if resolution is not None and not resolution.isEmpty():
            self._last_source_resolution = (resolution.width(), resolution.height())
            self.source_resolution_changed.emit(resolution.width(), resolution.height())
            self._preset_frame.set_crop_rect(self._current_crop_rect, self._last_source_resolution)
            self._video_widget.set_crop_rect(self._current_crop_rect, self._last_source_resolution)

        # FPS для покадровой перемотки
        fps = meta.value(QMediaMetaData.Key.VideoFrameRate)
        if fps is not None and float(fps) > 0:
            self._video_fps = float(fps)
            logger.debug(f"FPS из метаданных: {self._video_fps}")

    def _on_state_changed(self, state):
        self._update_play_button()

    def _on_audio_state_changed(self, state):
        self._update_play_button()

    def _update_play_button(self):
        active = self._active_player()
        if active.playbackState() == QMediaPlayer.PlayingState:
            self._btn_play.setText("⏸")
        else:
            self._btn_play.setText("▶")

    def _on_slider_moved(self, value: int):
        active = self._active_player()
        active.setPosition(value)
        if self._mode == "video" and self._has_audio_source():
            self._sync_audio_to_video()
        self._time_label.setText(
            f"{self._format_time(value)} / {self._format_time(active.duration())}"
        )
    
    def _on_slider_pressed(self):
        pass

    def _on_slider_released(self):
        value = self._slider.value()
        self._active_player().setPosition(value)
        if self._mode == "video" and self._has_audio_source():
            self._sync_audio_to_video()
        self._apply_audio_volume()

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
        if self._linked_mode:
            # В связке клик меняет скорость обоих
            self._video_speed_index = self._speed_index
            self._audio_speed_index = self._speed_index
            self._player.setPlaybackRate(speed)
            self._audio_player.setPlaybackRate(speed)
        else:
            # В развязке — только активный, у второго сохраняется своя
            if self._mode == "video":
                self._video_speed_index = self._speed_index
                self._player.setPlaybackRate(speed)
            else:
                self._audio_speed_index = self._speed_index
                self._audio_player.setPlaybackRate(speed)
        self._speed_label.setText(f"{speed}x")
        self._update_speed_buttons()
        self.speed_changed.emit(speed)

    def get_speed(self) -> float:
        """Текущая выбранная скорость."""
        return SPEED_PRESETS[self._speed_index]

    def _on_volume_changed(self, vol: float):
        """Пользователь покрутил громкость. Диспетчеризация по текущему режиму."""
        if self._mode == "video":
            self._video_volume = vol
            self._audio_output.setVolume(vol)
            self.video_volume_changed.emit(vol)
        else:  # audio
            self._audio_volume = vol
            self._apply_audio_volume()
            self.audio_volume_changed.emit(vol)

    def set_video_volume(self, vol: float):
        """Установить громкость видео извне (без эмита)."""
        self._video_volume = max(0.0, min(1.0, vol))
        self._audio_output.setVolume(self._video_volume)
        if self._mode == "video":
            self._volume_control.set_volume(self._video_volume)

    def set_audio_volume(self, vol: float):
        """Установить громкость аудио извне (без эмита)."""
        self._audio_volume = max(0.0, min(1.0, vol))
        self._apply_audio_volume()
        if self._mode == "audio":
            self._volume_control.set_volume(self._audio_volume)

    def _apply_audio_volume(self):
        """Применить громкость аудио-плеера: с учётом режима, связки и позиции видео."""
        if not self._has_audio_source():
            return

        # В развязке аудио звучит только когда активен audio-режим
        if not self._linked_mode:
            if self._mode == "audio":
                self._audio_player_out.setVolume(self._audio_volume)
            else:
                self._audio_player_out.setVolume(0.0)
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

    def _update_speed_buttons(self):
        self._btn_speed_prev.setEnabled(self._speed_index > 0)
        self._btn_speed_next.setEnabled(self._speed_index < len(SPEED_PRESETS) - 1)

    def set_marker_mode(self, active: bool):
        """Режим карандаша: блокирует transport-кнопки плеера."""
        if self._marker_mode_active == active:
            return
        self._marker_mode_active = active
        if active:
            self._player.pause()
            self._audio_player.pause()
        has_media = self._has_video_source() or self._has_audio_source()
        self._set_controls_enabled(has_media)
        self._update_speed_buttons()

    def set_preset_blink_phase(self, phase: float):
        """Прокинуть фазу мигания в рамку пресета."""
        self._preset_frame.set_blink_phase(phase)

    def set_shift_buttons_blink_phase(self, phase: float):
        """Фаза мигания стрелок. Мигает только активная (не на краю) при карандаше."""
        opacity = 0.35 + 0.65 * max(0.0, min(1.0, phase))
        blink_left = self._marker_mode_active and self._btn_shift_left.isEnabled()
        blink_right = self._marker_mode_active and self._btn_shift_right.isEnabled()
        self._shift_left_effect.setOpacity(opacity if blink_left else 1.0)
        self._shift_right_effect.setOpacity(opacity if blink_right else 1.0)

    def set_shift_buttons_visible(self, visible: bool):
        """Показать/скрыть стрелки сдвига рамки."""
        self._btn_shift_left.setVisible(visible)
        self._btn_shift_right.setVisible(visible)
        if visible:
            self._btn_shift_left.raise_()
            self._btn_shift_right.raise_()
            self._relayout_shift_buttons()

    def set_shift_buttons_enabled(self, can_left: bool, can_right: bool):
        """Включить/выключить стрелки в зависимости от краёв рамки."""
        self._btn_shift_left.setEnabled(can_left)
        self._btn_shift_right.setEnabled(can_right)

    def _relayout_shift_buttons(self):
        """Расположить стрелки по краям видео-области."""
        if not hasattr(self, "_btn_shift_left") or not self._btn_shift_left.isVisible():
            return
        w = self._video_area.width()
        h = self._video_area.height()
        self._btn_shift_left.move(20, (h - 36) // 2)
        self._btn_shift_right.move(w - 56, (h - 36) // 2)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout_video()
        self._relayout_shift_buttons()

    def pause_all(self):
        """Приостановить оба плеера. Используется при скрытии редактора."""
        try:
            self._player.pause()
            self._audio_player.pause()
        except RuntimeError:
            pass

    def hide_floating(self):
        """Скрыть top-level окна плеера (volume popup)."""
        try:
            self._volume_control._popup.hide()
        except (RuntimeError, AttributeError):
            pass

    def _sync_speed_ui(self):
        """Синхронизировать UI скорости с активным плеером. В связке — между обоими."""
        if self._linked_mode:
            self._speed_index = (
                self._video_speed_index if self._mode == "video"
                else self._audio_speed_index
            )
            self._video_speed_index = self._speed_index
            self._audio_speed_index = self._speed_index
        else:
            self._speed_index = (
                self._video_speed_index if self._mode == "video"
                else self._audio_speed_index
            )
        speed = SPEED_PRESETS[self._speed_index]
        # Guard: setPlaybackRate с тем же значением на macOS может зависнуть
        if abs(self._player.playbackRate() - speed) > 0.01:
            self._player.setPlaybackRate(speed)
        if abs(self._audio_player.playbackRate() - speed) > 0.01:
            self._audio_player.setPlaybackRate(speed)
        self._speed_label.setText(f"{speed}x")
        self._update_speed_buttons()
        self.speed_changed.emit(speed)

    def _on_go_to_start(self):
        """Перескок в начало trim. Играет — продолжит, на паузе — останется на паузе."""
        if not self._has_video_source() and not self._has_audio_source():
            return
        active = self._active_player()
        trim_start, _ = self._trim_for(active)
        active.setPosition(int(trim_start * 1000))
        if self._mode == "video" and self._has_audio_source():
            self._sync_audio_to_video()

    def _on_rewind(self):
        """Перемотать на 1 кадр назад (в активном плеере)."""
        if not self._has_video_source() and not self._has_audio_source():
            return
        active = self._active_player()
        frame_ms = int(1000.0 / self._video_fps) if self._video_fps > 0 else 33
        pos = max(active.position() - frame_ms, 0)
        active.setPosition(pos)
        if self._mode == "video" and self._has_audio_source():
            self._sync_audio_to_video()

    def _on_forward(self):
        """Перемотать на 1 кадр вперёд (в активном плеере)."""
        if not self._has_video_source() and not self._has_audio_source():
            return
        active = self._active_player()
        frame_ms = int(1000.0 / self._video_fps) if self._video_fps > 0 else 33
        pos = active.position() + frame_ms
        duration = active.duration()
        if duration > 0 and pos > duration:
            pos = duration
        active.setPosition(pos)
        if self._mode == "video" and self._has_audio_source():
            self._sync_audio_to_video()

    def _on_loop_toggled(self, checked: bool):
        self._loop_enabled = checked
        logger.debug(f"Повтор: {'вкл' if checked else 'выкл'}")

    @staticmethod
    def _format_time(ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02}:{secs:02}"
