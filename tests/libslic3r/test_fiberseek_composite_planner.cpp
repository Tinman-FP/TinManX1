#include <catch2/catch_approx.hpp>
#include <catch2/catch_test_macros.hpp>

#include "libslic3r/ClipperUtils.hpp"
#include "libslic3r/FiberseekCompositePlanner.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/Surface.hpp"

#include <cmath>
#include <set>
#include <utility>
#include <vector>

using namespace Slic3r;
using namespace Slic3r::FiberseekComposite;

static bool contains_polyline_with_tolerance(const ExPolygon &region, const Polyline &polyline, double tolerance_mm)
{
    if (region.contains(polyline))
        return true;

    const ExPolygons expanded_regions = offset_ex(region, float(scale_(tolerance_mm)));
    for (const ExPolygon &expanded_region : expanded_regions)
        if (expanded_region.contains(polyline))
            return true;
    return false;
}

static CompositeRoute test_route_from_candidate(
    const CompositeCandidate &candidate,
    const CompositeRouteGraphOptions &options,
    std::size_t route_id)
{
    CompositeRoute route;
    route.id = route_id;
    route.layer_id = options.layer_id;
    route.candidate_ids.push_back(candidate.id);
    route.ordered_segments.push_back(candidate.polyline);
    route.cut_distance_mm = options.cut_distance_mm;
    route.coalesce_transition_length_mm = options.coalesce_transition_length_mm;
    route.cut_safe_threshold_mm = std::max(options.min_route_length_mm, options.min_segment_length_mm);
    route.plastic_mm_per_mm = options.plastic_mm_per_mm;
    route.fiber_mm_per_mm = options.fiber_mm_per_mm;

    CompositeRouteSegment segment;
    segment.phase = CompositeRoutePhase::Normal;
    segment.polyline = candidate.polyline;
    segment.length_mm = polyline_length_mm(candidate.polyline);
    segment.plastic_mm_per_mm = options.plastic_mm_per_mm;
    segment.fiber_mm_per_mm = options.fiber_mm_per_mm;
    segment.emits_plastic = true;
    segment.emits_fiber = true;
    route.planned_segments.push_back(std::move(segment));

    refresh_route_metrics(route);
    return route;
}

TEST_CASE("FibreSeek composite route metrics classify open routes", "[FiberseekComposite]")
{
    Polylines route {
        Polyline {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(80.0, 0.0),
            Point::new_scale(80.0, 20.0),
        },
    };
    Polylines tail {
        Polyline {
            Point::new_scale(80.0, 20.0),
            Point::new_scale(90.0, 20.0),
        },
    };

    const CompositeRouteMetrics metrics = measure_route(route, tail, 0.25, 1.0);

    CHECK(metrics.length_mm == Catch::Approx(100.0));
    CHECK(metrics.tail_length_mm == Catch::Approx(10.0));
    CHECK(metrics.fiber_positive_length_mm == Catch::Approx(100.0));
    CHECK(metrics.matrix_positive_length_mm == Catch::Approx(110.0));
    CHECK(metrics.closure_gap_mm == Catch::Approx(std::sqrt(6800.0)));
    CHECK(metrics.bbox_span_x_mm == Catch::Approx(80.0));
    CHECK(metrics.bbox_span_y_mm == Catch::Approx(20.0));
    CHECK(metrics.shape == CompositeRouteShape::OpenPath);
}

TEST_CASE("FibreSeek composite route metrics classify closed loops", "[FiberseekComposite]")
{
    Polylines route {
        Polyline {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(10.0, 0.0),
            Point::new_scale(10.0, 10.0),
            Point::new_scale(0.0, 10.0),
            Point::new_scale(0.0, 0.0),
        },
    };

    CompositeRoute composite_route;
    composite_route.ordered_segments = route;
    composite_route.plastic_mm_per_mm = 0.25;
    composite_route.fiber_mm_per_mm = 1.0;
    composite_route.cut_safe_threshold_mm = 55.0;
    refresh_route_metrics(composite_route);

    CHECK(composite_route.length_mm == Catch::Approx(40.0));
    CHECK(composite_route.closure_gap_mm == Catch::Approx(0.0));
    CHECK(composite_route.shape == CompositeRouteShape::ClosedLoop);
    CHECK(composite_route.is_closed_loop());
    CHECK_FALSE(composite_route.is_cut_safe());
}

TEST_CASE("FibreSeek layer stitch merges legal perimeter and infill roads", "[FiberseekComposite]")
{
    const auto printable_region = std::make_shared<ExPolygon>(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(100.0, 0.0),
        Point::new_scale(100.0, 100.0),
        Point::new_scale(0.0, 100.0),
    });

    CompositeCandidate perimeter;
    perimeter.id = 1;
    perimeter.layer_id = 7;
    perimeter.object_id = 2;
    perimeter.island_id = 3;
    perimeter.region_id = 4;
    perimeter.family = CandidateFamily::Perimeter;
    perimeter.polyline = Polyline {
        Point::new_scale(10.0, 10.0),
        Point::new_scale(70.0, 10.0),
        Point::new_scale(70.0, 40.0),
        Point::new_scale(10.0, 40.0),
        Point::new_scale(10.0, 10.0),
    };
    perimeter.length_mm = polyline_length_mm(perimeter.polyline);
    perimeter.has_printable_region = true;
    perimeter.printable_region_ref = printable_region;

    CompositeCandidate infill;
    infill.id = 2;
    infill.layer_id = perimeter.layer_id;
    infill.object_id = perimeter.object_id;
    infill.island_id = perimeter.island_id;
    infill.region_id = perimeter.region_id;
    infill.family = CandidateFamily::SolidInfill;
    infill.polyline = Polyline {
        Point::new_scale(15.0, 10.0),
        Point::new_scale(85.0, 10.0),
    };
    infill.length_mm = polyline_length_mm(infill.polyline);
    infill.has_printable_region = true;
    infill.printable_region_ref = printable_region;

    CompositeRouteGraphOptions options;
    options.layer_id = perimeter.layer_id;
    options.cut_distance_mm = 58.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 55.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = 4.2;
    options.coalesce_transition_length_mm = 12.0;
    options.route_stitch_transition_length_mm = 8.0;
    options.plastic_mm_per_mm = 1.0;
    options.fiber_mm_per_mm = 1.0;

    CompositeLayerDiagnostic diagnostic;
    diagnostic.layer_id = perimeter.layer_id;
    diagnostic.object_id = perimeter.object_id;
    diagnostic.region_id = perimeter.region_id;
    diagnostic.candidates = { perimeter, infill };
    diagnostic.routes.push_back(test_route_from_candidate(perimeter, options, 0));
    diagnostic.routes.push_back(test_route_from_candidate(infill, options, 1));

    stitch_composite_layer_routes(diagnostic, options);

    REQUIRE(diagnostic.routes.size() == 1);
    CHECK(diagnostic.routes.front().candidate_ids.size() == 2);
    CHECK(diagnostic.routes.front().length_mm == Catch::Approx(perimeter.length_mm + 5.0 + infill.length_mm));
    CHECK(diagnostic.routes.front().fiber_positive_length_mm == Catch::Approx(perimeter.length_mm + 5.0 + infill.length_mm));
    CHECK(diagnostic.routes.front().matrix_positive_length_mm == Catch::Approx(perimeter.length_mm + 5.0 + infill.length_mm));
    CHECK(diagnostic.routes.front().is_release_safe());
}

TEST_CASE("FibreSeek route shape uses route-specific short threshold", "[FiberseekComposite]")
{
    Polylines route {
        Polyline {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(40.0, 0.0),
            Point::new_scale(40.0, 20.0),
        },
    };

    CompositeRoute composite_route;
    composite_route.ordered_segments = route;
    composite_route.plastic_mm_per_mm = 0.25;
    composite_route.fiber_mm_per_mm = 1.0;
    composite_route.cut_safe_threshold_mm = 65.0;
    refresh_route_metrics(composite_route);

    CHECK(composite_route.length_mm == Catch::Approx(60.0));
    CHECK(composite_route.shape == CompositeRouteShape::ShortOpenPath);
    CHECK_FALSE(composite_route.is_cut_safe());
}


TEST_CASE("FibreSeek planned segments override route material metrics", "[FiberseekComposite]")
{
    CompositeRoute route;
    route.ordered_segments = {
        Polyline {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(70.0, 0.0),
        },
    };
    route.plastic_mm_per_mm = 0.25;
    route.fiber_mm_per_mm = 1.0;
    route.planned_segments = {
        {CompositeRoutePhase::Normal, {}, 20.0, 0.25, 1.0, 20.0, 20.0, 0.0, 0.0, true, true},
        {CompositeRoutePhase::PostCutTail, {}, 8.0, 0.25, 0.0, 20.0, 20.0, 0.0, 0.0, true, false},
        {CompositeRoutePhase::Unknown, {}, 5.0, 0.0, 0.0, 20.0, 20.0, 0.0, 0.0, false, false},
    };

    refresh_route_metrics(route);

    CHECK(route.length_mm == Catch::Approx(70.0));
    CHECK(route.fiber_positive_length_mm == Catch::Approx(20.0));
    CHECK(route.matrix_positive_length_mm == Catch::Approx(28.0));
    CHECK(route.travel_length_mm == Catch::Approx(5.0));
    CHECK(route.shape == CompositeRouteShape::LineOrTail);
}

TEST_CASE("FibreSeek candidates preserve polyline ownership metadata", "[FiberseekComposite]")
{
    Polylines polylines {
        Polyline {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(10.0, 0.0),
        },
        Polyline {
            Point::new_scale(20.0, 0.0),
        },
        Polyline {
            Point::new_scale(30.0, 0.0),
            Point::new_scale(40.0, 0.0),
        },
    };

    const std::vector<CompositeCandidate> candidates = make_candidates_from_polylines(
        polylines, CandidateFamily::IsogridInfill, 7, 2, 5, 3, 100);

    REQUIRE(candidates.size() == 2);
    CHECK(candidates[0].id == 100);
    CHECK(candidates[1].id == 101);
    CHECK(candidates[0].layer_id == 7);
    CHECK(candidates[0].object_id == 2);
    CHECK(candidates[0].island_id == 5);
    CHECK(candidates[0].region_id == 3);
    CHECK(candidates[0].family == CandidateFamily::IsogridInfill);
    CHECK(candidates[0].length_mm == Catch::Approx(10.0));
}

TEST_CASE("FibreSeek surface fill adapter converts slicer infill into owned candidates", "[FiberseekComposite]")
{
    Surface surface(
        stInternalSolid,
        ExPolygon(Polygon {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(40.0, 0.0),
            Point::new_scale(40.0, 80.0),
            Point::new_scale(0.0, 80.0),
        }));

    CompositeSurfaceFillOptions options;
    options.layer_id = 11;
    options.object_id = 2;
    options.island_id = 3;
    options.region_id = 4;
    options.first_candidate_id = 500;
    options.pattern = ipRectilinear;
    options.spacing_mm = 10.0;
    options.density = 1.0;
    options.angle_rad = 0.0;
    options.connect_to_perimeters = false;
    options.bounding_box = get_extents(surface.expolygon.contour);

    const std::vector<CompositeCandidate> candidates = make_candidates_from_surface_fill(surface, options);

    REQUIRE(!candidates.empty());
    CHECK(candidates.front().id == 500);
    CHECK(candidates.front().layer_id == 11);
    CHECK(candidates.front().object_id == 2);
    CHECK(candidates.front().island_id == 3);
    CHECK(candidates.front().region_id == 4);
    CHECK(candidates.front().family == CandidateFamily::SolidInfill);
    for (const CompositeCandidate &candidate : candidates) {
        CHECK(candidate.length_mm > 0.0);
        REQUIRE(candidate.has_printable_region);
        REQUIRE(candidate.printable_region_ref);
        CHECK(contains_polyline_with_tolerance(*candidate.printable_region_ref, candidate.polyline, 0.05));
    }
}

TEST_CASE("FibreSeek solid surface fill keeps Rocket-style segment candidates around holes", "[FiberseekComposite]")
{
    ExPolygon region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(100.0, 0.0),
        Point::new_scale(100.0, 60.0),
        Point::new_scale(0.0, 60.0),
    });
    region.holes.push_back(Polygon {
        Point::new_scale(40.0, 20.0),
        Point::new_scale(60.0, 20.0),
        Point::new_scale(60.0, 40.0),
        Point::new_scale(40.0, 40.0),
    });

    Surface surface(stInternalSolid, region);

    CompositeSurfaceFillOptions options;
    options.layer_id = 12;
    options.object_id = 3;
    options.island_id = 4;
    options.region_id = 5;
    options.first_candidate_id = 900;
    options.family = CandidateFamily::SolidInfill;
    options.pattern = ipRectilinear;
    options.spacing_mm = 10.0;
    options.density = 1.0;
    options.angle_rad = 0.0;
    options.fixed_angle = true;
    options.connect_to_perimeters = false;
    options.adjust_spacing = false;
    options.bounding_box = get_extents(surface.expolygon.contour);

    const std::vector<CompositeCandidate> candidates = make_candidates_from_surface_fill(surface, options);

    REQUIRE(!candidates.empty());
    CHECK(candidates.front().id == 900);
    bool saw_hole_clipped_segment = false;
    for (const CompositeCandidate &candidate : candidates) {
        CHECK(candidate.family == CandidateFamily::SolidInfill);
        CHECK(candidate.layer_id == 12);
        CHECK(candidate.object_id == 3);
        CHECK(candidate.island_id == 4);
        CHECK(candidate.region_id == 5);
        CHECK(candidate.has_printable_region);
        REQUIRE(candidate.printable_region_ref);
        CHECK(candidate.polyline.points.size() == 2);
        CHECK(contains_polyline_with_tolerance(*candidate.printable_region_ref, candidate.polyline, 0.05));
        if (candidate.length_mm < 55.0)
            saw_hole_clipped_segment = true;
    }
    CHECK(saw_hole_clipped_segment);
}

TEST_CASE("FibreSeek surface fill planner produces layer diagnostics", "[FiberseekComposite]")
{
    std::vector<Surface> surfaces;
    surfaces.emplace_back(
        stInternalSolid,
        ExPolygon(Polygon {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(40.0, 0.0),
            Point::new_scale(40.0, 80.0),
            Point::new_scale(0.0, 80.0),
        }));
    surfaces.emplace_back(
        stInternalSolid,
        ExPolygon(Polygon {
            Point::new_scale(50.0, 0.0),
            Point::new_scale(90.0, 0.0),
            Point::new_scale(90.0, 80.0),
            Point::new_scale(50.0, 80.0),
        }));

    std::vector<const Surface *> surface_ptrs;
    for (const Surface &surface : surfaces)
        surface_ptrs.push_back(&surface);

    CompositeSurfaceFillOptions surface_options;
    surface_options.layer_id = 12;
    surface_options.object_id = 4;
    surface_options.region_id = 1;
    surface_options.first_candidate_id = 700;
    surface_options.pattern = ipRectilinear;
    surface_options.spacing_mm = 10.0;
    surface_options.density = 1.0;
    surface_options.bounding_box = BoundingBox(Point::new_scale(0.0, 0.0), Point::new_scale(90.0, 80.0));

    CompositeRouteGraphOptions route_options;
    route_options.cut_distance_mm = 20.0;
    route_options.cut_safety_margin_mm = 0.0;
    route_options.min_segment_length_mm = 5.0;
    route_options.max_transition_length_mm = rocket_style_transition_limit_mm(10.0);

    const CompositeLayerDiagnostic diagnostic = plan_surface_fill_routes(surface_ptrs, surface_options, route_options);

    CHECK(diagnostic.layer_id == 12);
    CHECK(diagnostic.object_id == 4);
    CHECK(diagnostic.region_id == 1);
    CHECK(!diagnostic.candidates.empty());
    CHECK(!diagnostic.routes.empty());
    CHECK(diagnostic.direct_candidate_count == diagnostic.candidates.size());

    std::set<std::size_t> island_ids;
    for (const CompositeCandidate &candidate : diagnostic.candidates)
        island_ids.insert(candidate.island_id);
    CHECK(island_ids.size() == surfaces.size());
}

TEST_CASE("FibreSeek perimeter planning emits outer and hole routes", "[FiberseekComposite]")
{
    ExPolygon region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(80.0, 0.0),
        Point::new_scale(80.0, 80.0),
        Point::new_scale(0.0, 80.0),
    });
    region.holes.push_back(Polygon {
        Point::new_scale(25.0, 25.0),
        Point::new_scale(55.0, 25.0),
        Point::new_scale(55.0, 55.0),
        Point::new_scale(25.0, 55.0),
    });

    CompositePerimeterOptions perimeter_options;
    perimeter_options.layer_id = 12;
    perimeter_options.object_id = 4;
    perimeter_options.region_id = 1;
    perimeter_options.first_candidate_id = 700;
    perimeter_options.first_route_id = 40;
    perimeter_options.inset_mm = 0.0;
    perimeter_options.min_route_length_mm = 20.0;
    perimeter_options.outer_loop_count = 1;
    perimeter_options.inner_loop_count = 1;

    CompositeRouteGraphOptions route_options;
    route_options.cut_distance_mm = 10.0;
    route_options.cut_safety_margin_mm = 0.0;
    route_options.plastic_mm_per_mm = 1.0;
    route_options.fiber_mm_per_mm = 1.0;

    const CompositeLayerDiagnostic diagnostic =
        plan_perimeter_routes_from_expolygons({ region }, perimeter_options, route_options);

    REQUIRE(diagnostic.candidates.size() == 2);
    REQUIRE(diagnostic.routes.size() == 2);
    CHECK(diagnostic.candidates[0].family == CandidateFamily::Perimeter);
    CHECK(diagnostic.candidates[1].family == CandidateFamily::Perimeter);
    CHECK(diagnostic.candidates[0].id == 700);
    CHECK(diagnostic.candidates[1].id == 701);
    CHECK(diagnostic.routes[0].id == 40);
    CHECK(diagnostic.routes[1].id == 41);
    CHECK(diagnostic.routes[0].shape == CompositeRouteShape::ClosedLoop);
    CHECK(diagnostic.routes[1].shape == CompositeRouteShape::ClosedLoop);
    CHECK(diagnostic.routes[0].fiber_positive_length_mm == Catch::Approx(320.0));
    CHECK(diagnostic.routes[1].fiber_positive_length_mm == Catch::Approx(120.0));
}

TEST_CASE("FibreSeek layer diagnostics track ownership scope", "[FiberseekComposite]")
{
    CompositeLayerDiagnostic diagnostic;
    diagnostic.layer_id = 12;
    diagnostic.object_id = 2;
    diagnostic.region_id = 1;

    CHECK(diagnostic.empty());

    CompositeRoute route;
    route.layer_id = diagnostic.layer_id;
    route.id = 42;
    diagnostic.routes.push_back(route);

    CHECK_FALSE(diagnostic.empty());
    CHECK(diagnostic.routes.front().id == 42);
    CHECK(diagnostic.object_id == 2);
    CHECK(diagnostic.region_id == 1);
}

TEST_CASE("FibreSeek graph selector joins candidates into a cut-safe open route", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 10;
        candidate.layer_id = 4;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 25.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 4;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.graph_component_count == 1);
    CHECK(result.routes.front().candidate_ids.size() == 3);
    CHECK(result.routes.front().length_mm == Catch::Approx(77.0));
    CHECK(result.routes.front().is_cut_safe());
    CHECK(result.routes.front().shape == CompositeRouteShape::OpenPath);
}

TEST_CASE("FibreSeek route legality uses mechanical minimum independent of cut distance", "[FiberseekComposite]")
{
    CompositeCandidate candidate;
    candidate.id = 60;
    candidate.layer_id = 6;
    candidate.family = CandidateFamily::SolidInfill;
    candidate.polyline = Polyline {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(56.0, 0.0),
    };
    candidate.length_mm = polyline_length_mm(candidate.polyline);

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 55.0;
    options.min_route_length_mm = 55.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates({ candidate }, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.routes.front().length_mm == Catch::Approx(56.0));
    CHECK(result.routes.front().cut_distance_mm == Catch::Approx(58.0));
    CHECK(result.routes.front().cut_safe_threshold_mm == Catch::Approx(55.0));
    CHECK(result.routes.front().is_cut_safe());
}

TEST_CASE("FibreSeek row graph preserves endpoint-continuous route orientation", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 20;
        candidate.layer_id = 4;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 25.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 4;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.routes.front().candidate_ids.size() == 3);
    CHECK(result.routes.front().length_mm == Catch::Approx(77.0));
}

TEST_CASE("FibreSeek graph selector returns isolated non-cut-safe candidates as plastic fallback", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 2; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 1;
        candidate.layer_id = 9;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i) * 20.0, 0.0),
            Point::new_scale(double(i) * 20.0, 25.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 9;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    CHECK(result.routes.empty());
    REQUIRE(result.fallbacks.size() == 2);
    CHECK(result.graph_component_count == 2);
    CHECK(result.fallbacks.front().reason == FallbackReason::ShorterThanCutSafeThreshold);
}

TEST_CASE("FibreSeek solid fallback creates Rocket-style paired plastic substitutions", "[FiberseekComposite]")
{
    ExPolygon printable_region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(10.0, 0.0),
        Point::new_scale(10.0, 20.0),
        Point::new_scale(0.0, 20.0),
    });

    CompositeCandidate candidate;
    candidate.id = 31;
    candidate.layer_id = 9;
    candidate.family = CandidateFamily::SolidInfill;
    candidate.polyline = Polyline {
        Point::new_scale(5.0, 5.0),
        Point::new_scale(5.0, 15.0),
    };
    candidate.length_mm = polyline_length_mm(candidate.polyline);
    candidate.has_printable_region = true;
    candidate.printable_region = printable_region;
    candidate.fallback_role = erInternalInfill;
    candidate.fallback_line_width_mm = 0.6;

    CompositeRouteGraphOptions options;
    options.layer_id = 9;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates({ candidate }, options);

    CHECK(result.routes.empty());
    REQUIRE(result.fallbacks.size() == 1);
    CHECK(result.fallbacks.front().reason == FallbackReason::ShorterThanCutSafeThreshold);
    REQUIRE(result.fallbacks.front().replacement_segments.size() == 2);
    CHECK(polylines_length_mm(result.fallbacks.front().replacement_segments) == Catch::Approx(40.0).margin(0.1));
}

TEST_CASE("FibreSeek short candidates are prolonged against the printable island before fallback", "[FiberseekComposite]")
{
    ExPolygon printable_region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(10.0, 0.0),
        Point::new_scale(10.0, 20.0),
        Point::new_scale(0.0, 20.0),
    });

    CompositeCandidate candidate;
    candidate.id = 32;
    candidate.layer_id = 9;
    candidate.family = CandidateFamily::SolidInfill;
    candidate.polyline = Polyline {
        Point::new_scale(5.0, 8.0),
        Point::new_scale(5.0, 12.0),
    };
    candidate.length_mm = polyline_length_mm(candidate.polyline);
    candidate.has_printable_region = true;
    candidate.printable_region = printable_region;
    candidate.fallback_role = erInternalInfill;
    candidate.fallback_line_width_mm = 0.6;

    CompositeRouteGraphOptions options;
    options.layer_id = 9;
    options.cut_distance_mm = 15.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates({ candidate }, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.short_candidate_count == 0);
    CHECK(result.routes.front().length_mm == Catch::Approx(20.0).margin(0.1));
    REQUIRE(result.routes.front().ordered_segments.size() == 1);
    CHECK(polyline_length_mm(result.routes.front().ordered_segments.front()) == Catch::Approx(20.0).margin(0.1));
}

TEST_CASE("FibreSeek surface planner adds residual plastic refill around accepted fiber bands", "[FiberseekComposite]")
{
    Surface surface(stInternalSolid, ExPolygon(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(24.0, 0.0),
        Point::new_scale(24.0, 24.0),
        Point::new_scale(0.0, 24.0),
    }));

    CompositeSurfaceFillOptions surface_options;
    surface_options.family = CandidateFamily::SolidInfill;
    surface_options.layer_id = 9;
    surface_options.object_id = 1;
    surface_options.region_id = 2;
    surface_options.pattern = ipRectilinear;
    surface_options.density = 1.0;
    surface_options.spacing_mm = 12.0;
    surface_options.fiber_line_width_mm = 0.8;
    surface_options.fallback_solid_line_width_mm = 0.6;
    surface_options.fallback_infill_line_width_mm = 0.6;
    surface_options.angle_rad = 0.0;
    surface_options.fixed_angle = true;
    surface_options.adjust_spacing = false;
    surface_options.residual_plastic_refill_enabled = true;
    surface_options.bounding_box.merge(Point::new_scale(0.0, 0.0));
    surface_options.bounding_box.merge(Point::new_scale(24.0, 24.0));

    CompositeRouteGraphOptions route_options;
    route_options.layer_id = 9;
    route_options.cut_distance_mm = 15.0;
    route_options.cut_safety_margin_mm = 0.0;
    route_options.min_segment_length_mm = 10.0;
    route_options.min_route_length_mm = 10.0;
    route_options.line_spacing_mm = surface_options.spacing_mm;
    route_options.max_transition_length_mm = rocket_style_transition_limit_mm(0.8);
    route_options.plastic_mm_per_mm = 1.0;
    route_options.fiber_mm_per_mm = 1.0;
    route_options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeLayerDiagnostic diagnostic = plan_surface_fill_routes({ &surface }, surface_options, route_options);

    REQUIRE_FALSE(diagnostic.routes.empty());
    const auto residual_it = std::find_if(
        diagnostic.fallbacks.begin(),
        diagnostic.fallbacks.end(),
        [](const CompositeFallback &fallback) {
            return fallback.reason == FallbackReason::ResidualPlasticRefill;
        });
    REQUIRE(residual_it != diagnostic.fallbacks.end());
    CHECK(residual_it->extrusion_role == erSolidInfill);
    CHECK_FALSE(residual_it->replacement_segments.empty());
}

TEST_CASE("FibreSeek graph selector never joins separate printable islands", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 2; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 1;
        candidate.layer_id = 9;
        candidate.object_id = 1;
        candidate.region_id = 2;
        candidate.island_id = i;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 40.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 9;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    CHECK(result.routes.empty());
    REQUIRE(result.fallbacks.size() == 2);
    CHECK(result.graph_component_count == 2);
}

TEST_CASE("FibreSeek graph selector rejects sub-minimum and unsafe candidates before graphing", "[FiberseekComposite]")
{
    CompositeCandidate short_candidate;
    short_candidate.id = 21;
    short_candidate.layer_id = 2;
    short_candidate.family = CandidateFamily::SolidInfill;
    short_candidate.polyline = Polyline {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(0.0, 5.0),
    };
    short_candidate.length_mm = polyline_length_mm(short_candidate.polyline);

    CompositeCandidate crossing_candidate;
    crossing_candidate.id = 22;
    crossing_candidate.layer_id = 2;
    crossing_candidate.family = CandidateFamily::SolidInfill;
    crossing_candidate.legal_containment = false;
    crossing_candidate.polyline = Polyline {
        Point::new_scale(1.0, 0.0),
        Point::new_scale(1.0, 80.0),
    };
    crossing_candidate.length_mm = polyline_length_mm(crossing_candidate.polyline);

    CompositeRouteGraphOptions options;
    options.layer_id = 2;
    options.min_segment_length_mm = 10.0;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(
        {short_candidate, crossing_candidate}, options);

    CHECK(result.routes.empty());
    REQUIRE(result.fallbacks.size() == 2);
    CHECK(result.short_candidate_count == 1);
    CHECK(result.fallbacks[0].reason == FallbackReason::ShorterThanCutSafeThreshold);
    CHECK(result.fallbacks[1].reason == FallbackReason::UnsupportedVoidCrossing);
}

TEST_CASE("FibreSeek row graph can combine short adjacent rows into a cut-safe route", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 50;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 8.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 20.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 10.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.short_candidate_count == 3);
    CHECK(result.graph_component_count == 1);
    CHECK(result.routes.front().candidate_ids.size() == 3);
    CHECK(result.routes.front().length_mm == Catch::Approx(26.0));
    REQUIRE(result.routes.front().planned_segments.size() == 5);
    CHECK(result.routes.front().planned_segments[0].phase == CompositeRoutePhase::Normal);
    CHECK(result.routes.front().planned_segments[1].phase == CompositeRoutePhase::SlowTurn);
    CHECK(result.routes.front().planned_segments[1].length_mm == Catch::Approx(1.0));
    CHECK(result.routes.front().fiber_positive_length_mm == Catch::Approx(26.0));
    CHECK(result.routes.front().matrix_positive_length_mm == Catch::Approx(26.0));
    CHECK(result.routes.front().travel_length_mm == Catch::Approx(0.0));
    CHECK(result.routes.front().is_cut_safe());
}

TEST_CASE("FibreSeek row graph coalescing joins wider legal row gaps", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 2; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 52;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i) * 7.0, 0.0),
            Point::new_scale(double(i) * 7.0, 30.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult strict_result = select_composite_routes_from_candidates(candidates, options);
    CHECK(strict_result.routes.empty());
    REQUIRE(strict_result.fallbacks.size() == 2);

    options.coalesce_transition_length_mm = 12.0;
    const CompositeRouteGraphResult coalesced_result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(coalesced_result.routes.size() == 1);
    CHECK(coalesced_result.fallbacks.empty());
    CHECK(coalesced_result.graph_component_count == 1);
    CHECK(coalesced_result.routes.front().candidate_ids.size() == 2);
    CHECK(coalesced_result.routes.front().length_mm == Catch::Approx(67.0));
    CHECK(coalesced_result.routes.front().coalesce_transition_length_mm == Catch::Approx(12.0));
    CHECK(coalesced_result.routes.front().is_cut_safe());
}

TEST_CASE("FibreSeek row graph stitches legal route endpoints after component selection", "[FiberseekComposite]")
{
    ExPolygon printable_region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(8.0, 0.0),
        Point::new_scale(8.0, 150.0),
        Point::new_scale(0.0, 150.0),
    });

    std::vector<CompositeCandidate> candidates;
    for (const auto &[x, y0, y1] : std::vector<std::tuple<double, double, double>> {
             {1.0, 0.0, 70.0},
             {6.5, 75.0, 145.0},
         }) {
        CompositeCandidate candidate;
        candidate.id = candidates.size() + 200;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(x, y0),
            Point::new_scale(x, y1),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidate.has_printable_region = true;
        candidate.printable_region = printable_region;
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 60.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.8);
    options.plastic_mm_per_mm = 1.0;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult unstitched_result = select_composite_routes_from_candidates(candidates, options);
    REQUIRE(unstitched_result.routes.size() == 2);
    CHECK(unstitched_result.graph_component_count == 2);

    options.route_stitch_transition_length_mm = 8.0;
    const CompositeRouteGraphResult stitched_result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(stitched_result.routes.size() == 1);
    CHECK(stitched_result.graph_component_count == 2);
    CHECK(stitched_result.routes.front().candidate_ids.size() == 2);
    CHECK(stitched_result.routes.front().length_mm == Catch::Approx(147.433).margin(0.001));
    CHECK(stitched_result.routes.front().coalesce_transition_length_mm == Catch::Approx(8.0));
    REQUIRE(stitched_result.routes.front().planned_segments.size() == 3);
    CHECK(stitched_result.routes.front().planned_segments[1].phase == CompositeRoutePhase::SlowTurn);
    CHECK(stitched_result.routes.front().planned_segments[1].length_mm == Catch::Approx(std::sqrt(55.25)).margin(0.001));
    CHECK(stitched_result.routes.front().is_release_safe());
}

TEST_CASE("FibreSeek row graph post-selection stitching rejects void-crossing connectors", "[FiberseekComposite]")
{
    ExPolygon printable_region(
        Polygon {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(20.0, 0.0),
            Point::new_scale(20.0, 20.0),
            Point::new_scale(0.0, 20.0),
        },
        Polygon {
            Point::new_scale(8.0, 8.0),
            Point::new_scale(12.0, 8.0),
            Point::new_scale(12.0, 12.0),
            Point::new_scale(8.0, 12.0),
        });

    std::vector<CompositeCandidate> candidates;
    for (const double x : { 6.0, 14.0 }) {
        CompositeCandidate candidate;
        candidate.id = candidates.size() + 220;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(x, 9.0),
            Point::new_scale(x, 11.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidate.has_printable_region = true;
        candidate.printable_region = printable_region;
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 2.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 1.0;
    options.min_route_length_mm = 1.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = 0.5;
    options.route_stitch_transition_length_mm = 12.0;
    options.plastic_mm_per_mm = 1.0;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 2);
    CHECK(result.fallbacks.empty());
    CHECK(result.graph_component_count == 2);
    CHECK(result.routes[0].candidate_ids.size() == 1);
    CHECK(result.routes[1].candidate_ids.size() == 1);
}

TEST_CASE("FibreSeek row graph counts node-internal connectors toward cut-safe route length", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 55;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 8.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 25.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    CHECK(result.fallbacks.empty());
    CHECK(result.short_candidate_count == 3);
    CHECK(result.graph_component_count == 1);
    CHECK(result.routes.front().candidate_ids.size() == 3);
    CHECK(result.routes.front().length_mm == Catch::Approx(26.0));
    REQUIRE(result.routes.front().planned_segments.size() == 5);
    CHECK(result.routes.front().planned_segments[1].phase == CompositeRoutePhase::SlowTurn);
    CHECK(result.routes.front().planned_segments[3].phase == CompositeRoutePhase::SlowTurn);
    CHECK(result.routes.front().is_cut_safe());
}

TEST_CASE("FibreSeek row graph attaches a connected boundary tail for finish ironing", "[FiberseekComposite]")
{
    ExPolygon printable_region(Polygon {
        Point::new_scale(0.0, 0.0),
        Point::new_scale(2.0, 0.0),
        Point::new_scale(2.0, 8.0),
        Point::new_scale(0.0, 8.0),
    });

    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 60;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 8.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidate.has_printable_region = true;
        candidate.printable_region = printable_region;
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 20.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.plastic_mm_per_mm = 0.25;
    options.fiber_mm_per_mm = 1.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    const CompositeRoute &route = result.routes.front();
    REQUIRE(!route.tail_segments.empty());
    REQUIRE(route.tail_segments.front().points.size() >= 2);
    REQUIRE(!route.ordered_segments.empty());
    CHECK(route.tail_segments.front().points.front().distance_to(route.ordered_segments.back().points.back()) * SCALING_FACTOR == Catch::Approx(0.0).margin(0.001));
    CHECK(route.tail_length_mm > 0.0);
}

TEST_CASE("FibreSeek row graph leaves unselected branch rows as plastic fallback", "[FiberseekComposite]")
{
    const std::vector<std::pair<double, double>> row_origins {
        {0.0, 0.0},
        {1.0, 0.0},
        {2.0, 0.0},
        {2.0, 9.0},
    };

    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < row_origins.size(); ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 80;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(row_origins[i].first, row_origins[i].second),
            Point::new_scale(row_origins[i].first, row_origins[i].second + 8.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 20.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 10.0;
    options.min_route_length_mm = 10.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    REQUIRE(result.routes.size() == 1);
    REQUIRE(result.fallbacks.size() == 1);
    CHECK(result.short_candidate_count == 4);
    CHECK(result.graph_component_count == 1);
    CHECK(result.routes.front().candidate_ids.size() == 3);
    CHECK(result.fallbacks.front().reason == FallbackReason::ReplacedByBetterCombination);
}

TEST_CASE("FibreSeek row graph rejects connectors crossing printable voids", "[FiberseekComposite]")
{
    ExPolygon printable_region(
        Polygon {
            Point::new_scale(0.0, 0.0),
            Point::new_scale(20.0, 0.0),
            Point::new_scale(20.0, 20.0),
            Point::new_scale(0.0, 20.0),
        },
        Polygon {
            Point::new_scale(8.0, 8.0),
            Point::new_scale(12.0, 8.0),
            Point::new_scale(12.0, 12.0),
            Point::new_scale(8.0, 12.0),
        });

    std::vector<CompositeCandidate> candidates;
    for (const auto &[x, y] : std::vector<std::pair<double, double>> {{6.0, 6.0}, {14.0, 10.0}}) {
        CompositeCandidate candidate;
        candidate.id = candidates.size() + 100;
        candidate.layer_id = 6;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(x, y),
            Point::new_scale(x, y + 4.0),
        };
        candidate.length_mm = polyline_length_mm(candidate.polyline);
        candidate.has_printable_region = true;
        candidate.printable_region = printable_region;
        candidates.push_back(candidate);
    }

    CompositeRouteGraphOptions options;
    options.layer_id = 6;
    options.cut_distance_mm = 5.0;
    options.cut_safety_margin_mm = 0.0;
    options.min_segment_length_mm = 1.0;
    options.line_spacing_mm = 0.7;
    options.max_transition_length_mm = 10.0;
    options.strategy = CompositeRouteGraphStrategy::RocketRowGraph;

    const CompositeRouteGraphResult result = select_composite_routes_from_candidates(candidates, options);

    CHECK(result.routes.empty());
    REQUIRE(result.fallbacks.size() == 2);
    CHECK(result.graph_component_count == 2);
}

TEST_CASE("FibreSeek graph transition helper follows Rocket measured six-width limit", "[FiberseekComposite]")
{
    CHECK(rocket_style_transition_limit_mm(0.7) == Catch::Approx(4.2));
    CHECK(rocket_style_transition_limit_mm(0.8) == Catch::Approx(4.8));
}

TEST_CASE("FibreSeek layer diagnostic marks accepted and fallback candidates", "[FiberseekComposite]")
{
    std::vector<CompositeCandidate> candidates;
    for (std::size_t i = 0; i < 3; ++i) {
        CompositeCandidate candidate;
        candidate.id = i + 1;
        candidate.family = CandidateFamily::SolidInfill;
        candidate.polyline = Polyline {
            Point::new_scale(double(i), 0.0),
            Point::new_scale(double(i), 25.0),
        };
        candidates.push_back(candidate);
    }

    CompositeCandidate short_candidate;
    short_candidate.id = 99;
    short_candidate.family = CandidateFamily::SolidInfill;
    short_candidate.polyline = Polyline {
        Point::new_scale(10.0, 0.0),
        Point::new_scale(10.0, 5.0),
    };
    candidates.push_back(short_candidate);

    CompositeRouteGraphOptions options;
    options.layer_id = 18;
    options.cut_distance_mm = 58.0;
    options.cut_safety_margin_mm = 5.0;
    options.min_segment_length_mm = 10.0;
    options.max_transition_length_mm = rocket_style_transition_limit_mm(0.7);

    const CompositeLayerDiagnostic diagnostic = plan_layer_routes_from_candidates(candidates, options, 2, 3);

    REQUIRE(diagnostic.candidates.size() == 4);
    REQUIRE(diagnostic.routes.size() == 1);
    REQUIRE(diagnostic.fallbacks.size() == 1);
    CHECK(diagnostic.layer_id == 18);
    CHECK(diagnostic.object_id == 2);
    CHECK(diagnostic.region_id == 3);
    CHECK(diagnostic.short_candidate_count == 1);
    CHECK(diagnostic.candidates[0].status == CandidateStatus::Accepted);
    CHECK(diagnostic.candidates[1].status == CandidateStatus::Accepted);
    CHECK(diagnostic.candidates[2].status == CandidateStatus::Accepted);
    CHECK(diagnostic.candidates[3].status == CandidateStatus::Fallback);
}
