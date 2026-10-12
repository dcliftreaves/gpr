# minimum required cmake version
cmake_minimum_required( VERSION 3.5 FATAL_ERROR )

set(CMAKE_SUPPRESS_REGENERATION true)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_C_EXTENSIONS OFF)

# project name
project( gpr )

if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
  set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()

set(NEON_DEFAULT OFF)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)")
  set(NEON_DEFAULT ON)
endif()
option(NEON "Enable ARM NEON intrinsics" ${NEON_DEFAULT})
if(NEON)
  add_definitions(-DNEON=1)
else()
  add_definitions(-DNEON=0)
endif()

if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)" AND CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(FUSED_TUNE_CPU "native" CACHE STRING "ARM CPU tuning; empty disables -mcpu")
  if(FUSED_TUNE_CPU)
    add_compile_options(-mcpu=${FUSED_TUNE_CPU})
  endif()
endif()

option(FUSED_LOG_POLYNOMIAL "Use NEON polynomial log-curve in fused encoder" OFF)
option(FUSED_TIMING "Enable fused encoder stage timing prints" OFF)
option(FUSED_TIMING_DETAIL "Enable detailed fused encoder channel timing prints" OFF)
option(JANS_INLINE_PROFILE_RUNTIME "Enable opt-in entropy profile receipt lines" OFF)
if(FUSED_LOG_POLYNOMIAL AND NOT NEON)
  message(FATAL_ERROR "FUSED_LOG_POLYNOMIAL requires NEON")
endif()
if(FUSED_TIMING_DETAIL)
  set(FUSED_TIMING ON)
endif()
foreach(flag FUSED_LOG_POLYNOMIAL FUSED_TIMING FUSED_TIMING_DETAIL JANS_INLINE_PROFILE_RUNTIME)
  if(${flag})
    add_definitions(-D${flag}=1)
  endif()
endforeach()

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
if(NOT WIN32)
  find_package(Threads REQUIRED)
endif()
add_subdirectory( "source/lib/common" )
add_subdirectory( "source/lib/vc5_common" )

if(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_decoder")
  MESSAGE( STATUS "Found source/lib/vc5_decoder - enabling vc5 decoder and setting GPR_READING=1" )
  add_subdirectory( "source/lib/vc5_decoder" )
  add_subdirectory( "source/app/vc5_decoder_app" )
else(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_decoder")
  MESSAGE( STATUS "Could not find source/lib/vc5_decoder - disabling vc5 decoder and setting GPR_READING=0" )
endif(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_decoder")

if(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_encoder")
  MESSAGE( STATUS "Found source/lib/vc5_encoder - enabling vc5 encoder and setting GPR_WRITING=1" )
  add_subdirectory( "source/lib/vc5_encoder" )
  add_subdirectory( "source/app/vc5_encoder_app" )
else(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_encoder")
  MESSAGE( STATUS "Could not find source/lib/vc5_encoder - disabling vc5 encoder and setting GPR_WRITING=0" )
endif(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_encoder")

add_subdirectory( "source/lib/dng_sdk" )
add_subdirectory( "source/lib/gpr_sdk" )
add_subdirectory( "source/lib/xmp_core" )
add_subdirectory( "source/lib/expat_lib" )
add_subdirectory( "source/lib/md5_lib" )

if(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")
  MESSAGE( STATUS "Found source/lib/tiny_jpeg - enabling jpeg writing and setting GPR_JPEG_AVAILABLE=1" )
  add_subdirectory( "source/lib/tiny_jpeg" )
else(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")
  MESSAGE( STATUS "Could not find source/lib/tiny_jpeg - disabling jpeg writing and setting GPR_JPEG_AVAILABLE=0" )
endif(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")

add_subdirectory( "source/app/common/cJSON" )
add_subdirectory( "source/app/common/argument_parser" )
add_subdirectory( "source/app/gpr_tools" )

add_subdirectory( "source/app/bench_fused" )

function(gpr_native_tool name source_file)
  add_executable(${name} ${source_file} ${ARGN})
  target_include_directories(${name} PRIVATE
    source/lib/vc5_encoder source/lib/vc5_decoder source/lib/vc5_common
    source/lib/common/private source/lib/common/public)
  target_link_libraries(${name} vc5_decoder vc5_encoder vc5_common common)
  set_target_properties(${name} PROPERTIES RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
endfunction()

gpr_native_tool(gvid_preview_rgb_cli source/app/gvid_preview_rgb_cli.c)
gpr_native_tool(fused_decode_cli source/app/fused_decode_cli.c)
if(NOT WIN32)
  gpr_native_tool(labs_encoder_bench_cli source/app/labs_encoder_bench_cli.c)
endif()

add_library(fused_decode_coeff_io_obj OBJECT source/lib/vc5_decoder/fused_decode.c)
target_compile_definitions(fused_decode_coeff_io_obj PRIVATE GPR_DEBUG_COEFF_IO=1)
target_include_directories(fused_decode_coeff_io_obj PRIVATE
  source/lib/vc5_decoder source/lib/vc5_encoder source/lib/vc5_common
  source/lib/common/private source/lib/common/public)
gpr_native_tool(coeff_io_tool source/app/coeff_io_tool.c $<TARGET_OBJECTS:fused_decode_coeff_io_obj>)

include(TestBigEndian)
test_big_endian(IS_BIG_ENDIAN)
if(NOT IS_BIG_ENDIAN)
  target_compile_definitions(dng_sdk PUBLIC qDNGLittleEndian=1)
  target_compile_definitions(gpr_sdk PUBLIC qDNGLittleEndian=1)
endif()

include(tests/Validation.cmake)
