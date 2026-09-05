#include <catch2/catch_all.hpp>

#include <boost/filesystem.hpp>
#include <boost/nowide/fstream.hpp>
#include <fstream>

#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/AppConfig.hpp"
#include "libslic3r/Utils.hpp"
#include "libslic3r/Thread.hpp"

using namespace Slic3r;

namespace {

namespace fs = boost::filesystem;

struct TempPresetDir {
    fs::path path;

    TempPresetDir()
    {
        path = fs::temp_directory_path() / fs::unique_path("orcaslicer-preset-%%%%-%%%%-%%%%");
        fs::create_directories(path);
    }

    ~TempPresetDir()
    {
        boost::system::error_code ec;
        fs::remove_all(path, ec);
    }
};

void write_fixture(const fs::path &path, const std::string &contents)
{
    boost::nowide::ofstream stream(path.string(), std::ios::binary);
    stream << contents;
    REQUIRE(stream.good());
}

std::string read_fixture(const fs::path &path)
{
    boost::nowide::ifstream stream(path.string(), std::ios::binary);
    return std::string(std::istreambuf_iterator<char>(stream), {});
}

void write_print_preset(const DynamicPrintConfig &default_config, const fs::path &file, const std::string &name, const std::string &inherits = {})
{
    DynamicPrintConfig config(default_config);
    config.option<ConfigOptionString>("print_settings_id", true)->value = name;
    config.option<ConfigOptionString>(BBL_JSON_KEY_INHERITS, true)->value = inherits;

    fs::create_directories(file.parent_path());
    config.save_to_json(file.string(), name, "User", "1.0.0");
}

// Write a preset json carrying a name and an "inherits" value, using the given collection's
// default config so it loads back into that collection. Works for any preset type.
void write_preset_with_inherits(const DynamicPrintConfig &default_config, const fs::path &file,
                                const std::string &name, const std::string &inherits)
{
    DynamicPrintConfig config(default_config);
    config.option<ConfigOptionString>(BBL_JSON_KEY_INHERITS, true)->value = inherits;

    fs::create_directories(file.parent_path());
    config.save_to_json(file.string(), name, "User", "1.0.0");
}

// Add an in-memory preset (no file) with the given inherits value (empty => root preset).
Preset &add_inmemory_preset(PresetCollection &coll, const std::string &name, const std::string &inherits = {})
{
    DynamicPrintConfig config(coll.default_preset().config);
    config.option<ConfigOptionString>(BBL_JSON_KEY_INHERITS, true)->value = inherits;
    return coll.load_preset(std::string(), name, config, /*select=*/false);
}

DynamicPrintConfig physical_printer_config(const PresetBundle &bundle,
                                           std::vector<std::string> preset_names)
{
    DynamicPrintConfig config(bundle.physical_printers.default_config());
    config.option<ConfigOptionStrings>("preset_names")->values = std::move(preset_names);
    return config;
}

// Mark an already-loaded preset as renamed from one or more former names.
void set_renamed_from(PresetCollection &coll, const std::string &preset_name, std::vector<std::string> old_names)
{
    for (auto it = coll.begin(); it != coll.end(); ++it)
        if (it->name == preset_name)
            it->renamed_from = std::move(old_names);
}

// A standalone print preset collection that exposes the protected rename-map builder, so a
// renamed_from scenario can be set up without the full system-profile load pipeline.
// (PresetCollection is non-copyable - it holds a mutex - so it is constructed directly with
// the same type/keys/defaults PresetBundle uses for its print collection.)
struct RenameTestCollection : public PresetCollection
{
    RenameTestCollection()
        : PresetCollection(Preset::TYPE_PRINT, Preset::print_options(),
                           static_print_config_ref(FullPrintConfig::defaults()))
    {}
    using PresetCollection::update_map_system_profile_renamed;
};

} // namespace

TEST_CASE("Preset identity is canonicalized from load path", "[Preset][Identity]")
{
    TempPresetDir              temp_dir;
    PresetBundle               bundle;
    PresetsConfigSubstitutions substitutions;

    write_print_preset(bundle.prints.default_preset().config, temp_dir.path / PRESET_PRINT_NAME / "User.json", "User");
    write_print_preset(bundle.prints.default_preset().config, temp_dir.path / PRESET_LOCAL_DIR / "bundle-1" / PRESET_PRINT_NAME / "LocalBundle.json", "LocalBundle");
    write_print_preset(bundle.prints.default_preset().config, temp_dir.path / PRESET_SUBSCRIBED_DIR / "remote-1" / PRESET_PRINT_NAME / "Subscribed.json", "Subscribed");

    bundle.prints.load_presets(temp_dir.path.string(), PRESET_PRINT_NAME, substitutions, ForwardCompatibilitySubstitutionRule::Disable);
    bundle.prints.load_presets((temp_dir.path / PRESET_LOCAL_DIR / "bundle-1").string(), PRESET_PRINT_NAME, substitutions, ForwardCompatibilitySubstitutionRule::Disable);
    bundle.prints.load_presets((temp_dir.path / PRESET_SUBSCRIBED_DIR / "remote-1").string(), PRESET_PRINT_NAME, substitutions, ForwardCompatibilitySubstitutionRule::Disable);

    const Preset *root_user = bundle.prints.find_preset("User");
    REQUIRE(root_user != nullptr);
    CHECK(root_user->name == "User");
    CHECK_FALSE(root_user->is_from_bundle());

    const Preset *local_bundle = bundle.prints.find_preset("_local/bundle-1/LocalBundle");
    REQUIRE(local_bundle != nullptr);
    CHECK(local_bundle->name == "_local/bundle-1/LocalBundle");
    CHECK(local_bundle->is_from_bundle());

    const Preset *subscribed = bundle.prints.find_preset("_subscribed/remote-1/Subscribed");
    REQUIRE(subscribed != nullptr);
    CHECK(subscribed->name == "_subscribed/remote-1/Subscribed");
    CHECK(subscribed->is_from_bundle());
}

TEST_CASE("Failed user preset loads preserve original files and can recover", "[Preset][Recovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    PresetsConfigSubstitutions substitutions;
    const fs::path bad = temp_dir.path / PRESET_PRINT_NAME / "Recoverable.json";
    const fs::path info = temp_dir.path / PRESET_PRINT_NAME / "Recoverable.info";
    const fs::path good = temp_dir.path / PRESET_PRINT_NAME / "Healthy.json";
    write_print_preset(bundle.prints.default_preset().config, good, "Healthy");

    const std::string bytes = GENERATE(
        std::string("{\"version\":\"1.0.0\",\"layer_height\":"),
        std::string("{\"version\":\"1.0.0\",\"layer_height\":\"not-a-number\"}"),
        std::string("[\"not a preset object\"]"),
        std::string("{\"version\":\"invalid\",\"layer_height\":\"0.2\"}"));
    const std::string metadata = "sync_info = create\nsetting_id = recovery-test-only\n";
    write_fixture(bad, bytes);
    write_fixture(info, metadata);

    std::vector<std::string> callbacks;
    const auto load = [&]() {
        bundle.prints.load_presets(temp_dir.path.string(), PRESET_PRINT_NAME, substitutions,
            ForwardCompatibilitySubstitutionRule::Disable,
            [&](Preset &preset) {
                CHECK(preset.loaded);
                callbacks.push_back(preset.name);
            });
    };
    REQUIRE_NOTHROW(load());
    CHECK(callbacks == std::vector<std::string>{"Healthy"});
    CHECK(bundle.prints.find_preset("Recoverable", false) == nullptr);
    REQUIRE(bundle.prints.find_preset("Healthy", false) != nullptr);
    CHECK(read_fixture(good).size() > 0);
    CHECK(fs::exists(bad));
    CHECK(fs::exists(info));
    CHECK(read_fixture(bad) == bytes);
    CHECK(read_fixture(info) == metadata);

    // A retry must preserve the same evidence, and not publish a partial preset.
    callbacks.clear();
    REQUIRE_NOTHROW(load());
    CHECK(callbacks.empty());
    CHECK(read_fixture(bad) == bytes);
    CHECK(read_fixture(info) == metadata);

    write_print_preset(bundle.prints.default_preset().config, bad, "Recoverable");
    callbacks.clear();
    REQUIRE_NOTHROW(load());
    CHECK(callbacks == std::vector<std::string>{"Recoverable"});
    const auto *recovered = bundle.prints.find_preset("Recoverable", false);
    REQUIRE(recovered != nullptr);
    CHECK(recovered->loaded);
    CHECK(recovered->setting_id == "recovery-test-only");
    CHECK(read_fixture(info) == metadata);
}

TEST_CASE("Replacing a saved file preserves the destination on failure", "[Preset][Recovery][TinMan]")
{
    TempPresetDir temp_dir;
    const fs::path source = temp_dir.path / "new.tmp";
    const fs::path destination = temp_dir.path / "saved.json";
    write_fixture(destination, "previous contents");

    SECTION("missing replacement must not remove the saved file") {
        const auto error = rename_file(source.string(), destination.string());
        CHECK(bool(error));
        CHECK(error == std::errc::no_such_file_or_directory);
        CHECK(read_fixture(destination) == "previous contents");
    }
    SECTION("successful replacement publishes the new contents") {
        write_fixture(source, "new contents");
        CHECK_FALSE(rename_file(source.string(), destination.string()));
        CHECK(read_fixture(destination) == "new contents");
        CHECK_FALSE(fs::exists(source));
    }
    SECTION("renaming a file to itself must preserve it") {
        CHECK_FALSE(rename_file(destination.string(), destination.string()));
        CHECK(read_fixture(destination) == "previous contents");
    }
    SECTION("a directory cannot replace an existing file") {
        fs::create_directory(source);
        write_fixture(source / "child.txt", "retained child");
        CHECK(bool(rename_file(source.string(), destination.string())));
        CHECK(read_fixture(destination) == "previous contents");
        CHECK(read_fixture(source / "child.txt") == "retained child");
    }
}

TEST_CASE("App settings remain dirty after a failed replacement and retry cleanly", "[Preset][Recovery][TinMan][AppConfig]")
{
    save_main_thread_id();
    TempPresetDir temp_dir;
    struct DataDirectoryRestore {
        std::string previous = data_dir();
        ~DataDirectoryRestore() { set_data_dir(previous); }
    } restore;
    set_data_dir(temp_dir.path.string());
    AppConfig config;
    config.set("recovery_test", "before");
    REQUIRE_NOTHROW(config.save());
    CHECK_FALSE(config.dirty());
    const fs::path destination(config.config_path());
    const fs::path backup = temp_dir.path / "before.conf";
    const std::string original = read_fixture(destination);
    REQUIRE_FALSE(original.empty());
    fs::rename(destination, backup);
    fs::create_directory(destination);
    write_fixture(destination / "blocker", "keep this fixture");

    config.set("recovery_test", "after");
    REQUIRE_NOTHROW(config.save());
    CHECK(config.dirty());
    CHECK(read_fixture(backup) == original);
    CHECK(read_fixture(destination / "blocker") == "keep this fixture");

    fs::remove_all(destination);
    fs::rename(backup, destination);
    REQUIRE_NOTHROW(config.save());
    CHECK_FALSE(config.dirty());
    AppConfig reloaded;
    CHECK(reloaded.load().empty());
    CHECK(reloaded.get("recovery_test") == "after");
}

TEST_CASE("Preset serialization failure leaves the last file intact", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    const fs::path file = temp_dir.path / "saved.json";
    const std::string original = "{\"version\":\"1.0.0\"}\n";
    write_fixture(file, original);
    DynamicPrintConfig config;
    config.set_key_value("notes", new ConfigOptionString(std::string(1, char(0xff))));
    REQUIRE_THROWS(config.save_to_json(file.string(), "Saved", "User", "1.0.0"));
    CHECK(read_fixture(file) == original);
}

TEST_CASE("Failed preset save keeps the selected profile and unsaved edits", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    const fs::path file = temp_dir.path / PRESET_PRINT_NAME / "Existing.json";
    auto config = bundle.prints.default_preset().config;
    write_print_preset(config, file, "Existing");
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    bundle.prints.load_preset(file.string(), "Existing", config, true);
    const auto before = bundle.prints.get_selected_preset().config;
    const auto count = bundle.prints.size();
    const std::string bytes = read_fixture(file);
    auto &edited = bundle.prints.get_edited_preset();
    edited.config.set_key_value("notes", new ConfigOptionString(std::string(1, char(0xff))));
    edited.is_dirty = true;
    const auto draft = edited.config;
    const std::string name = GENERATE(std::string("Existing"), std::string("New"));
    REQUIRE_THROWS(bundle.prints.save_current_preset(name, false, false, nullptr));
    CHECK(bundle.prints.size() == count);
    CHECK(bundle.prints.get_selected_preset_name() == "Existing");
    CHECK(bundle.prints.get_selected_preset().config == before);
    CHECK(bundle.prints.get_edited_preset().config == draft);
    CHECK(bundle.prints.current_is_dirty());
    CHECK(read_fixture(file) == bytes);
}

TEST_CASE("A failed child preset reload preserves its tuned configuration", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    Preset parent = bundle.prints.default_preset();
    parent.config.set_key_value("layer_height", new ConfigOptionFloat(0.3));
    Preset child(Preset::TYPE_PRINT, "Child", false);
    child.config = parent.config;
    child.config.set_key_value("layer_height", new ConfigOptionFloat(0.15));
    child.file = (temp_dir.path / "Child.json").string();
    write_fixture(child.file, "{broken json");
    const auto before = child.config;
    REQUIRE_NOTHROW(child.reload(parent));
    CHECK(child.config == before);
    CHECK(read_fixture(child.file) == "{broken json");
}

TEST_CASE("Checked configuration replacement preserves files and cleans temporary writes", "[utils][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    const fs::path file = temp_dir.path / fs::path("profile-\xc3\xa9.json");
    const std::string contents("binary\0and UTF-8 \xc3\xa9\n", 20);
    REQUIRE_NOTHROW(write_file_with_replace(file.string(), contents));
    CHECK(read_fixture(file) == contents);
    REQUIRE_NOTHROW(write_file_with_replace(file.string(), "replacement\n"));
    CHECK(read_fixture(file) == "replacement\n");

    const fs::path directory = temp_dir.path / "directory.json";
    fs::create_directory(directory);
    write_fixture(directory / "keep", "untouched");
    REQUIRE_THROWS(write_file_with_replace(directory.string(), "cannot replace directory"));
    CHECK(read_fixture(directory / "keep") == "untouched");
    REQUIRE_THROWS(write_file_with_replace((temp_dir.path / "missing" / "profile.json").string(), "missing parent"));
    for (const auto &entry : fs::directory_iterator(temp_dir.path))
        CHECK(entry.path().filename().string().find(".tinman-save-") != 0);
}

TEST_CASE("Preset save commits only after persistence and retains identity", "[Preset][SaveRecovery][TinMan]")
{
    const auto type = GENERATE(Preset::TYPE_PRINT, Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER);
    const bool new_preset = GENERATE(false, true);
    const bool detach = GENERATE(false, true);
    TempPresetDir temp_dir;
    PresetBundle bundle;
    PresetCollection &presets = type == Preset::TYPE_PRINT ? bundle.prints :
        type == Preset::TYPE_FILAMENT ? bundle.filaments : bundle.printers;
    const std::string section = type == Preset::TYPE_PRINT ? PRESET_PRINT_NAME :
        type == Preset::TYPE_FILAMENT ? PRESET_FILAMENT_NAME : PRESET_PRINTER_NAME;
    presets.update_user_presets_directory(temp_dir.path.string(), section);
    auto config = presets.default_preset().config;
    config.option<ConfigOptionString>("inherits", true)->value.clear();
    const fs::path file = temp_dir.path / section / "Existing.json";
    auto &stored = presets.load_preset(file.string(), "Existing", config, true);
    stored.setting_id = "local-fixture-id";
    stored.save(nullptr);
    presets.select_preset_by_name("Existing", true);
    const std::string key = type == Preset::TYPE_PRINT ? "notes" : type == Preset::TYPE_FILAMENT ? "filament_notes" : "printer_notes";
    auto &draft = presets.get_edited_preset();
    REQUIRE_NOTHROW(draft.config.set_deserialize_strict(key, "a tuned value"));
    const auto expected_value = draft.config.opt_serialize(key);
    draft.is_dirty = true;
    const std::string name = new_preset ? "Saved copy" : "Existing";
    REQUIRE(presets.save_current_preset(name, detach));
    const auto &saved = presets.get_selected_preset();
    CHECK(saved.name == name);
    CHECK(saved.config.opt_serialize(key) == expected_value);
    CHECK(presets.get_edited_preset().config == saved.config);
    CHECK_FALSE(presets.current_is_dirty());
    CHECK(saved.is_visible);
    CHECK(saved.is_user());
    CHECK(saved.setting_id == (new_preset ? "" : "local-fixture-id"));
    CHECK(saved.inherits() == (new_preset && !detach ? "Existing" : ""));
    if (new_preset && !detach)
        CHECK(saved.base_id == "local-fixture-id");
    CHECK(fs::is_regular_file(saved.file));
    fs::path info(saved.file);
    info.replace_extension(".info");
    CHECK(fs::is_regular_file(info));
    DynamicPrintConfig reloaded;
    std::map<std::string, std::string> metadata;
    std::string reason;
    REQUIRE_NOTHROW(reloaded.load_from_json(saved.file, ForwardCompatibilitySubstitutionRule::Disable, metadata, reason));
    CHECK(reason.empty());
    CHECK(reloaded.opt_serialize(key) == expected_value);
    if (type == Preset::TYPE_FILAMENT)
        CHECK(saved.config.option<ConfigOptionStrings>("filament_settings_id")->values.front() == name);
    else
        CHECK(saved.config.opt_string(type == Preset::TYPE_PRINT ? "print_settings_id" : "printer_settings_id") == name);
}

TEST_CASE("Project embedded saves do not require writable preset files", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    bundle.prints.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    bundle.prints.get_edited_preset().is_dirty = true;
    REQUIRE(bundle.prints.save_current_preset("Project profile", false, true));
    const auto &saved = bundle.prints.get_selected_preset();
    CHECK(saved.is_project_embedded);
    CHECK(saved.config.opt_float("layer_height") == Catch::Approx(0.17));
    CHECK_FALSE(fs::exists(saved.file));
    CHECK_FALSE(bundle.prints.current_is_dirty());
}

TEST_CASE("Partial preset saves preserve every draft option on failure", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    const fs::path file = temp_dir.path / PRESET_PRINT_NAME / "Existing.json";
    bundle.prints.load_preset(file.string(), "Existing", bundle.prints.default_preset().config, true);
    auto &draft = bundle.prints.get_edited_preset();
    draft.config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    draft.config.set_key_value("notes", new ConfigOptionString(std::string(1, char(0xff))));
    draft.is_dirty = true;
    const auto before = draft.config;
    REQUIRE_THROWS(bundle.save_changes_for_preset("Copy", Preset::TYPE_PRINT, {"layer_height"}, false));
    CHECK(bundle.prints.get_edited_preset().config == before);
    CHECK(bundle.prints.current_is_dirty());
    CHECK(bundle.prints.get_selected_preset_name() == "Existing");
    CHECK(bundle.prints.find_preset("Copy", false, true) == nullptr);
}

TEST_CASE("Failed sidecar save is reported without publishing a preset", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    const fs::path file = temp_dir.path / PRESET_PRINT_NAME / "Existing.json";
    auto &stored = bundle.prints.load_preset(file.string(), "Existing", bundle.prints.default_preset().config, true);
    stored.save(nullptr);
    const auto previous = stored.config;
    fs::path info = file;
    info.replace_extension(".info");
    fs::remove(info);
    fs::create_directory(info);
    write_fixture(info / "keep", "metadata blocker");
    auto &draft = bundle.prints.get_edited_preset();
    draft.config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
    draft.is_dirty = true;
    REQUIRE_THROWS(bundle.prints.save_current_preset("Existing"));
    CHECK(bundle.prints.get_selected_preset().config == previous);
    CHECK(bundle.prints.current_is_dirty());
    CHECK(bundle.prints.get_edited_preset().config.opt_float("layer_height") == Catch::Approx(0.17));
    CHECK(read_fixture(info / "keep") == "metadata blocker");
    fs::remove_all(info);
    REQUIRE(bundle.prints.save_current_preset("Existing"));
    CHECK_FALSE(bundle.prints.current_is_dirty());
    CHECK(fs::is_regular_file(info));
}

TEST_CASE("Synchronized presets retry local persistence after a failure", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    auto &stored = add_inmemory_preset(bundle.prints, "Pending");
    stored.sync_info = "save";
    const fs::path base = temp_dir.path / PRESET_PRINT_NAME / "base";
    write_fixture(base, "directory blocker");
    std::map<std::string, std::string> pending_deletions;
    REQUIRE_NOTHROW(bundle.prints.save_user_presets(temp_dir.path.string(), PRESET_PRINT_NAME, pending_deletions));
    CHECK(bundle.prints.find_preset("Pending", false, true)->sync_info == "save");
    CHECK(read_fixture(base) == "directory blocker");
    fs::remove(base);
    REQUIRE_NOTHROW(bundle.prints.save_user_presets(temp_dir.path.string(), PRESET_PRINT_NAME, pending_deletions));
    const auto *saved = bundle.prints.find_preset("Pending", false, true);
    CHECK(saved->sync_info.empty());
    CHECK(fs::is_regular_file(saved->file));
}

TEST_CASE("Saving a parent reloads valid child overrides", "[Preset][SaveRecovery][TinMan]")
{
    TempPresetDir temp_dir;
    PresetBundle bundle;
    bundle.prints.update_user_presets_directory(temp_dir.path.string(), PRESET_PRINT_NAME);
    const fs::path parent_file = temp_dir.path / PRESET_PRINT_NAME / "Parent.json";
    const fs::path child_file = temp_dir.path / PRESET_PRINT_NAME / "Child.json";
    auto parent_config = bundle.prints.default_preset().config;
    auto &parent = bundle.prints.load_preset(parent_file.string(), "Parent", parent_config, true);
    parent.save(nullptr);
    auto child_config = parent_config;
    child_config.option<ConfigOptionString>("inherits", true)->value = "Parent";
    child_config.set_key_value("layer_height", new ConfigOptionFloat(0.15));
    auto &child = bundle.prints.load_preset(child_file.string(), "Child", child_config, false);
    child.save(&parent_config);
    bundle.prints.select_preset_by_name("Parent", true);
    bundle.prints.get_edited_preset().config.set_key_value("notes", new ConfigOptionString("updated parent"));
    bundle.prints.get_edited_preset().config.set_key_value("layer_height", new ConfigOptionFloat(0.3));
    REQUIRE(bundle.prints.save_current_preset("Parent"));
    const auto *reloaded = bundle.prints.find_preset("Child", false, true);
    CHECK(reloaded->config.opt_float("layer_height") == Catch::Approx(0.15));
    CHECK(reloaded->config.opt_string("notes") == "updated parent");
}

TEST_CASE("Read-only preset identities are not overwritten", "[Preset][SaveRecovery][TinMan]")
{
    PresetBundle bundle;
    const auto before = bundle.prints.get_selected_preset();
    bundle.prints.get_edited_preset().config.set_key_value("notes", new ConfigOptionString("unsaved"));
    bundle.prints.get_edited_preset().is_dirty = true;
    CHECK_FALSE(bundle.prints.save_current_preset(before.name));
    CHECK(bundle.prints.get_selected_preset().config == before.config);
    CHECK(bundle.prints.current_is_dirty());
    CHECK(bundle.prints.get_edited_preset().config.opt_string("notes") == "unsaved");
}

TEST_CASE("Legacy bundle import without bundle metadata stays in the user preset directory", "[Preset][Identity]")
{
    TempPresetDir temp_dir;
    PresetBundle  bundle;

    PresetsConfigSubstitutions substitutions;
    std::vector<std::string>   result;
    int                        overwrite = 0;
    std::string                file      = (temp_dir.path / "legacy-bundle" / "Imported.json").string();
    const fs::path             user_root = temp_dir.path / "user";

    write_print_preset(bundle.prints.default_preset().config, file, "Imported");
    fs::create_directories(user_root);
    bundle.prints.update_user_presets_directory(user_root.string(), PRESET_PRINT_NAME);

    REQUIRE(bundle.import_json_presets(
        substitutions,
        file,
        [](std::string const &) { return 1; },
        ForwardCompatibilitySubstitutionRule::Disable,
        overwrite,
        result));

    const Preset *imported = bundle.prints.find_preset("Imported");
    REQUIRE(imported != nullptr);
    CHECK(imported->name == "Imported");
    CHECK(imported->bundle_id.empty());
    CHECK_FALSE(imported->is_from_bundle());
    // Detached user presets (no inherits) are saved in the "base" subfolder of the user preset root.
    CHECK(fs::equivalent(fs::path(imported->file).parent_path().parent_path(), user_root / PRESET_PRINT_NAME));
}

TEST_CASE("Current vendor type tolerates missing printer model", "[Preset][Bundle]")
{
    PresetBundle bundle;

    VendorProfile orca_vendor("ORCA");
    VendorProfile::PrinterModel model;
    model.name = "Orca Test";
    orca_vendor.models.emplace_back(model);
    bundle.vendors.emplace("ORCA", std::move(orca_vendor));

    bundle.printers.get_edited_preset().config.erase("printer_model");

    CHECK(bundle.get_current_vendor_type() == VendorType::Unknown);
}

TEST_CASE("Printer extruder count tolerates missing nozzle diameter", "[Preset][Bundle]")
{
    PresetBundle bundle;
    DynamicPrintConfig& config = bundle.printers.get_edited_preset().config;

    config.erase("nozzle_diameter");
    CHECK(bundle.get_printer_extruder_count() == 1);

    config.set_key_value("nozzle_diameter", new ConfigOptionFloats());
    CHECK(bundle.get_printer_extruder_count() == 1);

    config.set_key_value("nozzle_diameter", new ConfigOptionFloats({ 0.4, 0.6 }));
    CHECK(bundle.get_printer_extruder_count() == 2);
}

TEST_CASE("Full FFF projection repairs missing materials and invalid tool routes", "[Preset][MultiTool]")
{
    PresetBundle bundle;
    DynamicPrintConfig &printer = bundle.printers.get_edited_preset().config;
    printer.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.4, 0.4, 0.6}));
    printer.set_key_value("single_extruder_multi_material", new ConfigOptionBool(false));
    printer.set_num_extruders(4);

    const std::string fallback_name = bundle.filaments.get_edited_preset().name;
    bundle.filament_presets = {fallback_name, "Removed Filament"};
    bundle.project_config.option<ConfigOptionInts>("filament_map")->values = {4, 9};

    const DynamicPrintConfig full = bundle.full_config(false);
    CHECK((full.option<ConfigOptionStrings>("filament_settings_id")->values ==
           std::vector<std::string>{fallback_name, fallback_name}));
    CHECK((full.option<ConfigOptionInts>("filament_map")->values == std::vector<int>{4, 1}));
    CHECK(full.option<ConfigOptionFloats>("nozzle_diameter")->values.size() == 4);
    CHECK(full.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values.size() == 4);
}

TEST_CASE("Physical printer selection tolerates empty and stale preset lists", "[Preset][PhysicalPrinter]")
{
    PresetBundle bundle;
    add_inmemory_preset(bundle.printers, "Machine A");
    add_inmemory_preset(bundle.printers, "Machine B");

    bundle.physical_printers.load_printer(
        std::string(), "Empty", physical_printer_config(bundle, {}), false);
    bundle.physical_printers.select_printer("Empty");
    CHECK_FALSE(bundle.physical_printers.has_selection());

    bundle.physical_printers.load_printer(
        std::string(), "Stale", physical_printer_config(bundle, {"Removed Machine"}), false);
    bundle.physical_printers.select_printer("Stale");
    CHECK_FALSE(bundle.physical_printers.has_selection());

    bundle.physical_printers.load_printer(
        std::string(), "Workshop", physical_printer_config(bundle, {"Machine A", "Machine B"}), false);
    bundle.physical_printers.select_printer("Workshop * Missing Machine");
    REQUIRE(bundle.physical_printers.has_selection());
    CHECK(bundle.physical_printers.get_selected_printer_name() == "Workshop");
    CHECK(bundle.physical_printers.get_selected_printer_preset_name() == "Machine A");

    bundle.physical_printers.select_printer("Unknown Printer");
    CHECK_FALSE(bundle.physical_printers.has_selection());
}

TEST_CASE("Physical printer reload and deletion preserve collection identity", "[Preset][PhysicalPrinter]")
{
    PresetBundle bundle;
    add_inmemory_preset(bundle.printers, "Machine A");
    add_inmemory_preset(bundle.printers, "Machine B");

    bundle.physical_printers.load_printer(
        std::string(), "Alpha", physical_printer_config(bundle, {"Machine A"}), false);
    bundle.physical_printers.load_printer(
        std::string(), "Charlie", physical_printer_config(bundle, {"Machine A"}), false);
    bundle.physical_printers.load_printer(
        std::string(), "alpha", physical_printer_config(bundle, {"Machine B"}), false);

    bundle.physical_printers.select_printer("Charlie * Machine A");
    bundle.physical_printers.load_printer(
        std::string(), "Bravo", physical_printer_config(bundle, {"Machine A"}), false);

    CHECK(std::distance(bundle.physical_printers.begin(), bundle.physical_printers.end()) == 3);
    CHECK(std::next(bundle.physical_printers.begin())->name == "Bravo");
    const PhysicalPrinter *alpha = bundle.physical_printers.find_printer("Alpha", false);
    REQUIRE(alpha != nullptr);
    CHECK(alpha->get_preset_names() == std::set<std::string>{"Machine B"});

    REQUIRE(bundle.physical_printers.has_selection());
    CHECK(bundle.physical_printers.get_selected_printer_name() == "Charlie");
    CHECK_FALSE(bundle.physical_printers.delete_printer("Beta"));
    CHECK(bundle.physical_printers.find_printer("Charlie") != nullptr);

    REQUIRE(bundle.physical_printers.delete_printer("Alpha"));
    REQUIRE(bundle.physical_printers.has_selection());
    CHECK(bundle.physical_printers.get_selected_printer_name() == "Charlie");
}

TEST_CASE("find_preset resolves a system preset's renamed_from", "[Preset][Rename]")
{
    RenameTestCollection coll;

    // "New Process" is the current preset; it was renamed from "Old Process".
    add_inmemory_preset(coll, "New Process");
    set_renamed_from(coll, "New Process", { "Old Process" });
    coll.update_map_system_profile_renamed();

    // The rename map knows the old name...
    const std::string *renamed = coll.get_preset_name_renamed("Old Process");
    REQUIRE(renamed != nullptr);
    CHECK(*renamed == "New Process");

    // ...and plain find_preset() now follows it (the core of this PR; previously this
    // resolution lived only in find_preset2 and a few call sites).
    const Preset *resolved = coll.find_preset("Old Process");
    REQUIRE(resolved != nullptr);
    CHECK(resolved->name == "New Process");

    // A genuinely unknown name still returns null (no spurious match).
    CHECK(coll.find_preset("Totally Unknown") == nullptr);

    // A child that still inherits the OLD name resolves through the runtime walker,
    // which uses plain find_preset().
    Preset       &child  = add_inmemory_preset(coll, "Child Process", "Old Process");
    const Preset *parent = coll.get_preset_parent(child);
    REQUIRE(parent != nullptr);
    CHECK(parent->name == "New Process");
}

TEST_CASE("find_preset resolves a preset renamed more than once", "[Preset][Rename]")
{
    RenameTestCollection coll;

    // "New Process" was renamed twice, so it carries both former names in renamed_from.
    add_inmemory_preset(coll, "New Process");
    set_renamed_from(coll, "New Process", { "Original Process", "Old Process" });
    coll.update_map_system_profile_renamed();

    // Each historical name resolves to the current preset.
    for (const char *old_name : { "Original Process", "Old Process" }) {
        INFO("resolving old name: " << old_name);
        const std::string *renamed = coll.get_preset_name_renamed(old_name);
        REQUIRE(renamed != nullptr);
        CHECK(*renamed == "New Process");

        const Preset *resolved = coll.find_preset(old_name);
        REQUIRE(resolved != nullptr);
        CHECK(resolved->name == "New Process");
    }

    // A child inheriting either former name resolves through the runtime walker.
    Preset &child = add_inmemory_preset(coll, "Child Process", "Original Process");
    REQUIRE(coll.get_preset_parent(child) != nullptr);
    CHECK(coll.get_preset_parent(child)->name == "New Process");
}

TEST_CASE("find_preset2 auto-matches removed Generic vendor profiles to the library", "[Preset][Rename]")
{
    PresetBundle bundle;

    // The OrcaFilamentLibrary replacement that removed empty "<vendor> Generic" profiles map to.
    add_inmemory_preset(bundle.filaments, "Generic PLA @System");

    // Plain lookups do NOT fuzzy-match a removed vendor profile.
    CHECK(bundle.filaments.find_preset("Voron Generic PLA") == nullptr);
    CHECK(bundle.filaments.find_preset2("Voron Generic PLA", /*auto_match=*/false) == nullptr);

    // With auto_match, the removed "Voron Generic PLA" resolves to "Generic PLA @System".
    const Preset *matched = bundle.filaments.find_preset2("Voron Generic PLA", /*auto_match=*/true);
    REQUIRE(matched != nullptr);
    CHECK(matched->name == "Generic PLA @System");

    // No library preset exists for an unrelated material => still no match.
    CHECK(bundle.filaments.find_preset2("BrandX Generic PETG", /*auto_match=*/true) == nullptr);
}

TEST_CASE("Renamed parent is normalized into a loaded preset's inherits", "[Preset][Rename]")
{
    TempPresetDir        temp_dir;
    RenameTestCollection coll;

    // Current parent, renamed from "Old Process".
    add_inmemory_preset(coll, "New Process");
    set_renamed_from(coll, "New Process", { "Old Process" });
    coll.update_map_system_profile_renamed();

    // A user preset on disk that still inherits the OLD name.
    write_preset_with_inherits(coll.default_preset().config,
                               temp_dir.path / PRESET_PRINT_NAME / "Child.json", "Child", "Old Process");

    PresetsConfigSubstitutions substitutions;
    coll.load_presets(temp_dir.path.string(), PRESET_PRINT_NAME, substitutions,
                      ForwardCompatibilitySubstitutionRule::Disable);

    const Preset *child = coll.find_preset("Child");
    REQUIRE(child != nullptr);
    // The dangling "Old Process" was rewritten to the resolved parent name at load time,
    // so the runtime walker (plain find_preset) can resolve the chain.
    CHECK(child->inherits() == "New Process");
    REQUIRE(coll.get_preset_parent(*child) != nullptr);
    CHECK(coll.get_preset_parent(*child)->name == "New Process");
}

TEST_CASE("Removed Generic parent is normalized into a loaded filament's inherits", "[Preset][Rename]")
{
    TempPresetDir temp_dir;
    PresetBundle  bundle;

    add_inmemory_preset(bundle.filaments, "Generic PLA @System");

    // A user filament that still inherits a removed "<vendor> Generic PLA" profile.
    write_preset_with_inherits(bundle.filaments.default_preset().config,
                               temp_dir.path / PRESET_FILAMENT_NAME / "MyPLA.json", "MyPLA", "Voron Generic PLA");

    PresetsConfigSubstitutions substitutions;
    bundle.filaments.load_presets(temp_dir.path.string(), PRESET_FILAMENT_NAME, substitutions,
                                  ForwardCompatibilitySubstitutionRule::Disable);

    const Preset *child = bundle.filaments.find_preset("MyPLA");
    REQUIRE(child != nullptr);
    CHECK(child->inherits() == "Generic PLA @System");
    REQUIRE(bundle.filaments.get_preset_parent(*child) != nullptr);
    CHECK(bundle.filaments.get_preset_parent(*child)->name == "Generic PLA @System");
}

namespace {

// A live reference to a preset's compatible_printers / compatible_prints list. Fetches the *stored*
// preset (real=true) so writes and reads hit the same object; creates the option if absent.
std::vector<std::string> &compatible_list(PresetCollection &coll, const std::string &preset_name, const char *field_key)
{
    Preset *preset = coll.find_preset(preset_name, /*first_visible_if_not_found=*/false, /*real=*/true);
    REQUIRE(preset != nullptr);
    return preset->config.option<ConfigOptionStrings>(field_key, true)->values;
}

} // namespace

TEST_CASE("Renamed printer/process names are normalized into compatible lists on load", "[Preset][Rename]")
{
    PresetBundle bundle;

    // Current printer + process, each renamed from an older name.
    add_inmemory_preset(bundle.printers, "New Printer");
    set_renamed_from(bundle.printers, "New Printer", { "Old Printer" });
    add_inmemory_preset(bundle.prints, "New Process");
    set_renamed_from(bundle.prints, "New Process", { "Old Process" });

    // A user process still compatible with the OLD printer name.
    add_inmemory_preset(bundle.prints, "My Process");
    compatible_list(bundle.prints, "My Process", "compatible_printers") = { "Old Printer" };

    // A user filament referencing the OLD printer AND OLD process names, plus an unknown printer.
    add_inmemory_preset(bundle.filaments, "My Filament");
    compatible_list(bundle.filaments, "My Filament", "compatible_printers") = { "Old Printer", "Unknown Printer" };
    compatible_list(bundle.filaments, "My Filament", "compatible_prints")   = { "Old Process" };

    // Build the rename maps (done during system load in the real pipeline), then normalize.
    AppConfig app_config;
    bundle.load_installed_printers(app_config); // rebuilds every collection's rename map
    bundle.normalize_compatible_presets();

    // The stale printer name in a process' compatible_printers is rewritten to the current name.
    CHECK(compatible_list(bundle.prints, "My Process", "compatible_printers") == std::vector<std::string>{ "New Printer" });

    // The stale process name in a filament's compatible_prints is rewritten (this field has no
    // runtime rename fallback, so load-time normalization is the only fix).
    CHECK(compatible_list(bundle.filaments, "My Filament", "compatible_prints") == std::vector<std::string>{ "New Process" });

    // The renamed printer is rewritten while the unknown/deleted name is preserved as-is.
    CHECK(compatible_list(bundle.filaments, "My Filament", "compatible_printers") ==
          (std::vector<std::string>{ "New Printer", "Unknown Printer" }));

    // Normalizing rewrites config in place without flagging the preset dirty.
    CHECK_FALSE(bundle.prints.find_preset("My Process", false, true)->is_dirty);

    // A system preset that already references the current name is left untouched (idempotent no-op).
    bundle.normalize_compatible_presets();
    CHECK(compatible_list(bundle.prints, "My Process", "compatible_printers") == std::vector<std::string>{ "New Printer" });
}

TEST_CASE("Renamed names are normalized into a SYSTEM preset's compatible lists", "[Preset][Rename]")
{
    PresetBundle bundle;

    // Current printer + process, each renamed from an older name.
    add_inmemory_preset(bundle.printers, "New Printer");
    set_renamed_from(bundle.printers, "New Printer", { "Old Printer" });
    add_inmemory_preset(bundle.prints, "New Process");
    set_renamed_from(bundle.prints, "New Process", { "Old Process" });

    // A *system* (vendor) filament whose own compatible lists still reference the OLD names. A vendor
    // profile can point at a sibling preset that was later renamed, so system presets must be
    // normalized too (they are skipped by neither collection walk).
    add_inmemory_preset(bundle.filaments, "System Filament").is_system = true;
    compatible_list(bundle.filaments, "System Filament", "compatible_printers") = { "Old Printer" };
    compatible_list(bundle.filaments, "System Filament", "compatible_prints")   = { "Old Process" };

    AppConfig app_config;
    bundle.load_installed_printers(app_config); // build the rename maps
    bundle.normalize_compatible_presets();

    // The stale references in the system preset are rewritten to the current names.
    CHECK(compatible_list(bundle.filaments, "System Filament", "compatible_printers") ==
          std::vector<std::string>{ "New Printer" });
    CHECK(compatible_list(bundle.filaments, "System Filament", "compatible_prints") ==
          std::vector<std::string>{ "New Process" });

    // The rewrite does not flag the system preset dirty, and is idempotent.
    CHECK_FALSE(bundle.filaments.find_preset("System Filament", false, true)->is_dirty);
    bundle.normalize_compatible_presets();
    CHECK(compatible_list(bundle.filaments, "System Filament", "compatible_printers") ==
          std::vector<std::string>{ "New Printer" });
}

TEST_CASE("compatible_prints on SLA materials resolves against sla_prints, not prints", "[Preset][Rename]")
{
    PresetBundle bundle;

    // A renamed SLA process, and a same-named FFF process that must NOT be picked up: resolving the
    // SLA material's compatible_prints against `prints` would wrongly rewrite to "Wrong FFF Process".
    add_inmemory_preset(bundle.sla_prints, "New SLA Process");
    set_renamed_from(bundle.sla_prints, "New SLA Process", { "Old SLA Process" });
    add_inmemory_preset(bundle.prints, "Wrong FFF Process");
    set_renamed_from(bundle.prints, "Wrong FFF Process", { "Old SLA Process" });

    add_inmemory_preset(bundle.sla_materials, "My SLA Material");
    compatible_list(bundle.sla_materials, "My SLA Material", "compatible_prints") = { "Old SLA Process" };

    AppConfig app_config;
    bundle.load_installed_printers(app_config);
    bundle.normalize_compatible_presets();

    CHECK(compatible_list(bundle.sla_materials, "My SLA Material", "compatible_prints") ==
          std::vector<std::string>{ "New SLA Process" });
}

TEST_CASE("Profile validator flags dangling and renamed preset references", "[Preset][Validate]")
{
    PresetBundle bundle;

    // Current printers: a real one, and a renamed one (its old name resolves via renamed_from).
    add_inmemory_preset(bundle.printers, "Real Printer");
    add_inmemory_preset(bundle.printers, "New Printer");
    set_renamed_from(bundle.printers, "New Printer", { "Old Printer" });

    // A real process, referenced from a filament's compatible_prints.
    add_inmemory_preset(bundle.prints, "Real Process").is_system = true;

    // A fully valid system filament: references only current names.
    add_inmemory_preset(bundle.filaments, "Good Filament").is_system = true;
    compatible_list(bundle.filaments, "Good Filament", "compatible_printers") = { "Real Printer" };
    compatible_list(bundle.filaments, "Good Filament", "compatible_prints")   = { "Real Process" };

    AppConfig app_config;
    bundle.load_installed_printers(app_config); // build the rename maps

    // With only valid references, the validator is clean.
    CHECK_FALSE(bundle.check_preset_references());

    SECTION("deleted compatible_printers is flagged") {
        add_inmemory_preset(bundle.filaments, "Ghost Ref Filament").is_system = true;
        compatible_list(bundle.filaments, "Ghost Ref Filament", "compatible_printers") = { "Ghost Printer" };
        CHECK(bundle.check_preset_references());
    }

    SECTION("renamed compatible_printers (old name) is flagged") {
        add_inmemory_preset(bundle.filaments, "Old Ref Filament").is_system = true;
        compatible_list(bundle.filaments, "Old Ref Filament", "compatible_printers") = { "Old Printer" };
        CHECK(bundle.check_preset_references());
    }

    SECTION("deleted compatible_prints is flagged") {
        add_inmemory_preset(bundle.filaments, "Bad Process Ref").is_system = true;
        compatible_list(bundle.filaments, "Bad Process Ref", "compatible_prints") = { "Ghost Process" };
        CHECK(bundle.check_preset_references());
    }

    SECTION("deleted inherits parent is flagged") {
        add_inmemory_preset(bundle.filaments, "Orphan Filament", "Ghost Parent").is_system = true;
        CHECK(bundle.check_preset_references());
    }

    SECTION("non-system preset with a dangling reference is ignored") {
        add_inmemory_preset(bundle.filaments, "User Filament"); // is_system stays false
        compatible_list(bundle.filaments, "User Filament", "compatible_printers") = { "Ghost Printer" };
        CHECK_FALSE(bundle.check_preset_references());
    }
}
