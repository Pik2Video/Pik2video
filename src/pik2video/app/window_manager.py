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

from src.pik2video.gui.capture.overlays import CoordinateOverlay
from src.pik2video.gui.capture.preset_window import PresetWindow
from src.pik2video.gui.common.utils import keep_window_inside_screen, bring_window_to_front

logger = logging.getLogger(__name__)


class WindowManager(QObject):
    def __init__(self, qt_app: QApplication, main_window, controller, parent=None):
        super().__init__(parent)
        self.qt_app = qt_app
        self.main_window = main_window
        self.controller = controller

        self.overlay: Optional[CoordinateOverlay] = None
        self.preset_window: Optional[PresetWindow] = None
        #self.app_settings_window = None

    # ---------------- Overlay ----------------

    def show_overlay(self) -> CoordinateOverlay:
        """Создать (если нужно) и показать overlay."""
        if self.overlay is None:
            self.overlay = CoordinateOverlay()
            screen = self.qt_app.primaryScreen().geometry()
            self.overlay.setGeometry(screen)
            self.overlay.show()
            logger.debug("Overlay создан и показан")
        return self.overlay

    def close_overlay(self):
        if self.overlay:
            self.overlay.close()
            self.overlay = None
            logger.debug("Overlay закрыт")

    # ---------------- Preset window ----------------

    def show_preset_window(self) -> PresetWindow:
        if self.preset_window is None:
            self.preset_window = PresetWindow(self.controller)
            self.preset_window.show()
            logger.debug("Окно пресетов создано и показано")
        return self.preset_window

    def close_preset_window(self):
        if self.preset_window:
            self.preset_window.close()
            self.preset_window = None
            logger.debug("Окно пресетов закрыто")

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