# library
set( LIB_NAME vc5_encoder )

# get source files
file( GLOB SRC_FILES "*.c" )

# get ARM64 assembly sources (only on ARM64 hosts).
# Clang/GCC treat .S (capital) as preprocessed assembly: the C preprocessor
# runs first so #ifdef __aarch64__ inside the file is honored.
if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(arm64|aarch64)")
  enable_language(ASM)
  file( GLOB ASM_FILES "*.S" )
  list(APPEND SRC_FILES ${ASM_FILES})
endif()

# get include files
file( GLOB INC_FILES "*.h" )

# add include files from other folders
include_directories( "../vc5_common" )
include_directories( "../common/private" )
include_directories( "../common/public" )

# library
add_library( ${LIB_NAME} STATIC ${SRC_FILES} ${INC_FILES} )

# Public include directories for downstream consumers via install/export.
# Existing in-tree users still rely on the include_directories() above
# (kept for backwards-compatible build behavior); these are appended for
# the install/export interface so find_package(gpr) consumers get the
# right -I when they #include <gpr/gpr_video.h>.
target_include_directories( ${LIB_NAME}
  PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}>
    $<INSTALL_INTERFACE:include/gpr>
)

if(NOT WIN32)
  find_package( Threads REQUIRED )
  target_link_libraries( ${LIB_NAME} Threads::Threads m )
endif()

# set the folder where to place the projects
set_target_properties( ${LIB_NAME} PROPERTIES FOLDER lib )
