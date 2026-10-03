# src/pik2video/gui/editor/tools_panel.py
"""
Панель инструментов редактора (зона 2).

Отвечает только за:
- сетку инструментов (label слева, кнопка справа)
- состояние «None» когда нет файла
- нижний блок «Информация» с метками и скоростью
"""

import logging
from datetime import timedelta

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout, QWidget

from .global_settings_panel import GlobalSettingsPanel
from .tools.bitrate import BitrateTool
from .tools.format import FormatTool
from .tools.resolution import ResolutionTool
from .tools.rotation import RotationTool
from .tools.speed import SpeedTool

logger = logging.getLogger(__name__)


TOOL_WIDTH = 106
TOOL_HEIGHT = 26
LABEL_WIDTH = 70


class ToolsPanel(QFrame):
    """Левая колонка с инструментами и блоком «Информация»."""

    def __init__(self, state, controller, parent=None):
        super().__init__(parent)
        self.state = state
        self.controller = controller

        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("""
            ToolsPanel {
                background-color: #2a2a2a;
                border: 1px solid #444;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Стек: страницы «Инструменты» и «Настройки» ──
        self._stack = QStackedWidget()
        self._stack.setStyleSheet("background: transparent; border: none;")
        root.addWidget(self._stack)

        # ── Страница 0: инструменты ──
        tools_page = QWidget()
        tools_page.setStyleSheet("background: transparent; border: none;")
        tools_root = QVBoxLayout(tools_page)
        tools_root.setContentsMargins(0, 0, 0, 0)
        tools_root.setSpacing(0)

        top = QWidget()
        top.setStyleSheet("background: transparent; border: none;")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(8, 8, 8, 8)
        top_layout.setSpacing(6)

        title = QLabel("Инструменты")
        title.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: bold; "
            "background: transparent; border: none;"
        )
        top_layout.addWidget(title)

        grid = QGridLayout()
        grid.setContentsMargins(0, 4, 6, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)

        self._tool_stacks = []

        self.format_tool = FormatTool(initial=self.state.get_format())
        self.format_tool.valueChanged.connect(self.state.set_format)
        self._add_tool(grid, 0, "Формат", self.format_tool)

        self.resolution_tool = ResolutionTool(initial=self.state.get_resolution())
        self.resolution_tool.valueChanged.connect(self.state.set_resolution)
        self._add_tool(grid, 1, "Разрешение", self.resolution_tool)

        self.bitrate_tool = BitrateTool(
            mode=self.state.get_bitrate_mode(),
            value=self.state.get_bitrate_value(),
        )
        self.bitrate_tool.valueChanged.connect(self.state.set_bitrate)
        self._add_tool(grid, 2, "Битрейт", self.bitrate_tool)

        self.rotation_tool = RotationTool(initial=self.state.get_rotation())
        self.rotation_tool.valueChanged.connect(self.state.set_rotation)
        self._add_tool(grid, 3, "Поворот", self.rotation_tool)

        top_layout.addLayout(grid)
        top_layout.addStretch()

        tools_root.addWidget(top, stretch=1)

        self.info_block = self._build_info_block()
        tools_root.addWidget(self.info_block, stretch=0)

        self._stack.addWidget(tools_page)

        # ── Страница 1: настройки ──
        self._settings_panel = GlobalSettingsPanel(self.controller)
        self._stack.addWidget(self._settings_panel)

        # По умолчанию — инструменты
        self._stack.setCurrentIndex(0)

        # ── Обновления ──
        self.state.videos_changed.connect(self._update_all)
        self.state.active_video_changed.connect(lambda _: self._update_all())
        self.state.video_loaded.connect(lambda _: self._update_all())
        self.state.video_unloaded.connect(self._update_all)
        self.state.trim_changed.connect(lambda *_: self._update_all())
        self.state.settings_changed.connect(self._update_all)

        self._update_all()

    def show_tools(self):
        """Показать страницу инструментов."""
        self._stack.setCurrentIndex(0)

    def show_settings(self):
        """Показать страницу глобальных настроек."""
        self._stack.setCurrentIndex(1)

    def _add_tool(self, grid: QGridLayout, row: int, label_text: str, tool: QWidget):
        """Добавить строку: label + stacked (tool / None)."""
        label = QLabel(label_text)
        label.setFixedWidth(LABEL_WIDTH)
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        label.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )

        stack = QStackedWidget()
        stack.setFixedSize(TOOL_WIDTH, TOOL_HEIGHT)
        stack.setStyleSheet("background: transparent; border: none;")

        # Страница 0 — инструмент
        stack.addWidget(tool)

        # Страница 1 — None
        none_label = QLabel("None")
        none_label.setAlignment(Qt.AlignCenter)
        none_label.setStyleSheet(
            "color: #555; font-size: 11px; "
            "background: #1e1e1e; border: 1px solid #3a3a3a;"
        )
        stack.addWidget(none_label)

        grid.addWidget(label, row, 0)
        grid.addWidget(stack, row, 1, alignment=Qt.AlignRight)

        self._tool_stacks.append(stack)

    def _build_info_block(self) -> QFrame:
        """Тёмный блок снизу: метки + скорость."""
        block = QFrame()
        block.setStyleSheet("""
            QFrame {
                background-color: #151515;
                border: none;
                border-top: 1px solid #000;
            }
        """)

        layout = QVBoxLayout(block)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(2)

        self.lbl_duration = QLabel("Длительность:  --")
        self.lbl_size = QLabel("Размер:        --")
        self.lbl_resolution = QLabel("Разрешение:    --")

        for lbl in (self.lbl_duration, self.lbl_size, self.lbl_resolution):
            lbl.setStyleSheet(
                "color: #888; font-size: 11px; "
                "background: transparent; border: none;"
            )
            layout.addWidget(lbl)

        layout.addSpacing(8)

        speed_row = QWidget()
        speed_row.setStyleSheet("background: transparent; border: none;")
        speed_layout = QHBoxLayout(speed_row)
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.setSpacing(8)

        speed_label = QLabel("Скорость")
        speed_label.setFixedWidth(LABEL_WIDTH)
        speed_label.setStyleSheet(
            "color: #ccc; font-size: 11px; background: transparent; border: none;"
        )
        speed_layout.addWidget(speed_label)
        speed_layout.addStretch()

        self.speed_tool = SpeedTool(initial=self.state.get_speed())
        self.speed_tool.valueChanged.connect(self.state.set_speed)
        speed_layout.addWidget(self.speed_tool)

        layout.addWidget(speed_row)

        return block

    def _update_all(self):
        """Переключить состояние инструментов и обновить метки."""
        has_file = self.state.has_videos()
        for stack in self._tool_stacks:
            stack.setCurrentIndex(0 if has_file else 1)
        self.speed_tool.setEnabled(has_file)
        self._update_info()

    def _update_info(self):
        """Обновить метки по текущему состоянию."""
        if not self.state.has_videos():
            self.lbl_duration.setText("Длительность:  --")
            self.lbl_size.setText("Размер:        --")
            self.lbl_resolution.setText("Разрешение:    --")
            return

        start, end = self.state.get_trim()
        duration = end - start if end > start else 0.0
        speed = self.state.get_speed() or 1.0
        final_duration = duration / speed

        self.lbl_duration.setText(
            f"Длительность:  {self._format_duration(final_duration)}"
        )

        path = self.state.get_video_path()
        try:
            from pathlib import Path
            size_bytes = Path(path).stat().st_size
            self.lbl_size.setText(f"Размер:        {self._format_size(size_bytes)}")
        except Exception:
            self.lbl_size.setText("Размер:        --")

        self.lbl_resolution.setText("Разрешение:    --")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        td = timedelta(seconds=int(seconds))
        total = int(td.total_seconds())
        m, s = divmod(total, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}"
        return f"{m:02}:{s:02}"

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        if size_bytes < 1024:
            return f"{size_bytes} B"
        kb = size_bytes / 1024
        if kb < 1024:
            return f"{kb:.1f} KB"
        mb = kb / 1024
        if mb < 1024:
            return f"{mb:.2f} MB"
        gb = mb / 1024
        return f"{gb:.2f} GB"
