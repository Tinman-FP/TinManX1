# Arc Overhang Third-Party Notice

Source: <https://github.com/Kelsch/arc-overhang-orcaslicer-integration>

Vendored commit: `0693ef29a0eb3e96fdc336841cd714e071f3ed9a`

License: GPL-3.0, copied in `LICENSE`.

Credits retained from upstream:

- Original concept: Steven McCulloch, <https://github.com/stmcculloch/arc-overhang>
- PrusaSlicer integration: Nicolai Wachenschwan, <https://github.com/nicolai-wachenschwan/arc-overhang-prusaslicer-integration>
- OrcaSlicer integration: Kelsch, <https://github.com/Kelsch/arc-overhang-orcaslicer-integration>

TinManX1 integration status:

- The upstream script is preserved here as a reference implementation and attribution anchor.
- Direct production execution must go through a wrapper or refactor because the upstream script uses interactive prompts, imports plotting dependencies, and overwrites its input G-code file in place.
- The integrated Arc Support path should write to an explicit output path and emit an audit summary with inserted arc blocks, removed bridge blocks, and machine-start/toolchange mutation checks.
