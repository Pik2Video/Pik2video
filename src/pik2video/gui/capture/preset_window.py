from typing import ClassVar

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.pik2video.gui.common.blink_style import (
    PRESET_BG_BRIGHT,
    PRESET_BG_DIM,
    PRESET_BORDER_BRIGHT,
    PRESET_BORDER_DIM,
    lerp_color_hex,
)
from src.pik2video.gui.common.tooltip import TooltipButton


class PresetWindow(QWidget):
    """
    Окно с пресетами области записи.
    Два режима: горизонтальный (сверху) и вертикальный (справа).
    """
    
    preset_selected = Signal(dict, str, str)
    
    PRESETS: ClassVar[list] = [
        ("🖥️", "fullscreen", "Весь экран"),
        ("📱", "mobile", "Мобильный"),
        ("📺", "youtube", "YouTube"),
        ("📸", "instagram", "Instagram"),
        ("🎬", "tiktok", "TikTok"),
        ("🖼️", "4x3", "4:3"),
        ("📺", "16x10", "16:10"),
    ]
    
    PRESET_SIZES: ClassVar[dict] = {
        "fullscreen": (0, 0),
        "mobile": (390, 844),
        "youtube": (1920, 1080),
        "instagram": (1080, 1350),
        "tiktok": (1080, 1920),
        "4x3": (1600, 1200),
        "16x10": (1920, 1200),
    }

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.translator = controller.get_translator()
        self._blink_direction = 1
        self._blink_value = 0.0
        
        # Загружаем сохранённую позицию
        self._is_vertical = controller.get_preset_vertical() if hasattr(controller, 'get_preset_vertical') else False

        self._active_preset_id = "fullscreen"   # ← новый атрибут
        self._blink_phase = 0.0                  # 0.0 = тусклая, 1.0 = яркая
        
        self.setWindowFlags(
            Qt.Window |
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow, True)
        
        self._setup_ui()
        self._apply_styles()
        self._apply_layout()
        self._position_window()
        self._start_blinking()
        
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._apply_button_styles()

    @staticmethod
    def get_default_preset_coords(screen_geometry) -> dict:
        """
        Возвращает координаты пресета по умолчанию (весь экран).
        """
        return {
            "x1": 0,
            "y1": 0,
            "x2": screen_geometry.width(),
            "y2": screen_geometry.height()
        }

    def _setup_ui(self):
        """Создаёт интерфейс"""
        self.container = QWidget()
        self.container.setObjectName("container")
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.addWidget(self.container)
        
        # Внутренний layout контейнера (будет перестраиваться)
        self.inner_layout = QVBoxLayout(self.container)
        self.inner_layout.setContentsMargins(6, 4, 6, 4)
        self.inner_layout.setSpacing(4)
        
        # Кнопка переключения (всегда есть)
        self.btn_toggle = TooltipButton("⟷", "Переключить положение панели")
        self.btn_toggle.setFixedSize(28, 22)
        # self.btn_toggle.setToolTip("Переключить положение панели")
        self.btn_toggle.clicked.connect(self._toggle_layout)
        
        # Мигающий текст (только в горизонтальном режиме)
        self.blink_label = QLabel("УСТАНОВИТЕ ОБЛАСТЬ ДЛЯ ЗАХВАТА ЭКРАНА")
        self.blink_label.setAlignment(Qt.AlignCenter)
        self.blink_label.setWordWrap(True)
        
        # Кнопки пресетов
        self.buttons_layout = QHBoxLayout() if not self._is_vertical else QVBoxLayout()
        self.buttons_layout.setSpacing(8)
        
        self.buttons = {}
        for icon, preset_id, tooltip in self.PRESETS:
            btn = TooltipButton(icon, tooltip)
            btn.setFixedSize(44, 34)
            #btn.setToolTip(tooltip)
            btn.clicked.connect(lambda checked, p=preset_id: self._on_preset_clicked(p))
            self.buttons_layout.addWidget(btn)
            self.buttons[preset_id] = btn

    def _apply_layout(self):
        """Применяет текущий макет (горизонтальный или вертикальный)"""
        # Очищаем inner_layout
        while self.inner_layout.count():
            item = self.inner_layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
            elif item.layout():
                # Удаляем старый layout
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().setParent(None)
        
        if self._is_vertical:
            # Вертикальный режим: кнопка переключения + кнопки пресетов столбиком
            self.setFixedSize(80, 380)
            
            toggle_row = QHBoxLayout()
            toggle_row.addStretch()
            toggle_row.addWidget(self.btn_toggle)
            
            self.inner_layout.addLayout(toggle_row)
            self.inner_layout.addSpacing(4)
            
            # Перестраиваем buttons_layout как вертикальный
            self.buttons_layout = QVBoxLayout()
            self.buttons_layout.setSpacing(6)
            for icon, preset_id, tooltip in self.PRESETS:
                btn = TooltipButton(icon, tooltip)
                btn.setFixedSize(44, 34)
                # btn.setToolTip(tooltip)
                btn.clicked.connect(lambda checked, p=preset_id: self._on_preset_clicked(p))
                self.buttons_layout.addWidget(btn, alignment=Qt.AlignCenter)
                self.buttons[preset_id] = btn
            
            self.inner_layout.addLayout(self.buttons_layout)
            self.blink_label.setVisible(False)
        else:
            # Горизонтальный режим: текст + кнопки в ряд + кнопка переключения
            self.setFixedSize(900, 80)
            
            # Верхняя строка: текст + кнопка переключения
            top_row = QHBoxLayout()
            top_row.addWidget(self.blink_label, stretch=1)
            top_row.addWidget(self.btn_toggle)
            
            self.inner_layout.addLayout(top_row)
            
            # Нижняя строка: кнопки пресетов
            self.buttons_layout = QHBoxLayout()
            self.buttons_layout.setSpacing(40)
            self.buttons_layout.addStretch()
            for icon, preset_id, tooltip in self.PRESETS:
                btn = TooltipButton(icon, tooltip)
                btn.setFixedSize(44, 34)
                #btn.setToolTip(tooltip)
                btn.clicked.connect(lambda checked, p=preset_id: self._on_preset_clicked(p))
                self.buttons_layout.addWidget(btn)
                self.buttons[preset_id] = btn
            self.buttons_layout.addStretch()
            
            self.inner_layout.addLayout(self.buttons_layout)
            self.blink_label.setVisible(True)
        
        self._position_window()
        self._apply_styles()

    def _toggle_layout(self):
        """Переключает между горизонтальным и вертикальным режимом"""
        self._is_vertical = not self._is_vertical
        self._apply_layout()
        # Сохраняем выбор глобально (переживёт перезапуск)
        if hasattr(self.controller, 'set_preset_vertical'):
            self.controller.set_preset_vertical(self._is_vertical)
        if hasattr(self.controller, 'save_settings'):
            self.controller.save_settings()


    def _apply_styles(self):
        """Применяет стили"""
        self.setStyleSheet("""
            QWidget#container {
                background-color: rgba(24, 24, 28, 235);
                border: 1px solid #888899;
            }
            QLabel {
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
                font-size: 18px;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #999;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
        """)

    def _position_window(self):
        """Располагает окно в зависимости от режима"""
        screen = QGuiApplication.primaryScreen().geometry()
        
        if self._is_vertical:
            x = screen.width() - self.width() - 20
            y = (screen.height() - self.height()) // 2
        else:
            x = (screen.width() - self.width()) // 2
            y = 50
        self.move(x, y)

    def _start_blinking(self):
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._blink)
        self._blink_timer.start(60)

    def _blink(self):
        if not self.blink_label.isVisible():
            return
        self._blink_value += 0.03 * self._blink_direction
        if self._blink_value >= 1.0:
            self._blink_value = 1.0
            self._blink_direction = -1
        elif self._blink_value <= 0.0:
            self._blink_value = 0.0
            self._blink_direction = 1
        
        r = int(224 + (255 - 224) * self._blink_value)
        g = int(224 - (224 - 80) * self._blink_value)
        b = int(224 - (224 - 80) * self._blink_value)
        self.blink_label.setStyleSheet(f"color: #{r:02x}{g:02x}{b:02x}; font-weight: bold;")

    def _on_preset_clicked(self, preset_id: str):
        screen = QGuiApplication.primaryScreen().geometry()
        if preset_id == "fullscreen":
            coords = {"x1": 0, "y1": 0, "x2": screen.width(), "y2": screen.height()}
        else:
            width, height = self.PRESET_SIZES[preset_id]
            coords = self._center_region(screen, width, height)

        # Локализованное название пресета
        preset_name_key = {
            "fullscreen": "preset_fullscreen",
            "mobile": "preset_mobile",
            "youtube": "preset_youtube",
            "instagram": "preset_instagram",
            "tiktok": "preset_tiktok",
            "4x3": "preset_4x3",
            "16x10": "preset_16x10",
        }.get(preset_id, preset_id)


        preset_name = self.translator.tr(preset_name_key)
        self.set_active_preset(preset_id)   # ← выделяем кнопку
        self.preset_selected.emit(coords, preset_name, preset_id)

    def set_active_preset(self, preset_id):
        """Отметить пресет как активный и обновить подсветку всех кнопок."""
        self._active_preset_id = preset_id
        self._apply_button_styles()

    def set_blink_phase(self, phase: float):
        """Установить фазу мигания активного пресета (0.0 … 1.0)."""
        self._blink_phase = max(0.0, min(1.0, phase))
        self._apply_button_styles()

    def _apply_button_styles(self):
        """Подсветить активную кнопку; цвет зависит от фазы мигания."""
        active_bg = lerp_color_hex(PRESET_BG_DIM, PRESET_BG_BRIGHT, self._blink_phase)
        active_border = lerp_color_hex(PRESET_BORDER_DIM, PRESET_BORDER_BRIGHT, self._blink_phase)

        for preset_id, btn in self.buttons.items():
            if preset_id == self._active_preset_id:
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {active_bg};
                        border: 2px solid {active_border};
                        color: #ffffff;
                        font-size: 18px;
                    }}
                """)
            else:
                btn.setStyleSheet("")

    def _center_region(self, screen, width: int, height: int) -> dict:
        x1 = (screen.width() - width) // 2
        y1 = (screen.height() - height) // 2
        return {"x1": x1, "y1": y1, "x2": x1 + width, "y2": y1 + height}

    def retranslate_ui(self):
        self.blink_label.setText(self.translator.tr("preset_blink_message"))
        button_texts = {
            "fullscreen": self.translator.tr("preset_fullscreen"),
            "mobile": self.translator.tr("preset_mobile"),
            "youtube": self.translator.tr("preset_youtube"),
            "instagram": self.translator.tr("preset_instagram"),
            "tiktok": self.translator.tr("preset_tiktok"),
            "4x3": self.translator.tr("preset_4x3"),
            "16x10": self.translator.tr("preset_16x10"),
        }
        for preset_id, btn in self.buttons.items():
            btn.set_tooltip(button_texts.get(preset_id, preset_id))

    def closeEvent(self, event):
        if hasattr(self, '_blink_timer') and self._blink_timer.isActive():
            self._blink_timer.stop()
        super().closeEvent(event)
