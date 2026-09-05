#include <catch2/catch_all.hpp>

#include <array>
#include <memory>
#include <limits>
#include <new>

#include "libslic3r/Print.hpp"
#include "libslic3r/GCode/ConflictChecker.hpp"
#include "test_data.hpp"

using namespace Slic3r;

namespace {
struct PrintWithOriginalConfig : Print {
    const DynamicPrintConfig &original_config() const { return m_ori_full_print_config; }
};
} // namespace

TEST_CASE("Wipe tower collision state starts empty", "[Print][TinMan][WipeTowerState]")
{
    alignas(FakeWipeTower) std::array<unsigned char, sizeof(FakeWipeTower)> storage;
    storage.fill(0x42);
    const auto destroy = [](FakeWipeTower *tower) { tower->~FakeWipeTower(); };
    std::unique_ptr<FakeWipeTower, decltype(destroy)> tower(new (storage.data()) FakeWipeTower, destroy);
    CHECK(tower->pos.isZero());
    CHECK(tower->plate_origin.isZero());
    CHECK(tower->width == 0.f);
    CHECK(tower->height == 0.f);
    CHECK(tower->layer_height == 0.f);
    CHECK(tower->depth == 0.f);
    CHECK(tower->brim_width == 0.f);
    CHECK(tower->rotation_angle == 0.f);
    CHECK(tower->cone_angle == 0.f);
    REQUIRE(tower->height == 0.f);
    CHECK(tower->getTrueExtrusionLayersFromWipeTower().empty());
    CHECK(tower->getFakeExtrusionPathsFromWipeTower().empty());
}

TEST_CASE("Changing wipe tower style replaces collision geometry", "[Print][TinMan][WipeTowerState]")
{
    FakeWipeTower tower;
    SECTION("Legacy walls and rib offset do not survive a type two tower") {
        tower.set_fake_extrusion_data(Vec2f(10, 20), 20, 1, 0.2f, 10, 2, Vec2d::Zero());
        tower.outer_wall[0.2f] = {Polyline{{Point(0, 0), Point(100, 0)}}};
        tower.rib_offset = Vec2f(3, 4);
        tower.set_fake_extrusion_data(Vec2f(30, 40), 25, 1, 0.2f, 15,
                                      {{0.f, 15.f}}, 3, 45, 20, Vec2d::Zero());
        CHECK(tower.outer_wall.empty());
        CHECK(tower.rib_offset.isZero());
        CHECK(tower.rotation_angle == 45.f);
        CHECK(tower.z_and_depth_pairs.size() == 1);
    }
    SECTION("Type two taper and rotation do not survive a legacy tower") {
        tower.set_fake_extrusion_data(Vec2f(30, 40), 25, 1, 0.2f, 15,
                                      {{0.f, 15.f}}, 3, 45, 20, Vec2d::Zero());
        tower.rib_offset = Vec2f(3, 4);
        tower.set_fake_extrusion_data(Vec2f(10, 20), 20, 1, 0.2f, 10, 2, Vec2d::Zero());
        CHECK(tower.z_and_depth_pairs.empty());
        CHECK(tower.rotation_angle == 0.f);
        CHECK(tower.cone_angle == 0.f);
        CHECK(tower.rib_offset.isApprox(Vec2f(3, 4)));
    }
}

TEST_CASE("Cleared wipe tower data has no previous bounds or taper", "[Print][TinMan][WipeTowerState]")
{
    Print print;
    auto &data = const_cast<WipeTowerData &>(print.wipe_tower_data());
    data.height = 25.f;
    data.depth = 20.f;
    data.brim_width = 3.f;
    data.z_and_depth_pairs = {{0.f, 20.f}, {10.f, 15.f}};
    data.bbx = BoundingBoxf(Vec2d(-3, -3), Vec2d(23, 23));
    data.rib_offset = Vec2f(2, 4);
    data.clear();
    CHECK(data.height == 0.f);
    CHECK(data.depth == 0.f);
    CHECK(data.brim_width == 0.f);
    CHECK(data.z_and_depth_pairs.empty());
    CHECK_FALSE(data.bbx.defined);
    CHECK(data.bbx.min.isZero());
    CHECK(data.bbx.max.isZero());
    CHECK(data.rib_offset.isZero());
}

TEST_CASE("Clearing a print removes the previous wipe tower", "[Print][TinMan][WipeTowerState]")
{
    Print print;
    auto &data = const_cast<WipeTowerData &>(print.wipe_tower_data());
    data.height = 25.f;
    data.bbx = BoundingBoxf(Vec2d(10, 10), Vec2d(30, 30));
    auto &fake = const_cast<FakeWipeTower &>(print.get_fake_wipe_tower());
    fake.set_fake_extrusion_data(Vec2f(50, 50), 20, 1, 0.2f, 10, 2, Vec2d::Zero());
    fake.outer_wall[0.2f] = {Polyline{{Point(0, 0), Point(100, 0)}}};
    print.clear();
    CHECK(print.wipe_tower_data().height == 0.f);
    CHECK_FALSE(print.wipe_tower_data().bbx.defined);
    CHECK(print.get_fake_wipe_tower().height == 0.f);
    CHECK(print.get_fake_wipe_tower().outer_wall.empty());
}

TEST_CASE("Constant-depth wipe towers do not need a taper table", "[Print][TinMan][WipeTowerState]")
{
    FakeWipeTower tower;
    tower.set_fake_extrusion_data(Vec2f(30, 40), 20, 1, 0.2f, 10, {}, 0, 90, 0, Vec2d::Zero());
    const auto constant = tower.getFakeExtrusionPathsFromWipeTower2();
    tower.z_and_depth_pairs = {{0.f, 10.f}};
    const auto explicit_depth = tower.getFakeExtrusionPathsFromWipeTower2();
    REQUIRE(constant.size() == 5);
    REQUIRE(explicit_depth.size() == constant.size());
    for (size_t layer = 0; layer < constant.size(); ++layer) {
        REQUIRE(constant[layer].size() == explicit_depth[layer].size());
        for (size_t path = 0; path < constant[layer].size(); ++path)
            CHECK(constant[layer][path].polyline.points == explicit_depth[layer][path].polyline.points);
    }
    const auto box = get_extents(constant.front().front().polyline.to_polyline().points);
    CHECK(std::abs(box.min.x() - scale_(20.)) <= 1.);
    CHECK(std::abs(box.min.y() - scale_(40.)) <= 1.);
    CHECK(std::abs(box.max.x() - scale_(30.)) <= 1.);
    CHECK(std::abs(box.max.y() - scale_(60.)) <= 1.);
}

TEST_CASE("Invalid wipe tower layer heights fail instead of looping", "[Print][TinMan][WipeTowerState]")
{
    FakeWipeTower tower;
    tower.set_fake_extrusion_data(Vec2f(30, 40), 20, 1, 0.2f, 10, {{0.f, 10.f}}, 0, 0, 0, Vec2d::Zero());
    tower.layer_height = GENERATE(0.f, -0.2f, std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN());
    CHECK_THROWS_AS(tower.getFakeExtrusionPathsFromWipeTower(), SlicingError);
    CHECK_THROWS_AS(tower.getFakeExtrusionPathsFromWipeTower2(), SlicingError);
    CHECK_THROWS_AS(tower.getTrueExtrusionLayersFromWipeTower(), SlicingError);
}

TEST_CASE("Invalid wipe tower total heights fail instead of looping", "[Print][TinMan][WipeTowerState]")
{
    FakeWipeTower tower;
    tower.set_fake_extrusion_data(Vec2f(30, 40), 20, 1, 0.2f, 10, {{0.f, 10.f}}, 0, 0, 0, Vec2d::Zero());
    tower.height = GENERATE(-1.f, std::numeric_limits<float>::infinity(), std::numeric_limits<float>::quiet_NaN());
    CHECK_THROWS_AS(tower.getFakeExtrusionPathsFromWipeTower(), SlicingError);
    CHECK_THROWS_AS(tower.getFakeExtrusionPathsFromWipeTower2(), SlicingError);
}

TEST_CASE("Reslicing between tower styles and no tower removes stale geometry", "[Print][TinMan][WipeTowerState]")
{
    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_key_value("filament_diameter", new ConfigOptionFloats{1.75, 1.75});
    config.set_key_value("filament_colour", new ConfigOptionStrings{"#000000", "#FFFFFF"});
    config.set_key_value("filament_settings_id", new ConfigOptionStrings{"Fixture A", "Fixture B"});
    config.set_deserialize_strict({
        {"enable_prime_tower", true},
        {"single_extruder_multi_material", true},
        {"flush_volumes_matrix", "0,60,60,0"},
        {"wipe_tower_type", "type1"},
        {"prime_tower_width", 20},
        {"wipe_tower_x", "100"},
        {"wipe_tower_y", "100"},
        {"layer_height", 0.25},
        {"initial_layer_print_height", 0.25},
        {"timelapse_type", "0"}
    });
    Print print;
    Model model;
    for (int i = 0; i < 2; ++i) {
        auto *object = model.add_object();
        object->add_volume(Test::mesh(Test::TestMesh::cube_20x20x20))->config.set("extruder", i + 1);
        object->add_instance()->set_offset(Vec3d(30 * i, 0, 0));
        object->ensure_on_bed();
    }
    print.set_status_silent();
    print.apply(model, config);
    print.process();
    INFO("prime=" << print.config().enable_prime_tower.value
         << " spiral=" << print.config().spiral_mode.value
         << " diameters=" << print.config().filament_diameter.size()
         << " colors=" << print.config().filament_colour.size()
         << " used=" << print.extruders().size());
    REQUIRE(print.has_wipe_tower());
    REQUIRE_FALSE(print.get_fake_wipe_tower().outer_wall.empty());
    CHECK(print.wipe_tower_data().height > 0.f);
    CHECK(print.wipe_tower_data().bbx.defined);

    config.set_deserialize_strict({{"wipe_tower_type", "type2"}});
    print.apply(model, config);
    print.process();
    REQUIRE(print.has_wipe_tower());
    CHECK(print.get_fake_wipe_tower().outer_wall.empty());
    CHECK_FALSE(print.get_fake_wipe_tower().z_and_depth_pairs.empty());
    CHECK_FALSE(print.get_fake_wipe_tower().getTrueExtrusionLayersFromWipeTower().empty());
    CHECK(print.wipe_tower_data().height > 0.f);
    CHECK(print.wipe_tower_data().bbx.defined);

    config.set_deserialize_strict({{"wipe_tower_type", "type1"}});
    print.apply(model, config);
    print.process();
    REQUIRE(print.has_wipe_tower());
    CHECK_FALSE(print.get_fake_wipe_tower().outer_wall.empty());
    CHECK(print.get_fake_wipe_tower().z_and_depth_pairs.empty());
    CHECK(print.wipe_tower_data().height > 0.f);
    CHECK(print.wipe_tower_data().bbx.defined);

    config.set_deserialize_strict({{"enable_prime_tower", false}});
    print.apply(model, config);
    print.process();
    CHECK_FALSE(print.has_wipe_tower());
    CHECK(print.wipe_tower_data().height == 0.f);
    CHECK_FALSE(print.wipe_tower_data().bbx.defined);
    CHECK(print.get_fake_wipe_tower().getTrueExtrusionLayersFromWipeTower().empty());
}

TEST_CASE("Adding a second material restores the requested prime tower", "[Print][TinMan][WipeTowerReapply]")
{
    const std::string style = GENERATE("type1", "type2");
    DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
    config.set_key_value("filament_diameter", new ConfigOptionFloats{1.75, 1.75});
    config.set_key_value("filament_colour", new ConfigOptionStrings{"#000000", "#FFFFFF"});
    config.set_key_value("filament_settings_id", new ConfigOptionStrings{"Fixture A", "Fixture B"});
    config.set_deserialize_strict({
        {"enable_prime_tower", true},
        {"single_extruder_multi_material", true},
        {"flush_volumes_matrix", "0,60,60,0"},
        {"wipe_tower_type", style},
        {"independent_support_layer_height", true},
        {"layer_height", 0.25},
        {"initial_layer_print_height", 0.25},
        {"timelapse_type", "0"}
    });
    PrintWithOriginalConfig print;
    Model model;
    for (int i = 0; i < 2; ++i) {
        auto *object = model.add_object();
        object->add_volume(Test::mesh(Test::TestMesh::cube_20x20x20))->config.set("extruder", 1);
        object->add_instance()->set_offset(Vec3d(30 * i, 0, 0));
        object->ensure_on_bed();
    }
    print.set_status_silent();
    print.apply(model, config);
    print.process();
    REQUIRE(print.extruders().size() == 1);
    REQUIRE_FALSE(print.has_wipe_tower());
    REQUIRE(config.opt_bool("enable_prime_tower"));
    CHECK_FALSE(print.original_config().opt_bool("enable_prime_tower"));
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);
    for (const auto *object : print.objects())
        CHECK(object->config().independent_support_layer_height.value);

    const bool use_height_range = GENERATE(false, true);
    if (use_height_range) {
        model.objects[1]->layer_config_ranges[{5., 10.}].set("extruder", 2);
        model.objects[1]->layer_config_ranges[{5., 10.}].set("layer_height", 0.25);
    } else
        model.objects[1]->volumes[0]->config.set("extruder", 2);
    print.apply(model, config);
    REQUIRE(print.extruders().size() == 2);
    REQUIRE(print.config().enable_prime_tower.value);
    CHECK(print.original_config().opt_bool("enable_prime_tower"));
    print.process();
    CHECK(print.has_wipe_tower());
    CHECK(print.wipe_tower_data().height > 0.f);
    for (const auto *object : print.objects())
        CHECK_FALSE(object->config().independent_support_layer_height.value);
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);

    if (use_height_range)
        model.objects[1]->layer_config_ranges.clear();
    else
        model.objects[1]->volumes[0]->config.set("extruder", 1);
    print.apply(model, config);
    REQUIRE(print.extruders().size() == 1);
    CHECK_FALSE(print.config().enable_prime_tower.value);
    CHECK_FALSE(print.original_config().opt_bool("enable_prime_tower"));
    for (const auto *object : print.objects())
        CHECK(object->config().independent_support_layer_height.value);
    print.process();
    CHECK_FALSE(print.has_wipe_tower());
    CHECK(print.wipe_tower_data().height == 0.f);
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);
}

TEST_CASE("Sequential tower normalization follows the current object count", "[Print][TinMan][WipeTowerReapply]")
{
    const bool requested = GENERATE(false, true);
    auto config = DynamicPrintConfig::full_print_config();
    config.set_key_value("filament_diameter", new ConfigOptionFloats{1.75, 1.75});
    config.set_key_value("filament_colour", new ConfigOptionStrings{"#000000", "#FFFFFF"});
    config.set_key_value("filament_settings_id", new ConfigOptionStrings{"Fixture A", "Fixture B"});
    config.set_deserialize_strict({
        {"enable_prime_tower", requested},
        {"single_extruder_multi_material", true},
        {"print_sequence", "by object"},
        {"timelapse_type", "0"}
    });
    Model model;
    auto *object = model.add_object();
    for (int i = 0; i < 2; ++i) {
        auto *volume = object->add_volume(Test::mesh(Test::TestMesh::cube_20x20x20));
        volume->config.set("extruder", i + 1);
        volume->set_offset(Vec3d(i * 30, 0, 0));
    }
    object->add_instance();
    object->ensure_on_bed();
    Print print;
    print.set_status_silent();
    print.apply(model, config);
    REQUIRE(print.extruders().size() == 2);
    CHECK(print.config().enable_prime_tower.value == requested);
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);

    auto *second = model.add_object();
    second->add_volume(Test::mesh(Test::TestMesh::cube_20x20x20))->config.set("extruder", 1);
    second->add_instance()->set_offset(Vec3d(80, 0, 0));
    second->ensure_on_bed();
    print.apply(model, config);
    CHECK_FALSE(print.config().enable_prime_tower.value);
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);

    model.delete_object(1);
    print.apply(model, config);
    CHECK(print.config().enable_prime_tower.value == requested);
    CHECK(print.apply(model, config) == Print::APPLY_STATUS_UNCHANGED);
    CHECK(config.opt_bool("enable_prime_tower") == requested);
}
