# src/pik2video/gui/common/base.py

import logging

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from .close_policy import (
    CloseAction,
    CloseContext,
    ClosePolicy,
    CloseRule,
    evaluate_close,
)
from .dialogs import confirm
from .utils import keep_window_inside_screen

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
        action = evaluate_close(
            self.get_close_policy(),
            self.make_close_context(),
            ask=self._ask,
        )

        if action == CloseAction.CLOSE:
            event.accept()
            self.on_closed()
        else:
            event.ignore()

    # ─────────── Расширяемые точки ───────────

    def get_close_policy(self) -> ClosePolicy:
        """Политика закрытия. Переопределяется в наследниках."""
        return ClosePolicy.ALLOW

    def make_close_context(self) -> CloseContext:
        """Факты о состоянии для close_policy. Переопределяется при необходимости."""
        return CloseContext()

    def _ask(self, rule: CloseRule) -> bool:
        """Мост между политикой и QMessageBox."""
        return confirm(
            self,
            rule.text,
            title=rule.title,
            translator=getattr(self, "translator", None),
            yes_label=rule.yes_label,
            no_label=rule.no_label,
        )

    def on_closed(self):
        """Хук после успешного закрытия. Переопределяется в наследниках."""


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

