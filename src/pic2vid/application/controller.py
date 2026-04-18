# src/pic2vid/application/controller.py
import time
from pathlib import Path
from typing import Optional
from PySide6.QtCore import QObject, Signal, QTimer

from .session_types import SessionType
from .recording_service import RecordingService
from .session_service import SessionService
from .settings_model import SettingsModel
from .state_machine import StateMachine, AppState

# В начале файла, где импорты
from src.pic2vid.locale.translator import Translator



class AppController(QObject):
    state_changed = Signal(AppState)     # Сигнал вызывается каждый раз при изменении состояния приложения

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
        self.recording_service = RecordingService(self.settings) # Использует текущие настройки из SettingsModel

        # ---- Runtime данные текущей сессии ----
        self.raw_coordinates: Optional[dict] = None # исходные координаты
        self.region: Optional[dict] = None          # область записи в формате для recorder
        self._start_time: Optional[float] = None    # время начала записи

    def has_active_session_data(self) -> bool:
        """Проверяет, есть ли данные в текущей сессии"""
        return self.session_service.has_data()

    def get_translator(self):
        """Вернуть менеджер переводов"""
        return self.translator

    def save_settings(self):
        """Сохранить текущие настройки в файл"""
        self.settings.save_to_file()
        print("[Controller] Настройки сохранены")

    # -----------ПЕРЕХОД В РЕЖИМ ПОДГОТОВКИ-----------

    def get_session_type(self) -> Optional[SessionType]:
        return self._session_type

    def _emit_state(self):
        """Уведомить GUI о текущем состоянии приложения."""
        current_state = self.state_machine.get_state()
        print("[Controller] Отправляем state_changed:", current_state)
        self.state_changed.emit(current_state)

    # !!!!!!!  ========== МЕТОД ДЛЯ ТЕСТОВ ========== !!!!!!!
    def set_state_dev(self, state: AppState, session_type: Optional[SessionType] = None):
        """
        DEV ONLY:
        Эмулирует реальный workflow переходов состояний,
        чтобы GUI создавал все необходимые окна корректно.
        """

        print(f"\n[Controller][DEV] Запрос состояния: {state}")

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
        print(f"[Controller][DEV] session_type = {self._session_type}")

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

            print(f"[Controller][DEV] → Эмуляция {preparing_state}")
            self.state_machine.set_state_dev(preparing_state)
            self.state_changed.emit(preparing_state)

        # =========================================================
        # 2️⃣ RECORDING
        # =========================================================

        if state in (AppState.RECORDING, AppState.REVIEW):

            print("[Controller][DEV] → Эмуляция RECORDING")

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

            print("[Controller][DEV] → Эмуляция REVIEW")

            self.state_machine.set_state_dev(AppState.REVIEW)
            self.state_changed.emit(AppState.REVIEW)


    def prepare_video(self):

        print("\n[Controller] Запрошен PREPARING_VIDEO")

        """Перевести приложение в режим подготовки записи видео."""
        if self.state_machine.prepare_video():
            self._session_type = SessionType.VIDEO
            self._emit_state()
        else:

            print("[Controller] StateMachine ЗАПРЕТИЛ переход")

    def prepare_screen(self):

        print("\n[Controller] Запрошен PREPARING_SCREEN")

        """Перевести приложение в режим подготовки записи экрана."""
        if self.state_machine.prepare_screen():
            self._session_type = SessionType.SCREEN
            self._emit_state()
        else:
            print("[Controller] StateMachine ЗАПРЕТИЛ переход")

    def cancel_session(self):

        print("\n[Controller] Запрошен CANCEL_SESSION")

        """Отменить режим подготовки и вернуться в IDLE."""
        if self.state_machine.cancel_preparing():
            self._cleanup_runtime()   # очищаем тип и координаты
            self._emit_state()
        else:

            print("[Controller] Отмена невозможна в текущем состоянии")

    # -----------УСТАНОВКА ОБЛАСТИ ЗАПИСИ-----------

    def set_raw_coordinates(self, coords: dict):
        """
        Установить координаты области записи.

        coords ожидается в формате:
        {x1, y1, x2, y2}
        """
        #print("[Controller] set_raw_coordinates вызван")
        #print("[Controller] Полученные координаты:", coords)

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

        print("[Controller] Регион установлен:", self.region)

    def update_time(self):
        """
        Вызывается CaptureSession каждую секунду.
        Считает прошедшее время и отправляет строку в GUI.
        """
        elapsed = self.get_elapsed_time()

        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        formatted = f"TIME: {hours:02}:{minutes:02}:{seconds:02}"
        self.time_updated.emit(formatted)

    def update_ram(self):
        """
        Вызывается CaptureSession каждую секунду.
        Отправляет текущий размер сессии.
        """
        size_bytes = self.get_session_size()

        formatted_size = self._format_size(size_bytes)
        self.ram_updated.emit(f"RAM: {formatted_size}")

        #self.ram_updated.emit(formatted)

    def _format_size(self, size_bytes: int) -> str:
        """
        Перевести размер из байтов в удобный формат.
        """
        if size_bytes < 1024:
            return f"{size_bytes} B"

        size_kb = size_bytes / 1024
        if size_kb < 1024:
            return f"{size_kb:.1f} KB"

        size_mb = size_kb / 1024
        if size_mb < 1024:
            return f"{size_mb:.2f} MB"

        size_gb = size_mb / 1024
        return f"{size_gb:.2f} GB"

    def update_shots(self):
        """Отправить количество кадров в GUI (для screen режима)"""
        if self.recording_service and self._session_type == SessionType.SCREEN:
            shots = self.recording_service.get_frame_count()

            # print(f"[DEBUG] update_shots: {shots}")  

            self.shots_updated.emit(shots)



    def is_recording(self) -> bool:
        return self.state_machine.get_state() == AppState.RECORDING

    def is_preparing(self) -> bool:
        return self.state_machine.get_state() in (AppState.PREPARING_VIDEO, AppState.PREPARING_SCREEN)

    def is_review(self) -> bool:
        return self.state_machine.get_state() == AppState.REVIEW


    # -------------------------------
    # RECORD SESSION
    # -------------------------------
    def get_record_fps(self) -> int:
        return self.settings.record.fps

    def set_record_fps(self, fps: int):
        self.settings.record.fps = fps
        print(f"[Controller] Record FPS установлен: {fps}")

    def get_record_quality(self) -> str:
        return self.settings.record.common.quality

    def set_record_quality(self, quality: str):
        self.settings.record.common.quality = quality
        print(f"[Controller] Record качество установленo: {quality}")

    def get_record_timer(self) -> int:
        return self.settings.record.common.timer_seconds

    def set_record_timer(self, seconds: int):
        self.settings.record.common.timer_seconds = max(0, seconds)
        print(f"[Controller] Record таймер установлен: {seconds} сек")


    # -------------------------------
    # SCREEN SESSION
    # -------------------------------
    def get_screen_fps(self) -> int:
        return self.settings.screen.capture_per_minute

    def set_screen_fps(self, value: int):
        if 1 <= value <= 100:
            self.settings.screen.capture_per_minute = value
            print(f"[Controller] Screen capture_per_minute установленo: {value}")

    def get_screen_timer(self) -> int:
        return self.settings.screen.common.timer_seconds

    def set_screen_timer(self, seconds: int):
        self.settings.screen.common.timer_seconds = max(0, seconds)
        print(f"[Controller] Screen таймер установлен: {seconds} сек")


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
            print(f"[Controller] Screen finalize FPS установлен: {fps}")


    # -------------------------------
    # Общие финальные настройки
    # -------------------------------
    def get_export_filename(self) -> str:
        """Имя файла для финальной записи (без расширения)."""
        return self.settings.finalize.common.export_filename

    def set_export_filename(self, name: str):
        self.settings.finalize.common.export_filename = name
        print(f"[Controller] Export filename установлен: {name}")

    def get_export_path(self) -> str:
        """Путь для сохранения видео."""
        path = self.settings.finalize.common.export_path
        if not path:
            path = str(Path.home() / "Desktop")
        return path

    def set_export_path(self, path: str):
        """Установить путь для сохранения видео."""
        self.settings.finalize.common.export_path = path
        print(f"[Controller] Export path установлен: {path}")

    def get_video_format(self) -> str:
        """Возвращает текущий формат видео для VideoFinalizeWindow."""
        return self.settings.finalize.common.video_format

    def set_video_format(self, fmt: str):
        """Установить формат видео для VideoFinalizeWindow."""
        allowed = ["MP4", "MKV", "AVI", "MOV"]
        if fmt not in allowed:
            fmt = "MP4"  # дефолт
        self.settings.finalize.common.video_format = fmt
        print(f"[Controller] Video format установлен: {fmt}")


    # -------------------------------
    # GLOBAL SETTINGS
    # -------------------------------
    def get_language(self) -> str:
        return self.settings.global_settings.language

    def set_language(self, value: str):
        self.settings.global_settings.language = value
        print(f"[Controller] Язык установлен: {value}")

    def get_text_size(self) -> int:
        return self.settings.global_settings.text_size

    def set_text_size(self, value: int):
        self.settings.global_settings.text_size = value
        print(f"[Controller] Размер текста установлен: {value}")

    def get_show_tooltips(self) -> bool:
        return self.settings.global_settings.show_tooltips

    def set_show_tooltips(self, value: bool):
        self.settings.global_settings.show_tooltips = value
        print(f"[Controller] Подсказки: {value}")


    # ----------------------------------------------------------
    # ЗАПИСЬ
    # ----------------------------------------------------------
    def can_start_recording(self) -> bool:
        """  проверяем, можно ли начинать запись. """
        can = self.state_machine.can_start_recording(self.region is not None)
        print("[Controller] Проверка can_start_recording →", can)
        return can
    
    def start_recording(self) -> bool:
        """Начать запись."""
        
        print("\n[Controller] Запрошен START_RECORDING")
        
        if not self.can_start_recording():
            return False

        if not self.state_machine.start_recording():
            print("[Controller] StateMachine ЗАПРЕТИЛ переход в RECORDING")
            return False
            
        print("[Controller] StateMachine перевёл в RECORDING")
        
        self._start_time = time.time()
        self.time_updated.emit("TIME: 00:00:00")
        self.ram_updated.emit("RAM: 0 KB")
        self.shots_updated.emit(0)
        
        session_dir = self.session_service.create_session()

        # Передаём тип сессии в RecordingService
        self.recording_service.start_recording(
            session_dir=session_dir,
            region=self.region,
            session_type=self._session_type  # ← добавляем это
        )

        # Если установлен авто-таймер — запускаем его
        timer = self._get_current_timer()
        if timer > 0:
            self._start_auto_stop_timer(timer)

        self.state_changed.emit(self.state_machine.get_state())
        return True

    def _get_current_timer(self) -> int:
        """Получить текущее значение таймера в зависимости от типа сессии"""
        if self._session_type == SessionType.VIDEO:
            return self.settings.record.common.timer_seconds
        else:
            return self.settings.screen.common.timer_seconds    
        
    def stop_recording(self) -> bool:
        """  Остановить запись и перейти в состояние REVIEW.  """

        print("\n[Controller] Запрошен STOP_RECORDING")

        if not self.state_machine.can_stop_recording():
            print("[Controller] Нельзя остановить запись в текущем состоянии")
            return False

        self.recording_service.stop_recording() # запись останавливается
        self.state_machine.stop_recording()   # переводим состояние в REVIEW
        print("[Controller] Переход в REVIEW")
        self._emit_state()

        return True

    def finalize_session(self) -> bool:
        """ Сохранить результат и вернуться в IDLE. """
        print("\n[Controller] Запрошен FINALIZE_SESSION")

        if not self.state_machine.can_finalize_session():
            print("[Controller] Нельзя финализировать в текущем состоянии")
            return False

        print("[Controller] Экспортируем сессию...")

        # Получаем путь из настроек
        export_dir = Path(self.get_export_path())
        # Получаем имя файла из настроек
        filename = self.get_export_filename()

        # Определяем расширение в зависимости от типа сессии
        if self._session_type == SessionType.VIDEO:
            quality = self.settings.record.common.quality
            if quality == "Низкое":
                extension = ".avi"
            elif quality == "Высокое":
                extension = ".mov"
            else:
                extension = ".mp4"
        else:  # SCREEN
            video_format = self.settings.finalize.common.video_format
            extension = f".{video_format.lower()}"

        # Экспортируем
        result = self.session_service.export_session(export_dir, filename, extension)

        if result:
            print(f"[Controller] Видео сохранено: {result}")
        else:
            print("[Controller] Ошибка при экспорте видео")
            return False

        print("[Controller] Очистка сессии")

        self.session_service.cleanup() 
        self._cleanup_runtime() # очищаем сервисы и runtime

        self.state_machine.finalize_session() # переводим состояние
        print("[Controller] StateMachine перевёл в IDLE")

        self._emit_state()
        return True

    def discard_session(self) -> bool:
        """  Удалить текущую сессию без сохранения.  """
        print("\n[Controller] Запрошен DISCARD_SESSION")
        if not self.state_machine.can_discard_session():
            print("[Controller] Нельзя удалить в текущем состоянии")
            return False
        print("[Controller] Удаляем временную сессию")

        self.session_service.cleanup()
        self._cleanup_runtime() # очищаем сервисы и runtime

        self.state_machine.discard_session() # переводим состояние

        print("[Controller] StateMachine перевёл в IDLE")

        self._emit_state() # уведомляем GUI

        return True


        #def video_session_active(self) -> bool:
            #"""
            #Проверяет, была ли запущена видеосессия.
            #"""
            # Это нужно, чтобы понять какой finalize окно показывать
            #return hasattr(self, "video_session") and self.video_session is not None


    # ----------------------------------------------------------
    # ИНФОРМАЦИЯ О ТЕКУЩЕЙ СЕССИИ
    # ----------------------------------------------------------
    def get_elapsed_time(self) -> float:
        """ Вернуть длительность текущей записи. """
        if not self._start_time:
            return 0.0
        return time.time() - self._start_time

    def get_session_size(self) -> int:
        """ Вернуть размер текущей сессии. """
        return self.session_service.get_total_size()


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
        print("[Controller] Очистка runtime-данных")

        self.raw_coordinates = None
        self.region = None
        self._start_time = None
        self._session_type = None

        # 🔥 СБРОС ВСЕХ НАСТРОЕК
        self.settings = SettingsModel()

        # останавливаем авто-стоп таймер
        if hasattr(self, "_auto_stop_timer") and self._auto_stop_timer.isActive():
            print("[Controller] Остановка авто-таймера")
            self._auto_stop_timer.stop()
