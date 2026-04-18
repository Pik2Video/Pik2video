# src/pic2vid/app.py

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer  # ← добавили QTimer


from src.pic2vid.application.session_types import SessionType
from src.pic2vid.gui.window_positioning import bottom_right_position, center_to_parent, bring_window_to_front

from src.pic2vid.application.controller import AppController
from src.pic2vid.gui.overlays import CoordinateOverlay
from src.pic2vid.gui.windows import MainWindow, AppSettingsDialog
from src.pic2vid.gui.sessions import VideoCaptureSession, ScreenCaptureSession, VideoFinalizeWidget, ScreenFinalizeWidget
from src.pic2vid.application.state_machine import AppState


class Application:
    """
    Центральный управляющий класс приложения.
    
    Теперь:
    - MainWindow ОДИН и всегда виден
    - Внутри MainWindow меняются виджеты (CaptureSession, FinalizeWidget)
    - Overlay открывается отдельно только для выбора области
    """

    def __init__(self):
        # ───── Qt приложение ─────
        
        self.qt_app = QApplication.instance() or QApplication([])

        # ───── Контроллер ─────
        self.controller = AppController()
        self.controller.state_changed.connect(self._on_state_changed)

        # ───── Главное окно (ОДНО и всегда видно) ─────
        self.main_window = MainWindow(self.controller)

        # Добавляем флаг "поверх всех"
        self.main_window.setWindowFlags(
            self.main_window.windowFlags() | Qt.WindowStaysOnTopHint
        )

        self._position_main_window()
        self.main_window.show()  # ← ТОЛЬКО ЗДЕСЬ! Больше НИГДЕ!

        # ─── Подписка на сигналы MainWindow ───
        self.main_window.start_video_requested.connect(self.controller.prepare_video)
        self.main_window.start_screen_requested.connect(self.controller.prepare_screen)
        self.main_window.settings_requested.connect(self._open_app_settings)

        # ───── Вспомогательные окна ─────
        self.overlay = None           # Отдельное окно для выбора области
        self.app_settings_window = None  # Отдельное окно настроек


    # =================Позиционирование==================
    def _position_main_window(self):
        screen = self.main_window.screen().availableGeometry()
        pos = bottom_right_position(self.main_window, screen, margin=117)
        self.main_window.move(pos)

    # ==============ОБРАБОТКА ИЗМЕНЕНИЯ СОСТОЯНИЯ=============
    def _on_state_changed(self, state: AppState):
        """Реакция GUI на смену состояния контроллера"""
        print(f"\n[Application] Состояние: {state}")
        self._sync_windows_with_state(state)

    def _sync_windows_with_state(self, state: AppState):
        """Синхронизация UI с состоянием"""
        
        # ──────────────────────────────────────────────
        # 1. IDLE - главный экран с кнопками
        # ──────────────────────────────────────────────
        if state == AppState.IDLE:
            # Закрываем overlay если открыт
            if self.overlay:
                self.overlay.close()
                self.overlay = None
            
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
                print("[Application] Показываем видео сессию в MainWindow")
                self.main_window.show_video_session(self.controller)
            else:
                print("[Application] Показываем screen сессию в MainWindow")
                self.main_window.show_screen_session(self.controller)
            
            # 2.2 Показываем overlay для выбора области
            if self.overlay is None:
                self.overlay = CoordinateOverlay()
                self.overlay.coords_selected.connect(self._on_overlay_coords)
                
                screen = self.qt_app.primaryScreen().geometry()
                self.overlay.setGeometry(screen)
                self.overlay.show()
                print("[Application] Overlay показан")

                #QTimer.singleShot(50, lambda: self._bring_main_window_to_front())
            
            return
        
        # ──────────────────────────────────────────────
        # 3. RECORDING - идёт запись
        # ──────────────────────────────────────────────
        if state == AppState.RECORDING:
            # Закрываем overlay
            if self.overlay:
                self.overlay.close()
                self.overlay = None
            
            # Переключаем текущую сессию в режим записи
            if self.main_window.current_session:
                self.main_window.current_session.set_recording_mode()
                print("[Application] Сессия переключена в режим записи")
            
            return
        
        # ──────────────────────────────────────────────
        # 4. REVIEW - запись закончена (финализация)
        # ──────────────────────────────────────────────
        if state == AppState.REVIEW:
            # Закрываем overlay на всякий случай
            if self.overlay:
                self.overlay.close()
                self.overlay = None
            
            # Показываем экран финализации
            session_type = self.controller.get_session_type()
            
            if session_type == SessionType.VIDEO:
                print("[Application] Показываем финализацию видео")
                self.main_window.show_video_finalize(self.controller)
            else:
                print("[Application] Показываем финализацию screen")
                self.main_window.show_screen_finalize(self.controller)
            
            return

    
    # =================Управление overlay==================
    def _on_overlay_coords(self, coords: dict):
        """Получили координаты от overlay"""
        print(f"[Application] Получены координаты: {coords}")
        try:
            self.controller.set_raw_coordinates(coords)
            print("[Application] Координаты переданы в контроллер")
        except ValueError as e:
            print(f"[Application] Ошибка координат: {e}")

    # =================Управление настройками==================
    def _open_app_settings(self):
        """Открыть окно настроек"""
        if self.app_settings_window is None:
            self.app_settings_window = AppSettingsDialog(self.main_window, self.controller)
        
        self.app_settings_window.show()
        self.app_settings_window.activateWindow()
        bring_window_to_front(self.app_settings_window)

    

    # =================ЗАПУСК ПРИЛОЖЕНИЯ=======================
    def run(self):
        """Запуск главного цикла Qt приложения"""
        self.qt_app.exec()