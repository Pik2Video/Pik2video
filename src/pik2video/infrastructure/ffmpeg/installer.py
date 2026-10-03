# src/pik2video/infrastructure/ffmpeg/installer.py

import os
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import ClassVar, Optional, Tuple

from PySide6.QtCore import QObject, Signal

from src.pik2video.infrastructure.system.platform_detector import get_full_info


class FFmpegInstaller(QObject):
    """
    Скачивает и устанавливает FFmpeg.
    Использует сигналы для обновления прогресса в GUI.
    """

    progress_updated = Signal(int)   # 0-100
    status_updated = Signal(str)     # текст статуса
    finished = Signal(bool, str)     # (успех, сообщение)

    # URL и суффикс для каждой платформы
    # Кортеж: (url, suffix) где suffix - расширение файла (например, .zip, .tar.xz)
    URLS: ClassVar[dict] = {
        'macos': {
            'arm64': ('https://evermeet.cx/ffmpeg/get/zip', '.zip'),
            'x86_64': ('https://evermeet.cx/ffmpeg/get/zip', '.zip'),
        },
        'windows': {
            'x86_64': ('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', '.zip'),
        },
        'linux': {
            'x86_64': ('https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz', '.tar.xz'),
            'arm64': ('https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-arm64-static.tar.xz', '.tar.xz'),
        }
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.platform_info = get_full_info()
        self._cancel = False

    def install(self):
        """Основной метод установки. Запускается в отдельном потоке."""
        try:
            self.status_updated.emit("Определение папки для установки...")
            target_dir = self._get_target_dir()
            if not target_dir:
                self.finished.emit(False, "Не удалось определить целевую папку")
                return

            ffmpeg_path = target_dir / self._get_executable_name()
            if ffmpeg_path.exists():
                self.progress_updated.emit(100)
                self.status_updated.emit("FFmpeg уже установлен")
                self.finished.emit(True, "FFmpeg уже установлен")
                return

            self.status_updated.emit("Загрузка FFmpeg...")
            self.progress_updated.emit(10)
            archive_path = self._download_ffmpeg()
            if self._cancel:
                self.finished.emit(False, "Установка отменена пользователем")
                return

            self.progress_updated.emit(50)

            self.status_updated.emit("Распаковка...")
            extract_dir = self._extract_archive(archive_path)
            if self._cancel:
                self.finished.emit(False, "Установка отменена пользователем")
                return

            self.progress_updated.emit(70)

            self.status_updated.emit("Копирование файлов...")
            executable = self._find_executable(extract_dir)
            if not executable:
                self.finished.emit(False, "Не удалось найти исполняемый файл ffmpeg в архиве")
                return

            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(executable, ffmpeg_path)
            self.progress_updated.emit(85)

            self.status_updated.emit("Настройка прав доступа...")
            if self._is_unix():
                os.chmod(ffmpeg_path, 0o755)

            self.progress_updated.emit(100)
            self.status_updated.emit("FFmpeg успешно установлен")
            self.finished.emit(True, "Установка завершена")

        except Exception as e:
            self.finished.emit(False, f"Ошибка установки: {e!s}")
        finally:
            # Очистка временных файлов
            if 'archive_path' in locals() and archive_path and archive_path.exists():
                try:
                    archive_path.unlink()
                except Exception:
                    pass
            if 'extract_dir' in locals() and extract_dir and extract_dir.exists():
                try:
                    shutil.rmtree(extract_dir)
                except Exception:
                    pass

    def cancel(self):
        """Отмена установки"""
        self._cancel = True

    # ---- Вспомогательные методы ----

    def _get_target_dir(self) -> Optional[Path]:
        """Возвращает папку для установки (куда копируем ffmpeg)"""
        system = self.platform_info['system']
        if system == 'Darwin':  # macOS
            return Path.home() / 'Library' / 'Application Support' / 'Pik2Video'
        elif system == 'Windows':
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / 'Pik2Video'
            else:
                return Path.home() / 'AppData' / 'Roaming' / 'Pik2Video'
        elif system == 'Linux':
            return Path.home() / '.local' / 'share' / 'Pik2Video'
        else:
            return None

    def _get_executable_name(self) -> str:
        """Имя исполняемого файла (с расширением для Windows)"""
        if self.platform_info['system'] == 'Windows':
            return 'ffmpeg.exe'
        else:
            return 'ffmpeg'

    def _is_unix(self) -> bool:
        return self.platform_info['system'] in ('Darwin', 'Linux')

    def _get_download_url(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Возвращает кортеж (url, suffix) для текущей платформы.
        suffix — расширение файла (например, '.zip' или '.tar.xz').
        """
        info = self.platform_info
        os_type = info['os']
        arch = info['architecture']

        if os_type == 'macos':
            if arch == 'arm64':
                return self.URLS['macos']['arm64']
            elif arch == 'x86_64':
                return self.URLS['macos']['x86_64']
            else:
                return self.URLS['macos']['x86_64']  # fallback
        elif os_type == 'windows':
            return self.URLS['windows']['x86_64']
        elif os_type == 'linux':
            if arch == 'arm64':
                return self.URLS['linux']['arm64']
            else:
                return self.URLS['linux']['x86_64']
        else:
            return None, None

    def _download_ffmpeg(self) -> Optional[Path]:
        """
        Скачивает архив FFmpeg во временный файл.
        Возвращает путь к скачанному файлу.
        """
        import ssl
        import urllib.request

        url, suffix = self._get_download_url()
        if not url:
            raise ValueError("Не удалось определить URL для скачивания")

        # Создаём временный файл с правильным расширением
        fd, temp_path = tempfile.mkstemp(suffix=suffix)
        os.close(fd)
        temp_path = Path(temp_path)

        # Настройка SSL (для упрощения — отключаем проверку)
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        # Добавляем User-Agent, чтобы сервер вернул файл, а не HTML
        opener = urllib.request.build_opener()
        opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')]
        urllib.request.install_opener(opener)

        def report_progress(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, int(block_num * block_size * 100 / total_size))
                # Прогресс от 10 до 50%
                self.progress_updated.emit(10 + int(percent * 0.4))

        try:
            urllib.request.urlretrieve(url, str(temp_path), reporthook=report_progress)
            return temp_path
        except Exception as e:
            raise RuntimeError(f"Ошибка загрузки: {e}") from e

    def _extract_archive(self, archive_path: Path) -> Path:
        """Распаковывает архив (ZIP или TAR.XZ) во временную папку."""
        extract_dir = Path(tempfile.mkdtemp())
        suffix = archive_path.suffix

        if suffix == '.zip':
            with zipfile.ZipFile(archive_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
        elif suffix == '.tar.xz':
            with tarfile.open(archive_path, 'r:xz') as tar:
                tar.extractall(extract_dir)
        else:
            raise ValueError(f"Неподдерживаемый формат архива: {suffix}")

        return extract_dir

    def _find_executable(self, extract_dir: Path) -> Optional[Path]:
        """
        Ищет исполняемый файл ffmpeg в распакованной папке.
        Возвращает путь к нему или None.
        """
        executable_name = self._get_executable_name()
        for root, _dirs, files in os.walk(extract_dir):
            if executable_name in files:
                return Path(root) / executable_name
        return None

    def _test_ffmpeg(self, ffmpeg_path: Path) -> bool:
        """Проверяет, что ffmpeg запускается (вызов -version)."""
        try:
            result = subprocess.run(
                [str(ffmpeg_path), '-version'],
                capture_output=True,
                check=False,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
