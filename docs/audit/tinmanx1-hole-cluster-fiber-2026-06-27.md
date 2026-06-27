# TinManX1 Close-Hole Fiber Audit - 2026-06-27

This note records the follow-up native FibreSeek planner validation for close-spaced small holes.

## Superseded Cluster Experiment

The initial close-hole cluster halo experiment was superseded the same day after visual validation showed it could connect outboard gear-tooth features. The corrected planner keeps the 90 mm mechanical minimum but does not emit automatic `hole_cluster_reinforcement_loop` routes for this geometry.

## Corrected Planner Behavior

- Treats 90 mm as the non-negotiable mechanical minimum for emitted continuous-fiber routes.
- Keeps individual tiny hole loops disallowed when they cannot satisfy bend radius, printable-path, or 90 mm length requirements.
- Supports smooth multi-lap reinforcement for legal-size hole loops that remain inside printable material.
- Rejects enclosing web/outer rings that contain other distinct hole centers.

## Validation

```bash
python3 scripts/smoke_orcaslicer_codex_native_fiber_planner.py
python3 /Applications/TinManX1.app/Contents/Resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py --in-gcode <current gear-guide temp gcode> --out <tmp gcode> --summary-out <tmp summary> --fiber-reinforcement-mode heavy --fiber-generate-perimeters 1 --fiber-generate-infill 1 --fiber-infill-pattern tetragrid --fiber-infill-source plastic-traces --fiber-start-layer 0 --fiber-routes-per-cut 1
```

The corrected installed-app dry run on the cleaned gear-guide polymer stream produced 83 routes total, zero `hole_cluster_reinforcement_loop` routes, and zero continuous-fiber routes under 90 mm.
