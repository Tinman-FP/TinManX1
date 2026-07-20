# Codex Printer Work Cleanup - 2026-07-20

This note records the cleanup pass that consolidated current Codex-assisted
3D-printer work across the Tinman repos.

## Canonical TinManX1 Fork

- GitHub repo: `Tinman-FP/TinManX1`
- Canonical/default branch after cleanup: `tinmanx1-v2.4.2-rebase`
- Orca base shown in app: `2.4.2`
- TinManX1 visible revision: `v2026.07.20-unified.1`

The unified branch now carries the full Orca-derived source tree plus the
public release-package ledgers, attribution files, validation contracts,
profile helper scripts, and profile-maintenance utilities from the older
packaging branch.

## Printer/PA Work Published

- `Tinman-FP/qidi-plus4-codex-macros`
  - Plus 4 Qidi Box control macros.
  - Plus 4 PLR hardening package.
  - Max EZ staging PLR updates.
- `Tinman-FP/qidi-plus4-btt-max-ez`
  - Max EZ motion safety limits.
  - Max EZ locked/fail-closed PLR tooling.
- `Tinman-FP/rat-rig-dual-beacon-500-idex-config`
  - Rat Rig IDEX PLR hardening.
  - T0/T1 carriage position capture.
  - Dual-carriage status exposure.
- `Tinman-FP/PrusaPATuner`
  - `codex/pa-quadratic-stability` branch with the PA quadratic-fit fallback.
- `Tinman-FP/TinManX1`
  - Moonraker metadata-based remaining-time estimate.
  - Live Moonraker status stream restoration.
  - TinManX1 Qidi Box device-tab panel.
  - Unified release ledgers and helper scripts.
  - Splash/about TinManX1 revision visibility.

## Ported From Older TinManX1 Worktrees

The old `public_tinmanx1_release_20260626/TinManX1` worktree had three local
helper edits that were not yet published. These were ported into the unified
branch:

- HT-PLA-CF Codex helper profile seeding.
- HT-PLA-CF and HT-PLA-GF filament cost/name aliases.
- Arc Support pass-through fallback that preserves original G-code when an
  arc transform cannot produce printable arc moves.

## Intentionally Left As Local/Legacy

These local directories are not canonical publishing targets:

- `public_tinmanx1_release_20260626/patch-work`
  - Legacy patch staging tree with many historical TinManX1 source-package
    edits. Its useful release-package artifacts are now in the unified branch.
- `public_tinmanx1_release_20260626/TinManX1-source-v2.4.1`
  - Older external upstream checkout, ahead locally by one historical profile
    commit. It points at `FULU-Foundation/OrcaSlicer-bambulab`, not the
    Tinman fork.
- Backup `.theme` checkouts inside copied printer backup folders.
  - External Mainsail theme snapshots inside backups, not Tinman printer-source
    repos.

## Validation Run

- `python3 checks/verify_release.py`
- `python3 -m py_compile checks/verify_release.py checks/verify_polymaker_catalog.py scripts/test_moonraker_lane_data.py scripts/test_moonraker_slicer_time_estimate.py scripts/source-helpers/*.py`
- `python3 scripts/test_moonraker_slicer_time_estimate.py`
- `git diff --check`
- Rendered `resources/images/splash_logo.svg` and
  `resources/images/TinManX1_about.svg` with `rsvg-convert` for revision-line
  visual sanity checks.
