#pragma once

#include "PrintConfig.hpp"

#include <functional>
#include <string>
#include <utility>
#include <vector>

namespace Slic3r {
class PresetCollection;

struct PresetTransferCache {
    DynamicPrintConfig config;
    std::vector<std::string> options;
    size_t extruder_count = 0;

    void stage_options(const DynamicPrintConfig &source, const std::vector<std::string> &selected_options);
    void swap(PresetTransferCache &other) noexcept;
};

// Confirmation dialogs can stage several tabs before a later dialog cancels.
// Preserve any transfer already owned by an outer setup/project workflow.
class PresetTransferCacheScope {
public:
    explicit PresetTransferCacheScope(const std::vector<PresetTransferCache *> &caches);
    ~PresetTransferCacheScope() { rollback(); }
    PresetTransferCacheScope(const PresetTransferCacheScope &) = delete;
    PresetTransferCacheScope &operator=(const PresetTransferCacheScope &) = delete;

    void rollback() noexcept;
    void commit() noexcept { m_snapshots.clear(); }

private:
    std::vector<std::pair<PresetTransferCache *, PresetTransferCache>> m_snapshots;
};

// The selection callback owns confirmation and selection. A cancelled transfer
// returns false with no reason; other rejected requests provide an explanation.
bool transfer_preset_options(PresetCollection &presets, const std::string &source_name,
                             const std::string &destination_name, std::vector<std::string> options,
                             const std::function<bool(const std::string &)> &select,
                             std::string &reason);
}
