# src/pik2video/gui/common/base.py

import logging

from PySide6.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QFrame, QSizePolicy, QLabel
from PySide6.QtCore import Qt, QSize, QEvent, Signal, QObject
from PySide6.QtGui import QCloseEvent
from .dialogs import confirm
from .utils import center_to_parent, keep_window_inside_screen

logger = logging.getLogger(__name__)

class BaseDialog(QDialog):
    """
    Базовый класс для всех диалоговых окон.
    Отвечает за:
    - модальность (блокирует другие окна)
    - позиционирование
    - обработку закрытия окна
    """

    def __init__(self, parent: QWidget, controller=None):
        super().__init__(parent)

        self.setModal(True)            # Устанавливаем модальность (пока окно открыто — нельзя кликать в другие)
        self.controller = controller   # Контроллер (логика приложения)
        #self._is_positioned = False    # Флаг: уже ли окно было позиционировано

        # Устанавливаем флаги окна (что у него есть)
        self.setWindowFlags(
            Qt.Dialog                  # это диалог
            | Qt.WindowTitleHint       # есть заголовок
            | Qt.WindowCloseButtonHint # есть кнопка закрытия (крестик)
        )

        self.setFixedSize(self.sizeHint())

        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)


    def showEvent(self, event):
        super().showEvent(event)

        if self.parent():
            parent_geom = self.parent().frameGeometry()
            # Центрируем по геометрии родителя
            x = parent_geom.x() + (parent_geom.width() - self.width()) // 2
            y = parent_geom.y() + (parent_geom.height() - self.height()) // 2
            self.move(x, y)
            # Удерживаем в пределах экрана с отступом
            keep_window_inside_screen(self, margin=80)

    
    def closeEvent(self, event: QCloseEvent):

        # Проверяем: можно ли вообще закрывать
        if not self.can_close():
            event.ignore()  # отменяем закрытие
            return

        # Нужно ли подтверждение (например "Вы уверены?")
        if self.requires_confirmation_on_close() and not confirm(self, "Вы уверены?"):
            event.ignore()
            return

        # Хук перед закрытием (может отменить закрытие)
        if not self.on_before_close():
            event.ignore()
            return

        # Если всё ок — закрываем
        event.accept()

        self.on_after_close()


    def can_close(self) -> bool:
        # Можно ли закрыть окно (по умолчанию — да)
        return True

    def requires_confirmation_on_close(self) -> bool:
        # Нужно ли спрашивать подтверждение
        return False

    def on_before_close(self) -> bool:
        # Вызывается перед закрытием
        # Если вернуть False — окно НЕ закроется
        return True

    def on_after_close(self):
        # Вызывается после закрытия
        pass


class BaseFormDialog(BaseDialog):
    """
    Базовый класс для "форм" (настроек и т.п.)

    Внутри есть:
    - content_layout (основное содержимое)
    - buttons_layout (кнопки снизу)

    Наследники ОБЯЗАНЫ реализовать:
    - build_content()
    - build_buttons()
    """

    def __init__(self, parent, controller, title: str):
        # Инициализация базового диалога
        super().__init__(parent, controller)

        self.setWindowTitle(title) # Устанавливаем заголовок окна
        self.adjustSize()
        self._build_layout()       # Строим интерфейс
        self.adjustSize()          # Даём Qt время на вычисление размеров
        
        # Добавляем запас по высоте 
        size = self.size()
        self.setFixedSize(size.width(), size.height() + 38)

        # Стили кнопок (CSS)
        self.setStyleSheet("""
        QPushButton {
            background-color: #3a3a3a;
            border: 1px solid #555;
            border-radius: 4px;
            padding: 6px 16px;
        }

        QPushButton:hover {
            background-color: #4a4a4a;
        }

        QPushButton:pressed {
            background-color: #2a2a2a;
        }
        """)


    def _build_layout(self):
        # Главный вертикальный layout
        self.main_layout = QVBoxLayout(self)

        # внешние отступы всего окна   (слева, сверху, справа, снизу)
        self.main_layout.setContentsMargins(6, 6, 6, 6)

        self.main_layout.setSpacing(1) # Расстояние между элементами внутри main_layout

        # ───────── Контент ─────────

        # Виджет-контейнер для содержимого
        self.content_widget = QWidget()

        # Стили для блока контента
        self.content_widget.setStyleSheet("""
            background-color: #2f2f2f;
            border: 1px solid #444;
            border-radius: 6px;
        """)

        # Layout внутри контента
        self.content_layout = QVBoxLayout(self.content_widget)

        self.content_layout.setSpacing(6) # Расстояние между элементами внутри формы
        self.content_layout.setContentsMargins(3, 3, 3, 3) # Отступы внутри блока контента (внутри рамки)

        # Вызываем метод, который должен реализовать наследник
        self.build_content(self.content_layout)

        # Добавляем контент в главный layout
        self.main_layout.addWidget(self.content_widget)

        # ───────── Кнопки ─────────

        # Горизонтальный layout для кнопок
        self.buttons_layout = QHBoxLayout()

        # Отступы вокруг блока кнопок   | слева: 0 | сверху: 4 | справа: 0 | снизу: 0 |

        self.buttons_layout.setContentsMargins(0, 4, 0, 0)
        # Расстояние между кнопками
        self.buttons_layout.setSpacing(10) 

        # Создание кнопок (реализуется в наследниках)
        self.build_buttons()

        # Добавляем кнопки в главный layout
        self.main_layout.addLayout(self.buttons_layout)

    def build_content(self, layout: QVBoxLayout):
        # ДОЛЖЕН быть переопределён
        raise NotImplementedError

    def build_buttons(self):
        # ДОЛЖЕН быть переопределён
        raise NotImplementedError


# ─────────────────────────────────────────
# ОКНО НАСТРОЕК
# ─────────────────────────────────────────

class SettingsDialog(BaseFormDialog):

    def __init__(self, parent, controller, title="Настройки"):
        logger.debug(f"SettingsDialog.__init__ - received controller type: {type(controller)}")

        # Инициализация базовой формы
        super().__init__(parent, controller, title)

        logger.debug(f"SettingsDialog.__init__ - after super, self.controller type: {type(self.controller)}")
        
        self._parent = parent
        if self._parent:
            self._parent.installEventFilter(self)

        # Подключаем перевод для кнопок
        self.setup_buttons_localization(controller)

    def setup_buttons_localization(self, controller):
        """Подключаем перевод для кнопок"""
        self.controller = controller
        self.translator = controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_buttons)
        self.retranslate_buttons()

    def retranslate_buttons(self):
        """Обновляет текст на кнопках при смене языка"""
        if hasattr(self, 'btn_cancel'):
            self.btn_cancel.setText(self.translator.tr("cancel_button"))
            self.btn_apply.setText(self.translator.tr("apply_button"))

    def build_buttons(self):
        # Кнопка "отмена" (текст будет установлен в retranslate_buttons)
        self.btn_cancel = QPushButton("")

        # Кнопка "принять" (текст будет установлен в retranslate_buttons)
        self.btn_apply = QPushButton("")

        # Минимальная ширина кнопок
        self.btn_cancel.setMinimumWidth(160)
        self.btn_apply.setMinimumWidth(160)

        # При нажатии "отмена" — закрыть окно
        self.btn_cancel.clicked.connect(self.close)

        # При нажатии "принять" — вызвать обработчик
        self.btn_apply.clicked.connect(self._on_apply_clicked)

        # Добавляем кнопки в layout
        self.buttons_layout.addWidget(self.btn_cancel)

        # Пустое пространство (растягивает кнопки)
        self.buttons_layout.addStretch()

        self.buttons_layout.addWidget(self.btn_apply)

    def _on_apply_clicked(self):
        # Применяем настройки
        result = self.apply_settings()

        # Если всё прошло успешно — закрываем окно
        if result:
            self.close()

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        if obj == self._parent and event.type() == QEvent.Move:
            # Обновить позицию при перемещении родителя
            if self.isVisible():
                from .utils import center_to_parent, keep_window_inside_screen
                center_to_parent(self, self._parent)
                keep_window_inside_screen(self)
        return super().eventFilter(obj, event)

    def apply_settings(self) -> bool:
        # Метод для применения настроек (переопределяется)
        return True

    def requires_confirmation_on_close(self) -> bool:
        # В этом окне не нужно подтверждение при закрытии
        return False


# финальное окно

class FinalizeWidget(QWidget):
    """
    Базовый виджет финализации.
    Встраивается в MainWindow, а не отдельное окно.
    
    Наследники должны реализовать build_content()
    """
    
    finalize_requested = Signal()   # Сохранить и завершить
    discard_requested = Signal()    # Удалить без сохранения
    
    def __init__(self, parent, controller, title: str = ""):
        super().__init__(parent)
        self.controller = controller
        self.title = title
        
        self._build_ui()

        # Подключаем перевод для кнопок
        if controller:
            self.setup_localization()

    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator = self.controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
        
    def retranslate_ui(self):
        """Обновляет тексты на кнопках при смене языка"""
        if hasattr(self, 'btn_done'):
            self.btn_done.setText(self.translator.tr("finalize_button"))
            self.btn_delete.setText(self.translator.tr("discard_button"))
        
    def _build_ui(self):
        """Построение интерфейса"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Контент (заполняется в наследниках)
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("""
            background-color: #2f2f2f;
            border: 1px solid #444;
            border-radius: 6px;
        """)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(12, 12, 12, 12)
        self.content_layout.setSpacing(12)
        
        main_layout.addWidget(self.content_widget)
        
        # Нижняя панель с кнопками
        bottom_panel = QWidget()
        bottom_panel.setFixedHeight(50)
        bottom_panel.setStyleSheet("background:#282828;")
        bottom_layout = QHBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(8, 8, 8, 8)
        bottom_layout.setSpacing(10)
        
        # Кнопка "готово" (сохранить)
        self.btn_done = QPushButton("")
        self.btn_done.setFixedSize(160, 32)
        self.btn_done.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 4px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
        """)
        self.btn_done.clicked.connect(self._on_done_clicked)
        
        # Кнопка "удалить" (отменить)
        self.btn_delete = QPushButton("")
        self.btn_delete.setFixedSize(160, 32)
        self.btn_delete.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 4px;
                color: #e0e0e0;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
        """)
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        
        
        bottom_layout.addWidget(self.btn_done)
        bottom_layout.addStretch()

        # 🆕 Метки RAM и TIME между кнопками
        stats_widget = QWidget()
        stats_layout = QVBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(2)
        
        self.stats_ram = QLabel("RAM: 0 KB")
        self.stats_ram.setStyleSheet("color: #aaa; font-size: 10px; background: transparent; border: none;")
        self.stats_ram.setAlignment(Qt.AlignCenter)
        self.stats_ram.setToolTip("Вес текущего файла")
        
        self.stats_time = QLabel("00:00:00")
        self.stats_time.setStyleSheet("color: #aaa; font-size: 10px; background: transparent; border: none;")
        self.stats_time.setAlignment(Qt.AlignCenter)
        self.stats_time.setToolTip("Продолжительность последней записи")
        
        stats_layout.addWidget(self.stats_ram)
        stats_layout.addWidget(self.stats_time)
        
        bottom_layout.addWidget(stats_widget)

        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_delete)
        
        
        main_layout.addWidget(bottom_panel)
    
    def _on_done_clicked(self):
        """Пользователь нажал 'готово'"""
        self.finalize_requested.emit()
    
    def _on_delete_clicked(self):
        """Пользователь нажал 'удалить'"""
        if confirm(self, "Удалить запись без сохранения?"):
            self.discard_requested.emit()
    
    def build_content(self, layout: QVBoxLayout):
        """Переопределяется в наследниках для добавления содержимого"""
        raise NotImplementedError

    def update_stats(self, ram_text: str, time_text: str):
        """Обновить метки RAM и TIME в финальном окне"""
        if hasattr(self, 'stats_ram'):
            self.stats_ram.setText(f"RAM: {ram_text}")
        if hasattr(self, 'stats_time'):
            self.stats_time.setText(f"{time_text}")


class LocalizedMixin:
    """Миксин для добавления поддержки переводов"""
    
    def setup_localization(self, controller):
        self.controller = controller
        self.translator = controller.get_translator()
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Переопределяется в дочерних классах"""
        pass