# minimum required cmake version
cmake_minimum_required( VERSION 3.5 FATAL_ERROR )

set(CMAKE_SUPPRESS_REGENERATION true)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)

# project name
project( gpr )
include(GNUInstallDirs)

# Keep historical desktop defaults, while allowing the camera libraries to be
# built without the still SDK, command-line tools, or the other codec half.
option(GPR_BUILD_SDK "Build the DNG/XMP-backed still-image SDK" ON)
option(GPR_BUILD_STILL_APPS "Build gpr_tools (requires the SDK)" ON)
option(GPR_BUILD_LEGACY_CLI "Build the historical VC-5 command-line tools" ON)
option(GPR_BUILD_ENCODER "Build the stock VC-5 encoder" ON)
option(GPR_BUILD_DECODER "Build the stock VC-5 decoder" ON)
option(GPR_ENABLE_VIDEO "Build stock VC-5 capture and GVID interfaces" OFF)
option(GPR_ENABLE_PREVIEW "Build the native preview library without its frontend" OFF)
option(GPR_BUILD_PREVIEW_TOOLS "Build native stock-GVID preview" OFF)
option(GPR_BUILD_STOCK_VIDEO_EXPERIMENT "Build the stock VC-5 RAW-video experiment" OFF)
option(GPR_BUILD_CAPTURE_APP "Build the stock capture replay frontend" OFF)
option(GPR_BUILD_VIDEO_TESTS "Build capture lifecycle tests" OFF)
option(GPR_BUILD_PREVIEW_TESTS "Build stock preview and reader contract tests" OFF)
option(GPR_BUILD_MEDIA_TESTS "Build calibrated editable-RAW workflow tests (numpy/tifffile required)" OFF)
option(GPR_BUILD_CODEC_TESTS "Build stock Bayer input/output compatibility tests" OFF)
set(GPR_PREVIEW_ENABLED OFF)
if(GPR_ENABLE_PREVIEW OR GPR_BUILD_PREVIEW_TOOLS)
  set(GPR_PREVIEW_ENABLED ON)
endif()
if(GPR_BUILD_STILL_APPS AND NOT GPR_BUILD_SDK)
  message(FATAL_ERROR "GPR_BUILD_STILL_APPS requires GPR_BUILD_SDK; disable still apps for a camera build")
endif()
if(GPR_ENABLE_VIDEO AND NOT GPR_BUILD_ENCODER)
  message(FATAL_ERROR "GPR_ENABLE_VIDEO requires GPR_BUILD_ENCODER")
endif()
if(GPR_PREVIEW_ENABLED AND NOT GPR_BUILD_DECODER)
  message(FATAL_ERROR "Native preview requires GPR_BUILD_DECODER")
endif()
if(GPR_BUILD_STOCK_VIDEO_EXPERIMENT AND (NOT UNIX OR NOT GPR_BUILD_ENCODER OR NOT GPR_BUILD_DECODER))
  message(FATAL_ERROR "GPR_BUILD_STOCK_VIDEO_EXPERIMENT requires POSIX, encoder and decoder")
endif()

function(gpr_require_component component feature)
  if(NOT EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/${component}/CMakeLists.txt")
    message(FATAL_ERROR "${feature} requires source/lib/${component}")
  endif()
endfunction()

# AArch64 always provides Advanced SIMD.  Enable the encoder's existing NEON
# paths automatically on camera-class ARM64 targets while retaining an
# explicit switch for cross builds and bit-exact comparisons.
set(NEON_DEFAULT OFF)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64|ARM64)$")
  set(NEON_DEFAULT ON)
endif()
option(NEON "Enable ARM NEON intrinsics" ${NEON_DEFAULT})

if(NEON)
  add_definitions(-DNEON=1)
else()
  add_definitions(-DNEON=0)
endif()

option(GPR_ENABLE_PARALLEL_CHANNELS
       "Encode independent VC-5 channels in parallel on supported hosts" ON)
option(GPR_ENABLE_PARALLEL_UNPACK
       "Split Bayer unpacking across worker threads on supported hosts" ON)

option(GPR_ENABLE_IPO "Enable interprocedural optimization in release builds" ON)
if(GPR_ENABLE_IPO AND NOT CMAKE_BUILD_TYPE STREQUAL "Debug" AND
   NOT CMAKE_VERSION VERSION_LESS 3.9)
  cmake_policy(SET CMP0069 NEW)
  include(CheckIPOSupported)
  check_ipo_supported(RESULT GPR_IPO_SUPPORTED OUTPUT GPR_IPO_ERROR)
  if(GPR_IPO_SUPPORTED)
    set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)
  endif()
endif()

if(EXISTS "${CMAKE_SOURCE_DIR}/.git")
  execute_process(
    COMMAND git rev-parse --abbrev-ref HEAD
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_BRANCH
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )

  execute_process(
    COMMAND git log -1 --format=%h
    WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
    OUTPUT_VARIABLE GIT_COMMIT_HASH
    OUTPUT_STRIP_TRAILING_WHITESPACE
  )
else(EXISTS "${CMAKE_SOURCE_DIR}/.git")
  set(GIT_BRANCH "")
  set(GIT_COMMIT_HASH "")
endif(EXISTS "${CMAKE_SOURCE_DIR}/.git")

message(STATUS "Git current branch: ${GIT_BRANCH}")
message(STATUS "Git commit hash: ${GIT_COMMIT_HASH}")

add_definitions("-DGIT_COMMIT_HASH=\"${GIT_COMMIT_HASH}\"")
add_definitions("-DGIT_BRANCH=\"${GIT_BRANCH}\"")

# add needed subdirectories
add_subdirectory( "source/lib/common" )
add_subdirectory( "source/lib/vc5_common" )

if(GPR_BUILD_DECODER)
  gpr_require_component(vc5_decoder GPR_BUILD_DECODER)
  add_subdirectory( "source/lib/vc5_decoder" )
endif()

if(GPR_BUILD_ENCODER)
  gpr_require_component(vc5_encoder GPR_BUILD_ENCODER)
  add_subdirectory( "source/lib/vc5_encoder" )
endif()

if(GPR_BUILD_SDK OR GPR_BUILD_LEGACY_CLI)
  add_subdirectory( "source/lib/md5_lib" )
endif()
if(GPR_BUILD_SDK)
  foreach(component dng_sdk gpr_sdk xmp_core expat_lib tiny_jpeg)
    gpr_require_component(${component} GPR_BUILD_SDK)
  endforeach()
  add_subdirectory( "source/lib/dng_sdk" )
  add_subdirectory( "source/lib/gpr_sdk" )
  add_subdirectory( "source/lib/xmp_core" )
  add_subdirectory( "source/lib/expat_lib" )
  add_subdirectory( "source/lib/tiny_jpeg" )
endif()

if(GPR_BUILD_STILL_APPS OR GPR_BUILD_LEGACY_CLI)
  add_subdirectory( "source/app/common/argument_parser" )
endif()
if(GPR_BUILD_STILL_APPS)
  add_subdirectory( "source/app/common/cJSON" )
  add_subdirectory( "source/app/gpr_tools" )
endif()
if(GPR_BUILD_LEGACY_CLI)
  if(TARGET vc5_encoder)
    add_subdirectory( "source/app/vc5_encoder_app" )
  endif()
  if(TARGET vc5_decoder)
    add_subdirectory( "source/app/vc5_decoder_app" )
  endif()
endif()

if(GPR_ENABLE_VIDEO OR GPR_PREVIEW_ENABLED)
  add_subdirectory(source/lib/gpr_video)
endif()
if(GPR_BUILD_PREVIEW_TOOLS)
  if(NOT UNIX)
    message(FATAL_ERROR "GPR_BUILD_PREVIEW_TOOLS currently requires POSIX")
  endif()
  add_executable(gpr_preview_app source/app/gpr_preview_main.cpp)
  target_compile_features(gpr_preview_app PRIVATE cxx_std_11)
  target_link_libraries(gpr_preview_app gpr_preview)
endif()
if(GPR_BUILD_PREVIEW_TESTS)
  if(NOT GPR_PREVIEW_ENABLED)
    message(FATAL_ERROR "GPR_BUILD_PREVIEW_TESTS requires GPR_ENABLE_PREVIEW or GPR_BUILD_PREVIEW_TOOLS")
  endif()
  enable_testing()
  add_executable(preview_contract_test tests/preview_contract.cpp)
  target_compile_features(preview_contract_test PRIVATE cxx_std_11)
  target_link_libraries(preview_contract_test gpr_preview)
  add_test(NAME preview_contract COMMAND preview_contract_test ${CMAKE_SOURCE_DIR}/tests/fixtures/stock_preview)
  set_tests_properties(preview_contract PROPERTIES TIMEOUT 60)
  if(TARGET gpr_preview_app)
    find_package(PythonInterp 3 REQUIRED)
    add_test(NAME preview_cli COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/preview_cli.py $<TARGET_FILE:gpr_preview_app>)
    set_tests_properties(preview_cli PROPERTIES TIMEOUT 180)
  endif()
endif()
if(GPR_BUILD_CAPTURE_APP)
  if(NOT GPR_ENABLE_VIDEO OR NOT UNIX)
    message(FATAL_ERROR "GPR_BUILD_CAPTURE_APP requires GPR_ENABLE_VIDEO and POSIX")
  endif()
  add_executable(gpr_capture_app source/app/gpr_capture_main.cpp)
  target_compile_features(gpr_capture_app PRIVATE cxx_std_11)
  target_link_libraries(gpr_capture_app gpr_video)
endif()
if(GPR_BUILD_VIDEO_TESTS)
  if(NOT GPR_ENABLE_VIDEO)
    message(FATAL_ERROR "GPR_BUILD_VIDEO_TESTS requires GPR_ENABLE_VIDEO")
  endif()
  enable_testing()
  add_executable(capture_lifecycle_test tests/capture_lifecycle.cpp)
  target_compile_features(capture_lifecycle_test PRIVATE cxx_std_11)
  target_include_directories(capture_lifecycle_test PRIVATE source/lib/vc5_encoder
    source/lib/vc5_common source/lib/common/public)
  target_link_libraries(capture_lifecycle_test gpr_video)
  add_test(NAME capture_lifecycle COMMAND capture_lifecycle_test)
  set_tests_properties(capture_lifecycle PROPERTIES TIMEOUT 30)
  add_executable(capture_c_api_test tests/capture_c_api.c)
  target_link_libraries(capture_c_api_test gpr_video)
  add_test(NAME capture_c_api COMMAND capture_c_api_test)
  find_program(GPR_VIDEO_PYTHON NAMES python3 python)
  if(GPR_VIDEO_PYTHON)
    add_test(NAME gvid3_conformance COMMAND ${GPR_VIDEO_PYTHON}
      ${CMAKE_SOURCE_DIR}/tests/gvid3_test.py --native-writer $<TARGET_FILE:capture_lifecycle_test>)
    add_test(NAME gvid2_compatibility COMMAND ${GPR_VIDEO_PYTHON}
      ${CMAKE_SOURCE_DIR}/tests/stock_video_test.py)
    set_tests_properties(gvid3_conformance gvid2_compatibility PROPERTIES TIMEOUT 30)
  endif()
endif()
if(GPR_BUILD_STOCK_VIDEO_EXPERIMENT AND UNIX AND TARGET vc5_encoder AND TARGET vc5_decoder)
  add_subdirectory(source/app/stock_video)
endif()
if(GPR_BUILD_MEDIA_TESTS)
  if(NOT TARGET stock_video OR NOT TARGET gpr_capture_app OR NOT TARGET gpr_tools)
    message(FATAL_ERROR "GPR_BUILD_MEDIA_TESTS requires stock experiment, capture app and SDK tools")
  endif()
  enable_testing()
  find_package(PythonInterp 3 REQUIRED)
  add_executable(sdk_bayer_probe tests/sdk_bayer_probe.cpp)
  target_compile_features(sdk_bayer_probe PRIVATE cxx_std_11)
  target_link_libraries(sdk_bayer_probe gpr_sdk vc5_encoder)
  add_test(NAME raw_media COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/raw_media_test.py
    --sdk $<TARGET_FILE:gpr_tools> --decoder $<TARGET_FILE:stock_video> --capture $<TARGET_FILE:gpr_capture_app>
    --sdk-probe $<TARGET_FILE:sdk_bayer_probe>)
  # Many isolated SDK subprocesses exercise all formats; Pi leak-sanitizer
  # startup is much slower than native desktop startup.
  set_tests_properties(raw_media PROPERTIES TIMEOUT 1200)
  add_test(NAME stock_still COMMAND ${PYTHON_EXECUTABLE} ${CMAKE_SOURCE_DIR}/tests/stock_still_test.py
    --sdk $<TARGET_FILE:gpr_tools>)
  set_tests_properties(stock_still PROPERTIES TIMEOUT 600)
endif()

include(cmake/GPRInstall.cmake)

if(GPR_BUILD_CODEC_TESTS)
  if(NOT TARGET vc5_encoder OR NOT TARGET vc5_decoder)
    message(FATAL_ERROR "GPR_BUILD_CODEC_TESTS requires both codecs")
  endif()
  enable_testing()
  add_executable(bayer_formats_test tests/bayer_formats.cpp)
  target_compile_features(bayer_formats_test PRIVATE cxx_std_11)
  target_link_libraries(bayer_formats_test vc5_encoder vc5_decoder)
  add_test(NAME bayer_formats COMMAND bayer_formats_test ${CMAKE_SOURCE_DIR}/tests/fixtures/stock_preview)
  add_test(NAME bayer_formats_fast COMMAND bayer_formats_test ${CMAKE_SOURCE_DIR}/tests/fixtures/stock_preview)
  set_tests_properties(bayer_formats bayer_formats_fast PROPERTIES TIMEOUT 120)
  set_tests_properties(bayer_formats_fast PROPERTIES ENVIRONMENT
    "GPR_STREAM_UNPACK=1;GPR_BAND_STREAM=1;GPR_COMPACT_BANDS=1;GPR_DIRECT_BANDS=1")
endif()
