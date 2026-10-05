# src/pik2video/gui/editor/export_service.py
"""
Сборка и запуск команды FFmpeg.

Отвечает только за:
- построение списка аргументов
- вычисление выходного пути
- запуск FFmpeg через QProcess
- парсинг прогресса из stderr
- сигналы: started / progress / finished

Не знает:
- про виджеты
- про EditorState (принимает параметры через build_command)
"""

import logging
import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, Signal

from .state import EditorState

logger = logging.getLogger(__name__)


FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

FORMAT_EXTENSIONS = {
    "MP4": ".mp4",
    "MKV": ".mkv",
    "AVI": ".avi",
    "MOV": ".mov",
    "GIF": ".gif",
}

RESOLUTION_HEIGHT = {
    "original": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
}

ROTATION_FILTER = {
    0: None,
    90: "transpose=1",
    180: "transpose=1,transpose=1",
    270: "transpose=2",
}

ASPECT_RATIOS = {
    "16:9": (16, 9),
    "9:16": (9, 16),
    "1:1":  (1, 1),
    "4:5":  (4, 5),
    "4:3":  (4, 3),
}


class ExportService(QObject):
    """Собирает команду и запускает FFmpeg."""

    export_started = Signal()
    export_progress = Signal(int)          # 0..100
    export_finished = Signal(bool, str)    # успех, сообщение

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._duration = 0.0
        self._output_path = None

    # ── Публичный API ──

    def start_export(self, state: EditorState):
        """Собрать команду и запустить FFmpeg."""
        if self._process is not None:
            logger.warning("Экспорт уже запущен")
            return

        try:
            args = self.build_command(state)
            output = self.get_output_path(state)
        except Exception as e:
            logger.error(f"Ошибка сборки команды: {e}")
            self.export_finished.emit(False, str(e))
            return

        # Создать папку экспорта
        output.parent.mkdir(parents=True, exist_ok=True)

        self._output_path = output
        self._duration = self._get_export_duration(state)

        logger.info(f"Запуск FFmpeg: {' '.join(args)}")

        self._process = QProcess(self)
        self._process.setProcessChannelMode(QProcess.MergedChannels)
        self._process.readyReadStandardOutput.connect(self._on_output)
        self._process.finished.connect(self._on_finished)
        self._process.errorOccurred.connect(self._on_error)

        self.export_started.emit()
        self._process.start(args[0], args[1:])

    def cancel(self):
        """Прервать процесс."""
        if self._process is not None:
            logger.info("Экспорт отменён пользователем")
            self._process.kill()
            self._process.waitForFinished(2000)

    def is_running(self) -> bool:
        return self._process is not None

    # ── Сборка команды ──

    def build_command(self, state: EditorState) -> list:
        input_path = state.get_video_path()
        if not input_path:
            raise ValueError("Нет активного видеофайла")

        args = [FFMPEG_BIN, "-y", "-i", input_path]

        start, end = state.get_trim()
        duration = state.get_video_duration()
        if start > 0:
            args += ["-ss", f"{start:.3f}"]
        if end > 0 and (duration <= 0 or end < duration):
            args += ["-to", f"{end:.3f}"]


        filters = []

        # 1. Rotation
        rot_filter = ROTATION_FILTER.get(state.get_rotation())
        if rot_filter:
            filters.append(rot_filter)

        # 2. Aspect (crop / pad)
        aspect_filter = self._build_aspect_filter(state)
        if aspect_filter:
            filters.append(aspect_filter)

        # 3. Resolution
        height = RESOLUTION_HEIGHT.get(state.get_resolution())
        if height:
            filters.append(f"scale=-2:{height}")

        # 4. Speed
        speed = state.get_speed()
        if speed != 1.0:
            filters.append(f"setpts=PTS/{speed}")

        if filters:
            args += ["-vf", ",".join(filters)]

        if state.get_format() != "GIF":
            args += ["-c:v", "libx264"]
            if state.get_bitrate_mode() == "manual":
                args += ["-b:v", state.get_bitrate_value()]
            else:
                args += ["-crf", "23"]
            args += ["-pix_fmt", "yuv420p"]

        if state.get_format() != "GIF":
            args += ["-c:a", "aac", "-b:a", "128k"]
            speed = state.get_speed()
            if speed != 1.0:
                args += ["-af", self._build_atempo(speed)]

        args.append(str(self.get_output_path(state)))
        return args

    def get_output_path(self, state: EditorState) -> Path:
        base = state.get_export_path()
        if not base:
            base = str(Path.home() / "Desktop" / "output_file")
        base_dir = Path(base)

        name = state.get_export_filename() or "output"
        ext = FORMAT_EXTENSIONS.get(state.get_format(), ".mp4")

        final = base_dir / f"{name}{ext}"
        if final.exists():
            counter = 1
            while True:
                candidate = base_dir / f"{name}_{counter}{ext}"
                if not candidate.exists():
                    final = candidate
                    break
                counter += 1
        return final

    def _get_export_duration(self, state: EditorState) -> float:
        """Длительность экспорта с учётом трима и скорости."""
        start, end = state.get_trim()
        duration = state.get_video_duration()
        if duration <= 0:
            return 0.0
        end = end if end > 0 else duration
        length = max(0.0, end - start)
        speed = state.get_speed()
        if speed > 0:
            length /= speed
        return length

    # ── Парсинг прогресса ──

    def _on_output(self):
        if self._process is None:
            return

        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="ignore")

        for line in data.splitlines():
            # FFmpeg пишет "time=00:00:05.23" в строке прогресса
            if "time=" not in line:
                continue
            try:
                time_part = line.split("time=")[1].split()[0]
                h, m, s = time_part.split(":")
                seconds = int(h) * 3600 + int(m) * 60 + float(s)
                if self._duration > 0:
                    percent = min(100, int(seconds / self._duration * 100))
                    self.export_progress.emit(percent)
            except Exception:
                pass

    def _on_finished(self, exit_code: int, _exit_status):
        success = exit_code == 0
        output = str(self._output_path) if self._output_path else ""

        if success:
            logger.info(f"Экспорт завершён: {output}")
            self.export_finished.emit(True, output)
        else:
            logger.error(f"FFmpeg завершился с кодом {exit_code}")
            self.export_finished.emit(False, f"FFmpeg завершился с кодом {exit_code}")

        self._process = None
        self._output_path = None

    def _on_error(self, error):
        logger.error(f"Ошибка QProcess: {error}")
        self.export_finished.emit(False, f"Ошибка процесса: {error}")
        self._process = None
        self._output_path = None

    # ── Утилиты ──

    def _build_atempo(self, speed: float) -> str:
        if 0.5 <= speed <= 2.0:
            return f"atempo={speed}"

        if speed < 0.5:
            parts = []
            remaining = speed
            while remaining < 0.5:
                parts.append("atempo=0.5")
                remaining /= 0.5
            parts.append(f"atempo={remaining}")
            return ",".join(parts)

        parts = []
        remaining = speed
        while remaining > 2.0:
            parts.append("atempo=2.0")
            remaining /= 2.0
        parts.append(f"atempo={remaining}")
        return ",".join(parts)


    def _build_aspect_filter(self, state: EditorState) -> str:
        """Собрать фильтр crop/pad по пресету кадра."""
        preset = state.get_aspect_preset()
        if preset == "original" or preset not in ASPECT_RATIOS:
            return ""

        src_w, src_h = state.get_source_resolution()
        if src_w <= 0 or src_h <= 0:
            logger.warning("Разрешение источника неизвестно — фильтр aspect пропущен")
            return ""

        ratio_w, ratio_h = ASPECT_RATIOS[preset]
        target_ratio = ratio_w / ratio_h
        src_ratio = src_w / src_h
        mode = state.get_aspect_mode()

        # Считаем целевые размеры — округляем до чётных
        if mode == "pad":
            if src_ratio >= target_ratio:
                # Источник шире — вписываем по ширине, полосы сверху/снизу
                W = src_w & ~1
                H = int(src_w / target_ratio) & ~1
            else:
                # Источник выше — вписываем по высоте, полосы по бокам
                W = int(src_h * target_ratio) & ~1
                H = src_h & ~1
            return (
                f"scale={W}:{H}:force_original_aspect_ratio=decrease,"
                f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
            )

        # crop — обрезаем лишнее по центру
        if src_ratio >= target_ratio:
            # Источник шире — обрезаем бока
            H = src_h & ~1
            W = int(src_h * target_ratio) & ~1
        else:
            # Источник выше — обрезаем верх/низ
            W = src_w & ~1
            H = int(src_w / target_ratio) & ~1

        return f"crop={W}:{H}:(iw-{W})/2:(ih-{H})/2"