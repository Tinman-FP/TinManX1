# TinManX1 Close-Hole Fiber Audit - 2026-06-27

This note records the follow-up native FibreSeek planner validation for close-spaced small holes.

## Planner Change

- Treats 90 mm as the non-negotiable mechanical minimum for emitted continuous-fiber routes.
- Keeps individual tiny hole loops disallowed when they cannot satisfy bend radius or 90 mm length requirements.
- Adds rounded cluster-halo reinforcement around close hole groups when the group route can satisfy machine constraints.
- Records `hole_cluster_reinforcement_loop` route counts and skip reasons in the planner summary.

## Validation

```bash
python3 scripts/smoke_orcaslicer_codex_native_fiber_planner.py
python3 /Applications/TinManX1.app/Contents/Resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py --in-gcode <current gear-guide temp gcode> --out <tmp gcode> --summary-out <tmp summary> --fiber-reinforcement-mode heavy --fiber-generate-perimeters 1 --fiber-generate-infill 1 --fiber-infill-pattern tetragrid --fiber-infill-source plastic-traces --fiber-start-layer 0 --fiber-routes-per-cut 1
```

The installed-app dry run produced 134 routes total, including 51 `hole_cluster_reinforcement_loop` routes, with zero continuous-fiber routes under 90 mm.
