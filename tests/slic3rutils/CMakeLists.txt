get_filename_component(_TEST_NAME ${CMAKE_CURRENT_LIST_DIR} NAME)
add_executable(${_TEST_NAME}_tests
    ${_TEST_NAME}_tests_main.cpp
    )

if (MSVC)
    target_link_libraries(${_TEST_NAME}_tests Setupapi.lib)
endif ()

target_link_libraries(${_TEST_NAME}_tests test_common libslic3r_gui libslic3r Catch2::Catch2WithMain)

# wxWidgets' GTK port selection is normally applied in the src directory by
# wxWidgets_USE_FILE. This test target lives in a sibling directory and includes
# public GUI headers directly, so it must carry the same port definitions.
if (CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_compile_definitions(${_TEST_NAME}_tests PRIVATE __WXGTK__)
    if (SLIC3R_GTK STREQUAL "3")
        target_compile_definitions(${_TEST_NAME}_tests PRIVATE __WXGTK3__)
    endif ()
endif ()

set_property(TARGET ${_TEST_NAME}_tests PROPERTY FOLDER "tests")

orcaslicer_copy_test_dlls()

orcaslicer_discover_tests(${_TEST_NAME}_tests)
