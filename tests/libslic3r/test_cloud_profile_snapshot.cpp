#include <catch2/catch_all.hpp>
#include <nlohmann/json.hpp>
#include "libslic3r/CloudProfileSnapshot.hpp"

using namespace Slic3r;
using Json = nlohmann::json;

namespace {
Json row(const std::string &id, const std::string &name, const std::string &type = "print")
{
    return {{"id", id}, {"name", name}, {"updated_time", 2200000000LL},
            {"created_time", 2100000000LL},
            {"content", {{"name", name}, {"type", type}, {"layer_height", "0.17"}}}};
}

Json valid_snapshot()
{
    return {{"upserts", Json::array({row("id-a", "Process A")})},
            {"next_cursor", 2300000000LL}, {"deletes", Json::array()}};
}

CloudPresetSnapshot parse(const Json &value)
{
    return tinmanx_parse_cloud_profile_snapshot(200, value.dump(), "fixture-user");
}
} // namespace

TEST_CASE("Full cloud snapshots preserve tuned serialized values and metadata", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    body["upserts"].push_back(row("id-b", "Material B", "filament"));
    body["upserts"][1]["content"]["nozzle_temperature"] = Json::array({235, 245});
    body["upserts"][1]["content"]["filament_retract_length"] = Json::array({nullptr, "0.4"});
    body["upserts"].push_back(row("id-c", "Mixed tool printer", "printer"));
    body["upserts"][2]["content"]["nozzle_diameter"] = "0.4,0.6,0.4,0.6";
    const auto result = parse(body);
    REQUIRE(result.size() == 3);
    CHECK(result.at("Process A").at("layer_height") == "0.17");
    CHECK(result.at("Process A").at("setting_id") == "id-a");
    CHECK(result.at("Process A").at("user_id") == "fixture-user");
    CHECK(result.at("Process A").at("updated_time") == "2200000000");
    CHECK(result.at("Material B").at("nozzle_temperature") == "[235,245]");
    CHECK(result.at("Material B").at("filament_retract_length") == "[null,\"0.4\"]");
    CHECK(result.at("Mixed tool printer").at("nozzle_diameter") == "0.4,0.6,0.4,0.6");
}

TEST_CASE("Only explicit complete empty cloud libraries authorize an empty snapshot", "[CloudSnapshot][TinMan]")
{
    CHECK(parse(Json{{"upserts", Json::array()}}).empty());
    const std::string malformed = GENERATE("{}", "null", "[]", "{\"upserts\":null}", "{\"upserts\":{}}", "bad json");
    CHECK_THROWS(tinmanx_parse_cloud_profile_snapshot(200, malformed, "fixture-user"));
}

TEST_CASE("Full snapshots reject not-modified and failed HTTP responses", "[CloudSnapshot][TinMan]")
{
    const unsigned status = GENERATE(0u, 204u, 304u, 401u, 410u, 429u, 500u);
    CHECK_THROWS(tinmanx_parse_cloud_profile_snapshot(status, valid_snapshot().dump(), "fixture-user"));
    CHECK_THROWS(tinmanx_parse_cloud_profile_snapshot(200, valid_snapshot().dump(), ""));
}

TEST_CASE("Incomplete cloud pages and malformed deletion lists are rejected", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    SECTION("Explicit complete page") { body["has_more"] = false; CHECK(parse(body).size() == 1); }
    SECTION("More pages") { body["has_more"] = true; CHECK_THROWS(parse(body)); }
    SECTION("Invalid page flag") { body["has_more"] = "false"; CHECK_THROWS(parse(body)); }
    SECTION("Valid deleted identity") { body["deletes"] = Json::array({"old-id"}); CHECK(parse(body).size() == 1); }
    SECTION("Invalid deletion list") { body["deletes"] = "old-id"; CHECK_THROWS(parse(body)); }
    SECTION("Invalid deleted identity") { body["deletes"] = Json::array({42}); CHECK_THROWS(parse(body)); }
    SECTION("Empty deleted identity") { body["deletes"] = Json::array({""}); CHECK_THROWS(parse(body)); }
}

TEST_CASE("Cloud snapshots reject malformed records before returning any partial library", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    const std::string invalid = GENERATE("null", "{}", "{\"content\":null}", "{\"content\":[]}", "{\"content\":{\"type\":\"unknown\"}}");
    body["upserts"].push_back(Json::parse(invalid));
    CloudPresetSnapshot published = {{"Existing", {{"type", "print"}, {"layer_height", "0.17"}}}};
    const auto before = published;
    CHECK_THROWS(published = parse(body));
    CHECK(published == before);
    CHECK(parse(valid_snapshot()).size() == 1);
}

TEST_CASE("Cloud snapshot identities cannot alias or cross accounts", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    auto &record = body["upserts"][0];
    SECTION("Matching content identity") { record["content"]["setting_id"] = "id-a"; CHECK(parse(body).size() == 1); }
    SECTION("Conflicting identity") { record["content"]["setting_id"] = "other-id"; CHECK_THROWS(parse(body)); }
    SECTION("Missing identity") { record.erase("id"); CHECK_THROWS(parse(body)); }
    SECTION("Content identity fallback") { record.erase("id"); record["content"]["setting_id"] = "id-a"; CHECK(parse(body).size() == 1); }
    SECTION("Wrong identity type") { record["id"] = 42; CHECK_THROWS(parse(body)); }
    SECTION("Other account") { record["content"]["user_id"] = "other-user"; CHECK_THROWS(parse(body)); }
    SECTION("Same account") { record["content"]["user_id"] = "fixture-user"; CHECK(parse(body).size() == 1); }
    SECTION("Duplicate name") { body["upserts"].push_back(row("id-b", "Process A")); CHECK_THROWS(parse(body)); }
    SECTION("Duplicate identity") { body["upserts"].push_back(row("id-a", "Process B")); CHECK_THROWS(parse(body)); }
    SECTION("Invalid name") { record["content"]["name"] = Json::array(); CHECK_THROWS(parse(body)); }
}

TEST_CASE("Cloud snapshot names retain legacy fallbacks", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    body["upserts"][0]["content"].erase("name");
    CHECK(parse(body).count("Process A") == 1);
    body["upserts"][0].erase("name");
    CHECK(parse(body).count("id-a") == 1);
}

TEST_CASE("Cloud timestamps reject invalid signedness types and ranges", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    const std::string invalid = GENERATE("-1", "1.5", "true", "null", "18446744073709551615");
    const std::string field = GENERATE("updated_time", "created_time", "next_cursor");
    if (field == "next_cursor") body[field] = Json::parse(invalid);
    else body["upserts"][0][field] = Json::parse(invalid);
    CHECK_THROWS(parse(body));
}

TEST_CASE("Cloud content timestamp strings must be complete nonnegative decimals", "[CloudSnapshot][TinMan]")
{
    auto body = valid_snapshot();
    const std::string invalid = GENERATE("", "-1", "+1", "1x", " 1", "1.5", "9223372036854775808");
    body["upserts"][0]["content"]["updated_time"] = invalid;
    CHECK_THROWS(parse(body));
    body["upserts"][0]["content"]["updated_time"] = "2300000000";
    CHECK(parse(body).at("Process A").at("updated_time") == "2300000000");
}

TEST_CASE("Cloud account stamps reject stale and logged-out queued results", "[CloudSnapshot][TinMan]")
{
    const CloudProfileSession requested{"fixture-user", 3, true};
    CHECK(requested.matches({"fixture-user", 3, true}));
    CHECK_FALSE(requested.matches({"other-user", 3, true}));
    CHECK_FALSE(requested.matches({"fixture-user", 4, true}));
    CHECK_FALSE(requested.matches({"fixture-user", 3, false}));
    CHECK_FALSE(requested.matches({"", 3, true}));
    CHECK_FALSE(CloudProfileSession{}.matches({"", 0, true}));
    CHECK_FALSE(CloudProfileSession{"fixture-user", 3, false}.matches(requested));
}
