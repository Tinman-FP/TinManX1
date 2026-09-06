#include <catch2/catch_all.hpp>

#include <memory>
#include <boost/filesystem.hpp>

#include "libslic3r/Format/bbs_3mf.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/TinManMachineProfileContract.hpp"
#include "libslic3r/TriangleMesh.hpp"

using namespace Slic3r;
using Catch::Approx;

namespace {

PresetCollection &collection_for(PresetBundle &bundle, Preset::Type type)
{
    if (type == Preset::TYPE_FILAMENT) return bundle.filaments;
    if (type == Preset::TYPE_PRINTER) return bundle.printers;
    return bundle.prints;
}

std::string tuning_key(Preset::Type type)
{
    if (type == Preset::TYPE_FILAMENT) return "nozzle_temperature";
    if (type == Preset::TYPE_PRINTER) return "nozzle_diameter";
    return "layer_height";
}

void tune(DynamicPrintConfig &config, Preset::Type type)
{
    if (type == Preset::TYPE_FILAMENT)
        config.set_key_value("nozzle_temperature", new ConfigOptionInts{245});
    else if (type == Preset::TYPE_PRINTER)
        config.set_key_value("nozzle_diameter", new ConfigOptionFloats{0.6});
    else
        config.set_key_value("layer_height", new ConfigOptionFloat(0.17));
}

Preset embedded(PresetCollection &collection, Preset::Type type, const std::string &name,
                const std::string &parent = {})
{
    Preset preset(type, name, false);
    preset.config = collection.default_preset().config;
    preset.config.set_key_value("inherits", new ConfigOptionString(parent));
    if (type == Preset::TYPE_FILAMENT)
        preset.config.set_key_value("filament_settings_id", new ConfigOptionStrings{name});
    else
        preset.config.set_key_value(type == Preset::TYPE_PRINTER ? "printer_settings_id" : "print_settings_id",
                                    new ConfigOptionString(name));
    preset.is_project_embedded = true;
    preset.is_external = true;
    preset.version = Semver(1, 0, 0);
    tune(preset.config, type);
    return preset;
}

void load(PresetCollection &collection, Preset::Type type, std::vector<Preset *> inputs)
{
    PresetsConfigSubstitutions substitutions;
    collection.load_project_embedded_presets(inputs, Preset::get_type_string(type), substitutions,
                                            ForwardCompatibilitySubstitutionRule::Disable);
}

} // namespace

TEST_CASE("Standalone project profiles retain tuned values on export and reload", "[Preset][ProjectRecovery][TinMan]")
{
    const auto type = GENERATE(Preset::TYPE_PRINT, Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER);
    PresetBundle bundle;
    auto &collection = collection_for(bundle, type);
    Preset source = embedded(collection, type, "Standalone project profile");
    const DynamicPrintConfig before = source.config;
    std::unique_ptr<Preset> exported(collection.get_preset_differed_for_save(source));
    CHECK(source.config == before);
    REQUIRE(exported != nullptr);
    CHECK(exported->config.option(tuning_key(type))->serialize() == before.option(tuning_key(type))->serialize());
    load(collection, type, {exported.get()});
    const auto *loaded = collection.find_preset(source.name, false);
    REQUIRE(loaded != nullptr);
    CHECK(loaded->config.option(tuning_key(type))->serialize() == before.option(tuning_key(type))->serialize());
    CHECK(loaded->is_project_embedded);
}

TEST_CASE("Loading project profiles preserves selected identity and unsaved editor values", "[Preset][ProjectRecovery][TinMan]")
{
    const auto type = GENERATE(Preset::TYPE_PRINT, Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER);
    PresetBundle bundle;
    auto &collection = collection_for(bundle, type);
    collection.load_preset({}, "Z selected profile", collection.default_preset().config, true);
    tune(collection.get_edited_preset().config, type);
    const auto editor_before = collection.get_edited_preset().config;
    Preset source = embedded(collection, type, "A embedded profile", "Z selected profile");
    const auto source_before = source.config;
    load(collection, type, {&source});
    REQUIRE(collection.find_preset(source.name, false) != nullptr);
    CHECK(collection.get_selected_preset_name() == "Z selected profile");
    CHECK(collection.get_edited_preset().name == "Z selected profile");
    CHECK(collection.get_edited_preset().config == editor_before);
    CHECK(source.config == source_before);
}

TEST_CASE("Project inheritance resolves independently of archive entry order", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    auto &collection = bundle.prints;
    Preset parent = embedded(collection, Preset::TYPE_PRINT, "Project root");
    parent.config.set_key_value("outer_wall_speed", new ConfigOptionFloat(44.0));
    Preset child = embedded(collection, Preset::TYPE_PRINT, "Project child", parent.name);
    child.config.clear();
    child.config.set_key_value("inherits", new ConfigOptionString(parent.name));
    child.config.set_key_value("layer_height", new ConfigOptionFloat(0.23));
    Preset grandchild = embedded(collection, Preset::TYPE_PRINT, "Project grandchild", child.name);
    grandchild.config.clear();
    grandchild.config.set_key_value("inherits", new ConfigOptionString(child.name));
    grandchild.config.set_key_value("inner_wall_speed", new ConfigOptionFloat(55.0));
    const auto child_before = child.config;
    const auto grandchild_before = grandchild.config;
    load(collection, Preset::TYPE_PRINT, {&grandchild, &child, &parent});
    const auto *result = collection.find_preset(grandchild.name, false);
    REQUIRE(result != nullptr);
    CHECK(result->config.opt_float("layer_height") == Approx(0.23));
    CHECK(result->config.opt_float("outer_wall_speed") == Approx(44.0));
    CHECK(result->config.opt_float("inner_wall_speed") == Approx(55.0));
    CHECK(child.config == child_before);
    CHECK(grandchild.config == grandchild_before);
}

TEST_CASE("Embedded printer exports do not carry local connection credentials", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    auto &collection = bundle.printers;
    collection.load_preset({}, "Saved printer base", collection.default_preset().config, false);
    Preset source = embedded(collection, Preset::TYPE_PRINTER, "Shareable printer", "Saved printer base");
    source.config.set_key_value("print_host", new ConfigOptionString("192.0.2.99"));
    source.config.set_key_value("printhost_apikey", new ConfigOptionString("generated-test-only-key"));
    source.config.set_key_value("printhost_password", new ConfigOptionString("generated-test-only-password"));
    const auto before = source.config;
    std::unique_ptr<Preset> exported(collection.get_preset_differed_for_save(source));
    REQUIRE(exported != nullptr);
    for (const auto &key : exported->config.keys())
        CHECK_FALSE(tinmanx_runtime_connection_option(key));
    CHECK(source.config == before);
    CHECK(exported->config.option("nozzle_diameter")->serialize() == before.option("nozzle_diameter")->serialize());
}

TEST_CASE("Unresolved project parents retain inputs and do not block healthy profiles", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    auto &collection = bundle.prints;
    Preset first = embedded(collection, Preset::TYPE_PRINT, "Cycle first", "Cycle second");
    Preset second = embedded(collection, Preset::TYPE_PRINT, "Cycle second", "Cycle first");
    Preset missing = embedded(collection, Preset::TYPE_PRINT, "Missing parent", "Not installed");
    Preset healthy = embedded(collection, Preset::TYPE_PRINT, "Healthy root");
    const auto before = first.config;
    REQUIRE_NOTHROW(load(collection, Preset::TYPE_PRINT, {&first, &second, &missing, &healthy}));
    CHECK(collection.find_preset(first.name, false) == nullptr);
    CHECK(collection.find_preset(second.name, false) == nullptr);
    CHECK(collection.find_preset(missing.name, false) == nullptr);
    CHECK(collection.find_preset(healthy.name, false) != nullptr);
    CHECK(first.config == before);
}

TEST_CASE("Project import diagnostics remain valid across copies and successful loads", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    Preset source = embedded(bundle.prints, Preset::TYPE_PRINT, "Imported with substitutions");
    auto diagnostics = std::make_shared<ConfigSubstitutions>();
    diagnostics->push_back({print_config_def.get("layer_height"), "future value",
                            ConfigOptionUniquePtr(new ConfigOptionFloat(0.17))});
    source.loading_substitutions = diagnostics;
    Preset copy = source;
    std::weak_ptr<const ConfigSubstitutions> lifetime = diagnostics;
    diagnostics.reset();
    PresetsConfigSubstitutions reports;
    std::vector<Preset *> inputs{&source};
    bundle.prints.load_project_embedded_presets(inputs, PRESET_PRINT_NAME, reports,
                                              ForwardCompatibilitySubstitutionRule::Enable);
    REQUIRE(reports.size() == 1);
    REQUIRE(reports.front().substitutions.size() == 1);
    CHECK(reports.front().substitutions.front().old_value == "future value");
    CHECK(reports.front().substitutions.front().new_value->serialize() == "0.17");
    REQUIRE(source.loading_substitutions != nullptr);
    CHECK(source.loading_substitutions->size() == 1);
    CHECK_FALSE(bundle.prints.find_preset(source.name, false)->loading_substitutions);
    source.loading_substitutions.reset();
    CHECK_FALSE(lifetime.expired());
    copy.loading_substitutions.reset();
    CHECK(lifetime.expired());
    CHECK(reports.front().substitutions.front().new_value->serialize() == "0.17");
}

TEST_CASE("Project import filters empty duplicate and unrelated records without mutation", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    auto &collection = bundle.prints;
    Preset good = embedded(collection, Preset::TYPE_PRINT, "Unique root");
    Preset duplicate = good;
    duplicate.config.set_key_value("layer_height", new ConfigOptionFloat(0.29));
    Preset empty = embedded(collection, Preset::TYPE_PRINT, "");
    Preset wrong_type = embedded(bundle.filaments, Preset::TYPE_FILAMENT, "Wrong type");
    const auto before = collection.size();
    REQUIRE_NOTHROW(load(collection, Preset::TYPE_PRINT, {nullptr, &good, &duplicate, &empty, &wrong_type}));
    CHECK(collection.size() == before + 1);
    CHECK(collection.find_preset(good.name, false)->config.opt_float("layer_height") == Approx(0.17));
    CHECK(duplicate.config.opt_float("layer_height") == Approx(0.29));
    CHECK(collection.find_preset(wrong_type.name, false) == nullptr);
}

TEST_CASE("Invalid project inheritance does not consume inputs or prevent retry", "[Preset][ProjectRecovery][TinMan]")
{
    PresetBundle bundle;
    Preset source = embedded(bundle.prints, Preset::TYPE_PRINT, "Repairable project profile");
    source.config.set_key_value("inherits", new ConfigOptionInt(12));
    const auto before = source.config;
    REQUIRE_THROWS_AS(load(bundle.prints, Preset::TYPE_PRINT, {&source}), Slic3r::RuntimeError);
    CHECK(source.config == before);
    CHECK(bundle.prints.find_preset(source.name, false) == nullptr);
    source.config.set_key_value("inherits", new ConfigOptionString());
    REQUIRE_NOTHROW(load(bundle.prints, Preset::TYPE_PRINT, {&source}));
    REQUIRE(bundle.prints.find_preset(source.name, false) != nullptr);
}

TEST_CASE("Portable project archives preserve mixed tools and profiles without local credentials", "[Preset][ProjectRecovery][TinMan][3MF][MultiTool]")
{
    const int empty_identity = GENERATE(0, 1, 2, 3);
    const int topology = GENERATE(0, 1, 2);
    CAPTURE(empty_identity, topology);
    const std::vector<double> nozzles = topology == 0 ? std::vector<double>{0.6, 0.4, 0.4, 0.6} :
                                        topology == 1 ? std::vector<double>{0.6, 0.8} :
                                                        std::vector<double>{0.4, 0.7};
    const unsigned tools = static_cast<unsigned>(nozzles.size());
    namespace fs = boost::filesystem;
    struct Files {
        fs::path root = fs::temp_directory_path() / fs::unique_path("tinman-project-%%%%-%%%%");
        Files() { fs::create_directories(root); }
        ~Files() { boost::system::error_code error; fs::remove_all(root, error); }
    } files;
    struct Imported {
        PlateDataPtrs plates;
        std::vector<Preset *> presets;
        ~Imported() { for (auto *preset : presets) delete preset; release_PlateData_list(plates); }
    } imported;
    PresetBundle bundle;
    Preset process = embedded(bundle.prints, Preset::TYPE_PRINT, "Portable process");
    Preset material = embedded(bundle.filaments, Preset::TYPE_FILAMENT, "Portable material");
    Preset machine = embedded(bundle.printers, Preset::TYPE_PRINTER, "Portable machine");
    machine.config.set_num_extruders(tools);
    machine.config.set_key_value("nozzle_diameter", new ConfigOptionFloats(nozzles));
    machine.config.set_key_value("fiber_enabled", new ConfigOptionBool(topology == 2));
    machine.config.set_key_value("fiber_shared_nozzle", new ConfigOptionBool(topology == 2));
    machine.config.set_key_value("plastic_nozzle_diameter", new ConfigOptionFloat(0.4));
    machine.config.set_key_value("composite_nozzle_diameter", new ConfigOptionFloat(0.7));
    machine.config.set_key_value("fiber_cut_distance", new ConfigOptionFloat(58.5));
    machine.config.set_key_value("fiber_restart_length", new ConfigOptionFloat(54.5));
    const std::vector<std::string> fiber_keys{"fiber_enabled", "fiber_shared_nozzle", "plastic_nozzle_diameter",
                                             "composite_nozzle_diameter", "fiber_cut_distance", "fiber_restart_length"};
    if (empty_identity == 1)
        material.config.set_key_value("filament_settings_id", new ConfigOptionStrings());
    else if (empty_identity == 2)
        process.config.set_key_value("print_settings_id", new ConfigOptionString());
    else if (empty_identity == 3)
        machine.config.set_key_value("printer_settings_id", new ConfigOptionString());
    machine.config.set_key_value("printhost_apikey", new ConfigOptionString("generated-private-key"));
    machine.config.set_key_value("print_host", new ConfigOptionString("192.0.2.99"));
    const auto machine_before = machine.config;
    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_num_extruders(tools);
    config.set_key_value("nozzle_diameter", new ConfigOptionFloats(nozzles));
    const size_t materials = nozzles.size() + 1;
    std::vector<std::string> colors{"#111111", "#EE2222", "#22CC44", "#2244EE", "#DDAA22"};
    colors.resize(materials);
    std::vector<int> map;
    std::vector<double> matrix, volumes, multipliers;
    for (size_t slot = 0; slot < materials; ++slot) {
        map.push_back(static_cast<int>(slot % tools + 1));
        volumes.push_back(100 + 10 * slot);
        volumes.push_back(150 + 10 * slot);
    }
    for (size_t tool = 0; tool < nozzles.size(); ++tool) {
        multipliers.push_back(0.5 + 0.1 * tool);
        for (size_t from = 0; from < materials; ++from)
            for (size_t to = 0; to < materials; ++to)
                matrix.push_back(from == to ? 0 : 1000 * tool + 100 * from + to + 1);
    }
    config.set_key_value("filament_settings_id", new ConfigOptionStrings(std::vector<std::string>(materials, material.name)));
    config.set_key_value("filament_colour", new ConfigOptionStrings(colors));
    config.set_key_value("filament_multi_colour", new ConfigOptionStrings(colors));
    config.set_key_value("filament_colour_type", new ConfigOptionStrings(std::vector<std::string>(materials, "1")));
    config.set_key_value("filament_map", new ConfigOptionInts(map));
    config.set_key_value("flush_volumes_matrix", new ConfigOptionFloats(matrix));
    config.set_key_value("flush_volumes_vector", new ConfigOptionFloats(volumes));
    config.set_key_value("flush_multiplier", new ConfigOptionFloats(multipliers));
    config.apply_only(machine.config, fiber_keys);
    config.set_key_value("printhost_password", new ConfigOptionString("generated-private-password"));
    const auto config_before = config;
    Model model;
    model.set_backup_path((files.root / "export").string());
    auto *object = model.add_object("cube", "", make_cube(10, 10, 10));
    object->add_instance();
    object->config.set_key_value("extruder", new ConfigOptionInt(static_cast<int>(materials)));
    const std::string path = (files.root / "portable.3mf").string();
    StoreParams params;
    params.path = path.c_str();
    params.model = &model;
    params.config = &config;
    params.project_presets = {&process, &material, &machine};
    params.strategy = SaveStrategy::Zip64 | SaveStrategy::Silence | SaveStrategy::SkipAuxiliary;
    REQUIRE(store_bbs_3mf(params));
    CHECK(machine.config == machine_before);
    CHECK(machine.file.empty());
    CHECK(config == config_before);

    Model restored;
    restored.set_backup_path((files.root / "import").string());
    DynamicPrintConfig restored_config;
    ConfigSubstitutionContext substitutions(ForwardCompatibilitySubstitutionRule::Enable);
    bool is_bambu = false, is_orca = false;
    Semver version;
    REQUIRE(load_bbs_3mf(path.c_str(), &restored_config, &substitutions, &restored, &imported.plates,
                        &imported.presets, &is_bambu, &is_orca, &version, nullptr,
                        LoadStrategy::LoadConfig | LoadStrategy::LoadModel | LoadStrategy::Silence));
    REQUIRE(restored.objects.size() == 1);
    REQUIRE(restored.objects.front()->volumes.size() == 1);
    REQUIRE(restored.objects.front()->instances.size() == 1);
    const auto &restored_mesh = restored.objects.front()->volumes.front()->mesh();
    const auto &original_mesh = model.objects.front()->volumes.front()->mesh();
    CHECK(restored_mesh.facets_count() == original_mesh.facets_count());
    CHECK(restored_mesh.bounding_box().size().isApprox(original_mesh.bounding_box().size()));
    CHECK(restored.objects.front()->config.opt_int("extruder") == int(materials));
    std::vector<std::string> portable_keys{
        "nozzle_diameter", "printer_extruder_variant", "filament_settings_id", "filament_colour",
        "filament_multi_colour", "filament_colour_type", "filament_map", "flush_volumes_matrix",
        "flush_volumes_vector", "flush_multiplier"};
    portable_keys.insert(portable_keys.end(), fiber_keys.begin(), fiber_keys.end());
    for (const auto &key : portable_keys) {
        CAPTURE(key);
        REQUIRE(restored_config.option(key) != nullptr);
        CHECK(restored_config.option(key)->serialize() == config_before.option(key)->serialize());
    }
    REQUIRE(imported.presets.size() == (empty_identity == 0 ? 3 : 2));
    for (const auto &key : restored_config.keys())
        CHECK_FALSE(tinmanx_runtime_connection_option(key));
    for (const auto *preset : imported.presets) {
        CHECK(preset->config.option(tuning_key(preset->type))->serialize() ==
              (preset->type == Preset::TYPE_PRINT ? process.config :
               preset->type == Preset::TYPE_FILAMENT ? material.config : machine.config)
              .option(tuning_key(preset->type))->serialize());
        if (preset->type == Preset::TYPE_PRINTER) {
            for (const auto &key : preset->config.keys())
                CHECK_FALSE(tinmanx_runtime_connection_option(key));
            for (const auto &key : fiber_keys) {
                REQUIRE(preset->config.option(key) != nullptr);
                CHECK(preset->config.option(key)->serialize() == machine_before.option(key)->serialize());
            }
        }
    }
    REQUIRE_NOTHROW(bundle.load_project_embedded_presets(imported.presets, ForwardCompatibilitySubstitutionRule::Enable));
    CHECK((bundle.prints.find_preset(process.name, false) != nullptr) == (empty_identity != 2));
    CHECK((bundle.filaments.find_preset(material.name, false) != nullptr) == (empty_identity != 1));
    CHECK((bundle.printers.find_preset(machine.name, false) != nullptr) == (empty_identity != 3));

    const std::string second_path = (files.root / "portable-again.3mf").string();
    StoreParams again;
    again.path = second_path.c_str();
    again.model = &restored;
    again.config = &restored_config;
    again.project_presets = imported.presets;
    again.strategy = params.strategy;
    REQUIRE(store_bbs_3mf(again));
    Imported imported_again;
    Model restored_again;
    restored_again.set_backup_path((files.root / "import-again").string());
    DynamicPrintConfig config_again;
    REQUIRE(load_bbs_3mf(second_path.c_str(), &config_again, &substitutions, &restored_again,
                        &imported_again.plates, &imported_again.presets, &is_bambu, &is_orca, &version, nullptr,
                        LoadStrategy::LoadConfig | LoadStrategy::LoadModel | LoadStrategy::Silence));
    REQUIRE(restored_again.objects.size() == 1);
    REQUIRE(restored_again.objects.front()->volumes.size() == 1);
    REQUIRE(restored_again.objects.front()->instances.size() == 1);
    const auto &second_mesh = restored_again.objects.front()->volumes.front()->mesh();
    CHECK(second_mesh.facets_count() == original_mesh.facets_count());
    CHECK(second_mesh.bounding_box().size().isApprox(original_mesh.bounding_box().size()));
    CHECK(restored_again.objects.front()->config.opt_int("extruder") == int(materials));
    CHECK(imported_again.presets.size() == imported.presets.size());
    for (const auto &key : portable_keys) {
        CAPTURE(key);
        REQUIRE(config_again.option(key) != nullptr);
        CHECK(config_again.option(key)->serialize() == config_before.option(key)->serialize());
    }
    for (const auto &key : config_again.keys())
        CHECK_FALSE(tinmanx_runtime_connection_option(key));
    for (const auto *preset : imported_again.presets) {
        const auto &original_config = preset->type == Preset::TYPE_PRINT ? process.config :
                                      preset->type == Preset::TYPE_FILAMENT ? material.config : machine.config;
        CHECK(preset->config.option(tuning_key(preset->type))->serialize() ==
              original_config.option(tuning_key(preset->type))->serialize());
        if (preset->type == Preset::TYPE_PRINTER) {
            for (const auto &key : preset->config.keys())
                CHECK_FALSE(tinmanx_runtime_connection_option(key));
            for (const auto &key : fiber_keys) {
                REQUIRE(preset->config.option(key) != nullptr);
                CHECK(preset->config.option(key)->serialize() == machine_before.option(key)->serialize());
            }
        }
    }
}

TEST_CASE("Adding saved profiles preserves current identity while sorting the catalog", "[Preset][ProjectRecovery][TinMan]")
{
    namespace fs = boost::filesystem;
    const auto type = GENERATE(Preset::TYPE_PRINT, Preset::TYPE_FILAMENT, Preset::TYPE_PRINTER);
    struct Files {
        fs::path root = fs::temp_directory_path() / fs::unique_path("tinman-profile-sort-%%%%-%%%%");
        ~Files() { boost::system::error_code error; fs::remove_all(root, error); }
    } files;
    PresetBundle bundle;
    auto &collection = collection_for(bundle, type);
    collection.load_preset({}, "Z selected saved profile", collection.default_preset().config, true);
    tune(collection.get_edited_preset().config, type);
    const auto before = collection.get_edited_preset().config;
    const auto subdir = Preset::get_type_string(type);
    fs::create_directories(files.root / subdir);
    Preset addition = embedded(collection, type, type == Preset::TYPE_FILAMENT ? "Generic A addition" : "A addition");
    addition.config.save_to_json((files.root / subdir / (addition.name + ".json")).string(), addition.name, "User", "1.0.0");
    PresetsConfigSubstitutions substitutions;
    collection.load_presets(files.root.string(), subdir, substitutions, ForwardCompatibilitySubstitutionRule::Disable);
    REQUIRE(collection.find_preset(addition.name, false) != nullptr);
    CHECK(collection.get_selected_preset_name() == "Z selected saved profile");
    CHECK(collection.get_edited_preset().config == before);
}

TEST_CASE("Project material diffs preserve standard and high-flow variant values", "[Preset][ProjectRecovery][TinMan][MultiTool]")
{
    PresetBundle bundle;
    auto &collection = bundle.filaments;
    auto parent_config = collection.default_preset().config;
    parent_config.set_key_value("filament_extruder_variant", new ConfigOptionStrings{
        "Direct Drive Standard", "Direct Drive High Flow"});
    parent_config.option<ConfigOptionFloats>("filament_flow_ratio")->values = {0.96, 0.98};
    parent_config.option<ConfigOptionFloats>("filament_max_volumetric_speed")->values = {12.0, 19.0};
    const auto &parent = collection.load_preset({}, "Material variant base", parent_config, false);
    Preset child = parent;
    child.name = "Material variant project";
    child.is_project_embedded = true;
    child.is_external = true;
    child.config.set_key_value("inherits", new ConfigOptionString(parent.name));
    child.config.set_key_value("filament_settings_id", new ConfigOptionStrings{child.name});
    child.config.option<ConfigOptionFloats>("filament_flow_ratio")->values[1] = 0.95;
    const auto before = child.config;
    std::unique_ptr<Preset> exported(collection.get_preset_differed_for_save(child));
    REQUIRE(exported != nullptr);
    const auto *ratio = dynamic_cast<const ConfigOptionVectorBase *>(exported->config.option("filament_flow_ratio"));
    REQUIRE(ratio != nullptr);
    REQUIRE(ratio->size() == 2);
    CHECK(ratio->is_nil(0));
    CHECK_FALSE(ratio->is_nil(1));
    load(collection, Preset::TYPE_FILAMENT, {exported.get()});
    const auto *restored = collection.find_preset(child.name, false);
    REQUIRE(restored != nullptr);
    CHECK(restored->config.option<ConfigOptionFloats>("filament_flow_ratio")->values == std::vector<double>{0.96, 0.95});
    CHECK(restored->config.option<ConfigOptionFloats>("filament_max_volumetric_speed")->values == std::vector<double>{12.0, 19.0});
    CHECK(child.config == before);
}
