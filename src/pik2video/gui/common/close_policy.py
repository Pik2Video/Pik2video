# src/pik2video/gui/common/close_policy.py
"""
Единый центр логики закрытия окон.

Отвечает ТОЛЬКО за одно: по текущему состоянию окна решить,
что должно произойти при попытке пользователя закрыть окно.

Решения:
- закрыть молча
- спросить подтверждение и закрыть
- отменить закрытие (пользователь передумал)
- скрыть окно, приложение продолжает работу
- остановить запись, окно оставить открытым
- удалить данные сессии и закрыть

Не знает:
- про Qt (никаких QMessageBox, QWidget, QEvent)
- про конкретные окна (RecordingWindow, EditorWindow)
- про AppController

Работает с абстрактным CloseContext и коллбеком ask().
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Optional

# ─────────────────────────────────────────────────────────
#                      СЦЕНАРИИ
# ─────────────────────────────────────────────────────────

class ClosePolicy(Enum):
    """Сценарий закрытия окна."""

    ALLOW = auto()                     # закрыть без вопросов
    CONFIRM = auto()                   # всегда спрашивать
    CONFIRM_IF_RECORDING = auto()      # спросить, если идёт запись
    CONFIRM_IF_DATA = auto()           # спросить, если есть данные сессии
    CONFIRM_IF_EXPORTING = auto()      # спросить, если идёт экспорт
    HIDE_IF_EDITOR_OPEN = auto()       # скрыть, если редактор открыт
    CANCEL_PREPARING = auto()          # отменить подготовку и закрыть


# ─────────────────────────────────────────────────────────
#                     ДЕЙСТВИЯ
# ─────────────────────────────────────────────────────────

class CloseAction(Enum):
    """Что делать с окном после оценки политики."""

    CLOSE = auto()                     # закрыть окно
    CANCEL = auto()                    # отменить закрытие, окно остаётся
    HIDE = auto()                      # скрыть окно, приложение работает
    STOP_RECORDING = auto()            # остановить запись, окно остаётся
    DISCARD_AND_CLOSE = auto()         # удалить данные сессии и закрыть
    CANCEL_EXPORT_AND_CLOSE = auto()   # отменить экспорт и закрыть
    CANCEL_PREPARING_AND_CLOSE = auto()  # отменить подготовку и закрыть


# ─────────────────────────────────────────────────────────
#                     КОНТЕКСТ
# ─────────────────────────────────────────────────────────

@dataclass
class CloseContext:
    """Факты о состоянии окна/приложения на момент закрытия."""

    is_recording: bool = False
    is_preparing: bool = False
    has_data: bool = False
    is_exporting: bool = False
    editor_visible: bool = False


# ─────────────────────────────────────────────────────────
#                    ПРАВИЛА
# ─────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CloseRule:
    """
    Правило одной политики: что показать в диалоге и что делать.

    on_yes  — действие, если пользователь подтвердил
    on_no   — действие, если пользователь отказался
    on_skip — действие, если спрашивать не нужно
              (условие политики не выполнено)
    """

    text: str = ""
    title: str = "Подтверждение"
    yes_label: str = "Да"
    no_label: str = "Нет"

    on_yes: CloseAction = CloseAction.CLOSE
    on_no: CloseAction = CloseAction.CANCEL
    on_skip: CloseAction = CloseAction.CLOSE


RULES: dict[ClosePolicy, CloseRule] = {

    ClosePolicy.ALLOW: CloseRule(
        on_skip=CloseAction.CLOSE,
    ),

    ClosePolicy.CONFIRM: CloseRule(
        text="Закрыть окно?",
        on_yes=CloseAction.CLOSE,
        on_no=CloseAction.CANCEL,
    ),

    ClosePolicy.CONFIRM_IF_RECORDING: CloseRule(
        text=(
            "Запись будет остановлена.\n"
            "Файл сохранится и откроется в редакторе."
        ),
        title="Остановить запись?",
        yes_label="Остановить",
        no_label="Продолжить",
        on_yes=CloseAction.STOP_RECORDING,
        on_no=CloseAction.CANCEL,
        on_skip=CloseAction.CLOSE,
    ),

    ClosePolicy.CONFIRM_IF_DATA: CloseRule(
        text="Есть незавершённая запись.\n\nУдалить её без сохранения?",
        yes_label="Да, удалить",
        no_label="Нет, остаться",
        on_yes=CloseAction.DISCARD_AND_CLOSE,
        on_no=CloseAction.CANCEL,
        on_skip=CloseAction.CLOSE,
    ),

    ClosePolicy.CONFIRM_IF_EXPORTING: CloseRule(
        text="Идёт экспорт видео.\n\nПрервать экспорт и закрыть редактор?",
        yes_label="Прервать",
        no_label="Отмена",
        on_yes=CloseAction.CANCEL_EXPORT_AND_CLOSE,
        on_no=CloseAction.CANCEL,
        on_skip=CloseAction.CLOSE,
    ),

    ClosePolicy.HIDE_IF_EDITOR_OPEN: CloseRule(
        on_skip=CloseAction.HIDE,
    ),

    ClosePolicy.CANCEL_PREPARING: CloseRule(
        on_skip=CloseAction.CANCEL_PREPARING_AND_CLOSE,
    ),
}


# ─────────────────────────────────────────────────────────
#                    ОЦЕНКА
# ─────────────────────────────────────────────────────────

AskFunc = Callable[[CloseRule], bool]


def evaluate_close(
    policy: ClosePolicy,
    ctx: CloseContext,
    ask: Optional[AskFunc] = None,
) -> CloseAction:
    """
    Определить, что делать с окном при попытке закрытия.

    ask — коллбек, показывающий диалог и возвращающий True,
    если пользователь подтвердил действие.

    Если политика требует подтверждения, а ask не передан —
    возвращается CANCEL. Консервативное поведение: без диалога
    не закрываем.
    """
    rule = RULES[policy]

    # ── ALLOW ──
    if policy == ClosePolicy.ALLOW:
        return rule.on_skip

    # ── CONFIRM ──
    if policy == ClosePolicy.CONFIRM:
        return _ask(rule, ask)

    # ── CONFIRM_IF_RECORDING ──
    if policy == ClosePolicy.CONFIRM_IF_RECORDING:
        if not ctx.is_recording:
            return rule.on_skip
        return _ask(rule, ask)

    # ── CONFIRM_IF_DATA ──
    if policy == ClosePolicy.CONFIRM_IF_DATA:
        if not ctx.has_data:
            return rule.on_skip
        return _ask(rule, ask)

    # ── CONFIRM_IF_EXPORTING ──
    if policy == ClosePolicy.CONFIRM_IF_EXPORTING:
        if not ctx.is_exporting:
            return rule.on_skip
        return _ask(rule, ask)

    # ── HIDE_IF_EDITOR_OPEN ──
    if policy == ClosePolicy.HIDE_IF_EDITOR_OPEN:
        if ctx.editor_visible:
            return rule.on_skip
        return CloseAction.CLOSE

    # ── CANCEL_PREPARING ──
    if policy == ClosePolicy.CANCEL_PREPARING:
        if ctx.is_preparing:
            return rule.on_skip
        return CloseAction.CLOSE

    return CloseAction.CANCEL


def _ask(rule: CloseRule, ask: Optional[AskFunc]) -> CloseAction:
    """Спросить пользователя, если есть кому спросить."""
    if ask is None:
        return CloseAction.CANCEL
    if ask(rule):
        return rule.on_yes
    return rule.on_no
