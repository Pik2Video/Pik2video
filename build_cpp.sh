#!/bin/bash
# build_cpp.sh - пересборка C++ библиотеки из корня проекта

# Определяем абсолютный путь к корню проекта (папка, где находится этот скрипт)
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$PROJECT_ROOT/cpp/build"

echo "🔨 Пересборка C++ библиотеки..."
echo "Корень проекта: $PROJECT_ROOT"

# Проверяем, существует ли папка build
if [ ! -d "$BUILD_DIR" ]; then
    echo "⚠️ Папка build не найдена. Создаём..."
    mkdir -p "$BUILD_DIR"
fi

# Переходим в папку сборки
cd "$BUILD_DIR" || { echo "❌ Не удалось перейти в $BUILD_DIR"; exit 1; }

# Очищаем предыдущую сборку и кэш CMake
echo "🧹 Очистка..."
make clean 2>/dev/null
rm -f CMakeCache.txt
rm -rf CMakeFiles

# Запускаем CMake (если нужно обновить конфигурацию) и сборку
echo "⚙️ Запуск CMake..."
cmake .. || { echo "❌ Ошибка CMake"; exit 1; }

echo "📦 Сборка..."
make || { echo "❌ Ошибка компиляции"; exit 1; }

# Проверяем, создалась ли библиотека
if [ -f "libpik2video_recorder.dylib" ]; then
    echo "✅ Сборка завершена успешно!"
    echo "📁 Библиотека: $BUILD_DIR/libpik2video_recorder.dylib"
else
    echo "❌ Библиотека не создана. Проверьте ошибки сборки."
    exit 1
fi