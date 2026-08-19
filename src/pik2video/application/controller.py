# src/pik2video/application/controller.py
import logging

import psutil
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, QTimer

from src.pik2video.infrastructure.ffmpeg.ffmpeg_service import FFmpegService

from .session_types import SessionType
from .recording_service import RecordingService
from .session_service import SessionService
from .settings_model import SettingsModel
from .state_machine import StateMachine, AppState
from src.pik2video.utils import format_size, format_time
from src.pik2video.locale.translator import Translator

logger = logging.getLogger(__name__)

class AppController(QObject):
    state_changed = Signal(AppState)   # Сигнал вызывается каждый раз при изменении состояния приложения
    ffmpeg_required = Signal()

    time_updated = Signal(str)
    ram_updated = Signal(str)
    shots_updated = Signal(int)

    """
    Центральный контроллер приложения.
    Отвечает за:
    - управление состоянием (через StateMachine)
    - управление runtime-данными (координаты, таймер, время старта)
    - запуск и остановку записи
    - управление сессией (создание, экспорт, очистка)
    - уведомление GUI об изменении состояния (через сигнал state_changed)

    GUI должен взаимодействовать только с публичными методами этого класса.
    """

    def __init__(self, base_tmp_dir: Optional[Path] = None):
        # ─── Services & Models ───────────────────────
        super().__init__()
        self.settings = SettingsModel()
        self.settings.load_from_file()
        self.translator = Translator()

        # Устанавливаем язык в translator из загруженных настроек
        current_lang = self.settings.global_settings.language
        lang_code = "ru" if current_lang == "Русский" else "en"
        self.translator.set_language(lang_code)

        self.state_machine = StateMachine()
        self._session_type: Optional[SessionType] = None
        self.session_service = SessionService(
            base_tmp_dir or Path(__file__).resolve().parents[2] / "data" / "tmp"
        )
        self.recording_service = RecordingService(self.settings)

        self.ffmpeg = FFmpegService()                   # проверка наличия FFmpeg

         # 🆕 Проверить FFmpeg один раз при старте
        self._ffmpeg_missing = not self.ffmpeg.is_installed()
        if self._ffmpeg_missing:
            logger.error("FFmpeg не найден при старте")
        else:
            logger.info("FFmpeg найден при старте")

        # ---- Runtime данные текущей сессии ----
        self.raw_coordinates: Optional[dict] = None     # исходные координаты
        self.region: Optional[dict] = None              # область записи в формате для recorder
        self._start_time: Optional[float] = None        # время начала записи

    def _ensure_ffmpeg(self) -> bool:
        """Проверяет наличие FFmpeg (использует кэшированный результат)"""
        if self._ffmpeg_missing:
            logger.error("FFmpeg НЕ найден")
            self.ffmpeg_required.emit()
            return False
        logger.info("FFmpeg найден")
        return True

    def has_active_session_data(self) -> bool:
        """Проверяет, есть ли данные в текущей сессии"""
        return self.session_service.has_data()

    def get_translator(self):
        """Вернуть менеджер переводов"""
        return self.translator

    def save_settings(self):
        """Сохранить текущие настройки в файл"""
        self.settings.save_to_file()
        logger.info("Настройки сохранены")

    # -----------ПЕРЕХОД В РЕЖИМ ПОДГОТОВКИ-----------

    def get_session_type(self) -> Optional[SessionType]:
        return self._session_type

    def _emit_state(self):
        """Уведомить GUI о текущем состоянии приложения."""
        current_state = self.state_machine.get_state()
        logger.debug(f"Отправляем state_changed: {current_state}")
        self.state_changed.emit(current_state)

    # !!!!!!!  ========== МЕТОД ДЛЯ ТЕСТОВ ========== !!!!!!!
    def set_state_dev(self, state: AppState, session_type: Optional[SessionType] = None):
        """
        DEV ONLY:
        Эмулирует реальный workflow переходов состояний,
        чтобы GUI создавал все необходимые окна корректно.
        """

        logger.debug(f"Запрос состояния: {state}")

        # ---- Сброс runtime перед dev-переходом ----
        self._cleanup_runtime()

        if state == AppState.IDLE:
            self.state_machine.set_state_dev(AppState.IDLE)
            self._session_type = None
            self.state_changed.emit(AppState.IDLE)
            return

        # Если session_type не указан — ставим VIDEO по умолчанию
        if session_type is None:
            session_type = SessionType.VIDEO

        self._session_type = session_type
        logger.debug(f"session_type = {self._session_type}")

        # =========================================================
        # 1️⃣ PREPARING
        # =========================================================

        if state in (
            AppState.PREPARING_VIDEO,
            AppState.PREPARING_SCREEN,
            AppState.RECORDING,
            AppState.REVIEW,
        ):

            preparing_state = (
                AppState.PREPARING_VIDEO
                if session_type == SessionType.VIDEO
                else AppState.PREPARING_SCREEN
            )

            logger.debug(f"→ Эмуляция {preparing_state}")
            self.state_machine.set_state_dev(preparing_state)
            self.state_changed.emit(preparing_state)

        # =========================================================
        # 2️⃣ RECORDING
        # =========================================================

        if state in (AppState.RECORDING, AppState.REVIEW):

            logger.debug("→ Эмуляция RECORDING")

            # Для dev фиктивно создаём region,
            # иначе can_start_recording() в обычном коде будет невозможен
            self.region = {
                "left": 0,
                "top": 0,
                "width": 800,
                "height": 600,
            }

            self.state_machine.set_state_dev(AppState.RECORDING)
            self.state_changed.emit(AppState.RECORDING)

        # =========================================================
        # 3️⃣ REVIEW
        # =========================================================

        if state == AppState.REVIEW:

            logger.debug("→ Эмуляция REVIEW")


            self.state_machine.set_state_dev(AppState.REVIEW)
            self.state_changed.emit(AppState.REVIEW)


    def prepare_video(self):

        logger.info("Запрошен PREPARING_VIDEO")

        """Перевести приложение в режим подготовки записи видео."""

        # 👇 ДОБАВЛЯЕМ ПРОВЕРКУ
        if not self._ensure_ffmpeg():
            logger.warning("Нет FFmpeg → остаёмся в IDLE")
            return
        
        if self.state_machine.prepare_video():
            self._session_type = SessionType.VIDEO
            self._emit_state()
        else:

            logger.warning("StateMachine ЗАПРЕТИЛ переход")


    def prepare_screen(self):

        logger.info("Запрошен PREPARING_SCREEN")

        """Перевести приложение в режим подготовки записи экрана."""

        # 👇 ДОБАВЛЯЕМ ПРОВЕРКУ
        if not self._ensure_ffmpeg():
            logger.warning("Нет FFmpeg → остаёмся в IDLE")
            return

        if self.state_machine.prepare_screen():
            self._session_type = SessionType.SCREEN

            self.set_video_format("GIF")  # 🆕 формат по умолчанию для SCREEN
            
            self._emit_state()
        else:
            logger.warning("StateMachine ЗАПРЕТИЛ переход")

    def cancel_session(self):

        logger.info("Запрошен CANCEL_SESSION")

        """Отменить режим подготовки и вернуться в IDLE."""
        if self.state_machine.cancel_preparing():
            self._cleanup_runtime()   # очищаем тип и координаты
            self._emit_state()
        else:

            logger.warning("Отмена невозможна в текущем состоянии")

    # -----------УСТАНОВКА ОБЛАСТИ ЗАПИСИ-----------

    def set_raw_coordinates(self, coords: dict):
        """
        Установить координаты области записи.

        coords ожидается в формате:
        {x1, y1, x2, y2}
        """

        x1 = coords["x1"]
        y1 = coords["y1"]
        x2 = coords["x2"]
        y2 = coords["y2"]

        if x2 <= x1 or y2 <= y1:
            raise ValueError("Некорректные координаты области")
        self.raw_coordinates = coords
        self.region = {
            "left": x1,
            "top": y1,
            "width": x2 - x1,
            "height": y2 - y1
        }

        logger.debug(f"Регион установлен: {self.region}")


    def update_time(self):
        """
        Вызывается CaptureSession каждую секунду.
        Считает прошедшее время и отправляет строку в GUI.
        """
        elapsed = self.get_elapsed_time()
        formatted = format_time(elapsed, "TIME:")  # ← вызов функции из utils
        self.time_updated.emit(formatted)

    def update_ram(self):
        """
        Вызывается CaptureSession каждую секунду.
        Отправляет текущий размер сессии в GUI.
        """
        size_bytes = self.get_session_size()
        formatted_size = format_size(size_bytes)
        self.ram_updated.emit(f"RAM: {formatted_size}")

    def update_shots(self):
        """Отправить количество кадров в GUI (для screen режима)"""
        if self.recording_service and self._session_type == SessionType.SCREEN:
            shots = self.recording_service.get_frame_count()

            self.shots_updated.emit(shots)


    def is_recording(self) -> bool:
        state = self.state_machine.get_state()
        return state in (AppState.WAITING, AppState.RECORDING)

    def is_preparing(self) -> bool:
        return self.state_machine.get_state() in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)

    def is_review(self) -> bool:
        return self.state_machine.get_state() == AppState.REVIEW

    # ------- пауза -----
    def get_start_delay(self) -> int:
        """Получить задержку перед стартом для текущего типа сессии"""
        if self._session_type == SessionType.VIDEO:
            return self.settings.record.common.start_delay
        elif self._session_type == SessionType.SCREEN:
            return self.settings.screen.common.start_delay
        return self.settings.record.common.start_delay  # по умолчанию

    def set_start_delay(self, seconds: int):
        """Установить задержку перед стартом для текущего типа сессии"""
        if self._session_type == SessionType.VIDEO:
            self.settings.record.common.start_delay = max(0, seconds)
            logger.debug(f"Record start_delay установлен: {seconds} сек")
        elif self._session_type == SessionType.SCREEN:
            self.settings.screen.common.start_delay = max(0, seconds)
            logger.debug(f"Screen start_delay установлен: {seconds} сек")
        else:
            # Если тип сессии не установлен — сохраняем в оба
            self.settings.record.common.start_delay = max(0, seconds)
            self.settings.screen.common.start_delay = max(0, seconds)
            logger.debug(f"start_delay установлен: {seconds} сек (оба типа)")


    # -------------------------------
    # RECORD SESSION
    # -------------------------------
    def get_record_fps(self) -> int:
        return self.settings.record.fps

    def set_record_fps(self, fps: int):
        self.settings.record.fps = fps
        logger.debug(f"Record FPS установлен: {fps}")

    def get_record_quality(self) -> str:
        return self.settings.record.common.quality

    def set_record_quality(self, quality: str):
        self.settings.record.common.quality = quality
        logger.debug(f"Record качество установлено: {quality}")

    def get_record_timer(self) -> int:
        return self.settings.record.common.timer_seconds

    def set_record_timer(self, seconds: int):
        self.settings.record.common.timer_seconds = max(0, seconds)
        logger.debug(f"Record таймер установлен: {seconds} сек")


    # -------------------------------
    # SCREEN SESSION
    # -------------------------------
    def get_screen_fps(self) -> int:
        return self.settings.screen.capture_fps

    def set_screen_fps(self, value: int):
        if 1 <= value <= 1000:
            self.settings.screen.capture_fps = value
            logger.debug(f"Screen capture_fps установлено: {value}")

    def get_screen_timer(self) -> int:
        return self.settings.screen.common.timer_seconds

    def set_screen_timer(self, seconds: int):
        self.settings.screen.common.timer_seconds = max(0, seconds)
        logger.debug(f"Screen таймер установлен: {seconds} сек")


    # -------------------------------
    # финальные настройки
    # -------------------------------

    def get_screen_finalize_fps(self) -> int:
        """
        FPS итогового видео для режима screen capture.
        """
        return self.settings.finalize.screen.playback_fps

    def set_screen_finalize_fps(self, fps: int):
        if 1 <= fps <= 100:
            self.settings.finalize.screen.playback_fps = fps
            logger.debug(f"Screen finalize FPS установлен: {fps}")


    # -------------------------------
    # Общие финальные настройки
    # -------------------------------
    def get_export_filename(self) -> str:
        """Имя файла для финальной записи (без расширения)."""
        return self.settings.finalize.common.export_filename

    def set_export_filename(self, name: str):
        self.settings.finalize.common.export_filename = name
        logger.debug(f"Export filename установлен: {name}")

    def get_export_path(self) -> str:
        """Путь для сохранения видео."""
        path = self.settings.finalize.common.export_path
        if not path:
            path = str(Path.home() / "Desktop")
        return path

    def set_export_path(self, path: str):
        """Установить путь для сохранения видео."""
        self.settings.finalize.common.export_path = path
        logger.debug(f"Export path установлен: {path}")

    def get_video_format(self) -> str:
        """Возвращает текущий формат видео для VideoFinalizeWindow."""
        return self.settings.finalize.common.video_format

    def set_video_format(self, fmt: str):
        """Установить формат видео для VideoFinalizeWindow."""
        allowed = ["MP4", "MKV", "AVI", "MOV", "MOV", "GIF"]
        if fmt not in allowed:
            fmt = "MP4"  # дефолт
        self.settings.finalize.common.video_format = fmt
        logger.debug(f"Video format установлен: {fmt}")


    # 🆕 Разрешение
    def get_resolution(self) -> str:
        return self.settings.finalize.common.resolution

    def set_resolution(self, value: str):
        allowed = ["original", "1080p", "720p", "480p"]
        if value in allowed:
            self.settings.finalize.common.resolution = value
            logger.debug(f"Resolution установлен: {value}")

    # 🆕 Битрейт
    def get_bitrate_mode(self) -> str:
        return self.settings.finalize.common.bitrate_mode

    def get_bitrate_value(self) -> str:
        return self.settings.finalize.common.bitrate_value

    def set_bitrate(self, mode: str, value: str):
        self.settings.finalize.common.bitrate_mode = mode
        self.settings.finalize.common.bitrate_value = value
        logger.debug(f"Bitrate установлен: {mode}, {value}")

    # 🆕 Поворот
    def get_rotation(self) -> int:
        return self.settings.finalize.common.rotation

    def set_rotation(self, angle: int):
        if angle in (0, 90, 180, 270):
            self.settings.finalize.common.rotation = angle
            logger.debug(f"Rotation установлен: {angle}°")

    def get_speed_multiplier(self) -> float:
        return self.settings.finalize.screen.speed_multiplier

    def set_speed_multiplier(self, multiplier: float):
        self.settings.finalize.screen.speed_multiplier = multiplier
        logger.debug(f"Speed multiplier установлен: {multiplier}x")

    # ----------GLOBAL SETTINGS----------
    def get_language(self) -> str:
        return self.settings.global_settings.language

    def set_language(self, value: str):
        self.settings.global_settings.language = value
        logger.debug(f"Язык установлен: {value}")


    def get_text_size(self) -> int:
        return self.settings.global_settings.text_size

    def set_text_size(self, value: int):
        self.settings.global_settings.text_size = value
        print(f"[Controller] Размер текста установлен: {value}")

    def get_show_tooltips(self) -> bool:
        return self.settings.global_settings.show_tooltips

    def set_show_tooltips(self, value: bool):
        self.settings.global_settings.show_tooltips = value
        logger.debug(f"Подсказки: {value}")

    # всегда в топе
    def get_always_on_top(self) -> bool:
        return self.settings.global_settings.always_on_top

    def set_always_on_top(self, value: bool):
        self.settings.global_settings.always_on_top = value
        logger.debug(f"Всегда в топе: {value}")

        # 🆕 Применить сразу — отправить текущее состояние, чтобы GUI обновил флаг
        self.state_changed.emit(self.state_machine.get_state())

    def get_preset_vertical(self) -> bool:
        return self.settings.global_settings.preset_vertical

    def set_preset_vertical(self, value: bool):
        self.settings.global_settings.preset_vertical = value
        
    # ----------------------------------------------------------
    # ЗАПИСЬ
    # ----------------------------------------------------------
    def can_start_recording(self) -> bool:
        """  проверяем, можно ли начинать запись. """
        can = self.state_machine.can_start_recording(self.region is not None)
        logger.debug(f"Проверка can_start_recording → {can}")
        return can

    def start_recording(self) -> bool:
        """Начать запись (с задержкой или без)"""
        
        logger.info("Запрошен START_RECORDING")
        
        if not self.can_start_recording():
            return False

        if not self.state_machine.start_recording():
            logger.warning("StateMachine ЗАПРЕТИЛ переход")
            return False
            
        logger.debug("StateMachine перевёл в WAITING")
        
        session_dir = self.session_service.create_session()
        
        delay = self.get_start_delay()

        # Всегда отправляем WAITING в GUI (чтобы закрыть overlay)
        self.state_changed.emit(self.state_machine.get_state())
        
        if delay > 0:
            logger.debug(f"Задержка {delay} сек — ждём...")
            # self.state_changed.emit(self.state_machine.get_state())
            QTimer.singleShot(delay * 1000, lambda: self._begin_recording(session_dir))
            # return True
        else:
            # Без задержки — сразу начинаем запись
            self._begin_recording(session_dir)
        
        return True
            
    def _get_current_timer(self) -> int:
        """Получить текущее значение таймера в зависимости от типа сессии"""
        if self._session_type == SessionType.VIDEO:
            return self.settings.record.common.timer_seconds
        else:
            return self.settings.screen.common.timer_seconds  
                
    def _begin_recording(self, session_dir):
        """Фактическое начало записи после задержки"""
        
        if self.state_machine.get_state() != AppState.WAITING:
            logger.warning("Запись была отменена — не начинаем")
            return
        
        if not self.state_machine.begin_recording():
            logger.warning("Не удалось перейти в RECORDING")
            return
        
        logger.debug("StateMachine перевёл в RECORDING")
        
        self._start_time = time.time()
        self.time_updated.emit("TIME: 00:00:00")
        self.ram_updated.emit("RAM: 0 KB")
        self.shots_updated.emit(0)
        
        self.recording_service.start_recording(
            session_dir=session_dir,
            region=self.region,
            session_type=self._session_type
        )
        
        timer = self._get_current_timer()
        if timer > 0:
            self._start_auto_stop_timer(timer)
        
        self.state_changed.emit(self.state_machine.get_state())




    def stop_recording(self) -> bool:
        """  Остановить запись и перейти в состояние REVIEW.  """

        logger.info("Запрошен STOP_RECORDING")

        if not self.state_machine.can_stop_recording():
            logger.warning("Нельзя остановить запись в текущем состоянии")
            return False

        self.recording_service.stop_recording() # запись останавливается
        self.state_machine.stop_recording()   # переводим состояние в REVIEW
        logger.debug("Переход в REVIEW")
        self._emit_state()

        return True

    def finalize_session(self) -> bool:
        """ Сохранить результат и вернуться в IDLE. """
        logger.info("Запрошен FINALIZE_SESSION")

        if not self.state_machine.can_finalize_session():
            logger.warning("Нельзя финализировать в текущем состоянии")
            return False

        logger.debug("Экспортируем сессию...")

        # Получаем путь из настроек
        export_dir = Path(self.get_export_path())
        # Получаем имя файла из настроек
        filename = self.get_export_filename()

        if self._session_type == SessionType.VIDEO:
            extension = ".mp4"  # FFmpeg всегда пишет в MP4
        else:  # SCREEN
            video_format = self.settings.finalize.common.video_format
            extension = f".{video_format.lower()}"

        # Экспортируем
        result = self.session_service.export_session(export_dir, filename, extension)

        if result:
            logger.info(f"Видео сохранено: {result}")
        else:
            logger.error("Ошибка при экспорте видео")

            return False

        logger.debug("Очистка сессии")

        self.session_service.cleanup() 
        self._cleanup_runtime() # очищаем сервисы и runtime

        self.state_machine.finalize_session() # переводим состояние
        logger.debug("StateMachine перевёл в IDLE")

        self._emit_state()
        return True

    def discard_session(self) -> bool:
        """  Удалить текущую сессию без сохранения.  """
        logger.info("Запрошен DISCARD_SESSION")
        if not self.state_machine.can_discard_session():
            print("[Controller] Нельзя удалить в текущем состоянии")
            return False
        logger.debug("Удаляем временную сессию")

        self.session_service.cleanup()
        self._cleanup_runtime() # очищаем сервисы и runtime

        self.state_machine.discard_session() # переводим состояние

        logger.debug("StateMachine перевёл в IDLE")

        self._emit_state() # уведомляем GUI

        return True


    # ----------ИНФОРМАЦИЯ О ТЕКУЩЕЙ СЕССИИ----------
    def get_elapsed_time(self) -> float:
        """ Вернуть длительность текущей записи. """
        if not self._start_time:
            return 0.0
        return time.time() - self._start_time

    def get_session_size(self) -> int:
        """ Вернуть размер текущей сессии. """
        return self.session_service.get_total_size()

    def get_cpu_usage(self) -> int:
        """Возвращает текущую загрузку CPU в процентах (целое число)."""
        try:
            # psutil.cpu_percent(interval=None) возвращает мгновенную загрузку 
            # за период с момента последнего вызова (или за последнюю секунду).
            return int(psutil.cpu_percent(interval=None))
        except Exception:
            return 0


    # ============ВНУТРЕННЯЯ ЛОГИКА (GUI НЕ ДОЛЖЕН ЭТО ВЫЗЫВАТЬ)============
    def _start_auto_stop_timer(self, seconds: int):
        """ Запустить авто-остановку записи через N секунд. """
        if seconds <= 0:
            return  # авто-стоп не нужен

        # Если старый таймер был, отменяем его
        if hasattr(self, "_auto_stop_timer") and self._auto_stop_timer.isActive():
            self._auto_stop_timer.stop()

        # Создаём QTimer в основном потоке Qt
        self._auto_stop_timer = QTimer(self)
        self._auto_stop_timer.setSingleShot(True)  # одно срабатывание
        self._auto_stop_timer.timeout.connect(self.stop_recording)
        self._auto_stop_timer.start(seconds * 1000)  # QTimer работает в миллисекундах

    def _cleanup_runtime(self):
        """ Очистить runtime-данные текущей сессии. """
        logger.debug("Очистка runtime-данных")

        self.raw_coordinates = None
        self.region = None
        self._start_time = None
        self._session_type = None

        # 🔥 СБРОС ВСЕХ НАСТРОЕК
        #self.settings = SettingsModel()

        # останавливаем авто-стоп таймер
        if hasattr(self, "_auto_stop_timer") and self._auto_stop_timer.isActive():
            logger.debug("Остановка авто-таймера")
            self._auto_stop_timer.stop()

