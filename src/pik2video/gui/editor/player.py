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

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QSlider, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QPixmap

from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget

from .volume import VolumeControl

logger = logging.getLogger(__name__)

# Пресеты скорости воспроизведения
SPEED_PRESETS = [0.5, 0.75, 1.0, 1.5, 2.0]

# Шаг перемотки в секундах
SEEK_STEP_SEC = 5

class PlayerWidget(QWidget):
    """Плеер с placeholder-страницей и страницей видео."""

    position_changed = Signal(float)   # секунды
    duration_changed = Signal(float)   # секунды

    def __init__(self, parent=None):
        super().__init__(parent)

        # ── Медиа-объекты (до сборки UI) ──
        self._player = QMediaPlayer(self)
        self._audio_output = QAudioOutput(self)
        self._player.setAudioOutput(self._audio_output)

        self._trim_start = 0.0
        self._trim_end = 0.0
        self._loop_enabled = False
        self._last_frame = None
        self._keep_frames = True   # кэшировать кадры

        self._stack = QStackedWidget(self)

        # ── Страница 0: placeholder ──
        self._placeholder_page = self._build_placeholder()
        self._stack.addWidget(self._placeholder_page)

        # ── Страница 1: плеер ──
        self._player_page = self._build_player_page()
        self._stack.addWidget(self._player_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

        self._player.setVideoOutput(self._video_widget)

        # Захват кадров через sink
        try:
            self._video_sink = self._video_widget.videoSink()
            self._video_sink.videoFrameChanged.connect(self._on_video_frame)
        except Exception as e:
            logger.warning(f"Не удалось подключить QVideoSink: {e}")
            self._video_sink = None

        self._player.positionChanged.connect(self._on_position_changed)
        self._player.durationChanged.connect(self._on_duration_changed)
        self._player.playbackStateChanged.connect(self._on_state_changed)

        self._show_placeholder()

    # ── Построение UI ──

    def _build_placeholder(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)

        label = QLabel("Загрузите видеофайл")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: #666; font-size: 16px;")
        layout.addWidget(label)

        return page

    def _build_player_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Видео-виджет
        self._video_widget = QVideoWidget()
        self._video_widget.setStyleSheet("background-color: #000;")
        self._video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._video_widget, stretch=1)

        # Панель управления
        controls = self._build_controls()
        layout.addWidget(controls, stretch=0)

        return page

    def _build_controls(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(32)
        bar.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(8)

        # Play/Pause
        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(28, 24)
        self._btn_play.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)

        self._btn_play.clicked.connect(self._toggle_play)
        layout.addWidget(self._btn_play)

        # Перемотка назад
        self._btn_rewind = QPushButton("⏪")
        self._btn_rewind.setFixedSize(28, 24)
        self._btn_rewind.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)
        self._btn_rewind.clicked.connect(self._on_rewind)
        layout.addWidget(self._btn_rewind)

        # Перемотка вперёд
        self._btn_forward = QPushButton("⏩")
        self._btn_forward.setFixedSize(28, 24)
        self._btn_forward.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
        """)
        self._btn_forward.clicked.connect(self._on_forward)
        layout.addWidget(self._btn_forward)

        # Повтор
        self._btn_loop = QPushButton("🔁")
        self._btn_loop.setFixedSize(28, 24)
        self._btn_loop.setCheckable(True)
        self._btn_loop.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 12px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:checked {
                background-color: #5a5a5a;
                border-color: #888;
            }
        """)
        self._btn_loop.toggled.connect(self._on_loop_toggled)
        layout.addWidget(self._btn_loop)

        # Время: текущее / общее
        self._time_label = QLabel("00:00 / 00:00")

        self._time_label.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )
        self._time_label.setFixedWidth(100)
        self._time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._time_label)

        # Слайдер позиции
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        self._slider.sliderMoved.connect(self._on_slider_moved)
        self._slider.sliderPressed.connect(self._on_slider_pressed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444;
                height: 4px;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #888;
                width: 12px;
                margin: -4px 0;
                border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #3a7a3a;
                border-radius: 2px;
            }
        """)
        layout.addWidget(self._slider, stretch=1)

        # ── Блок скорости воспроизведения ──
        speed_block = QWidget()
        speed_block.setStyleSheet("background: transparent; border: none;")
        speed_layout = QHBoxLayout(speed_block)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)

        btn_style = """
            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
                color: #e0e0e0;
                font-size: 11px;
            }
            QPushButton:hover { background-color: #4a4a4a; }
            QPushButton:pressed { background-color: #2a2a2a; }
            QPushButton:disabled { color: #555; background-color: #2a2a2a; }
        """

        self._btn_speed_prev = QPushButton("<")
        self._btn_speed_prev.setFixedSize(20, 24)
        self._btn_speed_prev.setStyleSheet(btn_style)
        self._btn_speed_prev.clicked.connect(self._on_speed_prev)

        self._speed_label = QLabel("1x")
        self._speed_label.setFixedWidth(36)
        self._speed_label.setAlignment(Qt.AlignCenter)
        self._speed_label.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )

        self._btn_speed_next = QPushButton(">")
        self._btn_speed_next.setFixedSize(20, 24)
        self._btn_speed_next.setStyleSheet(btn_style)
        self._btn_speed_next.clicked.connect(self._on_speed_next)

        speed_layout.addWidget(self._btn_speed_prev)
        speed_layout.addWidget(self._speed_label)
        speed_layout.addWidget(self._btn_speed_next)

        layout.addWidget(speed_block)

        # ── Громкость ──
        self._volume_control = VolumeControl(self._audio_output)
        layout.addWidget(self._volume_control)

        # Текущий индекс в SPEED_PRESETS
        self._speed_index = SPEED_PRESETS.index(1.0)
        self._update_speed_buttons()

        return bar

    # ── Публичный API ──

    def load_video(self, path: str):
        """Загрузить видео и показать первый кадр."""
        logger.info(f"Плеер загружает: {path}")
        self._player.setSource(QUrl.fromLocalFile(path))
        self._show_player()

        # Показываем первый кадр: играем и сразу ставим на паузу
        self._player.play()
        self._player.pause()

        # Позицию в начало
        self._player.setPosition(0)

    def unload_video(self):
        """Остановить и вернуть placeholder."""
        self._player.stop()
        self._player.setSource(QUrl())
        self._trim_start = 0.0
        self._trim_end = 0.0
        self._show_placeholder()

    def set_position(self, seconds: float):
        """Внешняя установка позиции (из таймлайна)."""
        if self._player.duration() > 0:
            self._player.setPosition(int(seconds * 1000))

    def set_trim_range(self, start: float, end: float):
        """Обновить диапазон трима. Плеер не выходит за его пределы."""
        self._trim_start = max(0.0, start)
        self._trim_end = max(start, end)
        logger.debug(f"Плеер: диапазон {self._trim_start:.2f} .. {self._trim_end:.2f}")

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

    def _on_video_frame(self, frame):
        """Сохранить последний кадр для превью (только когда нужно)."""
        if not self._keep_frames:
            return
        if frame is None or not frame.isValid():
            return
        image = frame.toImage()
        if image.isNull():
            return
        self._last_frame = QPixmap.fromImage(image)

    # ── Внутренние слоты ──

    def _show_placeholder(self):
        self._stack.setCurrentIndex(0)

    def _show_player(self):
        self._stack.setCurrentIndex(1)

    def _toggle_play(self):
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            return

        # Если позиция вне диапазона — прыгаем на начало
        pos = self._player.position() / 1000.0
        if self._trim_end > 0 and (pos < self._trim_start or pos >= self._trim_end):
            self._player.setPosition(int(self._trim_start * 1000))

        self._player.play()

    def _on_position_changed(self, ms: int):
        if not self._slider.isSliderDown():
            self._slider.setValue(ms)
        self._time_label.setText(
            f"{self._format_time(ms)} / {self._format_time(self._player.duration())}"
        )

        seconds = ms / 1000.0

        # Достигли конца диапазона трима
        if (
            self._trim_end > 0
            and seconds >= self._trim_end
            and self._player.playbackState() == QMediaPlayer.PlayingState
        ):
            if self._loop_enabled:
                self._player.setPosition(int(self._trim_start * 1000))
                return
            else:
                self._player.pause()
                self._player.setPosition(int(self._trim_end * 1000))
                self.position_changed.emit(self._trim_end)
                return

        self.position_changed.emit(seconds)

    def _on_duration_changed(self, ms: int):
        self._slider.setRange(0, ms)
        self._time_label.setText(
            f"{self._format_time(self._player.position())} / {self._format_time(ms)}"
        )
        self.duration_changed.emit(ms / 1000.0)

    def _on_state_changed(self, state):
        if state == QMediaPlayer.PlayingState:
            self._btn_play.setText("⏸")
        else:
            self._btn_play.setText("▶")

    def _on_slider_moved(self, value: int):
        self._player.setPosition(value)
        self._time_label.setText(
            f"{self._format_time(value)} / {self._format_time(self._player.duration())}"
        )
    
    def _on_slider_pressed(self):
        pass

    def _on_slider_released(self):
        self._player.setPosition(self._slider.value())

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
        self._player.setPlaybackRate(speed)
        self._speed_label.setText(f"{speed}x")
        self._update_speed_buttons()
        logger.debug(f"Скорость: {speed}x")

    def _update_speed_buttons(self):
        self._btn_speed_prev.setEnabled(self._speed_index > 0)
        self._btn_speed_next.setEnabled(self._speed_index < len(SPEED_PRESETS) - 1)

    def _on_rewind(self):
        """Перемотать на 5 секунд назад."""
        pos = self._player.position() - SEEK_STEP_SEC * 1000
        if pos < 0:
            pos = 0
        self._player.setPosition(pos)

    def _on_forward(self):
        """Перемотать на 5 секунд вперёд."""
        pos = self._player.position() + SEEK_STEP_SEC * 1000
        duration = self._player.duration()
        if duration > 0 and pos > duration:
            pos = duration
        self._player.setPosition(pos)

    def _on_loop_toggled(self, checked: bool):
        self._loop_enabled = checked
        logger.debug(f"Повтор: {'вкл' if checked else 'выкл'}")

    @staticmethod
    def _format_time(ms: int) -> str:
        seconds = ms // 1000
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02}:{secs:02}"