# src/pik2video/gui/windows.py

import logging

from PySide6.QtWidgets import (
    QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QMainWindow, QComboBox, QCheckBox, QSpinBox, QMessageBox)

from PySide6.QtCore import Qt, Signal, QEvent


from .components_settings.setting_row import SettingRow
from .components_settings.global_settings import (
    LanguageSetting,
    TextSizeSetting,
    TooltipsSetting,
    AlwaysOnTopSetting, # импорт нового виджета
)

from .utils import center_to_parent, keep_window_inside_screen
from .base import SettingsDialog

from .sessions import VideoCaptureSession, ScreenCaptureSession
from .sessions import VideoFinalizeWidget, ScreenFinalizeWidget

logger = logging.getLogger(__name__)

''' ГЛАВНОЕ ОКНО '''
class MainWindow(QMainWindow):
    # Сигналы для общения с Application
    start_video_requested = Signal()
    start_screen_requested = Signal()
    settings_requested = Signal()

    def __init__(self, controller):
        super().__init__()

        self.controller = controller
        self.translator = controller.get_translator()

        # ───── БАЗОВЫЕ НАСТРОЙКИ ОКНА ─────
        self.setWindowFlag(Qt.Window)
        self.setAttribute(Qt.WA_QuitOnClose, True)

        self.setWindowTitle("главное окно")
        self.setFixedSize(430, 80)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #282828;
            }

            QPushButton {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 5px;
                color: #e6e6e6;
                padding: 0px 0px;
            }

            QPushButton:hover {
                background-color: #4a4a4a;
            }

            QPushButton:pressed {
                background-color: #2a2a2a;
            }
            QPushButton:disabled {
                color: rgba(255, 255, 255, 80);
                background-color: #2a2a2a;
            }
        """)

        
        # ───── СОЗДАЁМ CENTRAL + ROOT LAYOUT ─────
        central = QWidget()
        self.setCentralWidget(central)

        

        # 🆕 Фоновое изображение
        import sys
        from pathlib import Path

        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).resolve().parents[3]

        bg_path = base_path / "resources" / "backgrounds" / "main_bg.png"

        

        self.root_layout = QVBoxLayout(central)
        self.root_layout.setContentsMargins(1, 1, 1, 1)

        # ───── ГЛАВНЫЙ КОНТЕЙНЕР (СЮДА МЕНЯЕМ ЭКРАНЫ) ─────
        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(0, 0, 0, 0)

        self.root_layout.addWidget(self.container)

        # ───── текущая активная сессия ─────
        self.current_session = None

        # ───── ПОКАЗЫВАЕМ ПЕРВЫЙ ЭКРАН ─────
        self.show_idle_screen()

    # =========================================================
    # 🔴 ПЕРЕКЛЮЧЕНИЕ ЭКРАНОВ
    # =========================================================
    def set_screen(self, widget: QWidget):
        """Удаляет старый экран и ставит новый"""
        # очищаем контейнер
        while self.container_layout.count():
            item = self.container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # добавляем новый экран
        self.container_layout.addWidget(widget)

        # 🆕 Убедимся, что окно не вылезает за пределы экрана
        keep_window_inside_screen(self, margin=20)

    # =========================================================
    # 🟢 IDLE ЭКРАН (главный)
    # =========================================================
    def show_idle_screen(self):
        widget = QWidget()

        # 🆕 Фон только для главного экрана
        import sys
        from pathlib import Path
        if getattr(sys, 'frozen', False):
            base_path = Path(sys._MEIPASS)
        else:
            base_path = Path(__file__).resolve().parents[3]
        bg_path = base_path / "resources" / "backgrounds" / "main_bg.png"
        if bg_path.exists():
            widget.setObjectName("idleWidget")
            widget.setStyleSheet(f"""
                QWidget#idleWidget {{
                    background-image: url({bg_path});
                    background-repeat: no-repeat;
                }}
            """)
        
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(10, 7, 10, 7)
        main_layout.setSpacing(1)

        W = 170   # ширина широких кнопок
        S = 30    # ширина маленьких кнопок

        # СТРОКА 1 (прижата вправо)
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        #row1.addStretch()

        self.btn_editor = QPushButton("🔏    редактор")
        self.btn_editor.setFixedSize(W, 22)
        self.btn_editor.setEnabled(False)

        self.btn_record = QPushButton("запись видео")
        self.btn_record.setFixedSize(W, 22)
        self.btn_record.clicked.connect(self.start_video_requested.emit)

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(S, 22)
        self.btn_settings.clicked.connect(self.settings_requested.emit)

        row1.addWidget(self.btn_editor)
        row1.addWidget(self.btn_record)
        row1.addStretch()          # 🆕 пустота между кнопками и ⚙️
        row1.addWidget(self.btn_settings)

        # СТРОКА 2 (прижата влево)
        row2 = QHBoxLayout()
        row2.setSpacing(4)

        self.btn_notify = QPushButton("📄")
        self.btn_notify.setFixedSize(S, 22)

        self.btn_screen = QPushButton("screen запись")
        self.btn_screen.setFixedSize(W, 22)
        self.btn_screen.clicked.connect(self.start_screen_requested.emit)

        self.btn_stream = QPushButton("стрим     🔏")
        self.btn_stream.setFixedSize(W, 22)
        self.btn_stream.setEnabled(False)

        row2.addWidget(self.btn_notify)
        row2.addStretch()          # 🆕 пустота между 📄 и кнопками
        row2.addWidget(self.btn_screen)
        row2.addWidget(self.btn_stream)

        main_layout.addLayout(row1)
        main_layout.addStretch()
        main_layout.addLayout(row2)

        self.set_screen(widget)
        self.current_session = None
        self.setFixedSize(430,80)
        self.setup_localization()


    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет все тексты при смене языка"""
        logger.debug(f"retranslate_ui вызван, язык: {self.translator.get_current_language()}")
        self.setWindowTitle(self.translator.tr("main_window_title"))
        
        # Обновляем текст на кнопках, если они уже созданы
        if hasattr(self, 'btn_record'):
            self.btn_record.setText(self.translator.tr("record_video"))
            self.btn_screen.setText(self.translator.tr("screen_capture"))
            self.btn_settings.setToolTip(self.translator.tr("settings_tooltip"))
            self.btn_notify.setToolTip(self.translator.tr("notifications_tooltip"))

    # =========================================================
    # 🎬 ВИДЕО СЕССИЯ (встраивается в MainWindow)
    # =========================================================
    def show_video_session(self, controller):
        """Показать виджет видео записи внутри MainWindow"""
        from src.pik2video.gui.sessions import VideoCaptureSession

        session = VideoCaptureSession(controller)
        session.back_requested.connect(controller.cancel_session)
        self.current_session = session

        session.start_requested.connect(controller.start_recording)
        session.stop_requested.connect(controller.stop_recording)
        session.cancel_requested.connect(controller.cancel_session)

        session.time_update_requested.connect(controller.update_time)
        session.ram_update_requested.connect(controller.update_ram)
        session.shots_update_requested.connect(controller.update_shots)

        controller.time_updated.connect(session.set_time)
        controller.ram_updated.connect(session.set_ram)
        controller.shots_updated.connect(session.set_shots)

        self.set_screen(session)
        self.setFixedSize(430, 80)  # Размер под виджет

    # =========================================================
    # 🖥️ SCREEN СЕССИЯ (встраивается в MainWindow)
    # =========================================================
    def show_screen_session(self, controller):
        """Показать виджет screen захвата внутри MainWindow"""
        from src.pik2video.gui.sessions import ScreenCaptureSession

        session = ScreenCaptureSession(controller)
        session.back_requested.connect(controller.cancel_session)
        self.current_session = session

        session.start_requested.connect(controller.start_recording)
        session.stop_requested.connect(controller.stop_recording)
        session.cancel_requested.connect(controller.cancel_session)

        session.time_update_requested.connect(controller.update_time)
        session.ram_update_requested.connect(controller.update_ram)
        session.shots_update_requested.connect(controller.update_shots)

        controller.time_updated.connect(session.set_time)
        controller.ram_updated.connect(session.set_ram)
        controller.shots_updated.connect(session.set_shots)

        self.set_screen(session)
        self.setFixedSize(430, 80)  # Размер под виджет

        keep_window_inside_screen(self)

    # =========================================================
    # 💾 ФИНАЛИЗАЦИЯ ВИДЕО (встраивается в MainWindow)
    # =========================================================
    def show_video_finalize(self, controller):
        """Показать виджет финализации видео внутри MainWindow"""
        from src.pik2video.gui.sessions import VideoFinalizeWidget
        
        finalize = VideoFinalizeWidget(self, controller)
        finalize.finalize_requested.connect(controller.finalize_session)
        finalize.discard_requested.connect(controller.discard_session)
        
        self.current_session = finalize
        self.set_screen(finalize)
        self.setFixedSize(480, 330)  # Размер под виджет

        # 🆕 Убеждаемся, что окно не вылезает за пределы экрана
        keep_window_inside_screen(self)

    # =========================================================
    # 💾 ФИНАЛИЗАЦИЯ SCREEN (встраивается в MainWindow)
    # =========================================================
    def show_screen_finalize(self, controller):
        """Показать виджет финализации screen захвата внутри MainWindow"""
        from src.pik2video.gui.sessions import ScreenFinalizeWidget
        
        finalize = ScreenFinalizeWidget(self, controller)
        finalize.finalize_requested.connect(controller.finalize_session)
        finalize.discard_requested.connect(controller.discard_session)
        
        self.current_session = finalize
        self.set_screen(finalize)
        self.setFixedSize(480, 370)  # Размер под виджет

        keep_window_inside_screen(self, margin=20)


    def closeEvent(self, event):
        """Перехватываем закрытие окна"""
        logger.debug("вызван closeEvent. Текущая сессия завершена")
        
        # Проверяем через controller
        if self.controller.has_active_session_data():
            translator = self.controller.get_translator()
            
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Warning)
            
            if translator:
                msg_box.setWindowTitle(translator.tr("confirm_close_title"))
                msg_box.setText(translator.tr("confirm_close_message"))
                msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg_box.button(QMessageBox.Yes).setText(translator.tr("confirm_delete"))
                msg_box.button(QMessageBox.No).setText(translator.tr("confirm_cancel"))
            else:
                msg_box.setWindowTitle("Подтверждение")
                msg_box.setText("Есть незавершенная запись.\n\nУдалить её без сохранения?")
                msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                msg_box.button(QMessageBox.Yes).setText("Да, удалить")
                msg_box.button(QMessageBox.No).setText("Нет, остаться")
            
            msg_box.setDefaultButton(QMessageBox.No)
            
            result = msg_box.exec()
            
            if result == QMessageBox.Yes:
                logger.debug("Удаляем сессию и закрываемся")

                # Если идет запись - сначала останавливаем
                if self.controller.is_recording():
                    logger.debug("Останавливаем запись...")
                    self.controller.stop_recording()

                self.controller.discard_session()
                event.accept()
            else:
                logger.debug("Закрытие отменено")
                event.ignore()
        else:
            # Нет сессии - просто закрываемся
            event.accept()

    

class AppSettingsDialog(SettingsDialog):
    def __init__(self, parent, controller):
        logger.debug(f"AppSettingsDialog.__init__ - controller type: {type(controller)}")
        
        SettingsDialog.__init__(self, parent, controller, "app_settings")
        
        logger.debug(f"After SettingsDialog init - self.controller type: {type(self.controller)}")
        
        self.setup_localization(controller)
    
    def setup_localization(self, controller):
        logger.debug(f"setup_localization - controller type: {type(controller)}")
        self.controller = controller
        self.translator = controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()  # ← Раскомментируем теперь
    
    def build_content(self, layout: QVBoxLayout):
        self.content_widget.setMinimumWidth(480)

        # ───── создаем компоненты
        self.language_setting = LanguageSetting(self.controller)
        self.text_size_setting = TextSizeSetting(self.controller)
        self.tooltips_setting = TooltipsSetting(self.controller)

        self.always_on_top_setting = AlwaysOnTopSetting(self.controller)  # 🆕


        # ───── добавляем в layout
        self.row_language = SettingRow("", self.language_setting)
        self.row_text_size = SettingRow("", self.text_size_setting)
        self.row_tooltips = SettingRow("", self.tooltips_setting)

        self.row_always_on_top = SettingRow("", self.always_on_top_setting)  # 🆕


        layout.addWidget(self.row_language)
        layout.addWidget(self.row_text_size)
        layout.addWidget(self.row_tooltips)

        layout.addWidget(self.row_always_on_top)  # 🆕
    
    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        self.setWindowTitle(self.translator.tr("settings"))
        
        # Теперь setText работает!
        if hasattr(self, 'row_language'):
            self.row_language.setText(self.translator.tr("language_setting"))
            self.row_text_size.setText(self.translator.tr("text_size_setting"))
            self.row_tooltips.setText(self.translator.tr("show_tooltips"))

            self.row_always_on_top.setText(self.translator.tr("always_on_top"))  # 🆕
    
    def apply_settings(self) -> bool:
        
        old_lang = self.controller.get_language()
        new_lang = self.language_setting.get_value()

        logger.debug(f"old_lang: {old_lang}, new_lang: {new_lang}")
        
        self.controller.set_language(new_lang)
        self.controller.set_text_size(self.text_size_setting.get_value())
        self.controller.set_show_tooltips(self.tooltips_setting.get_value())

        self.controller.set_always_on_top(self.always_on_top_setting.get_value())  # 🆕
        
        
        # СОХРАНЯЕМ НАСТРОЙКИ
        self.controller.save_settings()
        
        # Если язык изменился, обновляем переводчик
        if old_lang != new_lang:
            logger.debug("Язык изменился, обновляем translator")
            lang_code = "ru" if new_lang == "Русский" else "en"
            logger.debug(f"lang_code: {lang_code}")
            self.translator.set_language(lang_code)
        else:
            logger.debug("Язык не изменился")
        
        return True
