#ifndef slic3r_FiberseekCompositePlanner_hpp_
#define slic3r_FiberseekCompositePlanner_hpp_

#include "libslic3r.h"
#include "BoundingBox.hpp"
#include "ExPolygon.hpp"
#include "ExtrusionEntity.hpp"
#include "Polyline.hpp"

#include <cstddef>
#include <memory>
#include <string>
#include <vector>

namespace Slic3r {
class Surface;
enum InfillPattern : int;

namespace FiberseekComposite {

enum class CandidateFamily {
    Unknown,
    Perimeter,
    SolidInfill,
    RhombicInfill,
    IsogridInfill,
    AnisogridInfill,
    TetragridInfill,
};

enum class CandidateStatus {
    Direct,
    ShortCandidate,
    Accepted,
    Fallback,
};

enum class FallbackReason {
    Unknown,
    ShorterThanCutSafeThreshold,
    UnsupportedVoidCrossing,
    RouteCapRemainder,
    ReplacedByBetterCombination,
    ResidualPlasticRefill,
};

enum class CompositeRoutePhase {
    Unknown,
    Start,
    Normal,
    SlowTurn,
    TensionLead,
    TensionRelease,
    PostCutTail,
};

enum class CompositeRouteShape {
    Unknown,
    NoXYMotion,
    OpenPath,
    ShortOpenPath,
    NearClosedLoop,
    ClosedLoop,
    LineOrTail,
};

enum class CompositeRouteGraphStrategy {
    LegacyNearestEndpoint,
    RocketRowGraph,
};

struct CompositeCandidate {
    std::size_t id { 0 };
    std::size_t layer_id { 0 };
    std::size_t object_id { 0 };
    std::size_t island_id { 0 };
    std::size_t region_id { 0 };
    CandidateFamily family { CandidateFamily::Unknown };
    CandidateStatus status { CandidateStatus::Direct };
    Polyline polyline;
    double length_mm { 0.0 };
    double min_available_bend_radius_mm { 0.0 };
    bool legal_containment { true };
    bool has_printable_region { false };
    ExPolygon printable_region;
    std::shared_ptr<const ExPolygon> printable_region_ref;
    ExtrusionRole fallback_role { erInternalInfill };
    double fallback_line_width_mm { 0.0 };
};

struct CompositeRouteSegment {
    CompositeRoutePhase phase { CompositeRoutePhase::Unknown };
    Polyline polyline;
    double length_mm { 0.0 };
    double plastic_mm_per_mm { 0.0 };
    double fiber_mm_per_mm { 0.0 };
    double requested_speed_mm_s { 0.0 };
    double planned_speed_mm_s { 0.0 };
    double turn_amount_rad { 0.0 };
    double min_radius_mm { 0.0 };
    bool emits_plastic { true };
    bool emits_fiber { true };
};

struct CompositeRoute {
    std::size_t id { 0 };
    std::size_t layer_id { 0 };
    std::vector<std::size_t> candidate_ids;
    Polylines ordered_segments;
    Polylines tail_segments;
    std::vector<CompositeRouteSegment> planned_segments;
    double length_mm { 0.0 };
    double tail_length_mm { 0.0 };
    double cut_safe_threshold_mm { 0.0 };
    double cut_distance_mm { 0.0 };
    double coalesce_transition_length_mm { 0.0 };
    double fiber_start_length_mm { 0.0 };
    double fiber_slow_length_mm { 0.0 };
    double fiber_tension_length_mm { 0.0 };
    double fiber_tension_release_fraction { 0.0 };
    double after_cut_plastic_coeff { 1.0 };
    double plastic_mm_per_mm { 0.0 };
    double fiber_mm_per_mm { 0.0 };
    double fiber_positive_length_mm { 0.0 };
    double matrix_positive_length_mm { 0.0 };
    double travel_length_mm { 0.0 };
    double closure_gap_mm { 0.0 };
    double bbox_span_x_mm { 0.0 };
    double bbox_span_y_mm { 0.0 };
    CompositeRouteShape shape { CompositeRouteShape::Unknown };
    std::size_t bend_risk_points { 0 };
    std::size_t unsupported_void_crossing_count { 0 };
    std::vector<std::string> warnings;

    bool is_cut_safe() const;
    bool is_geometrically_safe() const;
    bool is_release_safe() const;
    double printable_length_mm() const;
    bool is_closed_loop(double tolerance_mm = 1.0) const;
};

struct CompositeRouteMetrics {
    double length_mm { 0.0 };
    double tail_length_mm { 0.0 };
    double fiber_positive_length_mm { 0.0 };
    double matrix_positive_length_mm { 0.0 };
    double travel_length_mm { 0.0 };
    double closure_gap_mm { 0.0 };
    double bbox_span_x_mm { 0.0 };
    double bbox_span_y_mm { 0.0 };
    CompositeRouteShape shape { CompositeRouteShape::Unknown };
};

struct CompositeFallback {
    std::size_t id { 0 };
    std::size_t layer_id { 0 };
    std::vector<std::size_t> candidate_ids;
    Polylines replacement_segments;
    ExtrusionRole extrusion_role { erInternalInfill };
    FallbackReason reason { FallbackReason::Unknown };
};

struct CompositeLayerDiagnostic {
    std::size_t layer_id { 0 };
    std::size_t object_id { 0 };
    std::size_t region_id { 0 };
    std::size_t direct_candidate_count { 0 };
    std::size_t short_candidate_count { 0 };
    std::size_t graph_component_count { 0 };
    std::vector<CompositeCandidate> candidates;
    std::vector<CompositeRoute> routes;
    std::vector<CompositeFallback> fallbacks;

    bool empty() const;
};

struct CompositePlanDiagnostic {
    std::vector<CompositeLayerDiagnostic> layers;

    std::size_t route_count() const;
    std::size_t fallback_count() const;
    std::size_t routes_with_unsupported_void_crossings() const;
    bool is_release_safe() const;
};

struct CompositeRouteGraphOptions {
    std::size_t layer_id { 0 };
    double cut_distance_mm { 58.0 };
    double cut_safety_margin_mm { 5.0 };
    double min_segment_length_mm { 10.0 };
    double min_route_length_mm { 55.0 };
    double line_spacing_mm { 0.7 };
    double max_transition_length_mm { 4.2 };
    double coalesce_transition_length_mm { 0.0 };
    double route_stitch_transition_length_mm { 0.0 };
    double plastic_mm_per_mm { 0.0 };
    double fiber_mm_per_mm { 1.0 };
    CompositeRouteGraphStrategy strategy { CompositeRouteGraphStrategy::LegacyNearestEndpoint };
};

struct CompositePerimeterOptions {
    std::size_t layer_id { 0 };
    std::size_t object_id { 0 };
    std::size_t region_id { 0 };
    std::size_t first_candidate_id { 0 };
    std::size_t first_route_id { 0 };
    double inset_mm { 0.85 };
    double spacing_mm { 0.7 };
    double min_route_length_mm { 55.0 };
    std::size_t outer_loop_count { 1 };
    std::size_t inner_loop_count { 1 };
};

struct CompositeSurfaceFillOptions {
    CompositeSurfaceFillOptions();

    CandidateFamily family { CandidateFamily::SolidInfill };
    std::size_t layer_id { 0 };
    std::size_t object_id { 0 };
    std::size_t island_id { 0 };
    std::size_t region_id { 0 };
    std::size_t first_candidate_id { 0 };
    InfillPattern pattern;
    double density { 1.0 };
    double spacing_mm { 0.7 };
    double overlap_mm { 0.0 };
    double fiber_line_width_mm { 0.0 };
    double fallback_infill_line_width_mm { 0.0 };
    double fallback_solid_line_width_mm { 0.0 };
    double angle_rad { 0.0 };
    double z_mm { 0.0 };
    double resolution_mm { 0.0125 };
    bool fixed_angle { true };
    bool connect_to_perimeters { false };
    bool adjust_spacing { false };
    bool residual_plastic_refill_enabled { false };
    BoundingBox bounding_box;
};

struct CompositeRouteGraphResult {
    std::vector<CompositeRoute> routes;
    std::vector<CompositeFallback> fallbacks;
    std::size_t direct_candidate_count { 0 };
    std::size_t short_candidate_count { 0 };
    std::size_t graph_component_count { 0 };
};

double polyline_length_mm(const Polyline &polyline);
double polylines_length_mm(const Polylines &polylines);
std::vector<CompositeCandidate> make_candidates_from_polylines(
    const Polylines &polylines,
    CandidateFamily family,
    std::size_t layer_id,
    std::size_t object_id = 0,
    std::size_t island_id = 0,
    std::size_t region_id = 0,
    std::size_t first_candidate_id = 0);
std::vector<CompositeCandidate> make_candidates_from_surface_fill(
    const Surface &surface,
    const CompositeSurfaceFillOptions &options);
std::vector<CompositeCandidate> make_candidates_from_surface_fills(
    const std::vector<const Surface *> &surfaces,
    CompositeSurfaceFillOptions options);
double rocket_style_transition_limit_mm(double fiber_line_width_mm);
double cut_safe_threshold_mm(double cut_distance_mm, double safety_margin_mm);
bool route_length_is_cut_safe(double route_length_mm, double threshold_mm);
CompositeRouteMetrics measure_route(
    const Polylines &ordered_segments,
    const Polylines &tail_segments,
    double plastic_mm_per_mm,
    double fiber_mm_per_mm,
    double short_route_threshold_mm = 55.0);
void refresh_route_metrics(CompositeRoute &route);
CompositeRouteShape classify_route_shape(
    double length_mm,
    double closure_gap_mm,
    double bbox_span_x_mm,
    double bbox_span_y_mm,
    double short_route_threshold_mm = 55.0);
CompositeRouteGraphResult select_composite_routes_from_candidates(
    const std::vector<CompositeCandidate> &candidates,
    const CompositeRouteGraphOptions &options);
CompositeLayerDiagnostic plan_layer_routes_from_candidates(
    const std::vector<CompositeCandidate> &candidates,
    const CompositeRouteGraphOptions &options,
    std::size_t object_id = 0,
    std::size_t region_id = 0);
CompositeLayerDiagnostic plan_surface_fill_routes(
    const std::vector<const Surface *> &surfaces,
    CompositeSurfaceFillOptions surface_options,
    CompositeRouteGraphOptions route_options);
CompositeLayerDiagnostic plan_perimeter_routes_from_expolygons(
    const ExPolygons &regions,
    const CompositePerimeterOptions &perimeter_options,
    CompositeRouteGraphOptions route_options);
void stitch_composite_layer_routes(
    CompositeLayerDiagnostic &diagnostic,
    const CompositeRouteGraphOptions &options);
const char *route_shape_name(CompositeRouteShape shape);

} // namespace FiberseekComposite
} // namespace Slic3r

#endif // slic3r_FiberseekCompositePlanner_hpp_
