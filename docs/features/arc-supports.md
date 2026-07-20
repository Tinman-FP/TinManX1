# Arc Supports

Arc Supports is an experimental operator-test lane that adapts arc-overhang transform work into the TinManX1 source patch.

## Included Work

- Arc process selection glue
- Codex post-processing adapter lookup
- vendored GPL Arc Overhang engine path in the patch
- support-to-Arc conversion metadata
- post-processed preview reload path
- G-code viewer metadata parsing and Arc Support legend block
- smoke guard for runtime adapter behavior

## Status

Experimental. The transform must preserve machine-start, toolchange, and safety-critical G-code sections. Printer-bound output should remain operator-reviewed until local validation proves intended bridge replacement, arc insertion, and no unwanted mutation.
