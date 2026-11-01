# src/pik2video/gui/common/styles/editor.py
"""
QSS для окна редактора видео и его зон.

Константы по доменам (добавляются по мере миграции):
- EDITOR_WINDOW_QSS   — QMainWindow + central widget
- TOP_BAR_QSS         — TopBar + tools_block + presets + zoom + record
- TOOLS_PANEL_QSS     — ToolsPanel + info_block + app_info_block
- BOTTOM_PANEL_QSS    — BottomPanel + export_block + clear_frame
- PLAYER_QSS          — PlayerWidget + controls bar
- VOLUME_QSS          — VolumeControl + VolumePopup
- DROP_AREA_QSS       — VideoFilesPanel + DropZone + LinkButton
- TOOL_BUTTON_QSS     — FormatTool / ResolutionTool / RotationTool /
                        SpeedTool / BitrateTool
- RECORD_MENU_QSS     — _DimOverlayWindow + _RecordMenuWindow

Применение: self.setStyleSheet(BOTTOM_PANEL_QSS) на корневом виджете.
objectName-изоляция для контейнеров обязательна — иначе каскад заденет детей.
"""


EDITOR_WINDOW_QSS = ""
TOP_BAR_QSS = ""
TOOLS_PANEL_QSS = ""

BOTTOM_PANEL_QSS = """
QWidget#bottomPanel {
    background-color: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
}
QWidget#exportBlock {
    background-color: #383838;
    border: 1px solid #555;
    border-radius: 4px;
}
QFrame#exportNameFrame {
    background-color: #1e1e1e;
    border: 1px solid #444;
    border-radius: 4px;
}
QPushButton#exportPathValue {
    background-color: transparent;
    border: none;
    color: #5fbfbf;
    font-size: 13px;
    text-align: right;
    padding: 6px 10px;
}
QPushButton#exportPathValue:hover {
    color: #7fd8d8;
}
QPushButton#btnExport {
    background-color: #2a7a2a;
    border: 1px solid #3a9a3a;
    border-radius: 4px;
    color: white;
    font-size: 11px;
    font-weight: bold;
}
QPushButton#btnExport:hover { background-color: #3a9a3a; }
QPushButton#btnExport:pressed { background-color: #1a5a1a; }
QPushButton#btnExport:disabled {
    background-color: #2a2a2a;
    border: 1px solid #444;
    color: #555;
}
QFrame#clearFrame {
    background-color: #2a2a2a;
    border: 2px dashed #555;
    border-radius: 6px;
}
QPushButton#btnClear {
    background-color: #5a1a1a;
    border: 1px solid #7a2a2a;
    border-radius: 4px;
    color: #e0c0c0;
    font-size: 10px;
}
QPushButton#btnClear:hover { background-color: #7a2a2a; }
QPushButton#btnClear:pressed { background-color: #3a0a0a; }
QPushButton#btnClear:disabled {
    background-color: #2a2a2a;
    border: 1px solid #444;
    color: #666;
}
"""

PLAYER_QSS = """
/* ── Фон плеера (по умолчанию прозрачный для вложенных виджетов) ── */
QWidget {
    background: transparent;
}

/* ── Панель управления (нижняя полоса) ── */
QWidget#controlBar {
    background-color: #2a2a2a;
    border: 1px solid #444;
    border-radius: 4px;
}

/* ── Базовые кнопки (транспорт) ── */
QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #555;
    border-radius: 4px;
    color: #e0e0e0;
    font-size: 12px;
}
QPushButton:hover { background-color: #4a4a4a; }
QPushButton:pressed { background-color: #2a2a2a; }
QPushButton:disabled { color: #555; background-color: #2a2a2a; border-color: #444; }

/* Специфичные кнопки */
QPushButton#btnLoop:checked {
    background-color: #5a5a5a;
    border-color: #888;
}

QPushButton#btnSpeed {
    font-size: 11px;
}

/* ── Слайдер позиции ── */
QSlider::groove:horizontal {
    background: #444;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #888;
    width: 12px;
    margin: -4px 0;
    border-radius: 6px;
}
QSlider::sub-page:horizontal {
    background: #3a7a3a;
    border-radius: 2px;
}

/* ── Метки (время, скорость) ── */
QLabel {
    color: #ccc;
    font-size: 11px;
    background: transparent;
    border: none;
}
"""
VOLUME_QSS = ""
DROP_AREA_QSS = ""
TOOL_BUTTON_QSS = ""
RECORD_MENU_QSS = ""
