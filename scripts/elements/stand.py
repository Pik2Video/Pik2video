# resources/scripts/elements/stand.py


from PIL import ImageDraw

"""
Рисует подставку под монитор.

draw_stand():
- рисует трапециевидную подставку
- затемняет верхнюю часть для объёма
"""

def draw_stand(draw, size, bg_color, monitor_rect):
    monitor_x, monitor_y, monitor_width, monitor_height = monitor_rect
    stand_height = int(size * 0.10)
    top_width = int(monitor_width * 0.40)
    bottom_width = int(monitor_width * 0.85)

    top_y = monitor_y + monitor_height
    bottom_y = top_y + stand_height
    top_x = monitor_x + (monitor_width - top_width) // 2
    bottom_x = monitor_x + (monitor_width - bottom_width) // 2

    # Трапеция
    trapezoid_points = [
        (top_x, top_y),
        (top_x + top_width, top_y),
        (bottom_x + bottom_width, bottom_y),
        (bottom_x, bottom_y)
    ]
    draw.polygon(trapezoid_points, fill=bg_color, outline=(100, 100, 100), width=max(1, size // 10))

    # Затемнение верхней части
    dark_strip_height = stand_height // 10
    dark_points = [
        (top_x, top_y),
        (top_x + top_width, top_y),
        (top_x + top_width + ((bottom_x + bottom_width) - (top_x + top_width)) * (dark_strip_height / stand_height), top_y + dark_strip_height),
        (top_x + (bottom_x - top_x) * (dark_strip_height / stand_height), top_y + dark_strip_height)
    ]
    draw.polygon(dark_points, fill=(60, 60, 65))