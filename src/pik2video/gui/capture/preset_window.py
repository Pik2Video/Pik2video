from typing import ClassVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from src.pik2video.gui.common.blink_style import (
    PRESET_BG_BRIGHT,
    PRESET_BG_DIM,
    PRESET_BORDER_BRIGHT,
    PRESET_BORDER_DIM,
    lerp_color_hex,
)
from src.pik2video.gui.common.tooltip import TooltipButton


FIT_MARGIN = 40          # отступ авто-фита от краёв экрана, px
ZOOM_MIN = 20            # минимальный зум, %
ZOOM_MAX = 100           # максимальный зум (= fill по экрану), %
ZOOM_STEP = 5            # шаг зума, %


class PresetWindow(QWidget):
    """
    Окно с пресетами области записи.
    Два режима: горизонтальный (сверху) и вертикальный (справа).
    """

    preset_selected = Signal(dict, str, str)

    PRESETS: ClassVar[list] = [
        ("⛶", "fullscreen", "Весь экран"),
        ("9:19", "mobile", "Мобильный"),
        ("16:9", "youtube", "YouTube"),
        ("4:5", "instagram", "Instagram"),
        ("9:16", "tiktok", "TikTok"),
        ("4:3", "4x3", "4:3"),
    ]

    PRESET_SIZES: ClassVar[dict] = {
        "fullscreen": (0, 0),
        "mobile": (390, 844),
        "youtube": (1920, 1080),
        "instagram": (1080, 1350),
        "tiktok": (1080, 1920),
        "4x3": (1600, 1200),
    }

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.translator = controller.get_translator()

        # Загружаем сохранённую позицию
        self._is_vertical = controller.get_preset_vertical() if hasattr(controller, 'get_preset_vertical') else False

        self._active_preset_id = "fullscreen"
        self._blink_phase = 0.0                  # 0.0 = тусклая, 1.0 = яркая (для мигания активного пресета)

        # Per-preset зум: preset_id → процент (20..100). Пусто = авто-фит при первом выборе.
        self._zoom_percent: dict[str, int] = {}
        # Per-preset центр: preset_id → (cx, cy). Пусто = центр экрана.
        # Обновляется при перетаскивании, сохраняется при зуме.
        self._preset_centers: dict[str, tuple[int, int]] = {}

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

        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        self._apply_button_styles()

    @staticmethod
    def get_default_preset_coords(screen_geometry) -> dict:
        """Возвращает координаты пресета по умолчанию (весь экран)."""
        return {
            "x1": 0,
            "y1": 0,
            "x2": screen_geometry.width(),
            "y2": screen_geometry.height()
        }

    # ─────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────

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

        # Кнопка переключения ориентации (всегда есть)
        self.btn_toggle = TooltipButton("↕", "Переключить положение панели")
        self.btn_toggle.setFixedSize(28, 22)
        self.btn_toggle.clicked.connect(self._toggle_layout)

        # Кнопки зума (создаются один раз)
        self.btn_zoom_minus = QPushButton("−")
        self.btn_zoom_minus.setFixedSize(24, 24)
        self.btn_zoom_minus.clicked.connect(self._on_zoom_minus)

        self.lbl_zoom = QLabel("100%")
        self.lbl_zoom.setAlignment(Qt.AlignCenter)
        self.lbl_zoom.setFixedSize(44, 24)

        self.btn_zoom_plus = QPushButton("+")
        self.btn_zoom_plus.setFixedSize(24, 24)
        self.btn_zoom_plus.clicked.connect(self._on_zoom_plus)

        # Кнопки пресетов
        self.buttons_layout = QHBoxLayout() if not self._is_vertical else QVBoxLayout()
        self.buttons_layout.setSpacing(8)

        self.buttons = {}
        for icon, preset_id, tooltip in self.PRESETS:
            btn = TooltipButton(icon, tooltip)
            btn.setFixedSize(30, 30)
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
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().setParent(None)

        if self._is_vertical:
            # Вертикальный режим: toggle сверху, пресеты, зум
            self.setFixedSize(56, 370)

            # Кнопка переключения ориентации — в самом верху с отступом
            self.inner_layout.addWidget(self.btn_toggle, alignment=Qt.AlignCenter)
            self.inner_layout.addSpacing(8)

            self.buttons_layout = QVBoxLayout()
            self.buttons_layout.setSpacing(4)
            for icon, preset_id, tooltip in self.PRESETS:
                btn = TooltipButton(icon, tooltip)
                btn.setFixedSize(30, 30)
                btn.clicked.connect(lambda checked, p=preset_id: self._on_preset_clicked(p))
                self.buttons_layout.addWidget(btn, alignment=Qt.AlignCenter)
                self.buttons[preset_id] = btn

            self.inner_layout.addLayout(self.buttons_layout)
            self.inner_layout.addSpacing(8)

            # Зум столбиком: [−] / [NN%] / [+]
            self.inner_layout.addWidget(self.btn_zoom_minus, alignment=Qt.AlignCenter)
            self.btn_zoom_minus.setFixedSize(30, 24)

            self.inner_layout.addWidget(self.lbl_zoom, alignment=Qt.AlignCenter)
            self.lbl_zoom.setFixedSize(44, 24)

            self.inner_layout.addWidget(self.btn_zoom_plus, alignment=Qt.AlignCenter)
            self.btn_zoom_plus.setFixedSize(30, 24)
        else:
            # Горизонтальный режим: пресеты + зум + toggle в одну строку
            self.setFixedSize(480, 64)

            line = QHBoxLayout()
            line.setSpacing(12)
            line.addStretch()

            for icon, preset_id, tooltip in self.PRESETS:
                btn = TooltipButton(icon, tooltip)
                btn.setFixedSize(30, 30)
                btn.clicked.connect(lambda checked, p=preset_id: self._on_preset_clicked(p))
                line.addWidget(btn)
                self.buttons[preset_id] = btn

            line.addSpacing(20)

            # Зум — компактный блок: [- 100% +] без больших зазоров
            zoom_layout = QHBoxLayout()
            zoom_layout.setSpacing(2)
            zoom_layout.setContentsMargins(0, 0, 0, 0)

            self.btn_zoom_minus.setFixedSize(24, 24)
            self.lbl_zoom.setFixedSize(40, 24)
            self.btn_zoom_plus.setFixedSize(24, 24)
            zoom_layout.addWidget(self.btn_zoom_minus)
            zoom_layout.addWidget(self.lbl_zoom)
            zoom_layout.addWidget(self.btn_zoom_plus)

            line.addLayout(zoom_layout)

            # Кнопка переключения ориентации — в самом конце с отступом
            line.addSpacing(8)
            line.addWidget(self.btn_toggle)

            line.addStretch()
            self.inner_layout.addLayout(line)

        self.btn_toggle.setText("↔" if self._is_vertical else "↕")
        self._sync_zoom_ui()
        self._position_window()
        self._apply_styles()

    def _toggle_layout(self):
        """Переключает между горизонтальным и вертикальным режимом"""
        self._is_vertical = not self._is_vertical
        self._apply_layout()
        if hasattr(self.controller, 'set_preset_vertical'):
            self.controller.set_preset_vertical(self._is_vertical)
        if hasattr(self.controller, 'save_settings'):
            self.controller.save_settings()

    # ─────────────────────────────────────────
    # Стили
    # ─────────────────────────────────────────

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
                background: transparent;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #999;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
            QPushButton:disabled {
                color: #555;
                background-color: #1a1a1a;
                border-color: #333;
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

    # ─────────────────────────────────────────
    # Пресеты
    # ─────────────────────────────────────────

    def _on_preset_clicked(self, preset_id: str):
        """Пользователь выбрал пресет. Первый раз — авто-фит, дальше — сохранённый зум."""
        self.set_active_preset(preset_id)

        if preset_id == "fullscreen":
            self._sync_zoom_ui()
            self._emit_fullscreen()
            return

        # Первый выбор пресета — авто-фит
        if preset_id not in self._zoom_percent:
            self._zoom_percent[preset_id] = self._compute_fit_percent(preset_id)

        self._sync_zoom_ui()
        self._apply_zoom(preset_id)

    def _emit_fullscreen(self):
        """Отдельная ветка: fullscreen — весь экран без масштабирования."""
        screen = QGuiApplication.primaryScreen().geometry()
        coords = {"x1": 0, "y1": 0, "x2": screen.width(), "y2": screen.height()}
        preset_name = self.translator.tr("preset_fullscreen")
        self.preset_selected.emit(coords, preset_name, "fullscreen")

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
                        font-size: 11px;
                        font-weight: bold;
                    }}
                """)
            else:
                btn.setStyleSheet("")

    # ─────────────────────────────────────────
    # Зум
    # ─────────────────────────────────────────

    def _on_zoom_minus(self):
        self._change_zoom(-ZOOM_STEP)

    def _on_zoom_plus(self):
        self._change_zoom(+ZOOM_STEP)

    def _change_zoom(self, delta: int):
        preset_id = self._active_preset_id
        if not preset_id or preset_id == "fullscreen":
            return
        current = self._zoom_percent.get(preset_id, 100)
        new = max(ZOOM_MIN, min(ZOOM_MAX, current + delta))
        if new == current:
            return
        self._zoom_percent[preset_id] = new
        self._sync_zoom_ui()
        self._apply_zoom(preset_id)

    def _sync_zoom_ui(self):
        """Обновить label и состояние кнопок зума."""
        preset_id = self._active_preset_id
        if not preset_id or preset_id == "fullscreen":
            self.lbl_zoom.setText("—")
            self.btn_zoom_minus.setEnabled(False)
            self.btn_zoom_plus.setEnabled(False)
            return

        percent = self._zoom_percent.get(preset_id, 100)
        self.lbl_zoom.setText(f"{percent}%")
        self.btn_zoom_minus.setEnabled(percent > ZOOM_MIN)
        self.btn_zoom_plus.setEnabled(percent < ZOOM_MAX)

    def _apply_zoom(self, preset_id: str):
        """Пересчитать координаты пресета по текущему зуму и эмитить сигнал."""
        if not preset_id or preset_id == "fullscreen":
            return
        percent = self._zoom_percent.get(preset_id, 100)
        coords = self._percent_to_coords(preset_id, percent)
        if coords is None:
            return
        preset_name = self.translator.tr(f"preset_{preset_id}")
        self.preset_selected.emit(coords, preset_name, preset_id)

    # ─────────────────────────────────────────
    # Геометрия
    # ─────────────────────────────────────────

    def _fill_scale(self, w_req: int, h_req: int, screen) -> float:
        """Масштаб для 100%: пресет занимает экран по одной оси."""
        if w_req <= 0 or h_req <= 0:
            return 1.0
        return min(screen.width() / w_req, screen.height() / h_req)

    def _compute_fit_percent(self, preset_id: str) -> int:
        """Процент авто-фита: максимальный, при котором пресет влезает с отступом."""
        w_req, h_req = self.PRESET_SIZES[preset_id]
        screen = QGuiApplication.primaryScreen().geometry()

        fill = self._fill_scale(w_req, h_req, screen)
        if fill <= 0:
            return ZOOM_MAX

        fit = min(
            (screen.width() - 2 * FIT_MARGIN) / w_req,
            (screen.height() - 2 * FIT_MARGIN) / h_req,
        )
        percent = int(round(fit / fill * 100))
        return max(ZOOM_MIN, min(ZOOM_MAX, percent))

    def _percent_to_coords(self, preset_id: str, percent: int) -> dict | None:
        """Координаты пресета по зуму. Центр — сохранённый (после перетаскивания)
        или центр экрана. При изменении размера пресет «растёт» вокруг центра.
        """
        w_req, h_req = self.PRESET_SIZES[preset_id]
        screen = QGuiApplication.primaryScreen().geometry()

        fill = self._fill_scale(w_req, h_req, screen)
        scale = fill * percent / 100.0

        width = int(w_req * scale)
        height = int(h_req * scale)

        if preset_id in self._preset_centers:
            cx, cy = self._preset_centers[preset_id]
        else:
            cx = screen.width() // 2
            cy = screen.height() // 2

        x1 = cx - width // 2
        y1 = cy - height // 2

        # clamp: не выходить за пределы экрана
        x1 = max(0, min(x1, screen.width() - width))
        y1 = max(0, min(y1, screen.height() - height))

        return {"x1": x1, "y1": y1, "x2": x1 + width, "y2": y1 + height}

    def set_preset_center(self, cx: int, cy: int):
        """Сохранить центр активного пресета. Вызывается из StateCoordinator
        после перетаскивания (region_moved).
        """
        preset_id = self._active_preset_id
        if not preset_id or preset_id == "fullscreen":
            return
        self._preset_centers[preset_id] = (int(cx), int(cy))

    # ─────────────────────────────────────────
    # Локализация
    # ─────────────────────────────────────────

    def retranslate_ui(self):
        button_texts = {
            "fullscreen": self.translator.tr("preset_fullscreen"),
            "mobile": self.translator.tr("preset_mobile"),
            "youtube": self.translator.tr("preset_youtube"),
            "instagram": self.translator.tr("preset_instagram"),
            "tiktok": self.translator.tr("preset_tiktok"),
            "4x3": self.translator.tr("preset_4x3"),
        }
        for preset_id, btn in self.buttons.items():
            btn.set_tooltip(button_texts.get(preset_id, preset_id))

    def closeEvent(self, event):
        super().closeEvent(event)
