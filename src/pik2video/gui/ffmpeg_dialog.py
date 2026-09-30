from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QApplication
)
from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont

from src.pik2video.gui.progress_dialog import ProgressDialog


class FFmpegMissingDialog(QDialog):
    """
    Диалог, показываемый при отсутствии FFmpeg в системе.
    """

    FFMPEG_URL = "https://ffmpeg.org/download.html"

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self.translator = controller.get_translator() if controller else None
        self._installation_dialog = None

        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)

        self._setup_ui()
        self._apply_translations()
        self.adjustSize()
        self.setFixedSize(self.size())

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 24)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(12)

        self.icon_label = QLabel("⚠️")
        self.icon_label.setStyleSheet("font-size: 48px;")
        self.icon_label.setAlignment(Qt.AlignCenter)

        header_layout.addWidget(self.icon_label)
        header_layout.addStretch()

        self.header_label = QLabel()
        self.header_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self.header_label.setFont(font)
        self.header_label.setStyleSheet("color: #ff6b6b;")

        header_layout.addWidget(self.header_label)
        header_layout.addStretch()

        layout.addLayout(header_layout)

        self.message_label = QLabel()
        self.message_label.setAlignment(Qt.AlignLeft)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 12px;
                background: transparent;
                padding: 4px;
            }
        """)
        layout.addWidget(self.message_label)

        # Контейнер для кнопок, чтобы управлять растяжением
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        self.install_btn = QPushButton()
        self.install_btn.setFixedWidth(160)
        self.install_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a7a2a;
                border: none;
                border-radius: 6px;
                padding: 8px 12px;
                color: white;
                font-weight: bold;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #3a9a3a;
            }
            QPushButton:pressed {
                background-color: #1a5a1a;
            }
        """)
        self.install_btn.clicked.connect(self._start_installation)

        self.cancel_btn = QPushButton()
        self.cancel_btn.setFixedWidth(100)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 8px 12px;
                color: white;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #3a3a3a;
            }
        """)
        self.cancel_btn.clicked.connect(self.reject)

        button_layout.addWidget(self.install_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Сохраняем layout кнопок, чтобы можно было менять выравнивание
        self.button_layout = button_layout

        # Устанавливаем начальное состояние
        self._set_buttons_initial()

    def _set_buttons_initial(self):
        """Начальное состояние: две кнопки"""
        self.install_btn.setVisible(True)
        self.install_btn.setFixedWidth(160)
        self.install_btn.setEnabled(True)
        self.cancel_btn.setVisible(True)
        # Восстанавливаем обработчик
        self.install_btn.clicked.disconnect()
        self.install_btn.clicked.connect(self._start_installation)

    def _set_buttons_installing(self):
        """Состояние установки: только кнопка "Установка..." (центрированная)"""
        self.cancel_btn.setVisible(False)
        self.install_btn.setFixedWidth(200)  # растягиваем
        self.install_btn.setEnabled(False)

    def _set_buttons_success(self):
        """После успеха: только кнопка "Перезапустить приложение" (широкая)"""
        self.cancel_btn.setVisible(False)
        self.install_btn.setFixedWidth(200)
        self.install_btn.setEnabled(True)
        self.install_btn.setText("Перезапустить приложение")
        # Меняем обработчик
        self.install_btn.clicked.disconnect()
        self.install_btn.clicked.connect(self._restart_app)

    def _start_installation(self):
        """Запускает процесс установки FFmpeg через ProgressDialog"""
        self.install_btn.setText("Установка...")
        self._set_buttons_installing()

        self._installation_dialog = ProgressDialog(self, self.controller)
        self._installation_dialog.installation_completed.connect(self._on_installation_completed)
        self._installation_dialog.finished.connect(self._on_installation_dialog_closed)
        self._installation_dialog.show()

    def _on_installation_completed(self, success):
        if success:
            # Установка успешна – обновляем диалог
            self.message_label.setText(
                "FFmpeg успешно установлен.\n\n"
                "Нажмите кнопку ниже, чтобы перезапустить приложение."
            )
            self.header_label.setText("✅ FFmpeg установлен")
            self.icon_label.setStyleSheet("font-size: 48px; color: #2a7a2a;")
            self._set_buttons_success()
        else:
            # Ошибка – возвращаем начальное состояние
            self._set_buttons_initial()
            self.install_btn.setText(self.translator.tr("ffmpeg_missing_install") if self.translator else "Install FFmpeg")
            self._show_error("Не удалось установить FFmpeg. Попробуйте вручную или проверьте интернет-соединение.")

    def _restart_app(self):
        """Закрывает приложение (пользователь запустит его заново)"""
        QApplication.quit()

    def _on_installation_dialog_closed(self):
        self._installation_dialog = None

    def _show_error(self, message):
        from PySide6.QtWidgets import QMessageBox
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Critical)
        msg.setWindowTitle("Ошибка")
        msg.setText(message)
        msg.exec()

    def _apply_translations(self):
        if self.translator:
            self.setWindowTitle(self.translator.tr("ffmpeg_missing_title"))
            self.header_label.setText(self.translator.tr("ffmpeg_missing_header"))
            self.message_label.setText(self.translator.tr("ffmpeg_missing_message"))
            self.install_btn.setText(self.translator.tr("ffmpeg_missing_install"))
            self.cancel_btn.setText(self.translator.tr("ffmpeg_missing_cancel"))
        else:
            self.setWindowTitle("FFmpeg not found")
            self.header_label.setText("FFmpeg is missing")
            self.message_label.setText(
                "FFmpeg is not installed.\n\n"
                "Recording is impossible without it.\n"
                "Install FFmpeg and restart the application."
            )
            self.install_btn.setText("Install FFmpeg")
            self.cancel_btn.setText("Cancel")

    def showEvent(self, event):
        self._apply_translations()
        super().showEvent(event)