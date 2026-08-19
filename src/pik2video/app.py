# src/pik2video/app.py

import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer

from src.pik2video.infrastructure.logging import setup_logging

# ← НАСТРОЙКА ЛОГИРОВАНИЯ С ПРОВЕРКОЙ АРГУМЕНТОВ
debug_mode = "--debug" in sys.argv or "-d" in sys.argv
setup_logging(debug_mode=debug_mode)

import logging
logger = logging.getLogger(__name__)

from src.pik2video.utils import format_size, format_time

from src.pik2video.application.controller import AppController
from src.pik2video.application.session_types import SessionType
from src.pik2video.application.state_machine import AppState

from src.pik2video.gui.windows import MainWindow, AppSettingsDialog
from src.pik2video.gui.sessions import VideoCaptureSession, ScreenCaptureSession, VideoFinalizeWidget, ScreenFinalizeWidget
from src.pik2video.gui.overlays import CoordinateOverlay
from src.pik2video.gui.preset_window import PresetWindow
from src.pik2video.gui.ffmpeg_dialog import FFmpegMissingDialog

from src.pik2video.gui.utils import bottom_right_position, center_to_parent, bring_window_to_front, keep_window_inside_screen



class Application:
    """
    Главный класс приложения.
    
    Отвечает за:
    - Запуск Qt приложения
    - Управление окнами (главное окно, overlay, окно пресетов, настройки)
    - Реакцию на изменения состояния контроллера (показывает нужные виджеты)
    - Координацию между контроллером и GUI (передача координат области записи)
    
    Приложение имеет одно главное окно, внутри которого меняются виджеты
    в зависимости от текущего состояния (IDLE, PREPARING, RECORDING, REVIEW).
    """

    def __init__(self):
        # ───── Qt приложение ─────
        
        self.qt_app = QApplication.instance() or QApplication([])

        # ───── Контроллер ─────
        self.controller = AppController()
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.ffmpeg_required.connect(self._on_ffmpeg_missing)


        # ───── Главное окно (ОДНО и всегда видно) ─────
        self.main_window = MainWindow(self.controller)

        # Флаг "всегда в топе" управляется в _sync_windows_with_state

        # 🆕 Применить флаг "всегда в топе" при старте
        if self.controller.get_always_on_top():
            self.main_window.setWindowFlags(
                self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
            )
            self.main_window.show()
    
        self._position_main_window()
        self.main_window.show()

        # ─── Подписка на сигналы MainWindow ───
        self.main_window.start_video_requested.connect(self.controller.prepare_video)
        self.main_window.start_screen_requested.connect(self.controller.prepare_screen)
        self.main_window.settings_requested.connect(self._open_app_settings)

        # ───── Вспомогательные окна ─────
        self.overlay = None           # Отдельное окно для выбора области
        self.preset_window = None
        self.app_settings_window = None  # Отдельное окно настроек


    # =================Позиционирование==================
    def _position_main_window(self):
        screen = self.main_window.screen().availableGeometry()
        pos = bottom_right_position(self.main_window, screen, margin=117)
        self.main_window.move(pos)

    # ==============ОБРАБОТКА ИЗМЕНЕНИЯ СОСТОЯНИЯ=============
    def _on_state_changed(self, state: AppState):
        """Реакция GUI на смену состояния контроллера"""
        logger.debug(f"Состояние: {state}")
        self._sync_windows_with_state(state)

    # =================FFMPEG ОБРАБОТКА==================
    def _on_ffmpeg_missing(self):
        """Показать окно, если FFmpeg не установлен"""

        logger.error("FFmpeg не найден → показываем диалог")

        dialog = FFmpegMissingDialog(self.main_window)

        result = dialog.exec()

        # здесь можно расширить логику:
        # например открыть сайт или повторную проверку
        if result:
            logger.debug("Пользователь закрыл окно FFmpeg")

    def _sync_windows_with_state(self, state: AppState):
        """Синхронизация UI с состоянием"""

        # Управление флагом "всегда в топе"
        always_on_top = self.controller.get_always_on_top()
        is_preparing = state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)
        should_be_on_top = always_on_top or is_preparing
        
        is_currently_on_top = bool(self.main_window.windowFlags() & Qt.WindowStaysOnTopHint)

        # 🆕 ОТЛАДОЧНЫЙ PRINT — вставить здесь
        logger.debug(f"always_on_top={always_on_top}, is_preparing={is_preparing}, should={should_be_on_top}, current={is_currently_on_top}, state={state}")
        
        if should_be_on_top != is_currently_on_top:
            if should_be_on_top:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
                )
            else:
                self.main_window.setWindowFlags(
                    self.main_window.windowFlags() & ~Qt.WindowStaysOnTopHint
                )
            self.main_window.show()  # ← ОБЯЗАТЕЛЬНО вернуть        
        # ──────────────────────────────────────────────
        # 1. IDLE - главный экран с кнопками
        # ──────────────────────────────────────────────
        if state == AppState.IDLE:
            # Закрываем overlay если открыт
            if self.overlay:
                self.overlay.close()
                self.overlay = None

            # Закрываем окно с пресетами
            if self.preset_window:
                self.preset_window.close()
                self.preset_window = None
            
            # Показываем главный экран в MainWindow
            self.main_window.show_idle_screen()
            
            # Активируем главное окно
            self.main_window.activateWindow()
            bring_window_to_front(self.main_window)
            return
        
        # ──────────────────────────────────────────────
        # 2. PREPARING - подготовка к записи (выбор области)
        # ──────────────────────────────────────────────
        if state in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN):
            
            session_type = self.controller.get_session_type()
            
            # 2.1 Меняем содержимое MainWindow на CaptureSession
            if session_type == SessionType.VIDEO:
                logger.debug("Показываем видео сессию в MainWindow")
                self.main_window.show_video_session(self.controller)
            else:
                logger.debug("Показываем screen сессию в MainWindow")
                self.main_window.show_screen_session(self.controller)
            
            # 2.2 Показываем overlay для выбора области
            if self.overlay is None:
                self.overlay = CoordinateOverlay()
                self.overlay.coords_selected.connect(self._on_overlay_coords)
                screen = self.qt_app.primaryScreen().geometry()
                self.overlay.setGeometry(screen)
                self.overlay.show()
                logger.debug("Overlay показан")

                # 🆕 Устанавливаем начальный пресет (мобильный по умолчанию)
                #default_coords = PresetWindow.get_default_preset_coords(screen)
                #self.overlay.set_region(default_coords)
                #logger.debug(f"Установлен начальный пресет: {default_coords}")

            # 2.3 Показываем окно с пресетами (готовые размеры)
            if self.preset_window is None:
                self.preset_window = PresetWindow(self.controller)
                self.preset_window.preset_selected.connect(self._on_preset_selected)
                self.preset_window.show()
                logger.debug("Окно пресетов показано")

            
            return
        
        # ──────────────────────────────────────────────
        # WAITING — отсчёт перед стартом (🆕 НОВЫЙ БЛОК)
        # ──────────────────────────────────────────────
        if state == AppState.WAITING:
            # Закрываем overlay
            if self.overlay:
                self.overlay.close()
                self.overlay = None

            # Закрываем окно с пресетами
            if self.preset_window:
                self.preset_window.close()
                self.preset_window = None
            
            logger.debug("Переход в WAITING — окна закрыты")
            return

        # ──────────────────────────────────────────────
        # 3. RECORDING - идёт запись
        # ──────────────────────────────────────────────
        if state == AppState.RECORDING:
            
            
            # Переключаем текущую сессию в режим записи
            if self.main_window.current_session:
                self.main_window.current_session.set_recording_mode()
                logger.debug("Сессия переключена в режим записи")

            return
        
        # ──────────────────────────────────────────────
        # 4. REVIEW - запись закончена (финализация)
        # ──────────────────────────────────────────────
        if state == AppState.REVIEW:
            # Закрываем overlay на всякий случай
            if self.overlay:
                self.overlay.close()
                self.overlay = None

            # Закрываем окно с пресетами
            if self.preset_window:
                self.preset_window.close()
                self.preset_window = None
            
            # Показываем экран финализации
            session_type = self.controller.get_session_type()
            
            if session_type == SessionType.VIDEO:
                logger.debug("Показываем финализацию видео")
                self.main_window.show_video_finalize(self.controller)
            else:
                logger.debug("Показываем финализацию screen")
                self.main_window.show_screen_finalize(self.controller)
            
            # 🆕 Обновить метки с данными сессии
            if self.main_window.current_session:
                ram = format_size(self.controller.get_session_size())
                time_str = format_time(self.controller.get_elapsed_time())
                self.main_window.current_session.update_stats(ram, time_str)
            
            return

    
    # =================Управление overlay==================
    def _on_overlay_coords(self, coords: dict):
        """Получили координаты от overlay"""
        logger.debug(f"Получены координаты: {coords}")

        try:
            self.controller.set_raw_coordinates(coords)
            logger.debug("Координаты переданы в контроллер")

        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")

    
    # =================Управление пресетами==================
    def _on_preset_selected(self, coords: dict):
        """Пользователь выбрал готовый размер области записи"""
        logger.debug(f"Выбран пресет с координатами: {coords}")

        try:
            self.controller.set_raw_coordinates(coords)
            # Обновляем область на overlay (показать рамку)
            if self.overlay:
                self.overlay.set_region(coords)
                logger.debug("Область обновлена на overlay")

        except ValueError as e:
            logger.error(f"Ошибка координат: {e}")


    # =================Управление настройками==================
    def _open_app_settings(self):
        """Открыть окно настроек"""
        if self.app_settings_window is None:
            self.app_settings_window = AppSettingsDialog(self.main_window, self.controller)

        keep_window_inside_screen(self.app_settings_window)
        self.app_settings_window.show()

        self.app_settings_window.activateWindow()
        bring_window_to_front(self.app_settings_window)

    

    # =================ЗАПУСК ПРИЛОЖЕНИЯ=======================
    def run(self):
        """Запуск главного цикла Qt приложения"""
        self.qt_app.exec()
