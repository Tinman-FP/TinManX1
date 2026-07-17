# TinManX1 FibreSeek G-code Contract

This note captures the FibreSeek machine contract that TinManX1 must preserve
when generating plastic plus continuous-fiber G-code. It is based on local
Rocket-vs-TinManX1 behavior comparisons and TinManX1's own planner/audit tools.
Rocket files, private machine exports, and validation G-code snapshots are not
part of the public release tree.

## Current Contract

- Slot 1 is the plastic-only nozzle.
- Slot 2 is the CFC lane and is limited to `CFC <matrix> + <fiber>` filament
  profiles.
- Plastic-only and plastic-plus-fiber process profiles remain separate.
- Continuous-fiber modes are `light`, `medium`, and `heavy`.
- Fiber starts at the selected start layer and stops with the same number of top
  layers remaining.
- Generated-rib infill may use the selected pattern defaults or an explicit
  comma-separated angle list. A nonzero fiber infill density derives generated
  rib spacing from fiber line width.
- Closed fiber loops preserve source starts by default, or may use fiber-only
  seam placement (`source`, `nearest`, `aligned`, `rear`, `random`) without
  changing plastic seam behavior.
- Cut/restart routing uses a 55 mm mechanical minimum route length, 58 mm
  configured cut distance, and 54.8 mm emitted cut command distance.
- Bend radius is treated as a user-selected quality target. Routes below that
  target are advisory warnings, not automatic hard failures.
- TinManX1 must emit managed FibreSeek tool commands instead of bare `T0` or
  `T1` commands in generated fiber output.

## Required Command Shape

The release audit requires these sequence-level behaviors:

- A single `ORCA_CODEX_NATIVE_FIBER_PLANNER_MERGED` marker at the top.
- A machine contract block before the first printable layer.
- Bed and chamber preheat/wait commands that match the G-code config summary.
- Initial managed selection of plastic tool 1.
- Managed switch to fiber tool 0 only inside the native fiber planner block.
- Exactly one fiber prime block when fiber routes are emitted.
- Every fiber route has `M1001`, `M2800`, `CUT DISTANCE`, and `M1002` in that
  order.
- Post-cut tail motion uses the V axis only and does not advance the U fiber
  axis.
- Shutdown happens before `EXECUTABLE_BLOCK_END`.
- Continuous-fiber preview and summary metadata are emitted with route count,
  fiber layers, used length, and used mass.

Use `scripts/audit_fiberseek_gcode_contract.py` for strict TinManX1 output
validation. Use `scripts/compare_fiberseek_gcode.py <rocket.gcode>
<tinmanx1.gcode>` for neutral Rocket/TinManX1 comparison reports; it compares
command families, thermal setpoints, tool ownership, cut/load behavior, route
metadata, and summary values without storing Rocket files in the public tree.

## Latest Local Validation Snapshot

The latest local TinManX1 heavy PETG/PETG CCF feel-good slice passed
`scripts/audit_fiberseek_gcode_contract.py` with:

- 278 continuous-fiber routes.
- 39 fiber layers.
- 36,716.489 mm continuous-fiber route length.
- 279 each of `M1001`, `M2800`, and `M1002` including the prime block.
- 54.8 mm emitted cut distance.
- No route below the 55 mm mechanical minimum.
- No route below the 65 mm standalone cut-window recommendation.
- Advisories only for bend-radius quality target and skipped candidate routes.

The comparable local Rocket heavy PETG/PETG CCF slice used the same critical
thermal contract for this machine family: plastic nozzle 250 C, CFC nozzle
270 C, bed 75 C, chamber 0 C, plastic standby 150 C, and CFC standby 180 C.
Rocket's route count, route length, print time, and fiber mass are not expected
to match exactly because TinManX1 intentionally uses its own alternating route
planner.

## Public Release Boundary

Keep these artifacts in the public repo:

- TinManX1 profile JSON.
- TinManX1 planner, lint, smoke, audit, and comparison scripts.
- Clean-room behavior notes like this document.
- Source patches needed to expose, preserve, preview, and summarize CFC paths.

Keep these artifacts out of the public repo:

- Full Rocket G-code exports.
- Rocket database or app bundle files.
- Local `outputs/` validation snapshots.
- User application-support presets and live machine state.
- Private printer addresses, tokens, logs, and account data.
