# cpp/CMakeLists.txt
cmake_minimum_required(VERSION 3.10)
project(Pik2VideoRecorder)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(PkgConfig REQUIRED)
pkg_check_modules(FFMPEG REQUIRED libavcodec libavformat libavutil libswscale libavdevice libavfilter)

message(STATUS "FFMPEG_INCLUDE_DIRS: ${FFMPEG_INCLUDE_DIRS}")
message(STATUS "FFMPEG_LIBRARY_DIRS: ${FFMPEG_LIBRARY_DIRS}")
message(STATUS "FFMPEG_LIBRARIES: ${FFMPEG_LIBRARIES}")

add_library(pik2video_recorder SHARED
    recorder.cpp
    src/sync_clock.cpp
    src/video_input.cpp
    src/filter_graph.cpp
    src/video_encoder.cpp
    src/muxer.cpp
)

target_include_directories(pik2video_recorder PRIVATE
    ${FFMPEG_INCLUDE_DIRS}
    ${CMAKE_CURRENT_SOURCE_DIR}
    ${CMAKE_CURRENT_SOURCE_DIR}/include
)

target_compile_definitions(pik2video_recorder PRIVATE
    __STDC_CONSTANT_MACROS
    __STDC_FORMAT_MACROS
    __STDC_LIMIT_MACROS
)

target_link_directories(pik2video_recorder PRIVATE ${FFMPEG_LIBRARY_DIRS})
target_link_libraries(pik2video_recorder ${FFMPEG_LIBRARIES})

set_target_properties(pik2video_recorder PROPERTIES SUFFIX ".dylib")
set(CMAKE_BUILD_TYPE Debug)
