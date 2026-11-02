# src/pik2video/application/recording_service.py
import ctypes
import logging
from pathlib import Path

from PySide6.QtWidgets import QApplication  # <-- НОВОЕ: импорт для получения масштаба

from .session_types import SessionType
from .settings_model import SettingsModel

logger = logging.getLogger(__name__)


# UI "качество" → целевой bitrate. quality=0 — используем только bitrate (videotoolbox).
QUALITY_BITRATE = {
    "Низкое": 2000,
    "Среднее": 8000,
    "Высокое": 20000,
}


class Pik2VideoParams(ctypes.Structure):
    _fields_ = [
        ("output_dir", ctypes.c_char_p),
        ("left", ctypes.c_int),
        ("top", ctypes.c_int),
        ("width", ctypes.c_int),
        ("height", ctypes.c_int),
        ("fps", ctypes.c_int),
        ("bitrate_kbps", ctypes.c_int),
        ("quality", ctypes.c_int),
    ]


class RecordingService:
    """
    Сервис записи, использующий C++ движок вместо старого Python кода.
    """
    def __init__(self, settings: SettingsModel):
        self._settings = settings
        self._is_recording = False
        self._cpp_lib = None
        
        self._load_library()

    def _load_library(self):
        """Загружает динамическую библиотеку C++"""
        base_path = Path(__file__).resolve().parents[3]
        lib_path = base_path / "cpp" / "build" / "libpik2video_recorder.dylib"

        if not lib_path.exists():
            logger.error(f"Библиотека не найдена: {lib_path}")
            self._cpp_lib = None
            return

        try:
            self._cpp_lib = ctypes.CDLL(str(lib_path))
        except OSError as e:
            logger.error(f"Ошибка загрузки C++ библиотеки: {e}")
            self._cpp_lib = None
            return

        try:
            self._cpp_lib.recorder_start.argtypes = [ctypes.POINTER(Pik2VideoParams)]
            self._cpp_lib.recorder_start.restype = ctypes.c_int

            self._cpp_lib.recorder_stop.argtypes = []
            self._cpp_lib.recorder_stop.restype = None

            self._cpp_lib.recorder_get_elapsed_time.argtypes = []
            self._cpp_lib.recorder_get_elapsed_time.restype = ctypes.c_double

            self._cpp_lib.recorder_get_frame_count.argtypes = []
            self._cpp_lib.recorder_get_frame_count.restype = ctypes.c_int

            logger.debug("C++ библиотека загружена успешно")
        except AttributeError as e:
            logger.error(f"Символ C++ не найден: {e}")
            self._cpp_lib = None

    def start_recording(self, session_dir: Path, region: dict, session_type: SessionType) -> bool:
        
        if self._is_recording:
            return False
        
        if self._cpp_lib is None:
            logger.error("C++ библиотека не загружена")
            return False
        
        # <-- НОВОЕ: Получаем коэффициент масштаба экрана (для Retina)
        screen = QApplication.primaryScreen()
        scale = screen.devicePixelRatio() if screen else 1.0
        logger.debug(f"Коэффициент масштаба экрана: {scale}")

        # <-- НОВОЕ: Преобразуем координаты в физические пиксели
        left = int(region["left"] * scale)
        top = int(region["top"] * scale)
        width = int(region["width"] * scale)
        height = int(region["height"] * scale)

        # Для видео используем FPS из настроек
        if session_type == SessionType.VIDEO:
            fps = self._settings.record.fps
        else:
            fps = self._settings.screen.capture_fps
        
        quality_name = self._settings.record.common.quality
        bitrate_kbps = QUALITY_BITRATE.get(quality_name, 8000)

        params = Pik2VideoParams()
        params.output_dir = str(session_dir).encode('utf-8')
        params.left = left
        params.top = top
        params.width = width
        params.height = height
        params.fps = fps
        params.bitrate_kbps = bitrate_kbps
        params.quality = 0   # используем только bitrate
        logger.info(
            f"Запуск C++ записи: {session_dir}, {width}x{height}, {fps} FPS, "
            f"качество='{quality_name}' → {bitrate_kbps} kbps (масштаб {scale})"
        )
        result = self._cpp_lib.recorder_start(ctypes.byref(params))

        if result != 0:
            logger.error(f"Ошибка запуска записи: {result}")
            return False

        # Ждём фактического захвата первого кадра в C++.
        # init_output + VideoInput::open + init_filters занимают ~0.5 сек,
        # clock_.start() вызывается только после этого.
        import time as _time
        deadline = _time.monotonic() + 2.0
        started = False
        while _time.monotonic() < deadline:
            if self._cpp_lib.recorder_get_elapsed_time() > 0:
                started = True
                break
            _time.sleep(0.01)

        if not started:
            logger.warning("C++ recorder не стартовал за 2 сек")

        self._is_recording = True
        return True

    def stop_recording(self) -> bool:
        if not self._is_recording:
            return False
        if self._cpp_lib is None:
            return False
        logger.info("Остановка C++ записи")
        self._cpp_lib.recorder_stop()
        self._is_recording = False
        return True

    def get_elapsed_time(self) -> float:
        if self._cpp_lib and self._is_recording:
            return self._cpp_lib.recorder_get_elapsed_time()
        return 0.0

    def get_frame_count(self) -> int:
        if self._cpp_lib:
            return self._cpp_lib.recorder_get_frame_count()
        return 0

    @property
    def is_recording(self) -> bool:
        return self._is_recording
