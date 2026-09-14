#include "ConfigResolutionTrace.hpp"

#include <algorithm>
#include <cctype>

#include "Config.hpp"
#include "Preset.hpp"
#include "TinManMachineProfileContract.hpp"

namespace Slic3r {

void ConfigResolutionTrace::clear()
{
    m_settings.clear();
    m_warnings.clear();
}

void ConfigResolutionTrace::warn(std::string warning)
{
    m_warnings.emplace_back(std::move(warning));
}

bool ConfigResolutionTrace::reportable(const std::string &key)
{
    if (tinmanx_runtime_connection_option(key)) return false;
    std::string lower = key;
    std::transform(lower.begin(), lower.end(), lower.begin(),
                   [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    for (const char *private_marker : {"password", "apikey", "api_key", "access_code",
                                       "token", "secret", "printhost", "print_host"})
        if (lower.find(private_marker) != std::string::npos) return false;
    return true;
}

void ConfigResolutionTrace::record(const std::string &key, const ConfigOption &option,
                                   std::vector<ConfigValueOrigin> origins)
{
    if (reportable(key))
        m_settings[key].push_back({option.serialize(), std::move(origins)});
}

void ConfigResolutionTrace::applied(const ConfigBase &config, ConfigValueOrigin origin)
{
    for (const auto &key : config.keys())
        record(key, *config.option(key), {origin});
}

ConfigValueOrigin ConfigResolutionTrace::preset_origin(const std::string &key, const Preset &preset,
                                                       const PresetCollection &collection,
                                                       size_t material, bool projected)
{
    ConfigValueOrigin origin;
    origin.kind = preset.is_default ? ConfigOriginKind::Defaults :
                  preset.is_project_embedded ? ConfigOriginKind::ProjectPreset :
                  preset.is_system ? ConfigOriginKind::SystemPreset :
                  (preset.is_external || preset.is_from_bundle()) ? ConfigOriginKind::ImportedPreset :
                  ConfigOriginKind::UserPreset;
    origin.preset = preset.name;
    origin.material = material;
    origin.projected = projected && filament_options_with_variant.count(key) != 0;
    if (const auto *parent = preset.config.option<ConfigOptionString>("inherits"))
        origin.parent = parent->value;

    // Compare actual values, not the aggregate dirty flag (which can be stale,
    // or include only a runtime connection edit). Do not infer inheritance from
    // equality with a parent's already-flattened config.
    const auto *value = preset.config.option(key);
    if (value) origin.input_value = value->serialize();
    if (&preset == &collection.get_edited_preset() &&
        collection.get_selected_idx() < collection.size() &&
        collection.get_selected_preset_name() == preset.name && value) {
        const auto *saved_value = collection.get_selected_preset().config.option(key);
        if (!saved_value || *value != *saved_value) {
            origin.kind = ConfigOriginKind::UnsavedEdit;
            if (saved_value) origin.saved_value = saved_value->serialize();
        }
    }
    return origin;
}

void ConfigResolutionTrace::applied_preset(const ConfigBase &config, const Preset &preset,
                                          const PresetCollection &collection,
                                          size_t material, bool projected)
{
    for (const auto &key : config.keys())
        record(key, *config.option(key), {preset_origin(key, preset, collection, material, projected)});
}

void ConfigResolutionTrace::checkpoint(const ConfigBase &config, ConfigValueOrigin origin)
{
    // Remove erased metadata as well as recording changed/created options.
    // Entries remaining in the report must correspond to the returned config.
    for (auto it = m_settings.begin(); it != m_settings.end();) {
        if (!config.has(it->first)) it = m_settings.erase(it);
        else ++it;
    }
    for (const auto &key : config.keys()) {
        if (!reportable(key)) continue;
        const auto *option = config.option(key);
        const auto it = m_settings.find(key);
        if (it == m_settings.end() || it->second.back().value != option->serialize())
            record(key, *option, {origin});
    }
}

} // namespace Slic3r
