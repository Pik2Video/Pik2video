# scripts/generate_icon.py

from PIL import Image, ImageDraw
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from elements.monitor import draw_monitor
from elements.stand import draw_stand
from elements.sphere import draw_red_sphere

def create_app_icon(size, output_path):
    """
    Создаёт иконку: монитор + подставка + красный шар.
    """
    
    # Цвет фона (можно поменять на любой)
    bg_color = (45, 45, 48)  # тёмно-серый
    # bg_color = (240, 240, 245)  # светлый вариант (раскомментируйте для теста)
    
    # ✅ ИСПРАВЛЕНО: используем RGB (без прозрачности)
    img = Image.new('RGB', (size, size), bg_color)
    draw = ImageDraw.Draw(img)
    
    draw.rectangle([0, 0, size, size], fill=bg_color) # общий фон имеет квадратную форму
    
    # Рисуем фон снова (поверхность уже непрозрачная, но скругление нужно для эстетики)
    # Можно рисовать скруглённый прямоугольник на непрозрачном фоне
    # Для macOS лучше вообще убрать скругление, но оставим для красоты
    
    # Монитор
    rects = draw_monitor(draw, size, bg_color)
    monitor_rect = rects['monitor']
    screen_rect = rects['screen']
    
    # Подставка
    draw_stand(draw, size, bg_color, monitor_rect)
    
    # ===== ПОЗИЦИОНИРУЕМ ШАР =====
    screen_x, screen_y, screen_width, screen_height = screen_rect
    
    # Размер шара: 22% от экрана
    sphere_percent = 0.34
    sphere_size = int(min(screen_width, screen_height) * sphere_percent)
    
    # Позиция: на чёрном треугольнике (левый нижний угол)
    sphere_x = screen_x + int(screen_width * 0.18)
    sphere_y = screen_y + screen_height - int(screen_height * 0.46)
    
    # Рисуем шар
    draw_red_sphere(draw, (sphere_x, sphere_y, sphere_size, sphere_size))
    
    # Сохраняем без прозрачности
    img.save(output_path, 'PNG')
    print(f"  ✓ {size}x{size}px")

def create_ico_from_pngs(png_paths, ico_path):
    """Создаёт ICO файл."""
    images = []
    for png_path in png_paths:
        if os.path.exists(png_path):
            img = Image.open(png_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')  # ← конвертируем в RGB
            images.append(img)
    
    if images:
        images[0].save(
            ico_path,
            format='ICO',
            sizes=[(img.width, img.height) for img in images],
            append_images=images[1:]
        )
        print(f"  ✓ {ico_path}")

def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icons_dir = os.path.join(project_root, "resources", "icons")
    os.makedirs(icons_dir, exist_ok=True)
    
    print(f"📁 Папка для иконок: {icons_dir}")
    print("\n🎨 Генерация иконок (непрозрачный фон):")
    
    sizes = [512, 256, 128, 64, 48, 32, 16]
    png_files = []
    
    for size in sizes:
        png_path = os.path.join(icons_dir, f"icon_{size}.png")
        create_app_icon(size, png_path)
        png_files.append(png_path)
    
    print("\n📦 Сборка ICO файла:")
    ico_path = os.path.join(icons_dir, "app_icon.ico")
    create_ico_from_pngs(png_files, ico_path)
    
    print("\n✅ Готово!")

if __name__ == "__main__":
    main()