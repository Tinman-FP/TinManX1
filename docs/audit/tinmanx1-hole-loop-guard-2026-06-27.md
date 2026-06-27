# TinManX1 Hole Loop Guard Audit - 2026-06-27

This note records the safety correction after the close-hole cluster experiment connected outboard gear-tooth features on the gear-guide test part.

## Correction

- Disabled automatic cluster-halo output for close tiny holes.
- Added a printable-material check for generated hole reinforcement loops.
- Rejects generated hole loops that enclose other distinct hole centers, which filters web/outer rings.
- Keeps smooth two-lap hole reinforcement available only for legal-size loops that satisfy bend radius, printable material, and 90 mm minimum length.

## Current Gear-Guide Dry Run

The installed TinManX1 planner was run against a cleaned polymer-only stream from the current gear-guide slice.

Result:

- `perimeter_trace`: 82
- `stitched_perimeter_trace`: 1
- `hole_cluster_reinforcement_loop`: 0
- routes under 90 mm: 0

For this geometry, the smaller internal holes are still too small or too tightly coupled for a safe standalone continuous-fiber loop. The corrected planner therefore refuses those loops instead of connecting outboard features.
