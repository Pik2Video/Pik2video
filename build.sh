#!/bin/bash
# build.sh - скрипт для сборки приложения Pik2Video

echo "!!! 🔨 🔩 ⚙️ ⛓️ Запущен процесс сборки приложения Pik2Video... ⛓️ ⚙️ 🔩 🔨 !!!"

# 1. Генерация иконок PNG
echo "🎨 Генерирую PNG иконки..."
python scripts/generate_icon.py

# 2. Конвертация PNG → ICNS
echo "🖼️  Конвертирую PNG в ICNS..."
png2icns resources/icons/app_icon.icns resources/icons/icon_512.png

# 3. Очистка старых сборок
echo "📁 Очищаю старые сборки..."
rm -rf build dist

# 4. Сборка приложения
echo "📦 Собирка приложения... ожидайте. процесс может занять какое то время ⏳⏳⏳"
rye run pyinstaller \
    --onedir \
    --windowed \
    --name="Pik2Video" \
    --icon="resources/icons/app_icon.icns" \
    --add-data "resources/icons:resources/icons" \
    --add-data "src/pik2video/locale:pik2video/locale" \
    --hidden-import PySide6.QtCore \
    --hidden-import PySide6.QtGui \
    --hidden-import PySide6.QtWidgets \
    src/main.py

# 5. Копирование файлов переводов (дублирующий шаг для надежности)
echo "📁 Копирую файлы переводов в приложение..."
if [ -d "dist/Pik2Video.app" ]; then
    # Создаем папку locale внутри .app
    mkdir -p "dist/Pik2Video.app/Contents/Resources/locale"
    
    # Копируем все файлы из locale
    cp -r src/pik2video/locale/* "dist/Pik2Video.app/Contents/Resources/locale/"
    
    # Также копируем в папку MacOS (на всякий случай)
    mkdir -p "dist/Pik2Video.app/Contents/MacOS/pik2video/locale"
    cp -r src/pik2video/locale/* "dist/Pik2Video.app/Contents/MacOS/pik2video/locale/"
    
    echo "✅ Файлы переводов скопированы"
fi

# 6. Проверка результата
if [ -d "dist/Pik2Video.app" ]; then
    echo "✅ Сборка завершена успешно!"
    echo "📱 Приложение: dist/Pik2Video.app"
    open dist/
else
    echo "❌ Ошибка сборки! ⛓️‍💥 ⛓️‍💥 ⛓️‍💥"
    exit 1
fi