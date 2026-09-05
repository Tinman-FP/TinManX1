#include <catch2/catch_all.hpp>

#include "libslic3r/FilamentSelection.hpp"
#include "libslic3r/PresetBundle.hpp"

using namespace Slic3r;

namespace {
void add_material(PresetBundle &bundle, const std::string &name)
{
    bundle.filaments.load_preset("", name, bundle.filaments.default_preset().config, false);
}
}

TEST_CASE("Filament choice commits one slot without changing tool or editor state", "[TinMan][Preset][FilamentSelection]")
{
    PresetBundle bundle;
    add_material(bundle, "Old");
    add_material(bundle, "New");
    bundle.filament_presets = {"Old", "Old", "Old", "Old"};
    bundle.filaments.select_preset_by_name("Old", true);
    bundle.filaments.get_edited_preset().config.set_key_value("filament_flow_ratio", new ConfigOptionFloats{0.97});
    bundle.filaments.get_edited_preset().is_dirty = true;
    bundle.project_config.set_key_value("filament_colour", new ConfigOptionStrings{"#111111", "#222222", "#333333", "#444444"});
    const auto printer = bundle.printers.get_edited_preset().config;
    const auto process = bundle.prints.get_edited_preset().config;
    const auto editor = bundle.filaments.get_edited_preset().config;
    const auto physical = bundle.physical_printers.get_selected_full_printer_name();
    const auto index = GENERATE(size_t(0), size_t(1), size_t(2), size_t(3));
    FilamentSlotSelection selection{index, "New", bundle.printers.get_edited_preset().name,
        FilamentSelectionColor{"#AABBCC", "multi", "#AABBCC #DDEEFF"}};
    const auto before = bundle.project_config;
    std::string reason;
    REQUIRE(apply_filament_slot_selection(bundle, selection, reason));
    CHECK(reason.empty());
    const auto &project = static_cast<const DynamicPrintConfig &>(bundle.project_config);
    for (size_t i = 0; i < bundle.filament_presets.size(); ++i) {
        CHECK(bundle.filament_presets[i] == (i == index ? "New" : "Old"));
        CHECK(project.opt_string("filament_colour", i) ==
              (i == index ? "#AABBCC" : before.opt_string("filament_colour", i)));
    }
    CHECK(project.opt_string("filament_multi_colour", index) == "#AABBCC #DDEEFF");
    CHECK(project.opt_string("filament_colour_type", index) == "multi");
    for (const auto &key : before.diff(project))
        CHECK((key == "filament_colour" || key == "filament_colour_type" || key == "filament_multi_colour"));
    CHECK(bundle.printers.get_edited_preset().config == printer);
    CHECK(bundle.prints.get_edited_preset().config == process);
    CHECK(bundle.filaments.get_edited_preset().config == editor);
    CHECK(bundle.filaments.current_is_dirty());
    CHECK(bundle.physical_printers.get_selected_full_printer_name() == physical);
}

TEST_CASE("Stale filament requests preserve all slot and project data", "[TinMan][Preset][FilamentSelection]")
{
    PresetBundle bundle;
    add_material(bundle, "Old");
    add_material(bundle, "New");
    bundle.filament_presets = {"Old", "Old"};
    FilamentSlotSelection selection{1, "New", bundle.printers.get_edited_preset().name,
        FilamentSelectionColor{"#AABBCC", "", "#AABBCC"}};
    SECTION("Out of range slot") { selection.index = size_t(-1); }
    SECTION("Missing profile") { selection.preset_name = "Missing"; }
    SECTION("Hidden profile") { bundle.filaments.find_preset("New", false, true)->is_visible = false; }
    SECTION("Changed printer") { selection.printer_name = "Previous printer"; }
    SECTION("Malformed color vector") { bundle.project_config.set_key_value("filament_multi_colour", new ConfigOptionFloat(1)); }
    const auto before = bundle.project_config;
    const auto slots = bundle.filament_presets;
    std::string reason;
    CHECK_FALSE(apply_filament_slot_selection(bundle, selection, reason));
    CHECK_FALSE(reason.empty());
    CHECK(bundle.project_config == before);
    CHECK(bundle.filament_presets == slots);
}

TEST_CASE("Material-only changes retain project colors", "[TinMan][Preset][FilamentSelection]")
{
    PresetBundle bundle;
    add_material(bundle, "New");
    bundle.filament_presets = {"Previous"};
    const auto before = bundle.project_config;
    std::string reason;
    REQUIRE(apply_filament_slot_selection(bundle,
        {0, "New", bundle.printers.get_edited_preset().name, std::nullopt}, reason));
    CHECK(bundle.filament_presets.front() == "New");
    CHECK(bundle.project_config == before);
}

TEST_CASE("Physical printer names without a preset do not invent one", "[TinMan][Preset][FilamentSelection]")
{
    for (const std::string &name : {"", "A", "AB", "My printer", "Printer \xc3\xa9"}) {
        CHECK(PhysicalPrinter::get_short_name(name) == name);
        CHECK(PhysicalPrinter::get_preset_name(name).empty());
    }
    const std::string full = "My printer" + PhysicalPrinter::separator() + "Machine 0.6 nozzle";
    CHECK(PhysicalPrinter::get_short_name(full) == "My printer");
    CHECK(PhysicalPrinter::get_preset_name(full) == "Machine 0.6 nozzle");
}
