# gpr_polish — optional decoder-side CNN polish backed by CoreML.
# Apple-only (CoreML + Objective-C++). On non-Apple platforms this
# subdirectory is skipped by the top-level CMakeLists, so we do not
# define any library here in that case.

set(LIB_NAME gpr_polish)

set(SRC_FILES gpr_polish.mm)
set(INC_FILES gpr_polish.h)

add_library(${LIB_NAME} STATIC ${SRC_FILES} ${INC_FILES})

# Objective-C++ with ARC. The .mm extension already selects Objective-C++
# in CMake/Xcode, but we set -fobjc-arc explicitly so command-line ninja
# builds get the same behavior.
set_source_files_properties(gpr_polish.mm PROPERTIES
  COMPILE_FLAGS "-fobjc-arc")

target_include_directories(${LIB_NAME} PUBLIC
  "${CMAKE_CURRENT_SOURCE_DIR}")

find_library(COREML_FRAMEWORK CoreML REQUIRED)
find_library(FOUNDATION_FRAMEWORK Foundation REQUIRED)

target_link_libraries(${LIB_NAME} PUBLIC
  ${COREML_FRAMEWORK}
  ${FOUNDATION_FRAMEWORK})
