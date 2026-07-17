///|/ Wave overhang generator interface (algorithm abstraction).
///|/
///|/ Released under the terms of the AGPLv3 or higher.
///|/
#ifndef slic3r_WaveOverhangs_IGenerator_hpp_
#define slic3r_WaveOverhangs_IGenerator_hpp_

#include <tuple>
#include <vector>

#include "libslic3r/ExPolygon.hpp"
#include "libslic3r/ExtrusionEntity.hpp"
#include "libslic3r/Flow.hpp"
#include "libslic3r/Polygon.hpp"
#include "libslic3r/PrintConfig.hpp"

namespace Slic3r::WaveOverhangs {

// Ring spacing mode (uniform constant step vs progressively growing step).
enum class SpacingMode { Uniform, Progressive };

// Inter-ring seam/direction mode (see wave_overhang_seam_mode in PrintConfig).
enum class SeamMode { Alternating, Aligned, Random };

struct CommonParams {
    int         perimeter_count        = 1;
    int         additional_shell_count = 0;
    double      line_spacing           = 0.35;
    double      line_width             = 0.4;
    Flow        overhang_flow;
    double      scaled_resolution      = 1.0;
    SpacingMode spacing_mode           = SpacingMode::Uniform;   // Andersons only.
    SeamMode    seam_mode              = SeamMode::Alternating;  // shared.
    double      min_length_mm          = 0.0;   // mm; skip overhangs whose contour length is below this.
    int         max_iterations         = 0;     // 0 = unlimited; safety cap on main loop (wavefronts for Andersons, rings for Kaiser).
    // Alpha.6 tunables (Andersons only).
    double      perimeter_overlap      = 0.1;   // mm; extend wave propagation toward perimeters.
    double      minimum_wave_width     = 0.7;   // mm; split wave region when a neck is narrower than this.
    WaveOverhangPattern pattern        = WaveOverhangPattern::Smart;
    double      min_new_area           = 0.01;  // mm^2; early-termination threshold on new-area growth.
    bool        use_instead_of_bridges = false; // when true, wave over flat bridgeable spans too.
    double      fringe_reinforcement_max_cover_to_real = 140.0; // cover/reference ratio cap for adaptive shallow-fringe reinforcement.
    double      fringe_reinforcement_max_cover_area_mm2 = 40.5; // mm^2 cap for adaptive shallow-fringe reinforcement.
    double      fringe_contact_compensation_max_over_cap = 0.0; // ratio points over the cap where rejected fringe gets bounded half-step contact fronts.
    // Corner-aware spacing taper: densify line spacing near sharp overhang corners
    // so short cantilevered wave lines have neighbours to fuse with. The master
    // gate is `corner_taper_enable`; when false the main propagation runs
    // verbatim regardless of the other three values. The downstream generator
    // ALSO refuses to engage when line_spacing_corner is 0 or >= line_spacing,
    // or when corner_taper_distance is 0, so a partially-configured taper is
    // a no-op rather than a silent surprise.
    bool        corner_taper_enable    = false;
    double      line_spacing_corner    = 0.0;   // mm; 0 or >= line_spacing means taper off.
    double      corner_taper_distance  = 0.0;   // mm; radius of corner influence. 0 = taper off.
    double      corner_angle_threshold = 90.0;  // degrees; interior angle below this is a corner.
};

struct GenerationDiagnostics {
    struct Component {
        size_t candidate_index        = 0;
        size_t emitted_paths          = 0;
        size_t wave_cover_components  = 0;
        bool   fringe_filter_applied  = false;
        bool   fringe_reinforced      = false;
        bool   fringe_reinforcement_rejected = false;
        bool   fringe_contact_compensated = false;
        size_t fringe_contact_compensation_fronts = 0;
        double real_overhang_area_mm2 = 0.0;
        double wave_cover_area_mm2    = 0.0;
        double filled_area_mm2        = 0.0;
    };

    size_t candidate_regions        = 0;
    size_t real_overhang_empty      = 0;
    size_t bridgeable_skipped       = 0;
    size_t fringe_filtered_regions  = 0;
    size_t fringe_reinforced_regions = 0;
    size_t fringe_reinforcement_rejected_regions = 0;
    size_t fringe_contact_compensated_regions = 0;
    size_t fringe_contact_compensation_fronts = 0;
    size_t wave_cover_components    = 0;
    size_t split_cover_components   = 0;
    size_t seed_empty_splits        = 0;
    size_t accumulated_empty_splits = 0;
    size_t front_empty_splits       = 0;
    size_t front_levels             = 0;
    size_t front_polylines          = 0;
    size_t emitted_paths            = 0;
    size_t path_regions             = 0;
    double overhang_area_mm2        = 0.0;
    double real_overhang_area_mm2   = 0.0;
    double wave_cover_area_mm2      = 0.0;
    double filled_area_mm2          = 0.0;
    std::vector<Component> components;
};

struct GenerateResult {
    std::vector<ExtrusionPaths> paths;     // per-region
    Polygons                    residual;  // covered area (subtracted from infill upstream)
    GenerationDiagnostics       diagnostics;
};

class IGenerator {
public:
    virtual ~IGenerator() = default;
    virtual GenerateResult generate(const ExPolygons   &overhang_area,
                                    const Polygons     &lower_slices_polygons,
                                    const CommonParams &params) = 0;
    virtual const char *name() const = 0;
};

} // namespace Slic3r::WaveOverhangs

#endif
