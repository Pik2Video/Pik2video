# src/pik2video/gui/close_policy.py

from enum import Enum


class ClosePolicy(Enum):

    # окно можно закрыть без подтверждения
    ALLOW = 0

    # требуется подтверждение
    CONFIRM = 1

    # подтверждение только во время записи
    CONFIRM_IF_RECORDING = 2

    # подтверждение если есть результат записи
    CONFIRM_IF_REVIEW = 3