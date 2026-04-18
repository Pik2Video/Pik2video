# src/pic2vid/gui/sessions.py

from PySide6.QtWidgets import QWidget, QLabel, QApplication, QVBoxLayout
from PySide6.QtCore import Qt, QTimer, QEvent, Signal
from PySide6.QtGui import QResizeEvent, QCloseEvent

from .components_settings.screen_settings import CapturePerMinuteInput
from .components_settings.setting_row import SettingRow
from .components_settings.record_settings import FpsSwitcher
from .components_settings.common_settings import TimerInput, QualitySwitcher, ExportFilenameInput

from .components_settings.finalize_common_settings import  ExportPathInput, VideoFormatInput
from .components_settings.finalize_screen_settings import PlaybackFpsInput

from src.pic2vid.gui.dialogs import confirm
from .window_positioning import center_to_parent, fullscreen_geometry, bring_window_to_front
from src.pic2vid.utils import format_size, format_timer
from .base import SettingsDialog, FinalizeWidget
from .overlays import CoordinateOverlay
from .panels import CapturePanel

class CaptureSession(QWidget):

    closed_by_user = Signal()

    back_requested = Signal()
    """
    Базовая сессия захвата. Управляет:
    - overlay / состоянием / таймерами / запретом закрытия
    """

    TIME_INTERVAL = 1000
    RAM_INTERVAL = 1000

    def __init__(self, controller, title: str, size=(410, 70)):
        super().__init__()

        self.controller = controller
        self._settings_dialog = None
        self._active = False

        # ───────── UI ─────────
        self.panel = CapturePanel(self, controller)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel)

        self.panel.btn_back.clicked.connect(self.back_requested.emit)

        self.panel.btn_settings.clicked.connect(self._on_settings_clicked)

        # ───────── Таймеры ─────────
        self.time_timer = QTimer(self)
        self.ram_timer = QTimer(self)

        self.time_timer.timeout.connect(self._request_time_update)
        self.ram_timer.timeout.connect(self._request_ram_update)
        self.ram_timer.timeout.connect(self._request_shots_update)

     
    # ──────── Старт сессии ─────────────
    def start_session(self):
        self._active = True
        self.time_timer.start(self.TIME_INTERVAL)
        self.ram_timer.start(self.RAM_INTERVAL)

    # ──────── Стоп сессии ────────
    def stop_session(self):
        self._active = False
        self.time_timer.stop()
        self.ram_timer.stop()

    def is_active(self):
        return self._active

    # ───── Обновление UI извне ─────
    def set_time(self, text: str):
        self.panel.time_label.setText(text)

    def set_ram(self, text: str):
        self.panel.ram_label.setText(text)

    def set_shots(self, value: int):
        self.panel.counter_label.setText(f"{value} SHOTS")

    # ───── Внутренние события ─────
    def _request_time_update(self):
        self.time_update_requested.emit()

    def _request_ram_update(self):
        self.ram_update_requested.emit()

    def _request_shots_update(self):  # ← добавить
        self.shots_update_requested.emit()

    def _on_settings_clicked(self):
        if self._settings_dialog is None:
            main_window = self.window()
            self._settings_dialog = self.create_settings_dialog(main_window)

        self._settings_dialog.show()
        self._settings_dialog.activateWindow()
        self._settings_dialog.raise_()

    def create_settings_dialog(self):
        raise NotImplementedError

    # ───── Qt события ─────

    def on_before_close(self) -> bool:
        """
        Решает, можно ли закрыть окно.
        PREPARING → без подтверждения.
        RECORDING → подтверждение.
        """
        if self.controller.is_preparing():
            # просто закрываем окно
            return True

        if self.controller.is_recording():
            # показываем окно подтверждения
            if confirm(
                self,
                "Прервать запись?\n\n"
                "Текущая запись будет остановлена.\n"
                "Все данные этой сессии будут удалены."
            ):
                # Сигналы и действия
                self.cancel_requested.emit()
                return True
            return False

        # для остальных состояний (IDLE и т.д.) можно просто закрыть
        return True

    

    # ───── Дополнительные сигналы ─────
    time_update_requested = Signal()
    ram_update_requested = Signal()
    shots_update_requested = Signal()  # ← добавить



''' Окно записи видео. '''
class VideoCaptureSession(CaptureSession):

    # ───────── СИГНАЛЫ ─────────
    start_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, controller):
        super().__init__(
            controller=controller,
            title="запись видео",
        )

        self.panel.btn_start.clicked.connect(self._on_start_clicked)
        self.panel.btn_stop.clicked.connect(self._on_stop_clicked)

    # ───────── КНОПКИ ─────────
    def _on_start_clicked(self):
        """ Пользователь нажал START. Мы ничего не решаем. Просто сообщаем наружу. """
        self.start_requested.emit()

    def _on_stop_clicked(self):
        """ Пользователь нажал STOP. Сообщаем наружу. """
        self.stop_requested.emit()

    def create_settings_dialog(self, parent):
        return RecordSettingsDialog(parent, self.controller)

    # ───────── ВЫЗЫВАЕТСЯ ИЗ Application ─────────
    def set_recording_mode(self):
        """ Application вызывает этот метод, когда запись реально началась. """
        self.panel.btn_start.setEnabled(False)
        self.panel.set_recording_mode()
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.start_session()

    def set_idle_mode(self):
        """ Application вызывает, когда запись остановлена. """
        self.panel.btn_start.setEnabled(True)
        self.panel.set_idle_mode()
        self.panel.btn_start.setEnabled(True)
        self.panel.btn_stop.setEnabled(False)
        self.stop_session()

    
    def _on_closed_by_user(self):
        self.cancel_requested.emit()

''' Окно серийного захвата. '''
class ScreenCaptureSession(CaptureSession):
    # ───────── СИГНАЛЫ ─────────
    start_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, controller):
        super().__init__(
            controller=controller,
            title="захват экрана",
        )

        # Показываем метку SHOTS только для экрана
        self.panel.counter_label.setVisible(True)

        # Подключение кнопок к сигналам
        self.panel.btn_start.clicked.connect(self._on_start_clicked)
        self.panel.btn_stop.clicked.connect(self._on_stop_clicked)

        
    # ───────── Кнопки ─────────
    def _on_start_clicked(self):
        """Пользователь нажал START"""
        self.start_requested.emit()

    def _on_stop_clicked(self):
        """Пользователь нажал STOP"""
        self.stop_requested.emit()

    def create_settings_dialog(self, parent):
        return ScreenSettingsDialog(parent, self.controller)

    # ───────── Вызовы из Application ─────────
    def set_recording_mode(self):
        """Application сообщает, что запись началась"""
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_settings.setEnabled(False)
        self.panel.set_recording_mode()  
        self.panel.btn_stop.setEnabled(True)  # ← включаем кнопку стоп
        self.start_session()

    def set_idle_mode(self):
        """Application сообщает, что запись остановлена"""
        self.panel.btn_start.setEnabled(True)
        self.panel.btn_settings.setEnabled(True)
        self.panel.set_idle_mode()  
        self.panel.btn_stop.setEnabled(False)  # ← выключаем кнопку стоп
        self.stop_session()

    
    def _on_closed_by_user(self):
        self.cancel_requested.emit()



''' Окно настроек записи видео. Record '''
class RecordSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")  # заголовок установим позже
        
        # Подключаем локализацию ПОСЛЕ создания UI
        self.setup_localization()

    def build_content(self, layout):
        # Сохраняем строки как атрибуты
        self.export_filename_input = ExportFilenameInput(
            initial=self.controller.get_export_filename()
        )
        self.row_filename = SettingRow("", self.export_filename_input)
        layout.addWidget(self.row_filename)
        self.export_filename_input.valueChanged.connect(self.controller.set_export_filename)

        # FPS
        self.fps_switcher = FpsSwitcher(
            values=[25, 30, 60],
            initial=self.controller.get_record_fps()
        )
        self.row_fps = SettingRow("", self.fps_switcher)
        layout.addWidget(self.row_fps)

        # Качество
        self.quality_switcher = QualitySwitcher(
            values=["Низкое", "Среднее", "Высокое"],
            initial=self.controller.get_record_quality()
        )
        self.row_quality = SettingRow("", self.quality_switcher)
        layout.addWidget(self.row_quality)

        # Таймер
        self.timer_input = TimerInput()
        seconds = self.controller.get_record_timer()
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_input.hours.setValue(h)
        self.timer_input.minutes.setValue(m)
        self.timer_input.seconds.setValue(s)
        self.row_timer = SettingRow("", self.timer_input)
        layout.addWidget(self.row_timer)

    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator = self.controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        self.setWindowTitle(self.translator.tr("record_settings_title"))
        self.row_filename.setText(self.translator.tr("filename_setting"))
        self.row_fps.setText(self.translator.tr("fps_setting"))
        self.row_quality.setText(self.translator.tr("quality_setting"))
        self.row_timer.setText(self.translator.tr("stop_after_setting"))

    def apply_settings(self) -> bool:
        self.controller.set_record_fps(self.fps_switcher.get())
        self.controller.set_record_quality(self.quality_switcher.get())
        self.controller.set_record_timer(self.timer_input.get_seconds())
        return True

''' Окно настроек серийного захвата. '''
class ScreenSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")  # заголовок установим позже

        self.setFixedSize(440, 180)
        
        # Подключаем локализацию ПОСЛЕ создания UI
        self.setup_localization()

    def build_content(self, layout):
        # Сохраняем строки как атрибуты
        self.export_filename_input = ExportFilenameInput(
            initial=self.controller.get_export_filename()
        )
        self.row_filename = SettingRow("", self.export_filename_input)
        layout.addWidget(self.row_filename)
        self.export_filename_input.valueChanged.connect(self.controller.set_export_filename)

        # Capture per minute
        self.capture_input = CapturePerMinuteInput(initial=self.controller.get_screen_fps())
        self.row_capture = SettingRow("", self.capture_input)
        layout.addWidget(self.row_capture)

        # Таймер
        self.timer_input = TimerInput()
        seconds = self.controller.get_screen_timer()
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_input.hours.setValue(h)
        self.timer_input.minutes.setValue(m)
        self.timer_input.seconds.setValue(s)
        self.row_timer = SettingRow("", self.timer_input)
        layout.addWidget(self.row_timer)

    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator = self.controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        self.setWindowTitle(self.translator.tr("screen_settings_title"))
        self.row_filename.setText(self.translator.tr("filename_setting"))
        self.row_capture.setText(self.translator.tr("capture_per_minute"))
        self.row_timer.setText(self.translator.tr("stop_after_setting"))

    def apply_settings(self):
        self.controller.set_screen_fps(self.capture_input.get())
        self.controller.set_screen_timer(self.timer_input.get_seconds())
        return True



''' ФИНАЛЬНОЕ ОКНО ВИДЕОЗАПИСИ '''
class VideoFinalizeWidget(FinalizeWidget):
    """Виджет финализации видео (встраивается в MainWindow)"""
    
    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="")
        self.build_content(self.content_layout)

        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        # Обновляем кнопки через родительский метод
        super().retranslate_ui()
        
    def build_content(self, layout: QVBoxLayout):
        self.export_path_input = ExportPathInput(
            controller=self.controller,
            initial_path=self.controller.get_export_path()
        )
        layout.addWidget(self.export_path_input)
        self.export_path_input.valueChanged.connect(self.controller.set_export_path)


''' ФИНАЛЬНОЕ ОКНО СЕРИЙНОГО ЗАХВАТА '''
class ScreenFinalizeWidget(FinalizeWidget):
    """Виджет финализации screen захвата (встраивается в MainWindow)"""
    
    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="")
        self.build_content(self.content_layout)

        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        # Обновляем кнопки через родительский метод
        super().retranslate_ui()
        
        # Обновляем свои строки
        if hasattr(self, 'row_format'):
            self.row_format.setText(self.translator.tr("video_format"))
        if hasattr(self, 'row_fps'):
            self.row_fps.setText(self.translator.tr("playback_fps"))
        
    def build_content(self, layout: QVBoxLayout):
        self.video_format_selector = VideoFormatInput(
            initial=self.controller.get_video_format()
        )
        self.row_format = SettingRow("", self.video_format_selector)
        layout.addWidget(self.row_format)
        self.video_format_selector.valueChanged.connect(self.controller.set_video_format)
        
        self.playback_fps = PlaybackFpsInput(
            initial=self.controller.get_screen_finalize_fps()
        )
        self.row_fps = SettingRow("", self.playback_fps)
        layout.addWidget(self.row_fps)
        self.playback_fps.valueChanged.connect(self.controller.set_screen_finalize_fps)
        
        self.export_path_input = ExportPathInput(
            controller=self.controller,
            initial_path=self.controller.get_export_path()
        )
        layout.addWidget(self.export_path_input)
        self.export_path_input.valueChanged.connect(self.controller.set_export_path)