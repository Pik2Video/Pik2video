# application/settings_model.py

import logging

import json
from pathlib import Path
from dataclasses import asdict, dataclass, field

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


# 2️⃣ ────────────Общие настройки для всех сессий (Record + Screen)────────────
@dataclass
class CommonSessionSettings:
    timer_seconds: int = 0    # 0 = без ограничения
    quality: str = "Среднее"  # применимо к обоим типам
    start_delay: int = 0      # пауза перед стартом
    # сюда потом можно добавить ещё общие настройки


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



# ────────────Финальные настройки для screen capture────────────
@dataclass
class FinalizeScreenSettings:
    playback_fps: int = 10
    speed_multiplier: float = 1.0  # 🆕

# ────────────Общие финальные настройки для всех сессий────────────
@dataclass
class FinalizeCommonSettings:
    export_filename: str = "output"  # имя файла без расширения
    video_format: str = "MP4"        # общая настройка формата видео для обоих сценариев
    export_path: str = ""            # пустая строка — будем использовать дефолт
    resolution: str = "original"     # 🆕 original, 1080p, 720p, 480p
    bitrate_mode: str = "auto"       # 🆕 auto, manual
    bitrate_value: str = "4M"        # 🆕 для manual
    rotation: int = 0                # 🆕 0, 90, 180, 270




# ────────────Финальные настройки записи────────────
@dataclass
class FinalizeSettings:
    screen: FinalizeScreenSettings = field(default_factory=FinalizeScreenSettings)
    common: FinalizeCommonSettings = field(default_factory=FinalizeCommonSettings)

# 5️⃣ ────────────Главная модель настроек────────────
@dataclass
class SettingsModel:
    global_settings: AppGlobalSettings = field(default_factory=AppGlobalSettings)
    record: RecordSettings = field(default_factory=RecordSettings)
    screen: ScreenSettings = field(default_factory=ScreenSettings)

    finalize: FinalizeSettings = field(default_factory=FinalizeSettings)

    def save_to_file(self, filepath: Path = None):
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
            "finalize": asdict(self.finalize)
        }
        
        # Сохраняем в файл
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        logger.debug(f"Настройки сохранены в {filepath}")
    
    def load_from_file(self, filepath: Path = None):
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
                self.global_settings.preset_vertical = gs.get("preset_vertical", False)  # 🆕
            
            # Загружаем настройки записи
            if "record" in data:
                r = data["record"]
                self.record.fps = r.get("fps", 30)
                if "common" in r:
                    self.record.common.timer_seconds = r["common"].get("timer_seconds", 0)
                    self.record.common.quality = r["common"].get("quality", "Среднее")
                    self.record.common.start_delay = r["common"].get("start_delay", 0)  # пауза перед стартом
            
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
                if "screen" in f:
                    self.finalize.screen.playback_fps = f["screen"].get("playback_fps", 10)
                if "common" in f:
                    self.finalize.common.export_filename = f["common"].get("export_filename", "output")
                    self.finalize.common.video_format = f["common"].get("video_format", "MP4")
                    self.finalize.common.export_path = f["common"].get("export_path", "")
                    self.finalize.common.resolution = f["common"].get("resolution", "original")        # 🆕
                    self.finalize.common.bitrate_mode = f["common"].get("bitrate_mode", "auto")        # 🆕
                    self.finalize.common.bitrate_value = f["common"].get("bitrate_value", "4M")        # 🆕
                    self.finalize.common.rotation = f["common"].get("rotation", 0)                     # 🆕
            
            logger.debug(f"Настройки загружены из {filepath}")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка загрузки настроек: {e}")
            return False
