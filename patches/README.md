# Patches

Use this directory for public source patches or patch notes that can be reviewed and reapplied.

Do not place full app bundles, native binaries, downloaded installers, or private Application Support data here.

## Current Patch

- `tinmanx1-v2.4.0-houseclean-native-fiber.patch`: current TinManX1 source patch on the Orca Slicer 2.4.0 source line. It includes rebrand cleanup, startup splash correction, native FibreSeek planning, fiber preview/summary support, Wave Overhangs, Arc Support, Strength Lens, helper resources, attribution, and smoke checks.

## Install Helper

- `../scripts/install_orcaslicer_codex_app.py`: stages a built OrcaSlicer-derived app as `/Applications/TinManX1.app`, preserves the TinManX1 icon and data directory, bundles helper scripts/resources, signs the app, and keeps a timestamped backup of the prior installed bundle.
- `../scripts/verify_orcaslicer_codex.py`: checks the installed app identity, launcher, version, bundled feature resources, Strength Lens feature markers, LF-normalized GPL script, codesign, and TinManX separation.
