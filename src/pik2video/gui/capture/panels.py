# src/pik2video/gui/capture/panels.py

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QFont, QFontDatabase, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.pik2video.gui.common.blink_style import (
    LABEL_ALPHA_BRIGHT,
    LABEL_ALPHA_DIM,
    lerp_alpha,
)
from src.pik2video.gui.common.tooltip import TooltipButton


class RedDot(QWidget):
    """Красная точка — индикатор активной записи (статичная, без мигания)."""

    SIZE = 10
    COLOR = "#c0392b"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.hide()

    def start(self):
        self.show()

    def stop(self):
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(self.COLOR))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, self.SIZE, self.SIZE)


class AudioLevelIndicator(QWidget):
    """Индикатор уровня звука: тонкие полоски от центра с цветовым градиентом."""

    HEIGHT = 30                          # высота виджета
    BAR_WIDTH = 2                        # ширина одной полоски в пикселях
    GAP = 5                              # зазор между полосками

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self.HEIGHT)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._level = 0.0

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))
        self.update()

    def reset(self):
        self._level = 0.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        if w <= 0 or h <= 0:
            return

        center_y = h / 2.0                          # невидимая горизонтальная линия центра
        max_half = center_y - 1.0                   # максимальная длина полоски от центра

        bw = self.BAR_WIDTH
        gap = self.GAP
        n = max(1, int(w / (bw + gap)))             # число полосок — по ширине виджета
        total_w = n * bw + (n - 1) * gap            # фактическая ширина всех полосок с зазорами
        offset_x = (w - total_w) / 2.0              # центрируем блок по горизонтали

        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.00, QColor("#8b1a1a"))    # вишнёвый у верхней границы
        grad.setColorAt(0.20, QColor("#b8860b"))    # тёмно-янтарный
        grad.setColorAt(0.45, QColor("#c0c0c0"))    # серебристый
        grad.setColorAt(0.55, QColor("#c0c0c0"))    # серебристый
        grad.setColorAt(0.80, QColor("#b8860b"))    # тёмно-янтарный
        grad.setColorAt(1.00, QColor("#8b1a1a"))    # вишнёвый у нижней границы

        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))

        for i in range(n):
            x = offset_x + i * (bw + gap)

            distance = abs(i - (n - 1) / 2.0) / ((n - 1) / 2.0) if n > 1 else 0.0
            weight = 1.0 - 0.4 * distance                       # центр = 1.0, край = 0.6

            half = self._level * max_half * weight
            if half < 0.5:
                continue

            painter.drawRoundedRect(
                x, center_y - half, bw, half * 2.0,
                bw / 2.0, bw / 2.0
            )






class CapturePanel(QWidget):
    """
    Общая UI-панель для Video, Screen и Audio сценариев.

    Верх (чёрное поле):
        - страница 0 (Video/Screen): три метки — параметры записи
        - страница 1 (Audio): имя источника + индикатор уровня
    Низ:
        - страница 0: кнопка настроек по центру
        - страница 1: две метки сверху + таймер снизу
    Красная точка в правом верхнем углу — индикатор активной записи.
    """

    BOTTOM_HEIGHT = 42
    BUTTON_WIDTH = 110
    BUTTON_HEIGHT = 32
    SETTINGS_WIDTH = 60
    BLOCK_VERTICAL_MARGIN = 4

    def __init__(self, parent, controller=None):
        super().__init__(parent)
        self.controller = controller
        self.translator = controller.get_translator() if controller else None

        # Последний валидный текст инфополя (для восстановления после ошибки)
        self._last_info_text: str = ""
        # Активна ли сейчас ошибка (блокирует blink-перерисовку стиля)
        self._error_active: bool = False
        # Таймер сброса ошибки
        self._error_timer = None

        self._build_ui()

        if self.translator:
            self.setup_localization()

    def setup_localization(self):
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.btn_start.setText(self.translator.tr("start_button"))
        self.btn_stop.setText(self.translator.tr("stop_button"))
        self.btn_settings.set_tooltip(self.translator.tr("capture_settings_tooltip"))

    # ─────────────────────────────────────────
    # UI
    # ─────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Верхняя строка ──
        top_row = QHBoxLayout()
        top_row.setContentsMargins(2, 2, 2, 0)
        top_row.setSpacing(2)

        self.top_widget = QWidget()
        self.top_widget.setStyleSheet("background:#1f1f1f; border-radius:4px;")

        self.info_stack = QStackedWidget(self.top_widget)
        self.info_stack.setStyleSheet("background: transparent; border: none;")

        # Страница 0 — три метки для видео/скрина
        video_info_page = QWidget()
        video_info_page.setStyleSheet("background: transparent; border: none;")
        info_layout = QHBoxLayout(video_info_page)
        info_layout.setContentsMargins(12, 4, 12, 4)
        info_layout.setSpacing(6)

        self.left_label = QLabel("")
        self.left_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        self.left_label.setAlignment(Qt.AlignLeft)
        self.left_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        self.center_label = QLabel("")
        self.center_label.setStyleSheet("color: white; font-size: 12px;")
        self.center_label.setAlignment(Qt.AlignCenter)
        self.center_label.setWordWrap(False)
        self.center_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.right_label = QLabel("")
        self.right_label.setStyleSheet("color: #a0a0a0; font-size: 12px;")
        self.right_label.setAlignment(Qt.AlignRight)
        self.right_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Minimum)

        info_layout.addWidget(self.left_label, 0)
        info_layout.addWidget(self.center_label, 1)
        info_layout.addWidget(self.right_label, 0)

        self.info_stack.addWidget(video_info_page)

        # Страница 1 — индикатор звука
        audio_info_page = QWidget()
        audio_info_page.setStyleSheet("background: transparent; border: none;")
        audio_layout = QHBoxLayout(audio_info_page)
        audio_layout.setContentsMargins(12, 4, 12, 4)
        audio_layout.setSpacing(6)

        self.audio_level = AudioLevelIndicator()
        audio_layout.addWidget(self.audio_level, 1)

        self.info_stack.addWidget(audio_info_page)

        # Страница 2 — подготовка файла
        prepare_page = QWidget()
        prepare_page.setStyleSheet("background: transparent; border: none;")
        prepare_layout = QHBoxLayout(prepare_page)
        prepare_layout.setContentsMargins(12, 4, 12, 4)

        self.prepare_label = QLabel("// подготовка файла //")
        self.prepare_label.setAlignment(Qt.AlignCenter)
        self.prepare_label.setStyleSheet(
            "color: #d4a843; font-size: 11px; font-weight: bold;"
        )
        prepare_layout.addWidget(self.prepare_label)

        self.info_stack.addWidget(prepare_page)

        top_widget_layout = QHBoxLayout(self.top_widget)
        top_widget_layout.setContentsMargins(0, 0, 0, 0)
        top_widget_layout.addWidget(self.info_stack)

        self.red_dot = RedDot()

        top_row.addWidget(self.top_widget, stretch=1)

        root.addLayout(top_row)

        # ── Нижняя панель ──
        bottom_widget = QWidget()
        bottom_widget.setFixedHeight(self.BOTTOM_HEIGHT)
        bottom_widget.setStyleSheet("background:#282828;")

        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(
            8, self.BLOCK_VERTICAL_MARGIN, 8, self.BLOCK_VERTICAL_MARGIN
        )
        bottom_layout.setSpacing(10)

        self.btn_start = QPushButton("")
        self.btn_start.setFixedSize(self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
        self.btn_start.setStyleSheet("font-size:15px;")

        self.btn_stop = QPushButton("")
        self.btn_stop.setFixedSize(self.BUTTON_WIDTH, self.BUTTON_HEIGHT)
        self.btn_stop.setStyleSheet("font-size:15px;")
        self.btn_stop.setEnabled(False)

        self.center_stack = QStackedWidget()
        self.center_stack.setFixedHeight(self.BUTTON_HEIGHT)

        # Страница 0 — кнопка настроек
        settings_page = QWidget()
        settings_layout = QHBoxLayout(settings_page)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(0)
        settings_layout.addStretch()

        self.btn_settings = TooltipButton("⚙️")
        self.btn_settings.setFixedSize(self.SETTINGS_WIDTH, self.BUTTON_HEIGHT)
        self.btn_settings.setStyleSheet("font-size:13px;")

        settings_layout.addWidget(self.btn_settings)
        settings_layout.addStretch()

        self.center_stack.addWidget(settings_page)

        # Страница 1 — две метки сверху + таймер снизу
        self.status_page = QWidget()
        status_layout = QVBoxLayout(self.status_page)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(0)

        labels_row = QHBoxLayout()
        labels_row.setContentsMargins(0, 0, 0, 0)
        labels_row.setSpacing(12)
        labels_row.addStretch()

        status_font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        status_font.setPointSize(10)

        self.status_label_1 = QLabel("")
        self.status_label_1.setStyleSheet("color: #ccc; font-size: 10px;")
        self.status_label_1.setAlignment(Qt.AlignCenter)
        self.status_label_1.setFont(status_font)
        self.status_label_1.setMinimumWidth(75)

        self.status_label_2 = QLabel("")
        self.status_label_2.setStyleSheet("color: #ccc; font-size: 10px;")
        self.status_label_2.setAlignment(Qt.AlignCenter)
        self.status_label_2.setFont(status_font)
        self.status_label_2.setMinimumWidth(55)

        labels_row.addWidget(self.status_label_1)
        labels_row.addWidget(self.status_label_2)
        labels_row.addStretch()

        status_layout.addLayout(labels_row)

        timer_row = QHBoxLayout()
        timer_row.setContentsMargins(0, 0, 0, 0)
        timer_row.setSpacing(6)
        timer_row.addStretch()

        self.timer_label = QLabel("TIME: 00:00:00")
        self.timer_label.setStyleSheet(
            "color: white; font-size: 13px; font-weight: bold;"
        )
        self.timer_label.setAlignment(Qt.AlignCenter)
        timer_font = QFont(QFontDatabase.systemFont(QFontDatabase.FixedFont))
        timer_font.setPointSize(13)
        timer_font.setBold(True)
        self.timer_label.setFont(timer_font)
        self.timer_label.setMinimumWidth(150)
        timer_row.addWidget(self.timer_label)

        timer_row.addWidget(self.red_dot)
        timer_row.addStretch()

        status_layout.addLayout(timer_row)

        self.center_stack.addWidget(self.status_page)

        bottom_layout.addWidget(self.btn_start)
        bottom_layout.addWidget(self.center_stack, 1)
        bottom_layout.addWidget(self.btn_stop)

        root.addWidget(bottom_widget)

        self.set_preparing_mode()

    # ─────────────────────────────────────────
    # Режимы панели
    # ─────────────────────────────────────────

    def set_preparing_mode(self):
        """Центр показывает кнопку настроек, красная точка скрыта."""
        self.center_stack.setCurrentIndex(0)
        self.red_dot.stop()

    def set_recording_mode(self):
        """Центр переключён на страницу статуса, красная точка пульсирует."""
        self.center_stack.setCurrentWidget(self.status_page)
        self.red_dot.start()

    def set_waiting_mode(self):
        """Режим ожидания перед стартом записи."""
        self.center_stack.setCurrentWidget(self.status_page)
        self.status_label_1.setText("")
        self.status_label_2.setText("")
        self.timer_label.setText("TIME: 00:00:00")

    def set_preparation_mode(self):
        """Показать «Подготовка файла», заблокировать кнопки."""
        self.info_stack.setCurrentIndex(2)                # prepare_page
        self.center_stack.setCurrentWidget(self.status_page)
        self.btn_start.setEnabled(False)
        self.btn_stop.setEnabled(False)
        self.btn_settings.setEnabled(False)

    # ─────────────────────────────────────────
    # Чёрное поле — инфо
    # ─────────────────────────────────────────

    def show_video_info(self, left_text: str, right_text: str):
        """Видео/скрин: слева и справа метки параметров, центр пустой."""
        self.info_stack.setCurrentIndex(0)
        self.left_label.setText(left_text)
        self.center_label.setText("")
        self.right_label.setText(right_text)

    def show_audio_info(self):
        """Аудио: только индикатор уровня (без текста источника)."""
        self.info_stack.setCurrentIndex(1)
        self.audio_level.reset()

    def set_audio_level(self, level: float):
        """Обновить уровень индикатора звука (0.0 … 1.0)."""
        self.audio_level.set_level(level)

    def set_info_text(self, text: str):
        """Показать текст в центральной метке чёрного поля.

        Обновляет «последний валидный текст» и снимает активную ошибку
        (если она была — пользователь только что сделал валидное действие).
        """
        if self._error_timer is not None:
            self._error_timer.stop()
        self._error_active = False
        self._last_info_text = text
        self.center_label.setText(text)
        self.center_label.setStyleSheet("color: white; font-size: 12px;")

    def set_error_text(self, text: str, duration_ms: int = 5000):
        """Показать сообщение об ошибке в чёрном поле на duration_ms.

        Через duration_ms восстанавливается последний валидный текст.
        Повторный вызов перезапускает таймер (старый отменяется).
        """
        if self._error_timer is not None:
            self._error_timer.stop()

        self._error_active = True
        self.center_label.setText(text)
        self.center_label.setStyleSheet(
            "color: #ff6b6b; font-size: 12px; font-weight: bold;"
        )

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._restore_after_error)
        self._error_timer.start(duration_ms)

    def _restore_after_error(self):
        """Восстановить последний валидный текст после сообщения об ошибке."""
        self._error_active = False
        self.center_label.setText(self._last_info_text)
        self.center_label.setStyleSheet("color: white; font-size: 12px;")

    def set_info_blink_phase(self, phase: float):
        """Мигание центральной метки чёрного поля (0.0 … 1.0).

        Пока активна ошибка — стиль не трогаем (иначе blink затирает красный).
        """
        if self._error_active:
            return
        alpha = lerp_alpha(phase, LABEL_ALPHA_DIM, LABEL_ALPHA_BRIGHT)
        self.center_label.setStyleSheet(
            f"color: rgba(255, 255, 255, {alpha}); font-size: 12px;"
        )

    def update_recording_shots(self, shots_text: str):
        """Обновить левую метку (SHOTS для screen)."""
        self.left_label.setText(shots_text)

    # ─────────────────────────────────────────
    # Нижняя панель — инфо
    # ─────────────────────────────────────────

    def set_status_labels(self, text_1: str, text_2: str):
        """Обновить две метки над таймером."""
        self.status_label_1.setText(text_1)
        self.status_label_2.setText(text_2)

    def update_recording_time(self, time_text: str):
        """Обновить таймер. Принимает текст с префиксом TIME: или без."""
        text = time_text.strip()
        if not text.startswith("TIME:"):
            text = f"TIME: {text}"
        self.timer_label.setText(text)

    # ─────────────────────────────────────────
    # Сброс
    # ─────────────────────────────────────────

    def reset_recording_mode(self):
        """Сбросить панель в исходное состояние."""
        self.info_stack.setCurrentIndex(0)
        self.left_label.setText("")
        self.center_label.setText("")
        self.right_label.setText("")
        self.status_label_1.setText("")
        self.status_label_2.setText("")
        self.timer_label.setText("00:00:00")
        self.red_dot.stop()