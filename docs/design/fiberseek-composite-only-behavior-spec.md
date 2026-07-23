# FibreSeek Composite-Only Behavior Spec

This spec defines the TinManX1 target behavior for FibreSeek composite-only
slicing. It is based on observed Rocket 1.3.1.480 output, observable Rocket
profile/backend behavior, TinManX1 source inspection, and public continuous
fiber toolpath literature. It intentionally avoids copying Rocket code, private
database records, or vendor preset blobs.

## Core Finding

Rocket's FibreSeek baseline is a native `Composite Only` manufacturing mode.
Accepted reinforced roads are not extra paths drawn over a completed plastic
slice. They are owned by the composite tool and carry matrix-polymer extrusion
and continuous-fiber extrusion on the same motion line.

TinManX1's current FibreSeek path is an overlay planner. It can generate valid
machine-contract G-code, but it starts after normal plastic G-code already
exists. That architecture cannot reach Rocket parity on complex parts because
it cannot replace selected plastic roads with composite roads.

## User-Facing Modes

`plastic_plus_fiber_overlay`

- Keep the current TinManX1 planner behavior.
- Use it for experiments, supplemental reinforcement, and comparison.
- Do not claim Rocket composite-only parity in this mode.

`composite_only`

- Plan reinforced perimeters and infill before G-code export.
- Convert accepted selected model roads to composite roads.
- Keep or create plastic-only roads for surfaces, supports, brim, rejected fiber
  candidates, and user-selected plastic guard roads.
- Emit native CFC toolpaths, preview, summary, and usage from this composite
  route data.

## Reference Baseline

The first validated baseline is FibreSeek Seeker 3 PETG + X-CCF:

- Composite slot: CFC tool, 0.7 mm nozzle, X-CCF/PETG.
- Plastic slot: FFF tool, 0.4 mm nozzle, PETG.
- Fiber infill enabled and fiber perimeters enabled.
- Cellular isogrid infill, 25 percent baseline density.
- Isogrid line families: base angle plus 30, 150, and 90 degrees.
- Isogrid pitch basis: `fiber_cellular_line_width * 100 / density * 3`.
- Medium/ReinForced baseline: isogrid fiber infill, 20 percent density,
  fiber perimeters enabled, outer/inner fiber counts 2/2, one plastic outer
  guard road with fiber present, 55 mm minimum perimeter length.
- Heavy/Fortified baseline: solid fiber infill, `0/90/0` angle-list cycling,
  0.7 mm solid fiber road width, 10 mm minimum solid segment length, zero
  solid-infill perimeter extension, fiber perimeters enabled, outer/inner fiber
  counts 2/2, no plastic outer guard road with fiber present, 55 mm minimum
  perimeter length.
- Light/Speedy baseline: bundled PETG/X-CCF group allows fiber but has both
  fiber infill and fiber perimeters disabled. In Rocket API coupon tests it
  emitted `Plastic Only` and zero CFC on all seven neutral coupons. Use it as
  the low-coverage behavior family; any TinManX1 light-fiber option is a
  deliberate extension rather than Rocket parity.
- Baseline infill accepted-route threshold: CFC cut distance plus 5 mm.
  This is supported by Rocket's producer using the CFC cut distance plus a
  5000 um margin constant.
- Baseline graph transition limit: fiber line width times 6. The local Rocket
  constant probe resolves the solid helper's transition multiplier to integer
  constant 68 = 6, so a 0.7 mm heavy solid fiber road permits about 4.2 mm
  between joinable candidate road ends before containment and intersection
  checks are applied.
- Medium/ReinForced session profile uses 0.8 mm fiber roads, 10 mm minimum
  solid/cellular segment length, -0.3 mm solid/cellular perimeter extension,
  20 percent cellular fill density, 135 degree cellular base angle, and
  0.24 mm macro layer height.
- Heavy/Fortified session profile uses 0.7 mm fiber roads, 10 mm minimum
  solid/cellular segment length, zero solid/cellular perimeter extension,
  `0/90/0` solid angle-list cycling, zero plastic cellular fill density for
  heavy solid composite-only, and 0.2 mm macro layer height.
- Cut distance profile field: 58 mm.
- Observed emitted cut comment in current TinMan/Rocket-compatible macros:
  54.8 mm.
- Fiber restart length: 55 mm.
- Contact radius: 1.2 mm; extended contact radius: 1.8 mm.
- Fiber min radius: 12 mm medium baseline and 10 mm heavy PETG/X-CCF baseline,
  user controlled.
- Fiber max arc segment length: 3 mm medium baseline and 4 mm heavy baseline.
- Fiber start/slow length: 15/10 mm medium baseline and 5/5 mm heavy
  baseline.
- After-cut plastic multiplier: 0.72 for medium/heavy and 0.58 for the
  bundled speedy profile family.

Treat values outside this baseline as TinMan-derived profiles until physical
machine testing validates them.

## Route Data

TinManX1 needs a route representation that survives planning, G-code writing,
preview, summary, and comparison:

`CompositeRoute`

- route id, layer id, Z, object id, island id, region id
- source: perimeter, infill, hole loop, bridge, diagnostic
- strength phase: light, medium, heavy
- tool/material slot ids
- start, cut, end, and fallback metadata
- ordered route segments
- warnings: too short, bend risk, crossing reject, open route, fallback

`CompositeSegment`

- start/end point, optional arc metadata
- geometric length
- route phase: start, slow, normal, finish, cut-delay, tail, correction
- requested speed
- plastic delta and fiber delta
- optional P ratio
- minimum-bend estimate and local turn angle

`CompositeFallback`

- rejected candidate geometry that must print as plastic
- rejection reason
- source candidate id
- replacement plastic role

## Planner Inputs

Process/profile inputs:

- manufacturing mode
- strength level: light, medium, heavy
- fiber start layer and symmetric top-stop layer count
- fiber layer cadence and layer phase
- generate fiber perimeters/infill
- fiber perimeter counts
- plastic guard road counts
- fiber infill type: solid, rhombic, isogrid, anisogrid, tetragrid
- density, angles, and layer angle phase
- fiber line width and plastic substitute line width
- cut distance, restart length, contact radius, extended contact radius
- min route length, min perimeter length, min bend radius
- start, normal, finish, correction, and tension speed limits
- start length, slow length, tension length, max arc segment length
- after-cut plastic multiplier

Geometry inputs:

- layer island polygons
- hole polygons
- selected perimeter loops
- fill surfaces
- existing extrusion role/order context

## Layer Eligibility

For a part with `N` printable layers and `fiber_start_layer = S`, fiber routes
are eligible on layers:

`S <= layer <= N - S + 1`

Strength level then applies route density and layer cadence inside that window.
Heavy may be every eligible layer. Medium and light may skip layers or use lower
route density, but they should still preserve deterministic hole/area phase
coverage across the eligible stack.

For Rocket PETG/X-CCF parity specifically, medium is the first fiber-bearing
mode. Heavy is the first `Composite Only` mode. Light parity is plastic-only
unless the user explicitly selects a TinManX1-specific light-fiber strategy.

## Candidate Generation

Perimeters:

- Preserve plastic outer surfaces according to plastic guard-road settings.
- Select inner and/or outer perimeter candidates from layer geometry.
- Reject loops shorter than the minimum perimeter length unless they can be
  joined into a valid route without crossing voids or separate islands.
- Track hole loops separately so alternating coverage can reinforce different
  holes on different eligible layers.
- Plan outer and inner/hole perimeter bands separately. Accepted perimeter
  routes own both the reinforced polygon and the post-cut tail.
- Return short or unselected perimeter candidate areas as plastic fallback
  geometry; do not leave the model hollow and do not duplicate the same road as
  both normal plastic and composite.

Infill:

- Generate ribs from fill surfaces or clipped layer islands, not emitted G-code.
- Offset eligible islands inward by the configured fiber inset before clipping.
- For isogrid, use three deterministic line families: base plus 30, 150, and
  90 degrees, with deterministic lattice phase support.
- For solid, rhombic, anisogrid, and tetragrid, keep the same graph-selection
  and fallback rules; only the candidate line families differ.

Candidate geometry must be clipped against the island-with-holes shape. A route
must never cross empty pockets, holes, or separate islands to reach length.
When a candidate is too short, TinManX1 should first try legal prolonging or
joining inside the same printable island. Any remaining unaccepted candidate
must become plastic fallback geometry rather than disappearing.
An originally short fragment may become fiber only after the final selected
route reaches the cut-safe threshold and the complete route remains inside the
printable layer polygon. Short fragments are candidates, not automatic fiber.

## Route Graph

The native planner should treat candidate segments as a route graph:

1. Preserve each clipped candidate road as a route node first. Do not replace
   the candidate set with a geometric line union as the source of truth.
2. Split the island with the candidate roads only to evaluate legal transition
   paths and crossing guards.
3. Join adjacent candidate rows into the same node when both start-side and
   end-side transitions are legal and do not cross another candidate road.
4. Add explicit start/end-flagged connections between nodes when only one
   legal transition side exists.
5. Classify nodes, tails, branch points, and closed-loop seeds.
6. Calculate route lengths from node road length plus legal connector spacing.
7. Enumerate printable paths from tails and closed-loop seeds.
8. Reject paths below the accepted cut-safe threshold, using cut distance plus
   the configured safety margin as the first baseline.
9. Connect neighboring candidate lines only when the transition remains inside
   the printable island, does not cross another candidate line, and stays
   within the transition length budget.
10. Choose non-overlapping path combinations that maximize useful coverage.
11. Return unused or too-short candidate segments as plastic fallback.

This candidate-row ownership is a material finding from Rocket 1.3.1.480. Its
solid infill helper builds `InfillNode` objects from clipped segment rows,
tracks `StartFlag.START` and `StartFlag.END` on connections, then chooses
non-overlapping `Combination` sets by node index. A dense line union can
over-split coincident/collinear rows into thousands of graph edges and produce
misleading route statistics. TinManX1 should use geometric noding as a
containment/crossing check, not as the route-identity layer.

Candidate joining is scoped to one layer, object, region, island, and candidate
family. Segments from separate printable islands must never be joined just to
reach the cut-safe threshold; if each island cannot produce a legal cut-safe
route, those candidates stay plastic fallback.

The accepted route score must favor valid printable coverage over raw fiber
quantity. It is better to leave a candidate as plastic fallback than to connect
across a void, duplicate a road as both plastic and composite, or create a route
that cannot be cut and tailed safely.

Clean-room selector target:

1. Group clipped candidates into ordered line levels for one printable island.
2. Create an initial node for every candidate in the first level.
3. For each later level, compare each new candidate against the previous level.
4. Compute legal start-side and end-side transition candidates inside the split
   island, bounded by the transition-length budget.
5. Reject a transition if it crosses another candidate road in the previous or
   current level, except for the two endpoint roads being connected.
6. If both start and end transitions are legal, merge the new candidate into
   the previous candidate's node and store both internal transition segments.
7. If only one side is legal, create or reuse a new node for the candidate and
   add mirrored start/end-flagged graph connections between the two nodes.
8. If no side is legal, keep the candidate as its own node.
9. Split multi-line node ends where needed so graph traversal has stable start
   and end handles.
10. Assign each node a stable index and node length from its owned candidate
   roads.
11. Enumerate paths from tail nodes using start/end flags, node parity, and
   cycle guards so the same node is not reused in a path.
12. Convert every full path above the cut-safe threshold into a combination of
   node indexes.
13. Also accept any single node whose owned road length reaches the cut-safe
   threshold.
14. From longer paths, create additional sub-combinations when a contiguous
   subset still reaches the cut-safe threshold.
15. Sort combinations by descending node count, build non-overlapping groups,
   then choose the group with the greatest total accepted node length; on ties,
   prefer fewer separate combinations/routes.
16. Emit accepted paths by walking node roads and connector segments in order.
17. Return all unselected node roads as plastic fallback/stub geometry.

Route length for acceptance is not just direct XY road length. For multi-road
nodes, count the owned road lengths plus the connector spacing implied between
the node's internal roads. This avoids rejecting dense but mechanically
printable stitched rows merely because the connection moves are represented
separately from the candidate road identity.

This route graph is the key missing part in the current TinManX1 overlay
planner. It is also where TinManX1 can improve on Rocket by applying the
alternating hole/region phase more deliberately.

The first Rocket parity target is route ownership, not route cosmetics. For the
propeller benchmark, Rocket emits mostly long open composite roads, while the
current TinManX1 overlay output emits mostly closed loops. A valid
composite-only implementation must therefore be able to select long open
perimeter/infill composite roads and preserve their cut/tail semantics. It
should still support closed loops where geometry calls for them, but a mostly
closed-loop output is an overlay signature and should fail parity review.

The neutral coupon matrix confirms this beyond the propeller benchmark. Across
seven Z0 coupons, Rocket's medium and heavy fiber-bearing outputs used open
paths almost exclusively; near-closed paths appeared only in a few heavy cases,
and closed loops did not dominate any fiber-bearing coupon.

## Bend, Speed, And Tension

Minimum bend radius remains user controlled until real FibreSeek testing maps
speed, fiber type, and route quality. The planner should still compute local
turn severity and slow segments near high-curvature corners.

Implementation requirements:

- Segment arcs or curves by `fiber_max_arc_segment_length`.
- Force CFC output to G1 unless a machine profile explicitly validates arc
  commands for that controller.
- Use start, normal, and finish speed bands.
- Reduce speed around bends based on local turn angle and min-radius setting.
- Split moves when needed to transition into and out of slow sections.
- Apply fiber tension lead/release behavior as route phases, not as detached
  postprocessor text.
- Emit warnings for high-risk turns, and reserve hard rejection for routes that
  cross voids, violate cut-safe length, or exceed a machine-tested physical
  limit.

## Route Lifecycle

A composite route has this logical lifecycle:

1. Move to route start with the configured CFC tool.
2. Prime/restart fiber if required.
3. Emit route start metadata.
4. Print start/slow lead-in.
5. Print normal composite segments with matrix and fiber deltas.
6. Apply bend-based speed adjustments as needed.
7. Split the move stream at the cut-delay distance.
8. Emit the cut command.
9. Continue the tail with fiber disabled where mechanically required.
10. Scale post-cut plastic extrusion by the configured after-cut multiplier.
11. Emit finish/correction travel and route end metadata.

The cut-delay step must own exact split points. A text-only postprocessor that
inserts a cut command near the end of an existing route is not sufficient.

Rocket's writer behavior provides the baseline:

- Find the latest composite move in the active reinforced route.
- Measure backward from that move stream by
  `CutDistance - NozzleContactRadiusExtended`.
- Split the target move at the exact distance from its start.
- Split plastic and fiber deltas proportionally by XY segment length.
- Insert the configured cut block between the two split move fragments.
- Walk the following delay/tail span and disable fiber where required.
- Scale post-cut matrix extrusion by `FiberAfterCutExtrusionMultP`.

The tail is part of the accepted route object. It must be planned with the
same printable-island containment rules as the reinforced polygon, then emitted
after cut at the route's finish/correction speed policy.

## Writer Contract

The G-code writer must support composite moves with two extrusion deltas:

- matrix polymer delta
- continuous fiber delta

For composite-tool moves, the writer must emit both axes when both deltas are
positive, and include the machine-required ratio tag when applicable. Plastic
only moves keep the normal single-material path.

Balanced command contract:

- every reinforced route start has a matching route end
- every cut belongs to an active reinforced route
- route start, cut, tail, and end are in order
- tool ownership matches the profile slot contract
- preview and material summary use native route data

## Validation

Minimum validation before enabling composite-only for normal use:

- Analyzer passes balanced route start/cut/end checks.
- Composite-only mode is identified as composite-only by the analyzer.
- Fiber appears on expected eligible Z buckets.
- U-positive fiber-road XY length is in the same order of magnitude as the
  validated Rocket baseline for the same geometry and profile.
- V-positive matrix-road XY length is tracked separately so post-cut matrix-only
  tail motion does not masquerade as continuous fiber placement.
- Route length percentiles match the selected cut-safe policy.
- Route-shape distributions are plausible for the selected strategy; a Rocket
  composite-only comparison dominated by open composite roads must not be
  replaced by mostly closed overlay loops.
- No route crosses holes, pockets, or separate islands.
- Rejected candidate segments are visible as plastic fallback.
- Preview shows CFC path location from native route data.
- Material summary reports CFC use from native route data.
- PETG + X-CCF propeller comparison is within the agreed coverage envelope
  against the Rocket baseline before widening to other materials.

Coupon validation set:

- long rectangular plate
- single-hole plate
- multi-hole plate
- minimum-length bar ladder
- bend-radius hole ladder
- gear with six holes
- separate-islands guard

## Implementation Order

1. Add feature plumbing for `composite_only` without changing existing overlay
   behavior.
2. Add native data containers and a diagnostic sidecar exporter.
3. Generate infill candidate ribs from layer geometry.
4. Add route graph selection and plastic fallback.
5. Add perimeter route ownership.
6. Add composite writer support with separate matrix/fiber deltas.
7. Wire preview, usage summary, and analyzer gates.
8. Run coupon and propeller parity sweeps.

## Public References

- https://arxiv.org/abs/2112.12057
- https://arxiv.org/abs/2404.11404
- https://arxiv.org/abs/1908.07452
- https://pdfs.semanticscholar.org/9ad2/b146a625102b239574114bd2f1ddac263fe0.pdf
- https://www.ddmlab.ru/wp-content/uploads/2019/02/Aura-User-Manual.pdf
- https://github.com/Ultimaker/Cura/issues/14483
- https://github.com/prusa3d/PrusaSlicer/issues/9609
