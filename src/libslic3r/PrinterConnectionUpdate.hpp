#ifndef slic3r_PrinterConnectionUpdate_hpp_
#define slic3r_PrinterConnectionUpdate_hpp_

#include <string>

namespace Slic3r {
class PresetBundle;

struct PendingPhysicalPrinterUpdate {
    enum class Action { None, Switch, Replace, Add };
    Action action = Action::None;
    std::string printer_name;
    std::string old_preset_name;
    std::string new_preset_name;

    // Apply only after the requested printer preset has been saved successfully.
    void apply(PresetBundle &bundle) const;
};
} // namespace Slic3r

#endif
