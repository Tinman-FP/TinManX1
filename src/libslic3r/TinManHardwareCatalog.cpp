#include "TinManHardwareCatalog.hpp"
#include "TinManHardwareCatalogData.hpp"

#include <algorithm>
#include <map>
#include <nlohmann/json.hpp>
#include <set>
#include <stdexcept>

namespace Slic3r {
namespace {

char lower_ascii(char value)
{
    return value >= 'A' && value <= 'Z' ? static_cast<char>(value + ('a' - 'A')) : value;
}

std::string folded(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), lower_ascii);
    return value;
}

bool contains_alias(std::string_view text, std::string_view alias)
{
    return !alias.empty() && std::search(text.begin(), text.end(), alias.begin(), alias.end(),
        [](char a, char b) { return lower_ascii(a) == lower_ascii(b); }) != text.end();
}

TinManConnectionMode parse_connection_mode(const std::string &value)
{
    if (value == "inherited") return TinManConnectionMode::Inherited;
    if (value == "bambu") return TinManConnectionMode::Bambu;
    if (value == "creality") return TinManConnectionMode::Creality;
    if (value == "qidi_moonraker") return TinManConnectionMode::QidiMoonraker;
    if (value == "snapmaker") return TinManConnectionMode::Snapmaker;
    if (value == "moonraker") return TinManConnectionMode::Moonraker;
    throw std::invalid_argument("unknown connection_mode: " + value);
}

} // namespace

const TinManMachineDefinition *TinManHardwareCatalog::find_model(std::string_view model) const
{
    const auto found = std::find_if(machines.begin(), machines.end(),
        [model](const TinManMachineDefinition &definition) { return definition.model == model; });
    return found == machines.end() ? nullptr : &*found;
}

const TinManMachineDefinition *TinManHardwareCatalog::match(std::string_view preset_name,
                                                          std::string_view machine_hint) const
{
    const TinManMachineDefinition *best = nullptr;
    size_t best_length = 0;
    for (const auto &definition : machines) {
        for (const auto &alias : definition.aliases) {
            if (alias.size() > best_length &&
                (contains_alias(preset_name, alias) || contains_alias(machine_hint, alias))) {
                best = &definition;
                best_length = alias.size();
            }
        }
    }
    return best;
}

bool TinManHardwareCatalog::valid(std::string *error) const
{
    if (error) error->clear();
    const auto fail = [error](const std::string &message) {
        if (error) *error = message;
        return false;
    };
    if (schema_version != 1 || catalog_version.empty())
        return fail("unsupported or incomplete catalog version");
    const std::set<std::string> supported {"0.4", "0.6", "0.8", "1.0"};
    if (nozzle_variants.size() != supported.size() ||
        std::set<std::string>(nozzle_variants.begin(), nozzle_variants.end()) != supported)
        return fail("nozzle_variants must contain 0.4, 0.6, 0.8 and 1.0 exactly once");
    if (machines.empty()) return fail("machines is empty");

    std::set<std::string> ids, models;
    std::map<std::string, std::string> alias_owners, profile_owners;
    for (const auto &definition : machines) {
        if (definition.id.empty() || definition.vendor.empty() || definition.model.empty())
            return fail("machine identity is incomplete");
        if (definition.tool_count == 0 || definition.tool_count > 64)
            return fail("invalid tool_count: " + definition.model);
        if (!ids.insert(definition.id).second || !models.insert(folded(definition.model)).second)
            return fail("duplicate machine identity: " + definition.model);
        if (std::find(definition.aliases.begin(), definition.aliases.end(), definition.model) ==
            definition.aliases.end())
            return fail("machine model is not an alias: " + definition.model);
        for (const auto &alias : definition.aliases) {
            const auto owner = alias_owners.emplace(folded(alias), definition.id);
            if (alias.empty() || (!owner.second && owner.first->second != definition.id))
                return fail("empty or ambiguous machine alias: " + alias);
        }
        for (const auto &name : definition.managed_profile_names) {
            if (name.empty() || !profile_owners.emplace(name, definition.id).second)
                return fail("empty or duplicate managed profile: " + name);
        }
    }
    return true;
}

TinManHardwareCatalog tinmanx_parse_hardware_catalog(std::string_view json)
{
    try {
        const auto root = nlohmann::json::parse(json.begin(), json.end());
        TinManHardwareCatalog catalog;
        if (!root.at("schema_version").is_number_integer() || root.at("schema_version") != 1)
            throw std::invalid_argument("unsupported schema_version");
        catalog.schema_version = root.at("schema_version").get<int>();
        catalog.catalog_version = root.at("catalog_version").get<std::string>();
        catalog.nozzle_variants = root.at("nozzle_variants").get<std::vector<std::string>>();
        if (!root.at("machines").is_array())
            throw std::invalid_argument("machines must be an array");
        for (const auto &item : root.at("machines")) {
            TinManMachineDefinition definition;
            definition.id = item.at("id").get<std::string>();
            definition.vendor = item.at("vendor").get<std::string>();
            definition.model = item.at("model").get<std::string>();
            definition.aliases = item.at("aliases").get<std::vector<std::string>>();
            definition.managed_profile_names = item.value("managed_profile_names", std::vector<std::string>{});
            const auto &count = item.at("tool_count");
            if (!count.is_number_integer() || count < 1 || count > 64)
                throw std::invalid_argument("invalid tool_count: " + definition.model);
            definition.tool_count = count.get<size_t>();
            const auto capability = item.at("nozzle_capability").get<std::string>();
            if (capability != "stock_standard" && capability != "cm2_standard" &&
                capability != "stock_high_flow" && capability != "cm2_cht")
                throw std::invalid_argument("unknown nozzle_capability: " + capability);
            definition.high_flow_nozzles = capability == "stock_high_flow" || capability == "cm2_cht";
            definition.printer_agent = item.at("printer_agent").get<std::string>();
            definition.connection_mode = parse_connection_mode(item.at("connection_mode").get<std::string>());
            catalog.machines.emplace_back(std::move(definition));
        }
        std::string error;
        if (!catalog.valid(&error)) throw std::invalid_argument(error);
        return catalog;
    } catch (const nlohmann::json::exception &error) {
        throw std::invalid_argument(std::string("invalid hardware catalog: ") + error.what());
    }
}

const TinManHardwareCatalog &tinmanx_hardware_catalog()
{
    static const TinManHardwareCatalog catalog = tinmanx_parse_hardware_catalog(tinman_hardware_catalog_json);
    return catalog;
}

} // namespace Slic3r
