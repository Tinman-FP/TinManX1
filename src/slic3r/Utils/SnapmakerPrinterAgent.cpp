#include "SnapmakerPrinterAgent.hpp"
#include "Http.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "slic3r/GUI/GUI_App.hpp"

#include "nlohmann/json.hpp"
#include <boost/log/trivial.hpp>
#include <algorithm>
#include <cctype>
#include <cmath>
#include <utility>

namespace Slic3r {

namespace {

constexpr const char* SNAPMAKER_AGENT_VERSION = "0.0.1";

// Safely access a parallel array by index, returning a fallback if out of bounds.
template<typename T>
T safe_at(const std::vector<T>& vec, int index, const T& fallback)
{
    return (index >= 0 && index < static_cast<int>(vec.size())) ? vec[index] : fallback;
}

std::string canonical_material_label(std::string value)
{
    auto is_space = [](unsigned char c) { return std::isspace(c) != 0; };

    value.erase(value.begin(), std::find_if(value.begin(), value.end(), [&](unsigned char c) { return !is_space(c); }));
    value.erase(std::find_if(value.rbegin(), value.rend(), [&](unsigned char c) { return !is_space(c); }).base(), value.end());

    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) {
        if (c == ' ' || c == '_' || c == '/')
            return '-';
        return static_cast<char>(std::toupper(c));
    });

    std::string normalized;
    normalized.reserve(value.size());
    bool previous_dash = false;
    for (char c : value) {
        if (c == '-') {
            if (!previous_dash)
                normalized.push_back(c);
            previous_dash = true;
        } else {
            normalized.push_back(c);
            previous_dash = false;
        }
    }

    return normalized;
}

std::string material_type_from_label(const std::string& label)
{
    const std::string value = canonical_material_label(label);
    if (value.empty())
        return {};

    const std::pair<const char*, const char*> specialty_types[] = {
        {"HT-PLA-CF", "HT-PLA-CF"},
        {"HT-PLA-GF", "HT-PLA-GF"},
        {"PLA-CF",    "PLA-CF"},
        {"PLA-GF",    "PLA-GF"},
        {"PETG-CF",   "PETG-CF"},
        {"PETG-GF",   "PETG-GF"},
        {"PET-CF",    "PET-CF"},
        {"PET-GF",    "PET-GF"},
        {"PCTG-CF",   "PCTG-CF"},
        {"PCTG-GF",   "PCTG-GF"},
        {"PA-CF",     "PA-CF"},
        {"PA-GF",     "PA-GF"},
        {"ASA-CF",    "ASA-CF"},
        {"ABS-CF",    "ABS-CF"},
        {"PC-CF",     "PC-CF"},
        {"PCTG",      "PCTG"},
    };

    for (const auto& [needle, material] : specialty_types) {
        if (value.find(needle) != std::string::npos)
            return material;
    }

    const std::string simple_types[] = {"PLA", "PETG", "PET", "ABS", "ASA", "PC", "PA", "TPU", "PEBA", "PVA", "HIPS"};
    for (const std::string& material : simple_types) {
        if (value == material)
            return material;
    }

    return {};
}

bool fetch_json_document(const std::string& url,
                         const std::string& api_key,
                         nlohmann::json& output,
                         std::string& error)
{
    std::string body;
    bool        success = false;

    auto http = Http::get(url);
    if (!api_key.empty())
        http.header("X-Api-Key", api_key);
    http.timeout_connect(5)
        .timeout_max(10)
        .on_complete([&](std::string response, unsigned status) {
            if (status == 200) {
                body = std::move(response);
                success = true;
            } else {
                error = "HTTP error: " + std::to_string(status);
            }
        })
        .on_error([&](std::string, std::string message, unsigned status) {
            error = std::move(message);
            if (status > 0)
                error += " (HTTP " + std::to_string(status) + ")";
        })
        .perform_sync();

    if (!success)
        return false;

    output = nlohmann::json::parse(body, nullptr, false, true);
    if (output.is_discarded()) {
        error = "invalid JSON response";
        return false;
    }
    return true;
}

float nozzle_diameter_value(const nlohmann::json& value)
{
    double diameter = 0.0;
    try {
        if (value.is_number())
            diameter = value.get<double>();
        else if (value.is_string())
            diameter = std::stod(value.get<std::string>());
    } catch (...) {
        return 0.0f;
    }
    return diameter >= 0.1 && diameter <= 2.0 ? static_cast<float>(diameter) : 0.0f;
}

std::string nozzle_type_value(const nlohmann::json& value)
{
    if (!value.is_string())
        return "undefine";

    std::string type = value.get<std::string>();
    type.erase(type.begin(), std::find_if(type.begin(), type.end(), [](unsigned char c) { return !std::isspace(c); }));
    type.erase(std::find_if(type.rbegin(), type.rend(), [](unsigned char c) { return !std::isspace(c); }).base(), type.end());
    std::transform(type.begin(), type.end(), type.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });

    if (type == "hardened_steel" || type == "stainless_steel" || type == "tungsten_carbide" ||
        type == "brass")
        return type;
    if (type == "e3d")
        return "E3D";
    return "undefine";
}

} // anonymous namespace

SnapmakerPrinterAgent::SnapmakerPrinterAgent(std::string log_dir) : MoonrakerPrinterAgent(std::move(log_dir)) {}

AgentInfo SnapmakerPrinterAgent::get_agent_info_static()
{
    return AgentInfo{"snapmaker", "Snapmaker", SNAPMAKER_AGENT_VERSION, "Snapmaker printer agent"};
}

std::string SnapmakerPrinterAgent::combine_filament_type(const std::string& type, const std::string& sub_type)
{
    const std::string base = trim_and_upper(type);
    const std::string sub  = trim_and_upper(sub_type);

    if (base.empty())
        return {};

    if (sub.empty() || sub == "NONE")
        return base;

    // Snapmaker reports premium variants as a base material plus a full subtype
    // (for example base PLA, subtype HT-PLA-GF). Preserve the full material
    // identity so AMS sync can select the matching Codex profile.
    if (sub.rfind("HT-", 0) == 0 || sub.find(base + "-") != std::string::npos) {
        return sub;
    }

    if (sub == "CF")
        return base + "-CF";
    if (sub == "GF")
        return base + "-GF";
    if (sub == "SNAPSPEED" || sub == "HS")
        return base + " HIGH SPEED";
    if (sub == "SILK")
        return base + " SILK";
    if (sub == "WOOD")
        return base + " WOOD";
    if (sub == "MATTE")
        return base + " MATTE";
    if (sub == "MARBLE")
        return base + " MARBLE";

    // Unrecognized sub-type (brand names like Polylite, Basic, etc.) -- use base type only
    return base;
}

std::string SnapmakerPrinterAgent::resolve_filament_type(const std::string& type,
                                                         const std::string& sub_type,
                                                         const std::string& saved_label)
{
    const std::string reported_type = combine_filament_type(type, sub_type);
    if (!reported_type.empty())
        return reported_type;

    const std::string saved_type = material_type_from_label(saved_label);
    return saved_type.empty() ? "PLA" : saved_type;
}

std::vector<SnapmakerPrinterAgent::NozzleInfo>
SnapmakerPrinterAgent::parse_nozzle_metadata(const nlohmann::json& product_info,
                                             const nlohmann::json& save_variables)
{
    std::vector<NozzleInfo> result;
    const nlohmann::json* product_diameters = nullptr;
    if (product_info.is_object() && product_info.contains("nozzle_diameter") &&
        product_info["nozzle_diameter"].is_array()) {
        product_diameters = &product_info["nozzle_diameter"];
    }

    for (int tool_id = 0; tool_id < 16; ++tool_id) {
        const std::string size_key = "u1_t" + std::to_string(tool_id) + "_nozzle_size";
        const std::string type_key = "u1_t" + std::to_string(tool_id) + "_nozzle_type";

        float diameter = 0.0f;
        if (product_diameters != nullptr && tool_id < static_cast<int>(product_diameters->size()))
            diameter = nozzle_diameter_value((*product_diameters)[tool_id]);
        if (diameter == 0.0f && save_variables.is_object() && save_variables.contains(size_key))
            diameter = nozzle_diameter_value(save_variables[size_key]);
        if (diameter == 0.0f)
            continue;

        NozzleInfo info;
        info.tool_id = tool_id;
        info.diameter = diameter;
        if (save_variables.is_object() && save_variables.contains(type_key))
            info.type = nozzle_type_value(save_variables[type_key]);
        result.emplace_back(std::move(info));
    }
    return result;
}

bool SnapmakerPrinterAgent::fetch_device_info(const std::string& base_url,
                                              const std::string& api_key,
                                              MoonrakerDeviceInfo& info,
                                              std::string& error) const
{
    if (!MoonrakerPrinterAgent::fetch_device_info(base_url, api_key, info, error))
        return false;

    nlohmann::json product_info = nlohmann::json::object();
    nlohmann::json save_variables = nlohmann::json::object();
    std::string tooling_error;
    const bool have_product = fetch_json_document(join_url(base_url, "/server/files/config/snapmaker/product_info.json"),
                                                  api_key, product_info, tooling_error);
    if (!have_product) {
        BOOST_LOG_TRIVIAL(warning) << "SnapmakerPrinterAgent: product metadata unavailable: " << tooling_error;
    }

    nlohmann::json variables_response;
    tooling_error.clear();
    if (fetch_json_document(join_url(base_url, "/printer/objects/query?save_variables"),
                            api_key, variables_response, tooling_error)) {
        const auto& result = variables_response.contains("result") ? variables_response["result"] : nlohmann::json::object();
        const auto& status = result.contains("status") ? result["status"] : nlohmann::json::object();
        const auto& saved = status.contains("save_variables") ? status["save_variables"] : nlohmann::json::object();
        if (saved.contains("variables") && saved["variables"].is_object())
            save_variables = saved["variables"];
    } else {
        BOOST_LOG_TRIVIAL(warning) << "SnapmakerPrinterAgent: saved tooling metadata unavailable: " << tooling_error;
    }

    auto parsed = parse_nozzle_metadata(product_info, save_variables);
    if (!parsed.empty()) {
        std::lock_guard<std::mutex> lock(nozzle_info_mutex_);
        nozzle_info_ = std::move(parsed);
        BOOST_LOG_TRIVIAL(info) << "SnapmakerPrinterAgent: discovered " << nozzle_info_.size() << " U1 tool nozzles";
    }
    return true;
}

void SnapmakerPrinterAgent::augment_print_payload_locked(nlohmann::json& payload,
                                                         const nlohmann::json& status) const
{
    std::vector<NozzleInfo> nozzles;
    {
        std::lock_guard<std::mutex> lock(nozzle_info_mutex_);
        nozzles = nozzle_info_;
    }
    if (nozzles.empty())
        return;

    nlohmann::json tooling = nlohmann::json::array();
    for (const NozzleInfo& nozzle : nozzles) {
        nlohmann::json item = {
            {"id", nozzle.tool_id},
            {"diameter", nozzle.diameter},
            {"type", nozzle.type},
            {"flow", nozzle.flow}
        };

        const std::string object_name = nozzle.tool_id == 0 ? "extruder" : "extruder" + std::to_string(nozzle.tool_id);
        if (status.contains(object_name) && status[object_name].is_object()) {
            const auto& extruder = status[object_name];
            if (extruder.contains("temperature") && extruder["temperature"].is_number())
                item["temperature"] = extruder["temperature"];
            if (extruder.contains("target") && extruder["target"].is_number())
                item["target"] = extruder["target"];
        }
        tooling.push_back(std::move(item));
    }
    payload["print"]["tinman_tooling"] = std::move(tooling);
}

bool SnapmakerPrinterAgent::fetch_filament_info(std::string dev_id)
{
    std::string url = join_url(device_info.base_url, "/printer/objects/query?print_task_config&save_variables&filament_detect");

    std::string response_body;
    bool        success = false;
    std::string http_error;

    auto http = Http::get(url);
    if (!device_info.api_key.empty()) {
        http.header("X-Api-Key", device_info.api_key);
    }
    http.timeout_connect(5)
        .timeout_max(10)
        .on_complete([&](std::string body, unsigned status) {
            if (status == 200) {
                response_body = body;
                success       = true;
            } else {
                http_error = "HTTP error: " + std::to_string(status);
            }
        })
        .on_error([&](std::string body, std::string err, unsigned status) {
            http_error = err;
            if (status > 0) {
                http_error += " (HTTP " + std::to_string(status) + ")";
            }
        })
        .perform_sync();

    if (!success) {
        BOOST_LOG_TRIVIAL(warning) << "SnapmakerPrinterAgent::fetch_filament_info: HTTP request failed: " << http_error;
        return false;
    }

    auto json = nlohmann::json::parse(response_body, nullptr, false, true);
    if (json.is_discarded()) {
        BOOST_LOG_TRIVIAL(warning) << "SnapmakerPrinterAgent::fetch_filament_info: Invalid JSON response";
        return false;
    }

    // Navigate to result.status.print_task_config
    if (!json.contains("result") || !json["result"].contains("status") ||
        !json["result"]["status"].contains("print_task_config")) {
        BOOST_LOG_TRIVIAL(warning) << "SnapmakerPrinterAgent::fetch_filament_info: Missing print_task_config in response";
        return false;
    }

    auto& ptc = json["result"]["status"]["print_task_config"];
    const auto& status = json["result"]["status"];
    const auto& save_variables = status.contains("save_variables") && status["save_variables"].contains("variables") &&
                                 status["save_variables"]["variables"].is_object()
                                     ? status["save_variables"]["variables"]
                                     : nlohmann::json::object();

    // Read parallel arrays from print_task_config
    auto filament_exist    = ptc.value("filament_exist", std::vector<bool>{});
    auto filament_type     = ptc.value("filament_type", std::vector<std::string>{});
    auto filament_sub_type = ptc.value("filament_sub_type", std::vector<std::string>{});
    auto filament_color    = ptc.value("filament_color_rgba", std::vector<std::string>{});
    auto filament_vendor   = ptc.value("filament_vendor", std::vector<std::string>{});

    const int slot_count = static_cast<int>(filament_exist.size());
    if (slot_count == 0) {
        BOOST_LOG_TRIVIAL(info) << "SnapmakerPrinterAgent::fetch_filament_info: No filament slots reported";
        return false;
    }

    // Read NFC filament_detect data for temperature info (optional)
    nlohmann::json nfc_info;
    if (json["result"]["status"].contains("filament_detect") &&
        json["result"]["status"]["filament_detect"].contains("info")) {
        nfc_info = json["result"]["status"]["filament_detect"]["info"];
    }

    static const std::string empty_str;
    static const std::string default_color = "FFFFFFFF";

    std::vector<AmsTrayData> trays;
    trays.reserve(slot_count);

    for (int i = 0; i < slot_count; ++i) {
        AmsTrayData tray;
        tray.slot_index   = i;
        tray.has_filament = filament_exist[i];

        if (tray.has_filament) {
            const std::string saved_key  = "u1_t" + std::to_string(i) + "_filament";
            const std::string saved_label = save_variables.value(saved_key, std::string());
            tray.tray_type = resolve_filament_type(safe_at(filament_type, i, empty_str),
                                                   safe_at(filament_sub_type, i, empty_str),
                                                   saved_label);
            tray.tray_color    = safe_at(filament_color, i, default_color);

            auto* bundle = GUI::wxGetApp().preset_bundle;
            // Resolve by exact material identity first; never let an unmatched specialty
            // material fall through to the first visible preset.
            if (bundle) {
                std::string vendor      = safe_at(filament_vendor, i, empty_str);
                tray.tray_info_idx      = resolve_filament_id_for_tray(bundle->filaments, tray.tray_type, vendor, tray.tray_color);
            } else {
                tray.tray_info_idx = map_filament_type_to_generic_id(tray.tray_type);
            }

            // Extract NFC temperature data if available
            if (nfc_info.is_array() && i < static_cast<int>(nfc_info.size()) && nfc_info[i].is_object()) {
                auto& nfc_slot = nfc_info[i];
                std::string vendor = nfc_slot.value("VENDOR", "NONE");
                if (vendor != "NONE" && !vendor.empty()) {
                    tray.bed_temp    = nfc_slot.value("BED_TEMP", 0);
                    tray.nozzle_temp = nfc_slot.value("FIRST_LAYER_TEMP", 0);
                }
            }
        }

        trays.emplace_back(std::move(tray));
    }

    BOOST_LOG_TRIVIAL(info) << "SnapmakerPrinterAgent::fetch_filament_info: parsed " << trays.size()
                            << " filament slots from " << device_info.base_url;
    build_ams_payload(1, slot_count - 1, trays);
    return true;
}

} // namespace Slic3r
