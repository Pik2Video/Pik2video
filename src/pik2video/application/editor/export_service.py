# src/pik2video/application/editor/export_service.py
"""
Сборка и запуск команды FFmpeg.

Отвечает только за:
- построение списка аргументов
- вычисление выходного пути
- запуск FFmpeg через QProcess
- парсинг прогресса из stderr
- сигналы: export_started / export_progress / export_finished

Не знает:
- про виджеты
- про GUI

EditorState принимается через duck-typing (вызывает только методы
has_videos, get_video_path, has_zoom_markers и т.д.). Импортируется
только для type hints (TYPE_CHECKING) — в runtime зависимости нет.

Раньше жил как gui/editor/export/service.py.
"""

from __future__ import annotations

import logging
import math
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QProcess, Signal

if TYPE_CHECKING:
    from src.pik2video.application.editor.editor_state import EditorState

logger = logging.getLogger(__name__)


FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_BIN = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

FORMAT_EXTENSIONS = {
    "MP4": ".mp4",
    "MKV": ".mkv",
    "AVI": ".avi",
    "MOV": ".mov",
    "GIF": ".gif",
}

AUDIO_FORMAT_EXTENSIONS = {
    "WAV": ".wav",
    "MP3": ".mp3",
    "M4A": ".m4a",
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


class ExportService(QObject):
    """Собирает команду и запускает FFmpeg."""

    export_started = Signal()
    export_progress = Signal(int)
    export_finished = Signal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = None
        self._duration = 0.0
        self._output_path = None

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

        output.parent.mkdir(parents=True, exist_ok=True)

        free_space = shutil.disk_usage(output.parent).free
        source_path = state.get_video_path() or state.get_audio_path()
        source_size = Path(source_path).stat().st_size if source_path else 0
        required = source_size * 2

        if free_space < required:
            free_mb = free_space // (1024 * 1024)
            need_mb = required // (1024 * 1024)
            msg = f"Мало места на диске: свободно {free_mb} МБ, нужно около {need_mb} МБ."
            logger.error(msg)
            self.export_finished.emit(False, msg)
            return

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
        if self._process is not None:
            logger.info("Экспорт отменён пользователем")
            self._process.kill()
            self._process.waitForFinished(2000)
            self._process.deleteLater()
            self._process = None

    def is_running(self) -> bool:
        return self._process is not None

    def build_command(self, state: EditorState) -> list:
        if state.has_videos():
            if state.has_audio():
                return self._build_video_with_audio_command(state)
            return self._build_video_command(state)
        if state.has_audio():
            return self._build_audio_command(state)
        raise ValueError("Нет медиа для экспорта")

    def _video_has_audio(self, video_path: str) -> bool:
        try:
            result = subprocess.run(
                [
                    FFPROBE_BIN, "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=index",
                    "-of", "csv=p=0",
                    video_path,
                ],
                capture_output=True, text=True, timeout=5,
            )
            return bool(result.stdout.strip())
        except Exception as e:
            logger.warning(f"Не удалось проверить аудио-дорожку в видео: {e}")
            return False

    def _build_video_with_audio_command(self, state: EditorState) -> list:
        video_path = state.get_video_path()
        audio_path = state.get_audio_path()
        if not video_path or not audio_path:
            raise ValueError("Нет видео или аудио")

        has_video_audio = self._video_has_audio(video_path)

        args = [FFMPEG_BIN, "-y"]

        v_start, v_end = state.get_trim()
        v_duration = state.get_video_duration()
        if v_start > 0:
            args += ["-ss", f"{v_start:.3f}"]
        if v_end > 0 and (v_duration <= 0 or v_end < v_duration):
            args += ["-to", f"{v_end:.3f}"]
        args += ["-i", video_path]

        a_start, a_end = state.get_audio_trim()
        a_duration = state.get_audio_duration()
        audio_offset = state.get_audio_offset()

        shift_in_output = (audio_offset + a_start) - v_start
        if shift_in_output >= 0:
            a_start_input = a_start
            adelay_ms = int(shift_in_output * 1000)
        else:
            a_start_input = max(0.0, a_start - shift_in_output)
            adelay_ms = 0
        logger.info(f"[EXPORT] audio_offset={audio_offset:.3f}, v_start={v_start:.3f}, "
                    f"a_start={a_start:.3f}, a_start_input={a_start_input:.3f}, adelay={adelay_ms}ms")

        if a_start_input > 0:
            args += ["-ss", f"{a_start_input:.3f}"]
        if a_end > 0 and (a_duration <= 0 or a_end < a_duration):
            args += ["-to", f"{a_end:.3f}"]
        args += ["-i", audio_path]

        video_volume = state.get_video_volume()
        audio_volume = state.get_audio_volume()
        speed = state.get_speed()

        filter_parts = []

        has_zoom_markers = state.has_zoom_markers()

        if has_zoom_markers:
            seg_filter, seg_out = self._build_segmented_video_chain(state)
            filter_parts.append(seg_filter)

            post = []
            rot = ROTATION_FILTER.get(state.get_rotation())
            if rot:
                post.append(rot)
            h = RESOLUTION_HEIGHT.get(state.get_resolution())
            if h:
                post.append(f"scale=-2:{h}")
            if speed != 1.0:
                post.append(f"setpts=PTS/{speed}")

            if post:
                filter_parts.append(f"{seg_out}{','.join(post)}[vout]")
            else:
                filter_parts.append(f"{seg_out}null[vout]")
        else:
            v_filters = []
            crop = self._build_crop_filter(state)
            if crop:
                v_filters.append(crop)
            rot = ROTATION_FILTER.get(state.get_rotation())
            if rot:
                v_filters.append(rot)
            h = RESOLUTION_HEIGHT.get(state.get_resolution())
            if h:
                v_filters.append(f"scale=-2:{h}")
            if speed != 1.0:
                v_filters.append(f"setpts=PTS/{speed}")

            if v_filters:
                filter_parts.append(f"[0:v]{','.join(v_filters)}[vout]")
            else:
                filter_parts.append("[0:v]null[vout]")

        a_filters = []
        if adelay_ms > 0:
            a_filters.append(f"adelay={adelay_ms}:all=1")
        if speed != 1.0:
            a_filters.append(self._build_atempo(speed))
        a_filters.append(f"volume={audio_volume:.3f}")
        filter_parts.append(f"[1:a]{','.join(a_filters)}[aa]")

        if has_video_audio:
            va_filters = []
            if speed != 1.0:
                va_filters.append(self._build_atempo(speed))
            va_filters.append(f"volume={video_volume:.3f}")
            filter_parts.append(f"[0:a]{','.join(va_filters)}[va]")
            filter_parts.append("[va][aa]amix=inputs=2:duration=first:normalize=0[aout]")
        else:
            filter_parts.append("[aa]anull[aout]")

        filter_complex = ";".join(filter_parts)
        args += ["-filter_complex", filter_complex]
        args += ["-map", "[vout]", "-map", "[aout]"]

        if not has_video_audio:
            args += ["-shortest"]

        if state.get_format() != "GIF":
            args += ["-c:v", "libx264"]
            if state.get_bitrate_mode() == "manual":
                args += ["-b:v", state.get_bitrate_value()]
            else:
                args += ["-crf", "23"]
            args += ["-pix_fmt", "yuv420p"]
            args += ["-c:a", "aac", "-b:a", "128k"]

        args.append(str(self.get_output_path(state)))
        return args

    def _build_video_command(self, state: EditorState) -> list:
        input_path = state.get_video_path()
        if not input_path:
            raise ValueError("Нет активного видеофайла")

        args = [FFMPEG_BIN, "-y"]

        start, end = state.get_trim()
        duration = state.get_video_duration()
        if start > 0:
            args += ["-ss", f"{start:.3f}"]
        if end > 0 and (duration <= 0 or end < duration):
            args += ["-to", f"{end:.3f}"]
        args += ["-i", input_path]

        has_zoom_markers = state.has_zoom_markers()
        speed = state.get_speed()

        if has_zoom_markers:
            filter_complex, vout_label = self._build_segmented_video_chain(state)

            post = []
            rot = ROTATION_FILTER.get(state.get_rotation())
            if rot:
                post.append(rot)
            height = RESOLUTION_HEIGHT.get(state.get_resolution())
            if height:
                post.append(f"scale=-2:{height}")
            if speed != 1.0:
                post.append(f"setpts=PTS/{speed}")

            if post:
                filter_complex += f";{vout_label}{','.join(post)}[vfinal]"
                vout_label = "[vfinal]"

            args += ["-filter_complex", filter_complex]
            args += ["-map", vout_label, "-map", "0:a?"]
        else:
            filters = []

            crop_filter = self._build_crop_filter(state)
            if crop_filter:
                filters.append(crop_filter)

            rot_filter = ROTATION_FILTER.get(state.get_rotation())
            if rot_filter:
                filters.append(rot_filter)

            height = RESOLUTION_HEIGHT.get(state.get_resolution())
            if height:
                filters.append(f"scale=-2:{height}")

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
            if speed != 1.0:
                args += ["-af", self._build_atempo(speed)]

        args.append(str(self.get_output_path(state)))
        return args

    def _build_audio_command(self, state: EditorState) -> list:
        input_path = state.get_audio_path()
        if not input_path:
            raise ValueError("Нет активного аудиофайла")

        args = [FFMPEG_BIN, "-y", "-i", input_path]

        start, end = state.get_audio_trim()
        duration = state.get_audio_duration()
        if start > 0:
            args += ["-ss", f"{start:.3f}"]
        if end > 0 and (duration <= 0 or end < duration):
            args += ["-to", f"{end:.3f}"]

        speed = state.get_speed()
        if speed != 1.0:
            args += ["-af", self._build_atempo(speed)]

        fmt = state.get_audio_format()
        if fmt == "WAV":
            args += ["-c:a", "pcm_s16le"]
        elif fmt == "MP3":
            args += ["-c:a", "libmp3lame", "-q:a", "2"]
        elif fmt == "M4A":
            args += ["-c:a", "aac", "-b:a", "192k"]
        else:
            args += ["-c:a", "pcm_s16le"]

        args.append(str(self.get_output_path(state)))
        return args

    def get_output_path(self, state: EditorState) -> Path:
        base = state.get_export_path()
        if not base:
            base = str(Path.home() / "Desktop")
        base_dir = Path(base)

        if state.has_videos():
            name = state.get_export_filename()
            if not name:
                name = datetime.now().strftime("output_%m.%d_%H.%M.%S")
            ext = FORMAT_EXTENSIONS.get(state.get_format(), ".mp4")
        elif state.has_audio():
            name = state.get_audio_export_filename()
            if not name:
                name = datetime.now().strftime("output_%Y.%m.%d_%H.%M.%S")
            ext = AUDIO_FORMAT_EXTENSIONS.get(state.get_audio_format(), ".wav")
        else:
            name = "output"
            ext = ".mp4"

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
        if state.has_audio() and not state.has_videos():
            start, end = state.get_audio_trim()
            duration = state.get_audio_duration()
            if duration <= 0:
                return 0.0
            end = end if end > 0 else duration
            return max(0.0, end - start)

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

    def _on_output(self):
        if self._process is None:
            return
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="ignore")
        for line in data.splitlines():
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
        self._process.deleteLater()
        self._process = None
        self._output_path = None

    def _on_error(self, error):
        logger.error(f"Ошибка QProcess: {error}")
        self.export_finished.emit(False, f"Ошибка процесса: {error}")
        self._process.deleteLater()
        self._process = None
        self._output_path = None

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

    def _build_x_expr(self, cx_base: float, sw: int, W: int, markers: list[tuple[float, float]]) -> str:
        base = int(round(cx_base))
        max_x = max(0, sw - W)
        base = max(0, min(base, max_x))

        offsets = []
        for t, off in markers:
            x = base + int(round(off))
            x = max(0, min(x, max_x))
            offsets.append((t, x))

        EPS = 0.0005
        expr = str(offsets[-1][1])
        for i in range(len(offsets) - 2, -1, -1):
            t_next = max(0.0, offsets[i+1][0] - EPS)
            expr_i = str(offsets[i][1])
            expr = f"if(lt(t,{t_next:.4f}),{expr_i},{expr})"
        t0 = max(0.0, offsets[0][0] - EPS)
        expr = f"if(lt(t,{t0:.4f}),{base},{expr})"
        return expr

    PRESET_CANVAS = {
        "16:9": (1920, 1080),
        "9:16": (1080, 1920),
        "1:1":  (1080, 1080),
        "4:5":  (1080, 1350),
        "4:3":  (1600, 1200),
    }

    def _get_canvas_size(self, state: EditorState) -> tuple:
        preset = state.get_aspect_preset()
        if preset == "original" or preset not in self.PRESET_CANVAS:
            sw, sh = state.get_source_resolution()
            if sw <= 0 or sh <= 0:
                return (1920, 1080)
            return (int(sw) & ~1, int(sh) & ~1)
        return self.PRESET_CANVAS[preset]

    def _build_segmented_video_chain(self, state: EditorState) -> tuple:
        trim_start, trim_end = state.get_trim()
        duration = state.get_video_duration()
        if trim_end <= 0 or (duration > 0 and trim_end > duration):
            trim_end = duration if duration > 0 else trim_end
        total_dur = trim_end - trim_start
        if total_dur <= 0:
            raise ValueError("Нулевая длительность — нечего экспортировать")

        raw_markers = state.get_markers()
        markers = []
        for t, off, z, _p in raw_markers:
            t_norm = t - trim_start
            if 0 <= t_norm < total_dur - 0.001:
                markers.append((t_norm, off, z))
        markers.sort(key=lambda x: x[0])

        segments = []
        if not markers:
            segments.append((0.0, total_dur, 0.0, 0))
        else:
            if markers[0][0] > 0.001:
                segments.append((0.0, markers[0][0], 0.0, 0))
            for i, (t, off, z) in enumerate(markers):
                seg_end = markers[i + 1][0] if i + 1 < len(markers) else total_dur
                segments.append((t, seg_end, off, z))

        CW, CH = self._get_canvas_size(state)
        sw, sh = state.get_source_resolution()

        parts = []
        labels = []
        for i, (seg_start, seg_end, off, zoom) in enumerate(segments):
            cx, cy, cw, ch = state.compute_crop_for(zoom, off)
            if cw <= 0 or ch <= 0:
                continue
            scale_ratio = CW / cw

            vwx = max(0, cx)
            vwy = max(0, cy)
            vwx_end = min(sw, cx + cw)
            vwy_end = min(sh, cy + ch)
            vww = max(1, int(round(vwx_end - vwx)))
            vwh = max(1, int(round(vwy_end - vwy)))

            scale_w = max(2, int(round(vww * scale_ratio))) & ~1
            scale_h = max(2, int(round(vwh * scale_ratio))) & ~1
            pad_x = max(0, int(round(max(0.0, -cx) * scale_ratio))) & ~1
            pad_y = max(0, int(round(max(0.0, -cy) * scale_ratio))) & ~1

            if scale_w + pad_x > CW:
                scale_w = CW - pad_x
            if scale_h + pad_y > CH:
                scale_h = CH - pad_y
            scale_w &= ~1
            scale_h &= ~1

            trim_s = math.floor(seg_start * 1000) / 1000
            trim_e = math.floor(seg_end * 1000) / 1000
            parts.append(
                f"[0:v]trim=start={trim_s:.3f}:end={trim_e:.3f},"
                f"setpts=PTS-STARTPTS,"
                f"crop={vww}:{vwh}:{int(round(vwx))}:{int(round(vwy))},"
                f"scale={scale_w}:{scale_h}:flags=lanczos,"
                f"pad={CW}:{CH}:{pad_x}:{pad_y}:color=black,"
                f"setsar=1[v{i}]"
            )
            labels.append(f"[v{i}]")

        if not labels:
            raise ValueError("Не удалось построить ни одного сегмента")

        if len(labels) == 1:
            return (";".join(parts), labels[0])

        parts.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[vconcat]")
        return (";".join(parts), "[vconcat]")

    def _build_crop_filter(self, state: EditorState) -> str:
        cx, cy, cw, ch = state.get_crop_rect()
        sw, sh = state.get_source_resolution()

        if sw <= 0 or sh <= 0 or cw <= 0 or ch <= 0:
            return ""

        markers = state.get_markers()
        markers_offsets = [(m[0], m[1]) for m in markers] if markers else []
        if markers_offsets and cw < sw:
            vx0 = max(0.0, cx)
            vy0 = max(0.0, cy)
            vx1 = min(float(sw), cx + cw)
            vy1 = min(float(sh), cy + ch)

            W = int(vx1 - vx0) & ~1
            H = int(vy1 - vy0) & ~1
            Y = int(vy0) & ~1

            if W <= 0 or H <= 0:
                return ""

            cx_base = cx - state.get_offset_x()
            X_expr = self._build_x_expr(cx_base, sw, W, markers_offsets)
            X_expr_safe = X_expr.replace(",", "\\,")

            crop_part = f"crop={W}:{H}:{X_expr_safe}:{Y}"

            pad_w = int(cw) & ~1
            pad_h = int(ch) & ~1
            if pad_w > W or pad_h > H:
                pad_x = max(0, int(round(-cx)))
                pad_y = max(0, int(round(-cy)))
                pad_part = f"pad={pad_w}:{pad_h}:{pad_x}:{pad_y}:color=black"
                return f"{crop_part},{pad_part}"

            return crop_part

        EPS = 0.5
        if (abs(cx) < EPS and abs(cy) < EPS
                and abs(cw - sw) < EPS and abs(ch - sh) < EPS):
            return ""

        vx0 = max(0.0, cx)
        vy0 = max(0.0, cy)
        vx1 = min(float(sw), cx + cw)
        vy1 = min(float(sh), cy + ch)
        if vx1 <= vx0 or vy1 <= vy0:
            return ""

        crw = vx1 - vx0
        crh = vy1 - vy0
        W = int(crw) & ~1
        H = int(crh) & ~1
        X = int(vx0) & ~1
        Y = int(vy0) & ~1
        if W <= 0 or H <= 0:
            return ""

        if W == sw and H == sh and X == 0 and Y == 0:
            crop_part = ""
        else:
            crop_part = f"crop={W}:{H}:{X}:{Y}"

        pad_w = int(cw) & ~1
        pad_h = int(ch) & ~1
        if pad_w > W or pad_h > H:
            pad_x = max(0, int(round(vx0 - cx)))
            pad_y = max(0, int(round(vy0 - cy)))
            pad_part = f"pad={pad_w}:{pad_h}:{pad_x}:{pad_y}:color=black"
            if crop_part:
                return f"{crop_part},{pad_part}"
            return pad_part

        return crop_part
