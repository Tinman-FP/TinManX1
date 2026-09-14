#include "PrinterConnectionUpdate.hpp"
#include "PresetBundle.hpp"

namespace Slic3r {

void PendingPhysicalPrinterUpdate::apply(PresetBundle &bundle) const
{
    if (action == Action::None)
        return;
    auto &printers = bundle.physical_printers;
    if (printers.get_selected_printer_name() != printer_name ||
        printers.get_selected_printer_preset_name() != old_preset_name)
        throw std::runtime_error("The selected printer connection changed while the preset was being saved.");
    const Preset *saved = bundle.printers.find_preset(new_preset_name, false, true);
    if (!saved || !saved->is_visible)
        throw std::runtime_error("The saved printer preset is no longer available for the connection.");
    if (action == Action::Switch) {
        printers.unselect_printer();
        return;
    }

    PhysicalPrinter candidate = printers.get_selected_printer();
    bool changed = action == Action::Replace && candidate.delete_preset(old_preset_name);
    changed = candidate.add_preset(saved->name) || changed;
    if (changed)
        printers.save_printer(candidate);
    printers.select_printer(printer_name, saved->name);
}

} // namespace Slic3r
