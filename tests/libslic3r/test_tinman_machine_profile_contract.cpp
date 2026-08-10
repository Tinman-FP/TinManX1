#include <catch2/catch_all.hpp>

#include "libslic3r/TinManMachineProfileContract.hpp"
#include "libslic3r/AppConfig.hpp"
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

    tinmanx_apply_machine_catalog(config);

    REQUIRE(config.vendors().size() == 9);
    CHECK_FALSE(config.get_variant("Qidi", "Qidi X-Plus 4", "0.2"));
    CHECK_FALSE(config.get_variant("COSMOS", "Centauri COSMOS Tinman", "0.4"));
    for (const char *nozzle : {"0.4", "0.6", "0.8", "1.0"}) {
        CHECK(config.get_variant("Qidi", "Qidi X-Plus 4", nozzle));
        CHECK(config.get_variant("TinManX1", "FibreSeek Seeker 3", nozzle));
    }
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
