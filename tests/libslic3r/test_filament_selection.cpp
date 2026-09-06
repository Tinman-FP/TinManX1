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

namespace {
void configure_purge_layout(PresetBundle &bundle, size_t tools, size_t materials)
{
    add_material(bundle, "Material");
    bundle.filament_presets.assign(materials, "Material");
    bundle.printers.get_edited_preset().config.set_key_value(
        "nozzle_diameter", new ConfigOptionFloats(std::vector<double>(tools, 0.4)));
    std::vector<double> matrix, volumes, multipliers;
    for (size_t tool = 0; tool < tools; ++tool) {
        multipliers.push_back(0.5 + tool * 0.1);
        for (size_t from = 0; from < materials; ++from)
            for (size_t to = 0; to < materials; ++to)
                matrix.push_back(from == to ? 0 : 1000 * tool + 100 * from + to + 1);
    }
    for (size_t material = 0; material < materials; ++material) {
        volumes.push_back(100 + material * 10);
        volumes.push_back(150 + material * 10);
    }
    bundle.project_config.set_key_value("flush_volumes_matrix", new ConfigOptionFloats(matrix));
    bundle.project_config.set_key_value("flush_volumes_vector", new ConfigOptionFloats(volumes));
    bundle.project_config.set_key_value("flush_multiplier", new ConfigOptionFloats(multipliers));
}
}

TEST_CASE("Purge layout follows physical tool count without losing material settings", "[TinMan][Preset][PurgeLayout]")
{
    PresetBundle bundle;
    const size_t old_tools = GENERATE(1u, 2u, 4u);
    const size_t new_tools = GENERATE(1u, 2u, 4u);
    CAPTURE(old_tools, new_tools);
    configure_purge_layout(bundle, old_tools, 4);
    const auto before = bundle.project_config;
    const auto old_matrix = before.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    const auto volumes = before.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    bundle.printers.get_edited_preset().config.set_key_value(
        "nozzle_diameter", new ConfigOptionFloats(std::vector<double>(new_tools, 0.6)));
    const auto printer = bundle.printers.get_edited_preset().config;
    const auto process = bundle.prints.get_edited_preset().config;
    const auto filament = bundle.filaments.get_edited_preset().config;
    bundle.update_multi_material_filament_presets();
    CHECK(bundle.printers.get_edited_preset().config == printer);
    CHECK(bundle.prints.get_edited_preset().config == process);
    CHECK(bundle.filaments.get_edited_preset().config == filament);
    const auto &matrix = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    REQUIRE(matrix.size() == new_tools * 16);
    CHECK(bundle.project_config.option<ConfigOptionFloats>("flush_volumes_vector")->values == volumes);
    const auto &multipliers = bundle.project_config.option<ConfigOptionFloats>("flush_multiplier")->values;
    REQUIRE(multipliers.size() == new_tools);
    for (size_t tool = 0; tool < new_tools; ++tool) {
        CHECK(multipliers[tool] == (tool < old_tools ? 0.5 + tool * 0.1 : 1.0));
        for (size_t from = 0; from < 4; ++from)
            for (size_t to = 0; to < 4; ++to)
                CHECK(matrix[tool * 16 + from * 4 + to] == (tool < old_tools
                    ? old_matrix[tool * 16 + from * 4 + to]
                    : from == to ? 0.0 : volumes[2 * from] + volumes[2 * to + 1]));
    }
    const auto once = bundle.project_config;
    bundle.update_multi_material_filament_presets();
    CHECK(bundle.project_config == once);
    if (old_tools == new_tools)
        CHECK(bundle.project_config == before);
}

TEST_CASE("Deleting a material preserves the matching purge pairs and matrix rows", "[TinMan][Preset][PurgeLayout]")
{
    PresetBundle bundle;
    configure_purge_layout(bundle, 2, 4);
    const size_t removed = GENERATE(0u, 1u, 3u);
    CAPTURE(removed);
    const auto before = bundle.project_config;
    auto expected_volumes = before.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    expected_volumes.erase(expected_volumes.begin() + 2 * removed, expected_volumes.begin() + 2 * removed + 2);
    bundle.update_num_filaments(removed);
    CHECK(bundle.project_config.option<ConfigOptionFloats>("flush_volumes_vector")->values == expected_volumes);
    const auto &matrix = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    const auto &old_matrix = before.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    REQUIRE(matrix.size() == 18);
    for (size_t tool = 0; tool < 2; ++tool)
        for (size_t from = 0; from < 3; ++from)
            for (size_t to = 0; to < 3; ++to)
                CHECK(matrix[tool * 9 + from * 3 + to] == old_matrix[
                    tool * 16 + (from >= removed ? from + 1 : from) * 4 + (to >= removed ? to + 1 : to)]);
    const auto once = bundle.project_config;
    bundle.update_multi_material_filament_presets();
    CHECK(bundle.project_config == once);
}

TEST_CASE("Purge layout initializes replacement slots at the physical tool minimum", "[TinMan][Preset][PurgeLayout]")
{
    PresetBundle bundle;
    configure_purge_layout(bundle, 4, 4);
    const size_t removed = GENERATE(0u, 1u, 3u);
    const auto before = bundle.project_config;
    const auto &old_matrix = before.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    const auto &old_volumes = before.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    bundle.update_num_filaments(removed);
    REQUIRE(bundle.filament_presets.size() == 4);
    const auto &volumes = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    const auto &matrix = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    REQUIRE(volumes.size() == 8);
    REQUIRE(matrix.size() == 64);
    for (size_t i = 0; i < 4; ++i) {
        const size_t source = i < 3 ? (i >= removed ? i + 1 : i) : 0;
        CHECK(volumes[2 * i] == old_volumes[2 * source]);
        CHECK(volumes[2 * i + 1] == old_volumes[2 * source + 1]);
    }
    for (size_t tool = 0; tool < 4; ++tool)
        for (size_t from = 0; from < 4; ++from)
            for (size_t to = 0; to < 4; ++to) {
                const size_t old_from = from >= removed ? from + 1 : from;
                const size_t old_to = to >= removed ? to + 1 : to;
                CHECK(matrix[tool * 16 + from * 4 + to] == (from < 3 && to < 3
                    ? old_matrix[tool * 16 + old_from * 4 + old_to]
                    : from == to ? 0.0 : volumes[2 * from] + volumes[2 * to + 1]));
            }
}

TEST_CASE("Incomplete purge arrays recover to a stable complete layout", "[TinMan][Preset][PurgeLayout]")
{
    PresetBundle bundle;
    configure_purge_layout(bundle, 2, 4);
    auto &matrix = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    auto &volumes = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    bool replace_matrix = false;
    SECTION("Matrix has an incomplete tool plane") { matrix.push_back(999); replace_matrix = true; }
    SECTION("Matrix planes are not square") { matrix.resize(30); replace_matrix = true; }
    SECTION("Matrix is missing") { matrix.clear(); replace_matrix = true; }
    SECTION("Volume pair is incomplete") { volumes.resize(7); }
    SECTION("Volume pairs are missing") { volumes.clear(); }
    SECTION("Only one volume remains") { volumes.resize(1); }
    SECTION("Extra volume is discarded") { volumes.push_back(999); }
    const auto old_matrix = matrix, old_volumes = volumes;
    bundle.update_multi_material_filament_presets();
    REQUIRE(matrix.size() == 32);
    REQUIRE(volumes.size() == 8);
    for (size_t i = 0; i < 4; ++i)
        for (size_t part = 0; part < 2; ++part)
            CHECK(volumes[2 * i + part] == (2 * i + 1 < old_volumes.size()
                ? old_volumes[2 * i + part] : old_volumes.size() >= 2 ? old_volumes[part] : 140.));
    if (replace_matrix) {
        for (size_t tool = 0; tool < 2; ++tool)
            for (size_t from = 0; from < 4; ++from)
                for (size_t to = 0; to < 4; ++to)
                    CHECK(matrix[tool * 16 + from * 4 + to] == (from == to
                        ? 0.0 : volumes[2 * from] + volumes[2 * to + 1]));
    } else {
        CHECK(matrix == old_matrix);
    }
    const auto once = bundle.project_config;
    bundle.update_multi_material_filament_presets();
    CHECK(bundle.project_config == once);
}

TEST_CASE("Purge layout grows and shrinks logical materials independently of tools", "[TinMan][Preset][PurgeLayout]")
{
    PresetBundle bundle;
    const size_t tools = GENERATE(1u, 2u, 4u);
    const size_t old_count = GENERATE(4u, 5u, 8u);
    const size_t new_count = GENERATE(4u, 5u, 8u);
    CAPTURE(tools, old_count, new_count);
    configure_purge_layout(bundle, tools, old_count);
    const auto before = bundle.project_config;
    const auto &old_matrix = before.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    const auto &old_volumes = before.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    bundle.set_num_filaments(new_count);
    REQUIRE(bundle.filament_presets.size() == new_count);
    const auto &volumes = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_vector")->values;
    const auto &matrix = bundle.project_config.option<ConfigOptionFloats>("flush_volumes_matrix")->values;
    REQUIRE(volumes.size() == 2 * new_count);
    REQUIRE(matrix.size() == tools * new_count * new_count);
    for (size_t i = 0; i < new_count; ++i)
        for (size_t part = 0; part < 2; ++part)
            CHECK(volumes[2 * i + part] == old_volumes[2 * (i < old_count ? i : 0) + part]);
    for (size_t tool = 0; tool < tools; ++tool)
        for (size_t from = 0; from < new_count; ++from)
            for (size_t to = 0; to < new_count; ++to)
                CHECK(matrix[tool * new_count * new_count + from * new_count + to] ==
                    (from < old_count && to < old_count
                    ? old_matrix[tool * old_count * old_count + from * old_count + to]
                    : from == to ? 0.0 : volumes[2 * from] + volumes[2 * to + 1]));
    const auto once = bundle.project_config;
    bundle.update_multi_material_filament_presets();
    CHECK(bundle.project_config == once);
}
