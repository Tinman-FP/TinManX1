# TinManX1 Source Credit Ledger - June 2026

Generated: 2026-06-18

## Upstream Lineage

| Source | URL | Use / credit |
| --- | --- | --- |
| OrcaSlicer / SoftFever and contributors | <https://github.com/OrcaSlicer/OrcaSlicer> | Primary upstream slicer/app lineage. Preserve AGPL, notices, and upstream attribution. |
| Bambu Studio / Bambu Lab contributors | <https://github.com/bambulab/BambuStudio> | Upstream family member and connectivity/plugin behavior reference. Treat proprietary or closed plugin behavior with caution. |
| PrusaSlicer / Prusa Research contributors | <https://github.com/prusa3d/PrusaSlicer> | Upstream slicer family lineage and PrusaLink/profile behavior reference. Preserve AGPL attribution. |
| Slic3r contributors | <https://github.com/slic3r/Slic3r> | Original lineage behind PrusaSlicer-derived slicers. Credit in family-tree explanations. |
| Klipper | <https://github.com/Klipper3d/klipper> | Printer control context for Klipper-backed devices shown in TinManX1. |
| Moonraker | <https://github.com/Arksine/moonraker> | Device/API context for Moonraker-backed printers. |

## Local Device And App Provenance

| Source | Role | Handling |
| --- | --- | --- |
| TinManX1 app-support data | Live profile and host persistence surface. | Do not publish full app-support trees or secrets. Use small fixtures/smoke data. |
| Installed app bundle | Final validation target for repair tools and launchers. | Do not commit app bundles, native plugins, or generated build artifacts. |
| Centauri Carbon, Qidi, Prusa, K2, Snapmaker live devices | Printer-host/profile behavior reference. | Keep canonical identity and temporary reachability separate. |
| TinManX repair tools | Shared app/profile repair logic where tools live in TinManX but protect TinManX1. | Document cross-repo dependency and keep product features separated. |
| Rocket/FibreSeek local comparison work | Private interoperability reference for command sequencing, profile settings, and hardware constraints. | Do not publish proprietary Rocket/FibreSeek assets, databases, UI text, private G-code exports, or validation data. Publish only clean-room behavior summaries and TinManX1-owned tooling. |

## Publication Rules

- Keep upstream license and notice files intact.
- Add source credit when adapting upstream behavior or code.
- Do not commit proprietary Bambu networking binaries or any closed-source
  plugin artifacts.
- Do not publish user API keys, printer access codes, cloud tokens, or raw app
  support data.
- Keep `docs/TINMANX-SEPARATION.md` as the boundary between app repair and
  TinManX product work.
