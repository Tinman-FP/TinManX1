#include "CloudProfileSnapshot.hpp"

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <set>
#include <nlohmann/json.hpp>

namespace Slic3r {
namespace {

using Json = nlohmann::json;

std::string optional_text(const Json &object, const char *key)
{
    const auto it = object.find(key);
    if (it == object.end())
        return {};
    if (!it->is_string())
        throw std::invalid_argument(std::string("Invalid cloud profile text field: ") + key);
    return it->get<std::string>();
}

long long timestamp(const Json &value, bool allow_string = false)
{
    if (value.is_number_unsigned()) {
        const auto number = value.get<unsigned long long>();
        if (number <= static_cast<unsigned long long>(std::numeric_limits<long long>::max()))
            return static_cast<long long>(number);
    } else if (value.is_number_integer()) {
        const auto number = value.get<long long>();
        if (number >= 0)
            return number;
    } else if (allow_string && value.is_string()) {
        const auto text = value.get<std::string>();
        if (!text.empty() && std::all_of(text.begin(), text.end(), [](unsigned char c) { return c >= '0' && c <= '9'; })) {
            try { return std::stoll(text); } catch (const std::logic_error &) {}
        }
    }
    throw std::invalid_argument("Invalid cloud profile timestamp.");
}

} // namespace

CloudPresetSnapshot tinmanx_parse_cloud_profile_snapshot(unsigned int http_status,
                                                        const std::string &body,
                                                        const std::string &user_id)
{
    if (http_status != 200 || user_id.empty())
        throw std::invalid_argument("A complete authenticated cloud profile snapshot is required.");
    const auto root = Json::parse(body);
    if (!root.is_object() || !root.contains("upserts") || !root.at("upserts").is_array())
        throw std::invalid_argument("Cloud profile snapshot is missing its profile list.");
    if (root.contains("next_cursor"))
        timestamp(root.at("next_cursor"));
    if (root.contains("has_more") && (!root.at("has_more").is_boolean() || root.at("has_more").get<bool>()))
        throw std::invalid_argument("An incomplete cloud profile page cannot replace the local library.");
    if (root.contains("deletes")) {
        if (!root.at("deletes").is_array())
            throw std::invalid_argument("Invalid cloud profile deletion list.");
        for (const auto &id : root.at("deletes"))
            if (!id.is_string() || id.get_ref<const std::string &>().empty())
                throw std::invalid_argument("Invalid cloud profile deletion identity.");
    }

    CloudPresetSnapshot snapshot;
    std::set<std::string> identities;
    for (const auto &row : root.at("upserts")) {
        if (!row.is_object() || !row.contains("content") || !row.at("content").is_object())
            throw std::invalid_argument("Invalid cloud profile content.");
        const auto &content = row.at("content");
        const auto type = optional_text(content, "type");
        if (type != "print" && type != "filament" && type != "printer")
            throw std::invalid_argument("Invalid cloud profile type.");

        std::string id = optional_text(row, "id");
        const auto content_id = optional_text(content, "setting_id");
        if (id.empty()) id = content_id;
        if (id.empty() || (!content_id.empty() && content_id != id))
            throw std::invalid_argument("Invalid or conflicting cloud profile identity.");
        if (!identities.insert(id).second)
            throw std::invalid_argument("Cloud profile snapshot contains duplicate identities.");
        const auto owner = optional_text(content, "user_id");
        if (!owner.empty() && owner != user_id)
            throw std::invalid_argument("Cloud profile snapshot contains another account's metadata.");

        std::string name = optional_text(content, "name");
        const auto row_name = optional_text(row, "name");
        if (name.empty()) name = row_name.empty() ? id : row_name;
        if (snapshot.count(name) != 0)
            throw std::invalid_argument("Cloud profile snapshot contains duplicate names.");
        const long long updated = row.contains("updated_time") ? timestamp(row.at("updated_time")) : 0;
        if (row.contains("created_time")) timestamp(row.at("created_time"));
        if (content.contains("updated_time")) timestamp(content.at("updated_time"), true);

        std::map<std::string, std::string> values;
        for (const auto &[key, value] : content.items())
            values[key] = value.is_string() ? value.get<std::string>() : value.dump();
        values["setting_id"] = id;
        values["user_id"] = user_id;
        if (values.count("updated_time") == 0)
            values["updated_time"] = std::to_string(updated);
        snapshot.emplace(std::move(name), std::move(values));
    }
    return snapshot;
}

} // namespace Slic3r
