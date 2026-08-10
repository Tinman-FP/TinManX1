#include <catch2/catch_all.hpp>

#include "libslic3r/TinManMachineProfileContract.hpp"
#include "libslic3r/AppConfig.hpp"

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
