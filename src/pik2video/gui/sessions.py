# src/pik2video/gui/sessions.py

from PySide6.QtWidgets import QWidget, QLabel, QApplication, QHBoxLayout, QVBoxLayout, QSpinBox
from PySide6.QtCore import Qt, QTimer, QEvent, Signal
from PySide6.QtGui import QResizeEvent, QCloseEvent

from .components_settings.screen_settings import CapturePerMinuteInput, CleanSpinBox
from .components_settings.setting_row import SettingRow
from .components_settings.record_settings import FpsSwitcher
from .components_settings.common_settings import TimerInput, QualitySwitcher, ExportFilenameInput

from .components_settings.finalize_common_settings import  ExportPathInput, VideoFormatInput, ResolutionSelector, BitrateSelector, RotationSelector  # 🆕
from .components_settings.finalize_screen_settings import PlaybackFpsInput, SpeedPresetSelector

from src.pik2video.gui.dialogs import confirm
from .utils import center_to_parent, fullscreen_geometry, bring_window_to_front, keep_window_inside_screen
from .base import SettingsDialog, FinalizeWidget
from .overlays import CoordinateOverlay
from .panels import CapturePanel


class InfoMessageManager:
    """Управляет анимированными подсказками в режиме PREPARING"""
    
    def __init__(self, panel):  # ← теперь принимаем panel, а не label
        self.panel = panel
        self._timer = QTimer()
        self._timer.timeout.connect(self._next_message)
        self._current_index = 0
        self._dot_count = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._update_dots)
        self._is_animating = False
        
        # Список подсказок: (текст, цвет, шрифт, позиция)
        # позиция: "center", "left", "right"
        self.messages = [
            ("выберите область для захвата", "#a3731f", 14, "center"),
            ("начните зaпись", "#967005", 14, "center"),   # в слове запись буква а на английском !!!
            ("воспользуйтесь настройками", "#a3731f", 14, "center"),
            
            ("информация     →", "#a3731f", 14, "right"),  # будет справа
            ("←     назад", "#dee3e3", 14, "left"),        # будет слева
        ]
    
    def start(self):
        """Запускает ротацию подсказок"""
        self._current_index = 0
        self._show_message(0)
        self._timer.start(6000)
        self._start_dots_animation()
    
    def stop(self):
        """Останавливает анимацию подсказок"""
        self._timer.stop()
        self._dot_timer.stop()
        self._is_animating = False
    
    def _next_message(self):
        """Переход к следующей подсказке"""
        self._current_index = (self._current_index + 1) % len(self.messages)
        self._show_message(self._current_index)
    
    def _show_message(self, index):
        """Показывает конкретную подсказку"""
        text, color, font_size, position = self.messages[index]
        
        self._base_text = text
        self._dot_count = 0
        
        # Очищаем все поля сначала
        self.panel.center_label.setText("")
        self.panel.clear_side_texts()
        
        # Отображаем в зависимости от позиции
        if position == "center":
            self.panel.center_label.setText(text)
            self.panel.center_label.setStyleSheet(f"color: {color}; font-size: {font_size}px;")
        elif position == "left":
            self.panel.set_left_text(text)
            # Меняем цвет для левого текста
            self.panel.left_label.setStyleSheet(f"color: {color}; font-size: {font_size}px;")
        elif position == "right":
            self.panel.set_right_text(text)
            # Меняем цвет для правого текста
            self.panel.right_label.setStyleSheet(f"color: {color}; font-size: {font_size}px;")
    
    def _start_dots_animation(self):
        """Запускает анимацию точек в слове 'запись...'"""
        self._is_animating = True
        self._dot_timer.start(500)
    
    def _update_dots(self):
        """Обновляет анимацию точек"""
        if not self._is_animating:
            return
        
        # Анимация работает ТОЛЬКО для центрального текста
        text = self.panel.center_label.text()
        
        if not text:
            return
        
        if "запись" in text:
            base = text.replace("запись...", "запись").replace("запись..", "запись").replace("запись.", "запись")
            dots = "." * (self._dot_count % 4)
            new_text = base.replace("запись", f"запись{dots}")

            self.panel.center_label.setStyleSheet(f"color: #8B0000; font-size: 14px;")
            self.panel.center_label.setText(new_text)
            self._dot_count += 1
        elif "record" in text.lower():
            base = text.lower().replace("record...", "record").replace("record..", "record").replace("record.", "record")
            dots = "." * (self._dot_count % 4)
            new_text = base.replace("record", f"record{dots}")
            self.panel.center_label.setText(new_text)
            self._dot_count += 1


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

        # 🆕 СОЗДАЁМ МЕНЕДЖЕР ПОДСКАЗОК
        self.message_manager = InfoMessageManager(self.panel)

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
        self.cpu_timer.start(self.RAM_INTERVAL)  # 🆕 добавь запуск CPU таймера

    # ──────── Стоп сессии ────────
    def stop_session(self):
        self._active = False
        self.time_timer.stop()
        self.ram_timer.stop()
        self.cpu_timer.stop()  # 🆕 добавь остановку CPU таймера

    # 🆕 НОВЫЙ МЕТОД — вставить здесь
    def set_waiting_mode(self):
        """Режим ожидания перед стартом записи"""
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        self.panel.set_waiting_mode()
        delay = self.controller.get_start_delay()
        tr = self.controller.get_translator()
        self.panel.info_label.setText(f"{tr.tr('info_waiting')} {delay} {tr.tr('seconds')}")

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

        self.message_manager.start()

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
        # Останавливаем ротацию подсказок
        self.message_manager.stop()
        
        # Переключаем панель в режим записи
        self.panel.set_recording_mode()
        
        # Настраиваем чёрное поле для VIDEO режима
        self.panel.set_recording_video_mode()
        
        # Запускаем анимацию точек
        self._dot_count = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_timer.start(300)
        
        # Управление кнопками
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        
        # Запускаем таймеры обновления
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

        self.message_manager.start()

        
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
        # Останавливаем ротацию подсказок
        self.message_manager.stop()
        
        # Переключаем панель в режим записи
        self.panel.set_recording_mode()
        
        # Настраиваем чёрное поле для SCREEN режима
        self.panel.set_recording_screen_mode()
        
        # Запускаем анимацию точек (теперь в центре)
        self._dot_count = 0
        self._dot_timer = QTimer()
        self._dot_timer.timeout.connect(self._animate_dots)
        self._dot_timer.start(800)
        
        # Управление кнопками
        self.panel.btn_start.setEnabled(False)
        self.panel.btn_settings.setEnabled(False)
        self.panel.btn_stop.setEnabled(True)
        
        # Запускаем таймеры обновления
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


    def _update_cpu(self):
        usage = self.controller.get_cpu_usage()
        self.set_cpu(f"CPU: {usage} %")



''' Окно настроек записи видео. Record '''
class RecordSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        self.controller = controller
        super().__init__(parent, controller, title="")
        
        # Подключаем локализацию ПОСЛЕ создания UI
        self.setup_localization()

    def build_content(self, layout):

        # 🆕 Устанавливаем минимальную ширину (как в глобальных настройках)
        self.content_widget.setMinimumWidth(480)

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
        
        # Подключаем локализацию ПОСЛЕ создания UI
        self.setup_localization()

    def build_content(self, layout):

        # 🆕 Устанавливаем минимальную ширину (как в глобальных настройках)
        self.content_widget.setMinimumWidth(480)
        
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



''' ФИНАЛЬНОЕ ОКНО ВИДЕОЗАПИСИ '''
class VideoFinalizeWidget(FinalizeWidget):
    """Виджет финализации видео (встраивается в MainWindow)"""
    
    def __init__(self, parent, controller):
        super().__init__(parent, controller, title="")
        self.build_content(self.content_layout)

        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        super().retranslate_ui()
        if hasattr(self, 'row_format'):
            self.row_format.setText(self.translator.tr("video_format"))

        if hasattr(self, 'row_resolution'):
            self.row_resolution.setText(self.translator.tr("resolution"))
        if hasattr(self, 'row_bitrate'):
            self.row_bitrate.setText(self.translator.tr("bitrate"))
        if hasattr(self, 'row_rotation'):
            self.row_rotation.setText(self.translator.tr("rotation"))
        
    def build_content(self, layout: QVBoxLayout):

        # 🆕 Формат видео
        self.video_format_selector = VideoFormatInput(
            initial=self.controller.get_video_format()
        )
        self.row_format = SettingRow("", self.video_format_selector)
        layout.addWidget(self.row_format)
        self.video_format_selector.valueChanged.connect(self.controller.set_video_format)



        # 🆕 Разрешение
        self.resolution_selector = ResolutionSelector(
            initial=self.controller.get_resolution()
        )
        self.row_resolution = SettingRow("", self.resolution_selector)
        layout.addWidget(self.row_resolution)
        self.resolution_selector.valueChanged.connect(self.controller.set_resolution)
        
        # 🆕 Битрейт
        self.bitrate_selector = BitrateSelector(
            mode=self.controller.get_bitrate_mode(),
            value=self.controller.get_bitrate_value()
        )
        self.row_bitrate = SettingRow("", self.bitrate_selector)
        layout.addWidget(self.row_bitrate)
        self.bitrate_selector.valueChanged.connect(self.controller.set_bitrate)
        
        # 🆕 Поворот
        self.rotation_selector = RotationSelector(
            initial=self.controller.get_rotation()
        )
        self.row_rotation = SettingRow("", self.rotation_selector)
        layout.addWidget(self.row_rotation)
        self.rotation_selector.valueChanged.connect(self.controller.set_rotation)


        # 🆕 Живые метки (предпросмотр при экспорте)
        preview_widget = QWidget()
        preview_layout = QHBoxLayout(preview_widget)
        preview_layout.setContentsMargins(20, 0, 20, 0)
        preview_layout.setSpacing(10)
        
        self.preview_time = QLabel("TIME: --:--:--")
        self.preview_time.setStyleSheet("color: #ccc; font-size: 12px; background: transparent; border: none;")
        self.preview_time.setAlignment(Qt.AlignCenter)
        
        self.preview_label = QLabel("  значения при экспорте   ")
        self.preview_label.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        
        self.preview_ram = QLabel("RAM: --")
        self.preview_ram.setStyleSheet("color: #ccc; font-size: 12px; background: transparent; border: none;")
        self.preview_ram.setAlignment(Qt.AlignCenter)
        
        
        preview_layout.addWidget(self.preview_time)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_ram)
        
        
        layout.addWidget(preview_widget)


        
        # Путь сохранения
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

        if hasattr(self, 'row_speed'):
            self.row_speed.setText(self.translator.tr("playback_speed"))


        if hasattr(self, 'row_resolution'):
            self.row_resolution.setText(self.translator.tr("resolution"))
        if hasattr(self, 'row_bitrate'):
            self.row_bitrate.setText(self.translator.tr("bitrate"))
        if hasattr(self, 'row_rotation'):
            self.row_rotation.setText(self.translator.tr("rotation"))
        
    def build_content(self, layout: QVBoxLayout):
        # формат видео
        self.video_format_selector = VideoFormatInput(
            initial="GIF"
        )
        self.row_format = SettingRow("", self.video_format_selector)
        layout.addWidget(self.row_format)
        self.video_format_selector.valueChanged.connect(self.controller.set_video_format)


        # 🆕 Разрешение
        self.resolution_selector = ResolutionSelector(
            initial=self.controller.get_resolution()
        )
        self.row_resolution = SettingRow("", self.resolution_selector)
        layout.addWidget(self.row_resolution)
        self.resolution_selector.valueChanged.connect(self.controller.set_resolution)
        
        # 🆕 Битрейт
        self.bitrate_selector = BitrateSelector(
            mode=self.controller.get_bitrate_mode(),
            value=self.controller.get_bitrate_value()
        )
        self.row_bitrate = SettingRow("", self.bitrate_selector)
        layout.addWidget(self.row_bitrate)
        self.bitrate_selector.valueChanged.connect(self.controller.set_bitrate)
        
        # 🆕 Поворот
        self.rotation_selector = RotationSelector(
            initial=self.controller.get_rotation()
        )
        self.row_rotation = SettingRow("", self.rotation_selector)
        layout.addWidget(self.row_rotation)
        self.rotation_selector.valueChanged.connect(self.controller.set_rotation)



        # виджет FPS воспроизведения
        self.playback_fps = PlaybackFpsInput(
            initial=self.controller.get_screen_finalize_fps()
        )
        self.row_fps = SettingRow("", self.playback_fps)
        layout.addWidget(self.row_fps)
        self.playback_fps.valueChanged.connect(self.controller.set_screen_finalize_fps)


        # 🆕 Пресеты скорости (под FPS сборки)
        self.speed_preset = SpeedPresetSelector()
        self.row_speed = SettingRow("", self.speed_preset)
        layout.addWidget(self.row_speed)
        self.speed_preset.valueChanged.connect(self.controller.set_speed_multiplier)


        # 🆕 Живые метки (предпросмотр при экспорте)
        preview_widget = QWidget()
        preview_layout = QHBoxLayout(preview_widget)
        preview_layout.setContentsMargins(20, 0, 20, 0)
        preview_layout.setSpacing(10)
        
        self.preview_time = QLabel("TIME: --:--:--")
        self.preview_time.setStyleSheet("color: #ccc; font-size: 12px; background: transparent; border: none;")
        self.preview_time.setAlignment(Qt.AlignCenter)
        
        self.preview_label = QLabel("  значения при экспорте   ")
        self.preview_label.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        self.preview_label.setAlignment(Qt.AlignCenter)
        
        self.preview_ram = QLabel("RAM: --")
        self.preview_ram.setStyleSheet("color: #ccc; font-size: 12px; background: transparent; border: none;")
        self.preview_ram.setAlignment(Qt.AlignCenter)
        
        
        preview_layout.addWidget(self.preview_time)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_label)
        preview_layout.addStretch()
        preview_layout.addWidget(self.preview_ram)
        
        layout.addWidget(preview_widget)
        

        
        self.export_path_input = ExportPathInput(
            controller=self.controller,
            initial_path=self.controller.get_export_path()
        )
        layout.addWidget(self.export_path_input)
        self.export_path_input.valueChanged.connect(self.controller.set_export_path)