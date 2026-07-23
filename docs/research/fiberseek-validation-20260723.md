# TinManX1 FibreSeek Validation Notes - 2026-07-23

## Current Goal

Validate the TinManX1 native FibreSeek continuous-fiber planner against Rocket Slicer 1.3.1.480 using realistic plastic + continuous-fiber output. The old "fiber only" comparison path is not considered physically meaningful because the continuous fiber needs polymer matrix to remain fixed in the part.

## Saved Prop Baseline

Real prop model:

`6-blades boat prop(Ready) v1.stl` from the local FibreSeek propeller validation set.

Transform used for the apples-to-apples CLI checks:

`--scale 0.85 --rotate-x 90 --ensure-on-bed`

Saved Rocket heavy G-code:

`Heavy.gcode` from the same local FibreSeek propeller validation set.

Saved TinManX1 heavy G-code inspected:

`5 tinmanx1 6-blades boat prop(Ready) v1_0.4n_0.2mm_PETG_SEEKER 3_3d13h1m.gcode` from the same local validation set.

Initial saved-file findings:

- Rocket: 3,069 `M1001` fiber-load blocks, 314 layers, about 233.6 g fiber, about 279.4 g filament, direct route XY p50/p90 about 593 mm / 1,918 mm.
- Saved TinManX1: 7,600 `M1001` blocks, 307 fiber layers, about 246.83 g fiber, about 494.92 g filament, direct route XY p50/p90 about 178 mm / 827 mm.
- Saved TinManX1 was no longer under-fibered; the main mismatch was too many short cuts.
- Saved TinManX1 had 950 closed-loop fiber routes versus Rocket's 27. Rocket concentrates much more fiber into longer open paths.
- The saved file predated the latest machine-contract patch, so it was missing the final baseline `SET_PRESSURE_ADVANCE`, `SET_TOOL_CORNER_VELOCITY`, and `MINIMUM_CRUISE_RATIO` commands now emitted by current builds.

## Planner Changes

Changes made in this pass:

- Added a post-combine layer stitch pass so perimeter and infill fiber roads can be joined when the connector is legal inside the same printable island.
- Changed stitch scope from candidate-family scope to physical island scope for final route joining.
- Kept row-graph generation family-scoped; only the final stitch is allowed to join perimeter/infill families.
- Added spatial candidate and boundary indexes to avoid full candidate/boundary scans during connector legality checks.
- Added a pre-stitch route budget: keep up to `max(final route cap * 4, final route cap + 12)` routes before final mixed-family stitching, then apply the configured final cap.
- Restored paired plastic refill for unsupported/too-short solid fallback candidates and limited the cheaper single-road fallback to candidates dropped because a better CFC route won. This preserves Rocket-style matrix replacement where the fiber candidate itself cannot be legally printed.
- Added regression coverage proving a legal perimeter route and infill route in the same island become one cut-safe continuous route.

## Coupon Validation

Coupon:

`work/fiberseek_validation/coupons/coupon_06_gear_with_six_holes.stl`

Current heavy profile output:

`work/fiberseek_validation/tinman_coupon_post_fast_fallback_heavy_06_run1/plate_1.gcode`

Audit:

- Contract audit passed.
- Routes: 280
- Fiber layers: 28
- Continuous fiber length: 190,552.062 mm
- Continuous fiber mass: 19.4363 g
- Matrix path: 190,552.062 mm
- Cut distance: 54.8 mm
- Total filament: 37.28 g in the final fast-fallback run.

Current coupon route mix:

- Open path: 232
- Closed loop: 41
- Near closed loop: 7

The coupon now keeps the expected heavy-layer coverage and produces longer mostly-open routes, but Debug CLI slice time remains about 157-160 seconds.

Measured Debug CLI timing on the heavy coupon:

- Unbounded mixed-family post stitch: about 160.31 s.
- Route-budgeted post stitch: about 160.22 s.
- Boundary spatial index: about 157.06 s.
- Row-span pruning: about 156.73 s.
- Fast fallback distinction: about 150.93 s.

Sampling during the full prop run showed the hot stack inside:

`generate_fiberseek_composite_diagnostics -> plan_surface_fill_routes -> select_composite_routes_row_graph -> row_connection_options -> connector_is_candidate_legal -> connector_inside_printable_region_fast`

This means the remaining Debug runtime is broader row-graph connector enumeration during dense solid route generation. Boundary/candidate spatial indexes help correctness scalability, but a larger speed win likely needs earlier candidate pairing limits inside `select_composite_routes_row_graph` or a more Rocket-like bounded route candidate search. Release slicing is much faster and is the correct measure for user-facing throughput.

## Fresh Full Prop Result

Fresh current-build output:

`work/fiberseek_validation/prop_release_realistic_heavy_85_run1/plate_1.gcode`

Release CLI slice time:

- Real time: 63.36 s.
- User CPU time: 96.67 s.

Contract audit:

- Passed.
- Routes: 2,965.
- Fiber layers: 307.
- Continuous fiber length: 2,190,585.198 mm.
- Continuous fiber mass: 223.4397 g.
- Matrix path: 2,190,585.186 mm.
- Cut distance: 54.8 mm.
- No route warnings.

Direct CFC route-block comparison:

| File | Routes | CFC layers | XY total | XY p50 | XY p90 | Fiber mass | Total/header material |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Rocket `Heavy.gcode` | 3,069 | 314 | 2,461,136 mm | 592.6 mm | 1,917.9 mm | 233.6 g | 279.4 g |
| Saved TinManX1 `5 tinmanx1...` | 7,600 | 307 | 2,473,028 mm | 177.9 mm | 827.5 mm | 246.8301 g | 494.92 g |
| Fresh TinManX1 release | 2,965 | 307 | 2,207,824 mm | 516.8 mm | 1,581.3 mm | 223.4397 g | 422.59 g |

Interpretation:

- The major regression, too many tiny CFC cuts, is fixed for this heavy prop. Fresh TinManX1 is within 104 routes of Rocket while retaining comparable fiber mass.
- Fresh TinManX1's routes are somewhat shorter than Rocket's p50/p90, but much closer to Rocket than the saved TinManX1 export.
- The formal Rocket comparison has no hard command/setpoint findings. It reports advisories for route metadata absence in Rocket and large print-time/material-summary differences because Rocket and TinManX1 do not report plastic/fiber totals the same way.
- The TinManX1-to-TinManX1 compare intentionally flags the route-count reduction from 7,600 to 2,965 and notes that the old export had one untargeted `M104 S250` setpoint. The fresh output uses explicit tool-targeted temperature commands like Rocket.

## Strength Mode Spread

Same model, transform, PETG + PETG X-CCF filaments, and release binary:

| Mode | Slice time | Routes | CFC layers | CFC mass | Total material | Estimated print time | Route p50 | Route p90 | Audit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Heavy | 63.36 s | 2,965 | 307 | 223.4397 g | 422.59 g | 2d 6h 15m | 509.3 mm | 1,574.2 mm | Pass |
| Medium | 26.55 s | 917 | 154 | 55.6794 g | 296.36 g | 1d 2h 23m | 358.8 mm | 1,323.9 mm | Pass |
| Light | 14.17 s | 206 | 103 | 14.3456 g | 267.86 g | 17h 56m | 592.6 mm | 1,291.7 mm | Pass |

All three modes now produce distinct, proportional CFC output. This specifically closes the earlier regression where Light, Medium, and Heavy produced the same CFC mass and preview density.

## Nozzle Profile Validation

Coupon validation across FibreSeek process families:

| Profile family | Output | Result |
| --- | --- | --- |
| `0.4+0.7` composite Heavy | `tinman_coupon_post_fast_fallback_heavy_06_run1/plate_1.gcode` | Audit pass |
| `0.6+0.7` composite Heavy | `tinman_coupon_release_heavy_06nozzle_run1/plate_1.gcode` | Audit pass |
| `0.8+0.7` composite Heavy | `tinman_coupon_release_heavy_08nozzle_run3/plate_1.gcode` | Audit pass |
| `0.8` plastic-only | `tinman_coupon_release_plastic_08_run1/plate_1.gcode` | Slice pass |

The `0.8+0.7` composite profiles initially failed preset validation because `bridge_line_width` was generated from the 0.8 mm plastic nozzle, while the composite printer definition also contains the 0.7 mm fiber nozzle. The generator now emits `0.69` for composite `0.8+0.7` bridge width and `0.79` for plastic-only `0.8`.

## Local Release Candidate

The running `/Applications/TinManX1.app` was left untouched because it was open. A staged local RC bundle was created instead:

`outputs/TinManX1-2.4.2-fiberseek-rc-20260723/TinManX1.app`

Bundle checks:

- `CFBundleDisplayName`: `TinManX1`
- `CFBundleExecutable`: `TinManX1`
- `CFBundleIdentifier`: `com.tinmanfp.TinManX1`
- `CFBundleShortVersionString`: `2.4.2`
- `codesign --verify --deep --strict --verbose=2`: pass
- Bundle size: about 433 MB

Release verification:

- `python3 checks/verify_tinmanx1_fiberseek_release.py`: pass

## Pending

- Visually preview the fresh full prop in TinManX1 to confirm the improved route economy still looks like the expected heavy coverage.
- Consider a deeper Rocket-like bounded row search only if visual preview or future stress coupons show missing coverage; the route-count parity problem is no longer the first-order issue.
