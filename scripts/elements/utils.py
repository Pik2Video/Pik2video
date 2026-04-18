# elements/utils.py

from PIL import ImageDraw, ImageFont
import os

"""
Вспомогательные утилиты для генерации иконок.

Содержит общие функции, которые используются в других модулях:
- поиск системного шрифта
- измерение размера текста
- (в будущем) другие общие операции

Этот файл не рисует сам, только помогает другим рисовать.
"""


# =================ПОИСК ШРИФТА В СИСТЕМЕ==================

def find_system_font(font_size, bold=False):
    """
    Находит и загружает системный шрифт.

    Проверяет пути для разных операционных систем:
    - macOS: San Francisco, Helvetica
    - Windows: Arial
    - Linux: Liberation Sans

    Если шрифт не найден — возвращает стандартный шрифт Pillow.

    Аргументы:
        font_size (int): размер шрифта в пикселях
        bold (bool): если True, пытается загрузить жирное начертание

    Возвращает:
        ImageFont: объект шрифта для использования в Pillow
    """
    # Список возможных путей к шрифтам на разных ОС
    if bold:
        # Жирные шрифты
        font_paths = [
            # macOS
            "/System/Library/Fonts/SFNS-Bold.ttf",
            "/System/Library/Fonts/Helvetica-Bold.ttf",
            # Windows
            "C:\\Windows\\Fonts\\arialbd.ttf",
            # Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        # Обычные шрифты
        font_paths = [
            # macOS
            "/System/Library/Fonts/SFNS.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            # Windows
            "C:\\Windows\\Fonts\\arial.ttf",
            # Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size)
            except:
                continue  # если шрифт повреждён — пробуем следующий
    
    # Если ничего не нашли — используем встроенный шрифт
    return ImageFont.load_default()


# =================ИЗМЕРЕНИЕ РАЗМЕРА ТЕКСТА==================

def get_text_size(draw, text, font):
    """
    Возвращает ширину и высоту текста в пикселях.

    Работает с разными версиями Pillow:
    - Pillow 8+: использует textbbox()
    - Pillow 7 и старше: использует textsize()
    - Если ничего не работает — грубая оценка

    Аргументы:
        draw (ImageDraw): объект для рисования
        text (str): текст для измерения
        font (ImageFont): шрифт

    Возвращает:
        tuple (width, height): ширина и высота текста в пикселях
    """
    try:
        # Современный метод (Pillow 8.0.0 и выше)
        bbox = draw.textbbox((0, 0), text, font=font)
        return bbox[2] - bbox[0], bbox[3] - bbox[1]
    except (AttributeError, TypeError):
        try:
            # Старый метод (Pillow 7 и ниже)
            return draw.textsize(text, font=font)
        except:
            # Самая грубая оценка (на случай ошибок)
            return len(text) * font.size // 2, font.size