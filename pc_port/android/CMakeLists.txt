cmake_minimum_required(VERSION 3.22.1)
project(SilentHillAndroid C CXX)

if(NOT ANDROID)
    message(FATAL_ERROR "pc_port/android must be configured with the Android NDK toolchain")
endif()

set(SH_ANDROID_VENDOR_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vendor")
set(SH_ANDROID_SDL_DIR "${SH_ANDROID_VENDOR_DIR}/SDL")
set(SH_ANDROID_OPENAL_DIR "${SH_ANDROID_VENDOR_DIR}/openal-soft")
set(SH_ANDROID_JPEG_DIR "${SH_ANDROID_VENDOR_DIR}/libjpeg-turbo")

if(NOT EXISTS "${SH_ANDROID_SDL_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "SDL2 submodule is missing. Run: git submodule update --init --recursive")
endif()
if(NOT EXISTS "${SH_ANDROID_OPENAL_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "OpenAL Soft submodule is missing. Run: git submodule update --init --recursive")
endif()
if(NOT EXISTS "${SH_ANDROID_JPEG_DIR}/CMakeLists.txt")
    message(FATAL_ERROR
        "libjpeg-turbo submodule is missing. Run: git submodule update --init --recursive")
endif()
if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../PsyCross/CMakeLists.txt")
    message(FATAL_ERROR
        "PsyCross submodule is missing. Run: git submodule update --init --recursive")
endif()

# Build only the dependency pieces the game needs. SDLActivity requires the
# shared SDL2 library; OpenAL Soft stays shared to preserve its LGPL relinking
# model and uses Android's native OpenSL ES backend.
set(SDL_SHARED ON CACHE BOOL "" FORCE)
set(SDL_STATIC OFF CACHE BOOL "" FORCE)
set(SDL_TEST OFF CACHE BOOL "" FORCE)
set(SDL_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${SH_ANDROID_SDL_DIR}" "${CMAKE_BINARY_DIR}/sdl2")

set(LIBTYPE SHARED CACHE STRING "" FORCE)
set(ALSOFT_UTILS OFF CACHE BOOL "" FORCE)
set(ALSOFT_EXAMPLES OFF CACHE BOOL "" FORCE)
set(ALSOFT_TESTS OFF CACHE BOOL "" FORCE)
set(ALSOFT_INSTALL OFF CACHE BOOL "" FORCE)
set(ALSOFT_BACKEND_OPENSL ON CACHE BOOL "" FORCE)
set(ALSOFT_BACKEND_OBOE OFF CACHE BOOL "" FORCE)
add_subdirectory("${SH_ANDROID_OPENAL_DIR}" "${CMAKE_BINARY_DIR}/openal-soft")

# libjpeg-turbo intentionally rejects add_subdirectory integration. Build it
# with its supported standalone CMake entry point and expose the resulting
# archive as an imported target to the game build.
include(ExternalProject)
set(SH_ANDROID_JPEG_BUILD_DIR "${CMAKE_BINARY_DIR}/libjpeg-turbo")
file(MAKE_DIRECTORY "${SH_ANDROID_JPEG_BUILD_DIR}")
ExternalProject_Add(sh_android_jpeg_build
    SOURCE_DIR "${SH_ANDROID_JPEG_DIR}"
    BINARY_DIR "${SH_ANDROID_JPEG_BUILD_DIR}"
    CMAKE_ARGS
        "-DCMAKE_TOOLCHAIN_FILE=${CMAKE_TOOLCHAIN_FILE}"
        "-DANDROID_ABI=${ANDROID_ABI}"
        "-DANDROID_PLATFORM=${ANDROID_PLATFORM}"
        "-DANDROID_STL=${ANDROID_STL}"
        "-DCMAKE_BUILD_TYPE=${CMAKE_BUILD_TYPE}"
        "-DENABLE_SHARED=OFF"
        "-DENABLE_STATIC=ON"
        "-DWITH_TURBOJPEG=OFF"
        "-DWITH_TOOLS=OFF"
        "-DWITH_TESTS=OFF"
    BUILD_COMMAND "${CMAKE_COMMAND}" --build <BINARY_DIR> --target jpeg-static
    INSTALL_COMMAND ""
    BUILD_BYPRODUCTS "${SH_ANDROID_JPEG_BUILD_DIR}/libjpeg.a"
)
add_library(sh_android_jpeg_static STATIC IMPORTED GLOBAL)
set_target_properties(sh_android_jpeg_static PROPERTIES
    IMPORTED_LOCATION "${SH_ANDROID_JPEG_BUILD_DIR}/libjpeg.a"
    INTERFACE_INCLUDE_DIRECTORIES
        "${SH_ANDROID_JPEG_DIR}/src;${SH_ANDROID_JPEG_BUILD_DIR}"
)
add_dependencies(sh_android_jpeg_static sh_android_jpeg_build)
set(JPEG_LIBRARY sh_android_jpeg_static CACHE STRING "" FORCE)

# PsyCross uses find_package(SDL2/OpenAL). These small Android find modules
# expose the in-tree targets above without requiring desktop package metadata.
list(PREPEND CMAKE_MODULE_PATH "${CMAKE_CURRENT_SOURCE_DIR}/cmake")

set(SH_FMV_FFMPEG OFF CACHE BOOL "" FORCE)
set(SH_BUILD_MAP_DLLS ON CACHE BOOL "" FORCE)
set(SH_USE_OPENGL ON CACHE BOOL "" FORCE)
set(PSYCROSS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../PsyCross" CACHE PATH "" FORCE)

add_subdirectory("${CMAKE_CURRENT_SOURCE_DIR}/.." "${CMAKE_BINARY_DIR}/silent-hill")

target_compile_options(psycross_static PRIVATE
    -include "${CMAKE_CURRENT_SOURCE_DIR}/include/psycross_android_compat.h"
)
target_link_libraries(SilentHillPC PRIVATE SDL2::SDL2 OpenAL::OpenAL sh_android_jpeg_static)
target_compile_definitions(SilentHillPC PRIVATE SH_ANDROID_PORT=1)
