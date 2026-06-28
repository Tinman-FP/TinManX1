# TinManX1 Feature Attribution

This note tracks external feature sources ported into the TinManX1 source branch.

## Wave Overhangs

- Source: `dennisklappe/OrcaSlicer-WaveOverhangs`
- Upstream URL: `https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs`
- Ported source snapshot: `v0.3.2` / `379c18470f251b3839db12726a2c3a4e4135bfb8`
- Algorithm credit: Janis A. Andersons (`andersonsjanis`) for the Andersons wave-overhang algorithm.
- Algorithm credit: Rieks Kaiser (`riekskaiser`) for Kaiser LaSO wave-overhang reference work.
- OrcaSlicer port credit: Dennis Klappe (`dennisklappe`) and WaveOverhangs contributors.

The TinManX1 port keeps Wave Overhangs disabled by default and emits `WAVE_OVERHANG_*` debug markers for inspection when enabled.

## Arc Overhangs

- Source: Kelsch OrcaSlicer integration of Arc Overhangs.
- Port source note: sanitized local working copy of the Kelsch Arc Overhang OrcaSlicer integration.
- Ported source revision: `0693ef29a0eb3e96fdc336841cd714e071f3ed9a`
- License: GPL-3.0, vendored under `third_party/gpl/arc-overhang`.
- Concept credit: Steven McCulloch / layershift3d Arc Overhang concept.
- Integration credit: Nicolai Wachenschwan PrusaSlicer integration.
- OrcaSlicer integration credit: Kelsch OrcaSlicer integration.

The TinManX1 port keeps the upstream bridge/overhang-infill model: bridge-derived overhang source paths are replaced by guarded `Arc infill` output. Ordinary support extrusion is not a source path and must not be exported as Arc Overhang output.

## Strength Lens

- Source: prior local TinManX Strength Lens sidecar work.
- Port source note: sanitized local TinManX Strength Lens sidecar source.
- Ported Codex entrypoint: `scripts/orcaslicer_codex_strength_lens_sidecar.py`
- Reference credit: MechaniCalc Strength of Materials (`https://mechanicalc.com/reference/strength-of-materials`) for advisory load-case and stress-language vocabulary.
- Reference credit: Autodesk Fusion 360 Simulation learning path (`https://www.autodesk.com/learn/ondemand/curated/getting-started-with-simulation/KW9u4cqugIm75g2EoAc9q`) for future solver workflow vocabulary.
- Reference credit: SOLIDWORKS FEM/numerical-method explanation (`https://blogs.solidworks.com/tech/2019/10/fem-analysis-do-not-be-afraid-of-numerical-methods-when-calculating-strength.html`) for mesh/load/restraint framing.
- Reference credit: SOLIDWORKS Simulation analysis concepts (`https://help.solidworks.com/2024/english/Solidworks/cworks/c_Basic_Concepts_of_Analysis.htm`) for separating pre-solve study setup from solved stress results.
- Reference credit: FDM anisotropy literature, including open-access additive-manufacturing studies on build orientation and layer-driven mechanical-property directionality (`https://www.mdpi.com/2504-4494/3/3/64`, `https://pmc.ncbi.nlm.nih.gov/articles/PMC11207998/`).
- Reference credit: Oak Ridge National Laboratory extrusion-anisotropy summary (`https://www.ornl.gov/publication/reducing-mechanical-anisotropy-extrusion-based-printed-parts`) for the practical assumption that printed X/Y-plane roads are usually stronger than Z-direction layer bonds in extrusion-based printing.

The TinManX1 port emits advisory-only viewport metadata. The Prepare view now supports a selectable Strength Lens load axis (`Auto`, `X`, `Y`, `Z`) and treats normal FDM as stronger in X/Y than through the Z layer stack. It does not modify slicing, emit G-code, certify FEA, approve prints, or claim structural safety factors.

## FibreSeek / Continuous Fiber Planning

- Source: prior local TinManX FibreSeek metadata sidecar work.
- Source: TinManX1 native planner, profile generator, comparison, and audit work developed from William Tinney's FibreSeek workflow requirements and local validation.
- Port source note: sanitized local TinManX FibreSeek metadata sidecar source plus TinManX1-owned native planner tooling.
- Ported Codex entrypoint: `scripts/orcaslicer_codex_fiber_metadata_sidecar.py`
- Native planner entrypoint: `scripts/orcaslicer_codex_native_fiber_planner.py`
- Validation entrypoints: `scripts/audit_fiberseek_gcode_contract.py`, `scripts/check_tinmanx1_fiber_wiring.py`, and `scripts/compare_fiberseek_gcode.py`
- Local reference boundary: Rocket/FibreSeek behavior was used only as private interoperability evidence for command sequencing, profile comparison, and hardware constraints. Proprietary Rocket/FibreSeek assets, databases, UI strings, and private G-code exports are not redistributed.

The TinManX1 port preserves continuous-fiber lane metadata and review gates for Preview/Summary use. The native planner emits experimental FibreSeek-style command blocks and summaries, but it does not certify hardware readiness, start uploads, or replace real-machine qualification.
