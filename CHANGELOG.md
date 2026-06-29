# Changelog

## Unreleased

TinManX1 FibreSeek nice-to-have controls and release hardening.

Included:

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
