# src/pik2video/gui/progress_dialog.py

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout

from src.pik2video.infrastructure.ffmpeg.installer import FFmpegInstaller


class InstallationWorker(QThread):
    finished = Signal(bool, str)
    progress = Signal(int)
    status = Signal(str)

    def __init__(self, installer):
        super().__init__()
        self.installer = installer
        self._is_cancelled = False

    def run(self):
        self.installer.progress_updated.connect(self.progress.emit)
        self.installer.status_updated.connect(self.status.emit)
        self.installer.finished.connect(self._on_installer_finished)
        self.installer.install()

    def _on_installer_finished(self, success, message):
        self.finished.emit(success, message)
        self.quit()

    def cancel(self):
        self.installer.cancel()


class ProgressDialog(QDialog):
    installation_completed = Signal(bool)

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self.translator = controller.get_translator() if controller else None
        self._success = False

        self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        self.setFixedWidth(400)
        self.setMinimumHeight(180)

        self._setup_ui()
        self._apply_translations()
        self.adjustSize()
        self.setFixedSize(self.size())

        self.installer = FFmpegInstaller()
        self.worker = InstallationWorker(self.installer)

        self.worker.progress.connect(self._on_progress)
        self.worker.status.connect(self._on_status)
        self.worker.finished.connect(self._on_installation_finished)

        self.worker.start()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setStyleSheet("color: #e0e0e0;")
        layout.addWidget(self.title_label)

        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("color: #aaa; font-size: 11px;")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #444;
                border-radius: 4px;
                background: #2a2a2a;
                text-align: center;
                color: #e0e0e0;
            }
            QProgressBar::chunk {
                background: #3a7a3a;
                border-radius: 4px;
            }
        """)
        layout.addWidget(self.progress_bar)

        self.action_btn = QPushButton()
        self.action_btn.setFixedWidth(120)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 6px 12px;
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
        self.action_btn.clicked.connect(self._on_action_clicked)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.action_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    def _apply_translations(self):
        if self.translator:
            self.setWindowTitle(self.translator.tr("install_progress_title"))
            self.title_label.setText(self.translator.tr("installing_ffmpeg"))
            self.action_btn.setText(self.translator.tr("cancel_button"))
        else:
            self.setWindowTitle("Installing FFmpeg")
            self.title_label.setText("Installing FFmpeg...")
            self.action_btn.setText("Cancel")

    def _on_progress(self, value):
        self.progress_bar.setValue(value)

    def _on_status(self, text):
        self.status_label.setText(text)

    def _on_installation_finished(self, success, message):
        self._success = success
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText("FFmpeg успешно установлен!\nПерезапустите приложение, чтобы начать работу.")
            self.title_label.setText("Установка завершена")
            self.action_btn.setText("Перезапустить")
            self.installation_completed.emit(True)
            self.accept()
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a7a2a;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    color: white;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #3a9a3a;
                }
                QPushButton:pressed {
                    background-color: #1a5a1a;
                }
            """)
        else:
            self.status_label.setText(f"Ошибка: {message}")
            self.title_label.setText("Ошибка установки")
            self.action_btn.setText("Повторить")
            self.action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #8a2a2a;
                    border: none;
                    border-radius: 6px;
                    padding: 6px 12px;
                    color: white;
                    font-size: 13px;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background-color: #aa3a3a;
                }
                QPushButton:pressed {
                    background-color: #6a1a1a;
                }
            """)
        self.action_btn.setEnabled(True)

    def _on_action_clicked(self):
        if self._success:
            # Перезапускаем приложение
            self._restart_app()
        else:
            # Повторная попытка
            self._reset_ui()
            self.worker = InstallationWorker(self.installer)
            self.worker.progress.connect(self._on_progress)
            self.worker.status.connect(self._on_status)
            self.worker.finished.connect(self._on_installation_finished)
            self.worker.start()

    def _restart_app(self):
        """Перезапускает приложение"""
        import subprocess
        import sys
        self.accept()
        # Завершаем поток, если он ещё работает (хотя он уже завершён)
        if self.worker.isRunning():
            self.worker.quit()
            self.worker.wait()
        QApplication.quit()
        # Запускаем новый экземпляр
        subprocess.Popen([sys.executable] + sys.argv)
        sys.exit(0)

    def _reset_ui(self):
        self.progress_bar.setValue(0)
        self.status_label.setText("Повторная попытка...")
        self.title_label.setText("Установка FFmpeg")
        self.action_btn.setText("Отмена")
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #4a4a4a;
                border: 1px solid #666;
                border-radius: 6px;
                padding: 6px 12px;
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
        self.action_btn.setEnabled(True)
        self._success = False

    def closeEvent(self, event):
        if self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait()
        event.accept()
