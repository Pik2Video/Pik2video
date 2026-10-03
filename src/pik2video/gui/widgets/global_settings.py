# src/pik2video/gui/widgets/global_settings.py

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QCheckBox, QMenu, QPushButton

from src.pik2video.locale.languages import (
    AVAILABLE_LANGUAGES,
    code_from_display_name,
    flag_from_code,
)

# ── Константы ──

TEXT_SIZE_LABELS = {
    1: "Мелкий",
    2: "Средний",
    3: "Крупный",
}

BTN_WIDTH = 100
BTN_HEIGHT = 26


def _button_style() -> str:
    return """
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            border-radius: 4px;
            color: #e0e0e0;
            font-size: 11px;
            padding: 2px 8px;
        }
        QPushButton:hover { background-color: #4a4a4a; }
        QPushButton::menu-indicator { image: none; }
    """


# ── Виджеты ──

class LanguageSetting(QPushButton):
    """
    Виджет выбора языка — кнопка с флагом, выезжающее меню.
    """

    language_changed = Signal(str)  # "Русский" / "English"

    def __init__(self, controller):
        super().__init__()
        self._current = controller.get_language()

        self.setFixedSize(BTN_WIDTH, BTN_HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(_button_style())

        self._menu = QMenu(self)
        self._menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
            }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #3a3a3a; }
        """)

        for code, name in AVAILABLE_LANGUAGES.items():
            flag = flag_from_code(code)
            action = QAction(f"{flag}  {name}", self)
            action.triggered.connect(lambda checked=False, n=name: self._select(n))
            self._menu.addAction(action)

        self.setMenu(self._menu)
        self._update_text()

    def _update_text(self):
        code = code_from_display_name(self._current)
        self.setText(flag_from_code(code))

    def _select(self, lang_name: str):
        if lang_name == self._current:
            return
        self._current = lang_name
        self._update_text()
        self.language_changed.emit(lang_name)

    def get_value(self) -> str:
        return self._current

class TextSizeSetting(QPushButton):
    """
    Виджет выбора размера текста — кнопка с названием, выезжающее меню.
    """

    size_changed = Signal(int)  # 1 / 2 / 3

    def __init__(self, controller):
        super().__init__()
        self._current = controller.get_text_size()

        self.setFixedSize(BTN_WIDTH, BTN_HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(_button_style())

        self._menu = QMenu(self)
        self._menu.setStyleSheet("""
            QMenu {
                background-color: #2a2a2a;
                border: 1px solid #555;
                color: #e0e0e0;
            }
            QMenu::item { padding: 4px 20px; }
            QMenu::item:selected { background-color: #3a3a3a; }
        """)

        for size_value, label in TEXT_SIZE_LABELS.items():
            action = QAction(label, self)
            action.triggered.connect(lambda checked=False, v=size_value: self._select(v))
            self._menu.addAction(action)

        self.setMenu(self._menu)
        self._update_text()

    def _update_text(self):
        self.setText(TEXT_SIZE_LABELS.get(self._current, "—"))

    def _select(self, value: int):
        if value == self._current:
            return
        self._current = value
        self._update_text()
        self.size_changed.emit(value)

    def get_value(self) -> int:
        return self._current


class TooltipsSetting(QCheckBox):
    """Включение/выключение подсказок."""
    def __init__(self, controller):
        super().__init__()
        self.setChecked(controller.get_show_tooltips())
        self.setText("")

    def get_value(self):
        return self.isChecked()


class AlwaysOnTopSetting(QCheckBox):
    """Включение/выключение режима «всегда в топе»."""
    def __init__(self, controller):
        super().__init__()
        self.setChecked(controller.get_always_on_top())
        self.setText("")

    def get_value(self):
        return self.isChecked()


class AutoHideEditorSetting(QCheckBox):
    """Автоскрытие редактора при старте записи."""
    def __init__(self, controller):
        super().__init__()
        self.setChecked(controller.get_auto_hide_editor())
        self.setText("")

    def get_value(self):
        return self.isChecked()
