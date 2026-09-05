#include <catch2/catch_all.hpp>
#include <cmath>
#include <limits>

#include "libslic3r/Exception.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/Slicing.hpp"

using namespace Slic3r;

namespace {
SlicingParameters parameters()
{
    SlicingParameters result;
    result.valid = true;
    result.layer_height = 0.25;
    result.first_object_layer_height = 0.25;
    result.first_print_layer_height = 0.25;
    result.min_layer_height = 0.1;
    result.max_layer_height = 0.3;
    result.object_print_z_max = 20.;
    result.object_print_z_uncompensated_max = 20.;
    result.object_shrinkage_compensation_z = 1.;
    return result;
}
} // namespace

TEST_CASE("Material-only height ranges inherit the normal layer height", "[Slicing][LayerRangeRecovery][TinMan]")
{
    const auto params = parameters();
    t_layer_config_ranges ranges;
    ranges[{5., 10.}].set("extruder", 2);
    const auto implicit = layer_height_profile_from_ranges(params, ranges);
    CHECK_FALSE(ranges.at({5., 10.}).has("layer_height"));
    ranges.at({5., 10.}).set("layer_height", params.layer_height);
    CHECK(implicit == layer_height_profile_from_ranges(params, ranges));
    CHECK(implicit == layer_height_profile_from_ranges(params, {}));
    const auto layers = generate_object_layers(params, implicit, false);
    CHECK(layers.size() == 160);
}

TEST_CASE("Invalid explicit range heights produce a slicing error", "[Slicing][LayerRangeRecovery][TinMan]")
{
    t_layer_config_ranges ranges;
    const double invalid = GENERATE(0., -0.1, std::numeric_limits<double>::infinity(), std::numeric_limits<double>::quiet_NaN());
    ranges[{5., 10.}].set("layer_height", invalid);
    CHECK_THROWS_AS(layer_height_profile_from_ranges(parameters(), ranges), SlicingError);
}

TEST_CASE("Wrongly typed range heights are rejected without changing input", "[Slicing][LayerRangeRecovery][TinMan]")
{
    t_layer_config_ranges ranges;
    ranges[{5., 10.}].set_key_value("layer_height", new ConfigOptionString("invalid"));
    CHECK_THROWS_AS(layer_height_profile_from_ranges(parameters(), ranges), SlicingError);
    CHECK(ranges.at({5., 10.}).option("layer_height")->serialize() == "invalid");
}

TEST_CASE("Explicit range heights retain their intended transitions", "[Slicing][LayerRangeRecovery][TinMan]")
{
    t_layer_config_ranges ranges;
    ranges[{5., 10.}].set("layer_height", 0.2);
    const auto profile = layer_height_profile_from_ranges(parameters(), ranges);
    REQUIRE(profile.size() % 2 == 0);
    bool saw_override = false;
    bool saw_default = false;
    for (size_t i = 0; i < profile.size(); i += 2) {
        CHECK(std::isfinite(profile[i]));
        CHECK(profile[i + 1] > 0.);
        if (i > 0) CHECK(profile[i] >= profile[i - 2]);
        saw_override |= profile[i + 1] == 0.2;
        saw_default |= profile[i + 1] == 0.25;
    }
    CHECK(saw_override);
    CHECK(saw_default);
    CHECK(ranges.at({5., 10.}).option("layer_height")->getFloat() == 0.2);
}
