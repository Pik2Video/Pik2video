# src/pik2video/application/settings_model.py
import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 1️⃣ ────────────Глобальные настройки приложения────────────
@dataclass
class AppGlobalSettings:
    language: str = "Русский"
    text_size: int = 12
    show_tooltips: bool = True
    # start_delay: int = 0 
    always_on_top: bool = False
    preset_vertical: bool = False  # 🆕 false = горизонтально, true = вертикально
    auto_hide_editor: bool = True  # 🆕 автоскрытие редактора при старте записи True = установлен чек бокс
    show_recording_frame: bool = True  # показывать серебристую рамку захвата во время записи


# 2️⃣ ────────────Общие настройки для всех сессий (Record + Screen)────────────
@dataclass
class CommonSessionSettings:
    timer_seconds: int = 0    # 0 = без ограничения
    quality: str = "Среднее"  # применимо к обоим типам
    start_delay: int = 0      # пауза перед стартом
    audio_enabled: bool = False                                  # писать ли звук вместе с видео/скрином
    audio_sources: list = field(default_factory=lambda: ["system"])   # по умолчанию — системный звук
    audio_device: str = ""                                       # id или имя микрофона ("" = по умолчанию)


# 3️⃣ ────────────Настройки видеозаписи────────────
@dataclass
class RecordSettings:
    fps: int = 30
    common: CommonSessionSettings = field(default_factory=CommonSessionSettings)

# 4️⃣ ────────────Настройки скриншотов────────────
@dataclass
class ScreenSettings:
    capture_fps: int = 1
    common: CommonSessionSettings = field(default_factory=CommonSessionSettings)


@dataclass
class AudioSettings:
    timer_seconds: int = 0                                       # таймер авто-стопа для аудио-сессии
    start_delay: int = 0                                         # пауза перед стартом, сек
    sources: list = field(default_factory=lambda: ["system"])       # активные источники: "mic", "system"
    device: str = ""                                             # id или имя микрофона ("" = по умолчанию)
    sample_rate: int = 48000                                     # частота дискретизации
    channels: int = 2                                            # 1 = моно, 2 = стерео
    export_filename: str = ""                                    # имя файла аудио-записи ("" = авто)

# ────────────Общие финальные настройки для всех сессий────────────
@dataclass
class FinalizeCommonSettings:
    export_filename: str = ""  # имя файла без расширения; пусто = использовать имя исходника

# ────────────Финальные настройки записи────────────
@dataclass
class FinalizeSettings:
    common: FinalizeCommonSettings = field(default_factory=FinalizeCommonSettings)

# 5️⃣ ────────────Главная модель настроек────────────
@dataclass
class SettingsModel:
    global_settings: AppGlobalSettings = field(default_factory=AppGlobalSettings)
    record: RecordSettings = field(default_factory=RecordSettings)
    screen: ScreenSettings = field(default_factory=ScreenSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)  # настройки чистой аудио-сессии

    finalize: FinalizeSettings = field(default_factory=FinalizeSettings)

    def save_to_file(self, filepath: Optional[Path] = None):
        """Сохраняет настройки в JSON файл"""
        if filepath is None:
            filepath = Path.home() / ".pik2video" / "settings.json"
        
        # Создаем директорию, если её нет
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Преобразуем dataclass в словарь
        data = {
            "global_settings": asdict(self.global_settings),
            "record": asdict(self.record),
            "screen": asdict(self.screen),
            "audio": asdict(self.audio),                            # сохраняем настройки чистой аудио-сессии
            "finalize": asdict(self.finalize)
        }
        
        # Сохраняем в файл
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Настройки сохранены в {filepath}")
    
    def load_from_file(self, filepath: Optional[Path] = None):
        """Загружает настройки из JSON файла"""
        if filepath is None:
            filepath = Path.home() / ".pik2video" / "settings.json"
        
        if not filepath.exists():
            logger.info("Файл настроек не найден, используем значения по умолчанию")
            return False
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Загружаем глобальные настройки
            if "global_settings" in data:
                gs = data["global_settings"]
                self.global_settings.language = gs.get("language", "Русский")
                self.global_settings.text_size = gs.get("text_size", 12)
                self.global_settings.show_tooltips = gs.get("show_tooltips", True)
                self.global_settings.always_on_top = gs.get("always_on_top", False)
                self.global_settings.preset_vertical = gs.get("preset_vertical", False)
                self.global_settings.auto_hide_editor = gs.get("auto_hide_editor", False)  # 🆕
                self.global_settings.show_recording_frame = gs.get("show_recording_frame", True)
            
            # Загружаем настройки записи
            if "screen" in data:
                s = data["screen"]
                self.screen.capture_fps = s.get("capture_fps", 1)
                if "common" in s:
                    c = s["common"]
                    self.screen.common.timer_seconds = c.get("timer_seconds", 0)
                    self.screen.common.quality = c.get("quality", "Среднее")
                    self.screen.common.start_delay = c.get("start_delay", 0)
                    self.screen.common.audio_enabled = c.get("audio_enabled", False)      # флаг записи звука для скрина
                    self.screen.common.audio_sources = c.get("audio_sources", [])         # источники звука для скрина
                    self.screen.common.audio_device = c.get("audio_device", "")           # микрофон для скрина
            
            if "audio" in data:
                a = data["audio"]
                self.audio.timer_seconds = a.get("timer_seconds", 0)                       # таймер аудио-сессии
                self.audio.start_delay = a.get("start_delay", 0)                           # пауза перед стартом
                self.audio.sources = a.get("sources", ["system"])                             # источники звука
                self.audio.device = a.get("device", "")                                    # микрофон
                self.audio.sample_rate = a.get("sample_rate", 48000)                       # частота дискретизации
                self.audio.channels = a.get("channels", 2)                                 # число каналов
                self.audio.export_filename = a.get("export_filename", "")                  # имя файла аудио-записи                            # число каналов

            # Загружаем настройки экрана
            if "screen" in data:
                s = data["screen"]
                self.screen.capture_fps = s.get("capture_fps", 1)
                if "common" in s:
                    self.screen.common.timer_seconds = s["common"].get("timer_seconds", 0)
                    self.screen.common.quality = s["common"].get("quality", "Среднее")
                    self.screen.common.start_delay = s["common"].get("start_delay", 0)  # пауза перед стартом
            
            # Загружаем финальные настройки
            if "finalize" in data:
                f = data["finalize"]
                if "common" in f:
                    self.finalize.common.export_filename = f["common"].get("export_filename", "")
            
            logger.debug(f"Настройки загружены из {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
            return False
