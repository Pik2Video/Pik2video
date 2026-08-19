# src/pik2video/gui/components_settings/global_settings.py


from PySide6.QtWidgets import QComboBox, QSpinBox, QCheckBox
from PySide6.QtCore import Qt

# ────────────1️⃣ Язык приложения────────────
class LanguageSetting(QComboBox):
    """
    Виджет выбора языка приложения
    """
    def __init__(self, controller):
        super().__init__()
        # Добавляем варианты языков
        self.addItems(["Русский", "English"]) # Добавляем варианты языков
        self.setCurrentText(controller.get_language())        # Устанавливаем текущий язык из контроллера
        self.setFixedWidth(100)        # Фиксированная ширина, чтобы не ломалась строка


    def get_value(self):
        # Возвращает выбранный язык
        return self.currentText()


# ────────────2️⃣ Размер текста────────────
class TextSizeSetting(QSpinBox):
    """
    Виджет для выбора размера текста
    """
    def __init__(self, controller):
        super().__init__()
        # Ограничиваем диапазон значений
        self.setRange(1, 3)
        # Устанавливаем текущее значение из контроллера
        self.setValue(controller.get_text_size())
        # Фиксированная ширина, чтобы не ломалась строка
        self.setFixedWidth(30)

    def get_value(self):
        # Возвращает выбранный размер текста
        return self.value()


# ────────────3️⃣ Подсказки──────────────────
class TooltipsSetting(QCheckBox):
    """
    Виджет для включения/выключения подсказок
    """
    def __init__(self, controller):
        super().__init__()
        # Устанавливаем состояние из контроллера
        self.setChecked(controller.get_show_tooltips())
        # Текст на виджете пустой (его будет описывать SettingRow)
        self.setText("")

    def get_value(self):
        # Возвращает True/False
        return self.isChecked()

# ────────────4️⃣ Всегда в топе────────────
class AlwaysOnTopSetting(QCheckBox):
    """
    Виджет для включения/выключения режима "всегда в топе"
    """
    def __init__(self, controller):
        super().__init__()
        self.setChecked(controller.get_always_on_top())
        self.setText("")

    def get_value(self):
        return self.isChecked()
