# application/settings_model.py

import json
from pathlib import Path
from dataclasses import asdict, dataclass, field

# 1️⃣ ────────────Глобальные настройки приложения────────────
@dataclass
class AppGlobalSettings:
    language: str = "Русский"
    text_size: int = 12
    show_tooltips: bool = True


# 2️⃣ ────────────Общие настройки для всех сессий (Record + Screen)────────────
@dataclass
class CommonSessionSettings:
    timer_seconds: int = 0   # 0 = без ограничения
    quality: str = "Среднее" # применимо к обоим типам
    # сюда потом можно добавить ещё общие настройки


# 3️⃣ ────────────Настройки видеозаписи────────────
@dataclass
class RecordSettings:
    fps: int = 30
    common: CommonSessionSettings = field(default_factory=CommonSessionSettings)

# 4️⃣ ────────────Настройки скриншотов────────────
@dataclass
class ScreenSettings:
    capture_per_minute: int = 10
    common: CommonSessionSettings = field(default_factory=CommonSessionSettings)



# ────────────Финальные настройки для screen capture────────────
@dataclass
class FinalizeScreenSettings:
    playback_fps: int = 10

# ────────────Общие финальные настройки для всех сессий────────────
@dataclass
class FinalizeCommonSettings:
    export_filename: str = "output"  # имя файла без расширения
    video_format: str = "MP4"  # общая настройка формата видео для обоих сценариев
    export_path: str = ""  # пустая строка — будем использовать дефолт




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
            filepath = Path.home() / ".pic2vid" / "settings.json"
        
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
        
        print(f"[Settings] Сохранено в {filepath}")
    
    def load_from_file(self, filepath: Path = None):
        """Загружает настройки из JSON файла"""
        if filepath is None:
            filepath = Path.home() / ".pic2vid" / "settings.json"
        
        if not filepath.exists():
            print(f"[Settings] Файл не найден, используем настройки по умолчанию")
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
            
            # Загружаем настройки записи
            if "record" in data:
                r = data["record"]
                self.record.fps = r.get("fps", 30)
                if "common" in r:
                    self.record.common.timer_seconds = r["common"].get("timer_seconds", 0)
                    self.record.common.quality = r["common"].get("quality", "Среднее")
            
            # Загружаем настройки экрана
            if "screen" in data:
                s = data["screen"]
                self.screen.capture_per_minute = s.get("capture_per_minute", 10)
                if "common" in s:
                    self.screen.common.timer_seconds = s["common"].get("timer_seconds", 0)
                    self.screen.common.quality = s["common"].get("quality", "Среднее")
            
            # Загружаем финальные настройки
            if "finalize" in data:
                f = data["finalize"]
                if "screen" in f:
                    self.finalize.screen.playback_fps = f["screen"].get("playback_fps", 10)
                if "common" in f:
                    self.finalize.common.export_filename = f["common"].get("export_filename", "output")
                    self.finalize.common.video_format = f["common"].get("video_format", "MP4")
                    self.finalize.common.export_path = f["common"].get("export_path", "")
            
            print(f"[Settings] Загружено из {filepath}")
            return True
            
        except Exception as e:
            print(f"[Settings] Ошибка загрузки: {e}")
            return False
