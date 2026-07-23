#include "FiberseekCompositePlanner.hpp"

#include "ClipperUtils.hpp"
#include "Fill/FillBase.hpp"
#include "Geometry.hpp"
#include "PrintConfig.hpp"
#include "Surface.hpp"

#include <algorithm>
#include <cmath>
#include <iterator>
#include <limits>
#include <map>
#include <memory>
#include <numeric>
#include <set>
#include <tuple>
#include <unordered_set>

namespace Slic3r {
namespace FiberseekComposite {

namespace {

struct RouteExtents {
    bool has_points { false };
    Point first;
    Point last;
    coord_t min_x { 0 };
    coord_t min_y { 0 };
    coord_t max_x { 0 };
    coord_t max_y { 0 };
};

enum class CandidateEndpoint {
    Start,
    End,
};

struct RowCandidateView {
    std::size_t candidate_index { 0 };
    long long angle_key { 0 };
    double coord_mm { 0.0 };
    double span_mm { 0.0 };
    double length_mm { 0.0 };
};

struct RowConnection {
    std::size_t first { 0 };
    std::size_t second { 0 };
    CandidateEndpoint first_endpoint { CandidateEndpoint::End };
    CandidateEndpoint second_endpoint { CandidateEndpoint::Start };
    Point first_point;
    Point second_point;
    double length_mm { 0.0 };
};

struct CompositeNode {
    std::size_t id { 0 };
    std::vector<std::size_t> candidate_indices;
    std::vector<CandidateEndpoint> canonical_entry_endpoints;
    double owned_length_mm { 0.0 };
    double internal_connector_length_mm { 0.0 };
};

struct CompositeNodeConnection {
    std::size_t first { 0 };
    std::size_t second { 0 };
    CandidateEndpoint first_endpoint { CandidateEndpoint::End };
    CandidateEndpoint second_endpoint { CandidateEndpoint::Start };
    Point first_point;
    Point second_point;
    double length_mm { 0.0 };
};

struct CompositeNodeRouteCandidate {
    std::vector<std::size_t> path;
    std::vector<CandidateEndpoint> entry_endpoints;
    std::vector<std::size_t> key;
    double owned_length_mm { 0.0 };
    double score_length_mm { 0.0 };
};

struct CompositeRouteGeometry {
    Polylines ordered_segments;
    Polylines tail_segments;
    std::vector<CompositeRouteSegment> planned_segments;
    std::vector<std::size_t> materialized_candidate_indices;
};

struct BoundaryTailAnchor {
    const Polygon *boundary { nullptr };
    std::size_t segment_index { 0 };
    Point projection;
    double distance_mm { std::numeric_limits<double>::infinity() };
};

struct BoundarySegment {
    Point start;
    Point end;
    BoundingBox bbox;
};

struct PrintableRegionBounds {
    BoundingBox bbox;
    std::vector<BoundarySegment> boundary_segments;
    coord_t boundary_cell_size_scaled { 0 };
    std::map<std::pair<long long, long long>, std::vector<std::size_t>> boundary_cells;
};

struct ResidualPlasticRegion {
    const ExPolygon *printable_region { nullptr };
    ExtrusionRole extrusion_role { erInternalInfill };
    double plastic_line_width_mm { 0.0 };
    std::set<std::size_t> candidate_ids;
    Polylines covered_segments;
    bool has_accepted_route { false };
};

using RowConnectionKey = std::pair<std::size_t, std::size_t>;
using RowConnectionMap = std::map<RowConnectionKey, RowConnection>;
using RowConnectionOptionsMap = std::map<RowConnectionKey, std::vector<RowConnection>>;
using CompositeNodeConnectionKey = std::pair<std::size_t, std::size_t>;
using CompositeNodeConnectionMap = std::map<CompositeNodeConnectionKey, CompositeNodeConnection>;
using CompositeNodeConnectionOptionsMap = std::map<CompositeNodeConnectionKey, std::vector<CompositeNodeConnection>>;
using CandidateIntersectionCellKey = std::tuple<std::size_t, long long, long long>;

static constexpr std::size_t MAX_ROW_PATH_COUNT = 96;
static constexpr std::size_t MAX_ROW_ROUTE_CANDIDATE_COUNT = 768;
static constexpr std::size_t MAX_ROW_ROUTE_SELECTION_SEEDS = 96;
static constexpr std::size_t MAX_ROW_GREEDY_PATH_LENGTH = 56;
static constexpr std::size_t MAX_ROW_ROUTE_COMPLETION_PASSES = 3;
static constexpr std::size_t MAX_ROW_ROUTE_COMPLETION_COMPONENT_NODES = 512;
static constexpr double MIN_ROW_ROUTE_COMPLETION_UNCOVERED_RATIO = 0.15;
static constexpr std::size_t MAX_POST_COMBINE_STITCH_FULL_CANDIDATES = 512;
static constexpr double BOUNDARY_INTERSECTION_CELL_SIZE_MM = 8.0;

struct CandidateIntersectionIndex {
    coord_t cell_size_scaled { 0 };
    std::map<CandidateIntersectionCellKey, std::vector<std::size_t>> cells;
};

static bool scaled_points_equal(const Point &a, const Point &b, coord_t tolerance = SCALED_EPSILON);
static long long intersection_cell_index(coord_t coord, coord_t cell_size_scaled);

static void add_polyline_extents(RouteExtents &extents, const Polyline &polyline)
{
    if (polyline.points.empty())
        return;

    if (!extents.has_points) {
        extents.has_points = true;
        extents.first = polyline.points.front();
        extents.min_x = extents.max_x = polyline.points.front().x();
        extents.min_y = extents.max_y = polyline.points.front().y();
    }

    extents.last = polyline.points.back();
    for (const Point &point : polyline.points) {
        extents.min_x = std::min(extents.min_x, point.x());
        extents.max_x = std::max(extents.max_x, point.x());
        extents.min_y = std::min(extents.min_y, point.y());
        extents.max_y = std::max(extents.max_y, point.y());
    }
}

static RouteExtents route_extents(const Polylines &polylines)
{
    RouteExtents extents;
    for (const Polyline &polyline : polylines)
        add_polyline_extents(extents, polyline);
    return extents;
}

static double point_distance_mm(const Point &a, const Point &b)
{
    return a.distance_to(b) * SCALING_FACTOR;
}

static Point point_at_fraction_scaled(const Point &start, const Point &end, double fraction)
{
    fraction = std::clamp(fraction, 0.0, 1.0);
    return Point(
        coord_t(std::llround(double(start.x()) + double(end.x() - start.x()) * fraction)),
        coord_t(std::llround(double(start.y()) + double(end.y() - start.y()) * fraction)));
}

static BoundingBox segment_bounding_box(const Point &a, const Point &b, coord_t inflation = SCALED_EPSILON)
{
    BoundingBox bbox;
    bbox.merge(a);
    bbox.merge(b);
    return bbox.inflated(inflation);
}

static BoundingBox polyline_bounding_box(const Polyline &polyline, coord_t inflation = SCALED_EPSILON)
{
    BoundingBox bbox;
    for (const Point &point : polyline.points)
        bbox.merge(point);
    return bbox.inflated(inflation);
}

static BoundarySegment make_boundary_segment(const Point &start, const Point &end)
{
    BoundarySegment segment;
    segment.start = start;
    segment.end = end;
    segment.bbox = segment_bounding_box(start, end);
    return segment;
}

static void append_boundary_segments(PrintableRegionBounds &bounds, const Polygon &boundary)
{
    if (boundary.points.size() < 2)
        return;

    for (std::size_t i = 0; i < boundary.points.size(); ++i)
        bounds.boundary_segments.push_back(make_boundary_segment(
            boundary.points[i],
            boundary.points[(i + 1) % boundary.points.size()]));
}

static void build_boundary_intersection_index(PrintableRegionBounds &bounds)
{
    bounds.boundary_cell_size_scaled = std::max<coord_t>(1, scale_(BOUNDARY_INTERSECTION_CELL_SIZE_MM));
    bounds.boundary_cells.clear();

    for (std::size_t segment_index = 0; segment_index < bounds.boundary_segments.size(); ++segment_index) {
        const BoundarySegment &segment = bounds.boundary_segments[segment_index];
        if (!segment.bbox.defined)
            continue;

        const long long min_x = intersection_cell_index(segment.bbox.min.x(), bounds.boundary_cell_size_scaled);
        const long long max_x = intersection_cell_index(segment.bbox.max.x(), bounds.boundary_cell_size_scaled);
        const long long min_y = intersection_cell_index(segment.bbox.min.y(), bounds.boundary_cell_size_scaled);
        const long long max_y = intersection_cell_index(segment.bbox.max.y(), bounds.boundary_cell_size_scaled);
        for (long long cell_x = min_x; cell_x <= max_x; ++cell_x)
            for (long long cell_y = min_y; cell_y <= max_y; ++cell_y)
                bounds.boundary_cells[std::make_pair(cell_x, cell_y)].push_back(segment_index);
    }
}

static std::vector<std::size_t> boundary_intersection_query(
    const PrintableRegionBounds &bounds,
    const BoundingBox &bbox)
{
    std::vector<std::size_t> segments;
    if (!bbox.defined || bounds.boundary_cell_size_scaled <= 0 || bounds.boundary_cells.empty())
        return segments;

    const long long min_x = intersection_cell_index(bbox.min.x(), bounds.boundary_cell_size_scaled);
    const long long max_x = intersection_cell_index(bbox.max.x(), bounds.boundary_cell_size_scaled);
    const long long min_y = intersection_cell_index(bbox.min.y(), bounds.boundary_cell_size_scaled);
    const long long max_y = intersection_cell_index(bbox.max.y(), bounds.boundary_cell_size_scaled);

    std::set<std::size_t> seen;
    for (long long cell_x = min_x; cell_x <= max_x; ++cell_x) {
        for (long long cell_y = min_y; cell_y <= max_y; ++cell_y) {
            const auto found = bounds.boundary_cells.find(std::make_pair(cell_x, cell_y));
            if (found == bounds.boundary_cells.end())
                continue;
            for (std::size_t segment_index : found->second)
                if (seen.insert(segment_index).second)
                    segments.push_back(segment_index);
        }
    }

    return segments;
}

static PrintableRegionBounds make_printable_region_bounds(const ExPolygon &printable_region)
{
    PrintableRegionBounds bounds;
    bounds.bbox = get_extents(printable_region).inflated(SCALED_EPSILON);
    bounds.boundary_segments.reserve(count_points(printable_region));
    append_boundary_segments(bounds, printable_region.contour);
    for (const Polygon &hole : printable_region.holes)
        append_boundary_segments(bounds, hole);
    build_boundary_intersection_index(bounds);
    return bounds;
}

static bool candidate_has_printable_polyline(const CompositeCandidate &candidate)
{
    return candidate.polyline.points.size() >= 2;
}

static const ExPolygon *candidate_printable_region(const CompositeCandidate &candidate)
{
    if (!candidate.has_printable_region)
        return nullptr;
    return candidate.printable_region_ref ? candidate.printable_region_ref.get() : &candidate.printable_region;
}

static bool route_last_motion_points(const Polylines &polylines, Point &previous, Point &last)
{
    for (auto polyline_it = polylines.rbegin(); polyline_it != polylines.rend(); ++polyline_it) {
        const Polyline &polyline = *polyline_it;
        if (polyline.points.size() < 2)
            continue;
        for (std::size_t i = polyline.points.size() - 1; i > 0; --i) {
            if (scaled_points_equal(polyline.points[i - 1], polyline.points[i]))
                continue;
            previous = polyline.points[i - 1];
            last = polyline.points[i];
            return true;
        }
    }
    return false;
}

static Point closest_point_on_segment(const Point &point, const Point &start, const Point &end)
{
    const double dx = double(end.x() - start.x());
    const double dy = double(end.y() - start.y());
    const double length_sq = dx * dx + dy * dy;
    if (length_sq <= 0.0)
        return start;

    const double t = ((double(point.x() - start.x()) * dx) + (double(point.y() - start.y()) * dy)) / length_sq;
    return point_at_fraction_scaled(start, end, t);
}

static void consider_boundary_tail_anchor(
    const Polygon &boundary,
    const Point &route_end,
    BoundaryTailAnchor &best)
{
    if (boundary.points.size() < 2)
        return;

    for (std::size_t i = 0; i < boundary.points.size(); ++i) {
        const Point &start = boundary.points[i];
        const Point &end = boundary.points[(i + 1) % boundary.points.size()];
        const Point projection = closest_point_on_segment(route_end, start, end);
        const double distance_mm = point_distance_mm(route_end, projection);
        if (distance_mm + EPSILON >= best.distance_mm)
            continue;
        best.boundary = &boundary;
        best.segment_index = i;
        best.projection = projection;
        best.distance_mm = distance_mm;
    }
}

static BoundaryTailAnchor nearest_boundary_tail_anchor(const ExPolygon &printable_region, const Point &route_end)
{
    BoundaryTailAnchor best;
    consider_boundary_tail_anchor(printable_region.contour, route_end, best);
    for (const Polygon &hole : printable_region.holes)
        consider_boundary_tail_anchor(hole, route_end, best);
    return best;
}

static void append_tail_point(Polyline &tail, const Point &point)
{
    if (tail.points.empty() || !scaled_points_equal(tail.points.back(), point))
        tail.points.push_back(point);
}

static Polyline boundary_tail_polyline_from_anchor(
    const Polygon &boundary,
    std::size_t segment_index,
    const Point &tail_start,
    bool forward)
{
    Polyline tail;
    const std::size_t count = boundary.points.size();
    if (count < 2)
        return tail;

    append_tail_point(tail, tail_start);
    if (forward) {
        std::size_t vertex = (segment_index + 1) % count;
        append_tail_point(tail, boundary.points[vertex]);
        for (std::size_t i = 0; i + 1 < count; ++i) {
            vertex = (vertex + 1) % count;
            append_tail_point(tail, boundary.points[vertex]);
        }
    } else {
        std::size_t vertex = segment_index;
        append_tail_point(tail, boundary.points[vertex]);
        for (std::size_t i = 0; i + 1 < count; ++i) {
            vertex = (vertex + count - 1) % count;
            append_tail_point(tail, boundary.points[vertex]);
        }
    }

    if (tail.points.size() < 2 || polyline_length_mm(tail) <= EPSILON)
        tail.points.clear();
    return tail;
}

static double abs_turn_between(const Point &previous, const Point &current, const Point &next)
{
    const double in_x = double(current.x() - previous.x());
    const double in_y = double(current.y() - previous.y());
    const double out_x = double(next.x() - current.x());
    const double out_y = double(next.y() - current.y());
    const double in_len_sq = in_x * in_x + in_y * in_y;
    const double out_len_sq = out_x * out_x + out_y * out_y;
    if (in_len_sq <= 0.0 || out_len_sq <= 0.0)
        return 0.0;
    const double cross = in_x * out_y - in_y * out_x;
    const double dot = in_x * out_x + in_y * out_y;
    return std::abs(std::atan2(cross, dot));
}

static double tail_entry_turn_abs(const Point &route_previous, const Point &route_end, const Polyline &tail)
{
    if (tail.points.size() < 2)
        return std::numeric_limits<double>::infinity();
    for (std::size_t i = 1; i < tail.points.size(); ++i) {
        if (!scaled_points_equal(route_end, tail.points[i]))
            return abs_turn_between(route_previous, route_end, tail.points[i]);
    }
    return std::numeric_limits<double>::infinity();
}

static Polylines boundary_tail_for_route_end(
    const CompositeCandidate &candidate,
    const Point &route_previous,
    const Point &route_end,
    const CompositeRouteGraphOptions &options)
{
    const ExPolygon *printable_region = candidate_printable_region(candidate);
    if (printable_region == nullptr)
        return {};

    const BoundaryTailAnchor anchor = nearest_boundary_tail_anchor(*printable_region, route_end);
    if (anchor.boundary == nullptr)
        return {};

    const double snap_tolerance_mm = std::max(0.08, std::min(0.35, options.line_spacing_mm * 0.5));
    if (anchor.distance_mm > snap_tolerance_mm)
        return {};

    Polyline forward_tail = boundary_tail_polyline_from_anchor(
        *anchor.boundary, anchor.segment_index, route_end, true);
    Polyline reverse_tail = boundary_tail_polyline_from_anchor(
        *anchor.boundary, anchor.segment_index, route_end, false);

    if (forward_tail.points.empty())
        return reverse_tail.points.empty() ? Polylines{} : Polylines{ std::move(reverse_tail) };
    if (reverse_tail.points.empty())
        return Polylines{ std::move(forward_tail) };

    const double forward_turn = tail_entry_turn_abs(route_previous, route_end, forward_tail);
    const double reverse_turn = tail_entry_turn_abs(route_previous, route_end, reverse_tail);
    return forward_turn <= reverse_turn ?
        Polylines{ std::move(forward_tail) } :
        Polylines{ std::move(reverse_tail) };
}

static void populate_boundary_tail_for_row_path(
    CompositeRouteGeometry &geometry,
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<std::size_t> &path,
    const CompositeRouteGraphOptions &options)
{
    Point route_previous;
    Point route_end;
    if (!route_last_motion_points(geometry.ordered_segments, route_previous, route_end))
        return;

    for (auto it = path.rbegin(); it != path.rend(); ++it) {
        const std::size_t candidate_index = *it;
        if (candidate_index >= candidates.size())
            continue;
        Polylines tail = boundary_tail_for_route_end(
            candidates[candidate_index], route_previous, route_end, options);
        if (tail.empty())
            continue;
        geometry.tail_segments = std::move(tail);
        return;
    }
}

static ExtrusionRole fallback_role_for_surface(const Surface &surface)
{
    return surface.surface_type == stInternalSolid ? erSolidInfill : erInternalInfill;
}

static double fallback_line_width_for_surface(const Surface &surface, const CompositeSurfaceFillOptions &options)
{
    return surface.surface_type == stInternalSolid ?
        options.fallback_solid_line_width_mm :
        options.fallback_infill_line_width_mm;
}

static double candidate_length_mm(const CompositeCandidate &candidate)
{
    return candidate.length_mm > 0.0 ? candidate.length_mm : polyline_length_mm(candidate.polyline);
}

static Point point_offset_scaled(const Point &point, double dx_scaled, double dy_scaled)
{
    return Point(
        coord_t(std::llround(double(point.x()) + dx_scaled)),
        coord_t(std::llround(double(point.y()) + dy_scaled)));
}

static void append_printable_polyline(Polylines &target, Polyline polyline)
{
    if (polyline.points.size() >= 2 && polyline_length_mm(polyline) > EPSILON)
        target.push_back(std::move(polyline));
}

static double prolong_extension_length_mm(const ExPolygon &printable_region, double extra_mm)
{
    const BoundingBox bounds = get_extents(printable_region);
    double extension_mm = 10.0;
    if (bounds.defined) {
        const double dx = double(bounds.max.x() - bounds.min.x()) * SCALING_FACTOR;
        const double dy = double(bounds.max.y() - bounds.min.y()) * SCALING_FACTOR;
        extension_mm = std::max(extension_mm, std::hypot(dx, dy) + 2.0 * std::max(extra_mm, 0.0));
    }
    return extension_mm;
}

static Polylines clipped_extended_parallel_segment(
    const Point &start,
    const Point &end,
    double normal_offset_scaled,
    const ExPolygon &printable_region,
    double extension_mm)
{
    const double dx = double(end.x() - start.x());
    const double dy = double(end.y() - start.y());
    const double length = std::hypot(dx, dy);
    if (length <= 0.0)
        return {};

    const double ux = dx / length;
    const double uy = dy / length;
    const double nx = -uy;
    const double ny = ux;
    const double extension_scaled = double(scale_(extension_mm));

    Polyline extended;
    extended.points.push_back(point_offset_scaled(
        start,
        nx * normal_offset_scaled - ux * extension_scaled,
        ny * normal_offset_scaled - uy * extension_scaled));
    extended.points.push_back(point_offset_scaled(
        end,
        nx * normal_offset_scaled + ux * extension_scaled,
        ny * normal_offset_scaled + uy * extension_scaled));

    return intersection_pl(extended, printable_region);
}

static double point_distance_to_polyline_mm(const Point &point, const Polyline &polyline)
{
    if (polyline.points.empty())
        return std::numeric_limits<double>::infinity();
    if (polyline.points.size() == 1)
        return point_distance_mm(point, polyline.points.front());

    double best_distance_mm = std::numeric_limits<double>::infinity();
    for (std::size_t point_index = 1; point_index < polyline.points.size(); ++point_index) {
        const Point projection = closest_point_on_segment(
            point,
            polyline.points[point_index - 1],
            polyline.points[point_index]);
        best_distance_mm = std::min(best_distance_mm, point_distance_mm(point, projection));
    }
    return best_distance_mm;
}

static bool prolong_short_candidate_against_printable_region(
    CompositeCandidate &candidate,
    const CompositeRouteGraphOptions &options)
{
    if (candidate.family == CandidateFamily::Perimeter || !candidate.legal_containment)
        return false;
    if (!candidate_has_printable_polyline(candidate))
        return false;

    const double original_length_mm = candidate_length_mm(candidate);
    if (original_length_mm + EPSILON >= options.min_segment_length_mm)
        return false;

    const ExPolygon *printable_region = candidate_printable_region(candidate);
    if (printable_region == nullptr)
        return false;

    const Point original_midpoint = point_at_fraction_scaled(
        candidate.polyline.points.front(),
        candidate.polyline.points.back(),
        0.5);
    const double extension_mm = prolong_extension_length_mm(*printable_region, options.line_spacing_mm);
    const Polylines clipped = clipped_extended_parallel_segment(
        candidate.polyline.points.front(),
        candidate.polyline.points.back(),
        0.0,
        *printable_region,
        extension_mm);

    double best_distance_mm = std::numeric_limits<double>::infinity();
    double best_length_mm = 0.0;
    const Polyline *best_polyline = nullptr;
    const double max_midpoint_drift_mm = std::max(options.line_spacing_mm, 0.05);
    for (const Polyline &polyline : clipped) {
        if (polyline.points.size() < 2)
            continue;
        const double length_mm = polyline_length_mm(polyline);
        if (length_mm <= original_length_mm + EPSILON)
            continue;

        const double midpoint_distance_mm = point_distance_to_polyline_mm(original_midpoint, polyline);
        if (midpoint_distance_mm > max_midpoint_drift_mm)
            continue;

        if (midpoint_distance_mm + EPSILON < best_distance_mm ||
            (std::abs(midpoint_distance_mm - best_distance_mm) <= EPSILON && length_mm > best_length_mm)) {
            best_distance_mm = midpoint_distance_mm;
            best_length_mm = length_mm;
            best_polyline = &polyline;
        }
    }

    if (best_polyline == nullptr)
        return false;

    candidate.polyline = *best_polyline;
    candidate.length_mm = best_length_mm;
    return true;
}

static void prolong_short_candidates_against_printable_regions(
    std::vector<CompositeCandidate> &candidates,
    const CompositeRouteGraphOptions &options)
{
    for (CompositeCandidate &candidate : candidates)
        prolong_short_candidate_against_printable_region(candidate, options);
}

static Polylines plastic_substitution_segments_for_candidate(
    const CompositeCandidate &candidate,
    const CompositeRouteGraphOptions &options)
{
    const ExPolygon *printable_region = candidate_printable_region(candidate);
    if (printable_region == nullptr || candidate.polyline.points.size() < 2)
        return {};

    const double fallback_width_mm = candidate.fallback_line_width_mm > EPSILON ?
        candidate.fallback_line_width_mm :
        std::max(options.line_spacing_mm, 0.01);
    const double offset_scaled = 0.5 * double(scale_(fallback_width_mm));
    const double extension_mm = prolong_extension_length_mm(*printable_region, options.line_spacing_mm);

    Polylines replacements;
    for (std::size_t point_index = 1; point_index < candidate.polyline.points.size(); ++point_index) {
        const Point &start = candidate.polyline.points[point_index - 1];
        const Point &end = candidate.polyline.points[point_index];
        for (double side : { -1.0, 1.0 }) {
            Polylines clipped = clipped_extended_parallel_segment(
                start,
                end,
                side * offset_scaled,
                *printable_region,
                extension_mm);
            for (Polyline &clipped_line : clipped)
                append_printable_polyline(replacements, std::move(clipped_line));
        }
    }

    return replacements;
}

static bool fallback_needs_paired_plastic_substitution(
    const CompositeCandidate &candidate,
    FallbackReason reason)
{
    if (candidate.family == CandidateFamily::Perimeter)
        return false;
    if (!candidate_has_printable_polyline(candidate))
        return false;

    switch (reason) {
    case FallbackReason::UnsupportedVoidCrossing:
    case FallbackReason::ShorterThanCutSafeThreshold:
        return true;
    case FallbackReason::ReplacedByBetterCombination:
    case FallbackReason::ResidualPlasticRefill:
        return false;
    }

    return false;
}

static double nearest_endpoint_distance_mm(const CompositeCandidate &a, const CompositeCandidate &b)
{
    if (!candidate_has_printable_polyline(a) || !candidate_has_printable_polyline(b))
        return std::numeric_limits<double>::infinity();

    const Point &a_start = a.polyline.points.front();
    const Point &a_end = a.polyline.points.back();
    const Point &b_start = b.polyline.points.front();
    const Point &b_end = b.polyline.points.back();
    return std::min({
        point_distance_mm(a_start, b_start),
        point_distance_mm(a_start, b_end),
        point_distance_mm(a_end, b_start),
        point_distance_mm(a_end, b_end),
    });
}

static bool candidates_share_route_scope(const CompositeCandidate &a, const CompositeCandidate &b)
{
    return a.layer_id == b.layer_id &&
           a.object_id == b.object_id &&
           a.region_id == b.region_id &&
           a.island_id == b.island_id &&
           a.family == b.family;
}

static bool candidates_share_physical_route_scope(const CompositeCandidate &a, const CompositeCandidate &b)
{
    return a.layer_id == b.layer_id &&
           a.object_id == b.object_id &&
           a.region_id == b.region_id &&
           a.island_id == b.island_id;
}

static long long intersection_cell_index(coord_t coord, coord_t cell_size_scaled)
{
    if (cell_size_scaled <= 0)
        return 0;
    return static_cast<long long>(std::floor(double(coord) / double(cell_size_scaled)));
}

static CandidateIntersectionIndex build_candidate_intersection_index(
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    double cell_size_mm)
{
    CandidateIntersectionIndex index;
    index.cell_size_scaled = std::max<coord_t>(1, scale_(std::max(cell_size_mm, 1.0)));

    for (std::size_t candidate_index = 0; candidate_index < candidate_bounds.size(); ++candidate_index) {
        if (candidate_index >= candidate_region_indices.size())
            continue;
        const BoundingBox &bbox = candidate_bounds[candidate_index];
        if (!bbox.defined)
            continue;

        const std::size_t region_index = candidate_region_indices[candidate_index];
        if (region_index == std::numeric_limits<std::size_t>::max())
            continue;

        const long long min_x = intersection_cell_index(bbox.min.x(), index.cell_size_scaled);
        const long long max_x = intersection_cell_index(bbox.max.x(), index.cell_size_scaled);
        const long long min_y = intersection_cell_index(bbox.min.y(), index.cell_size_scaled);
        const long long max_y = intersection_cell_index(bbox.max.y(), index.cell_size_scaled);
        for (long long cell_x = min_x; cell_x <= max_x; ++cell_x)
            for (long long cell_y = min_y; cell_y <= max_y; ++cell_y)
                index.cells[std::make_tuple(region_index, cell_x, cell_y)].push_back(candidate_index);
    }

    return index;
}

static std::vector<std::size_t> candidate_intersection_query(
    const CandidateIntersectionIndex &index,
    const BoundingBox &bbox,
    std::size_t region_index)
{
    std::vector<std::size_t> candidates;
    if (!bbox.defined ||
        index.cell_size_scaled <= 0 ||
        region_index == std::numeric_limits<std::size_t>::max())
        return candidates;

    const long long min_x = intersection_cell_index(bbox.min.x(), index.cell_size_scaled);
    const long long max_x = intersection_cell_index(bbox.max.x(), index.cell_size_scaled);
    const long long min_y = intersection_cell_index(bbox.min.y(), index.cell_size_scaled);
    const long long max_y = intersection_cell_index(bbox.max.y(), index.cell_size_scaled);

    std::set<std::size_t> seen;
    for (long long cell_x = min_x; cell_x <= max_x; ++cell_x) {
        for (long long cell_y = min_y; cell_y <= max_y; ++cell_y) {
            const auto found = index.cells.find(std::make_tuple(region_index, cell_x, cell_y));
            if (found == index.cells.end())
                continue;
            for (std::size_t candidate_index : found->second) {
                if (seen.insert(candidate_index).second)
                    candidates.push_back(candidate_index);
            }
        }
    }

    return candidates;
}

static std::vector<CompositeCandidate> route_owned_candidates(
    const CompositeLayerDiagnostic &diagnostic)
{
    std::unordered_set<std::size_t> route_candidate_ids;
    for (const CompositeRoute &route : diagnostic.routes)
        route_candidate_ids.insert(route.candidate_ids.begin(), route.candidate_ids.end());

    std::vector<CompositeCandidate> candidates;
    candidates.reserve(std::min(route_candidate_ids.size(), diagnostic.candidates.size()));
    for (const CompositeCandidate &candidate : diagnostic.candidates)
        if (route_candidate_ids.count(candidate.id) != 0)
            candidates.push_back(candidate);
    return candidates;
}

static Point candidate_endpoint_point(const CompositeCandidate &candidate, CandidateEndpoint endpoint)
{
    return endpoint == CandidateEndpoint::Start ? candidate.polyline.points.front() : candidate.polyline.points.back();
}

static CandidateEndpoint opposite_endpoint(CandidateEndpoint endpoint)
{
    return endpoint == CandidateEndpoint::Start ? CandidateEndpoint::End : CandidateEndpoint::Start;
}

static RowConnectionKey row_connection_key(std::size_t first, std::size_t second)
{
    return std::minmax(first, second);
}

static bool scaled_points_equal(const Point &a, const Point &b, coord_t tolerance)
{
    return std::abs(a.x() - b.x()) <= tolerance && std::abs(a.y() - b.y()) <= tolerance;
}

static bool intersection_only_touches_connector_endpoint(
    const Point &connector_start,
    const Point &connector_end,
    const Point &segment_start,
    const Point &segment_end)
{
    return (scaled_points_equal(connector_start, segment_start) ||
            scaled_points_equal(connector_start, segment_end) ||
            scaled_points_equal(connector_end, segment_start) ||
            scaled_points_equal(connector_end, segment_end));
}

static bool connector_crosses_other_candidate(
    const Point &connector_start,
    const Point &connector_end,
    const BoundingBox &connector_bbox,
    const CompositeCandidate &candidate,
    const BoundingBox &candidate_bbox)
{
    if (candidate.polyline.points.size() < 2)
        return false;
    if (candidate_bbox.defined && !connector_bbox.overlap(candidate_bbox))
        return false;

    for (std::size_t i = 1; i < candidate.polyline.points.size(); ++i) {
        const Point &segment_start = candidate.polyline.points[i - 1];
        const Point &segment_end = candidate.polyline.points[i];
        if (!connector_bbox.overlap(segment_bounding_box(segment_start, segment_end)))
            continue;
        if (!Geometry::segments_intersect(connector_start, connector_end, segment_start, segment_end))
            continue;
        if (intersection_only_touches_connector_endpoint(connector_start, connector_end, segment_start, segment_end))
            continue;
        return true;
    }
    return false;
}

static bool connector_crosses_boundary_segments(
    const Point &connector_start,
    const Point &connector_end,
    const BoundingBox &connector_bbox,
    const PrintableRegionBounds &printable_region)
{
    const bool boundary_index_available =
        connector_bbox.defined &&
        printable_region.boundary_cell_size_scaled > 0 &&
        !printable_region.boundary_cells.empty();
    std::vector<std::size_t> nearby_segments = boundary_index_available ?
        boundary_intersection_query(printable_region, connector_bbox) :
        std::vector<std::size_t>();
    const bool use_nearby_segments = boundary_index_available;
    const std::size_t iteration_count = use_nearby_segments ?
        nearby_segments.size() :
        printable_region.boundary_segments.size();

    for (std::size_t iteration_index = 0; iteration_index < iteration_count; ++iteration_index) {
        const std::size_t segment_index = use_nearby_segments ? nearby_segments[iteration_index] : iteration_index;
        if (segment_index >= printable_region.boundary_segments.size())
            continue;
        const BoundarySegment &segment = printable_region.boundary_segments[segment_index];
        if (!connector_bbox.overlap(segment.bbox))
            continue;
        if (!Geometry::segments_intersect(connector_start, connector_end, segment.start, segment.end))
            continue;
        if (intersection_only_touches_connector_endpoint(connector_start, connector_end, segment.start, segment.end))
            continue;
        return true;
    }

    return false;
}

static bool connector_inside_printable_region_fast(
    const Point &connector_start,
    const Point &connector_end,
    const PrintableRegionBounds &printable_region)
{
    const BoundingBox connector_bbox = segment_bounding_box(connector_start, connector_end);
    if (printable_region.bbox.defined && !printable_region.bbox.contains(connector_bbox))
        return false;

    // Candidate endpoints are produced by clipping infill lines to this island.
    // A connector that stays inside the island cannot cross an outer or hole boundary.
    return !connector_crosses_boundary_segments(
        connector_start,
        connector_end,
        connector_bbox,
        printable_region);
}

static bool connector_is_candidate_legal(
    const Point &connector_start,
    const Point &connector_end,
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    const std::vector<PrintableRegionBounds> &printable_region_bounds,
    const CandidateIntersectionIndex *candidate_intersection_index,
    std::size_t source_index,
    std::size_t target_index)
{
    if (scaled_points_equal(connector_start, connector_end))
        return true;

    constexpr std::size_t no_region_index = std::numeric_limits<std::size_t>::max();
    std::size_t region_owner_index = candidate_region_indices[source_index];
    if (region_owner_index == no_region_index)
        region_owner_index = candidate_region_indices[target_index];
    if (region_owner_index != no_region_index &&
        !connector_inside_printable_region_fast(connector_start, connector_end, printable_region_bounds[region_owner_index]))
        return false;

    const BoundingBox connector_bbox = segment_bounding_box(connector_start, connector_end);
    const CompositeCandidate &source_candidate = candidates[source_index];
    std::vector<std::size_t> nearby_candidate_indices;
    const bool candidate_index_available =
        candidate_intersection_index != nullptr &&
        region_owner_index != no_region_index &&
        !candidate_intersection_index->cells.empty();
    if (candidate_index_available)
        nearby_candidate_indices = candidate_intersection_query(
            *candidate_intersection_index, connector_bbox, region_owner_index);

    const bool use_nearby_candidates = candidate_index_available;
    const std::size_t iteration_count = use_nearby_candidates ? nearby_candidate_indices.size() : candidates.size();
    for (std::size_t iteration_index = 0; iteration_index < iteration_count; ++iteration_index) {
        const std::size_t index = use_nearby_candidates ? nearby_candidate_indices[iteration_index] : iteration_index;
        if (index == source_index || index == target_index)
            continue;
        if (index >= candidates.size() || index >= candidate_bounds.size())
            continue;
        if (!candidates_share_physical_route_scope(source_candidate, candidates[index]))
            continue;
        if (connector_crosses_other_candidate(
                connector_start,
                connector_end,
                connector_bbox,
                candidates[index],
                candidate_bounds[index]))
            return false;
    }
    return true;
}

static double canonical_polyline_angle_rad(const Polyline &polyline)
{
    if (polyline.points.size() < 2)
        return 0.0;
    const Point &start = polyline.points.front();
    const Point &end = polyline.points.back();
    double angle = std::atan2(double(end.y() - start.y()), double(end.x() - start.x()));
    while (angle < 0.0)
        angle += PI;
    while (angle >= PI)
        angle -= PI;
    return angle;
}

static RowCandidateView make_row_candidate_view(const CompositeCandidate &candidate, std::size_t candidate_index)
{
    const double angle = canonical_polyline_angle_rad(candidate.polyline);
    const double direction_x = std::cos(angle);
    const double direction_y = std::sin(angle);
    const double normal_x = -direction_y;
    const double normal_y = direction_x;
    const Point &start = candidate.polyline.points.front();
    const Point &end = candidate.polyline.points.back();
    const double midpoint_x_mm = 0.5 * double(start.x() + end.x()) * SCALING_FACTOR;
    const double midpoint_y_mm = 0.5 * double(start.y() + end.y()) * SCALING_FACTOR;

    RowCandidateView view;
    view.candidate_index = candidate_index;
    view.angle_key = static_cast<long long>(std::llround(angle * 1000000.0));
    view.coord_mm = midpoint_x_mm * normal_x + midpoint_y_mm * normal_y;
    view.span_mm = midpoint_x_mm * direction_x + midpoint_y_mm * direction_y;
    view.length_mm = candidate_length_mm(candidate);
    return view;
}

static double row_candidate_span_min(const RowCandidateView &candidate)
{
    return candidate.span_mm - 0.5 * candidate.length_mm;
}

static double row_candidate_span_max(const RowCandidateView &candidate)
{
    return candidate.span_mm + 0.5 * candidate.length_mm;
}

static std::vector<std::vector<RowCandidateView>> row_levels_for_angle(
    std::vector<RowCandidateView> candidates,
    double level_tolerance_mm)
{
    std::sort(candidates.begin(), candidates.end(), [](const RowCandidateView &lhs, const RowCandidateView &rhs) {
        if (std::abs(lhs.coord_mm - rhs.coord_mm) > EPSILON)
            return lhs.coord_mm < rhs.coord_mm;
        if (std::abs(lhs.span_mm - rhs.span_mm) > EPSILON)
            return lhs.span_mm < rhs.span_mm;
        return lhs.candidate_index < rhs.candidate_index;
    });

    std::vector<std::vector<RowCandidateView>> levels;
    for (const RowCandidateView &candidate : candidates) {
        if (levels.empty() || std::abs(candidate.coord_mm - levels.back().front().coord_mm) > level_tolerance_mm)
            levels.push_back({ candidate });
        else
            levels.back().push_back(candidate);
    }

    for (std::vector<RowCandidateView> &level : levels) {
        std::sort(level.begin(), level.end(), [](const RowCandidateView &lhs, const RowCandidateView &rhs) {
            const double lhs_min = row_candidate_span_min(lhs);
            const double rhs_min = row_candidate_span_min(rhs);
            if (std::abs(lhs_min - rhs_min) > EPSILON)
                return lhs_min < rhs_min;
            if (std::abs(lhs.span_mm - rhs.span_mm) > EPSILON)
                return lhs.span_mm < rhs.span_mm;
            return lhs.candidate_index < rhs.candidate_index;
        });
    }
    return levels;
}

static std::vector<RowConnection> row_connection_options(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    const std::vector<PrintableRegionBounds> &printable_region_bounds,
    const CandidateIntersectionIndex *candidate_intersection_index,
    const RowCandidateView &first,
    const RowCandidateView &second,
    double budget_mm)
{
    const CompositeCandidate &first_candidate = candidates[first.candidate_index];
    const CompositeCandidate &second_candidate = candidates[second.candidate_index];
    std::vector<RowConnection> options;

    for (CandidateEndpoint first_endpoint : { CandidateEndpoint::Start, CandidateEndpoint::End }) {
        for (CandidateEndpoint second_endpoint : { CandidateEndpoint::Start, CandidateEndpoint::End }) {
            const Point first_point = candidate_endpoint_point(first_candidate, first_endpoint);
            const Point second_point = candidate_endpoint_point(second_candidate, second_endpoint);
            const double distance_mm = point_distance_mm(first_point, second_point);
            if (distance_mm > budget_mm + EPSILON)
                continue;
            if (!connector_is_candidate_legal(
                    first_point,
                    second_point,
                    candidates,
                    candidate_bounds,
                    candidate_region_indices,
                    printable_region_bounds,
                    candidate_intersection_index,
                    first.candidate_index,
                    second.candidate_index))
                continue;

            RowConnection connection;
            connection.first = first.candidate_index;
            connection.second = second.candidate_index;
            connection.first_endpoint = first_endpoint;
            connection.second_endpoint = second_endpoint;
            connection.first_point = first_point;
            connection.second_point = second_point;
            connection.length_mm = distance_mm;
            options.push_back(connection);
        }
    }

    std::sort(options.begin(), options.end(), [](const RowConnection &lhs, const RowConnection &rhs) {
        if (std::abs(lhs.length_mm - rhs.length_mm) > EPSILON)
            return lhs.length_mm < rhs.length_mm;
        if (lhs.first_endpoint != rhs.first_endpoint)
            return lhs.first_endpoint == CandidateEndpoint::Start;
        return rhs.second_endpoint == CandidateEndpoint::End;
    });
    return options;
}

static bool row_candidate_spans_close(const RowCandidateView &first, const RowCandidateView &second, double budget_mm)
{
    const double first_min = row_candidate_span_min(first);
    const double first_max = row_candidate_span_max(first);
    const double second_min = row_candidate_span_min(second);
    const double second_max = row_candidate_span_max(second);
    const double gap = std::max(second_min - first_max, first_min - second_max);
    return gap <= budget_mm + EPSILON;
}

static bool remaining_row_candidates_too_far(
    const RowCandidateView &first,
    const RowCandidateView &second,
    double budget_mm)
{
    return row_candidate_span_min(second) > row_candidate_span_max(first) + budget_mm + EPSILON;
}

static void append_oriented_candidate_polyline(
    Polylines &ordered,
    const CompositeCandidate &candidate,
    CandidateEndpoint entry_endpoint)
{
    Polyline polyline = candidate.polyline;
    if (entry_endpoint == CandidateEndpoint::End)
        polyline.reverse();
    ordered.push_back(std::move(polyline));
}

static Polyline oriented_candidate_polyline(const CompositeCandidate &candidate, CandidateEndpoint entry_endpoint)
{
    Polyline polyline = candidate.polyline;
    if (entry_endpoint == CandidateEndpoint::End)
        polyline.reverse();
    return polyline;
}

static CompositeRouteSegment make_route_segment(
    const Polyline &polyline,
    const CompositeRouteGraphOptions &options,
    CompositeRoutePhase phase,
    bool emits_plastic,
    bool emits_fiber)
{
    CompositeRouteSegment segment;
    segment.phase = phase;
    segment.polyline = polyline;
    segment.length_mm = polyline_length_mm(polyline);
    segment.plastic_mm_per_mm = emits_plastic ? options.plastic_mm_per_mm : 0.0;
    segment.fiber_mm_per_mm = emits_fiber ? options.fiber_mm_per_mm : 0.0;
    segment.emits_plastic = emits_plastic;
    segment.emits_fiber = emits_fiber;
    return segment;
}

static void append_route_segment(
    CompositeRouteGeometry &geometry,
    Polyline polyline,
    const CompositeRouteGraphOptions &options,
    CompositeRoutePhase phase,
    bool emits_plastic,
    bool emits_fiber)
{
    if (polyline.points.size() < 2 || polyline_length_mm(polyline) <= EPSILON)
        return;
    geometry.planned_segments.push_back(make_route_segment(polyline, options, phase, emits_plastic, emits_fiber));
    geometry.ordered_segments.push_back(std::move(polyline));
}

static void populate_composite_route_segments_from_ordered(CompositeRoute &route, const CompositeRouteGraphOptions &options)
{
    route.planned_segments.clear();
    route.planned_segments.reserve(route.ordered_segments.size());
    for (const Polyline &polyline : route.ordered_segments) {
        if (polyline.points.size() < 2 || polyline_length_mm(polyline) <= EPSILON)
            continue;
        route.planned_segments.push_back(make_route_segment(
            polyline, options, CompositeRoutePhase::Normal, true, true));
    }
}

static Polyline closed_polyline_from_polygon(const Polygon &polygon)
{
    Polyline polyline;
    if (polygon.points.size() < 2)
        return polyline;

    polyline.points = polygon.points;
    if (polyline.points.front() != polyline.points.back())
        polyline.points.push_back(polyline.points.front());
    return polyline;
}

static CompositeRoute make_direct_perimeter_route(
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
    populate_composite_route_segments_from_ordered(route, options);
    refresh_route_metrics(route);
    return route;
}

static Polylines rocket_solid_line_polylines_from_expolygon(
    ExPolygon expolygon,
    const CompositeSurfaceFillOptions &options,
    const Point &reference_point)
{
    const double direction_angle = options.angle_rad + 0.5 * PI;
    expolygon.rotate(-direction_angle);

    BoundingBox bounding_box = expolygon.contour.bounding_box();
    if (!bounding_box.defined)
        return {};

    const coord_t line_spacing = std::max<coord_t>(coord_t(scale_(options.spacing_mm)), 1);
    const Point rotated_reference = reference_point.rotated(-direction_angle);
    bounding_box.merge(align_to_grid(
        bounding_box.min,
        Point(line_spacing, line_spacing),
        rotated_reference));

    Polylines source_lines;
    const coord_t x_max = bounding_box.max.x() + SCALED_EPSILON;
    source_lines.reserve(size_t(std::max<coord_t>((x_max - bounding_box.min.x()) / line_spacing + 1, 0)));
    for (coord_t x = bounding_box.min.x(); x <= x_max; x += line_spacing)
        source_lines.emplace_back(Point(x, bounding_box.min.y()), Point(x, bounding_box.max.y()));

    ExPolygons clip_regions = offset_ex(expolygon, float(scale_(0.02)));
    if (clip_regions.empty())
        clip_regions.push_back(expolygon);

    Polylines clipped = intersection_pl(source_lines, clip_regions);
    for (Polyline &polyline : clipped)
        polyline.rotate(direction_angle);
    return clipped;
}

static std::vector<CompositeCandidate> make_rocket_solid_line_candidates_from_surface(
    const Surface &surface,
    const CompositeSurfaceFillOptions &options)
{
    if (surface.empty() || options.spacing_mm <= 0.0)
        return {};

    ExPolygons expanded_regions = offset_ex(surface.expolygon, float(scale_(options.overlap_mm)));
    if (expanded_regions.empty())
        expanded_regions.push_back(surface.expolygon);

    const Point reference_point = options.bounding_box.defined ?
        options.bounding_box.center() :
        surface.expolygon.contour.bounding_box().center();

    std::vector<CompositeCandidate> candidates;
    std::size_t next_id = options.first_candidate_id;
    for (const ExPolygon &printable_region : expanded_regions) {
        Polylines polylines = rocket_solid_line_polylines_from_expolygon(
            printable_region,
            options,
            reference_point);
        const std::shared_ptr<const ExPolygon> printable_region_ref =
            std::make_shared<ExPolygon>(printable_region);
        candidates.reserve(candidates.size() + polylines.size());
        for (Polyline &polyline : polylines) {
            if (polyline.points.size() < 2)
                continue;
            const double length_mm = polyline_length_mm(polyline);
            if (length_mm <= EPSILON)
                continue;

            CompositeCandidate candidate;
            candidate.id = next_id++;
            candidate.layer_id = options.layer_id;
            candidate.object_id = options.object_id;
            candidate.island_id = options.island_id;
            candidate.region_id = options.region_id;
            candidate.family = options.family;
            candidate.polyline = std::move(polyline);
            candidate.length_mm = length_mm;
            candidate.has_printable_region = true;
            candidate.printable_region_ref = printable_region_ref;
            candidate.fallback_role = fallback_role_for_surface(surface);
            candidate.fallback_line_width_mm = fallback_line_width_for_surface(surface, options);
            candidates.push_back(std::move(candidate));
        }
    }

    return candidates;
}

static const RowConnection *find_row_connection(
    const RowConnectionMap &connections,
    std::size_t first,
    std::size_t second)
{
    const auto key = row_connection_key(first, second);
    auto it = connections.find(key);
    return it == connections.end() ? nullptr : &it->second;
}

static CandidateEndpoint connection_endpoint_for_candidate(const RowConnection &connection, std::size_t candidate_index)
{
    return candidate_index == connection.first ? connection.first_endpoint : connection.second_endpoint;
}

static Point connection_point_for_candidate(const RowConnection &connection, std::size_t candidate_index)
{
    return candidate_index == connection.first ? connection.first_point : connection.second_point;
}

static Polylines route_polylines_from_row_component(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const RowConnectionMap &connections)
{
    if (component.empty())
        return {};

    std::set<std::size_t> component_set(component.begin(), component.end());
    std::size_t start = component.front();
    for (std::size_t candidate_index : component) {
        std::size_t degree = 0;
        for (std::size_t other : adjacency[candidate_index])
            if (component_set.count(other) != 0)
                ++degree;
        if (degree <= 1) {
            start = candidate_index;
            break;
        }
    }

    std::vector<std::size_t> sequence;
    sequence.reserve(component.size());
    std::set<std::size_t> visited;
    std::vector<std::size_t> stack { start };
    while (!stack.empty()) {
        const std::size_t current = stack.back();
        stack.pop_back();
        if (visited.count(current) != 0)
            continue;
        visited.insert(current);
        sequence.push_back(current);

        std::vector<std::size_t> neighbors;
        for (std::size_t other : adjacency[current])
            if (component_set.count(other) != 0 && visited.count(other) == 0)
                neighbors.push_back(other);
        std::sort(neighbors.begin(), neighbors.end(), std::greater<std::size_t>());
        for (std::size_t other : neighbors)
            stack.push_back(other);
    }

    for (std::size_t candidate_index : component) {
        if (visited.count(candidate_index) == 0)
            sequence.push_back(candidate_index);
    }

    Polylines ordered;
    bool has_current_end = false;
    Point current_end;
    CandidateEndpoint first_entry = CandidateEndpoint::Start;
    if (sequence.size() >= 2) {
        if (const RowConnection *connection = find_row_connection(connections, sequence[0], sequence[1]))
            first_entry = opposite_endpoint(connection_endpoint_for_candidate(*connection, sequence[0]));
    }

    for (std::size_t sequence_index = 0; sequence_index < sequence.size(); ++sequence_index) {
        const std::size_t candidate_index = sequence[sequence_index];
        CandidateEndpoint entry_endpoint = CandidateEndpoint::Start;

        if (sequence_index == 0) {
            entry_endpoint = first_entry;
        } else if (const RowConnection *connection = find_row_connection(connections, sequence[sequence_index - 1], candidate_index)) {
            const Point previous_connection_point = connection_point_for_candidate(*connection, sequence[sequence_index - 1]);
            const Point current_connection_point = connection_point_for_candidate(*connection, candidate_index);
            if (has_current_end && !scaled_points_equal(current_end, previous_connection_point))
                ordered.emplace_back(current_end, previous_connection_point);
            if (!scaled_points_equal(previous_connection_point, current_connection_point))
                ordered.emplace_back(previous_connection_point, current_connection_point);
            current_end = current_connection_point;
            has_current_end = true;
            entry_endpoint = connection_endpoint_for_candidate(*connection, candidate_index);
        } else if (has_current_end) {
            const CompositeCandidate &candidate = candidates[candidate_index];
            const double dist_to_start = point_distance_mm(current_end, candidate.polyline.points.front());
            const double dist_to_end = point_distance_mm(current_end, candidate.polyline.points.back());
            entry_endpoint = dist_to_end < dist_to_start ? CandidateEndpoint::End : CandidateEndpoint::Start;
            ordered.emplace_back(current_end, candidate_endpoint_point(candidate, entry_endpoint));
        }

        append_oriented_candidate_polyline(ordered, candidates[candidate_index], entry_endpoint);
        current_end = ordered.back().points.back();
        has_current_end = true;
    }

    return ordered;
}

static const std::vector<RowConnection> *row_connection_options_for_pair(
    const RowConnectionOptionsMap &connection_options,
    std::size_t first,
    std::size_t second)
{
    const auto it = connection_options.find(row_connection_key(first, second));
    return it == connection_options.end() ? nullptr : &it->second;
}

static CompositeNodeConnectionKey composite_node_connection_key(std::size_t first, std::size_t second)
{
    return std::minmax(first, second);
}

static const RowConnection *row_connection_matching_endpoints(
    const std::vector<RowConnection> &options,
    std::size_t first_candidate,
    CandidateEndpoint first_endpoint,
    std::size_t second_candidate,
    CandidateEndpoint second_endpoint)
{
    for (const RowConnection &connection : options) {
        if (connection_endpoint_for_candidate(connection, first_candidate) == first_endpoint &&
            connection_endpoint_for_candidate(connection, second_candidate) == second_endpoint)
            return &connection;
    }
    return nullptr;
}

static bool row_pair_has_node_internal_connections(
    const std::vector<RowConnection> &options,
    std::size_t first_candidate,
    std::size_t second_candidate)
{
    bool start_start = false;
    bool start_end = false;
    bool end_start = false;
    bool end_end = false;

    for (const RowConnection &connection : options) {
        const CandidateEndpoint first_endpoint = connection_endpoint_for_candidate(connection, first_candidate);
        const CandidateEndpoint second_endpoint = connection_endpoint_for_candidate(connection, second_candidate);
        if (first_endpoint == CandidateEndpoint::Start && second_endpoint == CandidateEndpoint::Start)
            start_start = true;
        else if (first_endpoint == CandidateEndpoint::Start && second_endpoint == CandidateEndpoint::End)
            start_end = true;
        else if (first_endpoint == CandidateEndpoint::End && second_endpoint == CandidateEndpoint::Start)
            end_start = true;
        else if (first_endpoint == CandidateEndpoint::End && second_endpoint == CandidateEndpoint::End)
            end_end = true;
    }

    return (start_start && end_end) || (start_end && end_start);
}

static bool find_node_entries_for_ordered_candidates_from(
    const std::vector<std::size_t> &ordered_candidates,
    const RowConnectionOptionsMap &connection_options,
    std::size_t connection_index,
    std::vector<CandidateEndpoint> &entries)
{
    if (connection_index + 1 >= ordered_candidates.size())
        return true;

    const std::size_t current = ordered_candidates[connection_index];
    const std::size_t next = ordered_candidates[connection_index + 1];
    const std::vector<RowConnection> *options =
        row_connection_options_for_pair(connection_options, current, next);
    if (options == nullptr)
        return false;

    const CandidateEndpoint required_exit = opposite_endpoint(entries[connection_index]);
    for (const RowConnection &connection : *options) {
        if (connection_endpoint_for_candidate(connection, current) != required_exit)
            continue;
        entries[connection_index + 1] = connection_endpoint_for_candidate(connection, next);
        if (find_node_entries_for_ordered_candidates_from(
                ordered_candidates,
                connection_options,
                connection_index + 1,
                entries))
            return true;
    }

    return false;
}

static bool node_entries_for_ordered_candidates(
    const std::vector<std::size_t> &ordered_candidates,
    const RowConnectionOptionsMap &connection_options,
    std::vector<CandidateEndpoint> &entries)
{
    entries.clear();
    if (ordered_candidates.empty())
        return false;

    entries.assign(ordered_candidates.size(), CandidateEndpoint::Start);
    if (ordered_candidates.size() == 1)
        return true;

    for (CandidateEndpoint first_entry : { CandidateEndpoint::Start, CandidateEndpoint::End }) {
        entries[0] = first_entry;
        if (find_node_entries_for_ordered_candidates_from(
                ordered_candidates,
                connection_options,
                0,
                entries))
            return true;
    }

    return false;
}

static double node_internal_connector_length_mm(
    const std::vector<std::size_t> &ordered_candidates,
    const std::vector<CandidateEndpoint> &entries,
    const RowConnectionOptionsMap &connection_options)
{
    double length_mm = 0.0;
    if (ordered_candidates.size() < 2 || entries.size() != ordered_candidates.size())
        return length_mm;

    for (std::size_t i = 1; i < ordered_candidates.size(); ++i) {
        const std::size_t previous = ordered_candidates[i - 1];
        const std::size_t current = ordered_candidates[i];
        const std::vector<RowConnection> *options =
            row_connection_options_for_pair(connection_options, previous, current);
        if (options == nullptr)
            continue;
        const RowConnection *connection = row_connection_matching_endpoints(
            *options,
            previous,
            opposite_endpoint(entries[i - 1]),
            current,
            entries[i]);
        if (connection != nullptr)
            length_mm += connection->length_mm;
    }

    return length_mm;
}

static std::vector<std::size_t> ordered_internal_node_component(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &internal_adjacency)
{
    if (component.size() <= 1)
        return component;

    const std::set<std::size_t> component_set(component.begin(), component.end());
    std::size_t start = component.front();
    bool found_tail = false;
    for (std::size_t candidate_index : component) {
        std::size_t degree = 0;
        for (std::size_t other : internal_adjacency[candidate_index])
            if (component_set.count(other) != 0)
                ++degree;
        if (degree > 2)
            return {};
        if (degree <= 1 &&
            (!found_tail || candidates[candidate_index].id < candidates[start].id)) {
            start = candidate_index;
            found_tail = true;
        }
    }

    if (!found_tail)
        return {};

    std::vector<std::size_t> ordered;
    ordered.reserve(component.size());
    std::set<std::size_t> visited;
    std::size_t previous = std::numeric_limits<std::size_t>::max();
    std::size_t current = start;
    while (current != std::numeric_limits<std::size_t>::max()) {
        ordered.push_back(current);
        visited.insert(current);

        std::vector<std::size_t> next_candidates;
        for (std::size_t other : internal_adjacency[current])
            if (component_set.count(other) != 0 && other != previous && visited.count(other) == 0)
                next_candidates.push_back(other);

        if (next_candidates.empty())
            break;

        std::sort(next_candidates.begin(), next_candidates.end(), [&candidates](std::size_t lhs, std::size_t rhs) {
            return candidates[lhs].id < candidates[rhs].id;
        });
        previous = current;
        current = next_candidates.front();
    }

    return ordered.size() == component.size() ? ordered : std::vector<std::size_t>{};
}

static CompositeNode make_single_candidate_node(
    const std::vector<CompositeCandidate> &candidates,
    std::size_t node_id,
    std::size_t candidate_index)
{
    CompositeNode node;
    node.id = node_id;
    node.candidate_indices.push_back(candidate_index);
    node.canonical_entry_endpoints.push_back(CandidateEndpoint::Start);
    node.owned_length_mm = candidate_length_mm(candidates[candidate_index]);
    return node;
}

static std::vector<CompositeNode> build_composite_nodes_from_row_graph(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<RowCandidateView> &row_candidates,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const RowConnectionOptionsMap &connection_options,
    std::vector<std::size_t> &candidate_to_node)
{
    constexpr std::size_t no_node = std::numeric_limits<std::size_t>::max();
    candidate_to_node.assign(candidates.size(), no_node);

    std::vector<unsigned char> eligible(candidates.size(), 0);
    for (const RowCandidateView &row_candidate : row_candidates) {
        const std::size_t candidate_index = row_candidate.candidate_index;
        if (candidate_index >= adjacency.size())
            continue;
        if (adjacency[candidate_index].size() <= 2)
            eligible[candidate_index] = 1;
    }

    std::vector<std::vector<std::size_t>> internal_adjacency(candidates.size());
    for (const auto &entry : connection_options) {
        const std::size_t first = entry.first.first;
        const std::size_t second = entry.first.second;
        if (first >= candidates.size() || second >= candidates.size())
            continue;
        if (eligible[first] == 0 || eligible[second] == 0)
            continue;
        if (!row_pair_has_node_internal_connections(entry.second, first, second))
            continue;
        internal_adjacency[first].push_back(second);
        internal_adjacency[second].push_back(first);
    }

    std::vector<CompositeNode> nodes;
    std::vector<unsigned char> visited(candidates.size(), 0);
    for (const RowCandidateView &row_candidate : row_candidates) {
        const std::size_t seed = row_candidate.candidate_index;
        if (seed >= candidates.size() || visited[seed] != 0)
            continue;

        if (eligible[seed] == 0 || internal_adjacency[seed].empty()) {
            visited[seed] = 1;
            nodes.push_back(make_single_candidate_node(candidates, nodes.size(), seed));
            candidate_to_node[seed] = nodes.back().id;
            continue;
        }

        std::vector<std::size_t> component;
        std::vector<std::size_t> queue { seed };
        visited[seed] = 1;
        for (std::size_t pos = 0; pos < queue.size(); ++pos) {
            const std::size_t current = queue[pos];
            component.push_back(current);
            for (std::size_t other : internal_adjacency[current]) {
                if (other >= visited.size() || visited[other] != 0)
                    continue;
                visited[other] = 1;
                queue.push_back(other);
            }
        }

        const std::vector<std::size_t> ordered =
            ordered_internal_node_component(candidates, component, internal_adjacency);
        std::vector<CandidateEndpoint> entries;
        if (ordered.size() <= 1 || !node_entries_for_ordered_candidates(ordered, connection_options, entries)) {
            for (std::size_t candidate_index : component) {
                nodes.push_back(make_single_candidate_node(candidates, nodes.size(), candidate_index));
                candidate_to_node[candidate_index] = nodes.back().id;
            }
            continue;
        }

        CompositeNode node;
        node.id = nodes.size();
        node.candidate_indices = ordered;
        node.canonical_entry_endpoints = entries;
        for (std::size_t candidate_index : node.candidate_indices)
            node.owned_length_mm += candidate_length_mm(candidates[candidate_index]);
        node.internal_connector_length_mm = node_internal_connector_length_mm(
            node.candidate_indices,
            node.canonical_entry_endpoints,
            connection_options);

        for (std::size_t candidate_index : node.candidate_indices)
            candidate_to_node[candidate_index] = node.id;
        nodes.push_back(std::move(node));
    }

    for (const RowCandidateView &row_candidate : row_candidates) {
        const std::size_t candidate_index = row_candidate.candidate_index;
        if (candidate_index < candidate_to_node.size() && candidate_to_node[candidate_index] == no_node) {
            nodes.push_back(make_single_candidate_node(candidates, nodes.size(), candidate_index));
            candidate_to_node[candidate_index] = nodes.back().id;
        }
    }

    return nodes;
}

static bool composite_node_endpoint_for_candidate_endpoint(
    const CompositeNode &node,
    std::size_t candidate_index,
    CandidateEndpoint candidate_endpoint,
    CandidateEndpoint &node_endpoint)
{
    if (node.candidate_indices.empty() || node.canonical_entry_endpoints.size() != node.candidate_indices.size())
        return false;

    const std::size_t first_candidate = node.candidate_indices.front();
    const CandidateEndpoint first_entry = node.canonical_entry_endpoints.front();
    if (candidate_index == first_candidate && candidate_endpoint == first_entry) {
        node_endpoint = CandidateEndpoint::Start;
        return true;
    }

    const std::size_t last_candidate = node.candidate_indices.back();
    const CandidateEndpoint last_exit = opposite_endpoint(node.canonical_entry_endpoints.back());
    if (candidate_index == last_candidate && candidate_endpoint == last_exit) {
        node_endpoint = CandidateEndpoint::End;
        return true;
    }

    return false;
}

static const std::vector<CompositeNodeConnection> *composite_node_connection_options_for_pair(
    const CompositeNodeConnectionOptionsMap &connection_options,
    std::size_t first,
    std::size_t second)
{
    const auto it = connection_options.find(composite_node_connection_key(first, second));
    return it == connection_options.end() ? nullptr : &it->second;
}

static CandidateEndpoint connection_endpoint_for_node(const CompositeNodeConnection &connection, std::size_t node_index)
{
    return node_index == connection.first ? connection.first_endpoint : connection.second_endpoint;
}

static Point connection_point_for_node(const CompositeNodeConnection &connection, std::size_t node_index)
{
    return node_index == connection.first ? connection.first_point : connection.second_point;
}

static void build_composite_node_graph(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &candidate_to_node,
    const RowConnectionOptionsMap &row_connection_options,
    std::vector<std::vector<std::size_t>> &node_adjacency,
    CompositeNodeConnectionMap &node_connections,
    CompositeNodeConnectionOptionsMap &node_connection_options)
{
    node_adjacency.assign(nodes.size(), {});
    node_connections.clear();
    node_connection_options.clear();

    for (const auto &entry : row_connection_options) {
        std::vector<CompositeNodeConnection> options;
        for (const RowConnection &row_connection : entry.second) {
            if (row_connection.first >= candidate_to_node.size() || row_connection.second >= candidate_to_node.size())
                continue;

            const std::size_t first_node = candidate_to_node[row_connection.first];
            const std::size_t second_node = candidate_to_node[row_connection.second];
            if (first_node == std::numeric_limits<std::size_t>::max() ||
                second_node == std::numeric_limits<std::size_t>::max() ||
                first_node == second_node)
                continue;

            CandidateEndpoint first_node_endpoint;
            CandidateEndpoint second_node_endpoint;
            if (!composite_node_endpoint_for_candidate_endpoint(
                    nodes[first_node],
                    row_connection.first,
                    row_connection.first_endpoint,
                    first_node_endpoint))
                continue;
            if (!composite_node_endpoint_for_candidate_endpoint(
                    nodes[second_node],
                    row_connection.second,
                    row_connection.second_endpoint,
                    second_node_endpoint))
                continue;

            CompositeNodeConnection connection;
            connection.first = first_node;
            connection.second = second_node;
            connection.first_endpoint = first_node_endpoint;
            connection.second_endpoint = second_node_endpoint;
            connection.first_point = row_connection.first_point;
            connection.second_point = row_connection.second_point;
            connection.length_mm = row_connection.length_mm;
            options.push_back(connection);
        }

        if (options.empty())
            continue;

        std::sort(options.begin(), options.end(), [](const CompositeNodeConnection &lhs, const CompositeNodeConnection &rhs) {
            if (std::abs(lhs.length_mm - rhs.length_mm) > EPSILON)
                return lhs.length_mm < rhs.length_mm;
            if (lhs.first_endpoint != rhs.first_endpoint)
                return lhs.first_endpoint == CandidateEndpoint::Start;
            return rhs.second_endpoint == CandidateEndpoint::End;
        });

        const CompositeNodeConnectionKey key = composite_node_connection_key(options.front().first, options.front().second);
        const CompositeNodeConnection &best_connection = options.front();
        auto existing = node_connections.find(key);
        if (existing != node_connections.end() && existing->second.length_mm <= best_connection.length_mm + EPSILON)
            continue;

        if (existing == node_connections.end()) {
            node_adjacency[best_connection.first].push_back(best_connection.second);
            node_adjacency[best_connection.second].push_back(best_connection.first);
        }
        node_connections[key] = best_connection;
        node_connection_options[key] = std::move(options);
    }
}

static std::vector<std::size_t> composite_node_component_tails(
    const std::vector<std::size_t> &component,
    const std::set<std::size_t> &component_set,
    const std::vector<std::vector<std::size_t>> &adjacency)
{
    if (component.size() <= 1)
        return component;

    std::vector<std::size_t> tails;
    for (std::size_t node_index : component) {
        std::size_t degree = 0;
        for (std::size_t other : adjacency[node_index])
            if (component_set.count(other) != 0)
                ++degree;
        if (degree != 2)
            tails.push_back(node_index);
    }
    if (tails.size() >= 2)
        return tails;
    return component;
}

static double composite_node_score_length_mm(const CompositeNode &node)
{
    return node.owned_length_mm + node.internal_connector_length_mm;
}

static std::vector<std::size_t> composite_node_neighbors_in_component(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const CompositeNodeConnectionMap &connections,
    const std::vector<unsigned char> &component_mask,
    const std::vector<unsigned char> &used,
    std::size_t current)
{
    std::vector<std::size_t> neighbors;
    if (current >= adjacency.size())
        return neighbors;

    for (std::size_t other : adjacency[current]) {
        if (other >= component_mask.size() || component_mask[other] == 0 || used[other] != 0)
            continue;
        neighbors.push_back(other);
    }

    std::sort(neighbors.begin(), neighbors.end(), [&nodes, &connections, current](std::size_t lhs, std::size_t rhs) {
        const double lhs_length = composite_node_score_length_mm(nodes[lhs]);
        const double rhs_length = composite_node_score_length_mm(nodes[rhs]);
        if (std::abs(lhs_length - rhs_length) > EPSILON)
            return lhs_length > rhs_length;

        const auto lhs_it = connections.find(composite_node_connection_key(current, lhs));
        const auto rhs_it = connections.find(composite_node_connection_key(current, rhs));
        const double lhs_connection_length = lhs_it == connections.end() ? std::numeric_limits<double>::infinity() : lhs_it->second.length_mm;
        const double rhs_connection_length = rhs_it == connections.end() ? std::numeric_limits<double>::infinity() : rhs_it->second.length_mm;
        if (std::abs(lhs_connection_length - rhs_connection_length) > EPSILON)
            return lhs_connection_length < rhs_connection_length;
        return nodes[lhs].id < nodes[rhs].id;
    });

    return neighbors;
}

static void enumerate_composite_node_paths_depth_first(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const CompositeNodeConnectionMap &connections,
    const std::vector<unsigned char> &component_mask,
    std::vector<unsigned char> &used,
    std::vector<std::size_t> &path,
    std::set<std::vector<std::size_t>> &unique_paths,
    std::size_t cutoff)
{
    if (path.empty() || unique_paths.size() >= MAX_ROW_PATH_COUNT)
        return;

    if (path.size() >= cutoff) {
        unique_paths.insert(path);
        return;
    }

    const std::size_t current = path.back();
    const std::vector<std::size_t> neighbors = composite_node_neighbors_in_component(
        nodes, adjacency, connections, component_mask, used, current);
    bool extended = false;
    for (std::size_t other : neighbors) {
        if (unique_paths.size() >= MAX_ROW_PATH_COUNT)
            break;
        used[other] = 1;
        path.push_back(other);
        enumerate_composite_node_paths_depth_first(
            nodes, adjacency, connections, component_mask, used, path, unique_paths, cutoff);
        path.pop_back();
        used[other] = 0;
        extended = true;
    }

    if (!extended)
        unique_paths.insert(path);
}

static std::vector<std::vector<std::size_t>> enumerate_composite_node_paths(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const CompositeNodeConnectionMap &connections)
{
    std::set<std::vector<std::size_t>> unique_paths;
    for (std::size_t node_index : component)
        unique_paths.insert({ node_index });
    if (component.size() <= 1)
        return std::vector<std::vector<std::size_t>>(unique_paths.begin(), unique_paths.end());

    const std::set<std::size_t> component_set(component.begin(), component.end());
    const std::vector<std::size_t> tails = composite_node_component_tails(component, component_set, adjacency);
    std::vector<unsigned char> component_mask(adjacency.size(), 0);
    for (std::size_t node_index : component)
        if (node_index < component_mask.size())
            component_mask[node_index] = 1;

    const std::size_t cutoff = std::min<std::size_t>(component.size(), MAX_ROW_GREEDY_PATH_LENGTH);
    for (std::size_t tail : tails) {
        if (unique_paths.size() >= MAX_ROW_PATH_COUNT)
            return std::vector<std::vector<std::size_t>>(unique_paths.begin(), unique_paths.end());
        std::vector<unsigned char> used(adjacency.size(), 0);
        if (tail < used.size())
            used[tail] = 1;
        std::vector<std::size_t> path { tail };
        enumerate_composite_node_paths_depth_first(
            nodes, adjacency, connections, component_mask, used, path, unique_paths, cutoff);
    }

    std::vector<std::size_t> by_length = component;
    std::sort(by_length.begin(), by_length.end(), [&nodes](std::size_t lhs, std::size_t rhs) {
        const double lhs_length = composite_node_score_length_mm(nodes[lhs]);
        const double rhs_length = composite_node_score_length_mm(nodes[rhs]);
        if (std::abs(lhs_length - rhs_length) > EPSILON)
            return lhs_length > rhs_length;
        return nodes[lhs].id < nodes[rhs].id;
    });

    for (std::size_t seed : by_length) {
        if (unique_paths.size() >= MAX_ROW_PATH_COUNT)
            break;
        std::vector<unsigned char> used(adjacency.size(), 0);
        if (seed < used.size())
            used[seed] = 1;
        std::vector<std::size_t> path { seed };
        enumerate_composite_node_paths_depth_first(
            nodes, adjacency, connections, component_mask, used, path, unique_paths, cutoff);
    }

    return std::vector<std::vector<std::size_t>>(unique_paths.begin(), unique_paths.end());
}

static bool find_composite_node_path_endpoint_entries_from(
    const std::vector<std::size_t> &path,
    const CompositeNodeConnectionOptionsMap &connection_options,
    std::size_t connection_index,
    std::vector<CandidateEndpoint> &entries)
{
    if (connection_index + 1 >= path.size())
        return true;

    const std::vector<CompositeNodeConnection> *options =
        composite_node_connection_options_for_pair(connection_options, path[connection_index], path[connection_index + 1]);
    if (options == nullptr)
        return false;

    const CandidateEndpoint required_exit = opposite_endpoint(entries[connection_index]);
    for (const CompositeNodeConnection &connection : *options) {
        if (connection_endpoint_for_node(connection, path[connection_index]) != required_exit)
            continue;
        entries[connection_index + 1] = connection_endpoint_for_node(connection, path[connection_index + 1]);
        if (find_composite_node_path_endpoint_entries_from(path, connection_options, connection_index + 1, entries))
            return true;
    }

    return false;
}

static bool composite_node_path_endpoint_entries(
    const std::vector<std::size_t> &path,
    const CompositeNodeConnectionOptionsMap &connection_options,
    std::vector<CandidateEndpoint> &entries)
{
    entries.clear();
    if (path.empty())
        return false;

    entries.assign(path.size(), CandidateEndpoint::Start);
    if (path.size() == 1)
        return true;

    const std::vector<CompositeNodeConnection> *first_options =
        composite_node_connection_options_for_pair(connection_options, path[0], path[1]);
    if (first_options == nullptr)
        return false;

    for (const CompositeNodeConnection &connection : *first_options) {
        entries[0] = opposite_endpoint(connection_endpoint_for_node(connection, path[0]));
        entries[1] = connection_endpoint_for_node(connection, path[1]);
        if (find_composite_node_path_endpoint_entries_from(path, connection_options, 1, entries))
            return true;
    }

    return false;
}

static std::vector<std::size_t> composite_node_combination_key(std::vector<std::size_t> path)
{
    std::sort(path.begin(), path.end());
    path.erase(std::unique(path.begin(), path.end()), path.end());
    return path;
}

static double composite_node_path_owned_length_mm(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &path)
{
    double owned_length_mm = 0.0;
    for (std::size_t node_index : path)
        owned_length_mm += nodes[node_index].owned_length_mm;
    return owned_length_mm;
}

static double composite_node_path_score_length_mm(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &path,
    const CompositeRouteGraphOptions &options)
{
    double score_length_mm = 0.0;
    for (std::size_t node_index : path)
        score_length_mm += composite_node_score_length_mm(nodes[node_index]);
    if (!path.empty())
        score_length_mm += double(path.size() - 1) * options.line_spacing_mm;
    return score_length_mm;
}

static std::vector<CompositeNodeRouteCandidate> composite_node_route_candidates(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const CompositeNodeConnectionMap &connections,
    const CompositeNodeConnectionOptionsMap &connection_options,
    const CompositeRouteGraphOptions &options,
    double threshold_mm)
{
    std::map<std::vector<std::size_t>, CompositeNodeRouteCandidate> by_combination;
    const std::vector<std::vector<std::size_t>> paths =
        enumerate_composite_node_paths(nodes, component, adjacency, connections);

    for (const std::vector<std::size_t> &path : paths) {
        for (std::size_t width = path.size(); width >= 1; --width) {
            for (std::size_t start = 0; start + width <= path.size(); ++start) {
                std::vector<std::size_t> subpath(path.begin() + start, path.begin() + start + width);
                const double owned_length_mm = composite_node_path_owned_length_mm(nodes, subpath);
                const double score_length_mm = composite_node_path_score_length_mm(nodes, subpath, options);
                if (!route_length_is_cut_safe(score_length_mm, threshold_mm))
                    continue;

                CompositeNodeRouteCandidate candidate;
                candidate.path = std::move(subpath);
                if (!composite_node_path_endpoint_entries(candidate.path, connection_options, candidate.entry_endpoints))
                    continue;
                candidate.key = composite_node_combination_key(candidate.path);
                candidate.owned_length_mm = owned_length_mm;
                candidate.score_length_mm = score_length_mm;

                auto existing = by_combination.find(candidate.key);
                if (existing == by_combination.end()) {
                    if (by_combination.size() >= MAX_ROW_ROUTE_CANDIDATE_COUNT)
                        continue;
                    by_combination.emplace(candidate.key, std::move(candidate));
                } else if (candidate.score_length_mm > existing->second.score_length_mm + EPSILON ||
                           (std::abs(candidate.score_length_mm - existing->second.score_length_mm) <= EPSILON &&
                            candidate.path.size() > existing->second.path.size())) {
                    existing->second = std::move(candidate);
                }
            }
            if (width == 1)
                break;
        }
    }

    std::vector<CompositeNodeRouteCandidate> route_candidates;
    route_candidates.reserve(by_combination.size());
    for (auto &item : by_combination)
        route_candidates.push_back(std::move(item.second));
    std::sort(route_candidates.begin(), route_candidates.end(), [](const CompositeNodeRouteCandidate &lhs, const CompositeNodeRouteCandidate &rhs) {
        if (lhs.path.size() != rhs.path.size())
            return lhs.path.size() > rhs.path.size();
        if (std::abs(lhs.score_length_mm - rhs.score_length_mm) > EPSILON)
            return lhs.score_length_mm > rhs.score_length_mm;
        return lhs.key < rhs.key;
    });
    return route_candidates;
}

static bool composite_node_route_intersects_used(const CompositeNodeRouteCandidate &candidate, const std::vector<unsigned char> &used)
{
    for (std::size_t node_index : candidate.key)
        if (node_index < used.size() && used[node_index] != 0)
            return true;
    return false;
}

static void composite_node_route_mark_used(const CompositeNodeRouteCandidate &candidate, std::vector<unsigned char> &used)
{
    for (std::size_t node_index : candidate.key)
        if (node_index < used.size())
            used[node_index] = 1;
}

static std::vector<CompositeNodeRouteCandidate> select_best_composite_node_route_group(
    const std::vector<CompositeNodeRouteCandidate> &route_candidates)
{
    std::vector<CompositeNodeRouteCandidate> best_group;
    double best_owned_length_mm = -1.0;
    std::size_t max_node_index = 0;
    for (const CompositeNodeRouteCandidate &candidate : route_candidates)
        for (std::size_t node_index : candidate.key)
            max_node_index = std::max(max_node_index, node_index);

    std::vector<unsigned char> used(max_node_index + 1, 0);
    const std::size_t seed_count = std::min(route_candidates.size(), MAX_ROW_ROUTE_SELECTION_SEEDS);
    for (std::size_t seed_index = 0; seed_index < seed_count; ++seed_index) {
        const CompositeNodeRouteCandidate &seed = route_candidates[seed_index];
        std::fill(used.begin(), used.end(), 0);
        std::vector<CompositeNodeRouteCandidate> group { seed };
        composite_node_route_mark_used(seed, used);
        double owned_length_mm = seed.owned_length_mm;

        for (const CompositeNodeRouteCandidate &candidate : route_candidates) {
            if (composite_node_route_intersects_used(candidate, used))
                continue;
            group.push_back(candidate);
            composite_node_route_mark_used(candidate, used);
            owned_length_mm += candidate.owned_length_mm;
        }

        if (owned_length_mm > best_owned_length_mm + EPSILON) {
            best_owned_length_mm = owned_length_mm;
            best_group = std::move(group);
        } else if (std::abs(owned_length_mm - best_owned_length_mm) <= EPSILON &&
                   (best_group.empty() || group.size() < best_group.size())) {
            best_group = std::move(group);
        }
    }

    return best_group;
}

static std::vector<std::vector<std::size_t>> unselected_composite_node_components(
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const std::vector<unsigned char> &selected)
{
    std::vector<std::vector<std::size_t>> components;
    if (component.empty())
        return components;

    std::vector<unsigned char> component_mask(adjacency.size(), 0);
    for (std::size_t node_index : component)
        if (node_index < component_mask.size() &&
            node_index < selected.size() &&
            selected[node_index] == 0)
            component_mask[node_index] = 1;

    std::vector<unsigned char> visited(adjacency.size(), 0);
    for (std::size_t seed : component) {
        if (seed >= component_mask.size() || component_mask[seed] == 0 || visited[seed] != 0)
            continue;

        std::vector<std::size_t> queue { seed };
        std::vector<std::size_t> remainder;
        visited[seed] = 1;
        for (std::size_t pos = 0; pos < queue.size(); ++pos) {
            const std::size_t current = queue[pos];
            remainder.push_back(current);

            if (current >= adjacency.size())
                continue;
            for (std::size_t other : adjacency[current]) {
                if (other >= component_mask.size() || component_mask[other] == 0 || visited[other] != 0)
                    continue;
                visited[other] = 1;
                queue.push_back(other);
            }
        }

        if (!remainder.empty())
            components.push_back(std::move(remainder));
    }

    return components;
}

static void mark_composite_node_route_group_selected(
    const std::vector<CompositeNodeRouteCandidate> &group,
    std::vector<unsigned char> &selected)
{
    for (const CompositeNodeRouteCandidate &candidate : group)
        composite_node_route_mark_used(candidate, selected);
}

static double composite_node_component_owned_length_mm(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &component)
{
    double owned_length_mm = 0.0;
    for (std::size_t node_index : component)
        if (node_index < nodes.size())
            owned_length_mm += nodes[node_index].owned_length_mm;
    return owned_length_mm;
}

static double composite_node_route_group_owned_length_mm(
    const std::vector<CompositeNodeRouteCandidate> &group)
{
    double owned_length_mm = 0.0;
    for (const CompositeNodeRouteCandidate &candidate : group)
        owned_length_mm += candidate.owned_length_mm;
    return owned_length_mm;
}

static std::vector<CompositeNodeRouteCandidate> select_composite_node_route_group_with_completion(
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &component,
    const std::vector<std::vector<std::size_t>> &adjacency,
    const CompositeNodeConnectionMap &connections,
    const CompositeNodeConnectionOptionsMap &connection_options,
    const CompositeRouteGraphOptions &options,
    double threshold_mm)
{
    std::vector<CompositeNodeRouteCandidate> route_candidates =
        composite_node_route_candidates(nodes, component, adjacency, connections, connection_options, options, threshold_mm);
    std::vector<CompositeNodeRouteCandidate> selected_routes =
        select_best_composite_node_route_group(route_candidates);

    const double component_owned_length_mm = composite_node_component_owned_length_mm(nodes, component);
    const double selected_owned_length_mm = composite_node_route_group_owned_length_mm(selected_routes);
    const double uncovered_ratio = component_owned_length_mm > EPSILON ?
        std::max(0.0, component_owned_length_mm - selected_owned_length_mm) / component_owned_length_mm :
        0.0;
    if (component.size() > MAX_ROW_ROUTE_COMPLETION_COMPONENT_NODES ||
        uncovered_ratio < MIN_ROW_ROUTE_COMPLETION_UNCOVERED_RATIO)
        return selected_routes;

    std::vector<unsigned char> selected(nodes.size(), 0);
    mark_composite_node_route_group_selected(selected_routes, selected);

    for (std::size_t pass = 0; pass < MAX_ROW_ROUTE_COMPLETION_PASSES; ++pass) {
        bool added_route = false;
        const std::vector<std::vector<std::size_t>> remainder_components =
            unselected_composite_node_components(component, adjacency, selected);

        for (const std::vector<std::size_t> &remainder : remainder_components) {
            if (remainder.empty())
                continue;
            if (remainder.size() > MAX_ROW_ROUTE_COMPLETION_COMPONENT_NODES)
                continue;

            std::vector<CompositeNodeRouteCandidate> remainder_candidates =
                composite_node_route_candidates(nodes, remainder, adjacency, connections, connection_options, options, threshold_mm);
            std::vector<CompositeNodeRouteCandidate> remainder_selected =
                select_best_composite_node_route_group(remainder_candidates);

            for (CompositeNodeRouteCandidate &candidate : remainder_selected) {
                if (composite_node_route_intersects_used(candidate, selected))
                    continue;
                composite_node_route_mark_used(candidate, selected);
                selected_routes.push_back(std::move(candidate));
                added_route = true;
            }
        }

        if (!added_route)
            break;
    }

    std::sort(selected_routes.begin(), selected_routes.end(), [](const CompositeNodeRouteCandidate &lhs, const CompositeNodeRouteCandidate &rhs) {
        if (lhs.key.empty() != rhs.key.empty())
            return !lhs.key.empty();
        if (!lhs.key.empty() && !rhs.key.empty() && lhs.key.front() != rhs.key.front())
            return lhs.key.front() < rhs.key.front();
        if (std::abs(lhs.score_length_mm - rhs.score_length_mm) > EPSILON)
            return lhs.score_length_mm > rhs.score_length_mm;
        return lhs.key < rhs.key;
    });
    return selected_routes;
}

static void orient_polyline_from_current_end(Polyline &polyline, const Point *current_end)
{
    if (current_end == nullptr || polyline.points.size() < 2)
        return;

    const double dist_to_start = point_distance_mm(*current_end, polyline.points.front());
    const double dist_to_end = point_distance_mm(*current_end, polyline.points.back());
    if (dist_to_end < dist_to_start)
        polyline.reverse();
}

static Polylines route_polylines_from_component(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<std::size_t> &component,
    double max_transition_length_mm)
{
    std::vector<std::size_t> remaining = component;
    std::sort(remaining.begin(), remaining.end(), [&candidates](std::size_t lhs, std::size_t rhs) {
        return candidates[lhs].id < candidates[rhs].id;
    });

    Polylines ordered;
    bool has_current_end = false;
    Point current_end;
    while (!remaining.empty()) {
        auto best_it = remaining.begin();
        double best_dist = has_current_end ? std::numeric_limits<double>::infinity() : 0.0;
        if (has_current_end) {
            for (auto it = remaining.begin(); it != remaining.end(); ++it) {
                const CompositeCandidate &candidate = candidates[*it];
                if (!candidate_has_printable_polyline(candidate))
                    continue;
                const double distance = std::min(
                    point_distance_mm(current_end, candidate.polyline.points.front()),
                    point_distance_mm(current_end, candidate.polyline.points.back()));
                if (distance < best_dist) {
                    best_dist = distance;
                    best_it = it;
                }
            }
        }

        const std::size_t chosen = *best_it;
        remaining.erase(best_it);
        if (!candidate_has_printable_polyline(candidates[chosen]))
            continue;
        Polyline next = candidates[chosen].polyline;
        orient_polyline_from_current_end(next, has_current_end ? &current_end : nullptr);
        if (has_current_end && best_dist <= max_transition_length_mm)
            ordered.emplace_back(current_end, next.points.front());
        ordered.push_back(std::move(next));
        current_end = ordered.back().points.back();
        has_current_end = true;
    }

    return ordered;
}

static const CompositeNodeConnection *composite_node_connection_matching_endpoints(
    const std::vector<CompositeNodeConnection> &options,
    std::size_t first_node,
    CandidateEndpoint first_endpoint,
    std::size_t second_node,
    CandidateEndpoint second_endpoint)
{
    for (const CompositeNodeConnection &connection : options) {
        if (connection_endpoint_for_node(connection, first_node) == first_endpoint &&
            connection_endpoint_for_node(connection, second_node) == second_endpoint)
            return &connection;
    }
    return nullptr;
}

static void materialized_candidate_order_for_node(
    const CompositeNode &node,
    CandidateEndpoint node_entry_endpoint,
    std::vector<std::size_t> &candidate_indices,
    std::vector<CandidateEndpoint> &entry_endpoints)
{
    candidate_indices.clear();
    entry_endpoints.clear();
    if (node.candidate_indices.empty() ||
        node.canonical_entry_endpoints.size() != node.candidate_indices.size())
        return;

    if (node_entry_endpoint == CandidateEndpoint::Start) {
        candidate_indices = node.candidate_indices;
        entry_endpoints = node.canonical_entry_endpoints;
        return;
    }

    candidate_indices.reserve(node.candidate_indices.size());
    entry_endpoints.reserve(node.canonical_entry_endpoints.size());
    for (std::size_t i = node.candidate_indices.size(); i > 0; --i) {
        candidate_indices.push_back(node.candidate_indices[i - 1]);
        entry_endpoints.push_back(opposite_endpoint(node.canonical_entry_endpoints[i - 1]));
    }
}

static bool append_internal_node_connection_segment(
    CompositeRouteGeometry &geometry,
    const std::vector<std::size_t> &candidate_indices,
    const std::vector<CandidateEndpoint> &entry_endpoints,
    std::size_t current_position,
    const RowConnectionOptionsMap &row_connection_options,
    const CompositeRouteGraphOptions &options)
{
    if (current_position == 0 ||
        current_position >= candidate_indices.size() ||
        entry_endpoints.size() != candidate_indices.size())
        return true;

    const std::size_t previous_candidate = candidate_indices[current_position - 1];
    const std::size_t current_candidate = candidate_indices[current_position];
    const std::vector<RowConnection> *connections =
        row_connection_options_for_pair(row_connection_options, previous_candidate, current_candidate);
    if (connections == nullptr)
        return false;

    const RowConnection *connection = row_connection_matching_endpoints(
        *connections,
        previous_candidate,
        opposite_endpoint(entry_endpoints[current_position - 1]),
        current_candidate,
        entry_endpoints[current_position]);
    if (connection == nullptr)
        return false;

    const Point previous_connection_point = connection_point_for_candidate(*connection, previous_candidate);
    const Point current_connection_point = connection_point_for_candidate(*connection, current_candidate);
    if (!scaled_points_equal(previous_connection_point, current_connection_point))
        append_route_segment(
            geometry,
            Polyline(previous_connection_point, current_connection_point),
            options,
            CompositeRoutePhase::SlowTurn,
            true,
            true);

    return true;
}

static bool append_composite_node_segments(
    CompositeRouteGeometry &geometry,
    const std::vector<CompositeCandidate> &candidates,
    const CompositeNode &node,
    CandidateEndpoint node_entry_endpoint,
    const RowConnectionOptionsMap &row_connection_options,
    const CompositeRouteGraphOptions &options)
{
    std::vector<std::size_t> candidate_indices;
    std::vector<CandidateEndpoint> entry_endpoints;
    materialized_candidate_order_for_node(node, node_entry_endpoint, candidate_indices, entry_endpoints);
    if (candidate_indices.empty() || entry_endpoints.size() != candidate_indices.size())
        return false;

    for (std::size_t i = 0; i < candidate_indices.size(); ++i) {
        if (!append_internal_node_connection_segment(
                geometry,
                candidate_indices,
                entry_endpoints,
                i,
                row_connection_options,
                options))
            return false;

        const std::size_t candidate_index = candidate_indices[i];
        if (candidate_index >= candidates.size())
            return false;

        append_route_segment(
            geometry,
            oriented_candidate_polyline(candidates[candidate_index], entry_endpoints[i]),
            options,
            CompositeRoutePhase::Normal,
            true,
            true);
        geometry.materialized_candidate_indices.push_back(candidate_index);
    }

    return true;
}

static CompositeRouteGeometry route_geometry_from_composite_node_path(
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<CompositeNode> &nodes,
    const std::vector<std::size_t> &path,
    const std::vector<CandidateEndpoint> &entry_endpoints,
    const CompositeRouteGraphOptions &options,
    const RowConnectionOptionsMap &row_connection_options,
    const CompositeNodeConnectionOptionsMap &node_connection_options)
{
    if (path.empty() || entry_endpoints.size() != path.size())
        return {};

    CompositeRouteGeometry geometry;
    bool has_current_end = false;
    Point current_end;

    for (std::size_t path_index = 0; path_index < path.size(); ++path_index) {
        const std::size_t node_index = path[path_index];
        if (node_index >= nodes.size())
            return {};

        if (path_index > 0) {
            const std::size_t previous_node = path[path_index - 1];
            const std::vector<CompositeNodeConnection> *connections =
                composite_node_connection_options_for_pair(node_connection_options, previous_node, node_index);
            if (connections == nullptr)
                return {};

            const CompositeNodeConnection *connection = composite_node_connection_matching_endpoints(
                *connections,
                previous_node,
                opposite_endpoint(entry_endpoints[path_index - 1]),
                node_index,
                entry_endpoints[path_index]);
            if (connection == nullptr)
                return {};

            const Point previous_connection_point = connection_point_for_node(*connection, previous_node);
            const Point current_connection_point = connection_point_for_node(*connection, node_index);
            if (has_current_end && !scaled_points_equal(current_end, previous_connection_point))
                append_route_segment(
                    geometry,
                    Polyline(current_end, previous_connection_point),
                    options,
                    CompositeRoutePhase::SlowTurn,
                    true,
                    true);
            if (!scaled_points_equal(previous_connection_point, current_connection_point))
                append_route_segment(
                    geometry,
                    Polyline(previous_connection_point, current_connection_point),
                    options,
                    CompositeRoutePhase::SlowTurn,
                    true,
                    true);
            current_end = current_connection_point;
            has_current_end = true;
        }

        if (!append_composite_node_segments(
                geometry,
                candidates,
                nodes[node_index],
                entry_endpoints[path_index],
                row_connection_options,
                options))
            return {};
        if (!geometry.ordered_segments.empty()) {
            current_end = geometry.ordered_segments.back().points.back();
            has_current_end = true;
        }
    }

    populate_boundary_tail_for_row_path(geometry, candidates, geometry.materialized_candidate_indices, options);
    return geometry;
}

static bool route_start_end_points(const CompositeRoute &route, Point &start, Point &end)
{
    const std::vector<CompositeRouteSegment> &segments = route.planned_segments;
    if (!segments.empty()) {
        const CompositeRouteSegment *first = nullptr;
        const CompositeRouteSegment *last = nullptr;
        for (const CompositeRouteSegment &segment : segments) {
            if (segment.polyline.points.size() < 2)
                continue;
            if (first == nullptr)
                first = &segment;
            last = &segment;
        }
        if (first != nullptr && last != nullptr) {
            start = first->polyline.points.front();
            end = last->polyline.points.back();
            return true;
        }
    }

    const RouteExtents extents = route_extents(route.ordered_segments);
    if (!extents.has_points)
        return false;
    start = extents.first;
    end = extents.last;
    return true;
}

static bool route_candidate_endpoint_indices(
    const CompositeRoute &route,
    const std::map<std::size_t, std::size_t> &candidate_indices_by_id,
    std::size_t &start_candidate_index,
    std::size_t &end_candidate_index)
{
    if (route.candidate_ids.empty())
        return false;

    const auto start_it = candidate_indices_by_id.find(route.candidate_ids.front());
    const auto end_it = candidate_indices_by_id.find(route.candidate_ids.back());
    if (start_it == candidate_indices_by_id.end() || end_it == candidate_indices_by_id.end())
        return false;

    start_candidate_index = start_it->second;
    end_candidate_index = end_it->second;
    return true;
}

static void reverse_route_for_stitch(CompositeRoute &route)
{
    std::reverse(route.candidate_ids.begin(), route.candidate_ids.end());

    std::reverse(route.ordered_segments.begin(), route.ordered_segments.end());
    for (Polyline &polyline : route.ordered_segments)
        polyline.reverse();

    std::reverse(route.planned_segments.begin(), route.planned_segments.end());
    for (CompositeRouteSegment &segment : route.planned_segments)
        segment.polyline.reverse();

    route.tail_segments.clear();
    refresh_route_metrics(route);
}

static void append_route_segment_to_route(
    CompositeRoute &route,
    const Polyline &polyline,
    const CompositeRouteGraphOptions &options,
    CompositeRoutePhase phase,
    bool emits_plastic,
    bool emits_fiber)
{
    if (polyline.points.size() < 2 || polyline_length_mm(polyline) <= EPSILON)
        return;
    route.ordered_segments.push_back(polyline);
    route.planned_segments.push_back(make_route_segment(polyline, options, phase, emits_plastic, emits_fiber));
}

static void append_route_for_stitch(
    CompositeRoute &route,
    CompositeRoute next,
    bool reverse_next,
    const Point &connector_start,
    const Point &connector_end,
    const CompositeRouteGraphOptions &options)
{
    route.tail_segments.clear();
    if (reverse_next)
        reverse_route_for_stitch(next);

    if (!scaled_points_equal(connector_start, connector_end))
        append_route_segment_to_route(
            route,
            Polyline(connector_start, connector_end),
            options,
            CompositeRoutePhase::SlowTurn,
            true,
            true);

    route.ordered_segments.insert(
        route.ordered_segments.end(),
        next.ordered_segments.begin(),
        next.ordered_segments.end());
    route.planned_segments.insert(
        route.planned_segments.end(),
        next.planned_segments.begin(),
        next.planned_segments.end());
    route.candidate_ids.insert(
        route.candidate_ids.end(),
        next.candidate_ids.begin(),
        next.candidate_ids.end());
    route.tail_segments = std::move(next.tail_segments);
    route.coalesce_transition_length_mm = std::max(
        route.coalesce_transition_length_mm,
        options.route_stitch_transition_length_mm);
    refresh_route_metrics(route);
}

static void prepend_route_for_stitch(
    CompositeRoute &route,
    CompositeRoute previous,
    bool reverse_previous,
    const Point &connector_start,
    const Point &connector_end,
    const CompositeRouteGraphOptions &options)
{
    if (reverse_previous)
        reverse_route_for_stitch(previous);
    previous.tail_segments.clear();

    if (!scaled_points_equal(connector_start, connector_end))
        append_route_segment_to_route(
            previous,
            Polyline(connector_start, connector_end),
            options,
            CompositeRoutePhase::SlowTurn,
            true,
            true);

    previous.ordered_segments.insert(
        previous.ordered_segments.end(),
        route.ordered_segments.begin(),
        route.ordered_segments.end());
    previous.planned_segments.insert(
        previous.planned_segments.end(),
        route.planned_segments.begin(),
        route.planned_segments.end());
    previous.candidate_ids.insert(
        previous.candidate_ids.end(),
        route.candidate_ids.begin(),
        route.candidate_ids.end());
    previous.tail_segments = std::move(route.tail_segments);
    previous.coalesce_transition_length_mm = std::max({
        previous.coalesce_transition_length_mm,
        route.coalesce_transition_length_mm,
        options.route_stitch_transition_length_mm});
    refresh_route_metrics(previous);
    route = std::move(previous);
}

struct RouteStitchChoice {
    bool found { false };
    bool prepend { false };
    bool reverse_other { false };
    std::size_t route_index { 0 };
    Point connector_start;
    Point connector_end;
    double distance_mm { std::numeric_limits<double>::infinity() };
};

static void consider_route_stitch_choice(
    RouteStitchChoice &best,
    bool prepend,
    bool reverse_other,
    std::size_t route_index,
    const Point &connector_start,
    const Point &connector_end,
    std::size_t source_candidate_index,
    std::size_t target_candidate_index,
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    const std::vector<PrintableRegionBounds> &printable_region_bounds,
    const CandidateIntersectionIndex *candidate_intersection_index,
    double budget_mm)
{
    const double distance_mm = point_distance_mm(connector_start, connector_end);
    if (distance_mm > budget_mm + EPSILON || distance_mm + EPSILON >= best.distance_mm)
        return;
    if (source_candidate_index >= candidates.size() || target_candidate_index >= candidates.size())
        return;
    if (!candidates_share_physical_route_scope(candidates[source_candidate_index], candidates[target_candidate_index]))
        return;
    if (!connector_is_candidate_legal(
            connector_start,
            connector_end,
            candidates,
            candidate_bounds,
            candidate_region_indices,
            printable_region_bounds,
            candidate_intersection_index,
            source_candidate_index,
            target_candidate_index))
        return;

    best.found = true;
    best.prepend = prepend;
    best.reverse_other = reverse_other;
    best.route_index = route_index;
    best.connector_start = connector_start;
    best.connector_end = connector_end;
    best.distance_mm = distance_mm;
}

static RouteStitchChoice best_route_stitch_choice(
    const CompositeRoute &route,
    const std::vector<CompositeRoute> &routes,
    const std::vector<unsigned char> &used,
    const std::map<std::size_t, std::size_t> &candidate_indices_by_id,
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    const std::vector<PrintableRegionBounds> &printable_region_bounds,
    const CandidateIntersectionIndex *candidate_intersection_index,
    double budget_mm)
{
    RouteStitchChoice best;
    Point route_start;
    Point route_end;
    std::size_t route_start_candidate = 0;
    std::size_t route_end_candidate = 0;
    if (!route_start_end_points(route, route_start, route_end) ||
        !route_candidate_endpoint_indices(route, candidate_indices_by_id, route_start_candidate, route_end_candidate))
        return best;

    for (std::size_t other_index = 0; other_index < routes.size(); ++other_index) {
        if (other_index >= used.size() || used[other_index] != 0)
            continue;

        const CompositeRoute &other = routes[other_index];
        Point other_start;
        Point other_end;
        std::size_t other_start_candidate = 0;
        std::size_t other_end_candidate = 0;
        if (!route_start_end_points(other, other_start, other_end) ||
            !route_candidate_endpoint_indices(other, candidate_indices_by_id, other_start_candidate, other_end_candidate))
            continue;

        consider_route_stitch_choice(
            best, false, false, other_index,
            route_end, other_start,
            route_end_candidate, other_start_candidate,
            candidates, candidate_bounds, candidate_region_indices, printable_region_bounds, candidate_intersection_index, budget_mm);
        consider_route_stitch_choice(
            best, false, true, other_index,
            route_end, other_end,
            route_end_candidate, other_end_candidate,
            candidates, candidate_bounds, candidate_region_indices, printable_region_bounds, candidate_intersection_index, budget_mm);
        consider_route_stitch_choice(
            best, true, false, other_index,
            other_end, route_start,
            other_end_candidate, route_start_candidate,
            candidates, candidate_bounds, candidate_region_indices, printable_region_bounds, candidate_intersection_index, budget_mm);
        consider_route_stitch_choice(
            best, true, true, other_index,
            other_start, route_start,
            other_start_candidate, route_start_candidate,
            candidates, candidate_bounds, candidate_region_indices, printable_region_bounds, candidate_intersection_index, budget_mm);
    }

    return best;
}

static void stitch_row_graph_routes(
    std::vector<CompositeRoute> &routes,
    const std::vector<CompositeCandidate> &candidates,
    const std::vector<BoundingBox> &candidate_bounds,
    const std::vector<std::size_t> &candidate_region_indices,
    const std::vector<PrintableRegionBounds> &printable_region_bounds,
    const CompositeRouteGraphOptions &options)
{
    const double budget_mm = options.route_stitch_transition_length_mm;
    if (budget_mm <= EPSILON || routes.size() < 2)
        return;

    const CandidateIntersectionIndex candidate_intersection_index =
        build_candidate_intersection_index(
            candidate_bounds,
            candidate_region_indices,
            std::max(budget_mm, options.line_spacing_mm * 4.0));

    std::map<std::size_t, std::size_t> candidate_indices_by_id;
    for (std::size_t index = 0; index < candidates.size(); ++index)
        candidate_indices_by_id[candidates[index].id] = index;

    std::vector<std::size_t> route_order(routes.size());
    std::iota(route_order.begin(), route_order.end(), 0);
    std::sort(route_order.begin(), route_order.end(), [&routes](std::size_t lhs, std::size_t rhs) {
        if (std::abs(routes[lhs].length_mm - routes[rhs].length_mm) > EPSILON)
            return routes[lhs].length_mm > routes[rhs].length_mm;
        return routes[lhs].id < routes[rhs].id;
    });

    std::vector<unsigned char> used(routes.size(), 0);
    std::vector<CompositeRoute> stitched_routes;
    stitched_routes.reserve(routes.size());

    for (std::size_t seed_index : route_order) {
        if (seed_index >= routes.size() || used[seed_index] != 0)
            continue;

        CompositeRoute route = routes[seed_index];
        used[seed_index] = 1;

        for (;;) {
            const RouteStitchChoice choice = best_route_stitch_choice(
                route,
                routes,
                used,
                candidate_indices_by_id,
                candidates,
                candidate_bounds,
                candidate_region_indices,
                printable_region_bounds,
                &candidate_intersection_index,
                budget_mm);
            if (!choice.found)
                break;

            CompositeRoute other = routes[choice.route_index];
            used[choice.route_index] = 1;
            if (choice.prepend)
                prepend_route_for_stitch(
                    route,
                    std::move(other),
                    choice.reverse_other,
                    choice.connector_start,
                    choice.connector_end,
                    options);
            else
                append_route_for_stitch(
                    route,
                    std::move(other),
                    choice.reverse_other,
                    choice.connector_start,
                    choice.connector_end,
                    options);
        }

        stitched_routes.push_back(std::move(route));
    }

    for (std::size_t route_index = 0; route_index < stitched_routes.size(); ++route_index)
        stitched_routes[route_index].id = route_index;
    routes = std::move(stitched_routes);
}

static CompositeFallback make_fallback(
    std::size_t id,
    std::size_t layer_id,
    const CompositeCandidate &candidate,
    const CompositeRouteGraphOptions &options,
    FallbackReason reason)
{
    CompositeFallback fallback;
    fallback.id = id;
    fallback.layer_id = layer_id;
    fallback.candidate_ids.push_back(candidate.id);
    if (candidate_has_printable_polyline(candidate)) {
        if (fallback_needs_paired_plastic_substitution(candidate, reason))
            fallback.replacement_segments = plastic_substitution_segments_for_candidate(candidate, options);
        if (fallback.replacement_segments.empty())
            fallback.replacement_segments.push_back(candidate.polyline);
    }
    fallback.extrusion_role = candidate.fallback_role;
    fallback.reason = reason;
    return fallback;
}

static std::size_t next_fallback_id_for_layer(const CompositeLayerDiagnostic &diagnostic)
{
    std::size_t next_id = 0;
    for (const CompositeFallback &fallback : diagnostic.fallbacks)
        next_id = std::max(next_id, fallback.id + 1);
    return next_id;
}

static SurfaceType surface_type_for_fallback_role(ExtrusionRole role)
{
    return role == erSolidInfill ? stInternalSolid : stInternal;
}

static Polylines plastic_line_fill_for_residual_region(
    const ExPolygon &region,
    ExtrusionRole role,
    const CompositeSurfaceFillOptions &options,
    double spacing_mm)
{
    if (region.empty() || spacing_mm <= EPSILON)
        return {};

    std::unique_ptr<Fill> filler(Fill::new_from_type(ipRectilinear));
    if (!filler)
        return {};

    Surface surface(surface_type_for_fallback_role(role), region);
    filler->layer_id = options.layer_id;
    filler->z = options.z_mm;
    filler->spacing = spacing_mm;
    filler->overlap = 0.0;
    filler->angle = float(options.angle_rad);
    filler->fixed_angle = options.fixed_angle;
    filler->link_max_length = 0;
    filler->loop_clipping = 0;
    if (options.bounding_box.defined)
        filler->set_bounding_box(options.bounding_box);

    FillParams fill_params;
    fill_params.density = 1.0f;
    fill_params.resolution = options.resolution_mm;
    fill_params.dont_adjust = true;
    fill_params.anchor_length = 0.0f;
    fill_params.anchor_length_max = 0.0f;
    fill_params.pattern = ipRectilinear;
    fill_params.dont_sort = true;
    fill_params.can_reverse = true;

    try {
        return filler->fill_surface(&surface, fill_params);
    } catch (InfillFailedException &) {
        return {};
    }
}

static void append_residual_plastic_refill_fallbacks(
    CompositeLayerDiagnostic &diagnostic,
    const CompositeSurfaceFillOptions &options)
{
    if (!options.residual_plastic_refill_enabled)
        return;

    using ResidualScopeKey = std::tuple<std::size_t, std::size_t, std::size_t, std::size_t, CandidateFamily>;
    std::map<std::size_t, ResidualScopeKey> candidate_scope_by_id;
    std::map<ResidualScopeKey, ResidualPlasticRegion> regions;

    for (const CompositeCandidate &candidate : diagnostic.candidates) {
        if (candidate.family == CandidateFamily::Perimeter)
            continue;
        const ExPolygon *printable_region = candidate_printable_region(candidate);
        if (printable_region == nullptr || printable_region->empty())
            continue;

        const ResidualScopeKey key {
            candidate.layer_id,
            candidate.object_id,
            candidate.island_id,
            candidate.region_id,
            candidate.family,
        };
        candidate_scope_by_id.emplace(candidate.id, key);

        ResidualPlasticRegion &region = regions[key];
        if (region.printable_region == nullptr)
            region.printable_region = printable_region;
        region.extrusion_role = candidate.fallback_role;
        region.plastic_line_width_mm = candidate.fallback_line_width_mm > EPSILON ?
            candidate.fallback_line_width_mm :
            fallback_line_width_for_surface(Surface(surface_type_for_fallback_role(candidate.fallback_role)), options);
        region.candidate_ids.insert(candidate.id);
    }

    if (regions.empty())
        return;

    for (const CompositeRoute &route : diagnostic.routes) {
        ResidualPlasticRegion *region = nullptr;
        for (std::size_t candidate_id : route.candidate_ids) {
            auto scope_it = candidate_scope_by_id.find(candidate_id);
            if (scope_it == candidate_scope_by_id.end())
                continue;
            auto region_it = regions.find(scope_it->second);
            if (region_it != regions.end()) {
                region = &region_it->second;
                break;
            }
        }
        if (region == nullptr)
            continue;

        region->has_accepted_route = true;
        if (!route.planned_segments.empty()) {
            for (const CompositeRouteSegment &segment : route.planned_segments)
                if ((segment.emits_plastic && segment.plastic_mm_per_mm > 0.0) ||
                    (segment.emits_fiber && segment.fiber_mm_per_mm > 0.0))
                    append_printable_polyline(region->covered_segments, segment.polyline);
        } else {
            for (const Polyline &polyline : route.ordered_segments)
                append_printable_polyline(region->covered_segments, polyline);
        }
    }

    for (const CompositeFallback &fallback : diagnostic.fallbacks) {
        ResidualPlasticRegion *region = nullptr;
        for (std::size_t candidate_id : fallback.candidate_ids) {
            auto scope_it = candidate_scope_by_id.find(candidate_id);
            if (scope_it == candidate_scope_by_id.end())
                continue;
            auto region_it = regions.find(scope_it->second);
            if (region_it != regions.end()) {
                region = &region_it->second;
                break;
            }
        }
        if (region == nullptr)
            continue;

        for (const Polyline &polyline : fallback.replacement_segments)
            append_printable_polyline(region->covered_segments, polyline);
    }

    std::size_t next_fallback_id = next_fallback_id_for_layer(diagnostic);
    const double fiber_line_width_mm = options.fiber_line_width_mm > EPSILON ?
        options.fiber_line_width_mm :
        std::max(options.spacing_mm, 0.01);
    const double coverage_half_width_mm = 0.5 * fiber_line_width_mm + 0.05;

    for (const auto &entry : regions) {
        const ResidualPlasticRegion &region = entry.second;
        if (!region.has_accepted_route || region.printable_region == nullptr || region.covered_segments.empty())
            continue;

        const Polygons covered = offset(
            region.covered_segments,
            float(scale_(coverage_half_width_mm)),
            ClipperLib::jtRound,
            DefaultLineMiterLimit,
            ClipperLib::etOpenButt);
        if (covered.empty())
            continue;

        ExPolygons residual_regions = diff_ex(*region.printable_region, covered, ApplySafetyOffset::Yes);
        if (residual_regions.empty())
            continue;

        Polylines replacement_segments;
        const double plastic_spacing_mm = region.plastic_line_width_mm > EPSILON ?
            region.plastic_line_width_mm :
            std::max(options.spacing_mm, 0.01);
        for (const ExPolygon &residual_region : residual_regions) {
            Polylines fill = plastic_line_fill_for_residual_region(
                residual_region,
                region.extrusion_role,
                options,
                plastic_spacing_mm);
            for (Polyline &polyline : fill)
                append_printable_polyline(replacement_segments, std::move(polyline));
        }

        if (replacement_segments.empty())
            continue;

        CompositeFallback fallback;
        fallback.id = next_fallback_id++;
        fallback.layer_id = diagnostic.layer_id;
        fallback.candidate_ids.assign(region.candidate_ids.begin(), region.candidate_ids.end());
        fallback.replacement_segments = std::move(replacement_segments);
        fallback.extrusion_role = region.extrusion_role;
        fallback.reason = FallbackReason::ResidualPlasticRefill;
        diagnostic.fallbacks.push_back(std::move(fallback));
    }
}

static CompositeRouteGraphResult select_composite_routes_row_graph(
    const std::vector<CompositeCandidate> &candidates,
    const CompositeRouteGraphOptions &options)
{
    CompositeRouteGraphResult result;
    result.direct_candidate_count = candidates.size();

    std::vector<BoundingBox> candidate_bounds;
    candidate_bounds.reserve(candidates.size());
    for (const CompositeCandidate &candidate : candidates) {
        candidate_bounds.push_back(candidate_has_printable_polyline(candidate) ?
            polyline_bounding_box(candidate.polyline) :
            BoundingBox());
    }

    constexpr std::size_t no_region_index = std::numeric_limits<std::size_t>::max();
    std::vector<std::size_t> candidate_region_indices(candidates.size(), no_region_index);
    std::vector<PrintableRegionBounds> printable_region_bounds;
    std::map<std::tuple<std::size_t, std::size_t, std::size_t, std::size_t, CandidateFamily>, std::size_t> region_indices_by_scope;
    for (std::size_t index = 0; index < candidates.size(); ++index) {
        const CompositeCandidate &candidate = candidates[index];
        if (!candidate.has_printable_region)
            continue;

        const auto key = std::make_tuple(
            candidate.layer_id,
            candidate.object_id,
            candidate.island_id,
            candidate.region_id,
            candidate.family);
        auto it = region_indices_by_scope.find(key);
        if (it == region_indices_by_scope.end()) {
            const std::size_t bounds_index = printable_region_bounds.size();
            const ExPolygon &printable_region = candidate.printable_region_ref ?
                *candidate.printable_region_ref :
                candidate.printable_region;
            printable_region_bounds.push_back(make_printable_region_bounds(printable_region));
            it = region_indices_by_scope.emplace(key, bounds_index).first;
        }
        candidate_region_indices[index] = it->second;
    }

    std::vector<RowCandidateView> row_candidates;
    row_candidates.reserve(candidates.size());

    std::size_t next_fallback_id = 0;
    for (std::size_t index = 0; index < candidates.size(); ++index) {
        const CompositeCandidate &candidate = candidates[index];
        if (!candidate_has_printable_polyline(candidate))
            continue;
        if (!candidate.legal_containment) {
            result.fallbacks.push_back(make_fallback(
                next_fallback_id++, options.layer_id, candidate, options, FallbackReason::UnsupportedVoidCrossing));
            continue;
        }
        if (candidate_length_mm(candidate) + EPSILON < options.min_segment_length_mm)
            ++result.short_candidate_count;
        row_candidates.push_back(make_row_candidate_view(candidate, index));
    }

    std::map<long long, std::vector<RowCandidateView>> rows_by_angle;
    for (const RowCandidateView &candidate : row_candidates)
        rows_by_angle[candidate.angle_key].push_back(candidate);

    std::vector<std::vector<std::size_t>> adjacency(candidates.size());
    RowConnectionMap connections;
    RowConnectionOptionsMap connection_options;
    const double level_tolerance_mm = std::max(options.line_spacing_mm * 0.05, 0.01);
    const double row_connection_budget_mm = std::max(
        options.max_transition_length_mm,
        options.coalesce_transition_length_mm);
    const CandidateIntersectionIndex candidate_intersection_index =
        build_candidate_intersection_index(
            candidate_bounds,
            candidate_region_indices,
            std::max(row_connection_budget_mm, options.line_spacing_mm * 4.0));

    for (auto &angle_group : rows_by_angle) {
        const std::vector<std::vector<RowCandidateView>> levels = row_levels_for_angle(angle_group.second, level_tolerance_mm);
        for (std::size_t level_index = 1; level_index < levels.size(); ++level_index) {
            const std::vector<RowCandidateView> &previous = levels[level_index - 1];
            const std::vector<RowCandidateView> &current = levels[level_index];
            for (const RowCandidateView &first : previous) {
                for (const RowCandidateView &second : current) {
                    if (remaining_row_candidates_too_far(first, second, row_connection_budget_mm))
                        break;
                    if (!candidates_share_route_scope(candidates[first.candidate_index], candidates[second.candidate_index]))
                        continue;
                    if (!row_candidate_spans_close(first, second, row_connection_budget_mm))
                        continue;
                    std::vector<RowConnection> options_for_pair = row_connection_options(
                            candidates,
                            candidate_bounds,
                            candidate_region_indices,
                            printable_region_bounds,
                            &candidate_intersection_index,
                            first,
                            second,
                            row_connection_budget_mm);
                    if (options_for_pair.empty())
                        continue;

                    const RowConnectionKey key = row_connection_key(first.candidate_index, second.candidate_index);
                    const RowConnection &best_connection = options_for_pair.front();
                    auto existing = connections.find(key);
                    if (existing != connections.end() && existing->second.length_mm <= best_connection.length_mm + EPSILON)
                        continue;

                    if (existing == connections.end()) {
                        adjacency[first.candidate_index].push_back(second.candidate_index);
                        adjacency[second.candidate_index].push_back(first.candidate_index);
                    }
                    connections[key] = best_connection;
                    connection_options[key] = std::move(options_for_pair);
                }
            }
        }
    }

    std::vector<std::size_t> candidate_to_node;
    const std::vector<CompositeNode> nodes = build_composite_nodes_from_row_graph(
        candidates,
        row_candidates,
        adjacency,
        connection_options,
        candidate_to_node);
    std::vector<std::vector<std::size_t>> node_adjacency;
    CompositeNodeConnectionMap node_connections;
    CompositeNodeConnectionOptionsMap node_connection_options;
    build_composite_node_graph(
        nodes,
        candidate_to_node,
        connection_options,
        node_adjacency,
        node_connections,
        node_connection_options);

    const double threshold_mm = std::max(options.min_route_length_mm, options.min_segment_length_mm);
    std::vector<bool> visited(nodes.size(), false);
    std::size_t next_route_id = 0;

    for (std::size_t seed_node = 0; seed_node < nodes.size(); ++seed_node) {
        if (visited[seed_node])
            continue;

        std::vector<std::size_t> component;
        std::vector<std::size_t> queue { seed_node };
        visited[seed_node] = true;

        for (std::size_t pos = 0; pos < queue.size(); ++pos) {
            const std::size_t current = queue[pos];
            component.push_back(current);

            for (std::size_t other : node_adjacency[current]) {
                if (!visited[other]) {
                    visited[other] = true;
                    queue.push_back(other);
                }
            }
        }

        ++result.graph_component_count;
        const std::vector<CompositeNodeRouteCandidate> selected_routes =
            select_composite_node_route_group_with_completion(
                nodes,
                component,
                node_adjacency,
                node_connections,
                node_connection_options,
                options,
                threshold_mm);
        std::set<std::size_t> selected_candidate_indexes;

        for (const CompositeNodeRouteCandidate &selected : selected_routes) {
            CompositeRouteGeometry geometry = route_geometry_from_composite_node_path(
                candidates,
                nodes,
                selected.path,
                selected.entry_endpoints,
                options,
                connection_options,
                node_connection_options);
            if (geometry.ordered_segments.empty())
                continue;

            CompositeRoute route;
            route.id = next_route_id++;
            route.layer_id = options.layer_id;
            route.ordered_segments = std::move(geometry.ordered_segments);
            route.tail_segments = std::move(geometry.tail_segments);
            route.planned_segments = std::move(geometry.planned_segments);
            route.cut_distance_mm = options.cut_distance_mm;
            route.coalesce_transition_length_mm = row_connection_budget_mm;
            route.cut_safe_threshold_mm = threshold_mm;
            route.plastic_mm_per_mm = options.plastic_mm_per_mm;
            route.fiber_mm_per_mm = options.fiber_mm_per_mm;
            for (std::size_t candidate_index : geometry.materialized_candidate_indices) {
                route.candidate_ids.push_back(candidates[candidate_index].id);
                selected_candidate_indexes.insert(candidate_index);
            }
            refresh_route_metrics(route);
            result.routes.push_back(std::move(route));
        }

        const FallbackReason fallback_reason = selected_candidate_indexes.empty() ?
            FallbackReason::ShorterThanCutSafeThreshold :
            FallbackReason::ReplacedByBetterCombination;
        for (std::size_t node_index : component) {
            if (node_index >= nodes.size())
                continue;
            for (std::size_t candidate_index : nodes[node_index].candidate_indices) {
                if (selected_candidate_indexes.count(candidate_index) != 0)
                    continue;
            result.fallbacks.push_back(make_fallback(
                    next_fallback_id++, options.layer_id, candidates[candidate_index], options, fallback_reason));
            }
        }
    }

    stitch_row_graph_routes(
        result.routes,
        candidates,
        candidate_bounds,
        candidate_region_indices,
        printable_region_bounds,
        options);

    return result;
}

} // namespace

bool CompositeRoute::is_cut_safe() const
{
    return route_length_is_cut_safe(this->length_mm, this->cut_safe_threshold_mm);
}

bool CompositeRoute::is_geometrically_safe() const
{
    return this->unsupported_void_crossing_count == 0;
}

bool CompositeRoute::is_release_safe() const
{
    return this->is_cut_safe() && this->is_geometrically_safe();
}

double CompositeRoute::printable_length_mm() const
{
    if (!this->planned_segments.empty()) {
        double total = 0.0;
        for (const CompositeRouteSegment &segment : this->planned_segments)
            total += segment.length_mm;
        return total;
    }

    return this->length_mm + this->tail_length_mm;
}

bool CompositeRoute::is_closed_loop(double tolerance_mm) const
{
    return this->shape == CompositeRouteShape::ClosedLoop || this->closure_gap_mm <= tolerance_mm;
}

bool CompositeLayerDiagnostic::empty() const
{
    return this->candidates.empty() && this->routes.empty() && this->fallbacks.empty();
}

std::size_t CompositePlanDiagnostic::route_count() const
{
    std::size_t count = 0;
    for (const CompositeLayerDiagnostic &layer : this->layers)
        count += layer.routes.size();
    return count;
}

std::size_t CompositePlanDiagnostic::fallback_count() const
{
    std::size_t count = 0;
    for (const CompositeLayerDiagnostic &layer : this->layers)
        count += layer.fallbacks.size();
    return count;
}

std::size_t CompositePlanDiagnostic::routes_with_unsupported_void_crossings() const
{
    std::size_t count = 0;
    for (const CompositeLayerDiagnostic &layer : this->layers)
        count += std::count_if(layer.routes.begin(), layer.routes.end(), [](const CompositeRoute &route) {
            return route.unsupported_void_crossing_count != 0;
        });
    return count;
}

bool CompositePlanDiagnostic::is_release_safe() const
{
    for (const CompositeLayerDiagnostic &layer : this->layers)
        for (const CompositeRoute &route : layer.routes)
            if (!route.is_release_safe())
                return false;
    return true;
}

CompositeSurfaceFillOptions::CompositeSurfaceFillOptions() :
    pattern(ipRectilinear)
{
}

double polyline_length_mm(const Polyline &polyline)
{
    return polyline.length() * SCALING_FACTOR;
}

double polylines_length_mm(const Polylines &polylines)
{
    double total = 0.0;
    for (const Polyline &polyline : polylines)
        total += polyline_length_mm(polyline);
    return total;
}

std::vector<CompositeCandidate> make_candidates_from_polylines(
    const Polylines &polylines,
    CandidateFamily family,
    std::size_t layer_id,
    std::size_t object_id,
    std::size_t island_id,
    std::size_t region_id,
    std::size_t first_candidate_id)
{
    std::vector<CompositeCandidate> candidates;
    candidates.reserve(polylines.size());
    std::size_t next_id = first_candidate_id;
    for (const Polyline &polyline : polylines) {
        if (polyline.points.size() < 2)
            continue;
        CompositeCandidate candidate;
        candidate.id = next_id++;
        candidate.layer_id = layer_id;
        candidate.object_id = object_id;
        candidate.island_id = island_id;
        candidate.region_id = region_id;
        candidate.family = family;
        candidate.polyline = polyline;
        candidate.length_mm = polyline_length_mm(polyline);
        candidates.push_back(std::move(candidate));
    }
    return candidates;
}

std::vector<CompositeCandidate> make_candidates_from_surface_fill(
    const Surface &surface,
    const CompositeSurfaceFillOptions &options)
{
    if (surface.empty() || options.density <= 0.0 || options.spacing_mm <= 0.0)
        return {};

    if (options.family == CandidateFamily::SolidInfill) {
        std::vector<CompositeCandidate> candidates = make_rocket_solid_line_candidates_from_surface(surface, options);
        if (!candidates.empty())
            return candidates;
    }

    std::unique_ptr<Fill> filler(Fill::new_from_type(options.pattern));
    if (!filler)
        return {};

    filler->layer_id = options.layer_id;
    filler->z = options.z_mm;
    filler->spacing = options.spacing_mm;
    filler->overlap = options.overlap_mm;
    filler->angle = float(options.angle_rad);
    filler->fixed_angle = options.fixed_angle;
    filler->link_max_length = 0;
    filler->loop_clipping = 0;
    if (options.bounding_box.defined)
        filler->set_bounding_box(options.bounding_box);

    FillParams fill_params;
    fill_params.density = float(options.density);
    fill_params.resolution = options.resolution_mm;
    fill_params.dont_adjust = !options.adjust_spacing;
    fill_params.anchor_length = options.connect_to_perimeters ? 1000.0f : 0.0f;
    fill_params.anchor_length_max = options.connect_to_perimeters ? 1000.0f : 0.0f;
    fill_params.pattern = options.pattern;
    fill_params.dont_sort = true;
    fill_params.can_reverse = true;

    Polylines polylines;
    try {
        polylines = filler->fill_surface(&surface, fill_params);
    } catch (InfillFailedException &) {
        return {};
    }

    std::vector<CompositeCandidate> candidates = make_candidates_from_polylines(
        polylines,
        options.family,
        options.layer_id,
        options.object_id,
        options.island_id,
        options.region_id,
        options.first_candidate_id);
    const std::shared_ptr<const ExPolygon> printable_region_ref =
        std::make_shared<ExPolygon>(surface.expolygon);
    for (CompositeCandidate &candidate : candidates) {
        candidate.has_printable_region = true;
        candidate.printable_region_ref = printable_region_ref;
        candidate.fallback_role = fallback_role_for_surface(surface);
        candidate.fallback_line_width_mm = fallback_line_width_for_surface(surface, options);
    }
    return candidates;
}

std::vector<CompositeCandidate> make_candidates_from_surface_fills(
    const std::vector<const Surface *> &surfaces,
    CompositeSurfaceFillOptions options)
{
    std::vector<CompositeCandidate> candidates;
    std::size_t next_candidate_id = options.first_candidate_id;

    if (options.family == CandidateFamily::SolidInfill) {
        std::map<SurfaceType, ExPolygons> regions_by_type;
        std::map<SurfaceType, const Surface *> templates_by_type;
        for (const Surface *surface : surfaces) {
            if (surface == nullptr || surface->empty())
                continue;
            regions_by_type[surface->surface_type].push_back(surface->expolygon);
            templates_by_type.emplace(surface->surface_type, surface);
        }

        for (auto &typed_regions : regions_by_type) {
            const Surface *template_surface = templates_by_type[typed_regions.first];
            if (template_surface == nullptr)
                continue;

            ExPolygons unioned_regions = union_ex(typed_regions.second);
            if (unioned_regions.empty())
                unioned_regions = std::move(typed_regions.second);

            for (ExPolygon &region : unioned_regions) {
                Surface unioned_surface(*template_surface, std::move(region));
                options.first_candidate_id = next_candidate_id;
                std::vector<CompositeCandidate> region_candidates =
                    make_candidates_from_surface_fill(unioned_surface, options);
                next_candidate_id += region_candidates.size();
                ++options.island_id;
                candidates.reserve(candidates.size() + region_candidates.size());
                std::move(region_candidates.begin(), region_candidates.end(), std::back_inserter(candidates));
            }
        }

        return candidates;
    }

    for (const Surface *surface : surfaces) {
        if (surface == nullptr)
            continue;

        options.first_candidate_id = next_candidate_id;
        std::vector<CompositeCandidate> surface_candidates = make_candidates_from_surface_fill(*surface, options);
        next_candidate_id += surface_candidates.size();
        ++options.island_id;
        candidates.reserve(candidates.size() + surface_candidates.size());
        std::move(surface_candidates.begin(), surface_candidates.end(), std::back_inserter(candidates));
    }

    return candidates;
}

double rocket_style_transition_limit_mm(double fiber_line_width_mm)
{
    return std::max(0.0, fiber_line_width_mm * 6.0);
}

double cut_safe_threshold_mm(double cut_distance_mm, double safety_margin_mm)
{
    return std::max(0.0, cut_distance_mm + safety_margin_mm);
}

bool route_length_is_cut_safe(double route_length_mm, double threshold_mm)
{
    return route_length_mm + EPSILON >= threshold_mm;
}

CompositeRouteMetrics measure_route(
    const Polylines &ordered_segments,
    const Polylines &tail_segments,
    double plastic_mm_per_mm,
    double fiber_mm_per_mm,
    double short_route_threshold_mm)
{
    CompositeRouteMetrics metrics;
    metrics.length_mm = polylines_length_mm(ordered_segments);
    metrics.tail_length_mm = polylines_length_mm(tail_segments);

    const RouteExtents extents = route_extents(ordered_segments);
    if (extents.has_points) {
        metrics.closure_gap_mm = extents.first.distance_to(extents.last) * SCALING_FACTOR;
        metrics.bbox_span_x_mm = double(extents.max_x - extents.min_x) * SCALING_FACTOR;
        metrics.bbox_span_y_mm = double(extents.max_y - extents.min_y) * SCALING_FACTOR;
    }

    if (fiber_mm_per_mm > 0.0)
        metrics.fiber_positive_length_mm = metrics.length_mm;
    if (plastic_mm_per_mm > 0.0)
        metrics.matrix_positive_length_mm = metrics.length_mm + metrics.tail_length_mm;
    metrics.shape = classify_route_shape(
        metrics.length_mm,
        metrics.closure_gap_mm,
        metrics.bbox_span_x_mm,
        metrics.bbox_span_y_mm,
        short_route_threshold_mm);
    return metrics;
}

void refresh_route_metrics(CompositeRoute &route)
{
    const double short_route_threshold_mm = route.cut_safe_threshold_mm > 0.0 ? route.cut_safe_threshold_mm : 55.0;
    const CompositeRouteMetrics metrics = measure_route(
        route.ordered_segments,
        route.tail_segments,
        route.plastic_mm_per_mm,
        route.fiber_mm_per_mm,
        short_route_threshold_mm);

    route.length_mm = metrics.length_mm;
    route.tail_length_mm = metrics.tail_length_mm;
    route.fiber_positive_length_mm = metrics.fiber_positive_length_mm;
    route.matrix_positive_length_mm = metrics.matrix_positive_length_mm;
    route.travel_length_mm = metrics.travel_length_mm;
    route.closure_gap_mm = metrics.closure_gap_mm;
    route.bbox_span_x_mm = metrics.bbox_span_x_mm;
    route.bbox_span_y_mm = metrics.bbox_span_y_mm;
    route.shape = metrics.shape;

    if (!route.planned_segments.empty()) {
        route.fiber_positive_length_mm = 0.0;
        route.matrix_positive_length_mm = 0.0;
        route.travel_length_mm = 0.0;
        for (const CompositeRouteSegment &segment : route.planned_segments) {
            if (segment.emits_fiber && segment.fiber_mm_per_mm > 0.0)
                route.fiber_positive_length_mm += segment.length_mm;
            if (segment.emits_plastic && segment.plastic_mm_per_mm > 0.0)
                route.matrix_positive_length_mm += segment.length_mm;
            if (!segment.emits_fiber && !segment.emits_plastic)
                route.travel_length_mm += segment.length_mm;
        }
    }
}

CompositeRouteShape classify_route_shape(
    double length_mm,
    double closure_gap_mm,
    double bbox_span_x_mm,
    double bbox_span_y_mm,
    double short_route_threshold_mm)
{
    if (length_mm <= 0.1)
        return CompositeRouteShape::NoXYMotion;
    if (closure_gap_mm <= 1.0)
        return CompositeRouteShape::ClosedLoop;
    if (closure_gap_mm <= 3.0)
        return CompositeRouteShape::NearClosedLoop;
    if (length_mm < short_route_threshold_mm)
        return CompositeRouteShape::ShortOpenPath;
    if (std::min(bbox_span_x_mm, bbox_span_y_mm) <= 1.0)
        return CompositeRouteShape::LineOrTail;
    return CompositeRouteShape::OpenPath;
}

CompositeRouteGraphResult select_composite_routes_from_candidates(
    const std::vector<CompositeCandidate> &input_candidates,
    const CompositeRouteGraphOptions &options)
{
    std::vector<CompositeCandidate> candidates = input_candidates;
    prolong_short_candidates_against_printable_regions(candidates, options);

    if (options.strategy == CompositeRouteGraphStrategy::RocketRowGraph)
        return select_composite_routes_row_graph(candidates, options);

    CompositeRouteGraphResult result;
    result.direct_candidate_count = candidates.size();

    std::vector<std::size_t> graph_candidates;
    graph_candidates.reserve(candidates.size());

    std::size_t next_fallback_id = 0;
    for (std::size_t i = 0; i < candidates.size(); ++i) {
        const CompositeCandidate &candidate = candidates[i];
        if (!candidate_has_printable_polyline(candidate))
            continue;
        if (!candidate.legal_containment) {
            result.fallbacks.push_back(make_fallback(
                next_fallback_id++, options.layer_id, candidate, options, FallbackReason::UnsupportedVoidCrossing));
            continue;
        }
        if (candidate_length_mm(candidate) + EPSILON < options.min_segment_length_mm) {
            ++result.short_candidate_count;
            result.fallbacks.push_back(make_fallback(
                next_fallback_id++, options.layer_id, candidate, options, FallbackReason::ShorterThanCutSafeThreshold));
            continue;
        }
        graph_candidates.push_back(i);
    }

    std::vector<bool> visited(candidates.size(), false);
    const double threshold_mm = std::max(options.min_route_length_mm, options.min_segment_length_mm);
    std::size_t next_route_id = 0;

    for (std::size_t seed : graph_candidates) {
        if (visited[seed])
            continue;

        std::vector<std::size_t> component;
        std::vector<std::size_t> queue { seed };
        visited[seed] = true;

        for (std::size_t pos = 0; pos < queue.size(); ++pos) {
            const std::size_t current = queue[pos];
            component.push_back(current);
            for (std::size_t other : graph_candidates) {
                if (visited[other])
                    continue;
                if (!candidates_share_route_scope(candidates[current], candidates[other]))
                    continue;
                if (nearest_endpoint_distance_mm(candidates[current], candidates[other]) <= options.max_transition_length_mm + EPSILON) {
                    visited[other] = true;
                    queue.push_back(other);
                }
            }
        }

        ++result.graph_component_count;
        Polylines ordered = route_polylines_from_component(candidates, component, options.max_transition_length_mm);
        const double component_length_mm = polylines_length_mm(ordered);
        if (route_length_is_cut_safe(component_length_mm, threshold_mm)) {
            CompositeRoute route;
            route.id = next_route_id++;
            route.layer_id = options.layer_id;
            route.ordered_segments = std::move(ordered);
            route.cut_distance_mm = options.cut_distance_mm;
            route.coalesce_transition_length_mm = options.max_transition_length_mm;
            route.cut_safe_threshold_mm = threshold_mm;
            route.plastic_mm_per_mm = options.plastic_mm_per_mm;
            route.fiber_mm_per_mm = options.fiber_mm_per_mm;
            populate_composite_route_segments_from_ordered(route, options);
            route.warnings.reserve(component.size());
            for (std::size_t candidate_index : component)
                route.candidate_ids.push_back(candidates[candidate_index].id);
            refresh_route_metrics(route);
            result.routes.push_back(std::move(route));
        } else {
            for (std::size_t candidate_index : component)
                result.fallbacks.push_back(make_fallback(
                    next_fallback_id++, options.layer_id, candidates[candidate_index], options, FallbackReason::ShorterThanCutSafeThreshold));
        }
    }

    return result;
}

void stitch_composite_layer_routes(
    CompositeLayerDiagnostic &diagnostic,
    const CompositeRouteGraphOptions &options)
{
    if (diagnostic.routes.size() < 2 || diagnostic.candidates.empty())
        return;

    std::vector<CompositeCandidate> compact_candidates;
    const std::vector<CompositeCandidate> *stitch_candidates = &diagnostic.candidates;
    if (diagnostic.candidates.size() > MAX_POST_COMBINE_STITCH_FULL_CANDIDATES) {
        compact_candidates = route_owned_candidates(diagnostic);
        if (!compact_candidates.empty())
            stitch_candidates = &compact_candidates;
    }

    std::vector<BoundingBox> candidate_bounds;
    candidate_bounds.reserve(stitch_candidates->size());
    for (const CompositeCandidate &candidate : *stitch_candidates) {
        candidate_bounds.push_back(candidate_has_printable_polyline(candidate) ?
            polyline_bounding_box(candidate.polyline) :
            BoundingBox());
    }

    constexpr std::size_t no_region_index = std::numeric_limits<std::size_t>::max();
    std::vector<std::size_t> candidate_region_indices(stitch_candidates->size(), no_region_index);
    std::vector<PrintableRegionBounds> printable_region_bounds;
    std::map<std::tuple<std::size_t, std::size_t, std::size_t, std::size_t>, std::size_t> region_indices_by_scope;

    for (std::size_t index = 0; index < stitch_candidates->size(); ++index) {
        const CompositeCandidate &candidate = (*stitch_candidates)[index];
        if (!candidate.has_printable_region)
            continue;

        const auto key = std::make_tuple(
            candidate.layer_id,
            candidate.object_id,
            candidate.island_id,
            candidate.region_id);
        auto it = region_indices_by_scope.find(key);
        if (it == region_indices_by_scope.end()) {
            const std::size_t bounds_index = printable_region_bounds.size();
            const ExPolygon &printable_region = candidate.printable_region_ref ?
                *candidate.printable_region_ref :
                candidate.printable_region;
            printable_region_bounds.push_back(make_printable_region_bounds(printable_region));
            it = region_indices_by_scope.emplace(key, bounds_index).first;
        }
        candidate_region_indices[index] = it->second;
    }

    stitch_row_graph_routes(
        diagnostic.routes,
        *stitch_candidates,
        candidate_bounds,
        candidate_region_indices,
        printable_region_bounds,
        options);

    for (std::size_t route_index = 0; route_index < diagnostic.routes.size(); ++route_index)
        diagnostic.routes[route_index].id = route_index;
}

CompositeLayerDiagnostic plan_layer_routes_from_candidates(
    const std::vector<CompositeCandidate> &input_candidates,
    const CompositeRouteGraphOptions &options,
    std::size_t object_id,
    std::size_t region_id)
{
    std::vector<CompositeCandidate> candidates = input_candidates;
    prolong_short_candidates_against_printable_regions(candidates, options);

    CompositeLayerDiagnostic diagnostic;
    diagnostic.layer_id = options.layer_id;
    diagnostic.object_id = object_id;
    diagnostic.region_id = region_id;
    diagnostic.candidates.reserve(candidates.size());

    for (CompositeCandidate candidate : candidates) {
        candidate.layer_id = options.layer_id;
        candidate.object_id = object_id;
        candidate.region_id = region_id;
        candidate.length_mm = candidate_length_mm(candidate);
        candidate.status = candidate.length_mm + EPSILON < options.min_segment_length_mm ?
            CandidateStatus::ShortCandidate :
            CandidateStatus::Direct;
        diagnostic.candidates.push_back(std::move(candidate));
    }

    CompositeRouteGraphResult selected = select_composite_routes_from_candidates(diagnostic.candidates, options);
    diagnostic.direct_candidate_count = selected.direct_candidate_count;
    diagnostic.short_candidate_count = selected.short_candidate_count;
    diagnostic.graph_component_count = selected.graph_component_count;
    diagnostic.routes = std::move(selected.routes);
    diagnostic.fallbacks = std::move(selected.fallbacks);

    std::unordered_set<std::size_t> accepted_candidate_ids;
    std::unordered_set<std::size_t> fallback_candidate_ids;
    for (const CompositeRoute &route : diagnostic.routes)
        accepted_candidate_ids.insert(route.candidate_ids.begin(), route.candidate_ids.end());
    for (const CompositeFallback &fallback : diagnostic.fallbacks)
        fallback_candidate_ids.insert(fallback.candidate_ids.begin(), fallback.candidate_ids.end());

    for (CompositeCandidate &candidate : diagnostic.candidates) {
        if (accepted_candidate_ids.count(candidate.id) != 0) {
            candidate.status = CandidateStatus::Accepted;
            continue;
        }
        if (candidate.status == CandidateStatus::Accepted)
            continue;
        if (fallback_candidate_ids.count(candidate.id) != 0)
            candidate.status = CandidateStatus::Fallback;
    }

    return diagnostic;
}

CompositeLayerDiagnostic plan_surface_fill_routes(
    const std::vector<const Surface *> &surfaces,
    CompositeSurfaceFillOptions surface_options,
    CompositeRouteGraphOptions route_options)
{
    route_options.layer_id = surface_options.layer_id;
    std::vector<CompositeCandidate> candidates = make_candidates_from_surface_fills(surfaces, surface_options);
    CompositeLayerDiagnostic diagnostic = plan_layer_routes_from_candidates(
        candidates,
        route_options,
        surface_options.object_id,
        surface_options.region_id);
    append_residual_plastic_refill_fallbacks(diagnostic, surface_options);
    return diagnostic;
}

CompositeLayerDiagnostic plan_perimeter_routes_from_expolygons(
    const ExPolygons &regions,
    const CompositePerimeterOptions &perimeter_options,
    CompositeRouteGraphOptions route_options)
{
    CompositeLayerDiagnostic diagnostic;
    diagnostic.layer_id = perimeter_options.layer_id;
    diagnostic.object_id = perimeter_options.object_id;
    diagnostic.region_id = perimeter_options.region_id;

    if (regions.empty() || (perimeter_options.outer_loop_count == 0 && perimeter_options.inner_loop_count == 0))
        return diagnostic;

    route_options.layer_id = perimeter_options.layer_id;
    route_options.line_spacing_mm = perimeter_options.spacing_mm > EPSILON ?
        perimeter_options.spacing_mm :
        route_options.line_spacing_mm;

    const double threshold_mm = std::max(
        perimeter_options.min_route_length_mm,
        std::max(route_options.min_route_length_mm, route_options.min_segment_length_mm));
    const double base_inset_mm = std::max(0.0, perimeter_options.inset_mm);
    const double spacing_mm = std::max(route_options.line_spacing_mm, 0.01);
    const std::size_t loop_count = std::max(perimeter_options.outer_loop_count, perimeter_options.inner_loop_count);

    std::size_t next_candidate_id = perimeter_options.first_candidate_id;
    std::size_t next_route_id = perimeter_options.first_route_id;
    diagnostic.candidates.reserve(regions.size() * loop_count * 2);

    ExPolygons inset_regions = base_inset_mm > EPSILON ?
        offset_ex(regions, -float(scale_(base_inset_mm)), ClipperLib::jtRound, DefaultMiterLimit) :
        regions;
    for (std::size_t loop_index = 0; loop_index < loop_count; ++loop_index) {
        if (inset_regions.empty())
            break;

        for (std::size_t island_id = 0; island_id < inset_regions.size(); ++island_id) {
            const ExPolygon &expolygon = inset_regions[island_id];
            const std::shared_ptr<const ExPolygon> printable_region_ref =
                std::make_shared<ExPolygon>(expolygon);

            auto append_perimeter_candidate = [&](const Polygon &polygon) {
                Polyline polyline = closed_polyline_from_polygon(polygon);
                if (polyline.points.size() < 2)
                    return;

                CompositeCandidate candidate;
                candidate.id = next_candidate_id++;
                candidate.layer_id = perimeter_options.layer_id;
                candidate.object_id = perimeter_options.object_id;
                candidate.island_id = island_id;
                candidate.region_id = perimeter_options.region_id;
                candidate.family = CandidateFamily::Perimeter;
                candidate.polyline = std::move(polyline);
                candidate.length_mm = polyline_length_mm(candidate.polyline);
                candidate.has_printable_region = true;
                candidate.printable_region_ref = printable_region_ref;
                candidate.fallback_role = erPerimeter;
                candidate.status = candidate.length_mm + EPSILON < threshold_mm ?
                    CandidateStatus::ShortCandidate :
                    CandidateStatus::Accepted;

                diagnostic.candidates.push_back(std::move(candidate));
                CompositeCandidate &stored_candidate = diagnostic.candidates.back();
                if (stored_candidate.status == CandidateStatus::ShortCandidate) {
                    ++diagnostic.short_candidate_count;
                    return;
                }

                diagnostic.routes.push_back(make_direct_perimeter_route(
                    stored_candidate,
                    route_options,
                    next_route_id++));
            };

            if (loop_index < perimeter_options.outer_loop_count)
                append_perimeter_candidate(expolygon.contour);
            if (loop_index < perimeter_options.inner_loop_count)
                for (const Polygon &hole : expolygon.holes)
                    append_perimeter_candidate(hole);
        }

        if (loop_index + 1 < loop_count)
            inset_regions = offset_ex(inset_regions, -float(scale_(spacing_mm)), ClipperLib::jtRound, DefaultMiterLimit);
    }

    diagnostic.direct_candidate_count = diagnostic.candidates.size();
    diagnostic.graph_component_count = diagnostic.routes.size();
    return diagnostic;
}

const char *route_shape_name(CompositeRouteShape shape)
{
    switch (shape) {
    case CompositeRouteShape::NoXYMotion:
        return "no_xy_motion";
    case CompositeRouteShape::OpenPath:
        return "open_path";
    case CompositeRouteShape::ShortOpenPath:
        return "short_open_path";
    case CompositeRouteShape::NearClosedLoop:
        return "near_closed_loop";
    case CompositeRouteShape::ClosedLoop:
        return "closed_loop";
    case CompositeRouteShape::LineOrTail:
        return "line_or_tail";
    case CompositeRouteShape::Unknown:
    default:
        return "unknown";
    }
}

} // namespace FiberseekComposite
} // namespace Slic3r
