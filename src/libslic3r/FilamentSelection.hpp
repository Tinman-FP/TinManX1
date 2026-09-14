#ifndef slic3r_FilamentSelection_hpp_
#define slic3r_FilamentSelection_hpp_

#include <cstddef>
#include <optional>
#include <string>

namespace Slic3r {

class PresetBundle;

struct FilamentSelectionColor {
    std::string primary;
    std::string type;
    std::string multi;
};

struct FilamentSlotSelection {
    size_t index;
    std::string preset_name;
    std::string printer_name;
    std::optional<FilamentSelectionColor> color;
};

// Call only after confirmation, on the thread that owns the bundle. Stages all
// allocations before committing the slot and palette; never exports selections
// or modifies the active filament editor, tool mapping, or hardware settings.
bool apply_filament_slot_selection(PresetBundle &bundle, const FilamentSlotSelection &selection,
                                   std::string &reason);

} // namespace Slic3r

#endif
