# src/pik2video/locale/languages.py
"""
Центральный реестр языков приложения.

Единственное место, где хранится соответствие:
- внутренний код языка ("ru", "en")
- отображаемое название ("Русский", "English")
- флаг для UI ("🇷🇺", "🇺🇸")

Раньше это знание дублировалось в SettingsManager,
AppSettingsDialog и LanguageSetting. Теперь — здесь.
"""

LANGUAGE_RU = "ru"
LANGUAGE_EN = "en"

DEFAULT_LANGUAGE = LANGUAGE_RU


# Код → отображаемое название
AVAILABLE_LANGUAGES: dict[str, str] = {
    LANGUAGE_RU: "Русский",
    LANGUAGE_EN: "English",
}

# Отображаемое название → код
LANGUAGE_CODE_MAP: dict[str, str] = {
    name: code for code, name in AVAILABLE_LANGUAGES.items()
}

# Код → флаг
LANGUAGE_FLAGS: dict[str, str] = {
    LANGUAGE_RU: "🇷🇺",
    LANGUAGE_EN: "🇺🇸",
}


def code_from_display_name(name: str) -> str:
    """'Русский' → 'ru'. Если неизвестно — DEFAULT_LANGUAGE."""
    return LANGUAGE_CODE_MAP.get(name, DEFAULT_LANGUAGE)


def display_name_from_code(code: str) -> str:
    """'ru' → 'Русский'. Если неизвестно — название по умолчанию."""
    return AVAILABLE_LANGUAGES.get(code, AVAILABLE_LANGUAGES[DEFAULT_LANGUAGE])


def flag_from_code(code: str) -> str:
    """'ru' → '🇷🇺'. Если неизвестно — белый флаг."""
    return LANGUAGE_FLAGS.get(code, "🏳️")