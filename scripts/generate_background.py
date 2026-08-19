from PIL import Image, ImageDraw
import os

def create_background(width, height, output_path):
    """Создаёт фоновое изображение с двумя прямоугольниками."""
    bg_color = (28, 28, 33)        # тёмный фон
    rect_color = (40, 40, 45)      # цвет прямоугольников
    
    img = Image.new('RGB', (width, height), bg_color)
    draw = ImageDraw.Draw(img)
    
    # Тонкая рамка по краям
    #draw.rectangle([0, 0, width - 1, height - 1], outline=(60, 60, 65), width=1)
    
    rect_w = int(width * 0.85)     # 80% ширины
    rect_h = int(height * 0.45)    # 45% высоты
    
    # ═══════════════════════════════════════
    # ПРЯМОУГОЛЬНИК 1: левый верхний угол
    # ═══════════════════════════════════════
    r1_x = 0
    r1_y = 0
    draw.rounded_rectangle(
        [r1_x, r1_y, r1_x + rect_w, r1_y + rect_h],
        radius=4,
        fill=rect_color
    )
    
    # ═══════════════════════════════════════
    # ПРЯМОУГОЛЬНИК 2: правый нижний угол
    # ═══════════════════════════════════════
    r2_x = width - rect_w
    r2_y = height - rect_h
    draw.rounded_rectangle(
        [r2_x, r2_y, r2_x + rect_w, r2_y + rect_h],
        radius=4,
        fill=rect_color
    )
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, 'PNG')
    print(f"  ✓ Фон создан: {output_path} ({width}x{height})")

if __name__ == "__main__":
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(project_root, "resources", "backgrounds", "main_bg.png")
    create_background(430, 80, output_path)
    print("✅ Готово!")