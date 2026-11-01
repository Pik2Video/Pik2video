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

from PySide6.QtCore import QObject, Qt, Slot

from src.pik2video.application.session_types import SessionType
from src.pik2video.application.state_machine import AppState
from src.pik2video.gui.capture.preset_window import PresetWindow

from .blink_manager import BlinkManager
from .window_manager import WindowManager

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

        # ── IDLE / REVIEW: закрыть оверлей, пресеты, скрыть рамку ──
        if state in (AppState.IDLE, AppState.REVIEW):
            self.wm.close_overlay()
            self.wm.hide_recording_frame()
            self.blink.stop()
            self.wm.close_preset_window()

        # ── COUNTDOWN / RECORDING: серебристая рамка (отдельное окно) ──
        if state in (AppState.COUNTDOWN, AppState.RECORDING):
            if self.controller.get_show_recording_frame():
                region = self.controller.session_manager.get_region()
                if region:
                    self.wm.show_recording_frame(region)
            self.wm.close_overlay()   # оверлей больше не нужен — рамка его заменила
            self.blink.stop()
            self.wm.close_preset_window()

        # ── IDLE ──
        if state == AppState.IDLE:
            # IDLE-окно больше не показывается: редактор его заменяет.
            logger.debug("IDLE: редактор активен, IDLE-окно не показываем")
            return

        # ── PREPARING ──
        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN, AppState.PREPARING_AUDIO):
            self._enter_preparing(state)                              # включаем и аудио-подготовку
            return

        # ── COUNTDOWN ──
        if state == AppState.COUNTDOWN:
            # окно записи должно быть поверх оверлея-рамки, иначе не нажать СТОП
            self.main_window.raise_()
            self.main_window.activateWindow()
            logger.debug("COUNTDOWN: оверлей в режиме записи, пресеты закрыты")
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

        preparing_states = (
            AppState.PREPARING_VIDEO,
            AppState.PREPARING_SCREEN,
            AppState.PREPARING_AUDIO,                                 # аудио-окно тоже всегда поверх
        )
        active_states = (
            AppState.COUNTDOWN,
            AppState.RECORDING,
        )

        # В PREPARING окно записи всегда поверх overlay —
        # иначе пользователь не дотянется до него.
        # В COUNTDOWN/RECORDING/REVIEW — только если включён флаг.
        is_preparing = state in preparing_states
        should_be_on_top = is_preparing or (always_on_top and state in active_states)

        is_currently_on_top = bool(
            self.main_window.windowFlags() & Qt.WindowStaysOnTopHint
        )

        logger.debug(
            f"always_on_top={always_on_top}, should={should_be_on_top}, "
            f"current={is_currently_on_top}, state={state}"
        )

        if should_be_on_top != is_currently_on_top:
            was_visible = self.main_window.isVisible()

            if should_be_on_top:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
                )
            else:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() & ~Qt.WindowStaysOnTopHint
                )

            # setWindowFlags скрывает окно — возвращаем видимость как было
            if was_visible:
                self.main_window.show()

    def _enter_preparing(self, state: AppState):
        session_type = self.controller.get_session_type()

        if session_type == SessionType.AUDIO:
            logger.debug("Показываем аудио сессию в MainWindow")
            self.main_window.show_audio_session(self.controller)
            return                                                    # для аудио overlay и preset_window не нужны

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
            overlay.region_moved.connect(self.on_region_moved)
            overlay.drag_started.connect(self.on_drag_started)
            overlay.drag_finished.connect(self.on_drag_finished)
            overlay.invalid_coords.connect(self.on_invalid_coords)

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

        # Overlay и preset_window — top-level, показываются последними,
        # поэтому явно поднимаем окно записи поверх них.
        self.main_window.raise_()

    def _enter_review(self, state: AppState):
        """После «Стоп»: финализация (merge/mux), перенос файла в черновики, передача редактору.

        Переход в IDLE произойдёт после подтверждения от редактора
        (см. Application._open_editor_with_file).
        """
        logger.debug("REVIEW: финализация записи")

        if not self.controller.finalize_recording():
            self._fail_review("Не удалось собрать файл записи")
            return

        logger.debug("REVIEW: перенос файла и передача редактору")

        session_file = self.controller.get_current_session_file()
        if not session_file or not session_file.exists():
            logger.error("Файл записи не найден — очищаем пустую сессию")
            self.controller.session_manager.cleanup()
            self.controller.session_manager.clear_runtime()
            self._fail_review("Файл записи не найден — запись потеряна")
            return

        target = self._move_to_drafts(session_file)
        if not target:
            self._fail_review("Не удалось переместить запись в черновики")
            return

        self.controller.session_manager.cleanup()
        self.controller.session_manager.clear_runtime()

        logger.info(f"Файл передан редактору: {target}")
        self.controller.open_editor_requested.emit(str(target))
        # Переход в IDLE произойдёт после подтверждения от редактора

    def _fail_review(self, message: str):
        """Показать ошибку REVIEW и вернуться в IDLE."""
        logger.error(f"REVIEW: {message}")

        from src.pik2video.gui.common.dialogs import error as show_error_dialog
        show_error_dialog(
            self.main_window,
            message,
            translator=self.controller.get_translator(),
        )

        self.controller.state_manager.finalize_session()


    def _move_to_drafts(self, session_file):
        """Переместить файл из сессии в папку черновиков.

        Если в настройках записи задано имя — используем его.
        Иначе генерируем recording_гггг.мм.дд_чч.мм.сс.
        """
        try:
            drafts_dir = self.controller.get_drafts_dir()


            extension = session_file.suffix or ".mp4"

            if self.controller.get_session_type() == SessionType.AUDIO:
                export_name = self.controller.get_audio_export_filename().strip()   # имя для аудио-записи
                prefix = "audio"                                                     # префикс для авто-имени аудио
            else:
                export_name = self.controller.get_export_filename().strip()         # имя для видео/скрина
                prefix = "recording"                                                 # префикс для авто-имени видео

            if export_name:
                base_name = export_name                                              # пользователь задал имя
            else:
                timestamp = datetime.now().strftime("%m.%d_%H.%M.%S")
                base_name = f"{prefix}_{timestamp}"                                  # автогенерация с нужным префиксом

            target = drafts_dir / f"{base_name}{extension}"
            counter = 1
            while target.exists():
                target = drafts_dir / f"{base_name}_{counter}{extension}"
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

        # В COUNTDOWN / RECORDING рамка — самостоятельное окно верхнего уровня:
        # не скрываем её при сворачивании окна записи, не трогаем при восстановлении.
        if state in (AppState.COUNTDOWN, AppState.RECORDING):
            return

        if is_minimized:
            self.wm.hide_aux_windows()
        else:
            if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
                self.wm.show_aux_windows()

    # ==================================================
    #             SETTINGS DIALOG PAUSE
    # ==================================================

    def pause_preparing_ui(self):
        """Пользователь открыл настройки: скрыть окно пресетов, остановить мигание."""
        state = self.controller.state_manager.get_state()
        if state not in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
            return

        self.blink.stop()
        if self.wm.preset_window and self.wm.preset_window.isVisible():
            self.wm.preset_window.hide()
        logger.debug("PREPARING UI приостановлен (открыты настройки)")

    def resume_preparing_ui(self):
        """Пользователь закрыл настройки: показать пресеты, возобновить мигание."""
        state = self.controller.state_manager.get_state()
        if state not in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
            return

        if self.wm.preset_window and not self.wm.preset_window.isVisible():
            self.wm.preset_window.show()
        self.blink.start()
        logger.debug("PREPARING UI возобновлён (настройки закрыты)")

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
            w = x2 - x1
            h = y2 - y1
            text = f"ширина: {w}px   высота: {h}px"
            self.main_window.current_session.set_info_text(text)

    def on_invalid_coords(self):
        """Пустой клик в оверлей — координаты не изменены, показать ошибку 5 сек."""
        logger.debug("Некорректные координаты — пресет сохранён")
        if self.main_window.current_session:
            self.main_window.current_session.set_error_text(
                "некорректные координаты", 5000
            )

    def on_region_moved(self, coords: dict):
        """Пресет перетащен мышью. Пресет остаётся активным, координаты обновились."""
        logger.debug(f"Пресет перемещён: {coords}")
        try:
            self.controller.set_raw_coordinates(coords)
        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")
            return

        # запомнить новый центр — чтобы при зуме пресет не прыгал в центр экрана
        if self.wm.preset_window:
            x1, y1 = coords["x1"], coords["y1"]
            x2, y2 = coords["x2"], coords["y2"]
            cx = (x1 + x2) // 2
            cy = (y1 + y2) // 2
            self.wm.preset_window.set_preset_center(cx, cy)

        if self.main_window.current_session:
            x1, y1 = coords["x1"], coords["y1"]
            x2, y2 = coords["x2"], coords["y2"]
            text = f"ширина: {x2-x1}px   высота: {y2-y1}px"
            self.main_window.current_session.set_info_text(text)

    def on_drag_started(self):
        logger.debug("Ручное выделение: начало")
        self.blink.stop()

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
            translator = self.controller.get_translator()
            preset_name = translator.tr("preset_fullscreen")
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
