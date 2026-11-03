# src/pik2video/application/editor/__init__.py
"""
Пакет бизнес-логики редактора.

Отделяет модель и сервисы редактора от GUI (gui/editor/).

Содержит:
- editor_controller.py — фасад для GUI (аналог AppController)
- editor_state.py — модель данных редактора
- export_service.py — сборка ffmpeg-команд
- managers/ — узкие менеджеры (timeline, player)
"""

from .editor_controller import EditorController

__all__ = ["EditorController"]
