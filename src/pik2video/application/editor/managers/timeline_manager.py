# src/pik2video/application/editor/managers/timeline_manager.py
"""
Менеджер таймлайна.

Отвечает за:
- cut-интервалы (что вырезается)
- visible-интервалы (что видно, с учётом скрытых cut)
- скрытие/восстановление cut
- конвертации visual_sec ↔ real_sec

Не знает:
- про GUI (пиксели, зум, скролл)
- про QMediaPlayer

TODO: перенос методов из EditorState и window.py (поэтапно).
"""

import logging

logger = logging.getLogger(__name__)


class TimelineManager:
    """Скелет. Пока пустой, будет наполняться при переносе."""

    def __init__(self, state):
        self._state = state
        logger.debug("TimelineManager инициализирован (скелет)")
