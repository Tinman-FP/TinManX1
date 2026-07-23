# FibreSeek Propeller Realistic CCF + Plastic Comparison - 2026-07-22

## Scope

This note archives the current apples-to-apples direction for the six-blade
propeller comparison after setting aside the experimental no-cut layer-change
idea. The comparison is focused on realistic plastic plus continuous-fiber
printing, not dry CCF-only printing.

## Important Clarification

Rocket's heavy/fortified "Composite Only" output is not dry fiber-only output.
The inspected G-code includes:

- `T0` composite route motion with positive `U` fiber feed and positive `V`
  matrix/carrier feed.
- `T1` non-route plastic extrusion.
- One `M1001`, `M2800`, and `M1002` sequence per fiber route.

TinManX1's "Rocket Compare Composite Only" output follows the same physical
idea: the composite nozzle still carries polymer plus continuous fiber, and the
plastic nozzle still contributes plastic motion. The label is useful for
matching Rocket behavior, but it should not be read as dry carbon fiber without
plastic.

## Current G-code Findings

| Export | Source / Mode | Fiber Routes | Fiber Z Levels | M1001 Load Total | T0 Fiber `U+` | T0 Matrix `V+` | T1 Plastic `E+` |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Heavy.gcode` | Rocket heavy/fortified | 3069 | 314 | 2457466 | 1620378.479 | 55251.134 | 10728.679 |
| `Reinforced.gcode` | Rocket medium/reinforced | 1416 | 254 | 569850 | 263824.347 | 15038.181 | 20201.377 |
| `Tinmanx1 Heavy ... 13h51m.gcode` | TinMan normal heavy plastic+fiber | 1633 | 307 | 746851 | 242197.789 | 13883.052 | 45684.300 |
| `Heavy Comparison ... 16h21m.gcode` | TinMan heavy comparison plastic+fiber | 1633 | 307 | 744868 | 241439.774 | 13851.557 | 45684.300 |
| `Medium fiber plus plastic ... 16h21m.gcode` | TinMan medium comparison plastic+fiber | 1366 | 307 | 688232 | 218755.365 | 13540.324 | 45731.044 |
| `3 TinmanX1 ... 3d12h42m.gcode` | TinMan Rocket-compare heavy | 7600 | 307 | 2864473 | 1789735.372 | 86546.420 | 46311.824 |

## Interpretation

The ordinary TinManX1 heavy plastic+fiber profile is mechanically valid, but it
is much lighter than Rocket heavy: roughly 15% of Rocket's positive fiber-axis
feed in this propeller comparison.

The TinManX1 Rocket-compare heavy profile is much closer to Rocket's heavy
fiber mass and exceeds Rocket's positive fiber feed in this sample, but it uses
more fiber starts/cuts than Rocket. That means the next planner improvement
should not simply add more fiber. It should reduce route fragmentation while
preserving Rocket-class coverage.

Medium comparison is not yet apples-to-apples. TinMan medium comparison is
currently close to or above Rocket medium in total M1001 load, but the layer
strategy differs: Rocket medium uses fewer fiber Z levels and a different layer
height/source layer schedule in prior scans.

Light comparison still needs a clean Rocket reference export with fiber enabled.
The earlier Rocket light/speedy sample was plastic-only, so it should not be
used as a light CCF baseline.

## Recommended Next Step

Keep the production route local to normal layer-by-layer cutting for now. For
Rocket parity, use the Rocket-compare heavy profile as the calibration target,
then improve the TinMan planner to:

- merge compatible same-layer fiber roads where doing so stays inside part
  material,
- reduce tiny or redundant route fragments,
- preserve the stronger Rocket-class fiber coverage,
- keep plastic plus composite matrix extrusion active in all comparison modes,
- avoid exposing "composite only" wording to users as if it means dry fiber.

The immediate engineering target is: Rocket-like heavy coverage with a route
count closer to Rocket's 3069 routes, instead of TinMan's current 7600-route
Rocket-compare heavy export.

## 2026-07-23 Follow-Up Pass

Latest exported TinManX1 prop:

`5 tinmanx1 6-blades boat prop(Ready) v1_0.4n_0.2mm_PETG_SEEKER 3_3d13h1m.gcode`

Compared against Rocket `Heavy.gcode`, this file remains mechanically close in
fiber mass but still route-fragmented:

| Metric | Rocket Heavy | TinManX1 Latest |
| --- | ---: | ---: |
| `M1001`/cut blocks | 3069 | 7600 |
| `M1001` load total | 2457466 | 2864473 |
| Reconstructed route XY | 2791.311 m | 2473.028 m |
| Reconstructed positive fiber XY | 2042.011 m | 1674.503 m |
| Unique cut distance | 54.8 mm | 54.8 mm |

The latest export predates the command-contract patch, so the stricter audit
correctly fails it for missing Rocket-style startup lines:

- `SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0`
- `SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.8`
- `SET_TOOL_CORNER_VELOCITY T=0 SCV=1`
- per-layer `SET_PRINT_STATS_INFO CURRENT_LAYER=...`

TinManX1 source now emits those lines and the comparison/audit self-tests
require them. The next exported G-code should therefore be audited as a fresh
post-patch artifact rather than judging this older file's header.

The route-fragmentation fix moved one step forward: TinManX1 FibreSeek process
payloads now allow 16 mm post-selection route stitching, up from 8 mm, while
keeping the same printable-region legality checks. A new unit test verifies
that a tempting connector across a printable void is still rejected. This is a
conservative way to reduce cut count without bringing back the earlier
cross-pocket/cross-tooth fiber failure.

Validation artifacts for this pass were written under:

`work/fiberseek_validation/latest_prop_compare.json`
`work/fiberseek_validation/latest_prop_layers.csv`
`work/fiberseek_validation/latest_prop_routes.csv`

Neutral coupon models were generated under:

`work/fiberseek_validation/coupons/manifest.json`
