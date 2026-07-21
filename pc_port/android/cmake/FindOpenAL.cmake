if(TARGET OpenAL::OpenAL)
    set(OPENAL_FOUND TRUE)
    set(OPENAL_LIBRARY OpenAL::OpenAL)
elseif(TARGET OpenAL)
    add_library(OpenAL::OpenAL ALIAS OpenAL)
    set(OPENAL_FOUND TRUE)
    set(OPENAL_LIBRARY OpenAL::OpenAL)
else()
    set(OPENAL_FOUND FALSE)
endif()

set(OPENAL_INCLUDE_DIR "${CMAKE_CURRENT_LIST_DIR}/../vendor/openal-soft/include")

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(OpenAL REQUIRED_VARS OPENAL_FOUND OPENAL_INCLUDE_DIR)

