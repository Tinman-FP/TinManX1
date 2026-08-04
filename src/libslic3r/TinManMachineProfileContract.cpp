#include "TinManMachineProfileContract.hpp"

#include "AppConfig.hpp"

#include <algorithm>
#include <array>
#include <cctype>
#include <string_view>

namespace Slic3r {

namespace {

struct MachineAlias {
    std::string_view alias;
    std::string_view model;
};

struct MachineFamily {
    std::string_view vendor;
    std::string_view model;
};

constexpr std::array<MachineFamily, 13> machine_families {{
    {"BBL", "Bambu Lab H2D"},
    {"BBL", "Bambu Lab X1 Carbon"},
    {"Creality", "Creality K2 Plus"},
    {"Elegoo", "Elegoo Centauri Carbon"},
    {"Prusa", "Prusa CORE One L"},
    {"Qidi", "Qidi X-Plus 4"},
    {"Qidi", "QidiMaxEz"},
    {"Ratrig", "RatRig V-Core 4 IDEX 500"},
    {"Ratrig", "RatRig V-Core 4 IDEX 500 COPY MODE"},
    {"Ratrig", "RatRig V-Core 4 IDEX 500 MIRROR MODE"},
    {"Snapmaker", "Snapmaker U1"},
    {"Sovol", "Sovol SV08 MAX"},
    {"TinManX1", "FibreSeek Seeker 3"},
}};

constexpr std::array<MachineAlias, 29> machine_aliases {{
    {"RatRig V-Core 4 IDEX 500 MIRROR MODE", "RatRig V-Core 4 IDEX 500 MIRROR MODE"},
    {"RatRig V-Core 4 IDEX 500 COPY MODE", "RatRig V-Core 4 IDEX 500 COPY MODE"},
    {"RatRig V-Core 4 IDEX 500", "RatRig V-Core 4 IDEX 500"},
    {"Bambu Lab X1 Carbon Tinman", "Bambu Lab X1 Carbon"},
    {"Bambu Lab X1 Carbon", "Bambu Lab X1 Carbon"},
    {"Bambu Lab H2D", "Bambu Lab H2D"},
    {"Creality K2 Plus", "Creality K2 Plus"},
    {"Elegoo Centauri Carbon 2", "Elegoo Centauri Carbon"},
    {"Elegoo Centauri Carbon", "Elegoo Centauri Carbon"},
    {"Centauri COSMOS Tinman", "Elegoo Centauri Carbon"},
    {"Prusa CORE One L HF", "Prusa CORE One L"},
    {"Prusa CORE One L", "Prusa CORE One L"},
    {"Qidi X-Plus 4", "Qidi X-Plus 4"},
    {"QIDI Plus 4", "Qidi X-Plus 4"},
    {"Qidi Plus 4", "Qidi X-Plus 4"},
    {"CURRENT QIDI", "Qidi X-Plus 4"},
    {"QidiMaxEz", "QidiMaxEz"},
    {"Qidi Max EZ", "QidiMaxEz"},
    {"Max EZ", "QidiMaxEz"},
    {"Snapmaker U1", "Snapmaker U1"},
    {"CURRENT Snapmaker U1", "Snapmaker U1"},
    {"CURRENT U1", "Snapmaker U1"},
    {"fdm_U1", "Snapmaker U1"},
    {"Sovol SV08 MAX", "Sovol SV08 MAX"},
    {"FibreSeek Seeker 3 - Codex", "FibreSeek Seeker 3"},
    {"FibreSeek Seeker 3", "FibreSeek Seeker 3"},
    {"SEEKER 3", "FibreSeek Seeker 3"},
    {"Elegoo Centauri Carbon2", "Elegoo Centauri Carbon"},
    {"Fibreseek3", "FibreSeek Seeker 3"},
}};

std::string lower_ascii(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char ch) {
        return static_cast<char>(std::tolower(ch));
    });
    return value;
}

std::string bare_preset_name(const std::string &name)
{
    const size_t slash = name.find_last_of('/');
    return slash == std::string::npos ? name : name.substr(slash + 1);
}

std::string_view matched_model(const std::string &preset_name, const std::string &machine_hint)
{
    const std::string name_lower = lower_ascii(preset_name);
    const std::string hint_lower = lower_ascii(machine_hint);
    std::string_view best_model;
    size_t best_length = 0;

    for (const MachineAlias &entry : machine_aliases) {
        const std::string alias_lower = lower_ascii(std::string(entry.alias));
        if ((name_lower.find(alias_lower) != std::string::npos ||
             hint_lower.find(alias_lower) != std::string::npos) &&
            entry.alias.size() > best_length) {
            best_model = entry.model;
            best_length = entry.alias.size();
        }
    }
    return best_model;
}

} // namespace

bool tinmanx_machine_preset_allowed(const std::string &preset_name, const std::string &machine_hint)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return true;

    const std::string bare_name = bare_preset_name(preset_name);
    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    return std::any_of(nozzles.begin(), nozzles.end(), [&](std::string_view nozzle) {
        return bare_name == std::string(model) + " " + std::string(nozzle) + " nozzle - TinMan Codex";
    });
}

bool tinmanx_process_preset_allowed(const std::string &preset_name, const std::string &active_printer_name)
{
    const std::string_view model = matched_model(active_printer_name, {});
    if (model.empty() || !tinmanx_machine_preset_allowed(active_printer_name))
        return true;

    const std::string process_name = bare_preset_name(preset_name);
    const std::string printer_name = bare_preset_name(active_printer_name);
    return process_name.find("@" + printer_name) != std::string::npos;
}

void tinmanx_apply_machine_catalog(AppConfig &config)
{
    std::map<std::string, std::map<std::string, std::set<std::string>>> vendors;
    constexpr std::array<const char *, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const MachineFamily &family : machine_families)
        vendors[std::string(family.vendor)][std::string(family.model)].insert(nozzles.begin(), nozzles.end());
    if (config.vendors() != vendors)
        config.set_vendors(std::move(vendors));
}

} // namespace Slic3r
