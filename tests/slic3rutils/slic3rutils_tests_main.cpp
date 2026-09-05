#include <catch2/catch_all.hpp>

#include "slic3r/GUI/TaskManager.hpp"
#include "slic3r/Utils/BBLNetworkPlugin.hpp"
#include "slic3r/Utils/CrealityPrint.hpp"
#include "slic3r/Utils/CrealityPrintAgent.hpp"
#include "slic3r/Utils/Http.hpp"
#include "slic3r/Utils/OrcaCloudServiceAgent.hpp"
#include "slic3r/Utils/SnapmakerPrinterAgent.hpp"
#include "slic3r/Utils/RecentProjectThumbnailCache.hpp"

TEST_CASE("Recent thumbnail lookup never opens the original project", "[TinMan][ThumbnailCache]")
{
    const auto directory = boost::filesystem::temp_directory_path() / boost::filesystem::unique_path("tinman-thumbnails-%%%%-%%%%");
    const Slic3r::RecentProjectThumbnailCache cache(directory);
    const std::string project = "/unavailable-volume/cloud-placeholder.3mf";
    const std::string png = std::string("\x89PNG\r\n\x1a\n", 8) + "fixture";
    CHECK(cache.read(project).empty());
    cache.write(project, png);
    CHECK(cache.read(project) == png);
    CHECK(cache.read(project + ".other").empty());
    cache.write(project, "invalid PNG");
    CHECK(cache.read(project) == png);
    cache.write(project, png + "updated");
    CHECK(cache.read(project) == png + "updated");
    cache.write(project + ".oversized", png + std::string(2 * 1024 * 1024, 'x'));
    CHECK(cache.read(project + ".oversized").empty());
    boost::filesystem::remove_all(directory);
}

namespace {

nlohmann::json flat_session_json(const nlohmann::json& fields)
{
    nlohmann::json session = {
        {"access_token", "test-token"},
        {"user_id", "test-user-id"}
    };
    session.update(fields);
    return session;
}

nlohmann::json nested_session_json(const nlohmann::json& metadata)
{
    return {
        {"access_token", "test-token"},
        {"user", {
            {"id", "test-user-id"},
            {"user_metadata", metadata}
        }}
    };
}

std::string resolved_display_name(const nlohmann::json& session)
{
    Slic3r::OrcaCloudServiceAgent agent("");
    REQUIRE(agent.set_user_session(session, false));
    return agent.get_user_nickname();
}

} // namespace

TEST_CASE("Bambu network manager survives repeated finalization", "[BBLNetworkPlugin][Lifecycle]")
{
    auto *manager = &Slic3r::BBLNetworkPlugin::instance();

    Slic3r::BBLNetworkPlugin::shutdown();
    CHECK(&Slic3r::BBLNetworkPlugin::instance() == manager);
    CHECK_FALSE(manager->has_agent());
    CHECK_FALSE(manager->is_loaded());

    Slic3r::BBLNetworkPlugin::shutdown();
    CHECK(&Slic3r::BBLNetworkPlugin::instance() == manager);
    CHECK_FALSE(manager->has_agent());
    CHECK_FALSE(manager->is_loaded());

    CHECK(manager->unload() == 0);
    CHECK(&Slic3r::BBLNetworkPlugin::instance() == manager);
    CHECK_FALSE(manager->has_agent());
    CHECK_FALSE(manager->is_loaded());
}

TEST_CASE("Print task scheduler shutdown is repeatable", "[TaskManager][Lifecycle]")
{
    Slic3r::TaskStateInfo task(Slic3r::PrintParams{});
    int callback_count = 0;
    task.set_state_changed_fn([&callback_count](Slic3r::TaskState, int) { ++callback_count; });

    task.cancel();
    task.cancel();
    CHECK(task.is_canceled());
    CHECK(task.state() == Slic3r::TaskState::TS_REMOVED);
    CHECK(callback_count == 3);

    Slic3r::TaskManager manager(nullptr);
    manager.start();
    manager.stop();
    manager.stop();
    manager.start();
    manager.stop();
}

TEST_CASE("Check SSL certificates paths", "[Http][NotWorking]") {
    
    Slic3r::Http g = Slic3r::Http::get("https://github.com/");
    
    unsigned status = 0;
    g.on_error([&status](std::string, std::string, unsigned http_status) {
        status = http_status;
    });
    
    g.on_complete([&status](std::string /* body */, unsigned http_status){
        status = http_status;
    });
    
    g.perform_sync();
    
    REQUIRE(status == 200);
}

TEST_CASE("Orca cloud flat session resolves display name consistently", "[OrcaCloudServiceAgent]")
{
    CHECK(resolved_display_name(flat_session_json({
        {"username", "orca_username"},
        {"display_name", "Display Name"},
        {"nickname", "Nickname"}
    })) == "Display Name");

    CHECK(resolved_display_name(flat_session_json({
        {"username", "orca_username"},
        {"nickname", "Nickname"}
    })) == "Nickname");

    CHECK(resolved_display_name(flat_session_json({
        {"username", "orca_username"},
        {"full_name", "Full Name"}
    })) == "Full Name");

    CHECK(resolved_display_name(flat_session_json({
        {"username", "orca_username"},
        {"name", "Provider Name"}
    })) == "Provider Name");

    CHECK(resolved_display_name(flat_session_json({
        {"username", "orca_username"}
    })) == "orca_username");
}

TEST_CASE("Orca cloud nested session resolves display name consistently", "[OrcaCloudServiceAgent]")
{
    CHECK(resolved_display_name(nested_session_json({
        {"username", "orca_username"},
        {"display_name", "Display Name"},
        {"nickname", "Nickname"}
    })) == "Display Name");

    CHECK(resolved_display_name(nested_session_json({
        {"username", "orca_username"},
        {"nickname", "Nickname"}
    })) == "Nickname");

    CHECK(resolved_display_name(nested_session_json({
        {"username", "orca_username"},
        {"full_name", "Full Name"}
    })) == "Full Name");

    CHECK(resolved_display_name(nested_session_json({
        {"username", "orca_username"},
        {"name", "Provider Name"}
    })) == "Provider Name");

    CHECK(resolved_display_name(nested_session_json({
        {"username", "orca_username"}
    })) == "orca_username");
}

TEST_CASE("Snapmaker live filament data outranks stale saved metadata", "[SnapmakerPrinterAgent]")
{
    using Slic3r::SnapmakerPrinterAgent;

    CHECK(SnapmakerPrinterAgent::resolve_filament_type("ASA-CF", "", "PET-CF") == "ASA-CF");
    CHECK(SnapmakerPrinterAgent::resolve_filament_type("PLA", "HT-PLA-GF", "PET-CF") == "HT-PLA-GF");
    CHECK(SnapmakerPrinterAgent::resolve_filament_type("PEBA", "", "PET-CF") == "PEBA");
}

TEST_CASE("Snapmaker saved filament metadata remains a missing-live-data fallback", "[SnapmakerPrinterAgent]")
{
    using Slic3r::SnapmakerPrinterAgent;

    CHECK(SnapmakerPrinterAgent::resolve_filament_type("", "", "PCTG-CF") == "PCTG-CF");
    CHECK(SnapmakerPrinterAgent::resolve_filament_type("", "", "PEBA") == "PEBA");
    CHECK(SnapmakerPrinterAgent::resolve_filament_type("", "", "") == "PLA");
}

TEST_CASE("Snapmaker product metadata is authoritative for mixed U1 nozzles", "[SnapmakerPrinterAgent]")
{
    using Slic3r::SnapmakerPrinterAgent;

    const nlohmann::json product = {{"nozzle_diameter", {0.6, 0.4, 0.4, 0.6}}};
    const nlohmann::json saved = {
        {"u1_t0_nozzle_size", 0.4}, {"u1_t0_nozzle_type", "hardened_steel"},
        {"u1_t1_nozzle_size", 0.6}, {"u1_t1_nozzle_type", "stainless_steel"},
        {"u1_t2_nozzle_size", 0.6}, {"u1_t2_nozzle_type", "hardened_steel"},
        {"u1_t3_nozzle_size", 0.4}, {"u1_t3_nozzle_type", "hardened_steel"}
    };

    const auto nozzles = SnapmakerPrinterAgent::parse_nozzle_metadata(product, saved);
    REQUIRE(nozzles.size() == 4);
    CHECK(nozzles[0].diameter == Catch::Approx(0.6));
    CHECK(nozzles[1].diameter == Catch::Approx(0.4));
    CHECK(nozzles[2].diameter == Catch::Approx(0.4));
    CHECK(nozzles[3].diameter == Catch::Approx(0.6));
    CHECK(nozzles[0].type == "hardened_steel");
    CHECK(nozzles[1].type == "stainless_steel");
}

TEST_CASE("Snapmaker saved nozzle metadata is a validated firmware fallback", "[SnapmakerPrinterAgent]")
{
    using Slic3r::SnapmakerPrinterAgent;

    const nlohmann::json saved = {
        {"u1_t0_nozzle_size", 0.6}, {"u1_t0_nozzle_type", "HARDENED_STEEL"},
        {"u1_t1_nozzle_size", 3.0}, {"u1_t1_nozzle_type", "brass"},
        {"u1_t2_nozzle_size", 0.4}, {"u1_t2_nozzle_type", "unknown_material"}
    };

    const auto nozzles = SnapmakerPrinterAgent::parse_nozzle_metadata(nlohmann::json::object(), saved);
    REQUIRE(nozzles.size() == 2);
    CHECK(nozzles[0].tool_id == 0);
    CHECK(nozzles[0].type == "hardened_steel");
    CHECK(nozzles[1].tool_id == 2);
    CHECK(nozzles[1].diameter == Catch::Approx(0.4));
    CHECK(nozzles[1].type == "undefine");
}

TEST_CASE("Creality CFS material normalization respects complete material tokens", "[CrealityPrintAgent]")
{
    using Slic3r::CrealityPrintAgent;

    CHECK(CrealityPrintAgent::normalize_filament_type("PCTG") == "PCTG");
    CHECK(CrealityPrintAgent::normalize_filament_type("PCTG-CF") == "PCTG");
    CHECK(CrealityPrintAgent::normalize_filament_type(" PC ") == "PC");
    CHECK(CrealityPrintAgent::normalize_filament_type("PC-ABS") == "PC");
    CHECK(CrealityPrintAgent::normalize_filament_type("PETG-CF") == "PETG");
    CHECK(CrealityPrintAgent::normalize_filament_type("PPA-CF") == "PPA");
    CHECK(CrealityPrintAgent::normalize_filament_type("PCGF") == "PCGF");
}

TEST_CASE("Creality CFS uses the direct printer host beside Moonraker", "[CrealityPrintAgent]")
{
    using Slic3r::CrealityPrintAgent;

    CHECK(CrealityPrintAgent::direct_api_host("192.0.2.174:7125") == "192.0.2.174");
    CHECK(CrealityPrintAgent::direct_api_host("http://192.0.2.174:4408/") == "192.0.2.174");
    CHECK(CrealityPrintAgent::direct_api_host("k2-plus.local") == "k2-plus.local");
}

TEST_CASE("Creality test and upload API reject stale Moonraker ports", "[CrealityPrint]")
{
    using Slic3r::CrealityPrint;

    CHECK(CrealityPrint::get_device_api_url("192.0.2.174:7125") == "http://192.0.2.174");
    CHECK(CrealityPrint::get_device_api_url("http://192.0.2.174:4408/") == "http://192.0.2.174");
    CHECK(CrealityPrint::get_device_api_url(" k2-plus.local ") == "http://k2-plus.local");
}

TEST_CASE("Creality CFS handoff requires indexed filament metadata and a confirmed mapping", "[CrealityPrint]")
{
    using Slic3r::CrealityPrint;

    const std::string valid = R"({"retGcodeFileInfo2":[{"name":"part.gcode","validation_completed":true,"material":"PCTG","materialColors":"#1B04AE","materialIds":"PCTG01","printer_model":"Creality K2 Plus","match":"T1A=T1B "}]})";
    std::string error;
    CHECK(CrealityPrint::validate_cfs_file_info_response(valid, "part.gcode", error));
    CHECK(error.empty());

    const std::string missing_metadata = R"({"retGcodeFileInfo2":[{"name":"part.gcode","validation_completed":true,"material":"","materialColors":"","materialIds":"","printer_model":"","match":""}]})";
    CHECK_FALSE(CrealityPrint::validate_cfs_file_info_response(missing_metadata, "part.gcode", error));
    CHECK(error.find("filament metadata") != std::string::npos);

    const std::string missing_mapping = R"({"retGcodeFileInfo2":[{"name":"part.gcode","validation_completed":true,"material":"PCTG","materialColors":"#1B04AE","materialIds":"PCTG01","printer_model":"Creality K2 Plus","match":"T1A=  "}]})";
    CHECK_FALSE(CrealityPrint::validate_cfs_file_info_response(missing_mapping, "part.gcode", error));
    CHECK(error.find("filament mapping") != std::string::npos);
}

TEST_CASE("Http digest authentication", "[Http][NotWorking]") {
    Slic3r::Http g = Slic3r::Http::get("https://httpbingo.org/digest-auth/auth/guest/guest");

    g.auth_digest("guest", "guest");

    unsigned status = 0;
    g.on_error([&status](std::string, std::string, unsigned http_status) {
        status = http_status;
    });

    g.on_complete([&status](std::string /* body */, unsigned http_status){
        status = http_status;
    });

    g.perform_sync();

    REQUIRE(status == 200);
}

TEST_CASE("Http basic authentication", "[Http][NotWorking]") {
    Slic3r::Http g = Slic3r::Http::get("https://httpbingo.org/basic-auth/guest/guest");

    g.auth_basic("guest", "guest");

    unsigned status = 0;
    g.on_error([&status](std::string, std::string, unsigned http_status) {
        status = http_status;
    });

    g.on_complete([&status](std::string /* body */, unsigned http_status){
        status = http_status;
    });

    g.perform_sync();

    REQUIRE(status == 200);
}
