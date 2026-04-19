# src/pik2video/gui/components_settings/common_settings.py

from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout, QSpinBox, QSizePolicy, QLineEdit, QApplication
from PySide6.QtCore import Qt, QEvent, Signal, QTimer
from PySide6.QtGui import QFont, QIntValidator


class CleanSpinBox(QSpinBox):
    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.lineEdit().selectAll()



class PremiumLineEdit(QLineEdit):
    """
    Ввод числового значения для таймера.
    Пустое поле отображает placeholder, иначе показывается двухзначное число белого цвета.
    """

    focusGained = Signal()
    valueChanged = Signal(int)

    def __init__(self, placeholder: str, max_value: int):
        super().__init__()

        self._placeholder_text = placeholder
        self._max_value = max_value

        self._value = 0
        self._is_placeholder = True

        self.setFixedSize(30, 26)
        self.setAlignment(Qt.AlignCenter)
        self.setMaxLength(2)

        font = QFont("Courier New")
        font.setPointSize(13)
        self.setFont(font)

        self.setValidator(QIntValidator(0, max_value))
        self.textEdited.connect(self._on_text_edited)

        # Изначально применяем placeholder
        self._apply_placeholder()

    # ───── UI состояния ─────
    def _apply_placeholder(self):
        self._is_placeholder = True
        self.blockSignals(True)
        self.setText(self._placeholder_text)
        self.blockSignals(False)
        self.setStyleSheet(
            "color: rgba(255,255,255,120); background:#121212; border:none; border-radius:4px;"
        )

    def _apply_value(self):
        self._is_placeholder = False
        self.blockSignals(True)
        self.setText(f"{self._value:02d}")  # всегда двухзначное число
        self.blockSignals(False)
        self.setStyleSheet(
            "color: white; background:#121212; border:none; border-radius:4px;"
        )

    # ───── Логика ввода ─────
    def _on_text_edited(self, text: str):
        if self._is_placeholder:
            return

        if text == "":
            self._set_value(0)
            return

        try:
            value = int(text)
        except ValueError:
            value = 0

        value = min(value, self._max_value)
        self._set_value(value)

    def _set_value(self, value: int):
        if self._value != value:
            self._value = value
            self.valueChanged.emit(value)

    # ───── События фокуса ─────
    def focusInEvent(self, event):
        if self._is_placeholder:
            self._is_placeholder = False
            self.setText("")
            self.setStyleSheet(
                "color: white; background:#121212; border:none; border-radius:4px;"
            )

        self.selectAll()
        self.focusGained.emit()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)

    # ───── API ─────
    def value(self) -> int:
        return self._value

    def setValue(self, value: int):
        value = min(value, self._max_value)
        self._value = value

        if value == 0:
            self._apply_placeholder()  # показываем плейсхолдер, а не "00"
        else:
            self._apply_value()

    def force_edit_mode(self):
        """Вызывается, когда фокус внутри таймера"""
        if self._is_placeholder:
            self._is_placeholder = False
            self.setText("")
        self.setStyleSheet(
            "color: white; background:#121212; border:none; border-radius:4px;"
        )

    def force_display_mode(self, has_any_value: bool):
        """Вызывается, когда фокус ушёл"""
        if has_any_value:
            self._apply_value()
        else:
            self._apply_placeholder()




class TimerInput(QWidget):
    """
    Ввод времени в формате hh:mm:ss с автозаполнением и белым цветом текста.
    """

    def __init__(self):
        super().__init__()

        self._has_focus_inside = False

        # Слушаем глобальное изменение фокуса, чтобы отслеживать TimerInput
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        # ───── UI ─────
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()

        self.block = QWidget()
        self.block.setFixedHeight(36)
        self.block.setStyleSheet("""
            QWidget {
                background-color: #252525;
                border-radius: 8px;
            }
            QWidget:hover {
                background-color: #323232;
            }
        """)

        layout = QHBoxLayout(self.block)
        layout.setContentsMargins(8, 1, 8, 1)
        layout.setSpacing(3)

        # Часы / минуты / секунды
        self.hours = PremiumLineEdit("hh", 10)
        self.minutes = PremiumLineEdit("mm", 59)
        self.seconds = PremiumLineEdit("ss", 59)

        self.fields = [self.hours, self.minutes, self.seconds]

        for f in self.fields:
            f.focusGained.connect(self._on_focus_in)
            f.valueChanged.connect(self._on_value_changed)

        # Добавляем виджеты в блок
        layout.addWidget(self.hours)
        layout.addWidget(self._colon())
        layout.addWidget(self.minutes)
        layout.addWidget(self._colon())
        layout.addWidget(self.seconds)

        outer.addWidget(self.block)
        outer.addStretch()

        self.setFocusPolicy(Qt.StrongFocus)

        self._update_display()

    # ───── Разделитель ":" ─────
    def _colon(self):
        lbl = QLabel(":")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedWidth(8)
        lbl.setStyleSheet("color:#aaa; background:transparent;")
        return lbl

    # ───── Логика ─────
    def _has_any_value(self):
        return any(f.value() > 0 for f in self.fields)

    def _update_display(self):
        has_value = self._has_any_value()

        for f in self.fields:
            if self._has_focus_inside:
                f.force_edit_mode()
            else:
                f.force_display_mode(has_value)

    def _on_focus_in(self):
        if not self._has_focus_inside:
            self._has_focus_inside = True
            self._update_display()

    def _on_value_changed(self, _):
        self._update_display()

    def _on_focus_changed(self, old, new):
        is_inside = new in self.fields

        # Если уход из таймера, заполняем пустые блоки нулями
        if self._has_focus_inside and not is_inside:
            self._fill_empty_with_zero()

        if is_inside != self._has_focus_inside:
            self._has_focus_inside = is_inside
            self._update_display()

    def _fill_empty_with_zero(self):
        for f in self.fields:
            if f.value() == 0 and not f._is_placeholder:
                f._apply_value()

    # ───── API ─────
    def get_seconds(self) -> int:
        return self.hours.value() * 3600 + self.minutes.value() * 60 + self.seconds.value()

    def is_active(self) -> bool:
        return self.get_seconds() > 0

    def reset(self):
        for f in self.fields:
            f.setValue(0)




class QualitySwitcher(QWidget):
    def __init__(self, values: list[str], initial: str):
        super().__init__()

        self.values = values
        self.index = values.index(initial)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(40)

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(40)

        self.label = QLabel(self.values[self.index])
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setFixedWidth(100)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.label)
        layout.addWidget(self.btn_next)

        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)

        self.btn_prev.clicked.connect(self.prev)
        self.btn_next.clicked.connect(self.next)

        self._update_buttons()

    def prev(self):
        if self.index > 0:
            self.index -= 1
            self._refresh()

    def next(self):
        if self.index < len(self.values) - 1:
            self.index += 1
            self._refresh()

    def _refresh(self):
        self.label.setText(self.values[self.index])
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.setEnabled(self.index > 0)
        self.btn_next.setEnabled(self.index < len(self.values) - 1)

    def get(self) -> str:
        return self.values[self.index]

    def set(self, value: str):
        if value in self.values:
            self.index = self.values.index(value)
            self._refresh()


class ExportFilenameInput(QWidget):
    valueChanged = Signal(str)

    def __init__(self, initial: str = "output"):
        super().__init__()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.lineedit = QLineEdit()
        self.lineedit.setText(initial)
        self.lineedit.setMinimumWidth(90)

        self.lineedit.textChanged.connect(self.valueChanged.emit)

        layout.addWidget(self.lineedit)

    def get(self) -> str:
        return self.lineedit.text()

    def set(self, value: str):
        self.lineedit.setText(value)