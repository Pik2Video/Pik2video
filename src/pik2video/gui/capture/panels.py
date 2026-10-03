# src/pik2video/gui/capture/panels.py

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from src.pik2video.gui.common.blink_style import (
    LABEL_ALPHA_BRIGHT,
    LABEL_ALPHA_DIM,
    lerp_alpha,
)
from src.pik2video.gui.common.tooltip import TooltipButton


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

        # обновляем всплывающие подсказки у кнопок
        self.btn_back.set_tooltip(self.translator.tr("back_tooltip"))

        # обновляем подсказку у кнопки информации
        self.btn_info.set_tooltip(self.translator.tr("info_tooltip"))

        # обновляем подсказку у кнопки предварительных настроек
        self.btn_settings.set_tooltip(self.translator.tr("capture_settings_tooltip"))

        
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
        
        # Общий контейнер строки (кнопка назад + чёрное поле + 📄)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(2, 2, 2, 0)
        top_row.setSpacing(2)

        # Кнопка НАЗАД (вне чёрного поля, слева)
        self.btn_back = TooltipButton("⬅️")
        self.btn_back.setFixedSize(26, 24)
        self.btn_back.setStyleSheet("font-size:11px; background:#282828; border:1px solid #555; border-radius:4px;")


        # Чёрное поле (три колонки)
        self.top_widget = QWidget()
        self.top_widget.setStyleSheet("background:#1f1f1f; border-radius:4px;")

        info_layout = QHBoxLayout(self.top_widget)
        info_layout.setContentsMargins(35, 4, 25, 4)

        # Левый текст (фиксированный, не растягивается)
        self.left_label = QLabel("")
        self.left_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        self.left_label.setAlignment(Qt.AlignLeft)
        self.left_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.left_label.hide()  # скрываем по умолчанию

        # Центральный текст (растягивается, забирает всё свободное место)
        self.center_label = QLabel("")
        self.center_label.setStyleSheet("color:white; font-size: 12px;")
        self.center_label.setAlignment(Qt.AlignCenter)
        self.center_label.setWordWrap(False)  # НЕ переносить на новую строку
        self.center_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        # Правый текст (фиксированный)
        self.right_label = QLabel("")
        self.right_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        self.right_label.setAlignment(Qt.AlignRight)
        self.right_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)
        self.right_label.hide()  # скрываем по умолчанию

        # Добавляем с коэффициентами растяжения (stretch)
        info_layout.addWidget(self.left_label, 0)      # 0 = НЕ растягивается
        info_layout.addWidget(self.center_label, 1)    # 1 = растягивается (забирает всё лишнее)
        info_layout.addWidget(self.right_label, 0)     # 0 = НЕ растягивается

        # Кнопка 📄 (вне чёрного поля, справа)
        self.btn_info = TooltipButton("📄")
        self.btn_info.setFixedSize(26, 24)
        self.btn_info.setStyleSheet("font-size:11px; background:#282828; border:1px solid #555; border-radius:4px;")
        self.btn_info.setEnabled(False)  # пока не используется

        top_row.addWidget(self.btn_back)
        top_row.addWidget(self.top_widget, stretch=1)  # чёрное поле растягивается
        top_row.addWidget(self.btn_info)

        root.addLayout(top_row)

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
        self.center_stack.setFixedHeight(self.BUTTON_HEIGHT * 1)  # увеличена высота для двух строк

        # Страница 0 — SETTINGS
        settings_page = QWidget()
        settings_layout = QHBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)

        # Добавляем растяжку сверху и снизу для центрирования
        settings_layout.addStretch()

        h_layout = QHBoxLayout()
        h_layout.addStretch()

        self.btn_settings = TooltipButton("⚙️")
        self.btn_settings.setFixedSize(self.SETTINGS_WIDTH, self.BUTTON_HEIGHT)
        self.btn_settings.setStyleSheet("font-size:13px;")

        h_layout.addWidget(self.btn_settings)
        h_layout.addStretch()

        settings_layout.addStretch()
        settings_layout.addWidget(self.btn_settings)
        settings_layout.addStretch()

        self.center_stack.addWidget(settings_page)

        # Страница 1 — RECORDING STATUS (RAM и CPU, каждый в своей строке)
        self.status_page = QWidget()
        status_layout = QHBoxLayout(self.status_page)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        status_layout.addStretch()

        status_container = QWidget()
        status_container.setFixedSize(self.STATUS_WIDTH, self.BUTTON_HEIGHT * 1)  # высота под две строки

        status_container_layout = QVBoxLayout(status_container)
        status_container_layout.setContentsMargins(4, 2, 4, 2)
        status_container_layout.setSpacing(4)

        # ========== СТРОКА 1: RAM ==========
        ram_row = QHBoxLayout()
        ram_row.setContentsMargins(0, 0, 0, 0)

        self.ram_label = QLabel("RAM: 0 KB")
        self.ram_label.setStyleSheet("color:white; font-size:11px; font-weight:500;")
        self.ram_label.setAlignment(Qt.AlignCenter)

        ram_row.addStretch()
        ram_row.addWidget(self.ram_label)
        ram_row.addStretch()

        # ========== СТРОКА 2: CPU ==========
        cpu_row = QHBoxLayout()
        cpu_row.setContentsMargins(0, 0, 0, 0)

        self.cpu_label = QLabel("CPU: 0 %")
        self.cpu_label.setStyleSheet("color:white; font-size:11px; font-weight:500;")
        self.cpu_label.setAlignment(Qt.AlignCenter)

        cpu_row.addStretch()
        cpu_row.addWidget(self.cpu_label)
        cpu_row.addStretch()

        status_container_layout.addLayout(ram_row)
        status_container_layout.addLayout(cpu_row)

        status_layout.addWidget(status_container)
        status_layout.addStretch()

        self.center_stack.addWidget(self.status_page)

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
        """Переключить на страницу статуса (RAM/CPU)"""
        if hasattr(self, 'status_page') and self.status_page:
            self.center_stack.setCurrentWidget(self.status_page)
        else:
            self.center_stack.setCurrentIndex(1)  # fallback

    # 🆕 НОВЫЙ МЕТОД — вставить здесь
    def set_waiting_mode(self):
        """Показать режим ожидания (отсчёт перед стартом)"""
        self.center_stack.setCurrentIndex(1)  # страница статуса
        self.ram_label.setText("Ожидание...")
        #self.time_label.setText("")

    # ─────────────────────────────────────────
    # Обновление текста верхней панели
    # ─────────────────────────────────────────
    def set_info_text(self, text: str):
        self.center_label.setText(text)

    def set_info_blink_phase(self, phase: float):
        """Установить фазу мигания текста в чёрном поле (0.0 … 1.0)."""
        alpha = lerp_alpha(phase, LABEL_ALPHA_DIM, LABEL_ALPHA_BRIGHT)
        self.center_label.setStyleSheet(
            f"color: rgba(255, 255, 255, {alpha}); font-size: 12px;"
        )
    def set_left_text(self, text: str):
        """Установить текст в левой части (для сообщения ← назад)"""
        if text:
            self.left_label.setText(text)
            self.left_label.show()
        else:
            self.left_label.hide()
            self.left_label.setText("")

    def set_right_text(self, text: str):
        """Установить текст в правой части (для сообщения информация →)"""
        if text:
            self.right_label.setText(text)
            self.right_label.show()
        else:
            self.right_label.hide()
            self.right_label.setText("")

    def clear_side_texts(self):
        """Очистить боковые тексты (при обычных сообщениях)"""
        self.left_label.hide()
        self.right_label.hide()
        self.left_label.setText("")
        self.right_label.setText("")

    
    # ─────────────────────────────────────────
    # Управление режимом RECORDING (чёрное поле)
    # ─────────────────────────────────────────

    def set_recording_video_mode(self):
        """
        Режим записи VIDEO:
        Левый блок: "запись ..."
        Правый блок: "TIME: 00:00:00"
        """
        # Очищаем центр (там ничего не нужно)
        self.center_label.setText("")
        
        # Показываем левый и правый блоки
        self.left_label.show()
        self.right_label.show()
        
        # Устанавливаем стили
        self.left_label.setStyleSheet("color: #8B0000; font-size: 15px;")
        self.right_label.setStyleSheet("color: white; font-size: 12px; padding-top: 2px;")
        
        # Начальные значения (обновляются через update_* методы)
        self.left_label.setText("запись")
        self.right_label.setText("TIME: 00:00:00")

    def set_recording_screen_mode(self):
        """
        Режим записи SCREEN:
        Левый блок: "0 SHOTS"
        Центр: "запись ..."
        Правый блок: "TIME: 00:00:00"
        """
        # Показываем все три блока
        self.left_label.show()
        self.center_label.show()
        self.right_label.show()
        
        # Устанавливаем стили
        self.left_label.setStyleSheet("color: #C0C0C0; font-size: 14px;")
        self.center_label.setStyleSheet("color: #8B0000; font-size: 14px;")
        self.right_label.setStyleSheet("color: white; font-size: 13px; padding-top: 2px;")
        
        # Начальные значения
        self.left_label.setText("0 SHOTS")
        self.center_label.setText("запись")
        self.right_label.setText("TIME: 00:00:00")

    def set_recording_idle_mode(self):
        """
        Вернуть чёрное поле в режим PREPARING (для подсказок)
        """
        # Скрываем боковые блоки
        self.left_label.hide()
        self.right_label.hide()
        
        # Центр будет заполняться через set_info_text
        self.center_label.show()
        self.center_label.setText("")  # очищаем на всякий случай

    # Обновление значений во время записи
    def update_recording_time(self, time_text: str):
        """Обновить таймер в правом блоке"""
        self.right_label.setText(time_text)

    def update_recording_shots(self, shots_text: str):
        """Обновить счётчик SHOTS в левом блоке (для screen)"""
        self.left_label.setText(shots_text)

    def update_recording_dots(self, dots_text: str):
        """Обновить анимацию точек в слове 'запись'"""
        # Для VIDEO — левый блок, для SCREEN — центр
        if self.left_label.isVisible() and "запись" in self.left_label.text():
            self.left_label.setText(dots_text)
        elif self.center_label.isVisible() and "запись" in self.center_label.text():
            self.center_label.setText(dots_text)

    def reset_recording_mode(self):
        """Сброс перед переходом в REVIEW (очищаем всё)"""
        self.left_label.setText("")
        self.right_label.setText("")
        self.center_label.setText("")
        self.left_label.hide()
        self.right_label.hide()
        self.center_label.show()
