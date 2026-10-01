# src/pik2video/gui/common/close_policy.py

from enum import Enum


class ClosePolicy(Enum):

    
    ALLOW = 0                      # окно можно закрыть без подтверждения

    CONFIRM = 1                    # требуется подтверждение

    CONFIRM_IF_RECORDING = 2       # подтверждение только во время записи

    CONFIRM_IF_REVIEW = 3          # подтверждение если есть результат записи