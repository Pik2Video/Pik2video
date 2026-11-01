# src/pik2video/gui/widgets/audio_settings.py

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)


class AudioSourceSelector(QWidget):
    """
    Выбор источников звука: микрофон и/или системный звук.
    Оба могут быть включены одновременно.
    """

    valueChanged = Signal(list)   # список активных источников: ["mic", "system"]

    MIC = "mic"
    SYSTEM = "system"

    def __init__(self, initial: list = None, parent=None):
        super().__init__(parent)
        if initial is None:
            initial = []                                        # пустой список — тоже валидное значение

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self.cb_mic = QCheckBox("Микрофон")                        # чекбокс записи с микрофона
        self.cb_mic.setChecked(self.MIC in initial)
        self.cb_mic.toggled.connect(self._on_toggled)

        self.cb_system = QCheckBox("Системный звук")               # чекбокс записи системного звука
        self.cb_system.setChecked(self.SYSTEM in initial)
        self.cb_system.toggled.connect(self._on_toggled)

        layout.addWidget(self.cb_mic)
        layout.addWidget(self.cb_system)
        layout.addStretch()

    def _on_toggled(self, _checked):
        self.valueChanged.emit(self.get())                         # сообщаем наружу при смене любого чекбокса

    def get(self) -> list:
        sources = []
        if self.cb_mic.isChecked():
            sources.append(self.MIC)
        if self.cb_system.isChecked():
            sources.append(self.SYSTEM)
        return sources

    def set(self, sources: list):
        sources = sources or []
        self.cb_mic.blockSignals(True)
        self.cb_system.blockSignals(True)
        self.cb_mic.setChecked(self.MIC in sources)
        self.cb_system.setChecked(self.SYSTEM in sources)
        self.cb_mic.blockSignals(False)
        self.cb_system.blockSignals(False)


class AudioDeviceSelector(QWidget):
    """
    Выбор устройства ввода (микрофона) из списка доступных.
    Заполняется позже — на этапе подключения аудио-движка.
    """

    valueChanged = Signal(str)

    def __init__(self, initial: str = "", parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.combo = QComboBox()                                   # выпадающий список устройств
        self.combo.setMinimumWidth(220)
        self.combo.currentIndexChanged.connect(self._on_changed)

        layout.addWidget(self.combo)

        self._initial = initial
        self.set_devices([("", "По умолчанию")])                   # пока только дефолтное устройство

    def _on_changed(self, _index):
        self.valueChanged.emit(self.get())                         # сообщаем выбранное устройство

    def set_devices(self, devices: list):
        """devices — список кортежей (id, отображаемое_имя)."""
        self.combo.blockSignals(True)
        self.combo.clear()
        for device_id, name in devices:
            self.combo.addItem(name, device_id)
        if self._initial:
            idx = self.combo.findData(self._initial)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def get(self) -> str:
        return self.combo.currentData() or ""

    def set(self, device_id: str):
        idx = self.combo.findData(device_id)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)

class SampleRateSelector(QWidget):
    """Выбор частоты дискретизации: 44100 или 48000 Гц."""

    valueChanged = Signal(int)

    RATES = [(44100, "44.1 кГц"), (48000, "48 кГц")]           # варианты частот

    def __init__(self, initial: int = 48000, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(140)
        for rate, label in self.RATES:
            self.combo.addItem(label, rate)
        idx = self.combo.findData(initial)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.currentIndexChanged.connect(self._on_changed)

        layout.addWidget(self.combo)

    def _on_changed(self, _index):
        self.valueChanged.emit(self.get())

    def get(self) -> int:
        return self.combo.currentData() or 48000

    def set(self, value: int):
        idx = self.combo.findData(value)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)


class ChannelsSelector(QWidget):
    """Выбор числа каналов: моно или стерео."""

    valueChanged = Signal(int)

    CHANNELS = [(1, "Моно"), (2, "Стерео")]                     # варианты каналов

    def __init__(self, initial: int = 2, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.combo = QComboBox()
        self.combo.setMinimumWidth(140)
        for ch, label in self.CHANNELS:
            self.combo.addItem(label, ch)
        idx = self.combo.findData(initial)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)
        self.combo.currentIndexChanged.connect(self._on_changed)

        layout.addWidget(self.combo)

    def _on_changed(self, _index):
        self.valueChanged.emit(self.get())

    def get(self) -> int:
        return self.combo.currentData() or 2

    def set(self, value: int):
        idx = self.combo.findData(value)
        if idx >= 0:
            self.combo.setCurrentIndex(idx)