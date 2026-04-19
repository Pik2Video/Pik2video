# src/pik2video/locale/translator.py

from PySide6.QtCore import QObject, Signal
import json
from pathlib import Path

class Translator(QObject):
    language_changed = Signal()
    
    def __init__(self):
        super().__init__()
        self._current_language = "ru"
        self._translations = {}
        self.load_language(self._current_language)
    
    def load_language(self, lang_code):
        """Загружает JSON файл с переводами"""
        
        # Определяем путь к файлу в зависимости от того, запущено ли приложение как собранное
        import sys
        
        # Определяем путь к файлу в зависимости от того, запущено ли приложение как собранное
        if getattr(sys, 'frozen', False):
            # Запущено как собранное приложение (.app)
            # Пробуем разные возможные пути
            possible_paths = []
            
            if hasattr(sys, '_MEIPASS'):
                # PyInstaller временная папка
                possible_paths.append(Path(sys._MEIPASS) / "locale")
            
            # Папка Resources в .app
            if hasattr(sys, 'executable'):
                exe_path = Path(sys.executable)
                possible_paths.append(exe_path.parent / "Resources" / "locale")
                possible_paths.append(exe_path.parent / "pik2video" / "locale")
            
            # Ищем первый существующий путь
            locale_dir = None
            for path in possible_paths:
                if path.exists():
                    locale_dir = path
                    break
            
            if locale_dir is None:
                # Если не нашли - используем первый вариант
                locale_dir = possible_paths[0] if possible_paths else Path("locale")
        else:
            # Запущено как скрипт (разработка)
            locale_dir = Path(__file__).parent
        
        json_file = locale_dir / f"{lang_code}.json"
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                self._translations = json.load(f)
            print(f"[Translator] Загружен язык: {lang_code} из {json_file}")
        except Exception as e:
            print(f"[Translator] Ошибка загрузки {lang_code}: {e}")
            print(f"[Translator] Искали в: {json_file}")
            self._translations = {}
    
    def tr(self, key):
        """Переводит ключ в текст"""
        return self._translations.get(key, key)
    
    def set_language(self, lang_code):
        """Смена языка"""
        if lang_code != self._current_language:
            self._current_language = lang_code
            self.load_language(lang_code)
            self.language_changed.emit()
            print(f"[Translator] Язык изменен на: {lang_code}")
    
    def get_current_language(self):
        return self._current_language