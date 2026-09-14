#ifndef slic3r_GUI_BambuSourceLibrary_hpp_
#define slic3r_GUI_BambuSourceLibrary_hpp_

#include <chrono>

namespace Slic3r::GUI {

// Refreshes the source-library function table for future sessions. Existing
// sessions retain their own stable table until their tunnel is closed.
void refresh_bambu_source_library();

// Stops every active Bambu file-transfer session and waits for its worker.
void stop_bambu_file_systems();
bool wait_for_bambu_file_systems(std::chrono::milliseconds timeout);

// Finalizes application ownership. The proprietary source image and callable
// table intentionally remain process-lifetime because media backends do not
// expose a complete callback/thread barrier.
void release_bambu_source_library();

} // namespace Slic3r::GUI

#endif // slic3r_GUI_BambuSourceLibrary_hpp_
