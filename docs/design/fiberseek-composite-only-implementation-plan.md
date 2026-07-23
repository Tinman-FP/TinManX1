# FibreSeek Composite-Only Implementation Plan

This document turns the Rocket 1.3.1.480 behavior audit into a TinManX1 build
plan. It records behavior and architecture only; it must not copy Rocket source
code, preset blobs, or private local file paths.

Companion documents:

- `docs/research/fiberseek-composite-only-gap-analysis.md`
- `docs/design/fiberseek-composite-only-behavior-spec.md`
- `docs/design/fiberseek-composite-only-cpp-integration-map.md`
- `docs/research/fiberseek-composite-route-prototype.md`
- `docs/research/fiberseek-rocket-backend-notes.md`
- `docs/research/fiberseek-rocket-coupon-matrix-20260721.md`

## Objective

TinManX1 needs a native FibreSeek `Composite Only` mode where the CFC tool owns
selected model roads and co-extrudes matrix polymer plus continuous fiber on the
same motion path. The current Python planner remains useful for overlay
reinforcement, but it is too late in the pipeline to match Rocket's composite
job structure.

Success means a FibreSeek Seeker 3 PETG + X-CCF heavy slice can be compared
against the Rocket shipped PETG + X-CCF baseline without a mode mismatch, with
similar reinforced-road coverage, layer distribution, command ordering, and
machine-contract safety.

## Evidence Summary

The propeller comparison shows Rocket emitting `Composite Only` while TinManX1
emits `Plastic + Continuous Fiber Overlay`. Rocket produced 3069 `M1001` route
starts, 314 Z levels with fiber routes, and 233.6 g of continuous fiber.
TinManX1 produced 821 `M1001` starts, 154 Z levels with fiber routes, and
33.44 g of continuous fiber. The TinManX1 output passes the basic FibreSeek
machine contract, so this is a planning-mode gap rather than a simple syntax
failure.

One profile-level mismatch also matters: the current TinManX1 heavy FibreSeek
overlay profiles carry `fiber_layer_step = 2`, so they only reinforce every
other eligible layer. Rocket's heavy propeller reference emits fiber on every
observed Z level. TinManX1 still needs native composite-only road ownership to
match Rocket, but the heavy apples-to-apples profiles must not keep the old
overlay cadence when they are used for Rocket parity comparisons.

The strengthened route-block comparison shows the shape mismatch too. Rocket's
reinforced blocks are overwhelmingly long open composite paths: 2976 open
paths, 59 near-closed paths, 27 closed loops, and 7 line/tail paths. TinManX1's
current output is mostly closed overlay loops: 660 closed loops and 161
line/tail paths. TinManX1 emits 15.2% of Rocket's reinforced-route load and
only 8.8% of Rocket's U-positive fiber-road XY motion. That confirms the
next target is not simply higher overlay density; TinManX1 needs native
composite road ownership.

The Rocket backend audit found these behavior-level rules:

- Composite moves carry separate plastic and fiber deltas.
- Fiber perimeters pass matrix-flow-per-mm and fiber-flow-per-mm into the same
  composite move builder.
- Cellular infill candidates are generated from layer island geometry, not from
  emitted G-code.
- Isogrid generation lays three line families at base plus 30, 150, and 90
  degrees, with pitch tied to fiber cellular width and density.
- The route selector chooses non-overlapping long combinations and returns
  rejected or too-short candidates as plastic stubs.
- Cut handling is part of route emission: the move stream is split at the cut
  distance, the cut block is inserted, and the post-cut plastic flow is scaled.
- Bend-radius handling shapes reinforced-route speed and segment splitting
  around turns; it should not be treated as a blanket route deletion rule.

The Rocket API coupon matrix adds a useful mode-level correction. On seven
neutral Z0 coupons, the shipped PETG/X-CCF `Speedy` profile emitted
`Plastic Only` and zero fiber. `ReinForced` emitted `Plastic and Composite`
with 49 to 241 CFC route starts depending on geometry. `Fortified` emitted
`Composite Only` with 80 to 572 CFC route starts. All fiber-bearing coupon
outputs used `;CUT DISTANCE 54.8`, and the reconstructed route blocks were
overwhelmingly open paths.

Technical literature points in the same direction. Continuous-fiber strength
depends heavily on directional toolpath placement, local stress direction, and
layer-by-layer manufacturability; recent work uses field-based or graph-based
fiber path planning rather than treating fiber as a decorative overlay. Useful
references:

- Field-Based Toolpath Generation for 3D Printing Continuous Fibre Reinforced
  Thermoplastic Composites: https://arxiv.org/abs/2112.12057
- Multi-layer continuous carbon fiber pattern optimization and spline based
  path planning interpretation: https://arxiv.org/abs/2404.11404
- Continuous Toolpath Planning in Additive Manufacturing:
  https://arxiv.org/abs/1908.07452
- Path Planning and Bending Behaviors of 3D Printed Continuous Carbon Fiber
  Reinforced Polymer Honeycomb Structures:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10708446/
- Learning Based Toolpath Planner on Diverse Graphs for 3D Printing:
  https://arxiv.org/abs/2408.09198
- Toolpath Generation for High Density Spatial Fiber Printing Guided by
  Principal Stresses: https://arxiv.org/abs/2410.16851
- Continuous fiber printing track simulation and minimum curvature discussion:
  https://pdfs.semanticscholar.org/9ad2/b146a625102b239574114bd2f1ddac263fe0.pdf
- Aura user manual, session/profile/material separation:
  https://www.ddmlab.ru/wp-content/uploads/2019/02/Aura-User-Manual.pdf

The open-source slicer ecosystem points to the same missing primitives. Cura's
CFF feature request describes the need to add fiber to selected layers and
perimeters, expose fiber width, temperature, flow, speed, bend radius, and cut
G-code, and avoid treating the part as a hacked multi-material print:
https://github.com/Ultimaker/Cura/issues/14483. PrusaSlicer's matching request
calls out replacing selected perimeters during slicing and eventually orienting
fiber like infill or automated fiber placement:
https://github.com/prusa3d/PrusaSlicer/issues/9609.

## Manufacturing Modes

Add an explicit process option:

- `plastic_plus_fiber_overlay`: current TinManX1 behavior. Keep this for
  experiments, light reinforcement, and machines where fiber is a secondary
  pass.
- `composite_only`: new FibreSeek mode. Accepted reinforced perimeters and
  infill become first-class composite roads. Plastic roads remain only where the
  strategy asks for plastic-only support, skins, brim, support, or rejected
  fiber stubs.

The existing `Light`, `Medium`, and `Heavy` strength names should remain. They
should control route density, layer cadence, and candidate acceptance policy,
not Rocket-specific naming.

The Rocket backend maps its old UI terms into three enum values:
`Speedy`, `ReinForced`, and `Fortified`. TinManX1 should keep the sanitized
labels but map them behaviorally:

| TinManX1 label | Rocket behavior family | Key baseline behavior |
| --- | --- | --- |
| Light | Speedy | PETG/X-CCF baseline is plastic-only in API coupon tests; treat any TinManX1 light-fiber strategy as a deliberate extension, not Rocket parity. |
| Medium | ReinForced | `Plastic and Composite`; isogrid infill plus fiber perimeters, 20% PETG/X-CCF isogrid density, one plastic outer guard road. |
| Heavy | Fortified | `Composite Only`; solid fiber infill plus fiber perimeters, no PETG/X-CCF plastic outer guard road, higher normal fiber speed. |

This mapping prevents the old regression where all three modes rendered the
same fiber path set with only summary numbers changing.

## Rocket Automation Harness

Rocket 1.3.1.480 runs an ASP.NET monolith and exposes:

```text
POST /api/slice/generate
```

The request is a complete project snapshot: identifiers, project path, print
mode, enabled parts, slot/material assignments, one settings set, active
plastics/composites/extruders/slots/printer/profile. The handler resets
override fields, maps the payload to Aura2's `SessionModel`, creates
`SessionSet(..., Edition.OPEN, PrintModes.<mode>)`, calls
`SlicingEngine.GenerateAsync()`, and writes `result.json.gz` under
`projectPath`.

Implementation task: add an out-of-tree or source-helper harness that can:

1. Build a `RequestGenerate` payload from Rocket preset/project JSON and a
   generated STL/3MF fixture.
2. POST to the running Rocket local backend port discovered from the process
   list or configured by argument.
3. Download or read the resulting `result.json.gz`.
4. Extract Rocket's compressed result, resolved session profile, and G-code.
5. Run `scripts/compare_fiberseek_gcode.py` against matching TinManX1 output.

This harness should remain clean-room: use Rocket as an oracle and record
behavioral metrics, but do not copy vendor preset blobs or source into
TinManX1.

Current status: `scripts/rocket_fiberseek_slice_harness.py` can build the
request payload, discover Rocket's local monolith port, post a generated STL,
and extract response JSON, resolved session profile, and G-code from
`result.json.gz`. The first full corrected coupon matrix is recorded in
`docs/research/fiberseek-rocket-coupon-matrix-20260721.md`.

## Native Data Model

TinManX1 currently carries normal extrusion as a single scalar. Composite-only
needs an internal representation that survives from route planning through
G-code writing and preview.

Recommended structures:

- `CompositeRoute`: layer id, Z, source, route id, tool id, material slot,
  start/cut/end metadata, and ordered segments.
- `CompositeSegment`: XY or XYZ geometry, speed, plastic delta, fiber delta,
  route phase, optional P ratio, and bend/cut warnings.
- `CompositeFallback`: plastic-only segments created from rejected fiber
  candidates.
- `CompositeTail`: post-cut tail geometry that belongs to the accepted route
  and is walked after the cutter fires.

Implementation choice: start with a separate composite route container owned by
the layer/region rather than overloading every existing `ExtrusionPath`. Once
the writer is stable, selected paths can be bridged into existing ordering and
preview code. This avoids destabilizing every normal Orca extrusion role.

Current status: `src/libslic3r/FiberseekCompositePlanner.*` now provides a
compile-tested diagnostic container with candidate families, route phases,
planned composite segments, independent matrix/fiber flow values, cut-safe
thresholds, route tails, tension/release metadata, after-cut plastic
compensation, fallback reasons, and release-safety helpers. It has two selector
strategies: the original nearest-endpoint diagnostic selector and a
Rocket-shaped row-graph diagnostic selector. The row-graph selector preserves
clipped candidates as owned rows, groups them by measured row level and angle,
searches start/end endpoint transition pairs between neighboring levels, rejects
connector segments that cross other candidate rows, enumerates tail-to-tail
paths plus contiguous path windows, accepts single-node or multi-node
combinations whose owned-road score reaches the cut-safe threshold, greedily
selects the best non-overlapping combination group by covered owned length, and
returns non-selected rows as plastic fallback. The planner also has a
surface-fill adapter that uses TinManX1's native `Fill::fill_surface()` machinery
to generate owned fiber-road candidates from raw slicer surfaces with perimeter
anchoring disabled. A multi-surface helper now feeds those candidates through the
native graph selector and returns a layer diagnostic.
`PrintObject::generate_fiberseek_composite_diagnostics()` now runs after normal
infill generation for `composite_only` plus `fiber_generate_infill`, filters
internal/internal-solid fill surfaces, applies the user start/top guard and layer
cadence, and stores route diagnostics on the owning `LayerRegion`. The hook now
reads the Rocket-style `fiber_infill_solid_payload` when present, including
solid angle-list cycling, solid road width, and minimum segment length, and uses
the row-graph strategy for FibreSeek composite-only work. The same pass now
applies first-stage native ownership: on selected composite-only infill layers,
normal internal/sparse-solid infill entities are replaced with explicit plastic
fallback entities, while top/bottom skins, bridge fill, ironing, gap fill, and
other non-owned fills are preserved. Accepted composite routes remain in the
diagnostic container for the native CFC writer.

Gap after the Rocket 1.3.1.480 deep dive: the current C++ row-graph selector is
still diagnostic and does not yet model Rocket's full `InfillNode` /
`PathNode` graph. Rocket preserves clipped candidate roads as route identities,
groups adjacent roads into nodes when both endpoint-side transitions are legal,
stores one-sided transitions as start/end-flagged graph connections, validates
those transitions inside split-island geometry, splits branch-heavy node ends,
enumerates paths from tails, adds single-node candidates that already exceed the
cut-safe length, creates contiguous sub-combinations from long paths, then
greedily chooses non-overlapping combinations that maximize covered node length.
TinManX1 now implements that selector shape in clean-room C++ for diagnostics,
but it still needs a `CompositeNode` layer, exact split-island transition
parity, and production-grade CFC writer parity before composite-only G-code
export is enabled by default. An experimental native writer now exists behind
`TINMANX1_NATIVE_COMPOSITE_ONLY_EXPERIMENTAL=1`; it emits accepted diagnostic
routes as FibreSeek `M1001`/`M1002` route blocks, short connector spans as
correction travel, and skips release-unsafe routes. It is for controlled G-code
comparison only until matrix-volume math, tool normalization, node parity,
split-island parity, and analyzer gates are complete.

## Geometry Hook

The hook needs to run after perimeters and fill regions are generated, but
before G-code export chooses tools and writes moves.

Candidate TinManX1 locations:

- `LayerRegion` already owns `slices`, `fill_expolygons`, `fill_surfaces`,
  `perimeters`, and `fills`.
- `GCode::process_layer()` later groups `LayerRegion::perimeters.entities` and
  `LayerRegion::fills.entities` by extruder/island.
- `Print::export_gcode()` currently runs normal G-code export, then calls the
  Python planner on the completed file. That post-export hook remains the
  overlay path, not the composite-only path.

Add a pre-export path such as:

- `Print::apply_fiberseek_composite_routes()`
- `PrintObject::generate_fiberseek_composite_routes()`
- `LayerRegion::fiberseek_composite_routes`

The planner should consume layer islands, perimeters, and fill regions directly.

Current hook status: a diagnostic/native-ownership version is wired into
`PrintObject::infill()` after `Layer::make_fills()` completes and before
`posInfill` is marked done. This pass clears stale diagnostics on every run,
uses the resolved `Print::full_print_config()`, applies Rocket's measured
solid-infill acceptance rule of `cut_distance + 5 mm`, applies the serialized
solid-infill payload where available, suppresses owned internal/sparse-solid
plastic source roads on selected composite-only layers, and inserts planned
plastic fallback roads for rejected candidates. Negative Rocket
perimeter-extension values are recorded in profiles, but the current C++
adapter only applies nonnegative fill overlap; matching Rocket's negative
inset/shrink behavior is the next geometry-parity item.

Current writer status: `GCode::process_layer()` can append accepted native
diagnostic routes after the normal plastic/fallback work for each object
instance when the explicit experimental environment variable is set. The writer
emits the existing TinManX1/Rocket-readable fiber comments, `T0`/`T1`, `M1001`,
`U`/`V`/`P` moves, configured `fiber_cut_gcode`, post-cut matrix-only tail moves,
and `M1002`. It deliberately leaves the normal fail-closed export guard in place
unless that environment variable is present.

## Perimeter Strategy

Inputs:

- outer fiber perimeter count
- inner fiber perimeter count
- plastic outer roads when fiber is present
- plastic inner roads when fiber is present
- minimum perimeter length
- cut distance, contact radius, extended contact radius
- minimum bend radius and maximum arc segment length

Rules:

- Keep the user-visible outer surface plastic when the profile asks for plastic
  outer roads.
- Convert selected inner/outer perimeter loops into composite routes on the CFC
  tool.
- Build a route tree for perimeter candidates using minimum perimeter length
  and extended cut-safe length so short loops can be joined when geometry
  permits.
- Plan outer and inner/hole perimeter routes separately; preserve path
  direction because Rocket treats outer and inner fiber bands differently.
- Reject routes that violate cut length or bend constraints, and emit the
  rejected geometry as plastic fallback rather than leaving a gap.
- Preserve TinManX1's useful alternating hole coverage, but apply it while
  selecting geometry-owned composite routes.

## Infill Strategy

Inputs:

- fiber infill type: solid, rhombic, isogrid, anisogrid, tetragrid
- density, orientation angles, and optional layer phase
- fiber cellular/solid line width
- plastic cellular/solid line width
- fiber inset into perimeters
- minimum segment length
- accepted route threshold, with the first baseline equal to CFC cut distance
  plus 5 mm

Rules:

- Generate candidate ribs from `LayerRegion` fill surfaces or clipped island
  polygons.
- Offset the island by the configured fiber inset before clipping candidates.
- For the PETG + X-CCF baseline, isogrid starts from three line families at
  base plus 30, 150, and 90 degrees.
- Use a graph combination solver: split nodes, find tails, enumerate candidate
  paths, accept non-overlapping combinations that satisfy the cut window, and
  return rejected nodes as plastic fallback.
- Layer phasing should be deterministic so different holes can be reinforced on
  alternating eligible layers without accidental cross-part stitching.

## Writer And Machine Contract

Composite-only cannot use the normal single-E `GCodeWriter` path unchanged.
Add a FibreSeek writer path that can emit:

- T0/T1 tool ownership consistent with the machine profile
- reinforced route start command
- line moves with plastic and fiber deltas on the proper axes
- P ratio tags when both plastic and fiber are present
- cut command and post-cut tail handling
- route end command
- temperature, fan, chamber, and preheat behavior from the CFC profile
- bend-speed shaping plus fiber tension lead/release splits

Writer splitting must happen on native route moves before text emission. Rocket
backs up from the active route end by `CutDistance - NozzleContactRadiusExtended`,
splits the affected composite move, inserts the cut block between the split
fragments, then walks the delay/tail span with fiber disabled and the profile's
after-cut matrix multiplier applied. TinManX1 should model this as route-phase
data plus move splitting, not as a post-export search/insert operation.

For FibreSeek CFC routes, force linear G1 output or segment arcs by
`fiber_max_arc_segment_length`. The Max EZ `G2` issue is a good reminder that
fiber/machine-specific G-code must not inherit generic arc output casually.

The current experimental writer approximates owned-road versus connector
segments by treating Rocket-sized short transition spans as correction travel.
The next writer iteration should promote explicit segment ownership from the
row-graph planner into `CompositeRouteSegment` so cut placement and matrix/fiber
flow are calculated from native route phases instead of this conservative length
heuristic.

## Validation Matrix

Analyzer gates:

- Output mode is `Composite Only` when composite-only is selected.
- `M1001`, cut, and end-route commands are balanced and ordered.
- Fiber routes appear on every eligible layer for heavy PETG + X-CCF.
- T0 composite roads carry both matrix and fiber where expected.
- No CFC route is below the configured cut-safe length after cut handling.
- No CFC route violates the selected bend radius without a planner warning.
- No CFC route crosses voids, pockets, or separate islands.
- Preview and summary use the native composite result, not a stale reload.

Comparison targets:

- Rocket PETG + X-CCF shipped baseline for the propeller.
- `coupon_01_rect_plate_100x40x6`: long straight perimeter and rib baseline.
- `coupon_02_single_hole_plate_100x60x6_h20`: single-hole perimeter
  ownership and hole loop coverage.
- `coupon_03_multi_hole_plate_120x80x6`: alternating-hole coverage and graph
  route selection.
- `coupon_04_min_length_bars_40_55_65_90`: cut threshold behavior across
  40, 55, 65, and 90 mm islands.
- `coupon_05_bend_radius_hole_ladder`: bend-radius stress case across small to
  larger holes.
- `coupon_06_gear_with_six_holes`: gear teeth, hole coverage, and no-crossing
  validation.
- `coupon_07_separate_islands`: guard against stitching routes across separate
  model islands.

The generated STEP/STL manifest lives at
`work/rocket-algorithm-1.3.1.480-research/coupons_z0/manifest.json` outside
the repo. The generator is `scripts/generate_fiberseek_test_coupons.py`.
Earlier centered-at-Z0 coupons are retained only as a lesson learned; Rocket
expects fixture geometry to sit on the build plate.

Metrics to compare:

- route count and load total by Z
- fiber and polymer usage
- print-time envelope
- T0/T1 ownership by role
- route length percentiles
- U-positive fiber-road XY by route and Z
- V-positive matrix-road XY by route and Z
- route shape classes: open path, near-closed path, closed loop, line/tail
- closure-gap and bounding-box distributions
- command sequence signatures
- shortest emitted path
- cut-distance comments and cut insertion location

Current analyzer artifacts:

- `scripts/compare_fiberseek_gcode.py` emits full JSON, including per-Z M1001
  load buckets, reconstructed route-block geometry, U-positive fiber-road XY,
  V-positive matrix-road XY, shape classes, closure gap, and bounding-box
  distributions.
- `--layer-csv <path>` writes a Z-bucket CSV for Rocket/TinMan comparisons.
- `--route-csv <path>` writes one reconstructed `M1001` to `M1002` block per
  CSV row for route-level inspection.
- The latest propeller comparison CSV shows Rocket with fiber load on 314 Z
  buckets and TinManX1 with fiber load on 154 Z buckets. TinManX1 has 161 Z
  buckets where Rocket emitted fiber load and TinManX1 emitted none. Even on
  shared reinforced Z buckets, TinManX1 emits about 179,499 mm of U-positive
  fiber-road XY against Rocket's about 1,018,715 mm.

## Phased Build

Phase 0: freeze current overlay planner as `plastic_plus_fiber_overlay` and keep
the analyzer strict enough to flag overlay-vs-composite mismatches.

Phase 1: add the composite-only option, profile plumbing, and native C++
containers. No behavior change until the feature flag is selected.

Phase 2: implement generated-rib infill from layer geometry and emit a diagnostic
sidecar without changing G-code. Validate route coverage and rejected plastic
fallback on coupons.

Phase 3: add perimeter route ownership and fallback. Validate hole coverage and
avoid stitching across separate islands.

Phase 4: add FibreSeek composite writer support with separate plastic/fiber
deltas, start/cut/end route state, and preview/summary integration.

Phase 5: run Rocket parity sweeps on the PETG + X-CCF baseline, then widen to
the TinManX1 CFC material families.

## Phase 1 Status

The first fail-closed plumbing pass is now in place:

- `fiber_manufacturing_mode` exists as a process option with
  `plastic_plus_fiber_overlay` and `composite_only` values.
- Existing generated FibreSeek process profiles default to
  `plastic_plus_fiber_overlay`, preserving current behavior.
- The post-export Python overlay planner is skipped when `composite_only` is
  selected, so a future composite-only profile cannot silently fall back to the
  wrong manufacturing mode.
- `Print::export_gcode()` now fails closed if continuous fiber is requested
  with `composite_only` before the native composite-road writer exists. This
  prevents a misleading plastic-only or overlay-style output from being
  exported under a composite-only label.
- The compact Strength UI and profile-generation/lint wiring know about the
  new option.

This does not yet emit production composite-only G-code. That is intentional:
the new mode is gated until native route containers, fallback geometry, and the
FibreSeek writer exist.

## Phase 2 Route Graph Target

The first diagnostic native planner should mirror Rocket's observed behavior at
the algorithm level while staying clean-room:

1. Generate candidate ribs from layer polygons/fill surfaces.
2. Clip ribs against islands with holes.
3. Split candidates into short and long sets using the profile minimum segment
   length.
4. Prolong short candidates against the legal island boundary when possible.
   If a short fragment cannot be prolonged, keep it in the graph as a possible
   joined-route fragment before falling back to plastic.
5. Preserve clipped candidate rows as node identities; use noded/split geometry
   only for containment, crossing, and transition legality checks.
6. Add start/end-flagged transition edges between candidates or merge adjacent
   candidates into one multi-road node when both endpoint transitions are legal.
7. Enumerate legal paths from tail nodes and closed-loop seeds without reusing
   a node inside one path.
8. Accept full paths, valid sub-paths, and single nodes whose owned road length
   plus connector spacing reaches the cut-safe
   threshold. The PETG/X-CCF baseline threshold is cut distance plus 5 mm.
9. Choose non-overlapping route combinations that maximize useful coverage, with
   a tie preference for fewer separate reinforced routes.
10. Export accepted open paths, closed loops, tails, and rejected fallback stubs
   to a diagnostic sidecar.
11. Prove on coupons that no route crosses holes, pockets, or separate islands.

The diagnostic sidecar should include route id, layer id, source geometry,
length, candidate-node ids, fallback-node ids, hole/void coverage distances,
bend-risk points, closure gap, bounding box, shape class, U-positive fiber-road
length, V-positive matrix-road length, and rejection reasons. It should be
possible to compare that sidecar to Rocket and TinMan G-code metrics before any
plastic roads are replaced in production output.

The Python coupon harness now exports this diagnostic shape for neutral
polygons, including direct candidates, short candidates, graph components,
accepted routes, plastic fallbacks, bend-risk counts, and an explicit
unsupported-void crossing count. It also exports route-shape diagnostics:
closure gap, bounding spans, and open/closed/line route class. The latest run
is stored at
`work/rocket-algorithm-1.3.1.480-research/prototype-routes-shape-metrics-20260721`.

Native C++ groundwork now exists in `src/libslic3r/FiberseekCompositePlanner.*`.
That module is compile-tested and now includes candidates, routes, fallbacks,
cut-safe checks, unsupported-void counts, independent fiber/matrix road-length
metrics, route closure, bounding spans, route-shape classes, Rocket's measured
six-line-width transition helper, a first route selector that joins nearby
candidates into cut-safe open routes or emits plastic fallback, and a
surface-fill-to-candidate adapter for real layer geometry. The multi-surface
adapter is ready for a `LayerRegion::fill_surfaces` diagnostic hook. It is not
connected to production G-code emission.

## Open Questions

- The exact emitted `CUT DISTANCE 54.8` formula needs one more controlled
  experiment because the profile database records 58 mm cut distance and
  1.8 mm extended contact radius.
- The exact U/V/P axis mapping should be verified with more short coupon slices.
- Bend radius should remain user controlled until physical FibreSeek testing can
  correlate bend radius with print speed and actual part quality.
- We should avoid claiming Rocket equivalence for non-PETG CFC material families
  until each has at least one validated Rocket or physical-machine baseline.

## Immediate Next Step

Build the Phase 2 layer-geometry adapter next. That means feeding real
`LayerRegion` fill/perimeter geometry into the native route selector and
writing a diagnostic sidecar before any production plastic roads are replaced.
That lets TinManX1 show the user exactly what geometry the new native planner
would own before we allow it to emit composite-only G-code.

Use `docs/design/fiberseek-composite-only-cpp-integration-map.md` as the source
map for this implementation. The most important rule is that `composite_only`
must not run through the post-export Python overlay path. It needs native C++
route data before `GCode::process_layer()` emits perimeter and infill roads.
