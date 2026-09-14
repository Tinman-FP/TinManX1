#pragma once

#include "MoonrakerPrinterAgent.hpp"

#include <mutex>
#include <string>
#include <vector>

namespace Slic3r {

class SnapmakerPrinterAgent final : public MoonrakerPrinterAgent
{
public:
    struct NozzleInfo {
        int         tool_id = -1;
        float       diameter = 0.0f;
        std::string type = "undefine";
        std::string flow = "standard";
    };

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

    static std::vector<NozzleInfo> parse_nozzle_metadata(const nlohmann::json& product_info,
                                                         const nlohmann::json& save_variables);

protected:
    bool fetch_device_info(const std::string& base_url,
                           const std::string& api_key,
                           MoonrakerDeviceInfo& info,
                           std::string& error) const override;
    void augment_print_payload_locked(nlohmann::json& payload, const nlohmann::json& status) const override;

private:
    // Combine filament_type + filament_sub_type into a unified type string
    static std::string combine_filament_type(const std::string& type, const std::string& sub_type);

    mutable std::mutex              nozzle_info_mutex_;
    mutable std::vector<NozzleInfo> nozzle_info_;
};

} // namespace Slic3r
