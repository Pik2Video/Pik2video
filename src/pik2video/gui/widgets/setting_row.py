# src/pik2video/gui/widgets/setting_row.py

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QSpacerItem, QSizePolicy

class SettingRow(QWidget):
    """
    Универсальная строка настройки:
    Слева текст (label), справа любой виджет управления (control).
    Автоматически учитывает внутренние отступы и фиксированные размеры для стабильного отображения.
    """

    def __init__(self, text: str, control: QWidget):
        super().__init__()

        # ───────── Layout ─────────
        layout = QHBoxLayout(self)  
        # Горизонтальный layout для label + control
        # Этот layout управляет расположением элементов в строке

        layout.setContentsMargins(8, 4, 4, 4)  
        # Отступы ВНУТРИ строки (слева, сверху, справа, снизу)
        # Эти значения делают пространство между краем строки и содержимым

        layout.setSpacing(8)  
        # Расстояние между label и control
        # Можно подправить, если элементы будут слишком близко или далеко

        # ───────── Label ─────────
        self.label = QLabel(text)  
        # Текст слева, описывающий настройку

        self.label.setFixedWidth(200)  
        # Фиксированная ширина текста
        # Стабилизирует отображение строк в разных окнах

        # ───────── Добавляем элементы в layout ─────────
        layout.addWidget(self.label)  
        # Добавляем текст слева

        # ───────── "Пружина" с минимальной шириной ─────────
        spacer = QSpacerItem(
            41,  # минимальная ширина пружины
            0,   # высота не важна для горизонтального layout
            QSizePolicy.Expanding,  # может растягиваться
            QSizePolicy.Minimum
        )
        layout.addItem(spacer)
        layout.addWidget(control)  
        # Добавляем виджет управления справа
        # Так как мы убрали addStretch(), ширина строки зависит от label+control+spacing+margins

        # ───────── Сохраняем control ─────────
        self.control = control  
        # Сохраняем ссылку на виджет, чтобы к нему можно было обращаться извне

    def setText(self, text: str):
        """Обновить текст настройки"""
        if hasattr(self, 'label'):
            self.label.setText(text)
        else:
            print(f"[ERROR] SettingRow: label не существует!")