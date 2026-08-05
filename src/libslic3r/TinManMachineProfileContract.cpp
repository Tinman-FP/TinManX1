#include "TinManMachineProfileContract.hpp"

#include "AppConfig.hpp"

#include <array>
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

constexpr char lower_ascii(char value)
{
    return value >= 'A' && value <= 'Z' ? static_cast<char>(value + ('a' - 'A')) : value;
}

bool contains_ascii_case_insensitive(std::string_view haystack, std::string_view needle)
{
    if (needle.empty())
        return true;
    if (needle.size() > haystack.size())
        return false;

    for (size_t offset = 0; offset <= haystack.size() - needle.size(); ++offset) {
        size_t index = 0;
        while (index < needle.size() && lower_ascii(haystack[offset + index]) == lower_ascii(needle[index]))
            ++index;
        if (index == needle.size())
            return true;
    }
    return false;
}

std::string_view bare_preset_name(std::string_view name)
{
    const size_t slash = name.find_last_of('/');
    return slash == std::string::npos ? name : name.substr(slash + 1);
}

std::string_view matched_model(std::string_view preset_name, std::string_view machine_hint)
{
    std::string_view best_model;
    size_t best_length = 0;

    for (const MachineAlias &entry : machine_aliases) {
        if ((contains_ascii_case_insensitive(preset_name, entry.alias) ||
             contains_ascii_case_insensitive(machine_hint, entry.alias)) &&
            entry.alias.size() > best_length) {
            best_model = entry.model;
            best_length = entry.alias.size();
        }
    }
    return best_model;
}

bool is_canonical_machine_name(std::string_view name, std::string_view model, std::string_view nozzle)
{
    constexpr std::string_view separator = " ";
    constexpr std::string_view suffix = " nozzle - TinMan Codex";
    if (name.size() != model.size() + separator.size() + nozzle.size() + suffix.size())
        return false;

    size_t offset = 0;
    const auto consume = [&](std::string_view token, size_t &position) {
        if (name.substr(position, token.size()) != token)
            return false;
        position += token.size();
        return true;
    };
    return consume(model, offset) && consume(separator, offset) && consume(nozzle, offset) && consume(suffix, offset);
}

const AppConfig::VendorMap &canonical_machine_catalog()
{
    static const AppConfig::VendorMap vendors = [] {
        AppConfig::VendorMap result;
        constexpr std::array<const char *, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
        for (const MachineFamily &family : machine_families)
            result[std::string(family.vendor)][std::string(family.model)].insert(nozzles.begin(), nozzles.end());
        return result;
    }();
    return vendors;
}

} // namespace

bool tinmanx_machine_preset_allowed(const std::string &preset_name, const std::string &machine_hint)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return true;

    const std::string_view bare_name = bare_preset_name(preset_name);
    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const std::string_view nozzle : nozzles)
        if (is_canonical_machine_name(bare_name, model, nozzle))
            return true;
    return false;
}

bool tinmanx_process_preset_allowed(const std::string &preset_name, const std::string &active_printer_name)
{
    const std::string_view model = matched_model(active_printer_name, {});
    if (model.empty() || !tinmanx_machine_preset_allowed(active_printer_name))
        return true;

    const std::string_view process_name = bare_preset_name(preset_name);
    const std::string_view printer_name = bare_preset_name(active_printer_name);
    size_t marker = process_name.find('@');
    while (marker != std::string_view::npos) {
        if (process_name.substr(marker + 1, printer_name.size()) == printer_name)
            return true;
        marker = process_name.find('@', marker + 1);
    }
    return false;
}

void tinmanx_apply_machine_catalog(AppConfig &config)
{
    const AppConfig::VendorMap &vendors = canonical_machine_catalog();
    if (config.vendors() != vendors)
        config.set_vendors(vendors);
}

} // namespace Slic3r
