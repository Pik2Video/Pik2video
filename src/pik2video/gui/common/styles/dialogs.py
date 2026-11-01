# src/pik2video/gui/common/styles/dialogs.py
"""
QSS для диалоговых окон.

Применяется:
- DIALOG_QSS — BaseFormDialog и наследники (SettingsDialog,
  RecordSettingsDialog, ScreenSettingsDialog, AudioSettingsDialog)
- FFMPEG_DIALOG_QSS — FFmpegMissingDialog, ProgressDialog (шаг 4)

Контракт: константы — только строки QSS. Никакой логики.
"""

DIALOG_QSS = """
/* ── Кнопки диалогов ── */
QPushButton {
    background-color: #3a3a3a;
    border: 1px solid #555;
    border-radius: 4px;
    color: #e0e0e0;
    padding: 4px 12px;
    font-size: 12px;
}
QPushButton:hover {
    background-color: #4a4a4a;
}
QPushButton:pressed {
    background-color: #2a2a2a;
}

/* ── Поля ввода ── */
QLineEdit, QSpinBox, QComboBox {
    background-color: #1e1e1e;
    border: 1px solid #555;
    border-radius: 0px;
    padding: 3px 6px;
    color: #e0e0e0;
    font-size: 12px;
    selection-background-color: #555;
}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {
    border-color: #888;
}

/* Внутренний QLineEdit у QSpinBox — прозрачный (иначе двойная рамка) */
QSpinBox QLineEdit {
    background: transparent;
    border: none;
    padding: 0;
    color: #e0e0e0;
}

/* ── Общая рамка контента диалога ── */
QWidget#contentWidget {
    background-color: #2f2f2f;
    border: 1px solid #444;
    border-radius: 6px;
}
"""
