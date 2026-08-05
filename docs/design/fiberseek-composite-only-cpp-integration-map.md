# FibreSeek Composite-Only C++ Integration Map

This map ties the clean-room Rocket behavior audit to TinManX1 source locations.
It is a build guide, not a code transplant. It records where TinManX1 needs new
native composite-route ownership so FibreSeek `Composite Only` output is not
limited by the current post-export overlay planner.

## Current TinManX1 Flow

The current FibreSeek path runs after ordinary G-code export:

- `src/libslic3r/Print.cpp:116` decides whether any continuous-fiber behavior
  is requested.
- `src/libslic3r/Print.cpp:195` decides whether the current profile should run
  the TinManX1 FibreSeek Python planner.
- `src/libslic3r/Print.cpp:252` launches
  `orcaslicer_codex_native_fiber_planner.py` with process options.
- `src/libslic3r/Print.cpp:2986` runs `gcode.do_export(...)` first.
- `src/libslic3r/Print.cpp:2987` then rewrites the already-exported G-code.
- `src/libslic3r/Print.cpp:2988` reloads preview results from the rewritten
  file.

That is correct for `plastic_plus_fiber_overlay`. It is the wrong architecture
for Rocket-style `composite_only`, because the primary model roads have already
been assigned to normal plastic extruders before fiber planning begins.

## Native Layer Emission Flow

The useful C++ insertion points are inside the existing layer export flow:

- `src/libslic3r/GCode.cpp:4583` starts `GCode::process_layer(...)`.
- `src/libslic3r/GCode.cpp:5021` enters object-layer extrusion grouping.
- `src/libslic3r/GCode.cpp:5052` iterates `LayerRegion` objects.
- `src/libslic3r/GCode.cpp:5064` groups both infill and perimeter entities.
- `src/libslic3r/GCode.cpp:5076` asks `LayerTools` which extruder owns each
  extrusion collection.
- `src/libslic3r/GCode.cpp:5104` appends the entities into the per-extruder,
  per-island order.
- `src/libslic3r/GCode.cpp:5503` emits perimeters before infill when configured.
- `src/libslic3r/GCode.cpp:5513` emits infill.
- `src/libslic3r/GCode.cpp:5515` emits infill-first perimeters afterward.
- `src/libslic3r/GCode.cpp:6198` writes perimeter entities.
- `src/libslic3r/GCode.cpp:6218` writes infill entities.
- `src/libslic3r/GCode.cpp:6171` and `src/libslic3r/GCode.cpp:6413` convert an
  `ExtrusionPath` to motion commands.
- `src/libslic3r/GCode.cpp:7111` emits normal linear `E` moves.
- `src/libslic3r/GCode.cpp:7173` emits normal `G2/G3` arc `E` moves.

Composite-only needs to enter before or during this flow. It cannot be
implemented as a file rewrite after `Print::export_gcode()`.

## Geometry Ownership

`LayerRegion` already owns the geometry needed for a native planner:

- `src/libslic3r/Layer.hpp:45`: raw sliced surfaces.
- `src/libslic3r/Layer.hpp:58`: fill expolygons.
- `src/libslic3r/Layer.hpp:60`: fill surfaces.
- `src/libslic3r/Layer.hpp:73`: perimeter extrusion collections.
- `src/libslic3r/Layer.hpp:77`: fill extrusion collections.
- `src/libslic3r/Layer.hpp:157`: layer islands.
- `src/libslic3r/Layer.hpp:197`: perimeter generation.
- `src/libslic3r/Layer.hpp:200`: fill generation.

Recommended first implementation:

```text
src/libslic3r/Fiber/FiberseekCompositeTypes.hpp
src/libslic3r/Fiber/FiberseekCompositePlanner.hpp
src/libslic3r/Fiber/FiberseekCompositePlanner.cpp
src/libslic3r/Fiber/FiberseekCompositeGCode.hpp
src/libslic3r/Fiber/FiberseekCompositeGCode.cpp
```

Add these files to `src/libslic3r/CMakeLists.txt`.

Add a native route container to `LayerRegion`:

```text
std::vector<FiberseekCompositeRoute> fiberseek_composite_routes;
std::vector<FiberseekCompositeFallback> fiberseek_composite_fallbacks;
```

Do not overload every existing `ExtrusionPath` in the first pass. Normal Orca
extrusion roles have many side effects: cooling markers, pressure advance,
volumetric limits, wipe paths, object labels, and arc fitting. Keep composite
roads explicit until writer, preview, and comparison are stable.

Minimum native structs for the diagnostic pass:

```text
FiberseekCompositeCandidate
  id, layer id, object id, island id, region id, source role
  source polyline/loop, candidate family, length, min-bend estimate
  direct-or-short status and legal-containment status

FiberseekCompositeRoute
  id, layer id, accepted candidate ids, ordered segments, tail segments
  route length, tail length, cut-safe threshold, cut metadata
  planned composite segments, route phases, material/tool ids
  matrix/fiber flow values, fiber-positive length, matrix-positive length
  travel length
  closure gap, bounding spans, route shape class
  tension/release fields, warnings
  unsupported-void crossing count must be zero

FiberseekCompositeFallback
  rejected candidate ids, replacement segments, rejection reason
  owning layer/region and intended plastic role
```

The diagnostic pass should persist these as a sidecar before any G-code change.
Production composite-only can be enabled only after accepted routes and
fallbacks are both represented.

Implementation status:

- `src/libslic3r/FiberseekCompositePlanner.hpp`
- `src/libslic3r/FiberseekCompositePlanner.cpp`

These files now provide the first compile-tested native diagnostic data model:
candidate family/status, accepted composite routes, route phases, planned
matrix/fiber segments, cut/tail/tension metadata, plastic fallbacks, layer
diagnostics, cut-safe length checks, unsupported-void crossing counts,
route-shape classification, fiber/matrix/travel length fields,
closure/bounding-box fields, and scaled-coordinate length helpers.
`measure_route()` and `refresh_route_metrics()` now compute route length, tail
length, U-positive route length, V-positive matrix length, travel length,
closure gap, bounding spans, and shape class from native polylines and planned
segments. `make_candidates_from_surface_fill()` and
`plan_surface_fill_routes()` are the first adapters from real slicer surfaces
into owned composite-road candidates and layer diagnostics; they call the
native fill engine with perimeter anchoring disabled so the FibreSeek graph
selector owns the route joining step. Multi-surface candidate generation now
preserves per-surface island ownership instead of collapsing every candidate
into one island id, and both selector strategies refuse to join candidates
across different layer/object/region/island/family scopes.

The native selector now has an explicit strategy switch:

- `LegacyNearestEndpoint`: the original diagnostic nearest-endpoint component
  heuristic, retained for compatibility and regression comparison.
- `RocketRowGraph`: the current FibreSeek composite-only diagnostic strategy. It
  preserves clipped candidate rows, groups rows by measured angle/level, builds
  start/end endpoint transitions only between neighboring levels, rejects
  connector segments that cross unrelated candidate roads, enumerates
  tail-to-tail paths plus contiguous path windows, accepts single-node and
  multi-node route combinations with a Rocket-style owned-road/spacing score,
  greedily selects the best non-overlapping combination group, and returns
  rejected rows as plastic fallback. `PrintObject::generate_fiberseek_composite_diagnostics()`
  uses this strategy for composite-only diagnostics.

`LayerRegion` now owns a `fiberseek_composite_diagnostic` container and a
`has_fiberseek_composite_routes()` helper. This does not alter normal extrusion
or G-code output, but it gives the native planner a source-adjacent place to
store accepted composite routes and plastic fallbacks before emission.

`PrintObject::generate_fiberseek_composite_diagnostics()` is now wired after
normal `Layer::make_fills()` completes. It runs only when the resolved full
config requests `fiber_manufacturing_mode = composite_only`,
`fiber_enabled = true`, and `fiber_generate_infill = true`; clears stale
diagnostics otherwise; filters to internal/internal-solid fill surfaces; applies
fiber start/top layer guards and layer cadence; uses Rocket's measured
solid-route threshold of `fiber_cut_distance + 5 mm`; reads the Rocket-style
`fiber_infill_solid_payload` values for solid angle-list cycling, road width,
and minimum segment length; applies first-stage source-road ownership by
removing normal internal/sparse-solid infill entities from selected
composite-only layers; emits rejected candidate rows back into `LayerRegion`
fills as plastic fallback paths with their original sparse/solid flow roles;
and stores the accepted route diagnostic back on each `LayerRegion`.
`GCode::process_layer()` now also has an experimental native CFC writer hook,
enabled only by `TINMANX1_NATIVE_COMPOSITE_ONLY_EXPERIMENTAL=1` or
`ORCASLICER_CODEX_NATIVE_COMPOSITE_ONLY_EXPERIMENTAL=1`, that appends accepted
diagnostic routes after normal plastic/fallback work for each object instance.
The normal composite-only export guard remains fail-closed unless this explicit
development gate is set.

Next selector correction: promote `RocketRowGraph` into a small clean-room
`CompositeNode` model while keeping split-island geometry as the transition
validator. The Rocket backend uses candidate segments as route identities,
groups adjacent segments into `InfillNode` objects when both endpoint-side
transitions are legal, stores one-sided transitions as explicit
start/end-flagged graph connections, then materializes the selected path through
node-internal connector tables. TinManX1 already keeps candidate polylines
intact, records endpoint transition choices, enumerates tail paths, accepts
single-long-node routes, creates contiguous sub-combinations, and selects
non-overlapping route groups. It still needs the internal node layer, exact
split-island transition parity, planned segment ownership, matrix-volume parity,
tool normalization, and analyzer gates before it should unlock production
composite-only export.

## Config Plumbing

Add a process enum separate from strength level:

```text
enum class FiberManufacturingMode {
    PlasticPlusFiberOverlay,
    CompositeOnly,
};
```

Add a `fiber_manufacturing_mode` option to the same config family that already
contains `fiber_reinforcement_mode`, `fiber_generate_perimeters`, and
`fiber_generate_infill`.

`fiber_reinforcement_mode` remains `Light`, `Medium`, `Heavy`. It should only
control route density, layer cadence, and acceptance policy. It must not decide
whether TinManX1 is in overlay or composite-only manufacturing mode.

Routing rule:

- `plastic_plus_fiber_overlay`: keep calling the current Python planner from
  `Print::export_gcode()`.
- `composite_only`: skip the post-export Python planner and use native
  composite routes from C++.

This split should be enforced in `orcaslicer_codex_native_fiber_planner_requested`
or its replacement so a composite-only profile cannot silently regress to
overlay.

## Planner Hook

Recommended build sequence:

1. After layer perimeters and fills exist, call a native planner that consumes
   `LayerRegion` geometry and config.
2. Generate perimeter candidates from selected loop ownership.
3. Generate infill candidates from clipped layer islands/fill surfaces.
4. Build route graphs per object, island, region, and source.
5. Group adjacent routeable segments into internal composite nodes when both
   endpoint transitions are legal.
6. Split branch-heavy node ends so path search cannot hide a turn choice inside
   a multi-segment node.
7. Accept non-overlapping routes that satisfy cut-safe length and crossing
   rules.
8. Return rejected candidate segments as plastic fallback.
9. Store accepted routes and fallbacks on the owning `LayerRegion`.

The first useful hook can be a pre-export pass on `PrintObject` or `Layer`
after `Layer::make_perimeters()` and `Layer::make_fills()` have completed.
That keeps route generation close to geometry and keeps `GCode::process_layer()`
mostly responsible for ordering and emission.

Avoid building candidate geometry from emitted G-code. That repeats the current
overlay limitation.

## Emission Hook

There are two practical emission strategies:

`replace_and_group`

- Convert accepted composite routes into an internal entity-like collection and
  allow the existing `GCode::process_layer()` grouping to order them by island.
- Requires clear extruder ownership from `LayerTools` and possibly a new
  composite role.
- Best long-term integration, but touches more normal slicer machinery.

`emit_composite_beside_region`

- Keep composite routes in `LayerRegion`.
- At `src/libslic3r/GCode.cpp:5503` through `src/libslic3r/GCode.cpp:5515`,
  call a new `GCode::extrude_fiberseek_composite_routes(...)` beside
  `extrude_perimeters()` and `extrude_infill()`.
- Emit routes for the same object/island/region ordering used by normal roads.
- Use plastic fallback routes in the normal plastic path or in a parallel
  fallback emitter.

Recommended first pass: `emit_composite_beside_region`. It is easier to reason
about and easier to gate with analyzer tests. Move toward `replace_and_group`
only after the writer and preview path are stable.

Current first pass: TinManX1 emits composite routes beside the normal layer
region output, but only behind the explicit experimental environment gate. The
hook intentionally runs after normal perimeters, preserved skins/bridges/gaps,
and plastic fallback paths so accepted composite-only roads are no longer
duplicated by internal/sparse-solid plastic infill.

Composite-only cannot leave duplicate plastic roads under accepted composite
roads. The first pass must either suppress the original plastic entities that
were converted to composite, or generate composite candidates from areas that
do not already emit the same plastic road.

The suppression rule must be geometry-owned rather than string-owned:

- each composite candidate records the source perimeter/fill entity or clipped
  fill surface it came from
- accepted candidates mark their source as composite-owned
- the normal plastic emitter skips or trims only those owned source segments
- rejected candidates emit through fallback geometry so the model stays solid

This is the step that separates true `composite_only` from a larger overlay
planner.

## Writer Work

`GCodeWriter` currently knows single-extrusion-axis moves:

- `src/libslic3r/GCodeWriter.hpp:80`: `extrude_to_xy(..., dE, ...)`.
- `src/libslic3r/GCodeWriter.hpp:82`: `extrude_arc_to_xy(..., dE, ...)`.
- `src/libslic3r/GCodeWriter.cpp:933`: linear `G1 X Y E...`.
- `src/libslic3r/GCodeWriter.cpp:958`: arc `G2/G3 X Y I J E...`.

Add a FibreSeek writer path that emits route lifecycle and composite moves:

```text
fiberseek_route_start(load)
fiberseek_extrude_to_xy(point, matrix_delta, fiber_delta, p_ratio, comment)
fiberseek_cut()
fiberseek_route_end()
```

Composite CFC route output should be linear `G1` unless the machine profile
explicitly validates arc support for CFC. For now, segment curved geometry by
`fiber_max_arc_segment_length` and feed it through the linear composite writer.

The writer should own:

- `M1001` load/start.
- fiber restart.
- `V` matrix delta and `U` fiber delta.
- `P` ratio tags.
- `M2800`, `M400`, cut-distance comments.
- post-cut fiber-disabled tail.
- after-cut plastic multiplier.
- route end `M1002`.
- speed changes for start, bend, normal, finish, and tension release sections.

The current experimental writer emits the route lifecycle and linear `G1`
composite moves from `LayerRegion::fiberseek_composite_diagnostic.routes`. It
uses configured `fiber_cut_gcode`, `fiber_cut_distance`, restart length, start
length, CFC line width, feedrate percent, after-cut multiplier, and fiber
diameter. Short Rocket-sized transition spans are currently emitted as
correction travel so the writer does not lay fiber across connector geometry
until explicit segment ownership is promoted into the route data model.

Rocket's `AddCut`/`CreateFiberDelay` behavior means TinManX1's writer should
split route moves before writing the final G-code text. The baseline sequence
is: locate the active route's last composite move, calculate the cut split at
`CutDistance - NozzleContactRadiusExtended`, split that move's geometry,
plastic delta, and fiber delta proportionally, insert the cut block, then
rewrite the following delay/tail moves with fiber disabled and post-cut matrix
extrusion scaled by the profile's after-cut multiplier. A string postprocessor
that inserts `M2800` near a route end cannot reproduce this reliably.

## Material Math

Use behavior-level math from the audit:

```text
plastic_filament_area = pi * plastic_filament_diameter^2 / 4
fiber_area = pi * fiber_diameter^2 / 4
matrix_mm_per_mm = ((line_width * layer_height) - fiber_area) / plastic_filament_area
matrix_mm_per_mm *= composite_plastic_extrusion_multiplier
fiber_mm_per_mm = fiber_extrusion_percent / 100
```

Guard the calculation:

- matrix bead area must remain positive after subtracting fiber area
- line width must match the composite nozzle profile, not the plastic-only
  nozzle
- first-layer composite values should use first-layer fiber height, width, flow,
  and speed settings when present

This is one reason a post-export overlay cannot match Rocket on usage: the
normal plastic `E` road has already deposited the full bead volume.

## Preview And Summary

`GCodeProcessor` already has FibreSeek parsing work from the overlay era. The
native C++ path should make preview and summary depend on the emitted route
blocks, not on the post-export sidecar reload.

Required checks:

- route color/visibility derives from `M1001` to `M1002` blocks and `U/V/P`
  moves
- CFC material usage comes from positive `U` motion
- composite matrix usage comes from positive `V` motion on CFC routes
- plastic-only usage stays tied to normal `E` moves
- preview does not require `.native_fiber.summary.json` for composite-only

## Regression Gates

Add or extend tests so these fail loudly:

- a `composite_only` profile reaches `run_orcaslicer_codex_native_fiber_planner`
- a `composite_only` export reports `Plastic + Continuous Fiber Overlay`
- a `composite_only` export has zero `M1001` blocks on eligible heavy layers
- accepted composite routes are duplicated as full normal plastic roads
- `M1001`, `M2800`, and `M1002` counts differ
- a route crosses a hole, pocket, or separate island
- a route is shorter than the cut-safe threshold after route joining
- `G2/G3` appears inside CFC route blocks before machine validation
- preview sees fiber mass but no visible CFC path

Use the existing helpers as the first gate layer:

```bash
python3 scripts/prototype_fiberseek_composite_routes.py --self-test
python3 scripts/source-helpers/compare_fiberseek_gcode.py --self-test
python3 scripts/source-helpers/check_tinmanx1_fiber_wiring.py
python3 scripts/source-helpers/smoke_orcaslicer_codex_native_fiber_planner.py
```

`scripts/source-helpers/check_tinmanx1_fiber_wiring.py` now covers the source-level
composite-only gate: it verifies that `fiber_manufacturing_mode` exists in
`PrintConfig`, appears in the GUI/profile surface, is known to profile
generation/linting, and prevents composite-only jobs from falling through the
post-export Python overlay path.

## First Milestone

The first shippable milestone is not full Rocket parity. It is a native
composite-only slice that:

- emits `PRINTING_MODE: Composite Only`
- uses the CFC slot for accepted PETG + X-CCF routes
- co-extrudes matrix and fiber on the same `G1` route moves
- preserves plastic guard roads and plastic fallbacks
- shows CFC in preview without a post-export reload
- passes the analyzer on the coupon suite

After that milestone, compare the propeller again against Rocket. The expected
directional change is large: route count, route length, every-eligible-layer
coverage, fiber mass, and print time should move toward the Rocket baseline.
