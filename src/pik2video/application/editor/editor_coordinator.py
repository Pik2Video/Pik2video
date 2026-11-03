# src/pik2video/application/editor/editor_coordinator.py
"""
Координатор бизнес-логики редактора.

Отвечает за:
- cut-skip: пропуск вырезанных участков при воспроизведении
- перескок playhead через cut (loop, стоп в конце)
- jump to start после загрузки файла / смены активного
- запрос первого кадра через play_until_first_frame
- метки таймлайна: place / delete / drag
- track drag (audio offset в state)
- scrub (перетаскивание playhead): seek + preview + resume
- подготовка к экспорту (выгрузка/возврат плеера)

Не знает:
- про виджеты (кнопки, диалоги, меню)
- про пиксели, зум, скролл (это gui/editor/timeline)

Эмитит сигналы для view (window.py), когда без UI не обойтись:
- preview_frame_ready(x, y) — показать превью кадра при scrub
- preview_hide_requested() — скрыть превью
"""

import logging

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class EditorCoordinator(QObject):
    """Бизнес-оркестратор редактора (между state и player_manager)."""

    preview_frame_ready = Signal(int, int)
    preview_hide_requested = Signal()

    def __init__(self, state, player_manager, parent=None):
        super().__init__(parent)
        self.state = state
        self.player = player_manager

        # Подписки на сигналы player_manager
        # (бизнес-слой, не Widget — работает напрямую с PlayerManager)
        self.player.position_changed.connect(self.on_player_position_changed)
        self.player.duration_changed.connect(self.on_duration_changed)

    # ── Стабы шага 1 (переедет в шаге 2) ──

    def on_player_position_changed(self, seconds: float):
        """TODO шаг 2: cut-skip, loop, стоп в конце, метки зума."""
        logger.debug(f"[COORD] position={seconds:.2f}")

    def on_duration_changed(self, seconds: float):
        """TODO шаг 2: update state + jump to start."""
        logger.debug(f"[COORD] duration={seconds:.2f}")
