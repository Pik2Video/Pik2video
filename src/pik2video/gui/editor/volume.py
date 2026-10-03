# src/pik2video/gui/editor/volume.py
"""
Контроль громкости.

Отвечает только за:
- иконку-кнопку динамика
- всплывающий вертикальный слайдер громкости
- mute/unmute по клику

Не знает:
- про плеер
- про EditorState
"""

import logging

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget

logger = logging.getLogger(__name__)


POPUP_WIDTH = 32
POPUP_HEIGHT = 120
POPUP_GAP = 6
HIDE_DELAY_MS = 200


class VolumePopup(QWidget):
    """Всплывающий вертикальный слайдер громкости."""

    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFixedSize(POPUP_WIDTH, POPUP_HEIGHT)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2a2a;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        self.slider = QSlider(Qt.Vertical)
        self.slider.setRange(0, 100)
        self.slider.setValue(100)
        self.slider.setStyleSheet("""
            QSlider::groove:vertical {
                background: #444;
                width: 4px;
                border-radius: 2px;
            }
            QSlider::handle:vertical {
                background: #ccc;
                height: 12px;
                margin: 0 -6px;
                border-radius: 6px;
            }
            QSlider::add-page:vertical {
                background: #3a7a3a;
                border-radius: 2px;
            }
            QSlider::sub-page:vertical {
                background: #444;
            }
        """)

        layout.addWidget(self.slider, alignment=Qt.AlignHCenter)


class VolumeControl(QWidget):
    """
    Кнопка-иконка громкости + всплывающий слайдер.
    При наведении — появляется слайдер.
    Клик по кнопке — mute/unmute.
    """

    def __init__(self, audio_output, parent=None):
        super().__init__(parent)
        self._audio_output = audio_output
        self._prev_volume = 1.0
        self._is_muted = False

        self._btn = QPushButton("🔊")
        self._btn.setFixedSize(24, 24)
        self._btn.setStyleSheet("""
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
        self._btn.clicked.connect(self._on_button_click)
        self._btn.installEventFilter(self)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._btn)

        self._popup = VolumePopup()
        self._popup.slider.valueChanged.connect(self._on_slider_value)
        self._popup.installEventFilter(self)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(HIDE_DELAY_MS)
        self._hide_timer.timeout.connect(self._maybe_hide_popup)

        self._audio_output.setVolume(1.0)
        self._update_icon()

    # ── События ──

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Enter:
            self._cancel_hide()
            if not self._popup.isVisible():
                self._show_popup()
        elif event.type() == QEvent.Leave:
            self._schedule_hide()
        return super().eventFilter(obj, event)

    # ── Popup ──

    def _show_popup(self):
        btn_global = self._btn.mapToGlobal(QPoint(0, 0))
        x = btn_global.x() + self._btn.width() // 2 - POPUP_WIDTH // 2
        y = btn_global.y() - POPUP_HEIGHT - POPUP_GAP
        self._popup.move(x, y)

        self._popup.slider.blockSignals(True)
        self._popup.slider.setValue(int(self._audio_output.volume() * 100))
        self._popup.slider.blockSignals(False)

        self._popup.show()

    def _schedule_hide(self):
        self._hide_timer.start()

    def _cancel_hide(self):
        self._hide_timer.stop()

    def _maybe_hide_popup(self):
        pos = QCursor.pos()

        btn_global = self._btn.mapToGlobal(self._btn.rect().topLeft())
        btn_rect_global = self._btn.rect().translated(btn_global)

        popup_rect_global = self._popup.rect().translated(self._popup.pos())

        if not (btn_rect_global.contains(pos) or popup_rect_global.contains(pos)):
            self._popup.hide()

    # ── Логика ──

    def _on_button_click(self):
        self._is_muted = not self._is_muted

        if self._is_muted:
            self._prev_volume = self._audio_output.volume()
            self._audio_output.setVolume(0.0)
        else:
            vol = self._prev_volume if self._prev_volume > 0 else 1.0
            self._audio_output.setVolume(vol)

        self._popup.slider.blockSignals(True)
        self._popup.slider.setValue(int(self._audio_output.volume() * 100))
        self._popup.slider.blockSignals(False)

        self._update_icon()

    def _on_slider_value(self, value: int):
        vol = value / 100.0
        self._audio_output.setVolume(vol)

        if vol > 0 and self._is_muted:
            self._is_muted = False
        elif vol == 0:
            self._is_muted = True

        self._update_icon()

    def _update_icon(self):
        vol = self._audio_output.volume()
        if vol == 0 or self._is_muted:
            self._btn.setText("🔇")
        elif vol < 0.4:
            self._btn.setText("🔈")
        elif vol < 0.7:
            self._btn.setText("🔉")
        else:
            self._btn.setText("🔊")
