# Attribution

This repository preserves source credit for the TinManX1 public patch release. It is intentionally explicit because the work combines upstream slicer lineage, experimental overhang research, local app-integration work, and Codex-assisted implementation.

## Project Stewardship

| Person / group | Credit |
| --- | --- |
| William Tinney / Tinman-FP | Project owner, requirements, printer workflow direction, local testing, validation feedback, release stewardship, and decision authority for what becomes public. |
| OpenAI Codex | Engineering assistant for code organization, implementation support, patch review, documentation, verification scripts, release packaging, and attribution cleanup. |

## Primary Slicer Lineage

| Source | URL | Credit |
| --- | --- | --- |
| OrcaSlicer / SoftFever and contributors | <https://github.com/OrcaSlicer/OrcaSlicer> | Primary upstream application and source baseline for this patchset. Preserve AGPL license, upstream notices, and contributor credit. |
| Bambu Studio / Bambu Lab contributors | <https://github.com/bambulab/BambuStudio> | Upstream family member and connectivity behavior reference. Proprietary plugin binaries are not redistributed here. |
| PrusaSlicer / Prusa Research contributors | <https://github.com/prusa3d/PrusaSlicer> | Upstream slicer family lineage and behavior reference. |
| Slic3r contributors | <https://github.com/slic3r/Slic3r> | Original slicer lineage behind PrusaSlicer-derived slicers. |

## Wave Overhangs

| Source | URL | Credit |
| --- | --- | --- |
| Dennis Klappe, OrcaSlicer-WaveOverhangs | <https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs> | OrcaSlicer Wave Overhangs fork and practical Orca integration reference. |
| Steven McCulloch, PrusaSlicer-WaveOverhangs | <https://github.com/stmcculloch/PrusaSlicer-WaveOverhangs> | PrusaSlicer wave-overhang lineage referenced by the Orca fork. |
| Janis A. Andersons et al. | <https://doi.org/10.2139/ssrn.6640458> | Wave-inspired overhang research lineage. |
| Rieks Kaiser, LaSO | <https://github.com/riekskaiser/wave_LaSO> | Laterally supported overhang algorithm reference. |

## Arc Supports

| Source | URL | Credit |
| --- | --- | --- |
| Steven McCulloch, arc-overhang | <https://github.com/stmcculloch/arc-overhang> | Original arc-overhang concept and transform lineage. |
| Nicolai Wachenschwan, PrusaSlicer arc-overhang integration | <https://github.com/nicolai-wachenschwan/arc-overhang-prusaslicer-integration> | PrusaSlicer integration path and prior implementation context. |
| Kelsch, OrcaSlicer arc-overhang integration | <https://github.com/Kelsch/arc-overhang-orcaslicer-integration> | Orca-style bridge/overhang transform reference used for Codex Arc Support research and adapter work. |

## Printer And Device Integration

| Source | URL | Credit |
| --- | --- | --- |
| Klipper | <https://github.com/Klipper3d/klipper> | Printer control context for Klipper-backed devices. |
| Moonraker | <https://github.com/Arksine/moonraker> | HTTP/WebSocket API context for Moonraker-backed printer device paths. |
| QIDI, Creality, Elegoo/Centauri, Snapmaker, Prusa printer ecosystems | Vendor ecosystems and local device behavior used as compatibility targets. No vendor affiliation is claimed. |

## Strength Lens And Materials Research

| Source | URL | Credit |
| --- | --- | --- |
| CNC Kitchen / Stefan Hermann | <https://www.cnckitchen.com/> | Expert-channel research context for material strength, calibration, infill, drying, nozzle behavior, and process limits. |
| ModBot | <https://www.youtube.com/@ModBotArmy> | Expert-channel research context for calibration workflow and slicer/printer setup. |
| Autodesk Fusion documentation | <https://www.autodesk.com/products/fusion-360/overview> | Visual-language reference for simulation-style interpretation. Codex Strength Lens is not Fusion FEA. |
| MechaniCalc | <https://mechanicalc.com/reference/strength-of-materials> | Mechanics vocabulary and load-path reference. |
| Rocket/FibreSeek local reference work | Proprietary/local reference only | Used as private interoperability and planning context for command sequencing, profile comparison, and hardware constraints. No proprietary Rocket/FibreSeek assets, binaries, database exports, UI text, or private validation data are redistributed here. |

## TinManX1 FibreSeek Planner And Profile Work

| Source | Credit |
| --- | --- |
| William Tinney / Tinman-FP | Requirements, FibreSeek workflow direction, material/profile priorities, UI review, slice validation, Rocket/TinManX1 comparison direction, and decisions about acceptable public scope. |
| OpenAI Codex | Implementation assistance for the native planner, G-code contract checks, FibreSeek profile generation/linting, comparison tooling, documentation, and release hygiene. |
| TinManX1 local validation sessions | Visual and G-code review that shaped the 55 mm route floor, small-hole handling, alternating CFC paths, fiber preview/summary behavior, and the decision to disable unsafe cluster/racetrack emission until machine testing proves a stronger containment model. |

## Additional Ledgers

- `docs/attribution/source-credit-ledger-2026-06.md`
- `docs/research/experimental-transform-credit-ledger.md`
- `docs/research/wave-overhang-source-snapshot-2026-05-19.md`
- `docs/research/arc-overhang-source-snapshot-2026-05-08.md`

If a future change adapts additional code or research, add it here before release.
