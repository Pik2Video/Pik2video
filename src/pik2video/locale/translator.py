# src/pik2video/locale/translator.py

import logging
from PySide6.QtCore import QObject, Signal
import json
from pathlib import Path

# Создаём логгер для этого модуля
logger = logging.getLogger(__name__)


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
        
        if getattr(sys, 'frozen', False):
            if hasattr(sys, '_MEIPASS'):
                locale_dir = Path(sys._MEIPASS) / "pik2video" / "locale"
            elif hasattr(sys, 'executable'):
                exe_path = Path(sys.executable)
                locale_dir = exe_path.parent / "Resources" / "locale"
            else:
                locale_dir = Path("locale")
        else:
            locale_dir = Path(__file__).parent
        
        json_file = locale_dir / f"{lang_code}.json"
        
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                self._translations = json.load(f)
            logger.info(f"Загружен язык: {lang_code} из {json_file}")
        except Exception as e:
            logger.error(f"Ошибка загрузки {lang_code}: {e}")
            logger.error(f"Искали в: {json_file}")
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
            logger.info(f"Язык изменен на: {lang_code}")
    
    def get_current_language(self):
        return self._current_language