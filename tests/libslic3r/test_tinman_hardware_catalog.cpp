#include <catch2/catch_all.hpp>
#include <nlohmann/json.hpp>
#include <stdexcept>

#include "libslic3r/TinManHardwareCatalog.hpp"
#include "TinManHardwareCatalogData.hpp"
#include "libslic3r/TinManMachineProfileContract.hpp"
#include "libslic3r/PrintConfig.hpp"

using namespace Slic3r;

TEST_CASE("Embedded hardware catalog preserves every curated machine contract", "[TinMan][HardwareCatalog]")
{
    const auto &catalog = tinmanx_hardware_catalog();
    REQUIRE(catalog.valid());
    REQUIRE(catalog.machines.size() == 13);
    REQUIRE(catalog.nozzle_variants.size() == 4);
    for (const auto &machine : catalog.machines) {
        INFO(machine.model);
        REQUIRE(catalog.find_model(machine.model) == &machine);
        for (const auto &alias : machine.aliases) {
            REQUIRE(catalog.match(alias) == &machine);
            CHECK(tinmanx_expected_printer_agent(alias) == machine.printer_agent);
        }
        for (const auto &nozzle : catalog.nozzle_variants) {
            const auto name = machine.model + " " + nozzle + " nozzle - TinMan Codex";
            CHECK(tinmanx_managed_machine_preset(name, machine.model));
            CHECK(tinmanx_machine_preset_allowed(name, machine.model));
            CHECK(tinmanx_canonical_machine_preset_name(name, machine.model, nozzle) == name);
            DynamicPrintConfig printer, project;
            printer.set_key_value("printer_model", new ConfigOptionString(machine.model));
            REQUIRE(tinmanx_apply_nozzle_volume_contract(name, printer, project));
            CHECK(project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values ==
                  std::vector<int>(machine.tool_count, machine.high_flow_nozzles ?
                      NozzleVolumeType::nvtHighFlow : NozzleVolumeType::nvtStandard));
        }
        for (const auto &name : machine.managed_profile_names)
            CHECK(tinmanx_managed_machine_preset(name, machine.model));
    }
    CHECK(catalog.match("ratrig v-core 4 idex 500 COPY MODE")->id == "ratrig-v-core-4-idex-500-copy");
    CHECK(catalog.match("My custom machine") == nullptr);
    CHECK(catalog.match("", "sNaPmAkEr U1")->tool_count == 4);
    CHECK(catalog.find_model("Prusa CORE One L")->high_flow_nozzles == false);
    CHECK(catalog.find_model("Bambu Lab X1 Carbon")->high_flow_nozzles == true);
}

TEST_CASE("Hardware catalog rejects malformed definitions instead of silently defaulting", "[TinMan][HardwareCatalog]")
{
    auto root = nlohmann::json::parse(tinman_hardware_catalog_json);
    SECTION("invalid JSON") {
        CHECK_THROWS_AS(tinmanx_parse_hardware_catalog("{"), std::invalid_argument);
        return;
    }
    SECTION("new schema") { root["schema_version"] = 2; }
    SECTION("fractional schema") { root["schema_version"] = 1.5; }
    SECTION("overflowing schema") { root["schema_version"] = uint64_t(4294967297); }
    SECTION("missing version") { root.erase("catalog_version"); }
    SECTION("no machines") { root["machines"] = nlohmann::json::array(); }
    SECTION("wrong machine collection type") { root["machines"] = nlohmann::json::object(); }
    SECTION("duplicate nozzle") { root["nozzle_variants"][3] = "0.4"; }
    SECTION("unknown connection") { root["machines"][0]["connection_mode"] = "bmbu"; }
    SECTION("unknown nozzle capability") { root["machines"][0]["nozzle_capability"] = "highflow"; }
    SECTION("negative tool count") { root["machines"][0]["tool_count"] = -1; }
    SECTION("zero tool count") { root["machines"][0]["tool_count"] = 0; }
    SECTION("fractional tool count") { root["machines"][0]["tool_count"] = 1.5; }
    SECTION("boolean tool count") { root["machines"][0]["tool_count"] = true; }
    SECTION("huge tool count") { root["machines"][0]["tool_count"] = 1000000; }
    SECTION("duplicate id") { root["machines"][1]["id"] = root["machines"][0]["id"]; }
    SECTION("ambiguous alias") { root["machines"][1]["aliases"].push_back("bambu lab h2d"); }
    SECTION("empty alias") { root["machines"][0]["aliases"].push_back(""); }
    SECTION("missing model alias") { root["machines"][0]["aliases"] = {"Old H2D"}; }
    CHECK_THROWS_AS(tinmanx_parse_hardware_catalog(root.dump()), std::invalid_argument);
    // An invalid test document cannot poison the production catalog.
    CHECK(tinmanx_hardware_catalog().machines.size() == 13);
}
