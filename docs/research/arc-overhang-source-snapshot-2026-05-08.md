# Arc Overhang Source Snapshot

Generated: `2026-05-08`

TinManX inspected the primary Kelsch OrcaSlicer integration directly from:
<https://github.com/Kelsch/arc-overhang-orcaslicer-integration>

Verified upstream commit:
`0693ef29a0eb3e96fdc336841cd714e071f3ed9a`

## Production Blockers Before Enablement

- The GPL transform source is not yet bundled under
  `third_party/gpl/arc-overhang/`, so Arc Support remains experimental and
  operator-test required before printer-bound execution is trusted.
- The upstream script contains interactive `input(...)` prompts, which must be
  removed or wrapped before TinManX can run it in a non-interactive slice task.
- The upstream script imports `matplotlib.pyplot` for debugging; production
  execution should remove or lazy-load plotting dependencies.
- The upstream script overwrites the input G-code file in place. TinManX needs a
  controlled output path plus an audit artifact before enabling any mutation.
- Required dependencies are `Shapely`, `numpy`, `matplotlib`, and
  `numpy-hilbert-curve`; the production path should prove which are actually
  required after debug plotting is removed.

## Current TinManX Guard

`arc_support.transform_readiness` records the source revision, local engine path,
license/dependency manifest presence, and blockers. `operator_test_allowed`
keeps the option selectable for William's experimental testing, while
`printer_bound_output_allowed` stays `false` until TinManX proves arc insertion,
intended bridge replacement, and zero machine-start/toolchange mutation.
