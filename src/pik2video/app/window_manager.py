# src/pik2video/app/window_manager.py
"""
Менеджер вспомогательных окон.

Отвечает только за жизненный цикл окон:
- overlay (выбор области)
- preset_window (пресеты)
- app_settings_window (настройки приложения)

Не знает о состояниях AppState — этим занимается StateCoordinator.
"""

import logging
from typing import Optional

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QApplication

from src.pik2video.gui.capture.overlays import CoordinateOverlay, RecordingFrame
from src.pik2video.gui.common.cursor_manager import CursorManager
from src.pik2video.gui.capture.preset_window import PresetWindow

logger = logging.getLogger(__name__)


class WindowManager(QObject):
    def __init__(self, qt_app: QApplication, main_window, controller, parent=None):
        super().__init__(parent)
        self.qt_app = qt_app
        self.main_window = main_window
        self.controller = controller

        self.overlay: Optional[CoordinateOverlay] = None
        self.preset_window: Optional[PresetWindow] = None
        self.recording_frame: Optional[RecordingFrame] = None

        self.cursor_manager = CursorManager(self)
        self.cursor_manager.block(self.main_window)   # над окном записи — стрелка, не override
        #self.app_settings_window = None

    # ---------------- Overlay ----------------

    def show_overlay(self) -> CoordinateOverlay:
        """Создать (если нужно) и показать overlay."""
        if self.overlay is None:
            self.overlay = CoordinateOverlay()
            screen = self.qt_app.primaryScreen().geometry()
            self.overlay.setGeometry(screen)
            self.overlay.show()
            self.cursor_manager.register(self.overlay)
            logger.debug("Overlay создан и показан")
        return self.overlay

    def close_overlay(self):
        if self.overlay:
            self.cursor_manager.unregister(self.overlay)
            self.overlay.close()
            self.overlay = None
            logger.debug("Overlay закрыт")

    # ---------------- Preset window ----------------

    def show_preset_window(self) -> PresetWindow:
        if self.preset_window is None:
            self.preset_window = PresetWindow(self.controller)
            self.preset_window.show()
            self.cursor_manager.block(self.preset_window)   # над пресетами — стрелка
            logger.debug("Окно пресетов создано и показано")
        return self.preset_window

    def close_preset_window(self):
        if self.preset_window:
            self.cursor_manager.unblock(self.preset_window)
            self.preset_window.close()
            self.preset_window = None
            logger.debug("Окно пресетов закрыто")

    # ---------------- Recording frame ----------------

    def _get_or_create_recording_frame(self) -> RecordingFrame:
        if self.recording_frame is None:
            self.recording_frame = RecordingFrame()
            logger.debug("RecordingFrame создан")
        return self.recording_frame

    def preload_recording_frame(self):
        """Прогреть окно рамки — создать NSWindow заранее.

        show()/hide() в первый раз создаёт native window (~50-100 мс).
        Делаем это при старте приложения, чтобы в момент записи show() был мгновенным.
        """
        frame = self._get_or_create_recording_frame()
        frame.setGeometry(0, 0, 100, 100)
        frame.show()
        frame.hide()
        logger.debug("RecordingFrame прогрет")

    def show_recording_frame(self, region: dict):
        """Показать серебристую рамку вокруг области. region = {left, top, width, height}."""
        if not region:
            logger.debug("RecordingFrame: region пуст, не показываем")
            return
        frame = self._get_or_create_recording_frame()
        frame.set_region(region)
        frame.show()
        logger.debug(f"RecordingFrame показан: {region}")

    def hide_recording_frame(self):
        """Скрыть рамку (вызывается при REVIEW/IDLE)."""
        if self.recording_frame and self.recording_frame.isVisible():
            self.recording_frame.hide()
            logger.debug("RecordingFrame скрыт")

    # ---------------- Minimize / restore ----------------

    def hide_aux_windows(self):
        """Спрятать overlay и preset_window (при сворачивании главного окна)."""
        if self.overlay and self.overlay.isVisible():
            self.overlay.hide()
        if self.preset_window and self.preset_window.isVisible():
            self.preset_window.hide()

    def show_aux_windows(self):
        """Показать overlay и preset_window (при восстановлении главного окна)."""
        if self.overlay and not self.overlay.isVisible():
            self.overlay.show()
        if self.preset_window and not self.preset_window.isVisible():
            self.preset_window.show()
