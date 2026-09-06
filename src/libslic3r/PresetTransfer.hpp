#pragma once

#include <functional>
#include <string>
#include <vector>

namespace Slic3r {
class PresetCollection;

// The selection callback owns confirmation and selection. A cancelled transfer
// returns false with no reason; other rejected requests provide an explanation.
bool transfer_preset_options(PresetCollection &presets, const std::string &source_name,
                             const std::string &destination_name, std::vector<std::string> options,
                             const std::function<bool(const std::string &)> &select,
                             std::string &reason);
}
