#include <catch2/catch_all.hpp>

#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PresetTransfer.hpp"

using namespace Slic3r;

namespace {
void stage_height(PresetTransferCache &cache, double height)
{
    cache.options = {"layer_height"};
    cache.config.set_key_value("layer_height", new ConfigOptionFloat(height));
}

void check_cache(const PresetTransferCache &actual, const PresetTransferCache &expected)
{
    CHECK(actual.config == expected.config);
    CHECK(actual.options == expected.options);
    CHECK(actual.extruder_count == expected.extruder_count);
}

void configure_transfer(PresetCollection &presets)
{
    auto config = presets.default_preset().config;
    presets.load_preset({}, "Current", config, true);
    config.set_key_value("layer_height", new ConfigOptionFloat(0.24));
    presets.load_preset({}, "Source", config, false);
    config.set_key_value("layer_height", new ConfigOptionFloat(0.12));
    presets.load_preset({}, "Destination", config, false);
    presets.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.18));
}
}

TEST_CASE("Keeping a setup nozzle edit leaves other destination nozzles unchanged", "[TinMan][Preset][SetupTransfer]")
{
    PresetBundle bundle;
    auto source = bundle.printers.default_preset().config;
    source.set_num_extruders(4);
    source.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.4, 0.6, 0.4, 0.4}));
    auto destination = source;
    destination.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.8, 0.4, 0.6, 1.0}));
    PresetTransferCache cache;
    cache.stage_options(source, {"nozzle_diameter#1"});
    destination.apply_only(cache.config, cache.options);
    CHECK(destination.option<ConfigOptionFloats>("nozzle_diameter")->values ==
          std::vector<double>{0.8, 0.6, 0.6, 1.0});
    CHECK(cache.options == std::vector<std::string>{"nozzle_diameter#1"});
}

TEST_CASE("Keeping material variant edits preserves other destination variants", "[TinMan][Preset][SetupTransfer]")
{
    PresetBundle bundle;
    auto source = bundle.filaments.default_preset().config;
    source.set_key_value("filament_flow_ratio", new ConfigOptionFloats({0.98, 1.02, 0.96, 0.94}));
    auto destination = source;
    destination.set_key_value("filament_flow_ratio", new ConfigOptionFloats({1.0, 0.99, 1.01, 0.97}));
    PresetTransferCache cache;
    cache.stage_options(source, {"filament_flow_ratio#1", "filament_flow_ratio#3"});
    destination.apply_only(cache.config, cache.options);
    CHECK(destination.option<ConfigOptionFloats>("filament_flow_ratio")->values ==
          std::vector<double>{1.0, 1.02, 1.01, 0.94});
    CHECK(cache.options == std::vector<std::string>{"filament_flow_ratio#1", "filament_flow_ratio#3"});
}

TEST_CASE("Failed transfer preparation retains the previous pending options", "[TinMan][Preset][SetupTransfer]")
{
    PresetTransferCache cache;
    stage_height(cache, 0.2);
    cache.extruder_count = 4;
    const auto before = cache;
    DynamicPrintConfig invalid;
    invalid.set_key_value("layer_height", new ConfigOptionFloat(0.32));
    invalid.set_key_value("outer_wall_speed", new ConfigOptionString("invalid"));
    CHECK_THROWS(cache.stage_options(invalid, {"layer_height", "outer_wall_speed"}));
    check_cache(cache, before);
}

TEST_CASE("Explicit whole-vector transfers still copy all requested values", "[TinMan][Preset][SetupTransfer]")
{
    PresetBundle bundle;
    auto source = bundle.printers.default_preset().config;
    source.set_num_extruders(4);
    source.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.4, 0.4, 0.6}));
    auto destination = bundle.printers.default_preset().config;
    PresetTransferCache cache;
    cache.stage_options(source, {"nozzle_diameter"});
    destination.apply_only(cache.config, cache.options);
    CHECK(destination.option<ConfigOptionFloats>("nozzle_diameter")->values ==
          std::vector<double>{0.6, 0.4, 0.4, 0.6});
}

TEST_CASE("Preparing a replacement cache drops unselected old values", "[TinMan][Preset][SetupTransfer]")
{
    PresetTransferCache cache;
    stage_height(cache, 0.2);
    cache.extruder_count = 4;
    DynamicPrintConfig source;
    source.set_key_value("outer_wall_speed", new ConfigOptionFloat(40.0));
    cache.stage_options(source, {"outer_wall_speed"});
    CHECK(cache.config.keys() == std::vector<std::string>{"outer_wall_speed"});
    CHECK(cache.options == std::vector<std::string>{"outer_wall_speed"});
    CHECK(cache.extruder_count == 4);
    source.set_key_value("outer_wall_speed", new ConfigOptionFloat(80.0));
    CHECK(cache.config.opt_float("outer_wall_speed") == 40.0);
    cache.stage_options(source, {});
    CHECK(cache.config.empty());
    CHECK(cache.options.empty());
    CHECK(cache.extruder_count == 4);
}

TEST_CASE("Cancelling a later confirmation does not leak a queued process transfer", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process, filament, printer;
    const PresetTransferCache empty;
    {
        PresetTransferCacheScope confirmation({&printer, &process, &filament});
        stage_height(process, 0.32);
        printer.extruder_count = 4;
        // The following filament dialog cancels before the preset switch.
    }
    check_cache(process, empty);
    check_cache(filament, empty);
    check_cache(printer, empty);
    DynamicPrintConfig later_process;
    later_process.set_key_value("layer_height", new ConfigOptionFloat(0.16));
    later_process.apply_only(process.config, process.options);
    CHECK(later_process.opt_float("layer_height") == 0.16);
}

TEST_CASE("Cancelled selection preserves pre-existing postponed transfers", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process, printer;
    stage_height(process, 0.24);
    printer.options = {"nozzle_diameter#1"};
    printer.config.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.4, 0.4, 0.6}));
    printer.extruder_count = 4;
    const auto old_process = process, old_printer = printer;
    {
        PresetTransferCacheScope confirmation({&process, &printer});
        stage_height(process, 0.32);
        printer.config.clear();
        printer.options.clear();
        printer.extruder_count = 1;
        confirmation.rollback();
        check_cache(process, old_process);
        check_cache(printer, old_printer);
        confirmation.rollback();
        // Repeated rollback and destruction must not swap cancelled values back.
    }
    check_cache(process, old_process);
    check_cache(printer, old_printer);
}

TEST_CASE("Accepted confirmations retain their transfers and do not resurrect consumed caches", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process;
    {
        PresetTransferCacheScope confirmation({&process});
        stage_height(process, 0.28);
        confirmation.commit();
    }
    CHECK(process.config.opt_float("layer_height") == 0.28);
    CHECK(process.options == std::vector<std::string>{"layer_height"});
    {
        PresetTransferCacheScope confirmation({&process});
        confirmation.commit();
        process.config.clear();
        process.options.clear();
    }
    check_cache(process, PresetTransferCache{});
}

TEST_CASE("Pending transfer rollback also covers exceptions during confirmation", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process;
    stage_height(process, 0.2);
    const auto before = process;
    CHECK_THROWS_AS(([&]() {
        PresetTransferCacheScope confirmation({&process});
        stage_height(process, 0.4);
        throw std::runtime_error("confirmation failed");
    }()), std::runtime_error);
    check_cache(process, before);
}

TEST_CASE("Nested pending transfer confirmations restore their own entry state", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process;
    stage_height(process, 0.12);
    const auto initial = process;
    {
        PresetTransferCacheScope outer({&process});
        stage_height(process, 0.2);
        const auto outer_draft = process;
        {
            PresetTransferCacheScope inner({&process});
            stage_height(process, 0.32);
        }
        check_cache(process, outer_draft);
        {
            PresetTransferCacheScope inner({&process});
            stage_height(process, 0.36);
            inner.commit();
        }
        CHECK(process.config.opt_float("layer_height") == 0.36);
    }
    check_cache(process, initial);
}

TEST_CASE("Transfer confirmation accepts absent and repeated tab caches", "[TinMan][Preset][TransferCache]")
{
    PresetTransferCache process;
    stage_height(process, 0.2);
    const auto initial = process;
    {
        PresetTransferCacheScope confirmation({nullptr, &process, &process, nullptr});
        stage_height(process, 0.32);
    }
    check_cache(process, initial);
    PresetTransferCacheScope no_tabs({});
    no_tabs.commit();
}

TEST_CASE("Cancelling a comparison transfer leaves current editor settings intact", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    const auto before = bundle.prints.get_edited_preset().config;
    std::string reason;
    bool asked = false;
    CHECK_FALSE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [&](const std::string &name) { asked = true; CHECK(name == "Destination"); return false; }, reason));
    CHECK(asked);
    CHECK(reason.empty());
    CHECK(bundle.prints.get_edited_preset().name == "Current");
    CHECK(bundle.prints.get_edited_preset().config == before);
}

TEST_CASE("A transfer cannot apply to a different destination after selection", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    const auto before = bundle.prints.get_edited_preset().config;
    std::string reason;
    CHECK_FALSE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [](const std::string &) { return true; }, reason));
    CHECK_FALSE(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == before);
}

TEST_CASE("Comparison transfer applies only selected values to the accepted destination", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    const auto destination = bundle.prints.find_preset("Destination", false)->config;
    std::string reason;
    REQUIRE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [&](const std::string &name) { return bundle.prints.select_preset_by_name(name, false); }, reason));
    CHECK(reason.empty());
    CHECK(bundle.prints.get_edited_preset().name == "Destination");
    CHECK(bundle.prints.get_edited_preset().config.opt_float("layer_height") == 0.24);
    CHECK(bundle.prints.get_edited_preset().config.diff(destination) == std::vector<std::string>{"layer_height"});
}

TEST_CASE("Unavailable comparison profiles are rejected before selection", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    std::string source = "Source", target = "Destination", reason;
    SECTION("Missing source") { source = "Missing"; }
    SECTION("Missing destination") { target = "Missing"; }
    SECTION("Hidden destination") { bundle.prints.find_preset(target, false, true)->is_visible = false; }
    const auto before = bundle.prints.get_edited_preset().config;
    bool asked = false;
    CHECK_FALSE(transfer_preset_options(bundle.prints, source, target, {"layer_height"},
        [&](const std::string &) { asked = true; return true; }, reason));
    CHECK_FALSE(asked);
    CHECK_FALSE(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == before);
}

TEST_CASE("Transfer rejects a destination made unavailable during confirmation", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    std::string reason;
    DynamicPrintConfig selected;
    CHECK_FALSE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [&](const std::string &name) {
            bundle.prints.select_preset_by_name(name, false);
            selected = bundle.prints.get_edited_preset().config;
            bundle.prints.find_preset(name, false, true)->is_visible = false;
            return true;
        }, reason));
    CHECK_FALSE(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == selected);
}

TEST_CASE("A comparison transfer captures its source and preserves unrelated destination edits", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    std::string reason;
    REQUIRE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [&](const std::string &name) {
            bundle.prints.find_preset("Source", false, true)->config.set_key_value("layer_height", new ConfigOptionFloat(0.3));
            bundle.prints.select_preset_by_name(name, false);
            bundle.prints.get_edited_preset().config.set_key_value("outer_wall_speed", new ConfigOptionFloat(42));
            return true;
        }, reason));
    CHECK(bundle.prints.get_edited_preset().config.opt_float("layer_height") == 0.24);
    CHECK(bundle.prints.get_edited_preset().config.opt_float("outer_wall_speed") == 42);
    CHECK(bundle.prints.find_preset("Source", false, true)->config.opt_float("layer_height") == 0.3);
}

TEST_CASE("Transfers into the current editor do not prompt or change selection", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    std::string reason;
    REQUIRE(transfer_preset_options(bundle.prints, "Source", "Current", {"layer_height"},
        [&](const std::string &) { FAIL("The current destination does not need a selection dialog."); return false; }, reason));
    CHECK(bundle.prints.get_edited_preset().name == "Current");
    CHECK(bundle.prints.get_edited_preset().config.opt_float("layer_height") == 0.24);
}

TEST_CASE("Mixed nozzle and material variants transfer only the requested indices", "[TinMan][Preset][PresetTransfer][MultiTool]")
{
    PresetBundle bundle;
    const bool printer = GENERATE(false, true);
    auto &presets = printer ? bundle.printers : bundle.filaments;
    const std::string key = printer ? "nozzle_diameter" : "filament_flow_ratio";
    auto config = presets.default_preset().config;
    const std::vector<double> source = printer ? std::vector<double>{0.6, 0.4, 0.4, 0.6}
                                              : std::vector<double>{0.97, 0.94};
    const std::vector<double> destination(source.size(), printer ? 0.8 : 1.0);
    config.set_key_value(key, new ConfigOptionFloats(source));
    presets.load_preset({}, "Source", config, false);
    config.set_key_value(key, new ConfigOptionFloats(destination));
    presets.load_preset({}, "Destination", config, true);
    const auto before = presets.get_edited_preset().config;
    const size_t index = GENERATE(0u, 1u);
    std::string reason;
    REQUIRE(transfer_preset_options(presets, "Source", "Destination", {key + "#" + std::to_string(index)}, {}, reason));
    auto expected = destination;
    expected[index] = source[index];
    CHECK(presets.get_edited_preset().config.option<ConfigOptionFloats>(key)->values == expected);
    CHECK(presets.get_edited_preset().config.diff(before) == std::vector<std::string>{key});
}

TEST_CASE("Printer tool count changes are local to an accepted transfer", "[TinMan][Preset][PresetTransfer][MultiTool]")
{
    PresetBundle bundle;
    auto &presets = bundle.printers;
    auto config = presets.default_preset().config;
    config.set_key_value("nozzle_diameter", new ConfigOptionFloats{0.6, 0.4, 0.4, 0.6});
    presets.load_preset({}, "Source", config, false);
    config.set_key_value("nozzle_diameter", new ConfigOptionFloats{0.8});
    presets.load_preset({}, "Destination", config, false);
    const auto current = presets.get_edited_preset().config;
    const bool accept = GENERATE(false, true);
    std::string reason;
    CHECK(transfer_preset_options(presets, "Source", "Destination", {"extruders_count", "nozzle_diameter"},
        [&](const std::string &name) { return accept && presets.select_preset_by_name(name, false); }, reason) == accept);
    CHECK(reason.empty());
    if (accept)
        CHECK(presets.get_edited_preset().config.option<ConfigOptionFloats>("nozzle_diameter")->values ==
              std::vector<double>{0.6, 0.4, 0.4, 0.6});
    else
        CHECK(presets.get_edited_preset().config == current);
}

TEST_CASE("Malformed or stale indexed options cannot silently use another variant", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    auto &presets = bundle.filaments;
    presets.load_preset({}, "Source", presets.default_preset().config, false);
    presets.load_preset({}, "Destination", presets.default_preset().config, true);
    const std::string key = GENERATE("filament_flow_ratio#", "filament_flow_ratio#-1", "filament_flow_ratio#1junk",
        "filament_flow_ratio#999", "filament_flow_ratio#999999999999999999999999", "inherits#0", "absent_option");
    CAPTURE(key);
    const auto before = presets.get_edited_preset().config;
    std::string reason;
    CHECK_FALSE(transfer_preset_options(presets, "Source", "Destination", {key}, {}, reason));
    CHECK_FALSE(reason.empty());
    CHECK(presets.get_edited_preset().config == before);
}

TEST_CASE("An invalid transferred value cannot partially modify destination settings", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    bundle.prints.select_preset_by_name("Destination", false);
    bundle.prints.find_preset("Source", false, true)->config.set_key_value("outer_wall_speed", new ConfigOptionString("invalid"));
    const auto before = bundle.prints.get_edited_preset().config;
    std::string reason;
    CHECK_FALSE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height", "outer_wall_speed"}, {}, reason));
    CHECK_FALSE(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == before);
}

TEST_CASE("Empty comparisons do not select a destination", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    const auto before = bundle.prints.get_edited_preset().config;
    std::string reason;
    CHECK(transfer_preset_options(bundle.prints, "Unavailable", "Unavailable", {}, {}, reason));
    CHECK(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == before);
}

TEST_CASE("Missing tool counts and missing selection handlers reject transfers", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    auto &presets = bundle.printers;
    presets.load_preset({}, "Source", presets.default_preset().config, false);
    presets.load_preset({}, "Destination", presets.default_preset().config, false);
    auto &source = presets.find_preset("Source", false, true)->config;
    SECTION("Empty source tool count") { source.set_key_value("nozzle_diameter", new ConfigOptionFloats()); }
    SECTION("Missing source tool count") { source.erase("nozzle_diameter"); }
    SECTION("No selection handler") {}
    const auto before = presets.get_edited_preset().config;
    std::string reason;
    CHECK_FALSE(transfer_preset_options(presets, "Source", "Destination", {"extruders_count"}, {}, reason));
    CHECK_FALSE(reason.empty());
    CHECK(presets.get_edited_preset().config == before);
}

TEST_CASE("A selection error does not apply captured transfer values", "[TinMan][Preset][PresetTransfer]")
{
    PresetBundle bundle;
    configure_transfer(bundle.prints);
    const auto before = bundle.prints.get_edited_preset().config;
    std::string reason;
    CHECK_FALSE(transfer_preset_options(bundle.prints, "Source", "Destination", {"layer_height"},
        [](const std::string &) -> bool { throw std::runtime_error("selection failed"); }, reason));
    CHECK_FALSE(reason.empty());
    CHECK(bundle.prints.get_edited_preset().config == before);
}
