# src/pik2video/gui/overlays.py

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget
)
from PySide6.QtCore import Qt


class CapturePanel(QWidget):
    """
    Общая UI-панель для Video и Screen сценария.

    PREPARING  → по центру кнопка настроек
    RECORDING  → по центру двухстрочный статус (RAM / SHOTS / TIME)
    """
    # Общая высота нижнего блока управления
    BOTTOM_HEIGHT = 35

    # Размеры кнопок START / STOP
    BUTTON_WIDTH = 130     
    BUTTON_HEIGHT = 27    

    # Размер центральных элементов
    SETTINGS_WIDTH = 60
    STATUS_WIDTH = 130

    BLOCK_VERTICAL_MARGIN = 4

    def __init__(self, parent, controller=None):
        super().__init__(parent)
        self.controller = controller
        self.translator = controller.get_translator() if controller else None
        self._build_ui()
        
        # Подключаем локализацию, если есть controller
        if self.translator:
            self.setup_localization()
    
    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет тексты на кнопках при смене языка"""
        self.btn_start.setText(self.translator.tr("start_button"))
        self.btn_stop.setText(self.translator.tr("stop_button"))
        # Метки TIME, RAM, SHOTS НЕ переводим - оставляем на английском
    
    # ─────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────
    def _build_ui(self):

        # Корневой layout всей панели (вертикальный)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ==========================================================
        # Верхняя информационная зона
        # ==========================================================

        self.top_widget = QWidget()
        self.top_widget.setStyleSheet("background:#1f1f1f;")

        top_layout = QHBoxLayout(self.top_widget)
        top_layout.setContentsMargins(5, 5, 5, 5)

        # Кнопка НАЗАД
        self.btn_back = QPushButton("⬅️")
        self.btn_back.setFixedSize(30, 22)
        self.btn_back.setStyleSheet("font-size:12px;")

        # Текст по центру
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color:white; font-size:10px;")
        self.info_label.setAlignment(Qt.AlignCenter)

        top_layout.addWidget(self.btn_back)
        top_layout.addStretch()
        top_layout.addWidget(self.info_label)
        top_layout.addStretch()
        top_layout.addSpacing(30)

        top_layout.setContentsMargins(5, 5, 5, 5)

        root.addWidget(self.top_widget)

        # ==========================================================
        # Нижний блок управления
        # ==========================================================
        bottom_widget = QWidget()
        bottom_widget.setFixedHeight(self.BOTTOM_HEIGHT)
        bottom_widget.setStyleSheet("background:#282828;")

        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(8, self.BLOCK_VERTICAL_MARGIN, 8, self.BLOCK_VERTICAL_MARGIN)
        bottom_layout.setSpacing(10)

        # Кнопка START (текст будет установлен в retranslate_ui)
        self.btn_start = QPushButton("")
        self.btn_start.setFixedSize(self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
        self.btn_start.setStyleSheet("font-size:15px;")

        # Кнопка STOP (текст будет установлен в retranslate_ui)
        self.btn_stop = QPushButton("")
        self.btn_stop.setFixedSize(self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
        self.btn_stop.setStyleSheet("font-size:15px;")
        self.btn_stop.setEnabled(False)

        # ==========================================================
        # Центральный стек
        # ==========================================================

        self.center_stack = QStackedWidget()
        self.center_stack.setFixedHeight(self.BUTTON_HEIGHT)

        # Страница 0 — SETTINGS
        settings_page = QWidget()
        settings_layout = QHBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)

        self.btn_settings = QPushButton("⚙️")
        self.btn_settings.setFixedSize(self.SETTINGS_WIDTH, self.BUTTON_HEIGHT)
        self.btn_settings.setStyleSheet("font-size:13px;")

        settings_layout.addStretch()
        settings_layout.addWidget(self.btn_settings)
        settings_layout.addStretch()

        self.center_stack.addWidget(settings_page)

        # Страница 1 — RECORDING STATUS
        status_page = QWidget()
        status_layout = QHBoxLayout(status_page)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        status_layout.addStretch()

        status_container = QWidget()
        status_container.setFixedSize(self.STATUS_WIDTH, self.BUTTON_HEIGHT)

        status_container_layout = QVBoxLayout(status_container)
        status_container_layout.setContentsMargins(4, 2, 4, 2)
        status_container_layout.setSpacing(0)

        # Верхняя строка (RAM + SHOTS) - НЕ ПЕРЕВОДИМ
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(6)

        self.ram_label = QLabel("RAM: 0 KB")
        self.ram_label.setStyleSheet("color:white; font-size:9px;")

        self.counter_label = QLabel("0 SHOTS")
        self.counter_label.setStyleSheet("color:white; font-size:9px;")
        self.counter_label.setVisible(False)

        top_row.addWidget(self.ram_label)
        top_row.addStretch()
        top_row.addWidget(self.counter_label)

        # Нижняя строка (TIME) - НЕ ПЕРЕВОДИМ
        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)

        self.time_label = QLabel("TIME: 00:00:00")
        self.time_label.setStyleSheet("color:white; font-size:9px;")
        self.time_label.setAlignment(Qt.AlignCenter)

        bottom_row.addStretch()
        bottom_row.addWidget(self.time_label)
        bottom_row.addStretch()

        status_container_layout.addLayout(top_row)
        status_container_layout.addLayout(bottom_row)

        status_layout.addWidget(status_container)
        status_layout.addStretch()

        self.center_stack.addWidget(status_page)

        # ==========================================================
        # Сборка нижнего layout
        # ==========================================================

        bottom_layout.addWidget(self.btn_start)
        bottom_layout.addWidget(self.center_stack, 1)
        bottom_layout.addWidget(self.btn_stop)

        root.addWidget(bottom_widget)

        # По умолчанию активен режим PREPARING
        self.set_preparing_mode()

    # ─────────────────────────────────────────
    # Режимы
    # ─────────────────────────────────────────
    def set_preparing_mode(self):
        self.center_stack.setCurrentIndex(0)

    def set_recording_mode(self):
        self.center_stack.setCurrentIndex(1)

    # ─────────────────────────────────────────
    # Обновление текста верхней панели
    # ─────────────────────────────────────────
    def set_info_text(self, text: str):
        self.info_label.setText(text)