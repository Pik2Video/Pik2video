# src/pik2video/gui/common/blink_style.py

"""
Единый центр стиля мигания.

Здесь хранятся ВСЕ цвета и формулы, связанные с эффектом мигания:
- диапазоны прозрачности для рамки оверлея и текста в чёрном поле
- цвета активного пресета в PresetWindow
- утилиты линейной интерполяции alpha и HEX-цветов

Каждый виджет сам решает, ЧТО рисовать, но КАК — берёт отсюда.
"""

# ─── Прозрачность (alpha, 0…255) ────────────────────────────
# Рамка оверлея
OVERLAY_ALPHA_DIM = 80      # тусклое состояние
OVERLAY_ALPHA_BRIGHT = 230  # яркое состояние

# Текст в чёрном информационном поле
LABEL_ALPHA_DIM = 80
LABEL_ALPHA_BRIGHT = 255

# ─── Цвета активного пресета (HEX) ──────────────────────────
PRESET_BG_DIM = "#2f2a1a"       # тусклый фон
PRESET_BG_BRIGHT = "#5a4a1a"    # яркий фон
PRESET_BORDER_DIM = "#6b5520"   # тусклая рамка
PRESET_BORDER_BRIGHT = "#d4a843"  # яркая рамка


# ─── Утилиты ────────────────────────────────────────────────
def lerp_alpha(phase: float, dim: int, bright: int) -> int:
    """Линейно интерполировать alpha: phase=0 → dim, phase=1 → bright."""
    phase = max(0.0, min(1.0, phase))
    return int(dim + (bright - dim) * phase)


def lerp_color_hex(c1: str, c2: str, t: float) -> str:
    """Смешать два HEX-цвета: t=0 → c1, t=1 → c2. Возвращает '#rrggbb'."""
    from PySide6.QtGui import QColor
    t = max(0.0, min(1.0, t))
    a = QColor(c1)
    b = QColor(c2)
    r = int(a.red()   + (b.red()   - a.red())   * t)
    g = int(a.green() + (b.green() - a.green()) * t)
    bl = int(a.blue() + (b.blue()  - a.blue())  * t)
    return f"#{r:02x}{g:02x}{bl:02x}"
