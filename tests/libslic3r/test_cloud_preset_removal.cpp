#include <catch2/catch_all.hpp>

#include <boost/filesystem.hpp>
#include <fstream>
#include "libslic3r/AppConfig.hpp"
#include "libslic3r/PresetBundle.hpp"

using namespace Slic3r;
using Catch::Approx;

namespace {

struct RemovalFixture {
    boost::filesystem::path root = boost::filesystem::temp_directory_path() /
        boost::filesystem::unique_path("tinman-removal-%%%%-%%%%");
    PresetBundle bundle;
    AppConfig app;
    std::map<std::string, std::map<std::string, std::string>> remote;

    RemovalFixture()
    {
        boost::filesystem::create_directories(root);
        app.set("preset_folder", "fixture-user");
    }
    ~RemovalFixture() { boost::system::error_code error; boost::filesystem::remove_all(root, error); }

    Preset &add(const std::string &name)
    {
        auto config = bundle.prints.default_preset().config;
        config.set_key_value("layer_height", new ConfigOptionFloat(0.2));
        config.set_key_value("print_settings_id", new ConfigOptionString(name));
        auto &preset = bundle.prints.load_preset((root / (name + ".json")).string(), name, config, true);
        preset.user_id = "fixture-user";
        preset.setting_id = "id-" + name;
        preset.save(nullptr);
        return preset;
    }

    void remove() { bundle.remove_users_preset(app, &remote); }
};

} // namespace

TEST_CASE("Cloud deletion preserves actual unsaved edits even with a stale flag", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    auto &preset = fixture.add("Edited process");
    const auto file = preset.file;
    auto &collection = fixture.bundle.prints;
    collection.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    collection.get_selected_preset().is_dirty = false;
    fixture.remove();
    REQUIRE(collection.find_preset("Edited process", false) != nullptr);
    CHECK(boost::filesystem::exists(file));
    CHECK(collection.get_selected_preset().name == "Edited process");
    CHECK(collection.get_edited_preset().config.opt_float("layer_height") == Approx(0.17));
    CHECK(collection.current_is_dirty());
}

TEST_CASE("Deleting an earlier cloud preset retains selected editor identity", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    fixture.add("A removed process");
    fixture.add("Z selected process");
    fixture.remote["Z selected process"] = {{"type", "print"}};
    auto &collection = fixture.bundle.prints;
    collection.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    collection.update_dirty();
    fixture.remove();
    CHECK(collection.find_preset("A removed process", false) == nullptr);
    CHECK(collection.get_selected_preset().name == "Z selected process");
    CHECK(collection.get_edited_preset().name == "Z selected process");
    CHECK(collection.get_edited_preset().config.opt_float("layer_height") == Approx(0.17));
    CHECK(collection.current_is_dirty());
}

TEST_CASE("Cloud deletion never removes an external imported file", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    auto &preset = fixture.add("Imported process");
    preset.is_external = true;
    const auto file = preset.file;
    fixture.remove();
    CHECK(fixture.bundle.prints.find_preset("Imported process", false) != nullptr);
    CHECK(boost::filesystem::exists(file));
}

TEST_CASE("Clean cloud-deleted presets are removed despite stale dirty flags", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    auto &preset = fixture.add("Clean removed process");
    const auto file = preset.file;
    preset.is_dirty = true;
    fixture.remove();
    CHECK(fixture.bundle.prints.find_preset("Clean removed process", false) == nullptr);
    CHECK_FALSE(boost::filesystem::exists(file));
}

TEST_CASE("Cloud deletion retains pending and local-only presets", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    auto &preset = fixture.add("Pending process");
    const bool local_only = GENERATE(false, true);
    if (local_only)
        preset.setting_id.clear();
    else
        preset.sync_info = "save";
    const auto file = preset.file;
    fixture.remove();
    CHECK(fixture.bundle.prints.find_preset("Pending process", false) != nullptr);
    CHECK(boost::filesystem::exists(file));
}

TEST_CASE("Unsaved presets cannot remove unrelated working-directory metadata", "[Preset][CloudRemoval][TinMan]")
{
    RemovalFixture fixture;
    struct RestoreDirectory {
        boost::filesystem::path previous = boost::filesystem::current_path();
        ~RestoreDirectory() { boost::system::error_code error; boost::filesystem::current_path(previous, error); }
    } restore;
    boost::filesystem::current_path(fixture.root);
    { std::ofstream sentinel(".info"); sentinel << "unrelated fixture metadata"; }
    Preset unsaved(Preset::TYPE_PRINT, "Unsaved process");
    REQUIRE(unsaved.file.empty());
    unsaved.remove_files(true);
    CHECK(boost::filesystem::exists(fixture.root / ".info"));
}

TEST_CASE("Cloud deletion preserves mixed-tool and flow-variant editor values", "[Preset][CloudRemoval][TinMan]")
{
    const bool printer = GENERATE(false, true);
    RemovalFixture fixture;
    PresetCollection &collection = printer ? static_cast<PresetCollection &>(fixture.bundle.printers) : fixture.bundle.filaments;
    const std::string name = printer ? "Mixed nozzle printer" : "Two flow variants";
    const auto file = (fixture.root / (name + ".json")).string();
    auto config = collection.default_preset().config;
    if (printer)
        config.set_key_value("printer_settings_id", new ConfigOptionString(name));
    else
        config.set_key_value("filament_settings_id", new ConfigOptionStrings{name});
    auto &preset = collection.load_preset(file, name, config, true);
    preset.user_id = "fixture-user";
    preset.setting_id = "fixture-id";
    preset.save(nullptr);
    auto &editor = collection.get_edited_preset().config;
    if (printer)
        editor.set_key_value("nozzle_diameter", new ConfigOptionFloats{0.4, 0.6, 0.4, 0.6});
    else
        editor.set_key_value("nozzle_temperature", new ConfigOptionInts{235, 245});
    const auto before = editor;
    fixture.remove();
    REQUIRE(collection.find_preset(name, false) != nullptr);
    CHECK(collection.get_selected_preset().name == name);
    CHECK(collection.get_edited_preset().config == before);
    CHECK(collection.current_is_dirty());
    CHECK(boost::filesystem::exists(file));
}
