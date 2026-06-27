# Changelog

## v2026.06.27.1

TinManX1 native FibreSeek planner safety correction.

Included:

- removed automatic close-hole cluster halos after validation showed they could connect outboard gear-tooth features
- added printable-material checks for generated hole reinforcement loops
- rejects enclosing web/outer rings that contain other distinct hole centers
- keeps the 90 mm mechanical minimum and smooth multi-lap route support for legal-size hole loops
- installed-app dry run against the current gear-guide slice confirmed zero cluster routes and zero routes under 90 mm

## v2026.06.27

TinManX1 native FibreSeek planner follow-up.

Included:

- hard 90 mm mechanical minimum carried through route filtering and planner summaries
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
