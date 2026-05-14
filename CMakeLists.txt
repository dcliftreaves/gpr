# minimum required cmake version
cmake_minimum_required( VERSION 3.5 FATAL_ERROR )

set(CMAKE_SUPPRESS_REGENERATION true)

set(CMAKE_C_FLAGS "-std=c99")

# project name + semantic version (used by gprConfig / gpr.pc)
project( gpr VERSION 2.0.0 LANGUAGES C CXX )

include(GNUInstallDirs)
include(CMakePackageConfigHelpers)

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

# FUSED_LOG_POLYNOMIAL: replace the fused encoder's LUT-based log curve
# with a NEON polynomial approximation. Default OFF (LUT path is faster
# on M1 where the LUT fits in L1d). Enable for Cortex-A78 targets where
# the LUT contends for limited L1d and the polynomial wins 1.5-2x.
option(FUSED_LOG_POLYNOMIAL "Use NEON polynomial log-curve in fused encoder (A78 optimization)" OFF)
if(FUSED_LOG_POLYNOMIAL)
  if(NOT NEON)
    message(FATAL_ERROR "FUSED_LOG_POLYNOMIAL requires NEON")
  endif()
  add_compile_definitions(FUSED_LOG_POLYNOMIAL=1)
endif()
message(STATUS "FUSED_LOG_POLYNOMIAL: ${FUSED_LOG_POLYNOMIAL}")

# GPR_POLISH: optional decoder-side CNN polish (CoreML-backed). Apple-only.
# Off by default on non-Apple platforms; on by default on macOS if the
# CoreML framework is present.
set(GPR_POLISH_DEFAULT OFF)
if(APPLE AND EXISTS "${CMAKE_SOURCE_DIR}/source/lib/gpr_polish")
  set(GPR_POLISH_DEFAULT ON)
endif()
option(GPR_POLISH "Build CoreML-backed decoder polish library" ${GPR_POLISH_DEFAULT})
message(STATUS "GPR_POLISH: ${GPR_POLISH}")

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

if(GPR_POLISH)
  MESSAGE( STATUS "Found source/lib/gpr_polish and APPLE - enabling CoreML polish library" )
  add_subdirectory( "source/lib/gpr_polish" )
  add_compile_definitions(GPR_POLISH_ENABLED=1)
endif()

if(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")
  MESSAGE( STATUS "Found source/lib/tiny_jpeg - enabling jpeg writing and setting GPR_JPEG_AVAILABLE=1" )
  add_subdirectory( "source/lib/tiny_jpeg" )
else(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")
  MESSAGE( STATUS "Could not find source/lib/tiny_jpeg - disabling jpeg writing and setting GPR_JPEG_AVAILABLE=0" )
endif(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/tiny_jpeg")

add_subdirectory( "source/app/common/cJSON" )
add_subdirectory( "source/app/common/argument_parser" )
add_subdirectory( "source/app/gpr_tools" )
add_subdirectory( "source/app/compare_quality" )
add_subdirectory( "source/app/ans_test" )

# Fix byte order detection for Linux ARM64 (from gopro/gpr#53 by mckfarm)
include(TestBigEndian)
test_big_endian(IS_BIG_ENDIAN)
if(NOT IS_BIG_ENDIAN)
  target_compile_definitions( dng_sdk PUBLIC qDNGLittleEndian=1 )
  target_compile_definitions( gpr_sdk PUBLIC qDNGLittleEndian=1 )
endif()

# ----------------------------------------------------------------------------
# Install / export / package config
#
# Lets downstream consumers do:
#   find_package(gpr 2.0 REQUIRED)
#   target_link_libraries(myapp PRIVATE gpr::gpr_video)
#
# Or via pkg-config:
#   cc $(pkg-config --cflags --libs gpr) myapp.c
#
# The static libraries themselves remain unchanged (vc5_encoder, vc5_common,
# vc5_decoder, gpr_sdk each remain their own .a — we don't consolidate them).
# Only the *publicly documented* headers are installed under include/gpr/.
# All other headers are internal and stay in the source tree.
# ----------------------------------------------------------------------------

# Public C headers — the small, stable surface a downstream user actually
# needs to write raw-video, fused-encode, or full GPR-SDK code.
#
# The "advertised" public API is in three sets (ENCODER, DECODER, SDK).
# Those headers transitively #include a handful of supporting headers
# from source/lib/common/public/ and source/lib/vc5_common/ — types
# like CODEC_ERROR, gpr_buffer, gpr_rgb_buffer, fpn_model, ENABLED_PARTS.
# Those transitive headers are listed in GPR_PUBLIC_HEADERS_SUPPORT
# below and installed flat into include/gpr/ alongside the rest, so the
# #include "foo.h" lines in the advertised headers resolve correctly
# when consumers do #include <gpr/...>.
#
# Truly internal headers (headers.h, codebooks.h, syntax.h, encoder.h,
# decoder.h, parameters.h, log.h, etc.) are NOT installed.
set(GPR_PUBLIC_HEADERS_ENCODER
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_encoder/gpr_video.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_encoder/gpr_video_format.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_encoder/fused_encode.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_encoder/vc5_encoder.h"
)

set(GPR_PUBLIC_HEADERS_DECODER "")
if(EXISTS "${CMAKE_SOURCE_DIR}/source/lib/vc5_decoder")
  set(GPR_PUBLIC_HEADERS_DECODER
    "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_decoder/vc5_decoder.h"
  )
endif()

set(GPR_PUBLIC_HEADERS_SDK
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/gpr_sdk/public/gpr.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/gpr_sdk/public/gpr_exif_info.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/gpr_sdk/public/gpr_profile_info.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/gpr_sdk/public/gpr_tuning_info.h"
)

# Supporting headers that the advertised public headers transitively
# #include. Required for <gpr/gpr.h>, <gpr/vc5_encoder.h>, and
# <gpr/vc5_decoder.h> to compile in a downstream project.
set(GPR_PUBLIC_HEADERS_SUPPORT
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/common/public/gpr_platform.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/common/public/gpr_allocator.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/common/public/gpr_buffer.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/common/public/gpr_rgb_buffer.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_common/error.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_common/types.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_common/vc5_common.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_common/config.h"
  "${CMAKE_CURRENT_SOURCE_DIR}/source/lib/vc5_common/noise_model.h"
)

# Convenience INTERFACE target for raw-video / fused-encode users.
# Pulls in vc5_encoder + vc5_common + Threads + libm so a downstream
# CMake project only has to write:
#     target_link_libraries(myapp PRIVATE gpr::gpr_video)
add_library( gpr_video INTERFACE )
target_link_libraries( gpr_video INTERFACE vc5_encoder vc5_common )
if(NOT WIN32)
  find_package( Threads REQUIRED )
  target_link_libraries( gpr_video INTERFACE Threads::Threads m )
endif()
add_library( gpr::gpr_video ALIAS gpr_video )

# Build a list of installable static-library targets. We install each
# distinct .a separately (vc5_encoder, vc5_common, vc5_decoder, gpr_sdk)
# — they are publicly distinct artifacts and consolidating them would
# break consumers who only need a subset.
set(GPR_INSTALL_TARGETS vc5_encoder vc5_common gpr_video)
if(TARGET vc5_decoder)
  list(APPEND GPR_INSTALL_TARGETS vc5_decoder)
endif()
if(TARGET gpr_sdk)
  list(APPEND GPR_INSTALL_TARGETS gpr_sdk)
endif()

install(
  TARGETS ${GPR_INSTALL_TARGETS}
  EXPORT  gprTargets
  ARCHIVE        DESTINATION ${CMAKE_INSTALL_LIBDIR}
  LIBRARY        DESTINATION ${CMAKE_INSTALL_LIBDIR}
  RUNTIME        DESTINATION ${CMAKE_INSTALL_BINDIR}
  INCLUDES       DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)

install(
  FILES ${GPR_PUBLIC_HEADERS_ENCODER}
        ${GPR_PUBLIC_HEADERS_DECODER}
        ${GPR_PUBLIC_HEADERS_SDK}
        ${GPR_PUBLIC_HEADERS_SUPPORT}
  DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}/gpr
)

# Export the targets so downstreams get imported gpr::vc5_encoder etc.
install(
  EXPORT      gprTargets
  FILE        gprTargets.cmake
  NAMESPACE   gpr::
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/gpr
)

# Generate and install gprConfig.cmake + gprConfigVersion.cmake so
# downstream find_package(gpr 2.0 REQUIRED) works.
configure_package_config_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/gprConfig.cmake.in"
  "${CMAKE_CURRENT_BINARY_DIR}/gprConfig.cmake"
  INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/gpr
)
write_basic_package_version_file(
  "${CMAKE_CURRENT_BINARY_DIR}/gprConfigVersion.cmake"
  VERSION ${PROJECT_VERSION}
  COMPATIBILITY SameMajorVersion
)
install(
  FILES
    "${CMAKE_CURRENT_BINARY_DIR}/gprConfig.cmake"
    "${CMAKE_CURRENT_BINARY_DIR}/gprConfigVersion.cmake"
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/gpr
)

# pkg-config integration — consumers without CMake still get
#   pkg-config --cflags --libs gpr
configure_file(
  "${CMAKE_CURRENT_SOURCE_DIR}/cmake/gpr.pc.in"
  "${CMAKE_CURRENT_BINARY_DIR}/gpr.pc"
  @ONLY
)
install(
  FILES "${CMAKE_CURRENT_BINARY_DIR}/gpr.pc"
  DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig
)

# Optional example programs. Another agent is responsible for creating
# examples/CMakeLists.txt; if it's not there yet, this is a no-op and
# the install still works.
if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/examples/CMakeLists.txt")
  add_subdirectory(examples)
endif()
