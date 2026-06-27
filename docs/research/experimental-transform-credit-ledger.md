# Experimental Transform Credit Ledger

Updated: `2026-05-19`

This ledger keeps TinManX's support-elimination research honest. Arc Support,
Wave Overhangs, conical/non-planar slicing, and brick-layer interlocks are
different ideas with different authors, licenses, risks, and validation needs.
Any TinManX feature that uses one of these ideas must preserve the source trail
from research note to slice result to preview/report metadata.

## Source Registry

| Registry ID | Lane | Credit / Source | URL | Current TinManX Use | Gate Before Printer-Bound Output |
| --- | --- | --- | --- | --- | --- |
| `arc-overhang:stmcculloch/original` | Arc Support | Steven McCulloch, original arc-overhang concept | <https://github.com/stmcculloch/arc-overhang> | Credited predecessor for Arc Support scaffold transforms. | Keep operator-test only until arc insertion and bridge replacement are audited. |
| `arc-overhang:nicolai-wachenschwan/prusaslicer` | Arc Support | Nicolai Wachenschwan, PrusaSlicer arc-overhang integration | <https://github.com/nicolai-wachenschwan/arc-overhang-prusaslicer-integration> | Credited integration path used by later Orca work. | Preserve attribution and inspect assumptions before adapting behavior. |
| `arc-overhang:kelsch/orcaslicer` | Arc Support | Kelsch OrcaSlicer / SoftFever integration | <https://github.com/Kelsch/arc-overhang-orcaslicer-integration> | Candidate GPL transform source for Orca-style bridge/overhang G-code. | Bundle GPL source, remove interactive/plotting paths, write controlled-output audit. |
| `wave-overhang:dennisklappe/orcaslicer` | Wave Overhangs | dennisklappe OrcaSlicer-WaveOverhangs fork | <https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs> | Research watch and future source-adapter candidate; inspected local v0.3.2 app and source tag are recorded in the Wave Overhang readiness manifest. | Keep opt-in/experimental; prove geometry limits, preview markers, fallback supports, and AGPL-3.0-or-later import strategy. |
| `wave-overhang:stmcculloch/prusaslicer` | Wave Overhangs | Steven McCulloch, PrusaSlicer-WaveOverhangs port lineage | <https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs> | Credited Andersons-port lineage referenced by the Orca wave fork. | Preserve lineage if any algorithm behavior is adapted. |
| `wave-overhang:andersons/research` | Wave Overhangs | Janis A. Andersons et al., wave-inspired overhang research | <https://doi.org/10.2139/ssrn.6640458> | Conceptual basis for lateral wave propagation over unsupported spans. | Treat as research-prior until TinManX validates materials, cooling, span limits, and surface tradeoffs. |
| `wave-overhang:kaiser-laso/research` | Wave Overhangs | Rieks Kaiser LaSO algorithm / thesis code lineage | <https://github.com/riekskaiser/wave_LaSO> | Research watch for alternate lateral-support propagation. | Keep simple-geometry only until complex overhang reliability is proven. |
| `conical-slicing:cnckitchen-guide` | Conical / Non-planar | Stefan Hermann / CNC Kitchen conical slicing guide | <https://www.cnckitchen.com/blog/guide-how-to-use-conical-slicing> | Workflow source for STL transform, slice, then G-code back-transform gates. | Require toolhead clearance, centered-origin handling, refined mesh checks, and macro lint. |
| `conical-slicing:rotbot-transform-scripts` | Conical / Non-planar | RotBotSlicer Transform variable-angle scripts | <https://github.com/RotBotSlicer/Transform/tree/master/Scripts%20for%20Variable%20Angle> | External transform reference for variable-angle STL and G-code transformation. | Do not bundle or execute until license/source snapshot and noninteractive wrapper are audited. |
| `conical-slicing:zhaw-variable-angle` | Conical / Non-planar | ZHAW variable-angle transformation work referenced by CNC Kitchen | <https://www.zhaw.ch/> | Upstream research credit for the conical workflow chain. | Preserve credit when describing the technique; verify exact code provenance before import. |
| `brick-layer:cnckitchen` | Brick-layer Interlock | CNC Kitchen brick-layer strength experiments | <https://www.cnckitchen.com/blog/brick-layers-make-3d-prints-stronger> | Research watch for interlocking layer/failure-plane shifting. | Keep off by default; require clearance envelope, surface-finish preview, and load-case declaration. |

## Implementation Rules

- Slice results must carry `material_strength.layer_interface_guidance.experimental_toolpath_transform_lanes[].source_registry` for every experimental transform lane.
- Strength Lens overlays must expose `source_registry` in overlay details so Preview can surface where the idea came from.
- Reports must preserve source cues even when top-cue ordering changes; source-backed credits should not disappear because a new warning was added.
- Direct code import requires a source snapshot, license file, dependency manifest, noninteractive wrapper, and smoke/audit proof.
- Research-inspired behavior that does not copy code still needs a source-registry ID and an explicit `research_watch`, `experimental_operator_review`, or `hardware_candidate` status.
- Any inspected downloaded artifact or source tag that influences implementation
  decisions must be recorded as structured provenance with artifact identity,
  commit/SHA when available, use scope, and linked source-registry IDs.
- Any public TinManX release note/About page should credit source authors for the transform lanes that are visible in the app, even if the lane remains disabled or advisory-only.
- Saved experimental transform projects must use
  `schemas/slicing/experimental-transform-project.schema.json` so source IDs,
  safety gates, and share-safe artifact policy travel with the project file.

## Source Snapshots

- Arc Overhang source snapshot:
  `docs/research/arc-overhang-source-snapshot-2026-05-08.md`
- Wave Overhang source snapshot:
  `docs/research/wave-overhang-source-snapshot-2026-05-19.md`
- Conical / RotBot source snapshot:
  `docs/research/conical-rotbot-source-snapshot-2026-05-19.md`

## Current TinManX Mapping

- `arc_support_scaffold` remains selectable for operator testing, but printer-bound trust is blocked until transform proof shows inserted arc markers, intended bridge replacement, and zero machine-start/toolchange mutation.
- `wave_overhang_compensation` is a preview/audit research lane. The Orca wave fork reports support-free 90 deg cantilever experiments, but also marks the work alpha and PLA/cooling-sensitive, so TinManX must not treat it as universal support replacement yet.
- `conical_nonplanar_slicing` is a hardware-candidate lane. CNC Kitchen's workflow notes that `G1` start-code moves are transformed while `G0` moves are ignored by the back-transform script, so TinManX's macro linter must catch start-code assumptions before output can be trusted.
- `brick_layer_interlock` is a research-watch lane. It may complement strength and support-elimination work, but it modifies layer interfaces and clearance assumptions, so it stays load-case gated.

## Generated Artifacts

- About/Credits export:
  `tools/build_experimental_transform_credits.py` writes
  `local-state/experimental-transform-credits.json` and
  `docs/app/experimental-transform-credits.md`.
- Transform project manifest:
  `tools/build_experimental_transform_project.py` writes
  `local-state/experimental-transform-project.json`, checked by
  `tools/check_experimental_transform_project.py`.

## Next Ledger Tasks

- Add adapter design docs for Wave Overhangs and RotBot Transform before any code import begins.
