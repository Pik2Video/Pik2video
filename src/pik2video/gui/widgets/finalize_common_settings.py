# src/pik2video/gui/widgets/finalize_common_settings.py

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
        self.allowed_formats = ["MP4", "MKV", "AVI", "MOV", "GIF"]

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




class ResolutionSelector(QWidget):
    """Выбор разрешения: Оригинал / 1080p / 720p / 480p"""
    
    valueChanged = Signal(str)
    
    RESOLUTIONS = {
        "original": "Оригинал",
        "1080p": "1080p",
        "720p": "720p",
        "480p": "480p",
    }
    
    def __init__(self, initial: str = "original"):
        super().__init__()
        self.current = initial
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn = QPushButton(self.RESOLUTIONS.get(initial, "Оригинал"))
        self.btn.setFocusPolicy(Qt.NoFocus)
        
        self.menu = QMenu(self)
        for key, label in self.RESOLUTIONS.items():
            action = QAction(label, self)
            action.triggered.connect(lambda checked, k=key: self.set(k))
            self.menu.addAction(action)
        self.btn.setMenu(self.menu)
        
        layout.addWidget(self.btn)
    
    def get(self) -> str:
        return self.current
    
    def set(self, value: str):
        if value in self.RESOLUTIONS:
            self.current = value
            self.btn.setText(self.RESOLUTIONS[value])
            self.valueChanged.emit(value)


class BitrateSelector(QWidget):
    """Битрейт: авто или вручную"""
    
    valueChanged = Signal(str, str)  # mode, value
    
    def __init__(self, mode: str = "auto", value: str = "4M"):
        super().__init__()
        self._mode = mode
        self._value = value
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        
        # Кнопка авто/вручную
        self.btn_mode = QPushButton("Авто" if mode == "auto" else "Вручную")
        self.btn_mode.setFixedWidth(80)
        self.btn_mode.setFocusPolicy(Qt.NoFocus)
        
        self.menu = QMenu(self)
        for m in ["auto", "manual"]:
            label = "Авто" if m == "auto" else "Вручную"
            action = QAction(label, self)
            action.triggered.connect(lambda checked, mode=m: self._set_mode(mode))
            self.menu.addAction(action)
        self.btn_mode.setMenu(self.menu)
        
        # Поле ввода значения (только для ручного режима)
        self.value_input = QLineEdit()
        self.value_input.setText(value)
        self.value_input.setFixedWidth(60)
        self.value_input.setAlignment(Qt.AlignCenter)
        self.value_input.setVisible(mode == "manual")
        self.value_input.textChanged.connect(self._on_value_changed)
        
        layout.addWidget(self.btn_mode)
        layout.addWidget(self.value_input)
        layout.addStretch()
    
    def _set_mode(self, mode: str):
        self._mode = mode
        self.btn_mode.setText("Авто" if mode == "auto" else "Вручную")
        self.value_input.setVisible(mode == "manual")
        self.valueChanged.emit(self._mode, self._value)
    
    def _on_value_changed(self, text: str):
        self._value = text
        self.valueChanged.emit(self._mode, self._value)
    
    def get_mode(self) -> str:
        return self._mode
    
    def get_value(self) -> str:
        return self._value


class RotationSelector(QWidget):
    """Поворот: 0° / 90° / 180° / 270°"""
    
    valueChanged = Signal(int)
    
    ANGLES = {0: "0°", 90: "90°", 180: "180°", 270: "270°"}
    
    def __init__(self, initial: int = 0):
        super().__init__()
        self.current = initial
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        self.btn = QPushButton(self.ANGLES.get(initial, "0°"))
        self.btn.setFocusPolicy(Qt.NoFocus)
        
        self.menu = QMenu(self)
        for angle, label in self.ANGLES.items():
            action = QAction(label, self)
            action.triggered.connect(lambda checked, a=angle: self.set(a))
            self.menu.addAction(action)
        self.btn.setMenu(self.menu)
        
        layout.addWidget(self.btn)
    
    def get(self) -> int:
        return self.current
    
    def set(self, angle: int):
        if angle in self.ANGLES:
            self.current = angle
            self.btn.setText(self.ANGLES[angle])
            self.valueChanged.emit(angle)