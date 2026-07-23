# FibreSeek Composite Route Prototype

This note records the first neutral-geometry route-planning prototype for the
TinManX1 FibreSeek composite-only effort. The prototype lives at
`scripts/prototype_fiberseek_composite_routes.py`.

## Purpose

The current TinManX1 FibreSeek planner works from already-emitted plastic
G-code. The prototype works from layer-like 2D polygons instead. It is a
clean-room research harness for the route-selection behavior needed by native
composite-only slicing:

- generate candidate ribs from printable island geometry
- clip candidates against holes and separate islands
- test both noded-intersection graphs and Rocket-style candidate-row graphs
- produce long non-overlapping printable paths over existing candidate geometry
- report short rejected components as plastic fallback candidates
- phase the rib lattice across layers to vary hole/feature coverage
- report hole-adjacent coverage for alternating-layer diagnostics
- report bend-radius risk points for speed/quality planning
- create visual and JSON diagnostics for repeatable comparison

It does not emit production G-code and it does not claim Rocket equivalence.

## Algorithm Sketch

1. Build a neutral coupon polygon.
2. Offset the polygon inward by the fiber inset.
3. Generate candidate line families for the selected pattern.
4. Clip each line to the printable polygon-with-holes.
5. Label clipped pieces shorter than the configured minimum segment length as
   short candidates, but keep them available for route joining or plastic
   fallback.
6. Select the route graph strategy:
   - `greedy` / `euler`: use a noded line union to split intersections and
     build a graph from noded candidate edges.
   - `row_graph`: preserve clipped candidate rows as node identities, then
     connect nearby row endpoints with legal transition edges and run a
     Rocket-style path/combination selector.
7. Build graph components from the selected strategy.
8. For each connected component:
   - `greedy` scores terminal-to-terminal paths by new hole coverage, total
     useful coverage, route length, and bend risk
   - `row_graph` enumerates terminal paths, adds contiguous path windows, keeps
     single-row routes that already clear the threshold, and selects the best
     non-overlapping combination group by owned-road coverage
   - mark unselected or capped leftovers as plastic fallback
9. Estimate available bend radius at each routed turn and count high-risk
   points against the configured bend-radius target.
10. Measure which hole boundaries lie within the configured coverage distance of
   accepted routes.

This is intentionally conservative for the separate-islands case: components
are planned independently and no route may bridge empty space.

## Latest Scored Isogrid Run

Command:

```bash
python3 scripts/prototype_fiberseek_composite_routes.py --coupon all --pattern isogrid --output-dir work/rocket-algorithm-1.3.1.480-research/prototype-routes-scored --no-png
```

Settings:

| Setting | Value |
| --- | ---: |
| Pattern | isogrid |
| Density | 25% |
| Fiber line width | 0.68 mm |
| Inset | 0.8 mm |
| Minimum segment length | 10 mm |
| Minimum route length | 65 mm |
| Minimum bend radius target | 12 mm |
| Derived spacing | 8.16 mm |
| Route strategy | greedy scored path selection |
| Terminal candidate cap | 140 |
| Route cap per component | 32 |

Results:

| Coupon | Candidates | Components | Accepted routes | Fallback routes | Accepted length | Fallback length | Hole coverage | Bend-risk points |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rect plate | 27 | 1 | 9 | 16 | 1153.804 mm | 241.322 mm | 0 / 0 | 39 |
| Single-hole plate | 42 | 1 | 14 | 18 | 1413.592 mm | 524.392 mm | 1 / 1 | 68 |
| Multi-hole plate | 72 | 1 | 19 | 28 | 1974.815 mm | 1007.375 mm | 6 / 6 | 118 |
| Min-length bars | 5 | 5 | 1 | 4 | 88.400 mm | 218.600 mm | 0 / 0 | 0 |
| Bend-radius ladder | 70 | 1 | 23 | 35 | 2655.814 mm | 660.263 mm | 3 / 3 | 153 |
| Gear with six holes | 54 | 1 | 9 | 18 | 842.845 mm | 886.610 mm | 7 / 7 | 50 |
| Separate islands | 34 | 2 | 3 | 4 | 196.040 mm | 1131.154 mm | 0 / 0 | 12 |

## Findings

The separate-islands coupon stayed split by graph component. That is the
correct guardrail: the planner must not stitch across air just to hit a minimum
length. The scored selector accepts only long legal paths and leaves the rest as
fallback instead of forcing full-component traversal.

The min-length bar coupon now correctly rejects four short components when the
route threshold is 65 mm. The longest bar produces one accepted route. This is
useful because it separates true printable route length from artificial
out-and-back length.

The earlier Euler-style route extraction covered aggressively, but it created
large amounts of duplicated edge travel and 180-degree backtracking. The scored
selector is a better production direction: it gives up some theoretical
coverage length, keeps fallback explicit, and exposes bend-risk counts. The
remaining bend-risk counts are not automatic rejects; they identify where the
writer should apply slower speed bands, tension lead/release, or future
machine-tested limits.

The prototype now supports deterministic layer phasing through
`--phase-index/--phase-count`. A three-phase isogrid sweep on the gear coupon
covered all seven internal boundaries (the center bore plus six holes) in every
phase:

| Phase | Candidates | Components | Accepted routes | Fallback routes | Accepted length | Fallback length | Covered holes | Bend-risk points |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0/3 | 54 | 1 | 9 | 18 | 842.845 mm | 886.610 mm | 7 / 7 | 50 |
| 1/3 | 57 | 1 | 6 | 16 | 748.667 mm | 955.162 mm | 7 / 7 | 41 |
| 2/3 | 60 | 1 | 11 | 43 | 1239.202 mm | 615.360 mm | 7 / 7 | 102 |

The saved diagnostics for that sweep are in:

`work/rocket-algorithm-1.3.1.480-research/prototype-route-phases-20260720-scored-pruned`

## Short-Candidate Graph Run

Rocket does not treat every clipped line shorter than the minimum segment length
as an immediate loss. The current clean-room prototype now keeps those short
segments in the graph, labels them as
`short_candidate_for_route_join_or_fallback`, and lets the route selector accept
them only when the finished route reaches the cut-safe threshold. Any unselected
short geometry remains explicit plastic fallback. The invariant is still hard:
accepted routes must stay inside the printable polygon and may not bridge empty
space.

Command:

```bash
python3 scripts/prototype_fiberseek_composite_routes.py --coupon all --pattern isogrid --output-dir work/rocket-algorithm-1.3.1.480-research/prototype-routes-short-candidates-20260721 --no-png
```

Results:

| Coupon | Candidates | Short candidates | Components | Accepted routes | Fallback routes | Accepted length | Fallback length | Hole coverage | Void crossings |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rect plate | 31 | 4 | 1 | 11 | 24 | 1239.039 mm | 186.096 mm | 0 / 0 | 0 |
| Single-hole plate | 44 | 2 | 3 | 14 | 20 | 1413.592 mm | 525.656 mm | 1 / 1 | 0 |
| Multi-hole plate | 80 | 8 | 3 | 19 | 34 | 1974.815 mm | 1052.444 mm | 6 / 6 | 0 |
| Min-length bars | 62 | 57 | 8 | 3 | 24 | 221.624 mm | 585.576 mm | 0 / 0 | 0 |
| Bend-radius ladder | 81 | 11 | 3 | 22 | 41 | 2473.553 mm | 899.034 mm | 3 / 3 | 0 |
| Gear with six holes | 75 | 21 | 6 | 10 | 29 | 899.481 mm | 968.298 mm | 7 / 7 | 0 |
| Separate islands | 40 | 6 | 6 | 7 | 13 | 489.049 mm | 865.756 mm | 0 / 0 | 0 |

The result is closer to the Rocket backend shape: short candidates are carried
far enough to participate in valid long routes, while fallbacks remain visible
for native plastic replacement. The extra graph components are expected because
short clipped geometry exposes more disconnected printable fragments; the
physical invariant is route containment, not a one-to-one match between graph
components and plastic islands.

## Route-Shape Metric Run

The latest prototype JSON now exports the same route-shape concepts used by the
Rocket/TinMan G-code analyzer: closure gap, bounding spans, and shape class.
This lets the clean-room route sidecar be compared against Rocket's mostly
open-path composite-road behavior instead of only route count and length.

Command:

```bash
python3 scripts/prototype_fiberseek_composite_routes.py --coupon all --pattern isogrid --output-dir work/rocket-algorithm-1.3.1.480-research/prototype-routes-shape-metrics-20260721
```

Results:

| Coupon | Accepted routes | Fallback routes | Accepted length | Shape counts | Hole coverage | Void crossings |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| Rect plate | 11 | 24 | 1239.039 mm | 10 open; 1 line/tail | 0 / 0 | 0 |
| Single-hole plate | 14 | 20 | 1413.592 mm | 13 open; 1 near-closed | 1 / 1 | 0 |
| Multi-hole plate | 19 | 34 | 1974.815 mm | 19 open | 6 / 6 | 0 |
| Min-length bars | 3 | 24 | 221.624 mm | 2 open; 1 line/tail | 0 / 0 | 0 |
| Bend-radius ladder | 22 | 41 | 2473.553 mm | 22 open | 3 / 3 | 0 |
| Gear with six holes | 10 | 29 | 899.481 mm | 10 open | 7 / 7 | 0 |
| Separate islands | 7 | 13 | 489.049 mm | 7 open | 0 / 0 | 0 |

The route-shape output is a useful signal: the prototype can already produce
Rocket-like open composite routes while preserving the no-crossing invariant.
The remaining work is to move this from a coupon harness into native TinManX1
layer geometry, then attach real matrix/fiber flow and writer semantics.

## Solid Row-Graph Run

The Rocket 1.3.1.480 deep dive showed that dense solid infill should preserve
clipped candidate roads as route-node identities. The prototype now exposes
that behavior through `--route-strategy row_graph`.

Command:

```bash
python3 scripts/prototype_fiberseek_composite_routes.py \
  --coupon coupon_06_gear_with_six_holes \
  --output-dir work/rocket-algorithm-1.3.1.480-research/prototype-routes-row-combination-20260721-gear-solid07 \
  --pattern solid --density 100 --line-width 0.7 --inset 0 \
  --min-segment-length 10 --min-route-length 63 \
  --min-bend-radius 10 --max-arc-segment-length 4 \
  --route-strategy row_graph --max-terminal-candidates 24 \
  --max-routes-per-component 8 --no-png
```

Results:

| Metric | Value |
| --- | ---: |
| Candidate segments | 596 |
| Direct / short candidates | 468 / 128 |
| Candidate length | 15971.463 mm |
| Transition budget | 4.2 mm |
| Row graph nodes / edges | 596 / 41 |
| Connected row components | 555 |
| Route selector | Rocket-style path combination |
| Candidate route combinations | 78 |
| Accepted routes | 65 |
| Fallback routes | 490 |
| Accepted length | 5420.885 mm |
| Fallback length | 10568.850 mm |
| Hole coverage | 7 / 7 |
| Unsupported crossings | 0 |

This is not full Rocket parity yet, but it fixes the false diagnostic from the
noded-union branch. The same dense gear previously produced 23,406 noded graph
edges from 596 clipped candidate rows and could falsely report zero accepted
routes. With row identity preserved, the prototype keeps the physical invariant
that accepted routes stay inside the printable polygon while proving that solid
candidate rows can be accepted and returned as fallback separately. The latest
run also matches the Rocket selector shape more closely by choosing
non-overlapping path combinations instead of accepting whole connected
components.

## Native C++ Promotion

The row-graph idea now exists in native code as
`CompositeRouteGraphStrategy::RocketRowGraph` in
`src/libslic3r/FiberseekCompositePlanner.*`. The diagnostic branch preserves
candidate rows, groups by measured row angle/level, stores endpoint transition
choices, rejects connectors that cross unrelated candidate rows, and allows
connected short rows to become one cut-safe route. The native branch now also
enumerates terminal paths, accepts single-long-row candidates, creates
contiguous path sub-combinations, and chooses non-overlapping route groups by
owned-road coverage. `PrintObject` uses this strategy for FibreSeek
composite-only diagnostics, and `libslic3r` compiles with the branch enabled.
The native `PrintObject` hook now uses the selected diagnostic to suppress
normal internal/sparse-solid plastic infill on selected composite-only layers
and recreate rejected candidate rows as explicit sparse/solid plastic fallback
paths.

The Python prototype remains the stricter geometry reference for now because it
checks connector containment against the printable polygon. The C++ branch still
needs exact split-island parity, but accepted-route CFC command emission now has
an opt-in native development path. `GCode::process_layer()` can emit diagnostic
routes as FibreSeek `M1001`/`M1002` command blocks when
`TINMANX1_NATIVE_COMPOSITE_ONLY_EXPERIMENTAL=1` is set. This is intentionally
not production-unlocked yet: accepted route segments now carry explicit
plastic/fiber ownership into the writer, but exact Rocket phase-speed behavior,
matrix-flow correction parity, and analyzer gates remain open.

## Next Prototype Work

- Promote the scored selector from greedy path removal toward a bounded
  combination optimizer.
- Close split-island transition parity between the Python reference, Rocket
  observations, and the native row graph.
- Convert bend-risk diagnostics into speed-band and tension-phase simulation.
- Promote explicit route-segment ownership into native CFC G-code emission and
  add analyzer coverage gates.
- Compare prototype coupon route coverage against Rocket coupon slices once the
  user can run those controlled slices.
