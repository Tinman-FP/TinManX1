# TinManX1 Architecture Hardening Pass - 2026-08-04

## Scope

This pass reviewed TinManX1 as a product rather than a single patch: preset architecture, continuous-fiber behavior, release hygiene, device integration seams, and how comparator slicers organize similar responsibilities.

## Comparator Notes

- Rocket Slicer remains the best hardware-behavior oracle for FibreSeek output. Its backend data is organized as database-like tables for plastics, composites, profiles, material mappings, and extruder mappings. TinManX1 should continue to compare against Rocket G-code, but Rocket-specific terms and internal naming should not leak into the TinManX1 UI.
- PrusaSlicer vendor bundles are a strong model for clean profile packaging. The useful lessons are explicit vendor files, predictable child profile references, install/relaunch validation, and the newer concept of configurable local or online preset sources.
- OrcaSlicer and Bambu Studio are the baseline ecosystem model for broad printer compatibility, cloud/device workflows, and profile inheritance. TinManX1 should keep those integrations isolated from FibreSeek-specific planner behavior.
- Fractal-Cortex and CF-Slicer reinforce the same continuous-fiber design lesson already captured in the TinManX1 research docs: route metadata must survive from planner to preview to summary to G-code. A single route object should be treated as the source of truth.
- Public continuous-fiber feature requests in Cura and PrusaSlicer highlight the must-have user-facing controls: selected layers, perimeter/infill scope, fiber width, fiber temperature, fiber flow, fiber speed, bend radius, and cut commands.

Reference links:
- https://github.com/OrcaSlicer/OrcaSlicer
- https://github.com/bambulab/BambuStudio
- https://github.com/prusa3d/PrusaSlicer
- https://github.com/prusa3d/PrusaSlicer/wiki/Vendor-bundles-and-updating-process
- https://github.com/supermerill/SuperSlicer
- https://github.com/fractalrobotics/Fractal-Cortex
- https://github.com/ThenTech/CF-Slicer
- https://github.com/Ultimaker/Cura/issues/14483
- https://github.com/prusa3d/PrusaSlicer/issues/9609

## Findings

1. TinManX1 already has the right major product boundaries: profile resources, FibreSeek planner code, public helper scripts, G-code contract checks, and release/package checks. The weak point is that these checks are split, so regressions can still slip through when a change only touches profiles or installed resources.
2. Profile data is now the highest-churn area of the product. Preset edits must be guarded like source code because stale notes, backup files, or machine-incompatible profile IDs can directly affect slicing.
3. The installed app resources and user/system profile caches can diverge from the repository. That explains why a fixed profile can still appear stale in the UI after a restart. TinManX1 needs an explicit repo-to-app/system preset sync and a checksum manifest for release packaging.
4. FibreSeek continuous-fiber routing should keep one durable route representation that feeds preview, summary, and G-code. Any route rewrite that only touches one of those outputs is a regression risk.
5. Rocket comparison profiles should remain separate from normal product profiles. Apples-to-apples validation is important, but comparison settings should not pollute daily-use profiles.
6. Device integration should be split by adapter: Bambu LAN/cloud behavior, Klipper/Moonraker behavior, Snapmaker material-slot behavior, and FibreSeek composite planning should not be patched through one shared UI path.
7. The largest profile-regression source was architectural: the native launcher executed a mutable Python preflight from Application Support before every startup. That unversioned script recreated 124 legacy machine sidecars and thousands of obsolete compatibility names after the curated resources had already been installed.

## Changes Made In This Pass

- Removed a stale profile backup artifact from the product profile tree into ignored work quarantine.
- Added a profile-resource hygiene check that rejects backup, swap, scratch, AppleDouble, and `.DS_Store` files inside `resources/profiles`.
- Normalized direct Bambu PET-CF presets across supported Bambu machines to the TinManX1 PET-CF surface tune: 285C first layer, 280C print, 1.00 flow, pressure advance 0.022, fan max 20, and 3.2 mm3/s max volumetric speed.
- Added a PET-CF tuning contract check so direct Bambu PET-CF profiles cannot drift back to the old 300C / 1.08 flow rescue tune unnoticed.
- Updated the profile checker so curated Bambu, Snapmaker, and TinManX1 profile IDs remain validated for presence and uniqueness without forcing them through the generic deterministic ID formula.
- Replaced machine-profile discovery from stale workstation state with a declared TinMan Codex contract: 13 curated machine or RatRig mode entries, each exposing only 0.4, 0.6, 0.8, and 1.0 mm variants.
- Kept upstream machine presets as hidden inheritance bases and generated one compatible quality process for every selector-facing TinMan Codex machine profile. FibreSeek retains its fixed 0.7 mm continuous-fiber nozzle internally.
- Added a recoverable live migration that backs up and removes legacy user machine copies, rewrites the enabled model list, and keeps physical-printer compatibility links pointed at the canonical profiles.
- Added a compiled machine-profile contract at the preset-loading boundary. Startup, cloud sync, local/bundle loading, and both machine selectors now reject historical curated-machine copies and reapply the 13-model, four-nozzle enabled catalog, so cloud restore cannot undo the cleanup.
- Applied the same contract at both `AppConfig::save()` boundaries. Persisted configuration is canonical even when a future caller bypasses the normal preset-loading path.
- Added focused C++ tests for canonical and historical Qidi, Snapmaker, FibreSeek, RatRig, cloud-prefixed, and unrelated experimental profile names.
- Changed Codex filament compatibility generation to consume the fixed machine contract instead of collecting every historical `Copy`, `Installed`, or imported profile name found on the workstation.
- Migrated FibreSeek plastic and CFC compatibility from the hidden composite-machine aliases to the four canonical TinMan Codex profiles. The fixed 0.7 mm fiber nozzle and slot-2 mapping remain part of each canonical machine profile.
- Removed the launcher's mutable Application Support preflight and archived the old script. Startup repairs that remain necessary are packaged and versioned with the application.
- Updated the filament generator to use Orca-compatible deterministic setting IDs and the current `default_filament_colour` schema. The full 66-vendor profile checker now reports zero errors and zero warnings.
- Ran an isolated contaminated-startup integration test with old COSMOS/current/HF variants and a 0.2 mm nozzle injected into the saved configuration. The installed binary persisted exactly 13 models, removed the legacy records, and restored Qidi to `0.4;0.6;0.8;1.0` without launcher-side mutation.
- Corrected the machine visibility boundary after live startup exposed an inheritance-order regression. Legacy source presets remain indexed and loadable so Orca can resolve every canonical child's `inherits` chain; they are filtered only by the two machine selectors. The release checker now rejects loader-level filtering, missing indexed bases, and invalid source variants.
- Modeled `Codex` as a bundled filament-import staging vendor in the deployment manifest. Orca legitimately removes its system-cache copy after importing the profiles into `user/default`; app-bundle integrity remains mandatory while the runtime cache check covers only retained vendors.
- Fixed the Prepare-tab nozzle selector contract for common-diameter multi-extruder machines. Snapmaker U1 and RatRig IDEX now switch their complete 0.4, 0.6, 0.8, or 1.0 mm machine preset through the unified selector; Bambu dual-nozzle machines retain independent left/right controls.
- Added four materially different processes for every RatRig normal/copy/mirror and Snapmaker U1 nozzle variant: Tank, Quality, Fast, and Draft. The modes define nozzle-scaled layer heights and line widths, progressively distinct speed/acceleration ceilings, and explicit shell/infill strength policies; Quality is the default.
- Added a 757-file profile deployment manifest with backed-up synchronization and checksum verification across the repository, installed app bundle, and Application Support cache.

## Recommended Next Moves

1. Promote the FibreSeek route object to a formal contract with golden fixtures for route count, cut count, preview role, fiber mass, and legal in-material moves.
2. Add UI contract tests for filament slot filtering, CFC filament auto-selection, strength modes, machine-profile visibility, and profile editor target selection.
3. Add golden slice fixtures for the RatRig/Snapmaker Tank, Quality, Fast, and Draft contracts before extending the same four-mode system to additional standard printers.
4. Split device integrations into named adapters with adapter-specific tests for Bambu, Klipper/Moonraker, Snapmaker, and FibreSeek.
5. Keep Rocket comparison fixtures, but label them as validation-only fixtures with their source version and settings payload.
