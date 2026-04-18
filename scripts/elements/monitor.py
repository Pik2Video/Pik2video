from PIL import ImageDraw

"""
Рисует монитор с экраном.

Функция draw_monitor():
- рисует корпус монитора
- рисует экран с диагональным делением
- возвращает координаты корпуса и экрана
"""

def draw_monitor(draw, size, bg_color):
    """
    Рисует монитор и возвращает координаты корпуса и экрана
    """
    monitor_width = int(size * 0.85)
    monitor_height = int(size * 0.75)
    monitor_x = (size - monitor_width) // 2
    monitor_y = int(size * 0.06)
    corner_radius = monitor_width // 10

    # Корпус монитора
    draw.rounded_rectangle(
        [monitor_x, monitor_y, monitor_x + monitor_width, monitor_y + monitor_height],
        radius=corner_radius,
        fill=bg_color,
        outline=(100, 100, 100),
        width=max(1, size // 30)
    )

    # Экран внутри корпуса
    screen_margin = monitor_width // 18
    screen_x = monitor_x + screen_margin
    screen_y = monitor_y + screen_margin
    screen_width = monitor_width - 2 * screen_margin
    screen_height = monitor_height - 2 * screen_margin

    # Диагональное деление экрана
    black_color = (20, 20, 25)
    silver_color = (140, 145, 155)
    draw.rectangle([screen_x, screen_y, screen_x + screen_width, screen_y + screen_height], fill=silver_color)
    draw.polygon([
        (screen_x, screen_y + screen_height),
        (screen_x, screen_y),
        (screen_x + screen_width, screen_y + screen_height)
    ], fill=black_color)

    return {
        'monitor': (monitor_x, monitor_y, monitor_width, monitor_height),
        'screen': (screen_x, screen_y, screen_width, screen_height)
    }