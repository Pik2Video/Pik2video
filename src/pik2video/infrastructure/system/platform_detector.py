"""
Модуль для определения операционной системы и архитектуры.
Используется в других частях приложения (например, для загрузки правильной версии FFmpeg).
"""

import platform
import sys
from typing import Dict, Optional


class PlatformDetector:
    """
    Класс для определения платформы и архитектуры.
    """

    # Карта для нормализации названий ОС
    OS_MAP = {
        "Darwin": "macos",
        "Windows": "windows",
        "Linux": "linux",
    }

    # Карта для архитектур (нормализация)
    ARCH_MAP = {
        "x86_64": "x86_64",
        "AMD64": "x86_64",
        "arm64": "arm64",
        "aarch64": "arm64",
    }

    @classmethod
    def get_os(cls) -> str:
        """
        Возвращает название операционной системы в нормализованном виде:
        - 'macos' для macOS
        - 'windows' для Windows
        - 'linux' для Linux
        Если ОС не определена, возвращает 'unknown'.
        """
        system = platform.system()
        return cls.OS_MAP.get(system, "unknown")

    @classmethod
    def get_architecture(cls) -> str:
        """
        Возвращает архитектуру процессора в нормализованном виде:
        - 'x86_64' для 64-битных Intel/AMD
        - 'arm64' для ARM64 (Apple Silicon, некоторые Linux)
        Если архитектура не определена, возвращает 'unknown'.
        """
        arch = platform.machine()
        return cls.ARCH_MAP.get(arch, "unknown")

    @classmethod
    def is_macos(cls) -> bool:
        """Возвращает True, если система macOS."""
        return cls.get_os() == "macos"

    @classmethod
    def is_windows(cls) -> bool:
        """Возвращает True, если система Windows."""
        return cls.get_os() == "windows"

    @classmethod
    def is_linux(cls) -> bool:
        """Возвращает True, если система Linux."""
        return cls.get_os() == "linux"

    @classmethod
    def is_apple_silicon(cls) -> bool:
        """
        Проверяет, является ли система macOS на процессоре Apple Silicon (M1/M2/M3).
        Возвращает True только для macOS + arm64.
        """
        return cls.is_macos() and cls.get_architecture() == "arm64"

    @classmethod
    def is_intel(cls) -> bool:
        """
        Проверяет, является ли система Intel (x86_64) для macOS или Windows/Linux.
        """
        return cls.get_architecture() == "x86_64"

    @classmethod
    def get_full_info(cls) -> Dict[str, str]:
        """
        Возвращает полную информацию о платформе в виде словаря.
        Полезно для отладки.
        """
        return {
            "os": cls.get_os(),
            "architecture": cls.get_architecture(),
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": sys.version.split()[0],
            "processor": platform.processor() or "unknown",
        }

    @classmethod
    def get_detailed_info(cls) -> str:
        """
        Возвращает строку с подробной информацией о платформе.
        """
        info = cls.get_full_info()
        return (
            f"OS: {info['os']} ({info['system']})\n"
            f"Architecture: {info['architecture']} ({info['machine']})\n"
            f"Python: {info['python_version']}\n"
            f"Processor: {info['processor']}"
        )


# Для удобства вынесем часто используемые функции на уровень модуля
def get_os() -> str:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.get_os()


def get_architecture() -> str:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.get_architecture()


def is_macos() -> bool:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.is_macos()


def is_windows() -> bool:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.is_windows()


def is_linux() -> bool:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.is_linux()


def is_apple_silicon() -> bool:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.is_apple_silicon()


def get_full_info() -> Dict[str, str]:
    """Обёртка для быстрого вызова."""
    return PlatformDetector.get_full_info()