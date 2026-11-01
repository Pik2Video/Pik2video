# src/pik2video/gui/capture/sessions.py

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import QCheckBox, QLabel, QSpinBox, QVBoxLayout, QWidget

from ..common.base import SettingsDialog
from ..common.utils import keep_window_inside_screen

from ..widgets.audio_settings import (
    AudioSourceSelector,
    SampleRateSelector,
    ChannelsSelector,
)
from ..widgets.common_settings import ExportFilenameInput, QualitySwitcher, TimerInput
from ..widgets.record_settings import FpsSwitcher
from ..widgets.screen_settings import CapturePerMinuteInput, CleanSpinBox, NullableSpinBox
from ..widgets.global_settings import AlwaysOnTopSetting, ShowRecordingFrameSetting
from ..widgets.setting_row import SettingRow

from .panels import CapturePanel


class CaptureSession(QWidget):
    """
    Базовая сессия захвата. Управляет:
    - overlay / состоянием / таймерами / запретом закрытия
    """

    back_requested = Signal()
    settings_visibility_changed = Signal(bool)   # True = настройки открыты, False = закрыты

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

        self.panel.btn_settings.clicked.connect(self._on_settings_clicked)

        # ───────── Таймеры ─────────
        self.time_timer = QTimer(self)
        self.ram_timer = QTimer(self)
        self.cpu_timer = QTimer(self)

        self.time_timer.timeout.connect(self._request_time_update)
        self.ram_timer.timeout.connect(self._request_ram_update)
        self.cpu_timer.timeout.connect(self._request_cpu_update)
        
        self.size_timer = QTimer(self)                             # отдельный таймер для размера файла (аудио)
        self.size_timer.timeout.connect(self._request_size_update) # обновление метки размера раз в секунду

    # ──────── Старт сессии ─────────────
    def start_session(self):
        self._active = True
        self.time_timer.start(self.TIME_INTERVAL)
        self.ram_timer.start(self.RAM_INTERVAL)
        self.cpu_timer.start(5000)                 # CPU — раз в 5 секунд (экономия места)
        self.size_timer.start(self.RAM_INTERVAL)   # запускаем обновление размера вместе с остальными

    # ──────── Стоп сессии ────────
    def stop_session(self):
        self._active = False
        self.time_timer.stop()
        self.ram_timer.stop()
        self.cpu_timer.stop()
        self.size_timer.stop()   # останавливаем обновление размера

    def set_preparation_mode(self):
        """Показать «Подготовка файла» в чёрном поле, заблокировать кнопки."""
        self.stop_session()
        if self.panel:
            try:
                self.panel.set_preparation_mode()
                self.panel.repaint()          # синхронная перерисовка до блокирующего merge
            except RuntimeError:
                pass

    # ───── Обновление UI извне ─────
    def set_time(self, text: str):
        """Обновить таймер в нижней панели."""
        if self.panel:
            try:
                self.panel.update_recording_time(text)     # таймер теперь в статус-странице
            except RuntimeError:
                pass

    def set_ram(self, text: str):
        """Обновить первую метку над таймером."""
        if self.panel:
            try:
                self.panel.status_label_1.setText(text)   # первая метка — RAM
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
        """Обновить вторую метку над таймером (CPU)."""
        if self.panel:
            try:
                self.panel.status_label_2.setText(text)   # вторая метка — CPU
            except RuntimeError:
                pass
    def set_size(self, text: str):
        """Обновить размер файла в нижней панели."""
        if self.panel:
            try:
                self.panel.status_label_2.setText(text)   # вторая метка сверху показывает размер
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

    def set_error_text(self, text: str, duration_ms: int = 5000):
        """Показать сообщение об ошибке в чёрном поле на duration_ms."""
        if self.panel:
            try:
                self.panel.set_error_text(text, duration_ms)
            except RuntimeError:
                pass

    # ───── Внутренние события ─────
    def _request_time_update(self):
        self.time_update_requested.emit()

    def _request_ram_update(self):
        self.ram_update_requested.emit()

    def _request_shots_update(self):
        self.shots_update_requested.emit()

    def _request_cpu_update(self):
        if self._active:
            self.cpu_update_requested.emit()

    def _request_size_update(self):
        self.size_update_requested.emit()   # сообщаем наружу о необходимости обновить размер файла

    def _on_settings_clicked(self):
        if self._settings_dialog is None:
            main_window = self.window()
            self._settings_dialog = self.create_settings_dialog(main_window)
            self._settings_dialog.installEventFilter(self)

        self.settings_visibility_changed.emit(True)          # пауза мигания + скрыть пресеты
        self.window().hide()                                 # скрываем окно записи
        keep_window_inside_screen(self._settings_dialog)
        self._settings_dialog.show()
        self._settings_dialog.activateWindow()
        self._settings_dialog.raise_()

    def eventFilter(self, obj, event):
        """Показать окно записи обратно после закрытия/скрытия диалога настроек."""
        if obj is self._settings_dialog and event.type() == QEvent.Hide:
            w = self.window()
            if w is not None and not w.isVisible():
                w.show()
                w.raise_()
                w.activateWindow()
            self.settings_visibility_changed.emit(False)     # возобновить мигание + показать пресеты
        return super().eventFilter(obj, event)

    def create_settings_dialog(self):
        raise NotImplementedError

    # ───── Дополнительные сигналы ─────
    time_update_requested = Signal()
    ram_update_requested = Signal()
    shots_update_requested = Signal()
    cpu_update_requested = Signal()
    size_update_requested = Signal()   # запрос на обновление размера файла (для аудио)

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
        fps = self.controller.get_record_fps()                       # текущий FPS из настроек
        quality = self.controller.get_record_quality()               # текущее качество из настроек
        self.panel.show_video_info(f"FPS: {fps}", f"Качество: {quality}")  # параметры записи в чёрное поле
        self.panel.set_recording_mode()                              # центр на статус, красная точка пульсирует
        self.panel.set_status_labels("RAM: 0.1 GB", "CPU: 0%")        # начальные значения двух меток
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.start_session()

    def _on_closed_by_user(self):
        self.cancel_requested.emit()

    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage}%")

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

        # Подключение кнопок к сигналам
        self.panel.btn_start.clicked.connect(self._on_start_clicked)
        self.panel.btn_stop.clicked.connect(self._on_stop_clicked)

        self.cpu_update_requested.connect(self._update_cpu)
        self.ram_timer.timeout.connect(self._request_shots_update)

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
        quality = self.controller.get_record_quality()               # текущее качество из настроек
        self.panel.show_video_info("0 SHOTS", f"Качество: {quality}")  # слева счётчик кадров, справа качество
        self.panel.set_recording_mode()                              # центр на статус, красная точка пульсирует
        self.panel.set_status_labels("RAM: 0.1 GB", "CPU: 0%")        # начальные значения двух меток
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_settings.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.start_session()

    def _on_closed_by_user(self):
        self.cancel_requested.emit()

    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage}%")


''' Окно записи звука. '''
class AudioCaptureSession(CaptureSession):

    start_requested = Signal()
    stop_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, controller):
        super().__init__(
            controller=controller,
            title="запись звука",
        )

        self.panel.btn_start.clicked.connect(self._on_start_clicked)   # старт записи звука
        self.panel.btn_stop.clicked.connect(self._on_stop_clicked)     # стоп записи звука
        self.cpu_update_requested.connect(self._update_cpu)            # обновление CPU
        self.ram_timer.timeout.connect(self._request_size_update)      # обновление размера файла раз в секунду

    def _on_start_clicked(self):
        self.start_requested.emit()

    def _on_stop_clicked(self):
        self.stop_requested.emit()

    def create_settings_dialog(self, parent):
        return AudioSettingsDialog(parent, self.controller)

    def set_recording_mode(self):
        """Application сообщает, что запись звука началась."""
        self.panel.show_audio_info()                                   # только индикатор в чёрное поле
        self.panel.set_recording_mode()                                # центр на статус, красная точка пульсирует
        self.panel.set_status_labels("Размер: 0.1 GB", "CPU: 0%")       # размер файла и CPU над таймером
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.start_session()

    def set_audio_level(self, level: float):
        """Обновить индикатор уровня сигнала в чёрном поле."""
        if self.panel:
            try:
                self.panel.set_audio_level(level)              # пробрасываем в AudioLevelIndicator
            except RuntimeError:
                pass

    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage}%")

''' Окно настроек записи видео. Record '''
class RecordSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        self.setup_localization()

    def build_content(self, layout):
        self.content_widget.setMinimumWidth(480)
        # Сохраняем строки как атрибуты
        self.export_filename_input = ExportFilenameInput(
            initial=self.controller.get_export_filename(),
            placeholder="recording_m.d_hh.mm.ss",
        )
        self.row_filename = SettingRow("", self.export_filename_input, align=Qt.AlignRight)
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

        self.audio_sources = AudioSourceSelector(initial=self.controller.get_audio_sources())
        self.audio_sources.valueChanged.connect(self.controller.set_audio_sources)
        self.row_audio_sources = SettingRow("", self.audio_sources)
        layout.addWidget(self.row_audio_sources)

        # Пауза перед стартом
        self.start_delay_input = NullableSpinBox()
        self.start_delay_input.setRange(0, 30)
        self.start_delay_input.setValue(self.controller.get_start_delay())
        self.start_delay_input.setFixedWidth(70)
        self.start_delay_input.setAlignment(Qt.AlignCenter)
        self.row_start_delay = SettingRow("", self.start_delay_input, align=Qt.AlignRight)

        # Таймер
        self.timer_input = TimerInput(align=Qt.AlignRight)
        seconds = self.controller.get_record_timer()
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_input.hours.setValue(h)
        self.timer_input.minutes.setValue(m)
        self.timer_input.seconds.setValue(s)
        self.row_timer = SettingRow("", self.timer_input, align=Qt.AlignRight)

        # Always on top
        self.always_on_top_setting = AlwaysOnTopSetting(self.controller)
        self.row_always_on_top = SettingRow("", self.always_on_top_setting)

        self.show_frame_setting = ShowRecordingFrameSetting(self.controller)
        self.row_show_frame = SettingRow("", self.show_frame_setting)

        # Секция «Дополнительно»
        self.adv_label = self._make_section_label("Дополнительно")
        layout.addWidget(self.adv_label)
        layout.addWidget(self.row_start_delay)
        layout.addWidget(self.row_timer)
        layout.addWidget(self.row_always_on_top)
        layout.addWidget(self.row_show_frame)

        

    def _on_audio_enabled_toggled(self, checked: bool):
        self.controller.set_audio_enabled(checked)
        self.audio_sources.setEnabled(checked)               # селектор источников активен, только если звук включён

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
        self.row_start_delay.setText(self.translator.tr("start_delay_setting"))
        self.row_timer.setText(self.translator.tr("stop_after_setting"))
        self.row_always_on_top.setText(self.translator.tr("always_on_top"))
        self.row_show_frame.setText(self.translator.tr("show_recording_frame"))
        self.adv_label.setText(self.translator.tr("additional"))
        self.row_audio_sources.setText(self.translator.tr("audio_sources_setting"))

    def apply_settings(self) -> bool:
        self.controller.set_record_fps(self.fps_switcher.get())
        self.controller.set_record_quality(self.quality_switcher.get())
        self.controller.set_start_delay(self.start_delay_input.value())
        self.controller.set_record_timer(self.timer_input.get_seconds())
        self.controller.set_always_on_top(self.always_on_top_setting.isChecked())
        self.controller.set_show_recording_frame(self.show_frame_setting.isChecked())
        self.controller.save_settings()
        return True
    
''' Окно настроек серийного захвата. '''
class ScreenSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        self.setup_localization() # Подключаем локализацию ПОСЛЕ создания UI

    def build_content(self, layout):
        self.content_widget.setMinimumWidth(480)
        
        # Сохраняем строки как атрибуты
        self.export_filename_input = ExportFilenameInput(
            initial=self.controller.get_export_filename(),
            placeholder="recording_m.d_hh.mm.ss",
        )
        self.row_filename = SettingRow("", self.export_filename_input, align=Qt.AlignRight)
        layout.addWidget(self.row_filename)
        self.export_filename_input.valueChanged.connect(self.controller.set_export_filename)

        # Capture per minute
        self.capture_input = CapturePerMinuteInput(initial=self.controller.get_screen_fps())
        self.row_capture = SettingRow("", self.capture_input)
        layout.addWidget(self.row_capture)

        # 🆕 Пауза перед стартом
        self.start_delay_input = NullableSpinBox()
        self.start_delay_input.setRange(0, 30)
        self.start_delay_input.setValue(self.controller.get_start_delay())
        self.start_delay_input.setFixedWidth(70)
        self.start_delay_input.setAlignment(Qt.AlignCenter)
        self.row_start_delay = SettingRow("", self.start_delay_input, align=Qt.AlignRight)

        # Таймер
        self.timer_input = TimerInput(align=Qt.AlignRight)
        seconds = self.controller.get_screen_timer()
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_input.hours.setValue(h)
        self.timer_input.minutes.setValue(m)
        self.timer_input.seconds.setValue(s)
        self.row_timer = SettingRow("", self.timer_input, align=Qt.AlignRight)

        # Always on top
        self.always_on_top_setting = AlwaysOnTopSetting(self.controller)
        self.row_always_on_top = SettingRow("", self.always_on_top_setting)

        self.show_frame_setting = ShowRecordingFrameSetting(self.controller)
        self.row_show_frame = SettingRow("", self.show_frame_setting)

        # Секция «Дополнительно»
        self.adv_label = self._make_section_label("Дополнительно")
        layout.addWidget(self.adv_label)
        layout.addWidget(self.row_start_delay)
        layout.addWidget(self.row_timer)
        layout.addWidget(self.row_always_on_top)
        layout.addWidget(self.row_show_frame)

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
        self.row_always_on_top.setText(self.translator.tr("always_on_top"))
        self.row_show_frame.setText(self.translator.tr("show_recording_frame"))
        self.adv_label.setText(self.translator.tr("additional"))

    def apply_settings(self):
        self.controller.set_screen_fps(self.capture_input.get())
        self.controller.set_start_delay(self.start_delay_input.value())
        self.controller.set_screen_timer(self.timer_input.get_seconds())
        self.controller.set_always_on_top(self.always_on_top_setting.isChecked())
        self.controller.set_show_recording_frame(self.show_frame_setting.isChecked())
        self.controller.save_settings()
        return True



''' Окно настроек записи звука. '''
class AudioSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        self.setup_localization()                                       # локализация после построения UI

    def build_content(self, layout):
        self.content_widget.setMinimumWidth(480)                        # ширина контента как в других диалогах
        self.export_filename_input = ExportFilenameInput(
            initial=self.controller.get_audio_export_filename(),        # имя файла аудио-записи из настроек
            placeholder="audio_m.d_hh.mm.ss",                    # плейсхолдер с форматом даты для аудио
        )
        self.row_filename = SettingRow("", self.export_filename_input, align=Qt.AlignRight)
        layout.addWidget(self.row_filename)
        self.export_filename_input.valueChanged.connect(self.controller.set_audio_export_filename)

        self.source_selector = AudioSourceSelector(                     # выбор источников звука (чекбоксы)
            initial=self.controller.get_audio_sources()
        )
        self.source_selector.valueChanged.connect(self.controller.set_audio_sources)
        self.row_sources = SettingRow("", self.source_selector)
        layout.addWidget(self.row_sources)

        self.rate_selector = SampleRateSelector(
            initial=self.controller.get_audio_sample_rate()
        )
        self.rate_selector.valueChanged.connect(self.controller.set_audio_sample_rate)
        self.row_rate = SettingRow("", self.rate_selector)
        layout.addWidget(self.row_rate)

        self.channels_selector = ChannelsSelector(
            initial=self.controller.get_audio_channels()
        )
        self.channels_selector.valueChanged.connect(self.controller.set_audio_channels)
        self.row_channels = SettingRow("", self.channels_selector)
        layout.addWidget(self.row_channels)

        self.timer_input = TimerInput(align=Qt.AlignRight)
        seconds = self.controller.get_audio_timer()                     # сохранённый таймер для аудио-сессии
        h = seconds // 3600
        m = (seconds % 3600) // 60
        s = seconds % 60
        self.timer_input.hours.setValue(h)
        self.timer_input.minutes.setValue(m)
        self.timer_input.seconds.setValue(s)
        self.row_timer = SettingRow("", self.timer_input, align=Qt.AlignRight)

        # Пауза перед стартом (новое для аудио)
        self.start_delay_input = NullableSpinBox()
        self.start_delay_input.setRange(0, 30)
        self.start_delay_input.setValue(self.controller.get_start_delay())
        self.start_delay_input.setFixedWidth(70)
        self.start_delay_input.setAlignment(Qt.AlignCenter)
        self.row_start_delay = SettingRow("", self.start_delay_input, align=Qt.AlignRight)

        # Always on top
        self.always_on_top_setting = AlwaysOnTopSetting(self.controller)
        self.row_always_on_top = SettingRow("", self.always_on_top_setting)

        self.show_frame_setting = ShowRecordingFrameSetting(self.controller)
        self.row_show_frame = SettingRow("", self.show_frame_setting)

        # Секция «Дополнительно»
        self.adv_label = self._make_section_label("Дополнительно")
        layout.addWidget(self.adv_label)
        layout.addWidget(self.row_start_delay)
        layout.addWidget(self.row_timer)
        layout.addWidget(self.row_always_on_top)
        layout.addWidget(self.row_show_frame)

    def setup_localization(self):
        self.translator = self.controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.translator.tr("audio_settings_title"))
        self.row_filename.setText(self.translator.tr("filename_setting"))
        self.row_sources.setText(self.translator.tr("audio_sources_setting"))
        self.row_rate.setText(self.translator.tr("audio_sample_rate_setting"))
        self.row_channels.setText(self.translator.tr("audio_channels_setting"))
        self.row_start_delay.setText(self.translator.tr("start_delay_setting"))
        self.row_timer.setText(self.translator.tr("stop_after_setting"))
        self.row_always_on_top.setText(self.translator.tr("always_on_top"))
        self.row_show_frame.setText(self.translator.tr("show_recording_frame"))
        self.adv_label.setText(self.translator.tr("additional"))

    def apply_settings(self):
        self.controller.set_audio_timer(self.timer_input.get_seconds())
        self.controller.set_start_delay(self.start_delay_input.value())
        self.controller.set_always_on_top(self.always_on_top_setting.isChecked())
        self.controller.set_show_recording_frame(self.show_frame_setting.isChecked())
        self.controller.save_settings()
        return True