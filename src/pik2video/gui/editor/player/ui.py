# src/pik2video/gui/editor/player/ui.py
from PySide6.QtCore import Qt
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

from src.pik2video.gui.common.styles import PLAYER_QSS
from .surface import PresetFrame, VideoSurface
from .volume import VolumeControl


class PlayerUI(QWidget):
    """Визуальный интерфейс плеера (без логики)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PLAYER_QSS)

        self._stack = QStackedWidget(self)
        self._stack.setStyleSheet("background: transparent;")

        self._placeholder_page = self._build_placeholder()
        self._stack.addWidget(self._placeholder_page)

        self._player_page = self._build_player_page()
        self._stack.addWidget(self._player_page)

        self._audio_page = self._build_audio_page()
        self._stack.addWidget(self._audio_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._stack, stretch=1)

        self._controls = self._build_controls()
        layout.addWidget(self._controls, stretch=0)

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
        page.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._video_area = QWidget()
        self._video_area.setStyleSheet("background: transparent;")
        self._video_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._video_area, stretch=1)

        self._video_widget = VideoSurface()
        self._preset_frame = PresetFrame()
        self._preset_frame.hide()

        stack = QStackedLayout(self._video_area)
        stack.setStackingMode(QStackedLayout.StackAll)
        stack.setContentsMargins(0, 0, 0, 0)
        stack.addWidget(self._video_widget)
        stack.addWidget(self._preset_frame)

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
        self._btn_shift_left.hide()

        self._btn_shift_right = QPushButton("→", self._video_area)
        self._btn_shift_right.setFixedSize(36, 36)
        self._btn_shift_right.setStyleSheet(self._btn_shift_left.styleSheet())
        self._shift_right_effect = QGraphicsOpacityEffect(self._btn_shift_right)
        self._shift_right_effect.setOpacity(1.0)
        self._btn_shift_right.setGraphicsEffect(self._shift_right_effect)
        self._btn_shift_right.hide()

        return page

    def _build_audio_page(self) -> QWidget:
        page = QWidget()
        page.setStyleSheet("background-color: #000;")
        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        self._audio_icon = QLabel("🎵")
        self._audio_icon.setAlignment(Qt.AlignCenter)
        self._audio_icon.setStyleSheet("font-size: 64px; background: transparent; border: none;")

        self._audio_name = QLabel("")
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

        self._btn_play = QPushButton("▶")
        self._btn_play.setFixedSize(28, 24)

        self._btn_go_start = QPushButton("↺")
        self._btn_go_start.setFixedSize(28, 24)
        layout.addWidget(self._btn_go_start)
        layout.addSpacing(6)

        self._btn_rewind = QPushButton("⏪")
        self._btn_rewind.setFixedSize(28, 24)
        layout.addWidget(self._btn_rewind)
        layout.addSpacing(2)
        layout.addWidget(self._btn_play)
        layout.addSpacing(2)

        self._btn_forward = QPushButton("⏩")
        self._btn_forward.setFixedSize(28, 24)
        layout.addWidget(self._btn_forward)
        layout.addSpacing(6)

        self._btn_loop = QPushButton("🔁")
        self._btn_loop.setObjectName("btnLoop")
        self._btn_loop.setFixedSize(28, 24)
        self._btn_loop.setCheckable(True)
        layout.addWidget(self._btn_loop)
        layout.addSpacing(8)

        self._time_label = QLabel("00:00 / 00:00")
        self._time_label.setObjectName("timeLabel")
        self._time_label.setFixedWidth(100)
        self._time_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self._time_label)
        layout.addSpacing(8)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 0)
        layout.addWidget(self._slider, stretch=1)
        layout.addSpacing(8)

        speed_block = QWidget()
        speed_block.setStyleSheet("background: transparent; border: none;")
        speed_layout = QHBoxLayout(speed_block)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(2)

        self._btn_speed_prev = QPushButton("<")
        self._btn_speed_prev.setObjectName("btnSpeed")
        self._btn_speed_prev.setFixedSize(20, 24)

        self._speed_label = QLabel("1x")
        self._speed_label.setObjectName("speedLabel")
        self._speed_label.setFixedWidth(36)
        self._speed_label.setAlignment(Qt.AlignCenter)

        self._btn_speed_next = QPushButton(">")
        self._btn_speed_next.setObjectName("btnSpeed")
        self._btn_speed_next.setFixedSize(20, 24)

        speed_layout.addWidget(self._btn_speed_prev)
        speed_layout.addWidget(self._speed_label)
        speed_layout.addWidget(self._btn_speed_next)

        layout.addWidget(speed_block)
        layout.addSpacing(8)

        self._volume_control = VolumeControl(initial=1.0)
        layout.addWidget(self._volume_control)

        return bar
