# resources/scripts/elements/sphere.py

from PIL import ImageDraw

def draw_red_sphere(draw, rect, sphere_color=(220, 50, 70)):
    """
    Рисует красный шар с одним бликом.
    
    Аргументы:
        draw: ImageDraw объект
        rect: (x, y, width, height) - область для шара
        sphere_color: цвет шара (R,G,B)
    
    Возвращает:
        dict: координаты и размеры шара (x, y, size)
    """
    x, y, w, h = rect
    
    if w < 2 or h < 2:
        return None
    
    # Размер шара (квадрат)
    sphere_size = min(w, h)
    
    # Центрируем шар в прямоугольнике
    sphere_x = x + (w - sphere_size) // 2
    sphere_y = y + (h - sphere_size) // 2
    
    # Рисуем красный шар
    draw.ellipse(
        [sphere_x, sphere_y, sphere_x + sphere_size, sphere_y + sphere_size],
        fill=sphere_color
    )
    
    # Рисуем один блик (только если размер позволяет)
    if sphere_size >= 4:
        lens_size = max(sphere_size // 3, 1)
        lens_x = sphere_x + sphere_size * 0.65
        lens_y = sphere_y + sphere_size * 0.25
        draw.ellipse(
            [lens_x, lens_y, lens_x + lens_size, lens_y + lens_size],
            fill=(255, 255, 255, 180)
        )
    
    return {
        'x': sphere_x,
        'y': sphere_y,
        'size': sphere_size
    }