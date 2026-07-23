# FibreSeek Rocket Backend Notes

This note records clean-room observations from Rocket Slicer 1.3.1.480 backend
inspection and reference G-code comparison. It is intended to guide TinManX1's
native FibreSeek composite-only implementation without copying Rocket code or
profile blobs.

## Backend Build Fingerprint

Rocket's local backend reports algorithm version `1.3.1.480+e3a2b29`, built
from a July 2026 commit labelled `fix: fiber out and overlap`. The local app
bundle reports Rocket Slicer `1.3.2.637`, but the algorithm DLLs and profile
database inspected here are the 1.3.1.480 planning target.

## Slice API Contract

Rocket's Mac package runs an ASP.NET monolith, not a simple slicer CLI. The
running process observed during this audit was:

```text
Aura.Monolith.API --ELECTRON_USER_DATA=/Applications/Rocket Slicer.app/Contents/Resources/backend/resources --urls=http://127.0.0.1:62865
```

The route that starts slicing is registered by `Aura.GUI.Web`:

```text
POST /api/slice/generate
```

The controller accepts a `RequestGenerate` payload with:

- `companyId`, `userId`, `projectId`, and `projectPath`
- `printMode` (`Speedy`, `ReinForced`, or `Fortified`; blank defaults to
  `FORTIFIED`)
- enabled `parts`
- `slotExtruderMaterials`
- one `settingsSet`
- the active `plastics`, `composites`, `extruderPs`, `extruderCs`, `slots`,
  `printer`, and `profile`

`GenerateHandler` resets `*Over` overrides, maps the request into Aura2's
`SessionModel`, parses `printMode` into `PrintModes`, constructs
`SessionSet(sessionModel, Edition.OPEN, printMode)`, and calls
`SlicingEngine.GenerateAsync()`. The result is serialized as
`result.json.gz` under `projectPath` and exposed through `/files/...`.

This gives TinManX1 a repeatable Rocket validation path: build clean
`RequestGenerate` payloads from Rocket project snapshots and preset rows, post
them to the local backend, then compare the resulting compressed slice data or
exported G-code. It also confirms that Light/Medium/Heavy in TinManX1 should
continue mapping to Rocket's `Speedy`/`ReinForced`/`Fortified` behavior
families even though the UI labels are sanitized.

`scripts/rocket_fiberseek_slice_harness.py` now exercises this path. It builds
payloads from the local Rocket project snapshot, discovers the running monolith
port, posts generated STL coupons, and extracts Rocket's response JSON, G-code,
and resolved session profile from `result.json.gz`. The first corrected
21-slice coupon matrix completed without Rocket API failures after normalizing
the coupon models to sit on the build plate.

## Shipped FibreSeeker Baseline Profiles

The bundled Rocket resources contain a FibreSeeker 3 printer with two slots,
one FFF plastic extruder, and one CFC composite extruder. The current shipped
CFC machine constants are:

| Setting | Rocket value |
| --- | ---: |
| CFC nozzle diameter | 0.7 mm |
| Cut distance | 58 mm |
| Fiber restart length | 55 mm |
| Nozzle contact radius | 1.2 mm |
| Extended contact radius | 1.8 mm |

The saved default project uses the profile group
`PETG 0.2mm --- CFC PETG + X-CCF --- PETG`. Its three strength profiles differ
materially:

| Field | Speedy | ReinForced | Fortified |
| --- | ---: | ---: | ---: |
| Macro layer height | 0.2 | 0.24 | 0.2 |
| Generate fiber infill | false | true | true |
| Generate fiber perimeters | false | true | true |
| Fiber infill type | 2 | 2 | 0 |
| Isogrid density | 25% | 20% | 25% |
| Isogrid angle | 0 deg | 0 deg | 45 deg |
| Solid fiber EW | 0.68 mm | 0.8 mm | 0.7 mm |
| Fiber inward extension | -0.8 mm | -0.3 mm | 0 mm |
| Fiber outer/inner counts | 1 / 1 | 2 / 2 | 2 / 2 |
| Plastic outer guard with fiber | 2 | 1 | 0 |
| Minimum perimeter length | 20 mm | 55 mm | 55 mm |
| Fiber min radius | 12 mm | 12 mm | 10 mm |
| Fiber start/slow length | 15 / 5 mm | 15 / 10 mm | 5 / 5 mm |
| Max arc segment length | 3 mm | 3 mm | 4 mm |
| After-cut plastic multiplier | 0.58 | 0.72 | 0.72 |
| Normal fiber max speed | 30 mm/s | 30 mm/s | 40 mm/s |

This is why Rocket modes cannot be modeled as a single path set with a scalar
fiber multiplier. They change route families, perimeter ownership, guard-road
counts, layer geometry, cut-tail parameters, and speed/bend behavior.

The Rocket API coupon matrix showed the same split in emitted output:

| Rocket profile | Observed coupon print mode | CFC behavior |
| --- | --- | --- |
| Speedy | Plastic Only | zero M1001/cut/end blocks on all seven coupons |
| ReinForced | Plastic and Composite | CFC routes on selected layers, plus plastic roads |
| Fortified | Composite Only | dense CFC road ownership across nearly all eligible layers |

All fiber-bearing coupon outputs used the emitted cut comment
`;CUT DISTANCE 54.8`.

## Composite Extrusion Model

Rocket calculates composite-tool motion with independent plastic-matrix and
fiber deltas.

Observed formula family:

```text
plastic_filament_area = pi * plastic_filament_diameter^2 / 4
fiber_area = pi * fiber_diameter^2 / 4
plastic_mm_per_mm = ((line_width * layer_height) - fiber_area) / plastic_filament_area
plastic_mm_per_mm *= composite_plastic_extrusion_multiplier
fiber_mm_per_mm = fiber_extrusion_percent / 100
```

For normal plastic tools, Rocket uses:

```text
plastic_mm_per_mm = (line_width * layer_height) / plastic_filament_area
plastic_mm_per_mm *= plastic_extrusion_multiplier
```

Key implications for TinManX1:

- Composite roads are not simply plastic roads plus a fiber overlay.
- Composite matrix extrusion must subtract the physical fiber cross-section
  from the deposited bead volume.
- Continuous fiber usage is route length scaled by the profile's fiber
  extrusion percentage.
- First-layer/fiber-first-layer variants use the same formula family with
  their own effective layer heights and multipliers.

## Route Ownership

Rocket passes `filamentPlasticPerMM` and `fiberPerMM` into composite perimeter
and infill block builders. Those builders emit reinforced routes as native
composite moves owned by the CFC slot.

The reference Rocket propeller G-code confirms this:

```text
M1001 L120
G1 F1500 U55 ; Extrude restart
G1 X161.790 Y151.984 V0.04924 U1.20100 P0.041 F120
...
M2800
M400
M1002
```

The important detail is the combined move: the same `G1` line carries matrix
polymer (`V`), continuous fiber (`U`), and the `P` plastic/fiber ratio. TinManX1
already speaks this machine vocabulary in overlay mode, but composite-only
needs to create those moves from slicer geometry before normal plastic G-code
is finalized.

## Cellular Infill Rules

The observed PETG/X-CCF baseline uses cellular isogrid at 25 percent density,
0.68 mm fiber cellular line width, and 0.8 mm inward extension relative to
perimeters. Rocket offsets eligible island geometry inward, clips line families
against island-with-holes geometry, and then runs the clipped segments through
a path/node solver.

Observed behavior:

- Cellular isogrid uses three line families at the base orientation plus 30,
  150, and 90 degrees.
- The observed isogrid pitch expression is
  `fiber_cellular_line_width * 100 / density * 3`.
- The third isogrid family includes a half-cell style phase offset, consistent
  with the staggered triangular lattice visible in Rocket output.
- Candidate segments are clipped against holes, pockets, and separate islands.
- Route acceptance for cellular/solid infill is based on an accepted path
  threshold derived from the CFC cut distance plus a 5 mm margin. In the
  decompiled producer this is the CFC cut distance plus integer constant 105;
  the local constant probe resolves that integer constant to 5000 um.
- The same constant probe resolves integer constant 68 to 6. Rocket's solid
  helper uses this as `maxTransitionLength = fiber_line_width_um * 6`, so the
  PETG/X-CCF heavy baseline uses about 4.2 mm for 0.7 mm solid fiber roads.
- Plastic fallback stubs are widened from fiber centerlines by
  `fiber_line_width / 2 + 20 um` before being intersected back with printable
  regions. Fallback is therefore real replacement polymer geometry, not only a
  warning or preview artifact.
- The isogrid producer uses the solid-fiber minimum segment length setting in
  the baseline path, while rhombic, anisogrid, and tetragrid use the cellular
  minimum segment length setting.
- Segments not included in accepted fiber route combinations are returned as
  non-fiber fallback geometry instead of being silently ignored.

The route solver first splits candidate segments into graph nodes, finds tail
nodes, recursively enumerates candidate paths, maps those paths into
non-overlapping node combinations, and then selects the longest useful
combination. For multi-line nodes, the effective threshold score includes the
candidate segment lengths plus an allowance of one line spacing per additional
line in the node. TinManX1's current row-graph prototype preserves one clipped
row per node, so it uses the same spacing allowance as an explicit clean-room
proxy when a run of adjacent rows is promoted into one cut-safe path.

This supports a TinManX1 implementation based on a native route graph with
explicit accepted routes and plastic fallback routes.

## Route Solver Order

The decompiled `InfillHelperFiber` control flow is obfuscated but readable
enough to establish the behavior sequence:

1. Short generated segments are separated from long candidates.
2. Short candidates are prolonged against the printable island boundary before
   the graph pass.
3. Remaining candidates are oriented and sorted into line families.
4. Intersections and branch/end nodes are converted into `InfillNode` graph
   nodes with a maximum transition length tied to fiber line width.
5. Multi-segment node ends are split when branch connections occur at the first
   or last segment of a node.
6. Node lengths are calculated from the full line sequence owned by each node.
7. Tail nodes seed recursive path enumeration.
8. Enumerated paths are converted into node combinations and accepted only when
   the sum of node lengths plus the multi-line node spacing allowance reaches
   the cut-safe threshold.
9. Single-node routes are also accepted when that node alone reaches the same
   threshold.
10. Additional sub-combinations of long paths are considered as contiguous
    path windows. `Combination.GetParts()` starts with path length minus one,
    creates every contiguous window of that size, then decrements the window
    size until the lower bound. These sub-combinations are marked as partial
    paths and later trimmed between the first and last selected node.
11. Candidate combinations are sorted by descending node count. For each seed,
    Rocket greedily appends later combinations that do not overlap the seed or
    any already appended combination. Duplicate combination groups are removed
    with order-insensitive comparers.
12. The winning group is the group with the greatest total owned-node length.
    If two groups cover the same owned length, Rocket chooses the group with
    fewer separate route combinations.
13. Selected graph paths become fiber polygons plus route tails. In path
    materialization, node-internal transitions are inserted from
    `InnerConnection`; between nodes, the selected `Connection.Segments` are
    inserted as transition moves.
14. Unselected nodes become plastic substitution stubs, are prolonged where
    needed, and are offset back into printable polymer fallback geometry.

The composite polygon writer then treats those route-owned transition segments
as extrusion segments. In the 1.3.1.480 decompile, the reinforced polygon loop
calculates `extrusionDeltaPlastic = filamentPerMM * segment.Length *
segment.ExtrusionWidthCorrection` and `extrusionDeltaFiber = fiberPerMM *
segment.Length` before calling `AddMove(...)` for each polygon segment. That
means a short selected bridge is not automatically a travel move; any travel-only
behavior must be represented explicitly by the planner rather than inferred from
segment length in the G-code writer.

The exact tail rule is also relevant. Rocket starts from nodes with at least
one connection, then keeps degree-one nodes plus nodes with the special
two-connection/same-source-segment shape used for branch ends after node-end
splitting. It does not use every connected node as a path seed.

This makes the critical TinManX1 rule explicit: insufficient fiber candidates
must not simply disappear. They either become part of a legal joined fiber path
or return to the plastic model as fallback.

### Clean-Room Source Map

These Rocket 1.3.1.480 line anchors are used only as behavior references:

| Behavior Area | Rocket Anchor |
| --- | --- |
| Solid fiber infill entry points | `InfillHelperFiber.cs`, `GetSolidInfill`, lines 463 and 495 |
| Rhombic fiber infill entry points | `InfillHelperFiber.cs`, `GetRombicInfill`, lines 835 and 867 |
| Isogrid fiber infill entry points | `InfillHelperFiber.cs`, `GetIsogridInfill`, lines 1031 and 1063 |
| Anisogrid fiber infill entry points | `InfillHelperFiber.cs`, `GetAnisogridInfill`, lines 1269 and 1301 |
| Tetragrid fiber infill entry points | `InfillHelperFiber.cs`, `GetTetragridInfill`, lines 1521 and 1553 |
| Shared cellular/solid helper | `InfillHelperFiber.cs`, private helper beginning around line 1822 |
| Infill node graph build | `InfillHelperFiber.cs`, `GetInfillNodes`, line 2150 |
| Path materialization and transitions | `InfillHelperFiber.cs`, `GetPolygonForPathNode`, line 4523; `GetPolygonForPath`, line 4714 |
| Composite polygon extrusion deltas | `PPBlocksCollectionBuilder.cs`, reinforced polygon loop around lines 8116-8121 |
| Path/fallback selector | `InfillHelperFiber.cs`, `GetPathsAndSubstitutions`, line 2366 |
| Best non-overlapping combinations | `InfillHelperFiber.cs`, `GetBestLongCombination`, line 2524 |
| Accepted graph paths | `InfillHelperFiber.cs`, `GetBestPaths`, line 2668 |
| Combination-to-path map | `InfillHelperFiber.cs`, `CreateDictCombinationToPath`, lines 2807 and 2986 |
| Tail discovery | `InfillHelperFiber.cs`, `FindTails`, line 3090 |
| Rejected-node plastic stubs | `InfillHelperFiber.cs`, `GetNotEnoughLengthLines`, line 3106 |
| Recursive path enumeration | `InfillHelperFiber.cs`, `FindPaths`, line 3367 |
| Node-end splitting | `InfillHelperFiber.cs`, `SplitNodeEnds`, line 3677 |
| Tail construction | `InfillHelperFiber.cs`, `GetTail`, line 4323 |
| Path-to-polygon conversion | `InfillHelperFiber.cs`, `GetPolygonForPath`, line 4714 |
| Plastic substitution pair | `InfillHelperFiber.cs`, `GetSubstitutionPair`, line 4945 |
| Inset fiber perimeter planner | `InsetFiberHelper.cs`, `GeneratePolygonByTree`, line 1264 |
| Outer fiber perimeter calculation | `InsetFiberHelper.cs`, `CalcInsetOuters`, line 1603 |
| Inner/hole fiber perimeter calculation | `InsetFiberHelper.cs`, `CalcInsetInners`, line 1797 |
| Composite infill block emitter | `PPBlocksCollectionBuilder.cs`, `AddMovePolygons(ISEMPPComposite, List<PolygonFiber>...)`, line 9269 |
| Composite perimeter block emitter | `PPBlocksCollectionBuilder.cs`, `AddMovePolygonsForPerimeter(ISEMPPComposite, List<PolygonFiber>...)`, line 9294 |
| Single composite perimeter route emitter | `PPBlocksCollectionBuilder.cs`, `AddMovePolygonForPerimeter`, line 8240 |
| Fiber move split helper | `PPBlocksBuilderHelper.cs`, `ConvertMoveIntoTwoFiber`, line 571 |
| Fiber tension split helper | `PPBlocksBuilderHelper.cs`, `ConvertMoveIntoThree`, line 876 |
| Fiber delay/cut helper | `PPBlocksBuilderHelper.cs`, `CreateFiberDelay`, line 1183 |

## Fiber Perimeter Rules

Rocket's perimeter reinforcement is handled by separate `InsetXFiber` and
`InsetFiberHelper` code paths, not by the cellular infill producer. The high
level behavior is:

1. Build offset inner and outer inset candidate bands from the current island
   and its holes.
2. Convert the bands into a tree collection.
3. Ask each tree for best paths using both `MinPerimeterLength` and the
   extended cut-safe length.
4. Process the selected paths with layer index, Z, extrusion width, cut-safe
   length, marker data, hole/non-hole role, and island boundary.
5. Keep only paths that reach the extended cut-safe length.
6. Convert accepted paths into `PolygonFiber` objects containing both the
   reinforced polygon and a tail.
7. Return short/unselected path areas as plastic substitution geometry.

Outer and inner fiber perimeters are planned separately. Outer routes are
generated with reversed path direction, while inner/hole routes are generated
with the opposite direction. Inner handling also separates same-orientation and
opposite-orientation bands so hole perimeters can be routed without merging
through unsupported voids.

The CFC perimeter emitter uses `AddMovePolygonsForPerimeter()` and ultimately
`AddMovePolygonForPerimeter(slotC, polygon, tail, filamentPerMM, fiberPerMM,
speedCoeff)`. It starts a reinforced polygon, moves to the start, restarts
fiber, emits composite moves carrying plastic and fiber deltas, cuts, then
walks the stored tail at finish speed. This is materially different from
overlay output because the perimeter road is owned by the CFC slot from the
start.

The local Rocket 1.3.1.480 decompile places this behavior in
`PPBlocksCollectionBuilder.cs`. The composite perimeter overload starts at line
8240. The observable source sequence is: create a reinforced-polygon start
block around lines 8282 and 8305, restart/feed fiber around line 8309, emit
`AddMove(slotC, ..., extrusionDeltaPlastic, extrusionDeltaFiber, ...)` for each
polygon segment around lines 8327 through 8332, apply the cut preparation and
`AddCut(slotC)` around lines 8335 through 8339, run correction/cut splitting
around line 8345, then iterate the stored `tail` list around lines 8411 through
8424 before creating the end polygon around line 8431.

Plastic inset emitters are fiber-aware too. When fiber perimeters or fiber
infill are active, Rocket switches to alternate plastic extrusion-per-mm
variants for first/fiber-first layers and normal layers. That is further
evidence that composite-only has to coordinate matrix volume, fiber volume, and
plastic fallback during slicing rather than after G-code export.

## Cut And Tail Lifecycle

Rocket does not append a cut command by text-searching near the end of a route.
The route builder owns the lifecycle:

1. Move to the route start.
2. Feed restart fiber (`U55` in the observed baseline).
3. Emit `M1001` route-start metadata.
4. Print composite start/normal/finish moves with separate matrix and fiber
   deltas.
5. Split a move exactly where the configured cut-delay distance is reached.
6. Emit the cutter command (`M2800`) and synchronization.
7. Continue the route tail with fiber disabled where required.
8. Scale post-cut matrix extrusion by the after-cut plastic multiplier.
9. Emit route-end metadata (`M1002`).

TinManX1 should model this as route semantics in the writer. A postprocessor
that inserts cut text after G-code is generated will not be reliable enough for
composite-only parity.

TinManX1's first native CFC emitter now mirrors this command vocabulary behind
an explicit development gate. It writes `M1001` route metadata, `U`/`V`/`P`
composite moves, configured cut G-code, post-cut matrix-only tail moves, and
`M1002` from native route diagnostics. Accepted C++ routes now pass explicit
segment ownership into the writer, so row-graph connectors no longer depend on a
short-polyline heuristic. It is not treated as Rocket parity yet because Rocket's
exact phase-speed behavior, split-island validation, and matrix-flow correction
still need to be promoted into the C++ data model.

## Bend, Speed, And Tension Behavior

Rocket does not appear to use the user-selected bend radius as a simple hard
delete rule for fiber geometry. The reinforced-route writer inspects the turn
amount between consecutive move segments, combines that with the configured
fiber minimum radius and maximum arc-segment length, and derives a reduced
speed for the affected move. The result is clamped against the configured
start, normal, and finish minimum speeds.

The same pass can split a move into two sections around a speed transition, or
into three sections for fiber-tension lead/normal/release behavior. The split
segments preserve the route but adjust fiber feed on the lead and release
sections. This explains why Rocket can keep fiber coverage in places where an
overly literal bend-radius rejection would remove it.

The same decompiled file shows the speed/tension pass beginning around line
8793. It loads start/normal/finish min/max speeds, max arc segment length, bend
radius, fiber start length, tension length, and slow length around lines 8828
through 8877. It calculates turn amount between adjacent move segments around
lines 8918 through 8924, can split a move into two around lines 8938 through
8954, and can split a longer move into three tension segments around lines 9007
through 9021. `PPBlocksBuilderHelper.cs` scales post-cut plastic extrusion by
`FiberAfterCutExtrusionMultP` around line 1295 and splits at the cut-distance
point around lines 1302 through 1304.

TinManX1 should therefore treat bend radius as a motion-quality and warning
input first:

- score turn severity on every composite segment junction
- slow sharp turns using the selected fiber radius and speed bands
- segment arcs/curves by the maximum fiber arc segment length
- flag high-risk geometry for the user and analyzer
- reserve hard rejection for routes that cross voids, violate cut-safe length,
  or exceed a machine-tested physical limit

## Propeller Reference Delta

The latest Rocket/TinManX1 propeller comparison shows that TinManX1 is safe but
not yet equivalent:

| Metric | Rocket | TinManX1 |
| --- | ---: | ---: |
| Mode | Composite Only | Plastic + CFC Overlay |
| M1001 route starts | 3069 | 821 |
| Reconstructed route blocks | 3069 | 821 |
| Route block XY p50 / p90 | 684 / 2095 mm | 115 / 1257 mm |
| U-positive fiber-road XY total | 2,042,011 mm | 179,663 mm |
| V-positive matrix-road XY total | 2,189,651 mm | 211,176 mm |
| Route shape classes | 2976 open; 59 near-closed; 27 closed; 7 line/tail | 660 closed; 161 line/tail |
| Route block move-count p50 / p90 | 202 / 944 | 96 / 638 |
| Parsed layers with fiber routes | 314 | 153 |
| Z levels with fiber routes | 314 | 154 |
| M1001 load total | 2,457,466 mm | 373,359 mm |
| Continuous fiber summary | 233.6 g | 33.44 g |
| Estimated print time | 128h 38m | 13h 54m |

That is why profile tuning has hit a ceiling. TinManX1 must move from overlay
reinforcement to native composite-road ownership to match or exceed Rocket's
continuous-fiber utilization.

## TinManX1 Design Requirements From This Evidence

- Add `composite_only` as a manufacturing mode separate from the existing
  overlay mode.
- Add first-class composite route data before G-code export.
- Generate candidate fiber perimeters and infill from layer geometry, not from
  emitted G-code.
- Clip candidates against islands and holes before route joining.
- Accept/reject routes using minimum length, bend, and crossing constraints.
- Emit rejected geometry as plastic fallback.
- Extend the G-code writer to output composite moves with separate matrix and
  fiber deltas plus the required `P` ratio.
- Drive preview, material summaries, and analyzer validation from the same
  route data.
