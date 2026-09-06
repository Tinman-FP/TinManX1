#include "PresetTransfer.hpp"
#include "Preset.hpp"

#include <algorithm>
#include <charconv>

namespace Slic3r {

void PresetTransferCache::swap(PresetTransferCache &other) noexcept
{
    config.swap(other.config);
    options.swap(other.options);
    std::swap(extruder_count, other.extruder_count);
}

PresetTransferCacheScope::PresetTransferCacheScope(const std::vector<PresetTransferCache *> &caches)
{
    m_snapshots.reserve(caches.size());
    for (auto *cache : caches) {
        if (cache && std::none_of(m_snapshots.begin(), m_snapshots.end(),
                                 [cache](const auto &entry) { return entry.first == cache; }))
            m_snapshots.emplace_back(cache, *cache);
    }
}

void PresetTransferCacheScope::rollback() noexcept
{
    for (auto &entry : m_snapshots)
        entry.first->swap(entry.second);
    m_snapshots.clear();
}

bool transfer_preset_options(PresetCollection &presets, const std::string &source_name,
                             const std::string &destination_name, std::vector<std::string> options,
                             const std::function<bool(const std::string &)> &select,
                             std::string &reason)
{
    reason.clear();
    if (options.empty())
        return true;
    const Preset *source = presets.find_preset(Preset::remove_suffix_modified(source_name), false);
    const Preset *destination = presets.find_preset(Preset::remove_suffix_modified(destination_name), false, true);
    if (!source || !destination || !destination->is_visible) {
        reason = "The source or destination preset is no longer available.";
        return false;
    }
    const std::string target = destination->name;
    // Do not retain collection pointers across a selection dialog: saving or
    // syncing presets there may replace the underlying entries.
    const auto source_config = source->config;
    size_t extruders = 0;
    for (const auto &key : options) {
        if (key == "extruders_count" && presets.type() == Preset::TYPE_PRINTER) {
            const auto *nozzles = source_config.option<ConfigOptionFloats>("nozzle_diameter");
            if (Preset::printer_technology(source_config) != ptFFF || !nozzles || nozzles->empty()) {
                reason = "The source preset has no valid extruder count to transfer.";
                return false;
            }
            extruders = nozzles->size();
            continue;
        }
        const auto separator = key.find('#');
        const auto *option = source_config.option(key.substr(0, separator));
        if (!option) {
            reason = "The source preset no longer contains the selected option: " + key;
            return false;
        }
        if (separator != std::string::npos) {
            const auto *vector = dynamic_cast<const ConfigOptionVectorBase *>(option);
            const char *first = key.data() + separator + 1, *last = key.data() + key.size();
            size_t index = 0;
            const auto parsed = std::from_chars(first, last, index);
            if (!vector || parsed.ec != std::errc() || parsed.ptr != last || index >= vector->size()) {
                reason = "The selected tool or material option is no longer available: " + key;
                return false;
            }
        }
    }
    if (extruders > 0)
        options.erase(std::remove(options.begin(), options.end(), "extruders_count"), options.end());
    if (target != presets.get_edited_preset().name) {
        if (!select) {
            reason = "The destination preset could not be selected.";
            return false;
        }
        try {
            if (!select(target))
                return false;
        } catch (const std::exception &error) {
            reason = "The destination preset could not be selected: " + std::string(error.what());
            return false;
        }
    }
    destination = presets.find_preset(target, false, true);
    if (!destination || !destination->is_visible || presets.get_edited_preset().name != target) {
        reason = "The destination preset changed while the transfer was being confirmed.";
        return false;
    }
    try {
        DynamicPrintConfig candidate = presets.get_edited_preset().config;
        if (extruders > 0)
            candidate.set_num_extruders(extruders);
        candidate.apply_only(source_config, options);
        presets.get_edited_preset().config = std::move(candidate);
    } catch (const std::exception &error) {
        reason = "The selected settings could not be transferred: " + std::string(error.what());
        return false;
    }
    return true;
}
}
