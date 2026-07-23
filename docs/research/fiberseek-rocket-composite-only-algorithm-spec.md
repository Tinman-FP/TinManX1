# FibreSeek Composite-Only Planner Spec From Rocket/Aura 1.3.1.480

This document records the observed Rocket Slicer/Aura 1.3.1.480 behavior that matters for TinManX1 continuous-fiber planning. The Rocket source is a decompiled and partially obfuscated C# corpus, so numeric constants that remain hidden behind obfuscation are treated as observed behavior only when the surrounding code proves the relationship.

## Source Corpus

- Rocket decompile root: `work/rocket-slicer-decompiled-20260720`
- Solid fiber producer: `Aura2SlicingEngine/Aura2.EntityFiller/FiberInfillProducerSolid.cs`
- Fiber infill helper: `Aura2SlicingEngine/Aura2.Aura.Engine.Util.GeometryBasics.InfillHelper/InfillHelperFiber.cs`
- Composite block writer: `Aura2SlicingEngine/Aura2.LayersStruct.PPBlocksCollection/PPBlocksCollectionBuilder.cs`
- Graph model: `PathNode.cs`, `InfillNode.cs`, `Connection.cs`, `Combination.cs`, `SegmentPairConnection.cs`, `StartFlag.cs`, `PolygonFiber.cs`

## Planner Stages

1. Build solid-fiber line candidates from the offset printable island.

   `FiberInfillProducerSolid.GetInfills(...)` constructs `FiberInfillData` from fiber extrusion width, plastic fallback extrusion width, `InfillFSolidMinSegmentLengthUM`, a route-level minimum path length, and `InfillFSolidExtendIntoPerimetersUM`. The route-level minimum is not the same setting as the per-segment minimum: it is derived from the fiber extruder `CutDistanceUM` plus an internal allowance.

   In `InfillHelperFiber.GetSolidInfill(...)`, Rocket offsets the island by `InfillExtendsIntoPerimeters` before generating line infill (`InfillHelperFiber.cs:527`, `:540-560`). It computes the current solid angle (`:519`) and generates fiber line infill at the fiber line width (`:554`).

2. Separate and recover short candidate lines.

   Rocket separates initial lines shorter than `InfillFSolidMinSegmentLengthUM` (`InfillHelperFiber.cs:569-573`). It then attempts to prolong short lines against island segments (`:577`) before accepting only lines that are long enough (`:583-584`). This means short raw segments are not automatically discarded; they get one chance to become printable fiber.

3. Sort, orient, and graph line groups.

   Accepted candidate lines are sorted and oriented (`InfillHelperFiber.cs:587-591`). Rocket then builds `InfillNode` graph nodes from line groups and the island boundary (`:638`, `:646`). `InfillNode` stores printable line segments, graph connections, inner connector paths, and a cached node length (`InfillNode.cs:172-224`).

4. Only legal transitions become graph edges.

   `GetInfillNodes(...)` splits island geometry with the inner infill lines (`InfillHelperFiber.cs:2150-2152`), then attempts transitions between adjacent line levels (`:2217-2231`). It rejects transitions that would intersect other line segments (`:2240-2248`, `:2256-2267`). Valid transitions are stored either as an inner connection within a node or as graph connections between nodes (`:2274-2330`). `Connection` carries the from endpoint, to endpoint/node, and transition segments (`Connection.cs:17-56`).

5. Enumerate paths from tails, not from every arbitrary nearest endpoint.

   `GetPathsAndSubstitutions(...)` first splits node ends, computes each node length, maps nodes to numeric identities, and finds tails (`InfillHelperFiber.cs:2366-2417`). Tails are nodes with graph exits that represent endpoints or ambiguous two-connection turn-through cases (`:3090-3103`). `PathNode` records the node plus explicit enter/exit endpoints and an `IsIndifferent` mode for standalone nodes (`PathNode.cs:19-73`).

6. Select route combinations by covered fiber length.

   Rocket builds all paths from tails with `FindPaths(...)` (`InfillHelperFiber.cs:2419-2472`, `:3367-3668`), turns paths into `Combination` keys, and creates a combination-to-path map (`:2479`, `:2807-3082`). A candidate path is accepted only when the owned node length plus transition allowance reaches the sufficient path length (`:3070-3079`).

   `GetBestLongCombination(...)` chooses non-overlapping route combinations with the greatest total covered node length, using fewer routes as a tie-breaker (`InfillHelperFiber.cs:2524-2660`). `GetBestPaths(...)` then reconstructs full or partial paths from the selected combinations (`:2668-2799`). Unselected or insufficient material becomes plastic fallback via `GetNotEnoughLengthLines(...)` (`:2508-2510`).

7. Convert selected graph paths into printable fiber/travel segments.

   `GetPolygonForPathNode(...)` emits line segments as `SegmentType.LINE` and connector segments as `SegmentType.TRAVEL` (`InfillHelperFiber.cs:4523-4712`). `GetPolygonForPath(...)` adds connection segments between selected path nodes and throws if the required graph connection is missing (`:4714-4936`). `SegmentType.LINE` and `TRAVEL` are defined at `InfillHelperFiber.cs:15-19`.

8. Build a boundary tail at the end of each accepted route.

   For each selected path, Rocket selects the last route segment and computes a tail from the island boundary (`InfillHelperFiber.cs:664-677`). `GetTail(...)` converts island contours to segment rings, finds the closest ring segment to the route end, splits the ring if needed, orients it based on turn amount, and returns ordered boundary tail segments (`:4323-4520`). `PolygonFiber` stores both the route polygon and the tail (`PolygonFiber.cs:42-46`).

9. Emit composite G-code with an explicit lifecycle.

   Rocket's writer adds a start marker, positions ahead of the route, restarts fiber by `FiberRestartLength`, optionally dwells for adhesion, emits route segments with plastic and fiber deltas, cuts fiber, then finish-irons along the tail for `FinishIroningDistanceUM` (`PPBlocksCollectionBuilder.cs:8240-8440`). Route segments are not all equivalent: normal line segments and transition/tail lifecycle segments have different roles in the output.

## Rocket Node And Path Model

The most important planner discovery in the Rocket 1.3.1.480 decompile is that
the route solver is endpoint-stateful. It does not treat candidate roads as an
unordered cloud of near endpoints.

The graph data structures are small but very specific:

- `StartFlag` is an endpoint enum with `START` and `END`.
- `Connection` stores a source endpoint/segment, a destination
  endpoint/segment/node, and the transition segment list.
- `PathNode` stores an `InfillNode` plus explicit `Enter` and `Exit`
  endpoint/segment tuples.
- `SegmentPairConnection` keys an internal connector by from-segment/from-end
  and to-segment/to-end.
- `InfillNode` owns ordered printable line segments, external graph
  connections, an `InnerConnection` table, and cached line length.

`GetInfillNodes(...)` builds those nodes from adjacent sorted line levels. When
both the start-side and end-side transition between adjacent segments are legal
and do not cross other candidate lines, Rocket folds the new segment into the
same `InfillNode` and stores those two transitions as inner connections. When
only one endpoint transition is legal, Rocket creates or keeps separate nodes
and stores a graph `Connection` for the legal side. When no legal transition
exists, the segment becomes a standalone node. The legal transition test uses
the split island and rejects connectors crossing other infill lines, so it is a
geometric validity gate, not a visual preference.

`GetPathsAndSubstitutions(...)` then mutates the graph before selecting routes:
it calls `SplitNodeEnds(...)`, assigns each node a line-length score, finds tail
nodes, recursively enumerates paths from those tails with `FindPaths(...)`, maps
paths into combinations, and picks the best non-overlapping combination group.
The selection score is covered node length; equal-length groups prefer fewer
separate route combinations.

`FindPaths(...)` carries endpoint state through the recursion. A node entered
from one segment/end exits through the opposite side implied by the node's line
order and parity; connections are only followed when their explicit from/to
endpoint state matches the path state. `SplitNodeEnds(...)` exists because a
multi-segment node whose first or last segment has multiple graph exits must be
split so branch endpoints can be searched without hiding a decision inside the
node.

`GetPolygonForPathNode(...)` materializes a selected path node by emitting
printable lines as `SegmentType.LINE` and node-internal transitions from
`InnerConnection` as `SegmentType.TRAVEL`. `GetPolygonForPath(...)` then joins
path nodes with the selected external `Connection.Segments`; if the endpoint
exact connection is missing, Rocket throws instead of inventing a route.

TinManX1 implication: the current row-graph implementation is directionally
correct because it also stores endpoint entry state and all legal
endpoint-to-endpoint connection options. The remaining parity gap is that
TinManX1 still treats most candidates as individual route elements, while
Rocket can group adjacent line segments inside an `InfillNode` and then use
inner-connection parity during path materialization.

## TinManX1 Parity Requirements

- Treat per-segment minimum length and route-level cut-safe length separately.
- Recover/prolong short solid-fiber candidates before fallback when the island allows it.
- Create graph edges only for transitions that remain inside the printable island and do not cross other fiber lines.
- Select a non-overlapping group of routes that maximizes covered fiber length, then minimize route count as a tie-breaker.
- Preserve path orientation with explicit enter and exit endpoints.
- Preserve segment phase/type so transitions can be slowed without losing fiber continuity.
- Emit unselected, too-short, or illegal fiber candidates as plastic fallback, not ghost fiber.
- Generate connected boundary tails for selected routes so finish ironing can consume real geometry.
- Keep CCF motion independent from visualization; the viewer should show the same planned CFC geometry that the writer emits.

## External Clean-Room Slicer References

Additional non-Rocket slicer references were reviewed in
`docs/research/fiberseek-external-slicer-survey-20260721.md`.
Fractal-Cortex is useful for multidirectional chunk transforms, staged geometry
repair, per-layer parallelism, and preview/G-code source-of-truth discipline.
ThenTech CF-Slicer is useful for explicit path-role metadata and conventional
Clipper-based shell/infill clipping. Neither project appears to implement
FibreSeek-style continuous-fiber lifecycle behavior, so Rocket/Aura remains the
authoritative hardware-contract reference.

## Current TinManX1 Implementation Status

TinManX1 already has native structures for `CompositeCandidate`,
`CompositeRoute`, `CompositeRouteSegment`, `CompositeFallback`, graph options,
and `tail_segments` (`src/libslic3r/FiberseekCompositePlanner.hpp`). The
row-graph planner now builds a clean-room `CompositeNode` layer above individual
fiber candidates, emits `Normal` candidate segments plus `SlowTurn` inter-row
and node-internal connectors, and the writer emits a Rocket-like route lifecycle
with restart, optional dwell, cut, and finish-ironing tail handling
(`src/libslic3r/GCode.cpp`).

Implemented parity steps:

- Solid CFC infill now uses a Rocket-style clipped-line candidate generator.
  For `CandidateFamily::SolidInfill`, TinManX1 offsets the surface island,
  lays down straight source lines at fiber spacing, clips them against the
  printable region, and creates one `CompositeCandidate` per clipped segment.
  This keeps the production solid-fiber path close to Rocket's segment-level
  graph input instead of inheriting arbitrary connected plastic-infill
  polylines from Orca's generic filler.
- Row-graph routes now populate `CompositeRoute::tail_segments` from the selected route's final printable island boundary, so finish ironing can use real connected geometry.
- Row-graph route enumeration now starts from graph tails with bounded depth-first search before falling back to the older greedy route, which is closer to Rocket's tail-started `FindPaths(...)` behavior.
- Row-graph route candidates now carry endpoint entry state. For each adjacent pair, TinManX1 stores all legal endpoint-to-endpoint connection options, then validates that every middle candidate enters one endpoint and exits the opposite endpoint before the route is accepted. This avoids artificial internal backtracking and moves the route reconstruction closer to Rocket's `PathNode.Enter` / `PathNode.Exit` model (`InfillHelperFiber.cs:2366-2510`, `:4523-4938`).
- Row-graph selection now lifts adjacent, non-branching candidate chains into
  `CompositeNode` objects before route enumeration. Each node records its legal
  entry/exit endpoints and includes node-internal connector travel in the
  route's cut-safe score, then materializes those internal transitions as
  `SlowTurn` plastic+fiber segments. This fixes the important Rocket/Aura-style
  case where several individually short rows become a legal continuous-fiber
  path only after their real connector travel is counted.
- Short non-perimeter fiber candidates now get a pre-graph recovery pass: TinManX1 extends the candidate's own centerline across the same printable island, clips it back to that island, and uses the nearest clipped segment when it increases available fiber length. This implements the practical behavior seen in Rocket's `ProlongSegments(ref lines, island)` short-line recovery while keeping the recovery constrained to the original printable region (`InfillHelperFiber.cs:573-584`, `InfillHelperUtil.cs:511-698`).
- Rejected non-perimeter candidates now produce Rocket-style plastic substitution geometry: TinManX1 offsets the candidate to both sides by the plastic fallback extrusion width, prolongs the line across the printable island, clips it back to the island, and only falls back to the original centerline when no valid substitution survives. This mirrors Rocket's `GetSubstitutionPair(...)` behavior (`InfillHelperFiber.cs:4945-5088`) and the branches that feed rejected/short lines through substitution (`:1885-1924`, `:2038-2069`).
- The layer-region planner passes actual internal/solid plastic flow widths into candidate fallback data, so substitution spacing tracks the plastic nozzle/process instead of assuming fiber spacing.
- Surface-fill planning now has residual plastic refill for composite-only regions. Accepted composite bands and existing fallback replacement bands are offset into covered areas, those areas are subtracted from the candidate's printable island, and rectilinear plastic refill is generated in the remaining regions as `ResidualPlasticRefill` fallbacks. This follows the Rocket evidence that selected/non-selected fiber geometry feeds additional plastic handling rather than simply deleting the normal plastic infill (`InfillHelperFiber.cs:697-715`, `:2019-2038`).
- Post-selection route stitching now has a profile-controlled legal connector
  allowance. The FibreSeek solid payload currently uses 16 mm for
  `route_stitch_transition_length_mm`, up from the earlier 8 mm, because the
  propeller comparison showed Rocket producing fewer, longer route blocks while
  TinManX1 was over-segmenting. The stitcher still rejects connectors outside
  the same route scope, across separate islands, through printable void
  boundaries, or across other candidate roads. A regression test covers the
  void-crossing case directly.
- The G-code contract now emits Rocket-style startup/progress commands for
  FibreSeek exports: `SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0`,
  `SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.8`,
  `SET_TOOL_CORNER_VELOCITY T=0 SCV=1`, and
  `SET_PRINT_STATS_INFO CURRENT_LAYER=...` after each layer change.

Remaining gaps:

- The short-line recovery is intentionally conservative. Rocket mutates shared `Segment` objects through a border-segment proximity search; TinManX1 currently performs equivalent centerline prolongation by clipping an extended line to the printable island and choosing the clipped segment closest to the original midpoint.
- TinManX1 now has a clean `CompositeNode` model for simple adjacent row chains,
  including endpoint state and internal connector materialization. Rocket's
  `PathNode` can still split and route more complex multi-segment nodes when
  branches occur at the first or last segment. TinManX1's solid-CFC input is
  segment-level, which limits the practical risk for the current heavy solid
  route path, but non-solid/generic fiber patterns can still arrive as
  multi-point polylines and do not yet have Rocket's exact branch-node parity.
- Rocket's residual handling remains richer in its alternate branch: it distinguishes explicit `SegmentType.TRAVEL` corridors, returns adjusted islands to upstream plastic handling, and then substitutes too-short plastic stubs. TinManX1 now has the main residual-refill behavior, but not a full byte-for-byte clone of that travel-corridor island handoff.

## Implementation Direction

The clean-room `CompositeNode` layer is now implemented behind the existing
`CompositeCandidate` API. The next staged refinements are:

1. preserve the current Rocket-style solid clipped-line generator as the input source,
2. split any non-solid/generic multi-point fiber polylines into routeable segment candidates before graphing,
3. extend node-internal transition tables for branch connections at the first or last segment,
4. refine short fiber candidate prolongation against Rocket's exact border-threshold behavior,
5. refine residual island refill against Rocket's exact travel-corridor and stub-substitution behavior,
6. keep boundary tails attached to every accepted route and verify the viewer displays exactly the emitted CFC geometry.

G-code comparisons against Rocket should now be interpreted as stronger
algorithmic parity for the solid-CFC path: TinManX1 can emit legal
continuous-fiber lifecycle G-code and has Rocket-style solid-line generation,
endpoint continuity, node-internal connector accounting, short-line
prolongation, plastic substitution, and residual refill passes. Differences may
still appear where Rocket's full multi-segment `PathNode` branch model or its
alternate residual travel-corridor handoff changes route grouping.
