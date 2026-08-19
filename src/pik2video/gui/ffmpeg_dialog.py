# src/pik2video/gui/ffmpeg_dialog.py


from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton
from PySide6.QtCore import Qt


class FFmpegMissingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("FFmpeg не найден")
        self.setModal(True)
        self.setFixedWidth(300)

        layout = QVBoxLayout(self)

        label = QLabel(
            "FFmpeg не установлен.\n\n"
            "Без него запись невозможна.\n"
            "Установите FFmpeg и перезапустите приложение."
        )
        label.setAlignment(Qt.AlignCenter)

        btn = QPushButton("OK")
        btn.clicked.connect(self.accept)

        layout.addWidget(label)
        layout.addWidget(btn)