# Changelog

## Unreleased

TinManX1 FibreSeek nice-to-have controls and release hardening.

Included:

- fixed Bambu LAN print sends that stalled at 70% or failed with `-4030` by eliminating the asynchronous reconnect race, verifying MQTT before upload, and performing one bounded reconnect/retry only when the start command was never published
- aligned TinManX1's `PrintParams` binary layout with Bambu Studio 2.7.1 so the current official networking plug-in receives deterministic H2D print options
- updated the visible revision to `v2026.08.12-bambu-lan-send.1`
- fixed Bambu LAN startup ordering so a saved H2D is reconnected after TinManX1 switches from the previous printer agent to the Bambu agent
- treated TinMan's private per-machine connection overlay as runtime state, preventing IP, credential, and host-agent restoration from producing false unsaved-profile warnings
- added a guarded macOS launch helper that adopts a newer official Bambu networking plug-in from an installed Bambu Studio, with rollback backups and no redistribution of proprietary binaries
- prevented stale temporary CAD projects and concurrent 3MF thumbnail extraction from blocking the main window during startup
- updated the visible revision to `v2026.08.12-bambu-lan-runtime.1`
- preserved a newer per-machine connection during startup migration so stale cached system profiles cannot replace a working PrusaLink hostname or IP address
- repaired the local CORE One L connection to use its stable `prusa-core-one-l.local` hostname across every TinMan nozzle profile
- added native regression coverage for stale-profile connection precedence and updated the visible revision to `v2026.08.11-prusalink-persistence.1`
- marked every curated TinMan machine except the Snapmaker U1 as High Flow at the machine-profile level, including correctly sized dual-nozzle vectors for the H2D, RatRig IDEX, and FibreSeek families
- migrated persisted nozzle-flow selections at startup and during live catalog deployment so stale Standard entries cannot override the machine profile and trigger Bambu nozzle-mismatch warnings; the U1 remains explicitly Standard
- updated the visible TinManX1 revision to `v2026.08.10-high-flow-nozzles.1`
- corrected the Bambu X1C PCTG preset after a plate-sized 0.6 mm field print: removed the fixed `K=0.08` override so X1C flow-dynamics calibration remains authoritative, lowered the post-first-layer nozzle target to `250 C`, and introduced 20% cooling from layer three while retaining the Bambu-validated `0.95` flow and `6 mm3/s` volumetric limit
- imported Bambu Studio's current generic-PCTG density, glass-transition, and AMS drying metadata, including the `65 C`/12 h drying baseline
- updated the visible TinManX1 revision to `v2026.08.10-x1c-pctg.1`
- moved private LAN connection settings out of generated printer copies into a persistent per-machine overlay shared by every canonical nozzle profile
- migrated saved printer-copy addresses, legacy address aliases, and locally discovered Bambu bindings into the canonical four-nozzle catalog without publishing private network data
- made startup profile cleanup restore the selected printer's connection before device-agent selection, preventing addresses from disappearing after relaunch
- confined macOS translation lookup to the packaged app resources, removing a build-tree locale scan that could delay startup by more than a minute
- added native regression coverage for cross-nozzle connection persistence and legacy-address migration
- updated the visible TinManX1 revision to `v2026.08.10-printer-connections.1`
- restored every CORE One L TinMan process to Prusa's standard-nozzle lineage instead of mixing standard machine presets with high-flow process inheritance
- restored Prusa's common `0.20 mm`, `500 mm/s^2` first-layer contract, stock line widths, and stock first-layer speeds for the 0.4, 0.6, and 0.8 mm CORE One L nozzles; the 1.0 mm profile conservatively extends those ratios because Prusa does not publish a stock 1.0 mm profile
- capped CORE One L process accelerations to Prusa's validated standard-profile envelope while preserving distinct Tank, Quality, Fast, and Draft behavior above the first layer
- added generated-profile regression checks for CORE One L first-layer values and standard Prusa inheritance
- updated the visible TinManX1 revision to `v2026.08.10-core-one-l-adhesion.1`
- fixed Snapmaker U1 print uploads being sent to Moonraker's writable but non-printable `config` root; TinManX1 now exposes and uses only the U1's `gcodes` root, including when an older saved storage preference points elsewhere
- fixed Snapmaker connection presets so saving a LAN address keeps the Prepare selector and printer thumbnail on Snapmaker instead of visually falling back to Bambu H2D
- declared the Snapmaker U1 as a Moonraker host, mirrors a missing web UI address from its printer address, and refreshes the selected device immediately after connection settings are saved
- updated the visible TinManX1 revision to `v2026.08.09-snapmaker-print.1`
- fixed Snapmaker U1 filament synchronization so the live machine slot material outranks stale saved metadata, while retaining saved metadata as a fallback when firmware reports no usable live material
- added regression coverage for ASA-CF versus stale PET-CF metadata, HT-PLA-GF subtype resolution, PEBA, and PCTG-CF fallback handling
- fixed curated printer selection so the displayed printer, bed, nozzle, process, and saved profile always resolve to the same TinMan Codex preset
- migrated hidden stock-machine selections at startup and replaced `Default Filament` with each machine's explicit compatible Codex PLA default
- updated the visible TinManX1 revision to `v2026.08.09-preset-sync.1`
- consolidated TinManX1 helper authoring under `scripts/source-helpers`, removed 16,000 lines of duplicate script copies, and added release-time byte-for-byte checks against packaged runtime helpers
- aligned the FibreSeek profile generator with the canonical four-nozzle catalog and added an idempotence gate so regeneration cannot silently restore retired profile variants
- repaired dormant Arc Overhang, Wave Overhang, Strength Lens, and FibreSeek smoke paths so they execute the same code and resource locations shipped in the app
- hardened Arc Overhang against converting ordinary support-only G-code into arc infill while preserving its guarded bridge/overhang workflow
- removed repeated allocation and catalog reconstruction from curated machine/process filtering, with mixed-case cloud-preset regression coverage
- added a configurable FibreSeek planner watchdog so a stalled Python process cannot hang slicing indefinitely or leave partially written G-code
- excluded ignored virtual environments and Python caches when staging local app bundles, preventing generated development files from inflating release packages
- removed machine-specific LAN addresses from public Qidi system presets and extended release hygiene checks to keep connection data out of portable profiles
- removed duplicate planner metadata keys and dead helper code, and added focused Python correctness lint coverage for the maintained helper tree
- updated the visible TinManX1 revision to `v2026.08.05-stability.1`
- established the independent TinManX1 Windows package identity `TinmanFP.TinManX1` and four-part product version `2026.8.5.1` while retaining Orca Slicer 2.4.2 compatibility attribution
- aligned NSIS, Windows executable resources, Win32 manifests, MSIX metadata, and cross-platform release artifact names with the TinManX1 package version
- aligned native Linux AppImage generator and workflow names with the TinManX1 package identity instead of the upstream Orca version
- restored full build-matrix CI for pull requests and pushes targeting the actual TinManX1 default branch
- kept passing unit tests green by publishing their check summary without requiring PR-comment write access
- hardened Windows installer builds with retried, self-verifying NSIS installation when Chocolatey's package feed is transiently unavailable
- replaced the inherited Orca WinGet publisher with a gated, pinned TinManX1 workflow and release-asset preflight checks
- added release-contract validation that prevents inherited WinGet identifiers, mutable publisher actions, stale splash revisions, and inconsistent Windows package metadata from returning unnoticed
- split the generated Bambu filament catalog into independent H2D and X1C high-flow contracts so the X1C never inherits active chamber settings and H2D profiles can track Bambu Studio directly
- added a reviewed Bambu Studio 2.7.1 material-reference snapshot covering every Codex material/vendor pair, importing exact matches while preserving manufacturer recipes for analogous chemistries
- normalized Micro Swiss-equipped printer profiles against the X1C high-flow values, retained the field-validated Fiberon PET-CF tune, and enforced active chamber targets only on capable printers and qualifying materials
- consolidated the full Orca-derived TinManX1 source branch with the public release-package ledgers, helper scripts, validation contracts, and profile-maintenance utilities so GitHub has one canonical fork branch for current work
- added the visible TinManX1 revision `v2026.07.20-unified.1` to startup splash rendering while preserving the based-on-Orca version line
- added Moonraker metadata-based remaining-time handling, live status stream restoration, and the TinManX1 Qidi Box device panel from the printer-operations workstream
- added visible TinMan auto-PA lane assets, lane-aware import placement, and automatic lane insertion before slice/export/send so Qidi, Max EZ, and RatRig calibration lanes appear on the intended bed edge before slicing
- trims any out-of-bounds skirt generated around a visible auto-PA lane and clamps advertised `PRINT_START` extents back to the bed before export
- normalizes RatRig-style `PRINT_START TOTAL_LAYER_COUNT` metadata to the emitted layer-change stream during auto-PA postprocessing so progress and PLR state stay aligned with the generated G-code
- shortens the Qidi Plus 4 front auto-PA lane so it clears the printer profile's front-right bed exclusion area while staying inside the front 20 mm calibration strip
- tightens the Max EZ rear auto-PA lane spacing so it clears the inherited Qidi rear-left bed exclusion area while staying inside the rear 20 mm calibration strip
- extends auto-PA layer-count normalization to Qidi-style `SET_PRINT_STATS_INFO TOTAL_LAYER` metadata
- normalizes layer-count metadata before deferring files with missing or invalid visible auto-PA lanes so PLR/progress bookkeeping stays sane even on rejected calibration exports
- sanitized the Moonraker lane-data test default host and local catalog-normalizer defaults so public helpers no longer point at a specific private LAN/worktree
- carried forward the pending HT-PLA-CF Codex helper entries and Arc Support pass-through fallback from the older 2.4.2 profile-maintenance branch
- rebased the current TinManX1 patch onto upstream Orca Slicer 2.4.2 commit `8500fcdccaa10b5099ac20d252af3a7c560046f1`
- updated the installed macOS TinManX1 app to report `2.4.2` while preserving the dedicated `OrcaSlicer-Codex` data directory and FibreSeek profile visibility
- refreshed splash/about branding text to say `Based on Orca Slicer Version 2.4.2`
- folded Bambu networking plug-in `02.06.00.50` recognition into the current 2.4.2 source patch without redistributing proprietary native plug-in binaries
- added a current Polymaker/Fiberon Universal Codex catalog snapshot from Polymaker's official preset index, covering 66 current materials and preserving each selected official source preset path
- enriched the Polymaker/Fiberon catalog with current Polymaker shop price sources and 1 kg-equivalent slicer costs
- added a local Codex catalog installer and verifier for those Polymaker/Fiberon presets, including enabled-filament list repair and active user preset `.info` sidecars
- added local Codex filament chamber/cost audit tooling for managed installed profiles, including generic 1 kg material averages when no vendor is present
- added installed manufacturer profile-tree chamber audit tooling for Prusa CORE One, Qidi X-Plus 4, Sovol SV08 MAX, Creality, and Bambu H2D profiles
- added installed profile-tree filament price audit tooling that resolves inheritance across all installed machine profile trees and verifies every material filament profile has a positive current 1 kg cost
- added a local-only TinManX1 Bambu network plug-in restore helper and source patch recognizing Bambu networking plug-in `02.06.00.50` for Bambu printer connectivity without redistributing native plug-in binaries
- added a local-only Bambu LAN binding repair helper that fixes stale TinManX1 `local_machines` IPs by matching printer TLS certificate CNs to saved Bambu serial numbers
- added a TinManX1 profile-pack installer/validator for syncing generated FibreSeek profiles into the installed app bundle and Application Support system store
- refreshed FibreSeek material costs for ASA, ABS-CF, ABS-GF, ASA-GF, PPA-CF, PPS-CF, PET-GF, PCTG, PCTG-CF, Push Plastic PC-PBT, and PA-CF while preserving active chamber-control settings
- added Push Plastic PC-PBT plastic and continuous-fiber matrix profiles across every FibreSeek Seeker 3 plastic and composite nozzle variant
- added a local Codex catalog installer for Push Plastic PC-PBT profiles across Universal, Creality K2 Plus, Elegoo Centauri, Prusa Core One, Qidi X-Plus 4, RatRig V-Core 4, Snapmaker U1, and Sovol SV08 MAX machine buckets
- extended the Push Plastic PC-PBT Codex installer to repair TinManX1's enabled filament list and active user preset `.info` sidecars so the profiles appear under Codex in installed apps
- added generated-rib fiber infill density and comma-separated custom angle controls
- added fiber-only seam placement controls: Source, Nearest, Aligned, Rear, and Random, plus aligned seam angle
- added a validated advanced layup payload helper for building `fiber_reinforcement_payload` JSON from named templates or simple band specs
- added profile-generator support and CI coverage for writing validated layup templates into continuous-fiber process profiles
- added a public FibreSeek layup editor contract and validator for future UI work
- added a neutral Rocket/TinManX1 G-code comparison helper for command families, thermal setpoints, tool ownership, cut/load behavior, route metadata, timing, and material summaries
- added a structural FibreSeek wiring checker so profile, config, UI, preset, generator, and planner handoff changes cannot silently drift
- expanded compact Strength/search UI exposure for the important fiber controls
- updated public release-scope and local install/verify helper defaults for the Orca Slicer 2.4.1 source line and TinManX1 bundle identity
- regenerated the public source patch from the verified TinManX1 worktree and updated source-helper scripts
- strengthened attribution language for upstream slicer contributors, transform-source authors, William Tinney / Tinman-FP, OpenAI Codex, and Rocket/FibreSeek private reference boundaries

## v2026.06.28-fibreseek-alpha.8

TinManX1 PCTG chamber target correction.

Included:

- sets all FibreSeek PCTG and PCTG-CF filament profiles to a 45 C active chamber target
- carries forward the FibreSeek Seeker 3 active chamber-control capability flag
- updates the visible TinManX1 splash/about rev line to `v2026.06.28-fibreseek-alpha.8`

## v2026.06.28-fibreseek-alpha.7

TinManX1 FibreSeek chamber-control profile cleanup.

Included:

- marks the FibreSeek Seeker 3 profile pack as active chamber-control capable
- keeps active chamber temperature control selected for every filament profile with a nonzero chamber target
- preserves PETG as chamber-off because its FibreSeek baseline chamber target is zero
- updates the visible TinManX1 splash/about rev line to `v2026.06.28-fibreseek-alpha.7`

## v2026.06.28-fibreseek-alpha.6

TinManX1 macOS launcher packaging fix.

Included:

- packages the macOS app with a `TinManX1` launcher wrapper and `TinManX1.real` binary so installed apps use the `OrcaSlicer-Codex` data directory where FibreSeek profiles are installed
- preserves the clean Python environment guard for FibreSeek helper planners in the packaged launcher
- updates the visible TinManX1 splash/about rev line to `v2026.06.28-fibreseek-alpha.6`

## v2026.06.28-fibreseek-alpha.5

TinManX1 2.4.1 startup branding follow-up.

Included:

- removed the upstream Orca/Bambu cloud migration popup that could show a misleading `Since version 2.4.0` message during TinManX1 startup
- updated the visible TinManX1 splash/about rev line to `v2026.06.28-fibreseek-alpha.5`
- kept the alpha.4 FibreSeek Python environment sanitation and 2.4.1 config-wiring fixes

## v2026.06.28-fibreseek-alpha.4

TinManX1 2.4.1 packaging fix for FibreSeek slicing and visible release revisioning.

Included:

- added a visible TinManX1 rev line to the splash and about artwork
- sanitized `PYTHONHOME` and `PYTHONPATH` before launching macOS helper planners so Autodesk Fusion's Python environment cannot break FibreSeek slicing
- restored upstream Orca Slicer 2.4.1 `chamber_minimal_temperature` config wiring that was dropped during rebase conflict cleanup
- updated the macOS app installer launcher template with the same clean Python environment guard

## v2026.06.28-fibreseek-alpha.3

TinManX1 Orca Slicer 2.4.1 carry-forward and installed-profile slicing fix.

Included:

- rebased the current TinManX1 patch onto upstream Orca Slicer 2.4.1
- updated TinManX1 splash/about branding strings to say `Based on Orca Slicer Version 2.4.1`
- made GitHub macOS and Windows release workflows build from the 2.4.1 patch line
- added the generated TinManX1 FibreSeek profile pack to the public package
- verified the installed macOS app profile bundle slices a PETG + X-CCF FibreSeek smoke model and emits native fiber metadata

## v2026.06.28-fibreseek-alpha.1

TinManX1 FibreSeek alpha profile-safety correction.

Included:

- fixed generated FibreSeek process profiles so `bridge_line_width` is explicit and never exceeds the selected plastic nozzle diameter
- fixed relative-E layer-change validation by making `layer_change_gcode` exactly `G92 E0`, matching Orca's strict validator
- disabled grouped medium/heavy route cuts by forcing `fiber_routes_per_cut` to `1` until grouped-route emission has a mechanically safe cut/load model
- added profile lint guards for bridge width, relative-E reset, and one-route-per-cut safety
- published the macOS arm64 prerelease package and Windows build-path asset from the corrected checkpoint

Supersedes `v2026.06.28-fibreseek-alpha`, which was caught by release validation before adoption.

## v2026.06.27.3

TinManX1 native FibreSeek planner regression rollback.

Included:

- kept isolated expanded-orbit candidates for tiny holes that cannot be followed directly but have room for an 8 mm bend-radius path
- disabled local hole-cluster racetrack emission after live visual validation showed the path could over-reinforce the gear-tooth region and still miss the intended inner holes
- fixed hole-loop grouping so concentric model shells are not merged with small internal holes
- updated smoke coverage for 56 mm pocket routes, 68.92 mm legal small-hole loops, 56.41 mm tiny-hole expanded orbits, and disabled production cluster halos
- installed-app recovery dry run against the bad gear slice produced 139 routes total, zero `hole_cluster_reinforcement_loop` routes, and 16.91 m / 1.72 g estimated continuous fiber

## v2026.06.27.2

TinManX1 native FibreSeek planner route-floor correction.

Included:

- corrected the misunderstood minimum route floor from 90 mm to 55 mm
- removed the derived `cut_distance + 2 * start_length` filter that kept candidate routes effectively capped at the old 90 mm assumption
- updated smoke coverage to prove 56 mm pocket routes and a 68.92 mm legal small-hole route pass the planner

## v2026.06.27.1

TinManX1 native FibreSeek planner safety correction.

Included:

- removed automatic close-hole cluster halos after validation showed they could connect outboard gear-tooth features
- added printable-material checks for generated hole reinforcement loops
- rejects enclosing web/outer rings that contain other distinct hole centers
- kept the then-assumed 90 mm mechanical minimum and smooth multi-lap route support for legal-size hole loops
- installed-app dry run against the current gear-guide slice confirmed zero cluster routes and zero routes under the then-assumed 90 mm floor

## v2026.06.27

TinManX1 native FibreSeek planner follow-up.

Included:

- hard 90 mm mechanical minimum carried through route filtering and planner summaries; superseded by the later 55 mm route-floor correction
- close-hole cluster halo reinforcement experiment for hole groups that cannot accept individual continuous-fiber loops
- profile bend-radius handling that honors the FibreSeek profile value instead of silently flooring it higher
- native planner smoke coverage for the close-hole cluster case
- installed-app validation against the current sliced gear guide part

Superseded by `v2026.06.27.1` for close-hole planning. The cluster-halo experiment is not used by the corrected planner.

## v2026.06.26

TinManX1 houseclean and native-fiber release package.

Included:

- one current source patch for TinManX1 on the Orca Slicer 2.4.0 source line
- startup splash fix that loads the same TinManX1 PNG used by the login/register home screen
- standalone native FibreSeek planner path with the stale external planner bridge removed
- TinManX1-facing helper text, summaries, and UI/log labels for the patched feature surface
- continuous-fiber route stitching for short pockets, layer start/top guard behavior, preview reload support, and fiber usage summaries
- smoke coverage for native fiber planning, Arc Support guard behavior, Strength/Fibre sidecars, and Wave Overhang scaffolding
- public release checker updates for the current patch and documentation set

Excluded:

- compiled app bundles, installers, and native plugin binaries
- private app-support data
- printer credentials, access codes, cloud tokens, and API keys
- proprietary Rocket or FibreSeek assets and private validation data

## v2026.06.19

Initial public pre-rebrand patch release.

Included:

- Wave Overhangs source-port patch for the Orca Slicer 2.4.0 source line
- Wave + Arc Support source-port patch
- Wave + Arc + Strength Lens + Fibre metadata source-port patch
- standalone helper scripts and smoke guards
- sanitized local app manifests and verification scripts
- source-credit ledgers and research snapshots
- public release checker for attribution, license, patch presence, and privacy guardrails
