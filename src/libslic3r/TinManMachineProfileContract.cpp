#include "TinManMachineProfileContract.hpp"

#include "AppConfig.hpp"
#include "PrintConfig.hpp"

#include <algorithm>
#include <array>
#include <boost/log/trivial.hpp>
#include <map>
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
    size_t nozzle_count;
    bool high_flow_nozzles;
};

constexpr std::array<MachineFamily, 13> machine_families {{
    {"BBL", "Bambu Lab H2D", 2, true},
    {"BBL", "Bambu Lab X1 Carbon", 1, true},
    {"Creality", "Creality K2 Plus", 1, true},
    {"Elegoo", "Elegoo Centauri Carbon", 1, true},
    {"Prusa", "Prusa CORE One L", 1, true},
    {"Qidi", "Qidi X-Plus 4", 1, true},
    {"Qidi", "QidiMaxEz", 1, true},
    {"Ratrig", "RatRig V-Core 4 IDEX 500", 2, true},
    {"Ratrig", "RatRig V-Core 4 IDEX 500 COPY MODE", 2, true},
    {"Ratrig", "RatRig V-Core 4 IDEX 500 MIRROR MODE", 2, true},
    {"Snapmaker", "Snapmaker U1", 4, false},
    {"Sovol", "Sovol SV08 MAX", 1, true},
    {"TinManX1", "FibreSeek Seeker 3", 2, true},
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

constexpr std::string_view connection_section = "tinman_machine_connections";
constexpr std::string_view nozzle_volume_section = "nozzle_volume_types";
constexpr std::array<std::string_view, 13> connection_options {{
    "bbl_use_printhost",
    "host_type",
    "printer_agent",
    "print_host",
    "print_host_webui",
    "printhost_apikey",
    "flashforge_serial_number",
    "printhost_cafile",
    "printhost_port",
    "printhost_authorization_type",
    "printhost_user",
    "printhost_password",
    "printhost_ssl_ignore_revoke",
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

bool is_snapmaker_u1_mixed_tooling_name(std::string_view name, std::string_view model)
{
    if (model != "Snapmaker U1")
        return false;

    const std::string_view bare_name = bare_preset_name(name);
    return bare_name == "Snapmaker U1 Live Mixed - TinMan Codex" ||
           bare_name == "Snapmaker U1 Tooling - TinMan Codex";
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

std::string connection_key(std::string_view model, std::string_view option)
{
    return std::string(model) + "::" + std::string(option);
}

std::string direct_printer_host(std::string address)
{
    const auto first = address.find_first_not_of(" \t\r\n");
    if (first == std::string::npos)
        return {};
    address.erase(0, first);
    const auto last = address.find_last_not_of(" \t\r\n");
    address.erase(last + 1);

    if (const auto scheme = address.find("://"); scheme != std::string::npos)
        address.erase(0, scheme + 3);
    if (const auto separator = address.find_first_of("/?#"); separator != std::string::npos)
        address.erase(separator);
    if (const auto userinfo = address.rfind('@'); userinfo != std::string::npos)
        address.erase(0, userinfo + 1);

    if (!address.empty() && address.front() == '[') {
        const auto bracket = address.find(']');
        return bracket == std::string::npos ? address : address.substr(0, bracket + 1);
    }
    if (const auto port = address.find(':'); port != std::string::npos)
        address.erase(port);
    return address;
}

std::string k2_webui_url(std::string_view host)
{
    return host.empty() ? std::string() : "http://" + std::string(host) + ":4408/";
}

std::string nozzle_flow_value(const MachineFamily &family, size_t nozzle_count)
{
    const std::string_view flow_type = family.high_flow_nozzles ? "High Flow" : "Standard";
    std::string value;
    for (size_t index = 0; index < nozzle_count; ++index) {
        if (!value.empty())
            value.push_back(',');
        value.append(flow_type);
    }
    return value;
}

const MachineFamily *family_for_model(std::string_view model)
{
    const auto found = std::find_if(machine_families.begin(), machine_families.end(),
        [model](const MachineFamily &family) { return family.model == model; });
    return found == machine_families.end() ? nullptr : &*found;
}

bool is_qidi_moonraker_model(std::string_view model)
{
    return model == "Qidi X-Plus 4" || model == "QidiMaxEz";
}

std::string legacy_machine_address(const AppConfig &app_config,
                                   std::string_view model,
                                   std::string_view preset_name)
{
    if (app_config.has("ip_address", std::string(preset_name)))
        return app_config.get("ip_address", std::string(preset_name));

    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const std::string_view nozzle : nozzles) {
        const std::string canonical = std::string(model) + " " + std::string(nozzle) +
                                      " nozzle - TinMan Codex";
        if (app_config.has("ip_address", canonical))
            return app_config.get("ip_address", canonical);
    }
    return {};
}

} // namespace

bool tinmanx_machine_preset_allowed(const std::string &preset_name, const std::string &machine_hint)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return true;

    return tinmanx_managed_machine_preset(preset_name, machine_hint);
}

bool tinmanx_managed_machine_preset(const std::string &preset_name, const std::string &machine_hint)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return false;

    const std::string_view bare_name = bare_preset_name(preset_name);
    if (is_snapmaker_u1_mixed_tooling_name(bare_name, model))
        return true;

    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const std::string_view nozzle : nozzles)
        if (is_canonical_machine_name(bare_name, model, nozzle))
            return true;
    return false;
}

bool tinmanx_runtime_connection_option(const std::string &option_name)
{
    return std::find(connection_options.begin(), connection_options.end(), option_name) != connection_options.end();
}

std::string tinmanx_expected_printer_agent(const std::string &preset_name,
                                           const std::string &machine_hint)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model == "Bambu Lab H2D" || model == "Bambu Lab X1 Carbon")
        return "bbl";
    if (model == "Creality K2 Plus")
        return "crealityprint";
    if (model == "Qidi X-Plus 4" || model == "QidiMaxEz")
        return "qidi";
    if (model == "Snapmaker U1")
        return "snapmaker";
    if (model == "Prusa CORE One L" ||
        model == "RatRig V-Core 4 IDEX 500" ||
        model == "RatRig V-Core 4 IDEX 500 COPY MODE" ||
        model == "RatRig V-Core 4 IDEX 500 MIRROR MODE" ||
        model == "Sovol SV08 MAX")
        return "moonraker";
    return {};
}

bool tinmanx_enforce_machine_connection_contract(const std::string &preset_name,
                                                  DynamicPrintConfig &printer_config)
{
    const std::string machine_hint = printer_config.has("printer_model") ?
        printer_config.opt_string("printer_model") : std::string();
    const std::string_view model = matched_model(preset_name, machine_hint);
    const std::string expected_agent = tinmanx_expected_printer_agent(preset_name, machine_hint);

    bool changed = false;
    if (!expected_agent.empty() && printer_config.has("printer_agent") &&
        printer_config.opt_string("printer_agent") != expected_agent) {
        printer_config.set_key_value("printer_agent", new ConfigOptionString(expected_agent));
        changed = true;
    }

    // Qidi's Klipper printers expose Moonraker. Repair the inherited Orca
    // OctoPrint default in old profile copies and persisted connection data.
    if (is_qidi_moonraker_model(model) && printer_config.has("host_type") &&
        printer_config.opt_enum<PrintHostType>("host_type") != htMoonraker) {
        printer_config.set_key_value("host_type", new ConfigOptionEnum<PrintHostType>(htMoonraker));
        changed = true;
    }

    // K2 direct API and Moonraker are separate services. Keep the printable
    // profile on CrealityPrint's port 80 while Device/status uses the 4408
    // Moonraker proxy. This also repairs copies saved with :7125 as print_host.
    if (model == "Creality K2 Plus") {
        if (printer_config.has("host_type") &&
            printer_config.opt_enum<PrintHostType>("host_type") != htCrealityPrint) {
            printer_config.set_key_value("host_type", new ConfigOptionEnum<PrintHostType>(htCrealityPrint));
            changed = true;
        }

        std::string direct_host;
        if (printer_config.has("print_host")) {
            const std::string current = printer_config.opt_string("print_host");
            direct_host = direct_printer_host(current);
            if (!direct_host.empty() && current != direct_host) {
                printer_config.set_key_value("print_host", new ConfigOptionString(direct_host));
                changed = true;
            }
        }
        if (direct_host.empty() && printer_config.has("print_host_webui"))
            direct_host = direct_printer_host(printer_config.opt_string("print_host_webui"));
        if (!direct_host.empty() && printer_config.has("print_host_webui")) {
            const std::string expected_webui = k2_webui_url(direct_host);
            if (printer_config.opt_string("print_host_webui") != expected_webui) {
                printer_config.set_key_value("print_host_webui", new ConfigOptionString(expected_webui));
                changed = true;
            }
        }
    }

    return changed;
}

bool tinmanx_apply_nozzle_volume_contract(const std::string &preset_name,
                                          const DynamicPrintConfig &printer_config,
                                          DynamicPrintConfig &project_config)
{
    const std::string machine_hint = printer_config.has("printer_model") ?
        printer_config.opt_string("printer_model") : std::string();
    std::string contract_name = preset_name;
    if (!tinmanx_managed_machine_preset(contract_name, machine_hint) &&
        printer_config.has("printer_settings_id")) {
        contract_name = printer_config.opt_string("printer_settings_id");
    }
    if (!tinmanx_managed_machine_preset(contract_name, machine_hint)) {
        BOOST_LOG_TRIVIAL(debug) << "TinMan nozzle contract skipped for preset '"
                                 << contract_name << "' model '" << machine_hint << "'";
        return false;
    }

    const MachineFamily *family = family_for_model(matched_model(contract_name, machine_hint));
    auto *project_flow = project_config.option<ConfigOptionEnumsGeneric>("nozzle_volume_type", true);
    if (family == nullptr || project_flow == nullptr) {
        BOOST_LOG_TRIVIAL(debug) << "TinMan nozzle contract unavailable for preset '"
                                 << contract_name << "'";
        return false;
    }

    size_t nozzle_count = family->nozzle_count;
    if (const auto *diameters = printer_config.option<ConfigOptionFloats>("nozzle_diameter");
        diameters != nullptr && !diameters->values.empty()) {
        nozzle_count = diameters->values.size();
    }

    const int expected = family->high_flow_nozzles ?
        NozzleVolumeType::nvtHighFlow : NozzleVolumeType::nvtStandard;
    project_flow->values.assign(nozzle_count, expected);
    BOOST_LOG_TRIVIAL(debug) << "TinMan nozzle contract applied to '" << contract_name
                             << "': " << nozzle_count << " nozzle(s), flow=" << expected;
    return true;
}

bool tinmanx_normalize_multitool_config(DynamicPrintConfig &config,
                                        size_t filament_count)
{
    const auto *diameters = config.option<ConfigOptionFloats>("nozzle_diameter");
    if (diameters == nullptr || diameters->values.empty()) {
        BOOST_LOG_TRIVIAL(error) << "Cannot normalize multi-tool configuration without a physical nozzle";
        return false;
    }

    const size_t tool_count = diameters->values.size();
    filament_count = std::max<size_t>(filament_count, 1);
    bool changed = false;

    auto *filament_map = config.option<ConfigOptionInts>("filament_map", true);
    if (filament_map->values.size() != filament_count) {
        filament_map->values.resize(filament_count, 1);
        changed = true;
    }
    for (int &tool : filament_map->values) {
        if (tool < 1 || static_cast<size_t>(tool) > tool_count) {
            tool = 1;
            changed = true;
        }
    }

    auto *flow_types = config.option<ConfigOptionEnumsGeneric>("nozzle_volume_type", true);
    if (flow_types->values.size() != tool_count) {
        flow_types->values.resize(tool_count, NozzleVolumeType::nvtStandard);
        changed = true;
    }

    if (auto *flush_multipliers = config.option<ConfigOptionFloats>("flush_multiplier", false);
        flush_multipliers != nullptr && flush_multipliers->values.size() != tool_count) {
        flush_multipliers->values.resize(tool_count, 1.0);
        changed = true;
    }

    if (auto *ams_counts = config.option<ConfigOptionStrings>("extruder_ams_count", false);
        ams_counts != nullptr && ams_counts->values.size() != tool_count) {
        ams_counts->values.resize(tool_count, std::string());
        changed = true;
    }

    if (changed) {
        BOOST_LOG_TRIVIAL(warning) << "Repaired multi-tool configuration: "
                                   << filament_count << " filament slot(s), "
                                   << tool_count << " physical tool(s)";
    }
    return changed;
}

std::string tinmanx_canonical_machine_preset_name(const std::string &preset_name,
                                                  const std::string &machine_hint,
                                                  const std::string &nozzle_variant)
{
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return {};

    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    std::string_view nozzle = nozzle_variant;
    const auto is_supported_nozzle = [&] {
        return std::find(nozzles.begin(), nozzles.end(), nozzle) != nozzles.end();
    };
    if (!is_supported_nozzle()) {
        nozzle = {};
        const std::string_view bare_name = bare_preset_name(preset_name);
        for (const std::string_view candidate : nozzles) {
            const std::string marker = std::string(candidate) + " nozzle";
            if (contains_ascii_case_insensitive(bare_name, marker)) {
                nozzle = candidate;
                break;
            }
        }
    }
    if (nozzle.empty())
        return {};

    return std::string(model) + " " + std::string(nozzle) + " nozzle - TinMan Codex";
}

bool tinmanx_process_preset_allowed(const std::string &preset_name, const std::string &active_printer_name)
{
    const std::string_view model = matched_model(active_printer_name, {});
    if (model.empty() || !tinmanx_machine_preset_allowed(active_printer_name))
        return true;

    const std::string_view process_name = bare_preset_name(preset_name);
    const std::string_view printer_name = bare_preset_name(active_printer_name);
    const std::string_view process_printer_name =
        is_snapmaker_u1_mixed_tooling_name(printer_name, model) ?
            std::string_view("Snapmaker U1 Live Mixed - TinMan Codex") : printer_name;
    size_t marker = process_name.find('@');
    while (marker != std::string_view::npos) {
        if (process_name.substr(marker + 1, process_printer_name.size()) == process_printer_name)
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

    std::map<std::string, std::string> saved_flow_types;
    if (config.has_section(std::string(nozzle_volume_section)))
        saved_flow_types = config.get_section(std::string(nozzle_volume_section));

    // Orca gives this persisted section precedence over the machine profile's
    // default. Migrate every recognized legacy/source entry as well as the
    // canonical profiles so stale Standard values cannot reintroduce nozzle
    // mismatch warnings after startup or cloud synchronization.
    for (auto &[name, value] : saved_flow_types) {
        const std::string_view model = matched_model(name, {});
        const MachineFamily *family = family_for_model(model);
        if (family == nullptr)
            continue;
        const size_t count = std::max<size_t>(1, std::count(value.begin(), value.end(), ',') + 1);
        value = nozzle_flow_value(*family, count);
    }

    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const MachineFamily &family : machine_families) {
        const std::string flow_value = nozzle_flow_value(family, family.nozzle_count);
        for (const std::string_view nozzle : nozzles) {
            const std::string canonical = std::string(family.model) + " " + std::string(nozzle) +
                                          " nozzle - TinMan Codex";
            saved_flow_types[canonical] = flow_value;
        }
    }
    config.set_section(std::string(nozzle_volume_section), saved_flow_types);
}

bool tinmanx_remember_machine_connection(AppConfig &app_config,
                                         const std::string &preset_name,
                                         const DynamicPrintConfig &printer_config,
                                         bool overwrite_existing)
{
    const std::string machine_hint = printer_config.has("printer_model") ?
        printer_config.opt_string("printer_model") : std::string();
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return false;

    const std::string raw_print_host = printer_config.has("print_host") ?
        printer_config.opt_string("print_host") : std::string();
    const std::string raw_webui = printer_config.has("print_host_webui") ?
        printer_config.opt_string("print_host_webui") : std::string();
    if (raw_print_host.empty() && raw_webui.empty())
        return false;

    const std::string k2_host = model == "Creality K2 Plus" ?
        direct_printer_host(!raw_print_host.empty() ? raw_print_host : raw_webui) : std::string();
    const std::string print_host = !k2_host.empty() ? k2_host : raw_print_host;
    const std::string webui = !k2_host.empty() ? k2_webui_url(k2_host) : raw_webui;

    const std::string raw_saved_print_host = app_config.get(
        std::string(connection_section), connection_key(model, "print_host"));
    const std::string raw_saved_webui = app_config.get(
        std::string(connection_section), connection_key(model, "print_host_webui"));
    const std::string saved_k2_host = model == "Creality K2 Plus" ?
        direct_printer_host(!raw_saved_print_host.empty() ? raw_saved_print_host : raw_saved_webui) : std::string();
    const std::string saved_print_host = !saved_k2_host.empty() ? saved_k2_host : raw_saved_print_host;
    const std::string saved_webui = !saved_k2_host.empty() ? k2_webui_url(saved_k2_host) : raw_saved_webui;
    const std::string saved_address = !saved_print_host.empty() ? saved_print_host : saved_webui;

    bool changed = false;
    for (const std::string_view option : connection_options) {
        const ConfigOption *config_option = printer_config.option(std::string(option));
        if (config_option == nullptr)
            continue;
        const std::string key = connection_key(model, option);
        const std::string existing = app_config.get(std::string(connection_section), key);
        if (!overwrite_existing && !existing.empty())
            continue;

        std::string value = config_option->serialize();
        if (option == "printer_agent") {
            const std::string expected_agent = tinmanx_expected_printer_agent(preset_name, machine_hint);
            if (!expected_agent.empty())
                value = expected_agent;
        } else if (option == "host_type") {
            if (model == "Creality K2 Plus")
                value = "crealityprint";
            else if (is_qidi_moonraker_model(model))
                value = "moonraker";
        } else if (option == "print_host" && !k2_host.empty()) {
            value = print_host;
        } else if (option == "print_host_webui" && !k2_host.empty()) {
            value = webui;
        }
        if (!overwrite_existing && !saved_address.empty() &&
            option == "print_host")
            value = saved_print_host;
        if (!overwrite_existing && !saved_address.empty() &&
            option == "print_host_webui")
            value = saved_webui;
        if (value.empty())
            continue;
        if (existing != value) {
            app_config.set_str(std::string(connection_section), key, value);
            changed = true;
        }
    }

    const std::string address = !overwrite_existing && !saved_address.empty() ?
        saved_address : (!print_host.empty() ? print_host : webui);
    constexpr std::array<std::string_view, 4> nozzles {{"0.4", "0.6", "0.8", "1.0"}};
    for (const std::string_view nozzle : nozzles) {
        const std::string canonical = std::string(model) + " " + std::string(nozzle) +
                                      " nozzle - TinMan Codex";
        if (app_config.get("ip_address", canonical) != address) {
            app_config.set_str("ip_address", canonical, address);
            changed = true;
        }
    }
    return changed;
}

bool tinmanx_restore_machine_connection(const AppConfig &app_config,
                                        const std::string &preset_name,
                                        DynamicPrintConfig &printer_config)
{
    const std::string machine_hint = printer_config.has("printer_model") ?
        printer_config.opt_string("printer_model") : std::string();
    const std::string_view model = matched_model(preset_name, machine_hint);
    if (model.empty())
        return false;

    bool restored = false;
    for (const std::string_view option : connection_options) {
        const std::string key = connection_key(model, option);
        const std::string option_name(option);
        const ConfigOption *current_option = printer_config.option(option_name);
        if (!app_config.has(std::string(connection_section), key) || current_option == nullptr)
            continue;
        const std::string value = app_config.get(std::string(connection_section), key);
        if (value.empty())
            continue;
        if (current_option->serialize() == value) {
            restored = true;
            continue;
        }
        ConfigOption *restored_option = current_option->clone();
        if (!restored_option->deserialize(value)) {
            delete restored_option;
            continue;
        }
        printer_config.set_key_value(option_name, restored_option);
        restored = true;
    }

    if (!restored) {
        const std::string address = legacy_machine_address(app_config, model, preset_name);
        if (!address.empty()) {
            if (printer_config.has("print_host"))
                printer_config.set_key_value("print_host", new ConfigOptionString(address));
            if (printer_config.has("print_host_webui"))
                printer_config.set_key_value("print_host_webui", new ConfigOptionString(address));
            restored = true;
        }
    }
    return tinmanx_enforce_machine_connection_contract(preset_name, printer_config) || restored;
}

} // namespace Slic3r
