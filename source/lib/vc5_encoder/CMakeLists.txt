# library
set( LIB_NAME vc5_encoder )

# get source files
file( GLOB SRC_FILES "*.c" )

# get include files
file( GLOB INC_FILES "*.h" )

# ARM64 hand-written NEON assembly hot loops. The .S file is gated
# internally on __aarch64__ + !FUSED_DISABLE_ASM, so it's safe to
# include unconditionally; non-ARM64 builds get an empty TU.
list( APPEND SRC_FILES "${CMAKE_CURRENT_SOURCE_DIR}/fused_encode_arm64.S" )
# Tell CMake the .S file is C-flavored (preprocessed) so the same
# compiler-driver flags / -march settings apply.
set_source_files_properties(
    "${CMAKE_CURRENT_SOURCE_DIR}/fused_encode_arm64.S"
    PROPERTIES LANGUAGE C
)

# add include files from other folders
include_directories( "../vc5_common" )
include_directories( "../common/private" )
include_directories( "../common/public" )

# library
add_library( ${LIB_NAME} STATIC ${SRC_FILES} ${INC_FILES} )

if(NOT WIN32)
  find_package( Threads REQUIRED )
  target_link_libraries( ${LIB_NAME} Threads::Threads m )
endif()

# set the folder where to place the projects
set_target_properties( ${LIB_NAME} PROPERTIES FOLDER lib )
