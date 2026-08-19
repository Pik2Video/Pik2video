import logging

import shutil
import subprocess
import platform
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

class FFmpegService:
    """
    Сервис для работы с FFmpeg.
    
    Отвечает за:
    - Проверку наличия FFmpeg в системе
    - Определение платформы и доступных кодеков
    - Формирование команд FFmpeg с оптимальными параметрами
    """

    # ─── Маппинг качества на параметры FFmpeg ───
    QUALITY_PRESETS = {
        "Низкое": {"preset": "ultrafast", "crf": "28", "bitrate": "1M"},
        "Среднее": {"preset": "medium", "crf": "23", "bitrate": "4M"},
        "Высокое": {"preset": "slow", "crf": "18", "bitrate": "8M"},
    }

    def is_installed(self) -> bool:
        """Проверяет доступность ffmpeg (включая homebrew для GUI)"""
        # Стандартный поиск
        result = shutil.which("ffmpeg")
        if result:
            return True
        
        # Поиск в homebrew (для GUI-запуска)
        brew_paths = [
            "/opt/homebrew/bin/ffmpeg",
            "/usr/local/bin/ffmpeg",
        ]
        for path in brew_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                logger.debug(f"FFmpeg найден: {path}")
                return True
        
        logger.warning("FFmpeg не найден в системе")
        return False


    def get_version(self) -> Optional[str]:
        """Получить версию ffmpeg"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.split("\n")[0] if result.stdout else None
        except Exception:
            return None

    def get_platform(self) -> str:
        """Определить платформу"""
        system = platform.system()
        
        if system == "Darwin":
            return "mac"
        elif system == "Windows":
            return "windows"
        elif system == "Linux":
            return "linux"
        
        return "unknown"

    def get_best_encoder(self) -> str:
        """
        Возвращает оптимальный аппаратный энкодер для платформы.
        Если аппаратный недоступен — fallback на libx264.
        """
        platform_name = self.get_platform()
        
        if platform_name == "mac":
            # VideoToolbox — аппаратное ускорение на macOS
            return "h264_videotoolbox"
        elif platform_name == "windows":
            # Можно определить NVENC или AMF, но для простоты — libx264
            return "libx264"
        elif platform_name == "linux":
            # VAAPI для Linux с Intel/AMD
            return "libx264"  # fallback, можно расширить
        
        return "libx264"

    def build_recording_command(
        self,
        output_path: Path,
        width: int,
        height: int,
        fps: int,
        quality: str = "Среднее"
    ) -> list[str]:
        """
        Создаёт команду FFmpeg для прямой записи видео.
        
        Args:
            output_path: путь для сохранения видео
            width, height: размеры видео
            fps: кадры в секунду
            quality: "Низкое", "Среднее", "Высокое"
        
        Returns:
            Список аргументов для subprocess.Popen
        """
        
        # Получаем пресет качества
        preset = self.QUALITY_PRESETS.get(quality, self.QUALITY_PRESETS["Среднее"])
        
        # Определяем кодер
        encoder = self.get_best_encoder()
        
        # Базовая команда
        cmd = [
            "ffmpeg",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{width}x{height}",
            "-r", str(fps),
            "-i", "pipe:0",
            "-c:v", encoder,
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-y",
        ]
        
        # Аппаратный энкодер — только битрейт
        if encoder in ("h264_videotoolbox", "h264_amf", "h264_nvenc"):
            cmd += ["-b:v", preset["bitrate"]]
        else:
            # Программный — preset + crf
            cmd += ["-preset", preset["preset"], "-crf", preset["crf"]]
        
        cmd.append(str(output_path))
        return cmd

    def build_assembly_command(
        self,
        frames_dir: Path,
        output_path: Path,
        fps: int,
        video_format: str = "MP4"
    ) -> list[str]:
        """
        Создаёт команду FFmpeg для сборки видео из кадров.
        """
        
        # 🆕 Особая команда для GIF
        if video_format == "GIF":
            return [
                "ffmpeg",
                "-framerate", str(fps),
                "-i", str(frames_dir / "frame_%06d.png"),
                "-vf", f"fps={fps},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse",
                "-loop", "0",
                "-y",
                str(output_path)
            ]
        
        # Маппинг формата на кодеки и расширения (MP4/MKV/AVI/MOV)
        format_map = {
            "MP4": {"codec": "libx264", "f": "mp4"},
            "MKV": {"codec": "libx264", "f": "matroska"},
            "AVI": {"codec": "mpeg4", "f": "avi"},
            "MOV": {"codec": "libx264", "f": "mov"}
        }
        
        fmt = format_map.get(video_format, format_map["MP4"])
        
        cmd = [
            "ffmpeg",
            "-framerate", str(fps),
            "-i", str(frames_dir / "frame_%06d.png"),
            "-c:v", fmt["codec"],
            "-pix_fmt", "yuv420p",
            "-preset", "medium",
            "-crf", "23",
            "-movflags", "+faststart",
            "-f", fmt["f"],
            "-y",
            str(output_path)
        ]
        
        return cmd

    def check_encoder_available(self, encoder: str) -> bool:
        """
        Проверяет, доступен ли указанный энкодер в FFmpeg.
        """
        try:
            result = subprocess.run(
                ["ffmpeg", "-encoders"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return encoder in result.stdout
        except Exception:
            return False