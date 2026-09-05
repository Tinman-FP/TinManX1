#include <catch2/catch_all.hpp>

#include <boost/filesystem.hpp>
#include "libslic3r/PresetBundle.hpp"

using namespace Slic3r;
using Catch::Approx;

namespace {

struct CloudFixture {
    boost::filesystem::path root = boost::filesystem::temp_directory_path() /
        boost::filesystem::unique_path("tinman-cloud-%%%%-%%%%");
    PresetBundle bundle;
    PresetsConfigSubstitutions substitutions;

    CloudFixture() { boost::filesystem::create_directories(root); }
    ~CloudFixture() { boost::system::error_code error; boost::filesystem::remove_all(root, error); }

    Preset &local(const std::string &name = "Cloud process")
    {
        auto config = bundle.prints.default_preset().config;
        config.set_key_value("layer_height", new ConfigOptionFloat(0.2));
        config.set_key_value("print_settings_id", new ConfigOptionString(name));
        auto &preset = bundle.prints.load_preset((root / (name + ".json")).string(), name, config, true);
        preset.user_id = "fixture-user";
        preset.setting_id = "fixture-setting";
        preset.updated_time = 100;
        preset.save(nullptr);
        return preset;
    }

    std::map<std::string, std::string> values(const std::string &time = "200") const
    {
        return {{"version", "1.0.0"}, {"setting_id", "fixture-setting"}, {"user_id", "fixture-user"},
                {"updated_time", time}, {"inherits", ""}, {"layer_height", "0.24"},
                {"print_settings_id", "Cloud process"}};
    }

    bool load(std::map<std::string, std::string> values, const std::string &name = "Cloud process")
    {
        return bundle.prints.load_user_preset(name, std::move(values), substitutions,
                                             ForwardCompatibilitySubstitutionRule::Disable);
    }
};

} // namespace

TEST_CASE("Cloud refresh never saves unconfirmed editor tuning", "[Preset][CloudRecovery][TinMan]")
{
    const bool reported_dirty = GENERATE(false, true);
    CloudFixture fixture;
    fixture.local();
    auto &collection = fixture.bundle.prints;
    collection.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    collection.get_selected_preset().is_dirty = reported_dirty;
    const auto editor_before = collection.get_edited_preset().config;
    fixture.load(fixture.values());
    CHECK(collection.get_selected_preset().config.opt_float("layer_height") == Approx(0.24));
    CHECK(collection.get_edited_preset().config == editor_before);
    CHECK(collection.current_is_dirty());
    CHECK(collection.get_selected_preset().is_dirty);
    std::map<std::string, std::string> deletions;
    collection.save_user_presets(fixture.root.string(), PRESET_PRINT_NAME, deletions);
    DynamicPrintConfig saved;
    saved.load(collection.get_selected_preset().file, ForwardCompatibilitySubstitutionRule::Disable);
    CHECK(saved.opt_float("layer_height") == Approx(0.24));
    CHECK(collection.get_edited_preset().config == editor_before);
}

TEST_CASE("Clean cloud refresh advances the editor and saved baseline together", "[Preset][CloudRecovery][TinMan]")
{
    const bool stale_dirty_flag = GENERATE(false, true);
    CloudFixture fixture;
    fixture.local();
    auto &collection = fixture.bundle.prints;
    collection.get_selected_preset().is_dirty = stale_dirty_flag;
    fixture.load(fixture.values());
    CHECK(collection.get_selected_preset().config.opt_float("layer_height") == Approx(0.24));
    CHECK(collection.get_edited_preset().config.opt_float("layer_height") == Approx(0.24));
    CHECK_FALSE(collection.current_is_dirty());
    CHECK_FALSE(collection.saved_is_dirty());
    CHECK_FALSE(collection.get_selected_preset().is_dirty);
    CHECK(collection.get_edited_preset().updated_time == 200);
}

TEST_CASE("Repeated cloud refresh retains pending local persistence", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    auto &preset = fixture.local();
    preset.sync_info = "save";
    const auto before = preset.config;
    fixture.load(fixture.values("100"));
    CHECK(preset.config == before);
    CHECK(preset.sync_info == "save");
}

TEST_CASE("Failed cloud metadata writes do not publish new metadata", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    auto &preset = fixture.local();
    preset.sync_info = "hold";
    auto info = fixture.root / "Cloud process.info";
    boost::filesystem::remove(info);
    boost::filesystem::create_directory(info);
    auto values = fixture.values("100");
    values["setting_id"] = "replacement-fixture-setting";
    fixture.load(values);
    CHECK(preset.setting_id == "fixture-setting");
    CHECK(preset.sync_info == "hold");
    CHECK(boost::filesystem::is_directory(info));
}

TEST_CASE("Cloud input cannot overwrite protected preset identities", "[Preset][CloudRecovery][TinMan]")
{
    const int protection = GENERATE(0, 1, 2, 3);
    CloudFixture fixture;
    auto &preset = fixture.local();
    if (protection == 0) preset.is_system = true;
    if (protection == 1) preset.is_default = true;
    if (protection == 2) preset.is_project_embedded = true;
    if (protection == 3) preset.is_external = true;
    const auto before = preset.config;
    fixture.load(fixture.values());
    CHECK(preset.config == before);
    CHECK(preset.updated_time == 100);
    CHECK(preset.sync_info.empty());
}

TEST_CASE("Malformed cloud timestamps cannot outrank valid local records", "[Preset][CloudRecovery][TinMan]")
{
    const std::string time = GENERATE("200junk", "-1", "999999999999999999999999", "", "2.5");
    CloudFixture fixture;
    auto &preset = fixture.local();
    const auto before = preset.config;
    REQUIRE_NOTHROW(fixture.load(fixture.values(time)));
    CHECK(preset.config == before);
    CHECK(preset.updated_time == 100);
    CHECK(preset.sync_info.empty());
}

TEST_CASE("Rejected cloud inheritance retains the old record and remains retryable", "[Preset][CloudRecovery][TinMan]")
{
    const bool cycle = GENERATE(false, true);
    CloudFixture fixture;
    auto &preset = fixture.local();
    const auto before = preset.config;
    auto values = fixture.values();
    values["inherits"] = cycle ? preset.name : "Unavailable parent";
    if (cycle)
        CHECK_THROWS_AS(fixture.load(values), Slic3r::RuntimeError);
    else
        CHECK_FALSE(fixture.load(values));
    CHECK(preset.config == before);
    CHECK(preset.updated_time == 100);
    CHECK(preset.sync_info.empty());
    REQUIRE_NOTHROW(fixture.load(fixture.values()));
    CHECK(preset.config.opt_float("layer_height") == Approx(0.24));
}

TEST_CASE("Cloud insertion preserves selection and unsaved values", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    fixture.local("Z local process");
    auto &collection = fixture.bundle.prints;
    collection.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    const auto before = collection.get_edited_preset().config;
    REQUIRE(fixture.load(fixture.values(), "A cloud addition"));
    CHECK(collection.get_selected_preset_name() == "Z local process");
    CHECK(collection.get_edited_preset().config == before);
    REQUIRE(collection.find_preset("A cloud addition", false) != nullptr);
    CHECK(collection.find_preset("A cloud addition", false)->sync_info == "save");
    collection.update_after_user_presets_loaded();
    CHECK(collection.get_selected_preset_name() == "Z local process");
    CHECK(collection.get_edited_preset().config == before);
}

TEST_CASE("Cloud insertion preserves an explicitly unselected catalog", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    struct StrictCollection : PresetCollection {
        using PresetCollection::PresetCollection;
        using PresetCollection::select_preset_by_name_strict;
    } collection(Preset::TYPE_PRINT, Preset::print_options(), static_print_config_ref(FullPrintConfig::defaults()), "Default");
    CHECK_FALSE(collection.select_preset_by_name_strict("Not installed"));
    REQUIRE(collection.get_selected_idx() == size_t(-1));
    REQUIRE(collection.load_user_preset("Cloud process", fixture.values(), fixture.substitutions,
                                       ForwardCompatibilitySubstitutionRule::Disable));
    CHECK(collection.get_selected_idx() == size_t(-1));
}

TEST_CASE("Matching cloud tuning becomes clean without a false unsaved warning", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    fixture.local();
    auto &collection = fixture.bundle.prints;
    collection.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.24));
    collection.update_dirty();
    REQUIRE(collection.current_is_dirty());
    fixture.load(fixture.values());
    CHECK_FALSE(collection.current_is_dirty());
    CHECK_FALSE(collection.saved_is_dirty());
    CHECK_FALSE(collection.get_selected_preset().is_dirty);
    CHECK_FALSE(collection.get_edited_preset().is_dirty);
}

TEST_CASE("Subscribed cloud profiles retain independent identities and updates", "[Preset][CloudRecovery][TinMan]")
{
    CloudFixture fixture;
    const PresetOrigin origin(PresetOrigin::Kind::SubscribedBundle, "fixture-bundle");
    const auto name = get_preset_canonical_name("Cloud process", origin);
    auto &collection = fixture.bundle.prints;
    REQUIRE(collection.load_user_preset("Cloud process", fixture.values("100"), fixture.substitutions,
                                       ForwardCompatibilitySubstitutionRule::Disable, origin));
    auto *preset = collection.find_preset(name, false);
    REQUIRE(preset != nullptr);
    CHECK(preset->bundle_id == "fixture-bundle");
    auto next = fixture.values();
    next["layer_height"] = "0.28";
    REQUIRE_NOTHROW(collection.load_user_preset("Cloud process", next, fixture.substitutions,
                                              ForwardCompatibilitySubstitutionRule::Disable, origin));
    CHECK(preset->config.opt_float("layer_height") == Approx(0.28));
    CHECK(preset->updated_time == 200);
    CHECK(collection.find_preset("Cloud process", false) == nullptr);
}

TEST_CASE("Cloud updates preserve printer and material vectors without persisting editor changes", "[Preset][CloudRecovery][TinMan][MultiTool]")
{
    const auto type = GENERATE(Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER);
    const bool edited = GENERATE(false, true);
    CloudFixture fixture;
    PresetCollection &collection = type == Preset::TYPE_FILAMENT ? fixture.bundle.filaments : fixture.bundle.printers;
    auto config = collection.default_preset().config;
    const std::string key = type == Preset::TYPE_FILAMENT ? "filament_flow_ratio" : "nozzle_diameter";
    const std::vector<double> original = type == Preset::TYPE_FILAMENT ?
        std::vector<double>{0.96, 0.98} : std::vector<double>{0.6, 0.4, 0.4, 0.6};
    const std::vector<double> remote = type == Preset::TYPE_FILAMENT ?
        std::vector<double>{0.94, 0.99} : std::vector<double>{0.4, 0.4, 0.6, 0.6};
    config.option<ConfigOptionFloats>(key)->values = original;
    const std::string name = "Vector profile";
    const std::string identity = type == Preset::TYPE_FILAMENT ? "filament_settings_id" : "printer_settings_id";
    if (type == Preset::TYPE_FILAMENT) {
        config.set_key_value(identity, new ConfigOptionStrings{name});
        config.set_key_value("filament_extruder_variant", new ConfigOptionStrings{
            "Direct Drive Standard", "Direct Drive High Flow"});
    } else {
        config.set_key_value(identity, new ConfigOptionString(name));
    }
    auto &local = collection.load_preset((fixture.root / "vector.json").string(), name, config, true);
    local.updated_time = 100;
    local.user_id = "fixture-user";
    local.setting_id = "fixture-setting";
    if (edited)
        collection.get_edited_preset().config.option<ConfigOptionFloats>(key)->values.front() =
            type == Preset::TYPE_FILAMENT ? 0.95 : 0.8;
    const auto before = collection.get_edited_preset().config;
    auto values = fixture.values();
    values.erase("layer_height");
    values.erase("print_settings_id");
    values[identity] = config.option(identity)->serialize();
    auto remote_config = config;
    remote_config.option<ConfigOptionFloats>(key)->values = remote;
    values[key] = remote_config.option(key)->serialize();
    if (type == Preset::TYPE_FILAMENT)
        values["filament_extruder_variant"] = config.option("filament_extruder_variant")->serialize();
    REQUIRE_NOTHROW(collection.load_user_preset(name, values, fixture.substitutions,
                                              ForwardCompatibilitySubstitutionRule::Disable));
    CHECK(collection.get_selected_preset().config.option<ConfigOptionFloats>(key)->values == remote);
    if (edited)
        CHECK(collection.get_edited_preset().config == before);
    else
        CHECK(collection.get_edited_preset().config == collection.get_selected_preset().config);
    CHECK(collection.current_is_dirty() == edited);
    CHECK(collection.saved_is_dirty() == edited);
    std::map<std::string, std::string> deletions;
    collection.save_user_presets(fixture.root.string(), Preset::get_type_string(type), deletions);
    DynamicPrintConfig saved;
    saved.load(collection.get_selected_preset().file, ForwardCompatibilitySubstitutionRule::Disable);
    CHECK(saved.option<ConfigOptionFloats>(key)->values == remote);
    CHECK(collection.current_is_dirty() == edited);
}
