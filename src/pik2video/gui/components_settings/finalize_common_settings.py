# src/pik2video/gui/components_settings/finalize_common_settings.py

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QPushButton, QMenu, QFileDialog
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from pathlib import Path



class VideoFormatInput(QWidget):
    """
    Настройка формата видео. 
    Кнопка открывает выпадающее меню с доступными форматами.
    """

    valueChanged = Signal(str)

    def __init__(self, initial: str = "MP4"):
        super().__init__()

        self.current_format = initial
        self.allowed_formats = ["MP4", "MKV", "AVI", "MOV"]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        #self.label = QLabel("Формат видео:")
        self.btn = QPushButton(self.current_format)
        self.btn.setFocusPolicy(Qt.NoFocus)

        # Меню
        self.menu = QMenu(self)
        for fmt in self.allowed_formats:
            action = QAction(fmt, self)
            action.triggered.connect(lambda checked, f=fmt: self.set(f))
            self.menu.addAction(action)
        self.btn.setMenu(self.menu)

        #layout.addWidget(self.label)
        layout.addWidget(self.btn)

    def get(self) -> str:
        return self.current_format

    def set(self, fmt: str):
        if fmt not in self.allowed_formats:
            fmt = "MP4"
        self.current_format = fmt
        self.btn.setText(fmt)
        self.valueChanged.emit(fmt)

class ExportPathInput(QWidget):
    """
    Виджет выбора папки для сохранения видео.
    Выглядит как: [ Сохранить в: /путь/к/папке ] [ Обзор... ]
    """

    valueChanged = Signal(str)

    def __init__(self, controller, initial_path: str = ""):
        super().__init__()
        
        self.controller = controller
        self.translator = controller.get_translator() if controller else None

        if not initial_path:
            initial_path = str(Path.home() / "Desktop")

        self._current_path = initial_path

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # ─── Блок "Сохранить в: путь" ───────────────────
        self.path_block = QWidget()
        self.path_block.setStyleSheet("""
            QWidget {
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 4px;
            }
        """)
        self.path_block.setFixedHeight(28)

        block_layout = QHBoxLayout(self.path_block)
        block_layout.setContentsMargins(8, 4, 8, 4)
        block_layout.setSpacing(6)

        # Текст "Сохранить в:" (будет переведен)
        self.label = QLabel("")
        self.label.setStyleSheet("""
            background-color: transparent;
            border: none;
            color: #e0e0e0;
        """)

        # Путь
        self.path_label = QLabel(self._current_path)
        self.path_label.setStyleSheet("""
            background-color: #2a2a2a;
            border: none;
            border-radius: 3px;
            padding: 2px 6px;
            color: #a0c0ff;
            font-family: monospace;
            font-size: 11px;
        """)
        self.path_label.setMinimumWidth(200)

        block_layout.addWidget(self.label)
        block_layout.addWidget(self.path_label)
        block_layout.addStretch()

        # ─── Кнопка "Обзор..." ───────────────────────────
        self.browse_btn = QPushButton("")
        self.browse_btn.setFixedWidth(80)
        self.browse_btn.setFixedHeight(28)
        self.browse_btn.setStyleSheet("""
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
        self.browse_btn.clicked.connect(self._browse_folder)

        layout.addWidget(self.path_block)
        layout.addWidget(self.browse_btn)
        
        # Подключаем переводы
        if self.translator:
            self.setup_localization()
    
    def setup_localization(self):
        """Подключаем систему переводов"""
        self.translator.language_changed.connect(self.retranslate_ui)
        self.retranslate_ui()
    
    def retranslate_ui(self):
        """Обновляет тексты при смене языка"""
        self.label.setText(self.translator.tr("save_to_label"))
        self.browse_btn.setText(self.translator.tr("browse_button"))

    def _browse_folder(self):
        """Открыть диалог выбора папки"""
        folder = QFileDialog.getExistingDirectory(
            self,
            self.translator.tr("select_folder_dialog") if self.translator else "Выберите папку для сохранения",
            self._current_path
        )
        if folder:
            self._current_path = folder
            self.path_label.setText(folder)
            self.valueChanged.emit(folder)

    def get(self) -> str:
        """Вернуть текущий путь"""
        return self._current_path

    def set(self, path: str):
        """Установить путь"""
        if path:
            self._current_path = path
            self.path_label.setText(path)
            self.valueChanged.emit(path)