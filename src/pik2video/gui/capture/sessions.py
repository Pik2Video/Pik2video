# src/pik2video/gui/capture/sessions.py

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QSpinBox, QVBoxLayout, QWidget

from ..common.base import SettingsDialog
from ..common.utils import keep_window_inside_screen
from ..widgets.common_settings import ExportFilenameInput, QualitySwitcher, TimerInput
from ..widgets.record_settings import FpsSwitcher
from ..widgets.screen_settings import CapturePerMinuteInput, CleanSpinBox
from ..widgets.setting_row import SettingRow

#from .overlays import CoordinateOverlay
from .panels import CapturePanel


class CaptureSession(QWidget):
    """
    Базовая сессия захвата. Управляет:
    - overlay / состоянием / таймерами / запретом закрытия
    """

    back_requested = Signal()

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
        self.cpu_timer = QTimer(self)  # 🆕 новый таймер для CPU

        self.time_timer.timeout.connect(self._request_time_update)
        self.ram_timer.timeout.connect(self._request_ram_update)
        self.cpu_timer.timeout.connect(self._request_cpu_update)
        self.ram_timer.timeout.connect(self._request_shots_update)

    # ──────── Старт сессии ─────────────
    def start_session(self):
        self._active = True
        self.time_timer.start(self.TIME_INTERVAL)
        self.ram_timer.start(self.RAM_INTERVAL)
        self.cpu_timer.start(self.RAM_INTERVAL)  # запуск CPU таймера

    # ──────── Стоп сессии ────────
    def stop_session(self):
        self._active = False
        self.time_timer.stop()
        self.ram_timer.stop()
        self.cpu_timer.stop()  # остановка CPU таймера

    # ───── Обновление UI извне ─────
    def set_time(self, text: str):
        """Обновить таймер в чёрном поле"""
        if self.panel and self.panel.right_label:
            try:
                self.panel.update_recording_time(text)
            except RuntimeError:
                pass

    def set_ram(self, text: str):
        """Обновить RAM в нижней панели"""
        if self.panel and hasattr(self.panel, 'ram_label'):
            try:
                self.panel.ram_label.setText(text)
            except RuntimeError:
                pass

    def set_shots(self, value: int):
        """Обновить счётчик SHOTS (только для screen)"""
        if self.panel:
            try:
                self.panel.update_recording_shots(f"{value} SHOTS")
            except RuntimeError:
                pass

    def set_cpu(self, text: str):
        """Обновить CPU в нижней панели"""
        if self.panel and hasattr(self.panel, 'cpu_label'):
            try:
                self.panel.cpu_label.setText(text)
            except RuntimeError:
                pass

    def set_info_text(self, text: str):
        """Показать текст в чёрном информационном поле (центральная метка)."""
        if self.panel:
            try:
                self.panel.set_info_text(text)
            except RuntimeError:
                pass

    def set_blink_phase(self, phase: float):
        """Прокинуть фазу мигания в панель."""
        if self.panel:
            try:
                self.panel.set_info_blink_phase(phase)
            except RuntimeError:
                pass

    # ───── Внутренние события ─────
    def _request_time_update(self):
        self.time_update_requested.emit()

    def _request_ram_update(self):
        self.ram_update_requested.emit()

    def _request_shots_update(self):  # ← добавить
        self.shots_update_requested.emit()

    def _request_cpu_update(self):
        if self._active:
            self.cpu_update_requested.emit()

    def _on_settings_clicked(self):
        if self._settings_dialog is None:
            main_window = self.window()
            self._settings_dialog = self.create_settings_dialog(main_window)

        keep_window_inside_screen(self._settings_dialog)
        self._settings_dialog.show()
        self._settings_dialog.activateWindow()
        self._settings_dialog.raise_()

    def _animate_dots(self):
        """Анимация точек во время записи"""
        self._dot_count = (self._dot_count + 1) % 4
        dots = "." * self._dot_count
        self.panel.update_recording_dots(f"запись{dots}")

    def create_settings_dialog(self):
        raise NotImplementedError

    # ───── Дополнительные сигналы ─────
    time_update_requested = Signal()
    ram_update_requested = Signal()
    shots_update_requested = Signal()
    cpu_update_requested = Signal()

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
        self.cpu_update_requested.connect(self._update_cpu)

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
        """Application сообщает, что запись началась"""
        self.panel.set_info_blink_phase(1.0)

        self.panel.set_recording_mode() # Переключаем панель в режим записи
        self.panel.set_recording_video_mode() # Настраиваем чёрное поле для VIDEO режима
        # Запускаем анимацию точек
        self._dot_count = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_timer.start(300)
        # Управление кнопками
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.start_session() # Запускаем таймеры обновления

    def set_idle_mode(self):
        """ Application вызывает, когда запись остановлена. """
        self.panel.btn_start.setEnabled(True)
        self.panel.set_idle_mode()
        self.panel.btn_start.setEnabled(True)
        self.panel.btn_stop.setEnabled(False)
        self.stop_session()

    def _on_closed_by_user(self):
        self.cancel_requested.emit()

    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage} %")

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

        #self.panel.counter_label.setVisible(True) # Показываем метку SHOTS только для экрана
        # Подключение кнопок к сигналам
        self.panel.btn_start.clicked.connect(self._on_start_clicked)
        self.panel.btn_stop.clicked.connect(self._on_stop_clicked)

        self.cpu_update_requested.connect(self._update_cpu)

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
        self.panel.set_info_blink_phase(1.0)
        
        self.panel.set_recording_mode() # Переключаем панель в режим записи
        self.panel.set_recording_screen_mode() # Настраиваем чёрное поле для SCREEN режима
        # Запускаем анимацию точек (теперь в центре)
        self._dot_count = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_timer.start(800)
        
        # Управление кнопками
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_settings.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        
        self.start_session() # Запускаем таймеры обновления

    def set_idle_mode(self):
        """Application сообщает, что запись остановлена"""
        self.panel.btn_start.setEnabled(True)
        self.panel.btn_settings.setEnabled(True)
        self.panel.set_idle_mode()  
        self.panel.btn_stop.setEnabled(False)  # ← выключаем кнопку стоп
        self.stop_session()

    def _on_closed_by_user(self):
        self.cancel_requested.emit()

    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage} %")

''' Окно настроек записи видео. Record '''
class RecordSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        self.setup_localization() # Подключаем локализацию ПОСЛЕ создания UI

    def build_content(self, layout):
        self.content_widget.setMinimumWidth(480) # Устанавливаем минимальную ширину (как в глобальных настройках)
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

        # Пауза перед стартом
        self.start_delay_input = CleanSpinBox()
        self.start_delay_input.setRange(0, 30)
        self.start_delay_input.setValue(self.controller.get_start_delay())
        self.start_delay_input.setMinimumWidth(60)
        self.start_delay_input.setAlignment(Qt.AlignCenter)
        self.start_delay_input.setButtonSymbols(QSpinBox.NoButtons)
        self.row_start_delay = SettingRow("", self.start_delay_input)
        layout.addWidget(self.row_start_delay)

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
        self.row_start_delay.setText(self.translator.tr("start_delay_setting"))  # 🆕
        self.row_timer.setText(self.translator.tr("stop_after_setting"))

    def apply_settings(self) -> bool:
        self.controller.set_record_fps(self.fps_switcher.get())
        self.controller.set_record_quality(self.quality_switcher.get())
        self.controller.set_start_delay(self.start_delay_input.value())  # 🆕
        self.controller.set_record_timer(self.timer_input.get_seconds())
        return True

''' Окно настроек серийного захвата. '''
class ScreenSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        #self.setFixedSize(440, 180)
        self.setup_localization() # Подключаем локализацию ПОСЛЕ создания UI

    def build_content(self, layout):
        self.content_widget.setMinimumWidth(480)  # 🆕 Устанавливаем минимальную ширину (как в глобальных настройках)
        
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

        # 🆕 Пауза перед стартом
        self.start_delay_input = CleanSpinBox()
        self.start_delay_input.setRange(0, 30)
        self.start_delay_input.setValue(self.controller.get_start_delay())
        self.start_delay_input.setMinimumWidth(60)
        self.start_delay_input.setAlignment(Qt.AlignCenter)
        self.start_delay_input.setButtonSymbols(QSpinBox.NoButtons)
        self.row_start_delay = SettingRow("", self.start_delay_input)
        layout.addWidget(self.row_start_delay)

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
        self.row_start_delay.setText(self.translator.tr("start_delay_setting"))
        self.row_timer.setText(self.translator.tr("stop_after_setting"))

    def apply_settings(self):
        self.controller.set_screen_fps(self.capture_input.get())
        self.controller.set_start_delay(self.start_delay_input.value())  # 🆕
        self.controller.set_screen_timer(self.timer_input.get_seconds())
        return True

