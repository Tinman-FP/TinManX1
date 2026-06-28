# TinManX1 Hole Loop Guard Audit - 2026-06-27

This note records the safety correction after the close-hole cluster experiment connected outboard gear-tooth features on the gear-guide test part.

## Correction

- Disabled automatic cluster-halo output for close tiny holes.
- Added a printable-material check for generated hole reinforcement loops.
- Rejects generated hole loops that enclose other distinct hole centers, which filters web/outer rings.
- Keeps smooth hole reinforcement available only for legal-size loops that satisfy bend radius, printable material, and the corrected 55 mm minimum length.

## Follow-Up Local Racetrack Correction

The broad cluster halo remains disabled. A later planner update tested a narrower local racetrack candidate for tight small-hole groups, but live visual validation showed it could over-reinforce the gear-tooth region and still miss the intended inner holes. Production cluster/racetrack emission is disabled pending a stronger material-containment model.

## Current Gear-Guide Dry Run

The installed TinManX1 planner was run against a cleaned polymer-only stream from the current gear-guide slice.

Result:

- `perimeter_trace`: 82
- `stitched_perimeter_trace`: 1
- `hole_cluster_reinforcement_loop`: 0
- routes under the then-assumed 90 mm floor: 0

For this geometry, the smaller internal holes may still be too small or too tightly coupled for a safe standalone continuous-fiber loop. The corrected planner refuses unsafe loops instead of connecting outboard features.

The current installed TinManX1 recovery planner dry run against the bad gear-family slice produced zero `hole_cluster_reinforcement_loop` routes and 16.91 m / 1.72 g estimated continuous fiber.
