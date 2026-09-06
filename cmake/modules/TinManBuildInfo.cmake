include_guard(GLOBAL)

set(_TINMAN_BUILD_INFO_TEMPLATE "${CMAKE_CURRENT_LIST_DIR}/../../src/libslic3r/TinManBuildInfo.hpp.in")

function(tinman_configure_build_info source_dir output_file)
    find_package(Git QUIET)
    set(GIT_COMMIT_HASH "0000000")
    set(_explicit_hash "$ENV{git_commit_hash}")

    if(NOT _explicit_hash STREQUAL "")
        string(LENGTH "${_explicit_hash}" _hash_length)
        if(NOT _explicit_hash MATCHES "^[0-9a-fA-F]+$" OR _hash_length LESS 7 OR _hash_length GREATER 64)
            message(FATAL_ERROR "git_commit_hash must be a hexadecimal commit ID of 7 to 64 characters")
        endif()
        if(GIT_FOUND AND EXISTS "${source_dir}/.git")
            execute_process(
                COMMAND "${GIT_EXECUTABLE}" rev-parse --short --verify "${_explicit_hash}^{commit}"
                WORKING_DIRECTORY "${source_dir}"
                RESULT_VARIABLE _result OUTPUT_VARIABLE GIT_COMMIT_HASH
                OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
            if(NOT _result EQUAL 0)
                execute_process(
                    COMMAND "${GIT_EXECUTABLE}" rev-parse --is-shallow-repository
                    WORKING_DIRECTORY "${source_dir}"
                    OUTPUT_VARIABLE _shallow OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
                if(_shallow STREQUAL "true" AND (_hash_length EQUAL 40 OR _hash_length EQUAL 64))
                    # PR CI may check out only the merge object, not its supplied head ID.
                    # Preserve that explicit full identity without guessing an abbreviation.
                    string(SUBSTRING "${_explicit_hash}" 0 7 GIT_COMMIT_HASH)
                    string(TOLOWER "${GIT_COMMIT_HASH}" GIT_COMMIT_HASH)
                    message(STATUS "Using full commit ID declared by the build environment; object is absent from shallow checkout")
                else()
                    message(FATAL_ERROR "git_commit_hash does not identify a commit in the source checkout")
                endif()
            endif()
        else()
            # Release archives and Flatpak builds may have no Git metadata.
            string(SUBSTRING "${_explicit_hash}" 0 7 GIT_COMMIT_HASH)
            string(TOLOWER "${GIT_COMMIT_HASH}" GIT_COMMIT_HASH)
        endif()
    elseif(GIT_FOUND AND EXISTS "${source_dir}/.git")
        execute_process(
            COMMAND "${GIT_EXECUTABLE}" rev-parse --short --verify HEAD
            WORKING_DIRECTORY "${source_dir}"
            RESULT_VARIABLE _result OUTPUT_VARIABLE _head
            OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        if(_result EQUAL 0 AND _head MATCHES "^[0-9a-fA-F]+$")
            set(GIT_COMMIT_HASH "${_head}")
        endif()

        execute_process(
            COMMAND "${GIT_EXECUTABLE}" symbolic-ref --quiet HEAD
            WORKING_DIRECTORY "${source_dir}"
            OUTPUT_VARIABLE _branch OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
        set(_git_inputs HEAD packed-refs)
        if(NOT _branch STREQUAL "")
            list(APPEND _git_inputs "${_branch}")
        endif()
        foreach(_input IN LISTS _git_inputs)
            # Git resolves worktree-private HEAD and shared refs to their actual locations.
            execute_process(
                COMMAND "${GIT_EXECUTABLE}" rev-parse --git-path "${_input}"
                WORKING_DIRECTORY "${source_dir}"
                RESULT_VARIABLE _path_result OUTPUT_VARIABLE _path
                OUTPUT_STRIP_TRAILING_WHITESPACE ERROR_QUIET)
            if(_path_result EQUAL 0 AND NOT _path STREQUAL "")
                get_filename_component(_path "${_path}" ABSOLUTE BASE_DIR "${source_dir}")
                # A packed branch may have no loose ref yet. Watch its nearest existing
                # directory so the next commit creating that ref also reconfigures.
                while(NOT EXISTS "${_path}")
                    get_filename_component(_path "${_path}" DIRECTORY)
                endwhile()
                set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${_path}")
            endif()
        endforeach()
    endif()

    # configure_file preserves the timestamp when the metadata has not changed.
    configure_file("${_TINMAN_BUILD_INFO_TEMPLATE}" "${output_file}" @ONLY)
    message(STATUS "TinManX1 build: ${TINMANX1_REVISION} (${GIT_COMMIT_HASH})")
endfunction()
