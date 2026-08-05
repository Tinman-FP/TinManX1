# FibreSeek Composite-Only Gap Analysis

This note records a sanitized engineering finding from comparing a Rocket
Slicer FibreSeek Seeker 3 heavy slice against a TinManX1 heavy slice of the
same propeller model. It intentionally records behavior, settings, and required
TinManX1 work without copying Rocket source, preset files, database blobs, or
private local file paths.

## Executive Finding

Rocket is not merely adding more continuous-fiber overlay paths. The reference
Rocket G-code is emitted in `PRINTING_MODE: Composite Only`, where the composite
tool owns the reinforced model roads and emits plastic matrix plus continuous
fiber on the same `T0` motion lines.

The current TinManX1 output is mechanically coherent, but it is still a
`Plastic + Continuous Fiber Overlay` job: Orca/TinMan first slices the model as
a normal plastic print, then the native FibreSeek planner appends or interleaves
continuous-fiber routes. That architecture cannot reach Rocket parity for this
part by profile tuning alone.

## G-Code Comparison

Command:

```bash
python3 scripts/source-helpers/compare_fiberseek_gcode.py \
  --layer-csv latest_prop_compare_by_z.csv \
  --route-csv latest_prop_compare_routes.csv \
  Heavy.gcode \
  "Codex requested 6-blades boat prop(Ready) v1_0.4n_0.2mm_PETG_SEEKER 3_13h54m.gcode"
```

The latest July 21 rerun artifacts are stored under
`work/rocket-algorithm-1.3.1.480-research/prop-comparison-20260721-rerun`
as `summary.json`, `layers.csv`, and `routes.csv`. Earlier comparison artifacts
remain in the parent research directory as `latest_prop_compare.json`,
`latest_prop_compare.md`, `latest_prop_compare_by_z.csv`, and
`latest_prop_compare_routes.csv`.

Key results:

| Metric | Rocket | TinManX1 |
| --- | ---: | ---: |
| Printing mode | Composite Only | Plastic + Continuous Fiber Overlay |
| Total layers | 314 | 322 |
| Layer height | 0.2 mm | 0.2 mm |
| M1001 route starts | 3069 | 821 |
| M1001 load total | 2,457,466 mm | 373,359 mm |
| M1001 load p50 / p90 | 591 / 1,916 mm | 170 / 1,312 mm |
| Parsed layers containing M1001 | 314 | 153 |
| Z levels containing M1001 | 314 | 154 |
| Reconstructed fiber route blocks | 3,069 | 821 |
| Fiber block XY p50 / p90 | 684 / 2,095 mm | 115 / 1,257 mm |
| Fiber block material-carrying XY total | 2,189,651 mm | 211,284 mm |
| Fiber block U-positive XY total | 2,042,011 mm | 179,663 mm |
| Fiber block V-positive XY total | 2,189,651 mm | 211,176 mm |
| Fiber block motion-count p50 / p90 | 202 / 944 | 96 / 638 |
| Closed-loop fiber blocks | 27 | 660 |
| Fiber block shape classes | 2,976 open paths; 59 near-closed; 27 closed; 7 line/tail | 660 closed; 161 line/tail |
| T0 route XY travel | 2,791,311 mm | 327,931 mm |
| T0 route U positive motion | 1,620,378 | 122,674 |
| T0 route V positive motion | 55,251 | 6,926 |
| T0 route P ratio tags | 718,765 | 153,642 |
| Estimated print time | 128h 38m | 13h 54m |
| Continuous fiber used | 233.6 g | 33.44 g |
| Polymer filament used | 279.4 g | 236.49 g |

TinManX1 is emitting about 15.2% of Rocket's reinforced-route load total on
this part, and only about 8.8% of Rocket's U-positive fiber-road XY motion.
The TinManX1 FibreSeek machine contract audit still passes, which means the
issue is not basic command safety; it is manufacturing-mode parity.

The current comparison sidecars are:

- `work/rocket-algorithm-1.3.1.480-research/prop-heavy-routes-current-20260721.csv`
- `work/rocket-algorithm-1.3.1.480-research/prop-heavy-layers-current-20260721.csv`

The Z distribution makes the same point from another angle. Rocket places
`M1001` composite-route events on every observed printed Z level in this file.
TinManX1 places them on about half of the observed Z levels because the current
planner is still an overlay/alternating-layer strategy.

The active TinManX1 heavy FibreSeek overlay profiles also encode that
alternating behavior directly with `fiber_layer_step = 2`. That is acceptable
for a deliberately lighter overlay process, but it is not an apples-to-apples
Rocket heavy comparison: Rocket's heavy propeller reference uses composite-only
fiber on every observed Z level. Correcting this profile cadence alone will not
close the fiber-volume gap, but leaving it in place guarantees TinManX1 starts
the comparison roughly half a Z-stack behind.

The reconstructed `M1001` to `M1002` block metrics make the deficit even
clearer. Rocket's median reinforced block owns about 684 mm of XY motion, while
TinManX1's median block owns about 115 mm. Rocket is therefore doing two things
at once: it reinforces more Z levels and assigns longer model roads to the
composite tool on those levels.

The route-shape evidence is equally important. Rocket emits mostly long open
composite paths; TinManX1 emits mostly closed overlay loops. That is the
signature of two different manufacturing models. Rocket is not just tracing
closed perimeters with more density. It is using composite-owned roads that
span the model, then returning candidates that cannot satisfy the route/cut
constraints to plastic fallback.

Inspecting representative route blocks shows the same thing at command-stream
level. Rocket commonly starts one `M1001` reinforced polygon, emits many
fiber-bearing `G1` roads, and uses in-route `G0` connector moves before the
single route cut and `M1002` close. TinManX1's current overlay output usually
emits much shorter closed or near-closed loops. Matching Rocket therefore needs
native route ownership and legal connector transitions inside the reinforced
polygon, not more post-export loop tracing.

Layer-bucket evidence also shows the missing-volume problem directly. Of the
314 Rocket Z buckets with U-positive fiber-road XY motion, 162 have no TinManX1
U-positive fiber-road XY counterpart. In the 152 Z buckets that both slicers
reinforce, TinManX1 still emits only about 179,499 mm of U-positive fiber-road
XY motion against Rocket's 1,018,715 mm. The rest of Rocket's 1,023,296 mm of
U-positive fiber-road XY exists on Z levels TinManX1 does not reinforce at all.

## Rocket Baseline Settings Observed

The shipped FibreSeek profile data available in Rocket's local database exposes
one PETG/X-CCF baseline profile:

| Setting | Observed value |
| --- | ---: |
| Generate fiber infill | 1 |
| Generate fiber perimeters | 1 |
| Fiber infill type | Cellular isogrid |
| Isogrid density | 25 |
| Isogrid angle | 0 deg |
| Fiber outer perimeter count | 1 |
| Fiber inner perimeter count | 1 |
| Plastic outer roads when fiber present | 2 |
| Plastic inner roads when fiber present | 0 |
| Composite/fiber line width | 0.8 mm |
| Fiber extrusion percent | 100% |
| Fiber solid line width | 0.68 mm |
| Fiber cellular line width | 0.68 mm |
| Fiber minimum bend radius | 12 mm |
| Fiber maximum arc segment length | 3 mm |
| Fiber start length | 15 mm |
| Fiber slow length | 5 mm |
| After-cut plastic extrusion multiplier | 0.58 |
| Minimum perimeter length | 20 mm |
| Infill accepted path threshold | cut distance + 5 mm |
| Macro layer height | 0.24 mm |
| Composite nozzle diameter | 0.7 mm |
| Plastic nozzle diameter | 0.4 mm |

The composite extruder baseline also records a 60 mm cut distance, 57 mm fiber
restart length, 1.1 mm contact radius, and 2.0 mm extended contact radius. The
observed emitted job uses `CUT DISTANCE 54.8`, so the emitted cut window appears
to include downstream correction rather than being a direct copy of the database
field.

The current Rocket 1.3.1.480 API matrix session profiles refine that older
database view for the shipped PETG/X-CCF coupon set:

| Mode | Macro layer | Fiber road | Solid angles | Min segment | Perimeter extension | Fiber min radius | Arc segment max | After-cut multiplier |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| Speedy / Light | 0.20 mm | 0.68 mm | `0` | 10 mm | -0.8 mm | 12 mm | 3 mm | 0.58 |
| ReinForced / Medium | 0.24 mm | 0.80 mm | `0` | 10 mm | -0.3 mm | 12 mm | 3 mm | 0.72 |
| Fortified / Heavy | 0.20 mm | 0.70 mm | `0/90/0` | 10 mm | 0.0 mm | 10 mm | 4 mm | 0.72 |

For heavy composite-only parity, TinManX1 therefore needs all-layer cadence,
0.7 mm solid fiber roads, `0/90/0` angle-list cycling, 10 mm candidate segment
splitting, and the route acceptance threshold of `cut_distance + 5 mm`.

For cellular isogrid infill, the backend builds a `FiberInfillData` object with
the cellular fiber line width, the matching plastic cellular width, solid
minimum segment length, the accepted path threshold, and the fiber inset into
perimeters. It then offsets the printable island by the fiber-perimeter inset,
lays down three isogrid line families, and runs those candidates through a route
combination solver. The visible spacing formula in the decompiled control flow
is consistent with `fiber_cellular_EW * 100 / density * 3`; this still needs a
controlled geometry slice to confirm the final effective pitch after clipping
and joining.

Rocket's slot/material wiring for this baseline is:

| Slot index | Slot type | Tool role | Material |
| ---: | --- | --- | --- |
| 0 | Composite | `T0` / 0.7 mm CFC nozzle | X-CCF / PETG composite |
| 1 | Plastic | `T1` / 0.4 mm FFF nozzle | PETG plastic |

This matters because a Rocket composite-only part is not "plastic model on
slot 1, fiber decoration on slot 0." Most reinforced model roads belong to the
composite slot.

## Rocket Backend Behavior Observed

Rocket's backend contains distinct generators for fiber perimeters, solid fiber
infill, and cellular fiber infill. The cellular families line up with the UI and
database options: rhombic, isogrid, anisogrid, and tetragrid. The composite
perimeter path builder passes both matrix-flow-per-mm and fiber-flow-per-mm into
the same composite move-building path, which is why the final `T0` route moves
carry composite matrix and fiber together.

The backend also has route-tree and graph-combination logic for choosing
printable fiber paths against cut-window constraints. Candidate cellular infill
segments are split into nodes, tails are used as path search starts, possible
paths are converted into non-overlapping node combinations, and the best long
combination is selected. Candidate segments not included in the accepted fiber
combination are returned as plastic stubs. That is a material handling rule, not
just a visual path preference: short or geometrically awkward fiber candidates
are not ignored, they are converted back into polymer support so composite-only
does not leave unsupported gaps.

The same route selector applies an important identity rule: the original clipped
candidate roads are the route nodes. Split island geometry is used to decide
whether a start-to-start, start-to-end, end-to-start, or end-to-end transition is
legal and whether it crosses another candidate, but the solver does not use a
fully noded geometric union as the route identity. A dense solid coupon exposed
why this matters: 596 clipped candidate lines became more than 23,000 union
edges in a naive prototype, producing a false zero-acceptance diagnostic. The
TinManX1 native selector should preserve candidate rows first, then attach
Rocket-style start/end-flagged connections.

The composite move builder also inserts the cut and delayed-fiber handling into
the move stream. It creates reinforced polygon start/end blocks, emits plastic
matrix and fiber deltas together for reinforced moves, applies start/slow/finish
speed handling, splits a move at the exact cut point, inserts the CFC cut block,
then rewrites the post-cut delay/tail span so fiber is off where the machine
requires it. The cut point is measured backward from the latest composite move
by `CutDistance - NozzleContactRadiusExtended`; plastic and fiber deltas are
split proportionally on the cut move, and post-cut plastic/matrix extrusion is
scaled by the after-cut multiplier. TinManX1 must model these as route
semantics, not just as postprocessor text.

## TinManX1 Current Limitation

TinManX1 currently plans fiber from already-generated plastic G-code. That gives
us useful safety and visualization features, including:

- selected fiber start/end layer guards
- light/medium/heavy route density controls
- alternating hole reinforcement
- stitched short-route handling
- bend-radius and route-length warnings
- FibreSeek `M1001`/`M2800`/`M1002` machine contract checks

But because it starts after normal plastic slicing, it does not own the model's
primary composite roads. It cannot naturally emit a Rocket-style composite-only
slice where `T0` co-extrudes matrix and fiber over most of the model volume.

The source-level integration confirms this architecture: `Print::export_gcode()`
first runs normal Orca/TinMan G-code generation, then calls the native FibreSeek
planner on the emitted file, and finally reloads the modified file for preview.
The Python planner reconstructs layer geometry from already-emitted extrusion
roles such as inner wall, outer wall, sparse infill, and generated ribs. That is
appropriate for overlay reinforcement, but it is too late in the pipeline to
decide that a model road should have been a composite `T0` road instead of a
plastic `T1` road.

Profile-only experiments confirmed this ceiling: raising route caps, changing
layer step to every layer, and tracing plastic paths can increase output, but
still does not approach Rocket's 233.6 g fiber usage for this geometry.

## Required TinManX1 Work

To reach Rocket parity or improve on it, TinManX1 needs a real composite-only
FibreSeek mode, not another overlay patch.

1. Add a process-level manufacturing mode:
   - `plastic_plus_fiber_overlay`
   - `composite_only`

2. Add FibreSeek composite-only process profiles using TinMan names:
   - `Light`, `Medium`, `Heavy`
   - include the observed PETG/X-CCF baseline values as the first validated
     profile family

3. Move composite road ownership earlier in the pipeline:
   - generate reinforced perimeters and infill as first-class composite roads
   - emit matrix and fiber together on the same `T0` path
   - keep plastic `T1` roads only where the composite strategy calls for them
   - remove or replace plastic roads where accepted composite roads take
     ownership, instead of drawing fiber over an already-complete plastic slice

4. Implement the missing advanced fiber controls:
   - fiber infill type: solid, rhombic, isogrid, anisogrid, tetragrid
   - fiber infill density and angles
   - fiber outer/inner perimeter counts
   - plastic outer/inner roads when fiber is present
   - composite line width, fiber extrusion percent, speed coefficient
   - minimum perimeter length and route tree joining controls

5. Replace longest-route selection with a composite route graph:
   - build candidate routes by island/area
   - join short branches into printable cut windows
   - choose best routes by cut length, geometry coverage, and layer phase
   - return rejected short candidates as plastic substitution/stub geometry
   - preserve TinManX1's alternating hole coverage and bend warnings

6. Keep the new comparison guard:
   - a Rocket `Composite Only` file compared to TinMan overlay output must fail
     validation, even when the basic FibreSeek machine contract is safe

## Practical Next Step

The next engineering step is to add the `composite_only` process mode and a
prototype composite-road generator behind a feature flag. It should first target
PETG + X-CCF on the FibreSeek Seeker 3 0.4/0.7 configuration, because that is
the only Rocket-shipped baseline we can treat as validated.

The source-level entry map for that work is
`docs/design/fiberseek-composite-only-cpp-integration-map.md`. The critical
implementation boundary is that `composite_only` must generate native C++ route
data before layer G-code emission. It must not fall through to the post-export
Python overlay planner.
