# TinManX1 Feature Attribution

This note tracks external feature sources ported into the TinManX1 source branch.

## Wave Overhangs

- Source: `dennisklappe/OrcaSlicer-WaveOverhangs`
- Upstream URL: `https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs`
- Ported source snapshot: `v0.4.0` / `f6a901d57cd128c922c81591ceae4fd0b7cc5524`
- Research credit: Janis A. Andersons, Salome Sanchez, and Tom Vaneker for the wave-inspired path-planning method published in *Additive Manufacturing Letters* (`10.1016/j.addlet.2026.100392`).
- Algorithm credit: Janis A. Andersons (`andersonsjanis`) for the wavefront generator used by the current implementation.
- OrcaSlicer port credit: Dennis Klappe (`dennisklappe`) and WaveOverhangs contributors.

The TinManX1 port keeps Wave Overhangs disabled by default, follows the upstream `v0.4.0` single-wavefront contract, and emits firmware-safe `WAVE_OVERHANG_*` diagnostics outside the G-code header when debug output is enabled. TinManX1 retains its hybrid-support remainder handling, fringe filtering, reinforcement, fallback seeding, and route diagnostics while adding upstream solid backing floors for angled overhangs, gradual floor-speed recovery, independent main/auxiliary cooling, temperature restoration, travel control, dwell timing, and end retraction.

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
- Ported Codex entrypoint: `scripts/source-helpers/orcaslicer_codex_strength_lens_sidecar.py`
- Reference credit: MechaniCalc Strength of Materials (`https://mechanicalc.com/reference/strength-of-materials`) for advisory load-case and stress-language vocabulary.
- Reference credit: Autodesk Fusion 360 Simulation learning path (`https://www.autodesk.com/learn/ondemand/curated/getting-started-with-simulation/KW9u4cqugIm75g2EoAc9q`) for future solver workflow vocabulary.
- Reference credit: SOLIDWORKS FEM/numerical-method explanation (`https://blogs.solidworks.com/tech/2019/10/fem-analysis-do-not-be-afraid-of-numerical-methods-when-calculating-strength.html`) for mesh/load/restraint framing.
- Reference credit: SOLIDWORKS Simulation analysis concepts (`https://help.solidworks.com/2024/english/Solidworks/cworks/c_Basic_Concepts_of_Analysis.htm`) for separating pre-solve study setup from solved stress results.
- Reference credit: FDM anisotropy literature, including open-access additive-manufacturing studies on build orientation and layer-driven mechanical-property directionality (`https://www.mdpi.com/2504-4494/3/3/64`, `https://pmc.ncbi.nlm.nih.gov/articles/PMC11207998/`).
- Reference credit: Oak Ridge National Laboratory extrusion-anisotropy summary (`https://www.ornl.gov/publication/reducing-mechanical-anisotropy-extrusion-based-printed-parts`) for the practical assumption that printed X/Y-plane roads are usually stronger than Z-direction layer bonds in extrusion-based printing.

The TinManX1 port emits advisory-only viewport metadata. The Prepare view now supports a selectable Strength Lens load axis (`Auto`, `X`, `Y`, `Z`) and treats normal FDM as stronger in X/Y than through the Z layer stack. It does not modify slicing, emit G-code, certify FEA, approve prints, or claim structural safety factors.

## FibreSeek / Continuous Fiber Metadata

- Source: prior local TinManX FibreSeek metadata sidecar work.
- Port source note: sanitized local TinManX FibreSeek metadata sidecar source.
- Ported Codex entrypoint: `scripts/source-helpers/orcaslicer_codex_fiber_metadata_sidecar.py`

The TinManX1 port preserves continuous-fiber lane metadata and review gates for Preview/Summary use. It does not emit machine commands, start uploads, or mark hardware validation as complete.

## Auto Pressure Advance / Max Flow Preflight

- Source: TinManX1 same-print calibration requirements from William Tinney's Qidi Plus 4, Max EZ, RatRig V-Core 4 IDEX, and Prusa Core One workflows.
- Reference credit: CNC Kitchen pressure-advance and volumetric-flow testing methodology, Klipper pressure-advance documentation, Marlin Linear Advance documentation, and Prusa pressure-advance behavior as calibration references.
- Project credit: William Tinney / Tinman-FP for printer fleet requirements, calibration-region constraints, Beacon-assisted measurement direction, and live G-code export validation.
- Implementation credit: OpenAI Codex / GPT-5 for the TinManX1 postprocessor wrapper, real-score gating, RatRig T0/T1 detection, max-flow governor integration path, visible calibration-lane gate, profile hook, and verification scaffolding.

The TinManX1 auto-PA path only applies PA, adaptive PA, or max-flow changes when real same-print calibration score files are available for the detected target printer and a named TinMan calibration lane is visible in the sliced object list. Without real scores or a visible edge-strip lane, it preserves the model G-code and emits an audit stamp rather than applying hidden or synthetic calibration data.
