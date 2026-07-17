# TinManX1 Release Scope

TinManX1 is a rebranded and extended Orca Slicer based build with FibreSeek
continuous-fiber support. Public release work should be deliberate: include the
source, profiles, scripts, and attribution needed to build and validate the app,
but do not publish local validation payloads or private machine state.

## Include

- Source changes required for TinManX1 branding, FibreSeek profile handling,
  continuous-fiber preview, G-code summary, and native fiber planning.
- `resources/profiles/TinManX1.json` and `resources/profiles/TinManX1/`.
- `resources/orcaslicer_codex/fiber_planner/`.
- TinManX1 image assets created for this app.
- FibreSeek profile generator, wiring check, profile lint, planner smoke test,
  G-code comparison, and G-code contract audit scripts.
- Public-safe documentation under `docs/`.
- Attribution and upstream version notes.

## Exclude

- `outputs/` and other generated local G-code comparisons.
- Rocket Slicer databases, app bundles, images, UI strings, or exported G-code.
- Installed app bundles and local application-support profile state.
- Private printer hostnames, IP addresses, tokens, logs, and account data.
- Build directories and packaging scratch directories.

## Release Gate

Run this before publishing a FibreSeek-capable TinManX1 checkpoint:

```bash
python3 checks/verify_tinmanx1_fiberseek_release.py
```

The gate checks Python syntax, C++ profile-whitelist keys, profile/config/UI
wiring, generated FibreSeek profile invariants, native planner smoke fixtures,
the neutral G-code comparison self-test, and obvious public-release hygiene
issues.
