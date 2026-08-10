#pragma once

#include "MoonrakerPrinterAgent.hpp"

#include <string>

namespace Slic3r {

class SnapmakerPrinterAgent final : public MoonrakerPrinterAgent
{
public:
    explicit SnapmakerPrinterAgent(std::string log_dir);
    ~SnapmakerPrinterAgent() override = default;

    static AgentInfo get_agent_info_static();
    AgentInfo        get_agent_info() override { return get_agent_info_static(); }

    bool fetch_filament_info(std::string dev_id) override;

    // Prefer the U1's live slot material. Saved metadata is only a fallback for
    // firmware that does not expose a usable live type/subtype pair.
    static std::string resolve_filament_type(const std::string& type,
                                             const std::string& sub_type,
                                             const std::string& saved_label);

private:
    // Combine filament_type + filament_sub_type into a unified type string
    static std::string combine_filament_type(const std::string& type, const std::string& sub_type);
};

} // namespace Slic3r
