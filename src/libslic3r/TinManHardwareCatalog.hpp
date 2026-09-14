#ifndef slic3r_TinManHardwareCatalog_hpp_
#define slic3r_TinManHardwareCatalog_hpp_

#include <cstddef>
#include <string>
#include <string_view>
#include <vector>

namespace Slic3r {

enum class TinManConnectionMode {
    Inherited,
    Bambu,
    Creality,
    QidiMoonraker,
    Snapmaker,
    Moonraker,
};

struct TinManMachineDefinition {
    std::string id;
    std::string vendor;
    std::string model;
    std::vector<std::string> aliases;
    std::vector<std::string> managed_profile_names;
    size_t tool_count {1};
    bool high_flow_nozzles {false};
    std::string printer_agent;
    TinManConnectionMode connection_mode {TinManConnectionMode::Inherited};
};

class TinManHardwareCatalog {
public:
    int schema_version {0};
    std::string catalog_version;
    std::vector<std::string> nozzle_variants;
    std::vector<TinManMachineDefinition> machines;

    const TinManMachineDefinition *find_model(std::string_view model) const;
    const TinManMachineDefinition *match(std::string_view preset_name,
                                         std::string_view machine_hint = {}) const;
    bool valid(std::string *error = nullptr) const;
};

// Invalid data throws std::invalid_argument. Never returns a partial catalog.
TinManHardwareCatalog tinmanx_parse_hardware_catalog(std::string_view json);

// Immutable data embedded from the profile generators' JSON; independent of
// resource-directory initialization and writable user files.
const TinManHardwareCatalog &tinmanx_hardware_catalog();

} // namespace Slic3r

#endif // slic3r_TinManHardwareCatalog_hpp_
