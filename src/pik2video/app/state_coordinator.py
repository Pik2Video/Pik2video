# src/pik2video/app/state_coordinator.py
"""
Координатор между состояниями приложения и GUI.

Реагирует на:
- смену состояния (AppState)
- сворачивание/разворачивание главного окна
- сигналы overlay (координаты, drag)
- сигналы preset_window (выбор пресета)
- тики мигания (blink phase)

Использует WindowManager для управления окнами
и BlinkManager для единого мигания.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Slot

from src.pik2video.application.session_types import SessionType
from src.pik2video.application.state_machine import AppState
from src.pik2video.gui.capture.preset_window import PresetWindow
from src.pik2video.gui.common.utils import bring_window_to_front
from src.pik2video.utils import format_size, format_time

from .window_manager import WindowManager
from .blink_manager import BlinkManager

logger = logging.getLogger(__name__)


class StateCoordinator(QObject):
    def __init__(
        self,
        controller,
        main_window,
        window_manager: WindowManager,
        blink_manager: BlinkManager,
        parent=None,
    ):
        super().__init__(parent)
        self.controller = controller
        self.main_window = main_window
        self.wm = window_manager
        self.blink = blink_manager

        # Подписка на фазу мигания
        self.blink.phase_changed.connect(self.on_blink_tick)

    # ==================================================
    #                    STATE
    # ==================================================

    @Slot(AppState)
    def on_state_changed(self, state: AppState):
        logger.debug(f"Состояние: {state}")

        self._sync_always_on_top(state)

        # Закрытие вспомогательных окон для IDLE / WAITING / REVIEW
        if state in (AppState.IDLE, AppState.WAITING, AppState.REVIEW):
            self.wm.close_overlay()
            self.blink.stop()
            self.wm.close_preset_window()

        # ── IDLE ──
        if state == AppState.IDLE:
            # Всегда пересоздаём IDLE-экран, но показываем окно только если редактор скрыт
            self.main_window.show_idle_screen()
            if getattr(self.main_window, "_editor_visible", False):
                logger.debug("IDLE: редактор открыт → IDLE обновлён, но остаётся скрытым")
                return
            self.main_window.activateWindow()
            bring_window_to_front(self.main_window)
            return

        # ── PREPARING ──
        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
            self._enter_preparing(state)
            return

        # ── WAITING ──
        if state == AppState.WAITING:
            logger.debug("Переход в WAITING — окна закрыты")
            return

        # ── RECORDING ──
        if state == AppState.RECORDING:
            if self.main_window.current_session:
                self.main_window.current_session.set_recording_mode()
                logger.debug("Сессия переключена в режим записи")
            return

        # ── REVIEW ──
        if state == AppState.REVIEW:
            self._enter_review(state)
            return

    def _sync_always_on_top(self, state: AppState):
        always_on_top = self.controller.get_always_on_top()
        is_preparing = state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)
        should_be_on_top = always_on_top or is_preparing

        is_currently_on_top = bool(
            self.main_window.windowFlags() & Qt.WindowStaysOnTopHint
        )

        logger.debug(
            f"always_on_top={always_on_top}, is_preparing={is_preparing}, "
            f"should={should_be_on_top}, current={is_currently_on_top}, state={state}"
        )

        if should_be_on_top != is_currently_on_top:
            if should_be_on_top:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
                )
            else:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() & ~Qt.WindowStaysOnTopHint
                )
            self.main_window.show()

    def _enter_preparing(self, state: AppState):
        session_type = self.controller.get_session_type()

        if session_type == SessionType.VIDEO:
            logger.debug("Показываем видео сессию в MainWindow")
            self.main_window.show_video_session(self.controller)
        else:
            logger.debug("Показываем screen сессию в MainWindow")
            self.main_window.show_screen_session(self.controller)

        # Overlay
        if self.wm.overlay is None:
            overlay = self.wm.show_overlay()
            overlay.coords_selected.connect(self.on_overlay_coords)
            overlay.drag_started.connect(self.on_drag_started)
            overlay.drag_finished.connect(self.on_drag_finished)

            screen = self.wm.qt_app.primaryScreen().geometry()
            default_coords = PresetWindow.get_default_preset_coords(screen)
            overlay.set_region(default_coords)
            self._apply_default_preset(default_coords)

            # Запускаем мигание
            self.blink.reset(phase=0.0, direction=1)
            self.blink.start()

        # Preset window
        if self.wm.preset_window is None:
            pw = self.wm.show_preset_window()
            pw.preset_selected.connect(self.on_preset_selected)
            pw.set_active_preset("fullscreen")
            pw.set_blink_phase(self.blink.get_phase())

    def _enter_review(self, state: AppState):
        """После «Стоп»: сохраняем запись и открываем редактор."""
        logger.debug("REVIEW: сохраняем запись и открываем редактор")

        session_file = self.controller.get_current_session_file()
        if not session_file or not session_file.exists():
            logger.error("Файл записи не найден — откат в IDLE")
            self.controller.discard_session()
            return

        target = self._move_to_drafts(session_file)
        if not target:
            self.controller.discard_session()
            return

        # Сначала открываем редактор — он пометит IDLE как «скрытый»
        self.controller.open_editor_requested.emit(str(target))

        # Потом очищаем сессию и уходим в IDLE
        self.controller.session_manager.cleanup()
        self.controller.session_manager.clear_runtime()
        self.controller.state_manager.finalize_session()
    
    def _move_to_drafts(self, session_file):
        """Переместить файл из сессии в папку черновиков."""
        try:
            drafts_dir = self.controller.get_drafts_dir()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            extension = session_file.suffix or ".mp4"
            target = drafts_dir / f"recording_{timestamp}{extension}"

            counter = 1
            while target.exists():
                target = drafts_dir / f"recording_{timestamp}_{counter}{extension}"
                counter += 1

            shutil.move(str(session_file), str(target))
            logger.info(f"Запись перемещена в черновик: {target}")
            return target
        except Exception as e:
            logger.error(f"Ошибка перемещения в черновик: {e}")
            return None

    # ==================================================
    #             MINIMIZE / RESTORE
    # ==================================================

    def on_main_window_state_changed(self, old_state, new_state):
        is_minimized = bool(new_state & Qt.WindowMinimized)
        state = self.controller.state_manager.get_state()

        if is_minimized:
            self.wm.hide_aux_windows()
        else:
            if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
                self.wm.show_aux_windows()

    # ==================================================
    #                OVERLAY EVENTS
    # ==================================================

    def on_overlay_coords(self, coords: dict):
        logger.debug(f"Получены координаты: {coords}")
        try:
            self.controller.set_raw_coordinates(coords)
        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")
            return

        if self.wm.preset_window:
            self.wm.preset_window.set_active_preset(None)

        if self.main_window.current_session:
            x1, y1 = coords["x1"], coords["y1"]
            x2, y2 = coords["x2"], coords["y2"]
            text = f"{x1},{y1} → {x2},{y2}  ({x2-x1}×{y2-y1})"
            self.main_window.current_session.set_info_text(text)

    def on_drag_started(self):
        logger.debug("Ручное выделение: начало")
        self.blink.stop()

        if self.wm.preset_window:
            self.wm.preset_window.set_active_preset(None)

        if self.main_window.current_session:
            self.main_window.current_session.set_info_text("")

    def on_drag_finished(self):
        logger.debug("Ручное выделение: завершено")
        self.blink.reset(phase=0.0, direction=1)
        self.blink.start()

    # ==================================================
    #                PRESET EVENTS
    # ==================================================

    def on_preset_selected(self, coords: dict, preset_name: str, preset_id: str):
        logger.debug(f"Выбран пресет '{preset_name}' с координатами: {coords}")
        try:
            self.controller.set_raw_coordinates(coords)
            if self.wm.overlay:
                self.wm.overlay.set_region(coords)
                logger.debug("Область обновлена на overlay")
        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")
            return

        if self.main_window.current_session:
            self.main_window.current_session.set_info_text(preset_name)

    def _apply_default_preset(self, coords: dict):
        try:
            self.controller.set_raw_coordinates(coords)
            logger.debug("Пресет 'Весь экран' применён по умолчанию")
        except ValueError as e:
            logger.error(f"Ошибка координат пресета: {e}")
            return

        if self.main_window.current_session:
            preset_name = self.main_window.translator.tr("preset_fullscreen")
            self.main_window.current_session.set_info_text(preset_name)

    # ==================================================
    #                    BLINK
    # ==================================================

    def on_blink_tick(self, phase: float):
        if self.wm.overlay:
            self.wm.overlay.set_blink_phase(phase)
        if self.main_window.current_session:
            self.main_window.current_session.set_blink_phase(phase)
        if self.wm.preset_window:
            self.wm.preset_window.set_blink_phase(phase)