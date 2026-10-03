# src/pik2video/app/blink_manager.py
"""
Единый менеджер мигания.

Управляет одной фазой (0.0 … 1.0) и её направлением.
Все виджеты, которым нужно мигать, подписываются на сигнал phase_changed.
Сам менеджер ничего не знает о виджетах — только генерирует фазу.
"""

import logging

from PySide6.QtCore import QObject, QTimer, Signal

logger = logging.getLogger(__name__)


class BlinkManager(QObject):
    """Генератор фазы мигания. Публикует phase_changed(float)."""

    phase_changed = Signal(float)

    def __init__(self, step: float = 0.04, interval_ms: int = 40, parent=None):
        super().__init__(parent)
        self._step = step
        self._interval_ms = interval_ms

        self._phase = 1.0
        self._direction = -1  # -1 = затухает, +1 = нарастает

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ---------- API ----------

    def start(self):
        """Запустить таймер мигания."""
        if not self._timer.isActive():
            self._timer.start(self._interval_ms)

    def stop(self):
        """Остановить таймер мигания."""
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()

    def reset(self, phase: float = 1.0, direction: int = -1):
        """Сбросить фазу и направление."""
        self._phase = max(0.0, min(1.0, phase))
        self._direction = -1 if direction < 0 else 1

    def get_phase(self) -> float:
        return self._phase

    # ---------- Internal ----------

    def _tick(self):
        self._phase += self._step * self._direction

        if self._phase >= 1.0:
            self._phase = 1.0
            self._direction = -1
        elif self._phase <= 0.0:
            self._phase = 0.0
            self._direction = 1

        self.phase_changed.emit(self._phase)
