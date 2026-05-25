# minimum required cmake version
cmake_minimum_required( VERSION 3.5 FATAL_ERROR )

set(CMAKE_SUPPRESS_REGENERATION true)

# Default to Release if no build type was specified — otherwise the libs
# compile at -O0 and decode runs ~6× slower. Discovered when a stale
# `build-local` (reconfigured without -DCMAKE_BUILD_TYPE=Release) made
# decode 63 ms per frame on M3 Max instead of ~10 ms, capping playback at
# ~15 fps instead of ~27 fps. The gpr2prores Makefile links against
# build-local unconditionally, so a misconfigured build-local silently
# degrades the whole playback pipeline. Setting Release here is the
# safety net.
if(NOT CMAKE_BUILD_TYPE AND NOT CMAKE_CONFIGURATION_TYPES)
    set(CMAKE_BUILD_TYPE Release CACHE STRING
        "Build type (Release, Debug, RelWithDebInfo, MinSizeRel)" FORCE)
    message(STATUS "CMAKE_BUILD_TYPE not set; defaulting to Release")
endif()

set(CMAKE_C_FLAGS "-std=c99")

# project name
project( gpr )

# LTO intentionally disabled:
# 1. GCC LTO fails on mixed C/C++ projects (lto-wrapper error on Ubuntu)
# 2. LTO changes floating-point rounding in the inverse wavelet, breaking
#    byte-exact backward compatibility with existing GPR files
# Users who want LTO can enable it with: cmake -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON

# NEON auto-enabled on ARM64
set(NEON_DEFAULT OFF)
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)")
  set(NEON_DEFAULT ON)
endif()
option(NEON "Enable ARM NEON intrinsics" ${NEON_DEFAULT})

if(NEON)
  add_compile_definitions(NEON=1)
else()
  add_compile_definitions(NEON=0)
endif()

message(STATUS "NEON enabled: ${NEON}")

# Cortex-A76 / Pi 5 tuning. Native ARM clang on Apple Silicon already targets
# apple-m1 by default, but Linux ARM64 (Pi 5) needs an explicit -mcpu= for
# the scheduler to pick A76-specific latencies and pipeline assignments.
# Default to -mcpu=native on Linux aarch64; users can override via
# CMAKE_C_FLAGS / CMAKE_CXX_FLAGS or set FUSED_TUNE_CPU=cortex-a76 to pin.
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)" AND
   CMAKE_SYSTEM_NAME STREQUAL "Linux")
  set(FUSED_TUNE_CPU "native" CACHE STRING
      "ARM cpu tuning for the encoder (passed as -mcpu=)")
  if(FUSED_TUNE_CPU)
    add_compile_options(-mcpu=${FUSED_TUNE_CPU})
    message(STATUS "ARM tuning: -mcpu=${FUSED_TUNE_CPU}")
  endif()
endif()

# FUSED_LOG_POLYNOMIAL: replace the fused encoder's LUT-based 14-bit log
# curve with a NEON polynomial approximation. Default OFF.
#
# History: enabled at 58577fe when it saved ~1.7 ms on Pi 5 (A76) on the
# THEN-CURRENT mode-1 unpack path that had a chained 4-deep scalar gather
# (load-use bound on A76 LSU). Subsequent T13b/T14/T15/T16 work
# (8fd3218..bb37c76) refactored the hot path to 16-independent-load
# scratch arrays that pipeline through both LSU ports — the LUT gather
# is no longer the long pole. Re-bench on Pi 5 50 MP × LL-only-fast
# (2026-05-21): polynomial median 128 ms vs LUT 44 ms. The polynomial
# was ~3x SLOWER on this configuration.
#
# Kept as an opt-in because:
#   1. Hardware variants exist where the LUT thrashes L1d (A53/A55
#      small caches, custom SoCs).
#   2. The mode-2 (no col-decimate) `unpack_channel_row` retains its
#      original 4-deep scalar dep chain and may still benefit.
option(FUSED_LOG_POLYNOMIAL "Use NEON polynomial log-curve in fused encoder" OFF)
if(FUSED_LOG_POLYNOMIAL)
  if(NOT NEON)
    message(FATAL_ERROR "FUSED_LOG_POLYNOMIAL requires NEON")
  endif()
  add_compile_definitions(FUSED_LOG_POLYNOMIAL=1)
endif()
message(STATUS "FUSED_LOG_POLYNOMIAL: ${FUSED_LOG_POLYNOMIAL}")

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

# gpr_polish — optional CoreML-backed Bayer polish. Objective-C++; Apple only.
if(APPLE AND EXISTS "${CMAKE_SOURCE_DIR}/source/lib/gpr_polish")
  MESSAGE( STATUS "Found source/lib/gpr_polish - enabling CoreML polish" )
  add_subdirectory( "source/lib/gpr_polish" )
endif()

add_subdirectory( "source/app/common/cJSON" )
add_subdirectory( "source/app/common/argument_parser" )
add_subdirectory( "source/app/gpr_tools" )
add_subdirectory( "source/app/compare_quality" )
add_subdirectory( "source/app/ans_test" )
add_subdirectory( "source/app/bench_fused" )

# Fix byte order detection for Linux ARM64 (from gopro/gpr#53 by mckfarm)
include(TestBigEndian)
test_big_endian(IS_BIG_ENDIAN)
if(NOT IS_BIG_ENDIAN)
  target_compile_definitions( dng_sdk PUBLIC qDNGLittleEndian=1 )
  target_compile_definitions( gpr_sdk PUBLIC qDNGLittleEndian=1 )
endif()
