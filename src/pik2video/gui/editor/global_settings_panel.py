# src/pik2video/gui/editor/global_settings_panel.py
"""
Панель глобальных настроек для встраивания в ToolsPanel.

Отвечает только за:
- показ виджетов настроек (язык, размер текста, подсказки, всегда сверху)
- применение изменений в контроллер (сразу, без кнопок)

Не знает:
- про окно-диалог
- про другие страницы ToolsPanel
"""

import logging

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from src.pik2video.gui.common.tooltip import set_tooltips_enabled
from src.pik2video.gui.widgets.global_settings import (
    AlwaysOnTopSetting,
    AutoHideEditorSetting,
    LanguageSetting,
    TextSizeSetting,
    TooltipsSetting,
)

logger = logging.getLogger(__name__)


class GlobalSettingsPanel(QWidget):
    """Панель глобальных настроек для встраивания в левую колонку редактора."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.translator = controller.get_translator()

        self._build_ui()
        self._apply_localization()

        self.translator.language_changed.connect(self._apply_localization)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Верхний контейнер (шапка + строки) ──
        top = QWidget()
        top.setStyleSheet("background: transparent; border: none;")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(8, 8, 8, 8)
        top_layout.setSpacing(8)

        self.title = QLabel("Настройки")
        self.title.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        top_layout.addWidget(self.title)

        self.language_setting = LanguageSetting(self.controller)
        self.text_size_setting = TextSizeSetting(self.controller)
        self.tooltips_setting = TooltipsSetting(self.controller)
        self.always_on_top_setting = AlwaysOnTopSetting(self.controller)
        self.auto_hide_setting = AutoHideEditorSetting(self.controller)

        self.row_language = self._make_row(self.language_setting)
        self.row_text_size = self._make_row(self.text_size_setting)
        self.row_tooltips = self._make_row(self.tooltips_setting)
        self.row_always_on_top = self._make_row(self.always_on_top_setting)
        self.row_auto_hide = self._make_row(self.auto_hide_setting)

        top_layout.addWidget(self.row_language)
        top_layout.addWidget(self.row_text_size)
        top_layout.addWidget(self.row_tooltips)
        top_layout.addWidget(self.row_always_on_top)
        top_layout.addWidget(self.row_auto_hide)
        top_layout.addStretch()

        layout.addWidget(top, stretch=1)

        # ── Сигналы: применяем сразу ──
        self.language_setting.language_changed.connect(self._on_language_changed)
        self.text_size_setting.size_changed.connect(self._on_text_size_changed)
        self.tooltips_setting.toggled.connect(self._on_tooltips_changed)
        self.always_on_top_setting.toggled.connect(self._on_always_on_top_changed)
        self.auto_hide_setting.toggled.connect(self._on_auto_hide_changed)

    def _make_row(self, control: QWidget) -> QWidget:
        """Компактная строка: label слева, control справа."""
        row = QWidget()
        row.setStyleSheet("background: transparent; border: none;")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        label = QLabel("")
        label.setWordWrap(True)
        label.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )
        row_layout.addWidget(label, stretch=1)
        row_layout.addWidget(control, stretch=0)

        row._label = label
        return row

    def _apply_localization(self):
        """Обновить тексты по текущему языку."""
        self.title.setText(self.translator.tr("settings"))
        self.row_language._label.setText(self.translator.tr("language_setting"))
        self.row_text_size._label.setText(self.translator.tr("text_size_setting"))
        self.row_tooltips._label.setText(self.translator.tr("show_tooltips"))
        self.row_always_on_top._label.setText(self.translator.tr("always_on_top"))
        self.row_auto_hide._label.setText(self.translator.tr("auto_hide_editor"))

    # ── Обработчики (применяем сразу и сохраняем) ──

    def _on_language_changed(self, value: str):
        self.controller.set_language(value)
        self.controller.save_settings()

    def _on_text_size_changed(self, value: int):
        self.controller.set_text_size(value)
        self.controller.save_settings()

    def _on_tooltips_changed(self, value: bool):
        self.controller.set_show_tooltips(value)
        self.controller.save_settings()
        set_tooltips_enabled(value)

    def _on_always_on_top_changed(self, value: bool):
        self.controller.set_always_on_top(value)
        self.controller.save_settings()

    def _on_auto_hide_changed(self, value: bool):
        self.controller.set_auto_hide_editor(value)
        self.controller.save_settings()
