# TinManX1

Public source patchset, documentation, and credit ledger for TinManX1, a FibreSeek-focused slicer build maintained by William Tinney / Tinman-FP with OpenAI Codex engineering assistance.

This repository is a clean public release package. It does not contain private printer credentials, app-support data, bundled app binaries, native networking plugins, or local machine history.

## What Is Included

- A current source patch for TinManX1 on the Orca Slicer 2.4.0 source line:
  - `patches/tinmanx1-v2.4.0-houseclean-native-fiber.patch`
- Helper scripts for the native FibreSeek planner, Arc Support, Strength Lens, fibre metadata sidecars, and smoke checks.
- Manifest helper notes and validation scripts for the local TinManX1 app workflow.
- Feature notes for native continuous fibre, Strength Lens, Wave Overhangs, Arc Supports, and backend printer/app improvements.
- Source credit ledgers and research snapshots used to keep attribution traceable.

## Feature Lanes

| Lane | Status | Notes |
| --- | --- | --- |
| Native FibreSeek planner | Experimental / active | Standalone continuous-fiber G-code generation path with light/medium/heavy reinforcement modes, layer guard controls, 90 mm mechanical route filtering, close-hole cluster reinforcement, and rendered fiber preview support. |
| Strength Lens | Advisory / experimental | Prepare-view strength evidence, material model hints, load-axis selection, and sidecar metadata. Not FEA and not certified engineering output. |
| Wave Overhangs | Experimental source port | Opt-in Wave Overhangs scaffold from the OrcaSlicer Wave Overhangs lineage with audit markers and smoke coverage. |
| Arc Supports | Experimental operator-test path | Arc-overhang transform adapter and runtime glue with guarded metadata. Printer-bound trust still requires local validation. |
| Backend improvements | Local app and device integration | TinManX1 app separation, upgrade verification, profile-boundary notes, and proprietary-plugin exclusion policy. |

## Upstream Baseline

- Primary upstream: [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer)
- TinManX1 application display version: based on Orca Slicer `2.4.0`
- Source base commit used to generate this patch: `6d9eb1792f50d11ea12d60526b6ace58666354fd`
- License family: AGPL-3.0-or-later, following OrcaSlicer and its upstream lineage

## Repository Boundaries

Included:

- source patches
- public documentation
- helper scripts
- manifest helper notes
- attribution and research notes

Excluded:

- `.app`, `.dmg`, `.deb`, `.AppImage`, `.dylib`, and other binary payloads
- private printer credentials, access codes, passwords, API keys, cloud tokens, and private keys
- full `Application Support` trees or private printer profile dumps
- proprietary Bambu networking plugin binaries
- proprietary Rocket or FibreSeek assets and private validation data

## Quick Review

Run the public release check before publishing changes:

```bash
python3 checks/verify_release.py
```

For local installed-app validation, see:

```bash
python3 scripts/verify_orcaslicer_codex.py --expected-version 2.4.0 --codesign
python3 scripts/collect_baseline_manifest.py --output manifests/current-local.json
```

Review generated manifests before committing them. They can contain local paths or machine details if collected directly from a workstation.

## Credits

The short version: this work stands on OrcaSlicer, Bambu Studio, PrusaSlicer, Slic3r, Arc Overhang, Wave Overhangs, Klipper, Moonraker, FibreSeek hardware context, and the 3D-printing research community. The project-specific coordination, requirements, testing, and release ownership are credited to William Tinney / Tinman-FP, with OpenAI Codex credited for engineering assistance, implementation support, documentation, and review.

See [ATTRIBUTION.md](ATTRIBUTION.md) for the full source-credit ledger.
