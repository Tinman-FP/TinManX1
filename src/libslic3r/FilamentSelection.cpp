#include "FilamentSelection.hpp"
#include "PresetBundle.hpp"

namespace Slic3r {

bool apply_filament_slot_selection(PresetBundle &bundle, const FilamentSlotSelection &selection,
                                   std::string &reason)
{
    reason.clear();
    if (selection.printer_name != bundle.printers.get_edited_preset().name) {
        reason = "The printer changed while the filament was being selected.";
        return false;
    }
    if (selection.index >= bundle.filament_presets.size()) {
        reason = "The selected filament slot is no longer available.";
        return false;
    }
    const Preset *preset = bundle.filaments.find_preset(
        Preset::remove_suffix_modified(selection.preset_name), false, true);
    if (!preset || !preset->is_visible) {
        reason = "The selected filament preset is no longer available.";
        return false;
    }

    auto slots = bundle.filament_presets;
    slots[selection.index] = preset->name;
    DynamicPrintConfig project = bundle.project_config;
    if (selection.color) {
        for (const char *key : {"filament_colour", "filament_colour_type", "filament_multi_colour"}) {
            auto *option = project.option<ConfigOptionStrings>(key, true);
            if (!option) {
                reason = "The project's filament color data is invalid.";
                return false;
            }
            if (option->values.size() < slots.size())
                option->values.resize(slots.size());
        }
        project.option<ConfigOptionStrings>("filament_colour")->values[selection.index] = selection.color->primary;
        project.option<ConfigOptionStrings>("filament_colour_type")->values[selection.index] = selection.color->type;
        project.option<ConfigOptionStrings>("filament_multi_colour")->values[selection.index] = selection.color->multi;
    }
    bundle.filament_presets.swap(slots);
    bundle.project_config = std::move(project);
    return true;
}

} // namespace Slic3r
