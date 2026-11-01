# src/pik2video/gui/editor/panels/__init__.py
"""
Пакет панелей редактора.

Содержит:
- TopBar — верхняя полоса: пресеты, ⛶, запись
- ToolsPanel — левая колонка: инструменты и настройки
- GlobalSettingsPanel — глобальные настройки
- BottomPanel — нижняя панель: экспорт, очистка
- DropArea — правая колонка: видео + аудио
- DropZone — зона приёма одного типа файлов
- LinkButton — кнопка связки видео+аудио
- VideoFilesPanel — список видеофайлов
"""

from .bottom_panel import BottomPanel
from .drop_area import DropArea
from .drop_zone import DropZone
from .global_settings_panel import GlobalSettingsPanel
from .link_button import LinkButton
from .tools_panel import ToolsPanel
from .top_bar import TopBar
from .video_files_panel import VideoFilesPanel

__all__ = [
    "BottomPanel",
    "DropArea",
    "DropZone",
    "GlobalSettingsPanel",
    "LinkButton",
    "ToolsPanel",
    "TopBar",
    "VideoFilesPanel",
]
