# Wave Overhang Source Snapshot

Generated: `2026-05-19`

TinManX inspected the public OrcaSlicer Wave Overhangs fork as a research and
future-adapter candidate for support-elimination work. This snapshot is not a
code import. It records source, credit, risk, and validation requirements before
TinManX copies or adapts any behavior.

## Sources Inspected

- OrcaSlicer-WaveOverhangs fork:
  <https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs>
- Verified `main` head by `git ls-remote`:
  `78495a2795d36a101bb5dde82fe2704b92dd39dd`
- Verified `v0.3.2` tag by `git ls-remote`:
  `379c18470f251b3839db12726a2c3a4e4135bfb8`
- Upstream PrusaSlicer WaveOverhangs lineage:
  <https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs>
- Andersons wave-overhang research DOI:
  <https://doi.org/10.2139/ssrn.6640458>
- Kaiser LaSO code lineage:
  <https://github.com/riekskaiser/wave_LaSO>

## What The Fork Adds

The fork presents wave overhangs as an opt-in OrcaSlicer feature. It adds a
dedicated Wave overhangs print-settings tab, a master experimental toggle, and
two selectable algorithms:

- Andersons: a port based on Steven McCulloch's PrusaSlicer-WaveOverhangs work,
  using supported-edge seeding and propagated fronts.
- Kaiser LaSO: a C++ reimplementation of Rieks Kaiser's laterally supported
  overhang approach, currently better suited to simple overhangs than complex
  geometry.

The feature writes preview/audit markers such as wave-overhang config and
region start/end comments, and includes an integration concept where normal
supports cover areas the wave algorithm cannot cover.

## TinManX Interpretation

Wave Overhangs may complement Arc Support because both try to grow toolpaths
outward from supported geometry instead of building disposable towers. The
important difference is that Wave Overhangs modulate the overhang fill itself
and may leave remaining regions for ordinary support, while Arc Support is a
post-slice replacement strategy for selected bridge/overhang infill.

TinManX should treat Wave Overhangs as a previewable transform family, not as a
drop-in support replacement. The current project direction remains:

- Keep `wave_overhang_compensation` at `research_watch`.
- Require source snapshot, license review, and adapter design before any code
  import.
- Surface source registry IDs in slice results and Strength Lens overlays.
- Show risk chips for surface-finish changes, cooling/material limits, small
  feature collision, and unsupported-span limits.
- Preserve normal/arc/tree fallback paths when wave coverage is incomplete.

## Production Blockers Before Enablement

- License and source compatibility must be checked for any adapted code path.
  The fork is listed as AGPL-3.0 inherited from OrcaSlicer.
- Presets are intentionally not baked in upstream; TinManX should not create
  default "magic" profiles until local test prints and material limits are
  measured.
- PLA with strong part cooling is the clearly favored initial material signal.
  PETG, ABS, and PC are specifically higher risk because of cooling and
  delamination behavior.
- Large spans can warp from thermal gradients, reheating, and nozzle pressure,
  so a wave path cannot be assumed to replace support over every bend.
- Kaiser LaSO needs simple-geometry gating until concave/narrow/multi-arm
  overhangs prove reliable.
- macOS physical-printer validation is not established by the upstream fork
  status, so William's Mac/printer path needs its own smoke and print tests.

## Local v0.3.2 App Inspection, 2026-06-06

William's downloaded
`OrcaSlicerWaveOverhangs_Mac_universal_V0.3.2.dmg` was inspected as a working
behavioral reference. The app bundle reports `OrcaSlicer-WaveOverhangs
2.4.0-dev`, and the public source tag inspected for matching code paths is
`v0.3.2` at `379c18470f251b3839db12726a2c3a4e4135bfb8`.

The important TinManX lesson is that the fork is not only a wavefront generator.
It integrates wave output into several slicer stages:

- two generator families are exposed behind an interface: Andersons and Kaiser
  LaSO
- normal bridge behavior can win for simple bridgeable regions, instead of
  forcing waves everywhere
- generated waves report a covered-area footprint, and uncovered support
  remainder polygons are preserved for normal support generation
- layer state distinguishes wave-floor polygons, wave-covered polygons, and
  wave-shadow polygons
- floor layers above wave regions are made authoritative so top/bottom shell
  propagation cannot silently refill or over-bridge the wave region
- G-code audit output includes `WAVE_OVERHANG_BUILD`,
  `WAVE_OVERHANG_CONFIG`, `WAVE_OVERHANG_START`, `WAVE_OVERHANG_END`,
  `_WAVE_OVERHANG_FAN_START`, and `_WAVE_OVERHANG_FAN_END`
- wave-specific controls include absolute wave flow, slow print/travel speeds,
  fan override, optional nozzle-temperature override, min-wave/min-layer dwell,
  end-of-line retraction, preserved outer perimeters, bridge suppression, and
  corner-aware spacing taper
- `wave_overhang_min_angle` is metadata-only in the inspected fork; Orca's
  upstream overhang-wall detection remains the effective candidate filter

TinManX should copy those boundaries conceptually, not import the code directly:
the next generator design should produce explicit `wave_covered`,
`support_remainder`, and `wave_floor_shadow` artifacts before any printer-bound
export is considered.

## Current TinManX Guard

`material_strength.layer_interface_guidance.experimental_toolpath_transform_lanes`
now includes `wave_overhang_compensation` with these source registry IDs:

- `wave-overhang:dennisklappe/orcaslicer`
- `wave-overhang:stmcculloch/prusaslicer`
- `wave-overhang:andersons/research`
- `wave-overhang:kaiser-laso/research`

The lane is advisory-only in Strength Lens. It does not alter printer-bound
G-code and should not be promoted beyond research watch until TinManX has a
source adapter, preview markers, coverage auditing, and material/span tests.

## Current Implementation Step Completed

TinManX now has a blocked Wave Overhang adapter-readiness contract instead of a
loose research note:

- `docs/app/wave-overhang-adapter.md` defines the adapter boundary, preview
  regions, operator test contract, and promotion gates.
- `schemas/slicing/wave-overhang-adapter-readiness.schema.json` describes the
  machine-readable blocked-readiness manifest.
- `tools/build_wave_overhang_adapter_readiness.py` writes
  `local-state/wave-overhang-adapter-readiness.json` with source registry IDs,
  credit names/work/kinds, inspected artifact provenance, license-review state,
  no-code-import policy, preview markers, material gates, and operator test
  fixtures.
- `tools/check_wave_overhang_adapter_readiness.py` and
  `tools/smoke_wave_overhang_adapter_readiness.sh` prove the lane remains
  research-watch blocked, printer-bound output stays disabled, and preview
  regions cannot be silently removed.

Use this command to rebuild and validate the current contract:

```bash
./tools/tinmanx.py wave-overhang-readiness --check
```

## Material-Adaptive Recipe Contract, 2026-06-06

TinManX now has a separate material recipe contract so Wave Overhangs and Arc
residual support are not treated as one global geometry. The contract is
advisory seed data only; it leaves printer-bound output blocked until coupon
receipts prove the selected material, nozzle, printer, flow margin, cooling,
chamber state, and conditioning state.

- `schemas/slicing/overhang-material-recipe.schema.json` defines the material
  recipe artifact.
- `tools/build_overhang_material_recipes.py` writes
  `local-state/overhang-material-recipes.json`.
- `tools/check_overhang_material_recipes.py` requires PLA, PETG/PCTG, ABS/ASA,
  PC, and PA/PPA/CF families to carry independent wave geometry, Arc residual
  geometry, speed, flow, cooling, chamber, and conditioning policy.
- `tools/smoke_overhang_material_recipes.sh` proves the recipes fail closed if
  flow geometry is removed or a non-PLA family is prematurely marked ready.

The important design boundary is that material selection may alter both the
wave path and the Arc residual path, not just fan or speed. PLA remains the
initial candidate. PETG/PCTG, ABS/ASA, PC, and PA/PPA/CF stay experimental
until their target-printer coupons pass, with PA/PPA/CF requiring dried
material evidence before promotion.

Use this command to rebuild and validate the current material recipe seed:

```bash
./tools/tinmanx.py overhang-material-recipes --check
```

## Slice-Job Recipe Handoff, 2026-06-06

The material recipe seed now reaches the slice contract without enabling native
printer-bound output. `tools/tinmanx_overhang_material_recipe.py` resolves the
selected material from tool assignments and filament profile metadata, then
`tools/create_slice_job.py` stores the selected `overhang_material_recipe` in
the slice-job manifest. `tools/run_slice_job.py` refreshes the same block in
slice results and attaches process-confidence evidence when a dry slice is run.

The runtime handoff carries native Wave Overhang config hints and Arc residual
support parameters, but it deliberately keeps `wave_overhangs=false`,
`enabled_by_default=false`, and `printer_bound_export_allowed=false`. The intent
is to give the next solver step material-specific geometry, flow, speed, cooling,
and residual-support inputs while keeping every exported slice behind an explicit
TinManX validation gate.

`tools/check_overhang_material_recipe_handoff.py` and
`tools/smoke_overhang_material_recipe_handoff.sh` guard that boundary. The smoke
path creates an Arc-support slice job, verifies the handoff in both the job and
result, proves the dry-slice result has runtime evidence, and runs a poison case
that must fail if the native wave flow hint is removed. The current default
RatRig TinMan smoke resolves the selected ABS profile to `ABS_ASA`, with
tight/conservative Arc residual hints.

## Preview Generator Prototype, 2026-06-06

TinManX now has a clean-room, preview-only Andersons-style generator prototype
implemented in `tools/build_wave_overhang_preview.py`. It uses Shapely geometry
operations to expand wavefronts from lower-layer anchor masks and emits:

- preview wave paths with `WAVE_OVERHANG_START` / `WAVE_OVERHANG_END` marker
  accounting
- `wave_covered`, `fallback_supported`, `wave_floor_shadow`,
  `normal_bridge_passthrough`, and `unsupported_overhang` region summaries
- the required coverage metrics from the readiness contract
- source registry and inspected resource provenance copied into the preview
  artifact

The prototype does not import Orca code and does not enable printer-bound
output. `tools/smoke_wave_overhang_preview_generator.sh` proves the current
fixture behavior: one simple straight overhang passes through to normal bridge
handling by default, three harder fixtures generate waves, and the straight
fixture can be forced into wave generation with `--instead-of-bridges`.

## G-code Geometry Bridge, 2026-06-06

The preview generator now accepts `--gcode` as a clean-room bridge from real
sliced output into TinManX's wavefront prototype. The implementation parses only
derived motion facts from the source file: layer comments or Z moves, absolute
or relative XY mode, absolute or relative extrusion mode, `G92 E` resets, and
positive XY extrusion segments. It buffers those segments by the configured line
width to approximate current/lower layer masks, selects either an explicit
`--source-layer-index` or the parsed layer pair with the largest anchored
derived overhang area, and then feeds that geometry into the existing
preview-only wave path generator.

The resulting case records `source_kind=gcode_layer_geometry`, source G-code
path and SHA-256, selected current/lower layer summaries, candidate counts, and
the `positive_extrusion_polyline_buffer` derivation method plus overhang/anchor
area thresholds. This keeps the functional preview tied to real sliced geometry
while preserving the earlier boundary: no OrcaSlicer-WaveOverhangs code import,
no source G-code mutation, and `printer_bound_output_allowed=false`.

`tools/smoke_wave_overhang_preview_generator.sh` now includes a synthetic
two-layer G-code fixture that verifies the parser path selects `gcode_layer_1`,
generates preview wave paths, and preserves source attribution in the artifact.
The smoke also includes a disconnected no-anchor fixture so a large area delta
without lower-layer contact cannot pass candidate selection.

The first real-model checkpoint used
`local-state/slices/main-carriage-arc-support-real-v19-preview-contract/plate_1.gcode`.
With anchored auto-selection over the parsed G-code layers, TinManX selected
`gcode_layer_13` (`z=2.16 mm`) over lower layer 12 (`z=2.0 mm`), recorded
`selected_overhang_area_mm2=652.87454` and
`selected_anchor_area_mm2=1138.8902`, generated 25 preview wave paths, and kept
`printer_bound_output_allowed=false`.

## Real G-code Output Guard, 2026-06-06

William compared a TinManX GUI slice against an OrcaSlicer-Codex GUI slice of
the same intended model setup to use OrcaSlicer-Codex as the no-wave control.
That clarified the product boundary: OrcaSlicer-Codex should not gain Wave
Overhangs; TinManX is the only app where this feature should be implemented.

The comparison exposed the current TinManX gap. The TinManX GUI showed
`support_type=arc(auto)` but did not expose a separate Wave Overhang control,
and the emitted G-code had no `wave_overhangs` settings or native
`WAVE_OVERHANG_*` markers. It still contained ordinary support output:

- TinManX GUI G-code:
  `/var/folders/0n/8rttb2wd2kb17y9g2tnlk7hc0000gn/T/orcaslicer_model/Sat_Jun_06/11_05_28#16289#34/Metadata/.16289.0.gcode`
- selected support settings: `enable_support=1`, `support_type=arc(auto)`,
  `support_style=default`, `support_threshold_angle=30`,
  `tinman_support_strategy=arc`
- Wave Overhang marker count: 0
- ordinary support extrusion: 6,437.45932 mm across 32,715 support moves

`tools/check_wave_overhang_gcode_output.py` now records this as an explicit
real-output gate. The fixture smoke proves three cases: ordinary support with no
wave markers passes only as a no-wave control, synthetic wave G-code without
support passes the wave/no-support guard, and wave-marked G-code that still
contains ordinary support fails when zero support is required.

Useful commands:

```bash
bash ./tools/smoke_wave_overhang_gcode_output_guard.sh
./tools/check_wave_overhang_gcode_output.py --gcode <tinmanx-output.gcode> --expect-wave --max-normal-support-e-mm 0 --max-normal-support-moves 0
./tools/check_wave_overhang_gcode_output.py --gcode <TinManX1-output.gcode> --expect-no-wave
```

This guard does not make Wave Overhangs printer-bound. It prevents TinManX from
claiming GUI-wave behavior until the native wave option and slicer pipeline are
actually wired into the TinManX Orca build.

## Source-Port Scaffold, 2026-06-06

TinManX now carries the first native source scaffold in the nested Orca source
mirror at `local-state/orca-source-full`, copied from
`dennisklappe/OrcaSlicer-WaveOverhangs` `v0.3.2` /
`379c18470f251b3839db12726a2c3a4e4135bfb8`:

- `src/libslic3r/WaveOverhangs/*` is present and listed in
  `src/libslic3r/CMakeLists.txt`
- `PrintConfig.hpp` / `PrintConfig.cpp` now define the wave enums and disabled
  default settings, including `support_remaining_areas_after_wave_overhangs`
- `Tab.cpp` has a `Wave overhangs` settings page, while
  `ConfigManipulation.cpp` hides advanced rows until the master toggle is on
- `scripts/smoke_tinmanx_wave_overhang_scaffold.py` guards source files, CMake,
  config keys, UI rows, visibility gates, debug-marker contract, and attribution

This is deliberately not the geometry handoff yet. Native generated G-code
should still fail the real-output wave/no-support guard until
`PerimeterGenerator`, layer wave-coverage artifacts, support-remainder
subtraction, and Arc residual conversion are wired.

## Native Geometry Handoff, 2026-06-06

The nested TinManX Orca source mirror now has the first compile-validated native
handoff from the copied WaveOverhangs generators into Orca's slicer pipeline:

- `ExtrusionPath` carries a `wave_overhang` tag that is copied through path
  constructors and assignments
- Andersons/Kaiser generated paths are tagged as wave overhang paths
- `PerimeterGenerator` calls the wave generator behind the disabled-by-default
  `wave_overhangs` option, preserves configured outer perimeters, can apply
  wave-specific flow, and records a covered footprint
- `LayerRegion` forwards covered footprints to `Layer::wave_overhang_covered_polygons`
- `SupportMaterial` subtracts those footprints from detected overhang support
  candidates when `support_remaining_areas_after_wave_overhangs` is enabled
- `GCode` can emit `WAVE_OVERHANG_BUILD`, `WAVE_OVERHANG_CONFIG`,
  `WAVE_OVERHANG_START`, and `WAVE_OVERHANG_END` when debug markers are enabled

Validation completed for this checkpoint:

```bash
python3 scripts/smoke_tinmanx_wave_overhang_scaffold.py
python3 -m py_compile scripts/smoke_tinmanx_wave_overhang_scaffold.py
cmake --build build/arm64 --target libslic3r --config Debug -j 4
cmake --build build/arm64 --target OrcaSlicer --config Debug -j 4
bash ./tools/smoke_wave_overhang_gcode_output_guard.sh
```

The linked `src/Debug/OrcaSlicer.app/Contents/MacOS/OrcaSlicer` binary was also
checked with `strings` for `WAVE_OVERHANG_BUILD`, `WAVE_OVERHANG_CONFIG`,
`WAVE_OVERHANG_START`, and `WAVE_OVERHANG_END`.

This still needs real TinManX GUI slice/export proof before it can be called a
functional printer-bound Wave Overhang workflow. The remaining risk is not source
compilation; it is whether an actual exported model shows wave paths, useful
support reduction, clear preview/audit behavior, and no unexpected ordinary
support in a no-fallback hybrid profile.

## Material Wave+Arc Runtime Proof, 2026-06-06

The Release build of the nested Orca source now links successfully and carries
the native wave audit strings plus source attribution:
`dennisklappe/OrcaSlicer-WaveOverhangs tag=v0.3.2
rev=379c18470f251b3839db12726a2c3a4e4135bfb8`.

TinManX now has an explicit `material_wave_arc` solver mode for printer-bound
experiments. The normal material-recipe handoff still remains advisory by
default, but an explicitly requested `material_wave_arc` job promotes the
selected material recipe into the staged Orca process profile with native Wave
settings, Wave debug markers, Arc residual settings, and
`wave_overhangs_instead_of_bridges=1`. The bridge override is intentional for
this solver mode because the source generator otherwise lets simple bridge-like
spans pass back to normal bridge handling.

Current runtime receipts:

- `local-state/jobs/main-carriage-prusa-material-wave-arc-release.wave-audit.json`
  shows `WAVE_OVERHANG_BUILD=1` and `WAVE_OVERHANG_CONFIG=1`, but
  `WAVE_OVERHANG_START=0` / `WAVE_OVERHANG_END=0`; ordinary Orca support remains
  at `154.7663 mm` across `2,031` support moves.
- `local-state/jobs/main-carriage-prusa-material-wave-arc-release-bridgeoverride.wave-audit.json`
  confirms the staged bridge override reached G-code
  (`instead_of_bridges=1`), but Main Carriage still emits no wave paths and keeps
  the same ordinary support amount.
- `local-state/jobs/wave-cantilever-material-wave-arc.wave-audit.json` uses the
  same Release binary and material Wave+Arc route on a controlled cantilever
  fixture, emits `34` `WAVE_OVERHANG_START` markers and `34`
  `WAVE_OVERHANG_END` markers, and leaves ordinary support at `0 mm` / `0`
  moves.

That makes Wave Overhang generation functional in TinManX's native route, but
not yet reliable on the complex Main Carriage geometry. The next Wave checkpoint
should add native generator diagnostics around overhang coverage, bridge/region
selection, seed generation, accumulated region growth, and front-level collapse,
then tune those gates against the Main Carriage receipt before claiming support
elimination beyond controlled fixtures.

## Native Generator Diagnostics, 2026-06-06

The Release Orca binary now emits `WAVE_OVERHANG_DIAG` comments when
`wave_overhang_debug_gcode` is enabled. The diagnostic line is compact and
machine-readable, covering candidate regions, bridge skips, cover/split counts,
seed and accumulated-region failures, front-level collapse, emitted path counts,
areas, and the active bridge override/min-new-area iteration settings. The
top-level G-code checker parses those diagnostics, and Strength Lens carries
them inside the `material_wave_arc_evidence` Process Confidence overlay.

Fresh receipts:

- `local-state/jobs/main-carriage-wave-diagnostics-audit.json` records `62`
  diagnostic lines, `0` start/end wave markers, and ordinary source Orca support
  at `154.7663 mm` across `2,031` moves. Only one diagnostic is nonzero:
  layer `49` sees a tiny `0.009 mm^2` real overhang, splits the cover twice,
  then reports `front_empty=2` and `actual_paths=0`.
- `local-state/jobs/main-carriage-wave-diagnostics-arc-audit.json` confirms the
  Arc-transformed preview G-code still carries those `62` diagnostics and no
  wave paths, while ordinary support extrusion is removed by the Arc transform.
- `local-state/jobs/wave-cantilever-wave-diagnostics-audit.json` remains the
  positive control: `138` diagnostic lines, one nonzero layer (`99`) with
  `candidates=1`, `front_levels=34`, `actual_paths=34`, `filled_area_mm2=606.017`,
  and `0` ordinary support moves.

Interpretation: Main Carriage is no longer a mystery seed/front problem. The
current native handoff gives the Wave generator almost no overhang area to work
with on that geometry, even though Orca's support source pass still finds a real
support burden. The next functional checkpoint is to widen or redirect the
geometry handoff so Wave can receive the same unsupported island/bridge feature
area that currently drives normal/Arc support, then rerun the same diagnostics
before tuning spacing, seeds, or front growth.

## Full-Island Geometry Handoff, 2026-06-06

The next native pass moved outer-perimeter preservation later in the pipeline:
when `wave_overhangs` is enabled, `PerimeterGenerator` now lets the Wave
generator inspect the full island region instead of pre-shrinking the candidate
area by `wave_overhang_outer_perimeters`. Existing perimeter preservation still
happens when clipping ordinary paths in the wave zone, so this change widens
detection without intentionally deleting the user's preserved shells.

Fresh Release receipts:

- `local-state/jobs/main-carriage-wave-unioncoverage-audit.json` records `62`
  diagnostics, `17` start/end wave regions, `17` actual Wave paths,
  `2.957 mm^2` total diagnostic overhang area, and `201.494 mm^2` of generated
  Wave-filled area. Raw ordinary Orca source support drops from `154.7663 mm` /
  `2,031` moves to `119.17829 mm` / `1,633` moves.
- `local-state/jobs/wave-cantilever-wave-unioncoverage-audit.json` remains the
  control proof: `138` diagnostics, one nonzero layer (`99`), `34` start/end
  wave regions, `34` actual paths, `596.0 mm^2` total overhang area,
  `641.526 mm^2` generated Wave-filled area, and `0` ordinary support moves.

A follow-up support-coverage handoff now forwards the union of the conservative
overhang-zone carve and the generated Wave-filled footprint to later support
generation. The filled footprint alone regressed Main Carriage raw support to
`137.21373 mm`; the union handoff preserves the `119.17829 mm` result while
recording the broader generated footprint for support subtraction where it
actually overlaps support contact geometry.

A raw by-layer support audit shows the largest remaining ordinary support on
layers `34`, `37`, `31`, `40`, `43`, `28`, `27`, and `26`, while native Wave
paths currently emit only on layers `1`, `29`, `41`, `42`, and `49`. That layer
offset is the useful clue: the next refactor needs a real support-contact /
projection-to-Wave candidate map, not only a broader footprint subtraction after
Wave paths already exist.

Interpretation: the native Wave route is now alive on the real Main Carriage
model and is reducing raw support, but it is not yet a support-elimination
generator for that geometry. The remaining blocker is still geometry source
quality: Main Carriage's support burden is much larger than the `2.957 mm^2`
currently reaching the Wave generator. The next functional step is to feed Wave
the same top-contact / unsupported feature polygons that Orca's support pass uses
for normal support, or to add an equivalent support-source mask before seed/front
tuning.

Strength Lens caveat: the material Wave+Arc slice result audits the
Arc-transformed preview G-code after normal support has been converted/removed,
so its "no ordinary support" overlay can be true for the transformed artifact
while raw Orca source support still remains. Until the slice result carries both
raw source and transformed audits, the raw Wave audit JSON files above are the
source of truth for remaining ordinary support.

## Support-Style Wave Candidate Mask, 2026-06-06

The next native pass added the equivalent support-source mask noted above. When
native Wave is enabled, `PerimeterGenerator` now builds a Wave lower-layer mask
from Orca's normal-support angle/overlap rule instead of using only the
overhang-wall lower mask expanded by half a nozzle. That lets Wave see the same
shallow unsupported features that normal support would otherwise turn into top
contacts, while keeping the change scoped to the explicit `wave_overhangs` path.

Fresh Release receipts:

- `local-state/jobs/main-carriage-wave-supportmask-audit.json` records `62`
  diagnostics, `238` start/end wave regions, `238` actual Wave paths,
  `22.689 mm^2` total diagnostic overhang area, `2,782.176 mm^2` generated
  Wave-filled area, and `0 mm` / `0` moves of ordinary raw Orca support.
- `local-state/jobs/wave-cantilever-wave-supportmask-audit.json` remains the
  control proof: `138` diagnostics, one nonzero layer (`99`), `34` start/end
  wave regions, `34` actual paths, `598.38 mm^2` total overhang area,
  `643.931 mm^2` generated Wave-filled area, and `0` ordinary support moves.

Operator-review receipts:

- `tools/build_wave_overhang_operator_review.py` now turns a raw Wave audit and
  G-code file into a review JSON/Markdown packet plus per-layer SVG toolpath
  previews. The packet is deliberately not a printer-bound export:
  `printer_bound_output_allowed=false` until visual/toolpath and material review
  are complete.
- `local-state/jobs/main-carriage-wave-supportmask-operator-review.json` reports
  `operator_review_required`, confirms `0 mm` / `0` ordinary support, and flags
  `broad_wave_filled_footprint` because Main Carriage's generated filled area is
  `122.62224x` the detected support-style overhang area. The SVG set in
  `local-state/jobs/main-carriage-wave-supportmask-review-svg/` captures the top
  eight review layers by filled footprint/chord/region count.
- `local-state/jobs/wave-cantilever-wave-supportmask-operator-review.json`
  reports `operator_review_required`, confirms `0 mm` / `0` ordinary support,
  and stays tight at a `1.076124x` filled-to-overhang ratio with one SVG review
  layer (`99`).

Interpretation: this is the first Main Carriage support-elimination proof from
native Wave, not an Arc-transformed preview trick. It should still be treated as
an operator-review candidate rather than a printer-bound release: Main Carriage's
generated Wave-filled footprint is now intentionally broad, so the next gate is
visual/toolpath review of the filled footprint, preserved-shell behavior, and
material-specific speed/flow/cooling before any hardware print.

## Focused-Cover Footprint Tuning, 2026-06-06

The follow-up tuning pass made two changes to reduce the Main Carriage footprint
without losing support elimination:

- `PerimeterGenerator` now hands Wave a support-style candidate window around
  the unsupported source instead of the whole island, preserving nearby anchors
  for seeds while keeping the candidate region bounded.
- The Wave generator now clamps pathological cover components when their cover
  area is more than `20x` the real unsupported source, using a focused margin of
  about two Wave spacings / two line widths. ABS/ASA's material recipe now starts
  with `wave_overhang_max_iterations=1` until broad-footprint receipts pass.

Final Main Carriage receipt:
`local-state/jobs/main-carriage-wave-abscap1-final-audit.json` has `188`
start/end Wave regions, `188` actual Wave paths, the same `22.689 mm^2`
support-style detected overhang area, `1,427.826 mm^2` generated Wave-filled
area, and `0 mm` / `0` ordinary raw support moves. The matching operator packet,
`local-state/jobs/main-carriage-wave-abscap1-final-operator-review.json`, still
reports `operator_review_required` and `broad_wave_filled_footprint`, but the
filled footprint is down from `2,782.176 mm^2` to `1,427.826 mm^2` while support
remains eliminated. The operator packet now also carries an experimental
`support_contact_proxy` receipt: against raw overhang sliver area the Main
Carriage fill ratio is `62.930319x`, but against the Wave-cover/contact proxy it
is `0.517099x` (`1,427.826 mm^2` filled versus `2,761.224 mm^2` reference
area). That does not approve printing, but it explains why the raw ratio is harsh
on long, shallow support-style fringes.

Control and bracket receipts:

- `local-state/jobs/wave-cantilever-wave-focusedcover-final-audit.json` remains
  healthy: `34` Wave paths, `598.38 mm^2` overhang area, `643.931 mm^2` filled
  area, and `0` ordinary support moves.
- A one-spacing focused cover was too tight
  (`local-state/jobs/main-carriage-wave-abscap1-focus1-audit.json`): it emitted
  only `2` Wave paths and left `134.49799 mm` / `1,880` ordinary support moves.
- A `1.5x` focused cover was also too tight
  (`local-state/jobs/main-carriage-wave-abscap1-focus15-audit.json`): it emitted
  only `4` Wave paths and left `134.49414 mm` / `1,879` ordinary support moves.

Interpretation: the current useful bracket is narrow. Two-spacing focused cover
with the ABS/ASA one-iteration cap is the best proven checkpoint: it keeps Main
Carriage support-free and halves the broad footprint, but it is still not
printer-bound. The next pass should tune support-style source selection or
graduate the contact-proxy receipt into a stronger generated support-contact
area check; tightening the focused margin further has already been bracketed as
too aggressive.

## Contact-Proxy Guard and Source-Window Bracket, 2026-06-06

The operator-review packet now treats the Wave-cover/contact proxy as a blocking
guard rather than a passive receipt. `support_contact_proxy.status` is
`guard_passed` or `guard_blocked`, and the default minimum filled/reference
ratio is `0.60x`. The smoke test now includes a no-ordinary-support fixture that
still blocks when Wave fill covers only `0.375x` of the contact proxy, matching
the Main Carriage failure class.

The selected native checkpoint narrows the support-style source handoff from the
earlier three/four-spacing window to a two-spacing/two-flow-width window while
keeping the focused cover margin at the last proven `2.0x` value. The final
Main Carriage packet,
`local-state/jobs/main-carriage-wave-contactguard-sourcewindow2-operator-review.json`,
is intentionally `blocked`: it keeps `0 mm` / `0` ordinary support with `188`
Wave regions, but the contact guard fails at `0.509982x` filled/reference
coverage (`1,407.624 mm^2` filled versus `2,760.147 mm^2` reference area) and
the broad-footprint flag remains at `62.039931x` raw filled/overhang ratio. The
cantilever control,
`local-state/jobs/wave-cantilever-wave-contactguard-sourcewindow2-operator-review.json`,
still passes the guard as `operator_review_required` with `34` Wave paths,
`1.0x` filled/reference coverage, and `0` ordinary support.

A `1.75x` focused-cover experiment is now the lower bracket: it reduced Main
Carriage Wave output to `2` regions, left `134.49799 mm` / `1,880` ordinary
support moves, and failed the contact guard at `0.004534x`. That confirms the
next useful step is not another focused-margin reduction. The next implementation
pass should make the generator's contact-reference area more authoritative:
split or score long shallow support-style fringes before cover expansion, then
only allow support elimination when the generated Wave footprint covers that
reference area without broad connected-island growth.

## Adaptive Fringe Reinforcement, 2026-06-06

The next native pass added per-component Wave diagnostics and a guarded
fringe-reinforcement path:

- `WAVE_OVERHANG_COMPONENT` markers now record candidate index, layer, Wave-cover
  area, filled area, real-overhang area, emitted paths, filled/contact ratio,
  cover/real ratio, and whether fringe filtering or reinforcement was applied.
- The operator-review packet now carries `component_contact_summary`, including
  the worst filled/contact components and counts for active, filtered, and
  reinforced components.
- High-ratio shallow fringe components still receive the two-spacing focused
  cover, but ABS/ASA's `max_iterations=1` cap can get one extra adaptive
  wavefront on those components only. Printer-bound output remains disabled.

Final Main Carriage adaptive-fringe packet:
`local-state/jobs/main-carriage-wave-adaptivefringe-operator-review.json` is now
back to `operator_review_required` instead of `blocked`: ordinary support remains
`0 mm` / `0` moves, the contact guard passes at `0.840307x`, and the run emits
`255` Wave regions / paths across `35` Wave layers. The component receipt shows
`127` active components, `75` fringe-filtered components, and `126`
fringe-reinforced components. The tradeoff is explicit: generated filled area
rose to `2,295.075 mm^2`, so the raw filled/overhang ratio increased to
`101.153643x` and `broad_wave_filled_footprint` still requires visual/toolpath
and material review.

The cantilever control remains healthy at
`local-state/jobs/wave-cantilever-wave-adaptivefringe-operator-review.json`:
`34` Wave paths, `1.0x` filled/contact ratio, `0` ordinary support, and no
fringe reinforcement. Interpretation: adaptive reinforcement solved the
contact-proxy guard without regressing the control, but it did not solve the
broad-footprint risk. The next logical step is to cap or spatially score the
extra reinforced wavefronts so the Main Carriage packet keeps contact coverage
above `0.60x` while reducing the raw footprint back toward the focused-cover
checkpoint.

## Reinforcement ROI Gate, 2026-06-06

The follow-up pass added the first per-component ROI gate for adaptive fringe
reinforcement. Components still qualify only after the high-ratio shallow-fringe
test, but the extra wavefront is now accepted only when the component's
Wave-cover/reference area is no more than `140x` its real unsupported source.
More extreme slivers are marked with `fringe_reject=1` in
`WAVE_OVERHANG_COMPONENT` diagnostics and keep the base one-iteration Wave
coverage.

Final Main Carriage ROI-gated packet:
`local-state/jobs/main-carriage-wave-roigate140-operator-review.json` keeps
ordinary support at `0 mm` / `0` moves and remains `operator_review_required`.
It still clears the contact guard at `0.626893x`, but reduces generated filled
area from the all-adaptive `2,295.075 mm^2` to `1,712.19 mm^2`. The raw
filled/overhang footprint drops from `101.153643x` to `75.46344x`, with `211`
Wave paths, `37` reinforced components, and `89` rejected reinforcement
components. This is still review-only because `broad_wave_filled_footprint`
remains visible, but it is the best current balance between support elimination,
contact coverage, and footprint control.

The cantilever control remains unchanged at
`local-state/jobs/wave-cantilever-wave-roigate140-operator-review.json`: `34`
Wave paths, `1.0x` contact coverage, `0` ordinary support, and no reinforcement
or rejection. Next useful work is to make the `140x` ROI cutoff material/profile
aware and add a second spatial cap for reinforced front length or footprint area
so the Main Carriage raw footprint can keep moving toward the `62x` focused-cover
checkpoint without losing the contact guard again.

## Reinforcement Spatial Cap, 2026-06-06

The second reinforcement gate now caps accepted adaptive fringe components by
post-filter Wave-cover area as well as ROI ratio. A component only receives the
extra adaptive wavefront when `cover_to_real <= 140x` and its post-filter
Wave-cover footprint is no more than `40.5 mm^2`; broader components are counted
with the existing `fringe_reject=1` diagnostic and keep the base one-iteration
coverage.

Final Main Carriage ROI+spatial packet:
`local-state/jobs/main-carriage-wave-roispatialcap-operator-review.json` keeps
ordinary support at `0 mm` / `0` moves and remains `operator_review_required`.
It still clears the contact guard at `0.606481x`, while reducing generated
filled area from the ROI-only `1,712.19 mm^2` to `1,656.44 mm^2`. The raw
filled/overhang footprint drops from `75.46344x` to `73.006303x`, with `205`
Wave paths, `33` reinforced components, and `93` rejected reinforcement
components.

The cantilever control remains unchanged at
`local-state/jobs/wave-cantilever-wave-roispatialcap-operator-review.json`: `34`
Wave paths, `1.0x` contact coverage, `0` ordinary support, and no reinforcement
or rejection. Printer-bound output is still blocked because Main Carriage keeps
the `broad_wave_filled_footprint` review flag. Next useful work is to move the
`140x` ROI cutoff and `40.5 mm^2` spatial cap into the material/profile recipe
space so PLA, PETG/PCTG, ABS/ASA, PC, and PA/PPA/CF can carry different Wave
geometry, speed, flow, and cooling assumptions before coupon testing.

## Material/Profile Reinforcement Caps, 2026-06-06

The ROI and spatial gates are now native Orca process settings instead of
hard-coded Andersons constants. `wave_overhang_fringe_reinforcement_max_cover_to_real`
and `wave_overhang_fringe_reinforcement_max_cover_area` are defined in
`PrintConfig`, surfaced in the Wave settings page, copied into
`WaveOverhangs::CommonParams`, and written by the TinManX material recipe
handoff. The ABS/ASA recipe currently stages the proven Main Carriage values:
`140x` cover/real ROI and `40.5 mm^2` post-filter Wave-cover area.

The handoff also keeps saved native runtime hints ahead of refreshed recipe
defaults, then fills any missing newly added keys from the current material
recipe. This matters because Main Carriage intentionally stays at
`wave_overhang_max_iterations=1`, while the cantilever coupon keeps
`wave_overhang_max_iterations=80`; both still receive the ABS/ASA reinforcement
caps from the refreshed recipe.

Final material-cap packets match the ROI+spatial baselines. Main Carriage
`local-state/jobs/main-carriage-wave-materialcaps-operator-review.json` remains
`operator_review_required`, keeps ordinary support at `0 mm` / `0` moves, emits
`205` Wave paths, and keeps the contact proxy at `0.606481x` with raw
filled/overhang `73.006303x`, `33` reinforced components, and `93` rejected
reinforcement components. The staged process profile records
`wave_overhang_max_iterations=1`, `wave_overhang_fringe_reinforcement_max_cover_to_real=140`,
and `wave_overhang_fringe_reinforcement_max_cover_area=40.5`.

The cantilever control
`local-state/jobs/wave-cantilever-wave-materialcaps-operator-review.json` also
remains `operator_review_required`: `34` Wave paths, `1.0x` contact coverage,
`0` ordinary support, and no reinforcement or rejection. Its staged process
profile records `wave_overhang_max_iterations=80` plus the same ABS/ASA
`140` / `40.5` cap settings. Printer-bound output remains blocked by Main
Carriage's broad-footprint review flag; the next useful pass is material-coupon
planning around per-family speed, flow, cooling, chamber, and conditioning
receipts before any hardware print decision.

## Material Thermal Split + Broad Component Review, 2026-06-07

The material recipe contract now reflects the ABS/ASA/PETG/PC/PPS/PPA bridge
and overhang research pass instead of treating fan and temperature as one global
Wave value. `PPS_PPS_CF` is a separate checked family, with high-temperature
hotend, hardened nozzle, chamber, drying, and vendor-profile receipts. Every
family now carries independent `bridge_fan_peak_percent`,
`overhang_fan_peak_percent`, `wave_fan_peak_percent`, `fan_ramp_policy`, and
bridge/overhang/Wave temperature deltas. Runtime handoff still writes Orca's
native `wave_overhang_fan_speed`, but it is derived from the Wave-specific peak
and the split bridge/overhang peaks stay visible in the result receipt.

The slice-result contract now validates `overhang_material_recipe` whenever it
is present and requires it for `material_wave_arc` results. The guard checks the
advisory-only state, printer-bound block, native Wave disabled-by-default handoff,
Arc residual parameters, split cooling/thermal receipt, and PPS/PPS-CF hardware
receipts.

Operator review also gained component-level broad-footprint scoring. The review
packet now reports `broad_wave_cover_to_real_component_count`,
`unrejected_broad_wave_cover_component_count`, and a review-only
`broad_wave_component_footprint` flag when a specific component exceeds the
cover/real threshold. This makes Main Carriage-style broad footprints actionable
by component candidate instead of relying only on the global filled/overhang
ratio.

Validation:

```bash
python3 -m py_compile tools/build_overhang_material_recipes.py tools/check_overhang_material_recipes.py tools/tinmanx_overhang_material_recipe.py tools/check_overhang_material_recipe_handoff.py tools/check_slice_result_contract.py tools/build_wave_overhang_operator_review.py
bash ./tools/smoke_overhang_material_recipes.sh
bash ./tools/smoke_overhang_material_recipe_handoff.sh
bash ./tools/smoke_material_wave_arc_solver_mode.sh
bash ./tools/smoke_wave_overhang_operator_review.sh
./tools/tinmanx.py overhang-material-recipes --check
git diff --check
```

## Contact-Margin-Aware Broad Gate Tuning, 2026-06-07

The component-level broad-footprint review now emits a machine-readable
`component_gate_tuning` block instead of only listing offending components. The
block records the current material/profile caps, broad cleanup cap candidates,
estimated affected layers/area, the support-contact proxy margin, and a
recommended next cap. It uses the exact `cover_to_real` and `filled_to_cover`
values from `WAVE_OVERHANG_COMPONENT` markers when present; this avoids
overstating component ratios by recomputing from rounded area fields. When the
contact proxy has less than `0.02x` guard margin, the recommendation becomes a
one-component probe instead of a broad cleanup jump. When less than `0.002x`
margin remains, the packet stops recommending further cap-only probes.

The real Main Carriage material-cap packet shows why this matters:

- baseline packet: `local-state/jobs/main-carriage-wave-materialcaps-operator-review.json`
- current caps: `140x` cover/real and `40.5 mm^2` cover area
- ordinary support: `0 mm` / `0` moves
- contact proxy: `0.606481x`, only `0.006481x` above the `0.60x` guard
- broad components: `116`, with `25` unrejected by the current fringe gate
- cap recommendations: one-component probe `138.188x`, broad-cleanup `100x`,
  near-complete `80x`, clear-all `40x`

The corrected one-component probe is the only cap-only reduction that still
passes the current contact guard:

- job/result: `local-state/jobs/main-carriage-wave-materialcaps-probe138188.slice-job.json`
  and `local-state/jobs/main-carriage-wave-materialcaps-probe138188.slice-result.json`
- operator packet:
  `local-state/jobs/main-carriage-wave-materialcaps-probe138188-operator-review.json`
- ordinary support remains eliminated: `0 mm` / `0` moves
- Wave regions stay at `205`
- unrejected broad components drop from `25` to `24`
- contact proxy drops to `0.600803x`, leaving only `0.000803x` margin
- packet status stays `operator_review_required`, but
  `component_gate_tuning.contact_margin_status=exhausted`

An executed cap-100 run proves that larger cap-only cleanup is too aggressive at
the current contact margin:

- job/result: `local-state/jobs/main-carriage-wave-materialcaps-cap100.slice-job.json`
  and `local-state/jobs/main-carriage-wave-materialcaps-cap100.slice-result.json`
- operator packet:
  `local-state/jobs/main-carriage-wave-materialcaps-cap100-operator-review.json`
- ordinary support remains eliminated: `0 mm` / `0` moves
- Wave regions drop from `205` to `198`
- unrejected broad components drop from `25` to `15`
- contact proxy drops to `0.568741x`, so the packet is `blocked`

Interpretation: tightening the cover/real cap can reduce broad accepted
reinforcement, but Main Carriage currently has too little contact margin for a
second cap-only step. The next native pass should add contact compensation for
rejected reinforcement, or relax another geometry constraint, before trying
`100x`, `80x`, or `40x` cleanup caps.

Validation:

```bash
python3 -m py_compile tools/build_wave_overhang_operator_review.py
bash ./tools/smoke_wave_overhang_operator_review.sh
./tools/check_slice_result_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-cap100.slice-result.json
./tools/check_support_strategy_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-cap100.slice-result.json --expected-style arc --expected-arc-status experimental_transform_blocked --expected-arc-threshold-angle 50 --expected-arc-spacing-profile tight --expected-arc-motion-profile conservative --expected-overhang-solver-mode material_wave_arc --expected-material-recipe-family ABS_ASA --expected-arc-transform-stage-status blocked --require-ok --require-runtime-process-settings --require-no-arc-transformed-gcode-files --require-selected-gcode-untransformed
./tools/check_wave_overhang_gcode_output.py --gcode local-state/slices/main-carriage-wave-materialcaps-cap100/plate_1.gcode --expect-wave --max-normal-support-e-mm 0 --max-normal-support-moves 0
./tools/check_slice_result_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-probe138188.slice-result.json
./tools/check_support_strategy_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-probe138188.slice-result.json --expected-style arc --expected-arc-status experimental_transform_blocked --expected-arc-threshold-angle 50 --expected-arc-spacing-profile tight --expected-arc-motion-profile conservative --expected-overhang-solver-mode material_wave_arc --expected-material-recipe-family ABS_ASA --expected-arc-transform-stage-status blocked --require-ok --require-runtime-process-settings --require-no-arc-transformed-gcode-files --require-selected-gcode-untransformed
./tools/check_wave_overhang_gcode_output.py --gcode local-state/slices/main-carriage-wave-materialcaps-probe138188/plate_1.gcode --expect-wave --max-normal-support-e-mm 0 --max-normal-support-moves 0
```

## Rejected-Fringe Contact Compensation, 2026-06-07

The next native pass adds a small contact-preservation path for fringe
components that are rejected only slightly above the current material/profile
cover/real cap. The new process setting is
`wave_overhang_fringe_contact_compensation_max_over_cap`; for ABS/ASA the
recipe stages `2.0`, meaning a rejected component can receive one half-spacing
compensation front only when it is within two cover/real points above the active
cap and still satisfies the `40.5 mm^2` area cap. This keeps the broad-footprint
gate material-aware instead of hard-coding another Andersons constant.

The diagnostics now expose both region and component evidence:

- `WAVE_OVERHANG_DIAG` includes `fringe_contact_compensated`.
- `WAVE_OVERHANG_COMPONENT` includes `fringe_compensate`.
- `tools/build_wave_overhang_operator_review.py` reports compensated
  region/component counts and keeps printer-bound output blocked until visual,
  toolpath, and material review pass.

Fresh Main Carriage result:

- job/result:
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe138188.slice-job.json`
  and
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe138188.slice-result.json`
- operator packet:
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe138188-operator-review.json`
- ordinary support remains eliminated: `0 mm` / `0` moves
- Wave regions rise from `205` to `206`
- contact proxy improves from `0.600803x` to `0.603861x`
- compensated regions/components: `1` / `1`
- broad components remain `116`, with `24` still unrejected
- `component_gate_tuning.contact_margin_status=thin`

Interpretation: the compensation hook gives back enough contact margin to leave
the exhausted state, but it is still not enough for a broad cleanup jump. A
follow-up one-component probe lowered the ratio cap from `138.188x` to
`137.49x` while keeping compensation enabled:

- job/result:
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe13749.slice-job.json`
  and
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe13749.slice-result.json`
- operator packet:
  `local-state/jobs/main-carriage-wave-materialcaps-comp2-probe13749-operator-review.json`
- ordinary support remains eliminated: `0 mm` / `0` moves
- Wave regions rise to `207`
- contact proxy is `0.601295x`
- compensated regions/components: `2` / `2`
- unrejected broad components drop to `23`
- `component_gate_tuning.contact_margin_status=exhausted`

That is the current cap-only stopping point. The next exact cap candidate is
`136.882x`, but the packet no longer recommends another cap-only probe because
only `0.001295x` contact margin remains. Larger cleanup caps such as `100x` or
`80x` remain blocked until another contact-preserving geometry rule, visual
toolpath review, or material coupon evidence improves the guard margin.

Validation:

```bash
python3 -m py_compile tools/build_overhang_material_recipes.py tools/check_overhang_material_recipes.py tools/tinmanx_overhang_material_recipe.py tools/check_overhang_material_recipe_handoff.py tools/check_slice_result_contract.py tools/check_wave_overhang_gcode_output.py tools/build_wave_overhang_operator_review.py
bash ./tools/smoke_overhang_material_recipes.sh
bash ./tools/smoke_overhang_material_recipe_handoff.sh
bash ./tools/smoke_material_wave_arc_solver_mode.sh
bash ./tools/smoke_wave_overhang_operator_review.sh
./tools/tinmanx.py overhang-material-recipes --check
cmake --build build/arm64 --config Release --target OrcaSlicer -j 4
./tools/check_slice_result_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-comp2-probe138188.slice-result.json
./tools/check_support_strategy_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-comp2-probe138188.slice-result.json --expected-style arc --expected-arc-status experimental_transform_blocked --expected-arc-threshold-angle 50 --expected-arc-spacing-profile tight --expected-arc-motion-profile conservative --expected-overhang-solver-mode material_wave_arc --expected-material-recipe-family ABS_ASA --expected-arc-transform-stage-status blocked --require-ok --require-runtime-process-settings --require-no-arc-transformed-gcode-files --require-selected-gcode-untransformed
./tools/check_wave_overhang_gcode_output.py --gcode local-state/slices/main-carriage-wave-materialcaps-comp2-probe138188/plate_1.gcode --expect-wave --max-normal-support-e-mm 0 --max-normal-support-moves 0
./tools/check_slice_result_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-comp2-probe13749.slice-result.json
./tools/check_support_strategy_contract.py --result local-state/jobs/main-carriage-wave-materialcaps-comp2-probe13749.slice-result.json --expected-style arc --expected-arc-status experimental_transform_blocked --expected-arc-threshold-angle 50 --expected-arc-spacing-profile tight --expected-arc-motion-profile conservative --expected-overhang-solver-mode material_wave_arc --expected-material-recipe-family ABS_ASA --expected-arc-transform-stage-status blocked --require-ok --require-runtime-process-settings --require-no-arc-transformed-gcode-files --require-selected-gcode-untransformed
./tools/check_wave_overhang_gcode_output.py --gcode local-state/slices/main-carriage-wave-materialcaps-comp2-probe13749/plate_1.gcode --expect-wave --max-normal-support-e-mm 0 --max-normal-support-moves 0
git diff --check
```
