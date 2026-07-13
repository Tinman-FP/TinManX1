# Patches

Use this directory for public source patches or patch notes that can be reviewed and reapplied.

Do not place full app bundles, native binaries, downloaded installers, or private Application Support data here.

## Current Patch

- `tinmanx1-v2.4.2-houseclean-native-fiber.patch`: current TinManX1 source patch on the Orca Slicer 2.4.2 source line. It includes rebrand cleanup, startup splash correction, native FibreSeek planning, fiber preview/summary support, fiber infill density/angle controls, fiber-only seam controls, profile/process generator and lint checks, Rocket/TinManX1 comparison tooling, Wave Overhangs, Arc Support, Strength Lens, helper resources, attribution, smoke checks, the FibreSeek layup editor contract, and Bambu networking plug-in `02.06.00.50` recognition without redistributing native plug-in binaries.
- `tinmanx1-v2.4.1-houseclean-native-fiber.patch`: archived 2.4.1 patch kept for traceability and comparison.
- `tinmanx1-v2.4.1-bambu-network-plugin-version.patch`: archived follow-up patch for the 2.4.1 line that recognized Bambu networking plug-in `02.06.00.50`.
- `tinmanx1-v2.4.0-houseclean-native-fiber.patch`: archived 2.4.0 patch kept for traceability and comparison.

Patch files preserve the regenerated source diff byte-for-byte, including whitespace inside upstream or generated hunks. Run whitespace checks against the public docs/scripts outside `patches/*.patch`, and use `checks/verify_release.py` for patch privacy and attribution validation.

## Install Helper

- `../scripts/install_orcaslicer_codex_app.py`: stages a built OrcaSlicer-derived app as `/Applications/TinManX1.app`, preserves the TinManX1 icon and data directory, bundles helper scripts/resources, signs the app, and keeps a timestamped backup of the prior installed bundle.
- `../scripts/source-helpers/install_tinmanx1_bambu_network_plugin.py`: local-only helper that copies a user-owned BambuStudio/OrcaSlicer network plug-in into TinManX1's Application Support plug-in folder and sets `OrcaSlicer.conf` to that version. It refuses to edit config while TinManX1 is running unless explicitly overridden.
- `../scripts/source-helpers/repair_tinmanx1_bambu_lan_bindings.py`: local-only helper that repairs stale saved Bambu LAN IPs by matching MQTT TLS certificate CNs to saved serial numbers. It does not read or print access codes.
- `../scripts/verify_orcaslicer_codex.py`: checks the installed app identity, launcher, version, bundled feature resources, Strength Lens feature markers, LF-normalized GPL script, codesign, and TinManX separation.
