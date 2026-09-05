#include <catch2/catch_all.hpp>

#include "libslic3r/ConfigResolutionTrace.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/TinManHardwareCatalog.hpp"

using namespace Slic3r;

namespace {

void check_report_matches(const DynamicPrintConfig &config, const ConfigResolutionTrace &trace)
{
    for (const auto &key : config.keys()) {
        INFO(key);
        const auto entry = trace.settings().find(key);
        if (!ConfigResolutionTrace::reportable(key)) {
            CHECK(entry == trace.settings().end());
            continue;
        }
        REQUIRE(entry != trace.settings().end());
        REQUIRE_FALSE(entry->second.empty());
        CHECK(entry->second.back().value == config.option(key)->serialize());
    }
    for (const auto &[key, history] : trace.settings()) CHECK(config.has(key));
}

const ConfigResolutionStep &last(const ConfigResolutionTrace &trace, const std::string &key)
{
    return trace.settings().at(key).back();
}

void add_material(PresetBundle &bundle, const std::string &name, int temperature)
{
    auto config = bundle.filaments.default_preset().config;
    config.set_key_value("nozzle_temperature", new ConfigOptionInts({temperature}));
    bundle.filaments.load_preset({}, name, config, false);
    bundle.filament_presets.push_back(name);
}

} // namespace

TEST_CASE("Reading absent preset metadata does not create settings", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    auto &preset = bundle.filaments.get_edited_preset();
    for (const char *key : {"inherits", "compatible_prints_condition", "compatible_printers_condition"})
        preset.config.erase(key);
    const Preset &read_only = preset;
    const auto before = read_only.config;
    CHECK(read_only.inherits().empty());
    CHECK(read_only.compatible_prints_condition().empty());
    CHECK(read_only.compatible_printers_condition().empty());
    CHECK(before == read_only.config);
    bundle.filament_presets = {preset.name, preset.name};
    ConfigResolutionTrace trace;
    bundle.full_config(false, std::nullopt, &trace);
    CHECK(before == read_only.config);
}

TEST_CASE("Config tracing preserves the resolved config and live inputs", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    const auto printer = bundle.printers.get_edited_preset().config;
    const auto process = bundle.prints.get_edited_preset().config;
    const auto filament = bundle.filaments.get_edited_preset().config;
    const auto project = bundle.project_config;
    const auto names = bundle.filament_presets;
    ConfigResolutionTrace trace;
    for (bool projected : {false, true}) {
        const auto expected = bundle.full_config(projected);
        const auto actual = bundle.full_config(projected, std::nullopt, &trace);
        CHECK(expected == actual);
        check_report_matches(actual, trace);
    }
    CHECK(printer == bundle.printers.get_edited_preset().config);
    CHECK(process == bundle.prints.get_edited_preset().config);
    CHECK(filament == bundle.filaments.get_edited_preset().config);
    CHECK(project == bundle.project_config);
    CHECK(names == bundle.filament_presets);
}

TEST_CASE("Config provenance distinguishes actual edits from a dirty flag", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    bundle.filament_presets.clear();
    add_material(bundle, "Tuned PET-CF", 275);
    bundle.filaments.select_preset_by_name("Tuned PET-CF", true);
    auto &edited = bundle.filaments.get_edited_preset();
    edited.config.set_key_value("filament_flow_ratio", new ConfigOptionFloats({0.98}));
    edited.is_dirty = false;
    bundle.project_config.set_key_value("nozzle_temperature", new ConfigOptionInts({300}));
    ConfigResolutionTrace trace;
    const auto config = bundle.full_config(true, std::nullopt, &trace);
    CHECK(config.option<ConfigOptionInts>("nozzle_temperature")->values == std::vector<int>{275});
    CHECK(last(trace, "nozzle_temperature").origins.front().kind == ConfigOriginKind::UserPreset);
    CHECK(last(trace, "filament_flow_ratio").origins.front().kind == ConfigOriginKind::UnsavedEdit);
    CHECK(last(trace, "filament_flow_ratio").origins.front().saved_value == "1");
    const auto &history = trace.settings().at("nozzle_temperature");
    CHECK(std::any_of(history.begin(), history.end(), [](const auto &step) {
        return step.value == "300" && step.origins.front().kind == ConfigOriginKind::Project;
    }));
    edited.is_dirty = true;
    bundle.full_config(true, std::nullopt, &trace);
    CHECK(last(trace, "nozzle_temperature").origins.front().kind == ConfigOriginKind::UserPreset);
}

TEST_CASE("Equal parent values do not invent inherited key provenance", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    auto config = bundle.prints.default_preset().config;
    bundle.prints.load_preset({}, "Parent", config, false);
    config.set_key_value("inherits", new ConfigOptionString("Parent"));
    bundle.prints.load_preset({}, "Child", config, true);
    ConfigResolutionTrace trace;
    bundle.full_config(false, std::nullopt, &trace);
    const auto &origin = last(trace, "outer_wall_speed").origins.front();
    CHECK(origin.preset == "Child");
    CHECK(origin.parent == "Parent");
    CHECK(origin.kind == ConfigOriginKind::UserPreset);
}

TEST_CASE("Material vector provenance preserves mixed tool routing", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    bundle.printers.get_edited_preset().config.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.4, 0.4, 0.6}));
    bundle.filament_presets.clear();
    for (int i = 0; i < 4; ++i) add_material(bundle, "Material " + std::to_string(i + 1), 240 + i * 10);
    bundle.project_config.set_key_value("filament_map", new ConfigOptionInts({4, 3, 2, 1}));
    for (bool projected : {false, true}) {
        ConfigResolutionTrace trace;
        const auto expected = bundle.full_config(projected);
        const auto actual = bundle.full_config(projected, std::nullopt, &trace);
        CHECK(expected == actual);
        check_report_matches(actual, trace);
        const auto &origins = last(trace, "nozzle_temperature").origins;
        REQUIRE(origins.size() == 4);
        for (size_t i = 0; i < origins.size(); ++i) {
            CHECK(origins[i].material == i + 1);
            CHECK(origins[i].preset == "Material " + std::to_string(i + 1));
        }
        CHECK(actual.option<ConfigOptionInts>("filament_map")->values == std::vector<int>{4, 3, 2, 1});
    }
}

TEST_CASE("Missing material fallbacks and normalization are explicit", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    bundle.filament_presets = {"Removed profile"};
    bundle.project_config.set_key_value("filament_map", new ConfigOptionInts({99}));
    ConfigResolutionTrace trace;
    const auto expected = bundle.full_config(false);
    const auto actual = bundle.full_config(false, std::nullopt, &trace);
    CHECK(expected == actual);
    REQUIRE_FALSE(trace.warnings().empty());
    CHECK(trace.warnings().front().find("Removed profile") != std::string::npos);
    CHECK(last(trace, "filament_map").origins.front().kind == ConfigOriginKind::Normalization);
    bundle.filament_presets.clear();
    bundle.full_config(false, std::nullopt, &trace);
    CHECK(trace.warnings().front().find("No material selected") != std::string::npos);
}

TEST_CASE("Trace excludes private connections and removes erased metadata", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    auto &printer = bundle.printers.get_edited_preset().config;
    printer.set_key_value("print_host", new ConfigOptionString("printer.invalid"));
    printer.set_key_value("printhost_password", new ConfigOptionString("test-only-value"));
    ConfigResolutionTrace trace;
    const auto actual = bundle.full_config(false, std::nullopt, &trace);
    CHECK(actual.opt_string("printhost_password") == "test-only-value");
    CHECK(trace.settings().count("print_host") == 0);
    CHECK(trace.settings().count("printhost_password") == 0);
    CHECK(trace.settings().count("inherits") == 0);
    CHECK_FALSE(ConfigResolutionTrace::reportable("custom_access_code"));
    CHECK_FALSE(ConfigResolutionTrace::reportable("cloudToken"));
}

TEST_CASE("Every curated hardware variant keeps traced and normal configs identical", "[Config][TinMan][Provenance]")
{
    for (const auto &machine : tinmanx_hardware_catalog().machines) {
        for (const auto &nozzle : tinmanx_hardware_catalog().nozzle_variants) {
            INFO(machine.model << " / " << nozzle);
            PresetBundle bundle;
            const std::string name = machine.model + " " + nozzle + " nozzle - TinMan Codex";
            auto printer = bundle.printers.default_preset().config;
            printer.set_key_value("printer_model", new ConfigOptionString(machine.model));
            printer.set_key_value("nozzle_diameter", new ConfigOptionFloats(std::vector<double>(machine.tool_count, std::stod(nozzle))));
            bundle.printers.load_preset({}, name, printer, true);
            ConfigResolutionTrace trace;
            const auto expected = bundle.full_config(false);
            const auto actual = bundle.full_config(false, std::nullopt, &trace);
            CHECK(expected == actual);
            CHECK(last(trace, "nozzle_volume_type").origins.front().kind == ConfigOriginKind::HardwareContract);
            check_report_matches(actual, trace);
        }
    }
}

TEST_CASE("SLA settings retain their real merge precedence", "[Config][TinMan][Provenance]")
{
    PresetBundle bundle;
    bundle.printers.get_edited_preset().config.set_key_value("printer_technology", new ConfigOptionEnum<PrinterTechnology>(ptSLA));
    ConfigResolutionTrace trace;
    const auto expected = bundle.full_config();
    const auto actual = bundle.full_config(true, std::nullopt, &trace);
    CHECK(expected == actual);
    check_report_matches(actual, trace);
}
