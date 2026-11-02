# src/pik2video/gui/editor/timeline/marker_menu.py
"""
Всплывающее меню инструментов метки.

Открывается у кнопки-карандаша на дорожке таймлайна.
4 кнопки в ряд: |], |[, ][ , ✕ (закрыть).

Каждая кнопка инструмента показывает свой курсор (символ), крестик — палец.
Клик на крестик → сигнал cursor_reset (сбросить активный инструмент).
"""

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


# (отображаемый текст, внутренний код инструмента, tooltip)
TOOLS = [
    ("|]", "]", "Обрезать правую часть (закрыть справа)"),
    ("|[", "[", "Обрезать левую часть (закрыть слева)"),
    ("|][|", "][", "Вставка (разрыв)"),
]


class MarkerMenu(QWidget):
    """Горизонтальное всплывающее меню с инструментами метки."""

    tool_selected = Signal(str)   # "]", "[", "]["
    cursor_reset = Signal()       # клик на крестик — сбросить активный инструмент

    def __init__(self, cursor_factory, active_tool: str | None = None, parent=None):
        """cursor_factory — callable(str) -> QCursor (берём из TimelineWidget.make_tool_cursor)."""
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setAttribute(Qt.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self._cursor_factory = cursor_factory

        self.setStyleSheet("""
            QWidget#markerMenuRoot {
                background-color: #1e1e1e;
                border: 1px solid #555;
                border-radius: 0px;
            }
            QPushButton {
                background-color: #2a2a2a;
                border: 1px solid #444;
                border-radius: 0px;
                color: #e0e0e0;
                padding: 4px 10px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
                border-color: #666;
            }
            QPushButton:pressed {
                background-color: #151515;
            }
            QPushButton#closeBtn {
                color: #ff5555;
                font-size: 14px;
                padding: 4px 10px;
            }
            QPushButton#closeBtn:hover {
                background-color: #4a1a1a;
                border-color: #a04040;
            }
            QPushButton[active="true"] {
                background-color: #3a2f10;
                border: 1px solid #8a6f2a;
                color: #ffcc66;
            }
        """)

        # Курсор меню по умолчанию — активный инструмент (для промежутков между кнопками).
        # Если инструмента нет — курсор остаётся стандартным (стрелка).
        if active_tool:
            self.setCursor(self._cursor_factory(active_tool))

        root = QWidget(self)
        root.setObjectName("markerMenuRoot")

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QHBoxLayout(root)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._tool_buttons = {}
        for text, kind, tooltip in TOOLS:
            btn = QPushButton(text)
            btn.setToolTip(tooltip)
            # Курсор кнопки инструмента — символ этого инструмента
            btn.setCursor(self._cursor_factory(kind))
            btn.clicked.connect(lambda checked=False, k=kind: self._on_tool(k))
            layout.addWidget(btn)
            self._tool_buttons[kind] = btn

        # Подсветить активный инструмент, если он выбран
        self._highlight_active(active_tool)

        close_btn = QPushButton("✕")
        close_btn.setObjectName("closeBtn")
        close_btn.setToolTip("Закрыть меню")
        # Курсор крестика — палец
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.clicked.connect(self._on_close_clicked)
        layout.addWidget(close_btn)

    def _highlight_active(self, kind: str | None):
        """Подсветить активную кнопку, снять подсветку с остальных."""
        for k, btn in self._tool_buttons.items():
            btn.setProperty("active", "true" if k == kind else "false")
            # Переприменить стиль — Qt не всегда обновляет по property автоматически
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    def _on_tool(self, kind: str):
        """Пользователь выбрал инструмент — эмитим сигнал и немедленно скрываем меню.

        Qt.Popup перехватывает следующий клик вне себя, даже если уже вызван close().
        Поэтому сначала hide() (синхронно), потом close() через QTimer.
        """
        self.tool_selected.emit(kind)
        self.hide()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.close)

    def _on_close_clicked(self):
        self.cursor_reset.emit()
        self.close()

    def open_at(self, global_pos: QPoint):
        """Показать меню так, чтобы его левый верхний угол был в global_pos."""
        self.adjustSize()
        screen = self.screen().availableGeometry() if self.screen() else None
        x, y = global_pos.x(), global_pos.y()
        w, h = self.width(), self.height()
        if screen is not None:
            if x + w > screen.right():
                x = screen.right() - w - 4
            if y + h > screen.bottom():
                y = screen.bottom() - h - 4
        self.move(x, y)
        self.show()
        self.setFocus()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
