# cpp/CMakeLists.txt
cmake_minimum_required(VERSION 3.10)
project(Pik2VideoRecorder)

set(CMAKE_CXX_STANDARD 17)

# Находим pkg-config и FFmpeg
find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED libavcodec libavformat libavutil libswscale libavdevice libavfilter)

# Отладочный вывод (увидите при cmake ..)
message(STATUS "FFMPEG_INCLUDE_DIRS: ${FFMPEG_INCLUDE_DIRS}")
message(STATUS "FFMPEG_LIBRARY_DIRS: ${FFMPEG_LIBRARY_DIRS}")
message(STATUS "FFMPEG_LIBRARIES: ${FFMPEG_LIBRARIES}")

# Создаём динамическую библиотеку
add_library(pik2video_recorder SHARED recorder.cpp)

# Подключаем заголовочные файлы
target_include_directories(pik2video_recorder PRIVATE ${FFMPEG_INCLUDE_DIRS})

# Явно добавляем пути к библиотекам и сами библиотеки
target_link_directories(pik2video_recorder PRIVATE ${FFMPEG_LIBRARY_DIRS})
target_link_libraries(pik2video_recorder ${FFMPEG_LIBRARIES})

# Устанавливаем суффикс .dylib
set_target_properties(pik2video_recorder PROPERTIES SUFFIX ".dylib")
set(CMAKE_BUILD_TYPE Debug)