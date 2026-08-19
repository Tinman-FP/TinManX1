#include <catch2/catch_all.hpp>

#include "libslic3r/TinManMachineProfileContract.hpp"
#include "libslic3r/AppConfig.hpp"
#include "libslic3r/Preset.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "slic3r/Utils/MoonrakerStorage.hpp"

using namespace Slic3r;

TEST_CASE("TinMan curated machines expose only canonical nozzle presets", "[Preset][TinMan]")
{
    CHECK(tinmanx_machine_preset_allowed(
        "Qidi X-Plus 4 0.4 nozzle - TinMan Codex", "Qidi X-Plus 4"));
    CHECK(tinmanx_machine_preset_allowed(
        "Qidi X-Plus 4 1.0 nozzle - TinMan Codex", "Qidi X-Plus 4"));
    CHECK(tinmanx_machine_preset_allowed(
        "__subscribed/team/Qidi X-Plus 4 0.8 nozzle - TinMan Codex", "Qidi X-Plus 4"));
    CHECK(tinmanx_machine_preset_allowed(
        "__subscribed/team/Qidi X-Plus 4 0.6 nozzle - TinMan Codex", "qIdI pLuS 4"));

    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "Qidi X-Plus 4 0.6 nozzle", "Qidi X-Plus 4"));
    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "CURRENT QIDI Copy", "Qidi X-Plus 4"));
    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "Snapmaker U1 (0.8 nozzle) - Codex Tinman", "Snapmaker U1"));
    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "FibreSeek Seeker 3 - Codex", "SEEKER 3"));
    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "RatRig V-Core 4 IDEX 500 COPY MODE 0.5 nozzle", "RatRig V-Core 4 IDEX 500 COPY MODE"));
    CHECK_FALSE(tinmanx_machine_preset_allowed(
        "Qidi X-Plus 4 0.4 nozzle - TinMan Codex Copy", "Qidi X-Plus 4"));

    CHECK(tinmanx_machine_preset_allowed("My Experimental Printer", "My Experimental Printer"));
}

TEST_CASE("TinMan canonicalizes persisted curated printer selections", "[Preset][TinMan]")
{
    CHECK(tinmanx_canonical_machine_preset_name(
        "Prusa CORE One L 0.6 nozzle", "Prusa CORE One L", "0.6") ==
        "Prusa CORE One L 0.6 nozzle - TinMan Codex");
    CHECK(tinmanx_canonical_machine_preset_name(
        "CURRENT Snapmaker U1 (0.8 nozzle)", "fdm_U1") ==
        "Snapmaker U1 0.8 nozzle - TinMan Codex");
    CHECK(tinmanx_canonical_machine_preset_name(
        "Snapmaker U1 0.6 nozzle - TinMan Codex - Copy", "Snapmaker U1", "0.6") ==
        "Snapmaker U1 0.6 nozzle - TinMan Codex");
    CHECK(tinmanx_canonical_machine_preset_name(
        "QIDI Plus 4 1.0 nozzle", "Qidi Plus 4") ==
        "Qidi X-Plus 4 1.0 nozzle - TinMan Codex");

    CHECK(tinmanx_canonical_machine_preset_name("My Experimental Printer", "My Experimental Printer").empty());
    CHECK(tinmanx_canonical_machine_preset_name("Prusa CORE One L 0.5 nozzle", "Prusa CORE One L").empty());
}

TEST_CASE("TinMan curated machines expose only their canonical process presets", "[Preset][TinMan]")
{
    const std::string printer = "Prusa CORE One L 0.4 nozzle - TinMan Codex";

    CHECK(tinmanx_process_preset_allowed(
        "0.20mm Quality @Prusa CORE One L 0.4 nozzle - TinMan Codex", printer));
    CHECK(tinmanx_process_preset_allowed(
        "0.20mm Quality @Prusa CORE One L 0.4 nozzle - TinMan Codex - Copy", printer));
    CHECK(tinmanx_process_preset_allowed(
        "team/process/0.20mm Tank @Prusa CORE One L 0.4 nozzle - TinMan Codex", printer));
    CHECK_FALSE(tinmanx_process_preset_allowed(
        "0.10mm FAST DETAIL @CORE One L 0.4", printer));

    CHECK(tinmanx_process_preset_allowed(
        "0.20mm STRUCTURAL @CORE One L 0.4", "Prusa CORE One L 0.4 nozzle"));
    CHECK(tinmanx_process_preset_allowed(
        "My Experimental Process", "My Experimental Printer"));
}

TEST_CASE("TinMan machine catalog replaces cloud-restored variants", "[Preset][TinMan]")
{
    AppConfig config;
    config.set_variant("Qidi", "Qidi X-Plus 4", "0.2", true);
    config.set_variant("COSMOS", "Centauri COSMOS Tinman", "0.4", true);
    config.set_str("nozzle_volume_types", "Bambu Lab X1 Carbon 0.6 nozzle - TinMan Codex", "Standard");
    config.set_str("nozzle_volume_types", "Bambu Lab H2D 0.6 nozzle", "Standard,Standard");
    config.set_str("nozzle_volume_types", "Snapmaker U1 0.6 nozzle - TinMan Codex", "High Flow,High Flow,High Flow,High Flow");

    tinmanx_apply_machine_catalog(config);

    REQUIRE(config.vendors().size() == 9);
    CHECK_FALSE(config.get_variant("Qidi", "Qidi X-Plus 4", "0.2"));
    CHECK_FALSE(config.get_variant("COSMOS", "Centauri COSMOS Tinman", "0.4"));
    for (const char *nozzle : {"0.4", "0.6", "0.8", "1.0"}) {
        CHECK(config.get_variant("Qidi", "Qidi X-Plus 4", nozzle));
        CHECK(config.get_variant("TinManX1", "FibreSeek Seeker 3", nozzle));
    }
    CHECK(config.get("nozzle_volume_types", "Bambu Lab X1 Carbon 0.6 nozzle - TinMan Codex") == "High Flow");
    CHECK(config.get("nozzle_volume_types", "Bambu Lab H2D 0.6 nozzle") == "High Flow,High Flow");
    CHECK(config.get("nozzle_volume_types", "RatRig V-Core 4 IDEX 500 0.8 nozzle - TinMan Codex") == "High Flow,High Flow");
    CHECK(config.get("nozzle_volume_types", "Snapmaker U1 0.6 nozzle - TinMan Codex") == "Standard,Standard,Standard,Standard");
}

TEST_CASE("TinMan machine hardware overrides stale project nozzle flow", "[Preset][TinMan]")
{
    DynamicPrintConfig project;
    project.set_key_value("nozzle_volume_type",
        new ConfigOptionEnumsGeneric({NozzleVolumeType::nvtStandard}));

    DynamicPrintConfig x1c;
    x1c.set_key_value("printer_model", new ConfigOptionString("Bambu Lab X1 Carbon"));
    x1c.set_key_value("printer_settings_id", new ConfigOptionString(
        "Bambu Lab X1 Carbon 0.6 nozzle - TinMan Codex"));
    x1c.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6}));
    REQUIRE(tinmanx_apply_nozzle_volume_contract(
        "Bambu Lab X1 Carbon 0.6 nozzle - TinMan Codex", x1c, project));
    CHECK(project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values ==
          std::vector<int>{NozzleVolumeType::nvtHighFlow});

    DynamicPrintConfig export_config;
    REQUIRE(tinmanx_apply_nozzle_volume_contract(
        "Bambu Lab X1 Carbon 0.6 nozzle - TinMan Codex", x1c, export_config));
    CHECK(export_config.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values ==
          std::vector<int>{NozzleVolumeType::nvtHighFlow});

    project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values.assign(
        4, NozzleVolumeType::nvtHighFlow);
    DynamicPrintConfig u1;
    u1.set_key_value("printer_model", new ConfigOptionString("Snapmaker U1"));
    u1.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.6, 0.6, 0.6}));
    REQUIRE(tinmanx_apply_nozzle_volume_contract(
        "Snapmaker U1 0.6 nozzle - TinMan Codex", u1, project));
    CHECK(project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values ==
          std::vector<int>(4, NozzleVolumeType::nvtStandard));

    project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values = {
        NozzleVolumeType::nvtStandard};
    REQUIRE(tinmanx_apply_nozzle_volume_contract(
        "imported-project.3mf", x1c, project));
    CHECK(project.option<ConfigOptionEnumsGeneric>("nozzle_volume_type")->values ==
          std::vector<int>{NozzleVolumeType::nvtHighFlow});

    x1c.set_key_value("printer_settings_id", new ConfigOptionString(
        "Bambu Lab X1 Carbon 0.6 nozzle"));
    CHECK_FALSE(tinmanx_apply_nozzle_volume_contract(
        "Bambu Lab X1 Carbon 0.6 nozzle", x1c, project));
}

TEST_CASE("TinMan connection overlay follows a machine across nozzle presets", "[Preset][TinMan]")
{
    AppConfig app_config;
    DynamicPrintConfig source;
    source.set_key_value("printer_model", new ConfigOptionString("Qidi X-Plus 4"));
    source.set_key_value("printer_agent", new ConfigOptionString("qidi"));
    source.set_key_value("print_host", new ConfigOptionString("192.0.2.145"));
    source.set_key_value("print_host_webui", new ConfigOptionString("http://192.0.2.145"));

    CHECK(tinmanx_remember_machine_connection(
        app_config, "Qidi X-Plus 4 0.6 nozzle - TinMan Codex - Copy", source));
    CHECK(app_config.get("ip_address", "Qidi X-Plus 4 1.0 nozzle - TinMan Codex") ==
          "192.0.2.145");

    DynamicPrintConfig target;
    target.set_key_value("print_host", new ConfigOptionString());
    target.set_key_value("print_host_webui", new ConfigOptionString());
    target.set_key_value("printer_model", new ConfigOptionString("Qidi X-Plus 4"));
    target.set_key_value("printer_agent", new ConfigOptionString("qidi"));
    CHECK(tinmanx_restore_machine_connection(
        app_config, "Qidi X-Plus 4 1.0 nozzle - TinMan Codex", target));
    CHECK(target.opt_string("print_host") == "192.0.2.145");
    CHECK(target.opt_string("print_host_webui") == "http://192.0.2.145");
    CHECK(target.opt_string("printer_agent") == "qidi");
}

TEST_CASE("TinMan connection routing cannot downgrade specialized printer agents", "[Preset][TinMan]")
{
    CHECK(tinmanx_expected_printer_agent("Creality K2 Plus 0.6 nozzle - TinMan Codex") == "crealityprint");
    CHECK(tinmanx_expected_printer_agent("Qidi X-Plus 4", "Qidi X-Plus 4") == "qidi");
    CHECK(tinmanx_expected_printer_agent("Snapmaker U1", "Snapmaker U1") == "snapmaker");
    CHECK(tinmanx_expected_printer_agent("My Experimental Printer").empty());

    AppConfig app_config;
    DynamicPrintConfig source;
    source.set_key_value("printer_model", new ConfigOptionString("Creality K2 Plus"));
    source.set_key_value("printer_agent", new ConfigOptionString("moonraker"));
    source.set_key_value("host_type", new ConfigOptionEnum<PrintHostType>(htMoonraker));
    source.set_key_value("print_host", new ConfigOptionString("192.0.2.174:7125"));
    source.set_key_value("print_host_webui", new ConfigOptionString("http://192.0.2.174:4408/"));

    const std::string preset = "Creality K2 Plus 0.6 nozzle - TinMan Codex - Copy";
    CHECK(tinmanx_remember_machine_connection(app_config, preset, source));
    CHECK(app_config.get("tinman_machine_connections", "Creality K2 Plus::printer_agent") == "crealityprint");
    CHECK(app_config.get("tinman_machine_connections", "Creality K2 Plus::host_type") == "crealityprint");
    CHECK(app_config.get("tinman_machine_connections", "Creality K2 Plus::print_host") == "192.0.2.174");
    CHECK(app_config.get("tinman_machine_connections", "Creality K2 Plus::print_host_webui") ==
          "http://192.0.2.174:4408/");
    CHECK(app_config.get("ip_address", "Creality K2 Plus 0.4 nozzle - TinMan Codex") == "192.0.2.174");

    DynamicPrintConfig restored = source;
    CHECK(tinmanx_restore_machine_connection(app_config, preset, restored));
    CHECK(restored.opt_string("printer_agent") == "crealityprint");
    CHECK(restored.opt_enum<PrintHostType>("host_type") == htCrealityPrint);
    CHECK(restored.opt_string("print_host") == "192.0.2.174");
    CHECK(restored.opt_string("print_host_webui") == "http://192.0.2.174:4408/");
}

TEST_CASE("TinMan Qidi connections cannot fall back to OctoPrint", "[Preset][TinMan]")
{
    AppConfig app_config;
    DynamicPrintConfig source;
    source.set_key_value("printer_model", new ConfigOptionString("Qidi X-Plus 4"));
    source.set_key_value("printer_agent", new ConfigOptionString("qidi"));
    source.set_key_value("host_type", new ConfigOptionEnum<PrintHostType>(htOctoPrint));
    source.set_key_value("print_host", new ConfigOptionString("192.0.2.145"));
    source.set_key_value("print_host_webui", new ConfigOptionString("192.0.2.145"));

    const std::string preset = "Qidi X-Plus 4 0.6 nozzle - TinMan Codex - Copy";
    CHECK(tinmanx_enforce_machine_connection_contract(preset, source));
    CHECK(source.opt_enum<PrintHostType>("host_type") == htMoonraker);

    CHECK(tinmanx_remember_machine_connection(app_config, preset, source));
    CHECK(app_config.get("tinman_machine_connections", "Qidi X-Plus 4::host_type") == "moonraker");

    source.set_key_value("host_type", new ConfigOptionEnum<PrintHostType>(htOctoPrint));
    CHECK(tinmanx_restore_machine_connection(app_config, preset, source));
    CHECK(source.opt_enum<PrintHostType>("host_type") == htMoonraker);
}

TEST_CASE("TinMan connection overlay migrates legacy canonical IP entries", "[Preset][TinMan]")
{
    AppConfig app_config;
    app_config.set_str("ip_address", "Snapmaker U1 0.4 nozzle - TinMan Codex", "192.0.2.3");

    DynamicPrintConfig target;
    target.set_key_value("printer_model", new ConfigOptionString("Snapmaker U1"));
    target.set_key_value("print_host", new ConfigOptionString());
    target.set_key_value("print_host_webui", new ConfigOptionString());
    CHECK(tinmanx_restore_machine_connection(
        app_config, "Snapmaker U1 0.8 nozzle - TinMan Codex", target));
    CHECK(target.opt_string("print_host") == "192.0.2.3");
    CHECK(target.opt_string("print_host_webui") == "192.0.2.3");
}

TEST_CASE("TinMan startup migration preserves a newer family connection", "[Preset][TinMan]")
{
    AppConfig app_config;
    const std::string section = "tinman_machine_connections";
    const std::string model = "Prusa CORE One L";
    const std::string current_host = "prusa-core-one-l.local";
    app_config.set_str(section, model + "::print_host", current_host);
    app_config.set_str(section, model + "::print_host_webui", current_host);

    DynamicPrintConfig stale_profile;
    stale_profile.set_key_value("printer_model", new ConfigOptionString(model));
    stale_profile.set_key_value("print_host", new ConfigOptionString("192.0.2.169"));
    stale_profile.set_key_value("print_host_webui", new ConfigOptionString("192.0.2.169"));
    stale_profile.set_key_value("printhost_apikey", new ConfigOptionString("legacy-api-key"));

    CHECK(tinmanx_remember_machine_connection(
        app_config, "Prusa CORE One L 0.6 nozzle - TinMan Codex", stale_profile, false));
    CHECK(app_config.get(section, model + "::print_host") == current_host);
    CHECK(app_config.get(section, model + "::print_host_webui") == current_host);
    CHECK(app_config.get(section, model + "::printhost_apikey") == "legacy-api-key");
    for (const char *nozzle : {"0.4", "0.6", "0.8", "1.0"}) {
        const std::string preset = model + " " + nozzle + " nozzle - TinMan Codex";
        CHECK(app_config.get("ip_address", preset) == current_host);
    }
}

TEST_CASE("TinMan runtime connection overlay has explicit dirty-state boundaries", "[Preset][TinMan]")
{
    CHECK(tinmanx_managed_machine_preset(
        "Bambu Lab H2D 0.6 nozzle - TinMan Codex", "Bambu Lab H2D"));
    CHECK_FALSE(tinmanx_managed_machine_preset("Bambu Lab H2D 0.6 nozzle", "Bambu Lab H2D"));
    CHECK_FALSE(tinmanx_managed_machine_preset("Unrelated Printer 0.6 nozzle", "Unrelated Printer"));

    CHECK(tinmanx_runtime_connection_option("print_host"));
    CHECK(tinmanx_runtime_connection_option("printhost_apikey"));
    CHECK(tinmanx_runtime_connection_option("printer_agent"));
    CHECK_FALSE(tinmanx_runtime_connection_option("nozzle_diameter"));
    CHECK_FALSE(tinmanx_runtime_connection_option("bed_shape"));
}

TEST_CASE("TinMan runtime connection overlay does not dirty managed printer presets", "[Preset][TinMan]")
{
    const std::string name = "Bambu Lab H2D 0.6 nozzle - TinMan Codex";
    Preset saved(Preset::TYPE_PRINTER, name);
    saved.config.set_key_value("printer_model", new ConfigOptionString("Bambu Lab H2D"));
    saved.config.set_key_value("printer_agent", new ConfigOptionString("bbl"));
    saved.config.set_key_value("print_host", new ConfigOptionString());
    saved.config.set_key_value("printhost_apikey", new ConfigOptionString());
    saved.config.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.6, 0.6}));

    Preset edited = saved;
    edited.config.set_key_value("print_host", new ConfigOptionString("192.0.2.120"));
    edited.config.set_key_value("printhost_apikey", new ConfigOptionString("lan-access-code"));

    CHECK_FALSE(PresetCollection::is_dirty(&edited, &saved));
    CHECK(PresetCollection::dirty_options(&edited, &saved).empty());

    edited.config.set_key_value("nozzle_diameter", new ConfigOptionFloats({0.4, 0.4}));
    CHECK(PresetCollection::is_dirty(&edited, &saved));
    CHECK(PresetCollection::dirty_options(&edited, &saved) == std::vector<std::string>{"nozzle_diameter"});
}

TEST_CASE("Moonraker print uploads use only the virtual SD gcode root", "[Preset][TinMan][Moonraker]")
{
    using namespace Slic3r::MoonrakerStorage;

    CHECK(is_printable_root("gcodes", "rw"));
    CHECK(is_printable_root("gcodes", "rwd"));
    CHECK_FALSE(is_printable_root("gcodes", "r"));
    CHECK_FALSE(is_printable_root("config", "rw"));
    CHECK_FALSE(is_printable_root("timelapse", "rw"));

    CHECK(print_root("") == "gcodes");
    CHECK(print_root("gcodes") == "gcodes");
    CHECK(print_root("config") == "gcodes");
    CHECK(print_root("timelapse") == "gcodes");

    boost::property_tree::ptree standard_response;
    standard_response.put("result.item.path", "renamed-standard.gcode");
    CHECK(uploaded_path(standard_response, "fallback.gcode") == "renamed-standard.gcode");

    boost::property_tree::ptree snapmaker_response;
    snapmaker_response.put("item.path", "renamed-snapmaker.gcode");
    CHECK(uploaded_path(snapmaker_response, "fallback.gcode") == "renamed-snapmaker.gcode");

    const boost::property_tree::ptree empty_response;
    CHECK(uploaded_path(empty_response, "fallback.gcode") == "fallback.gcode");
}
