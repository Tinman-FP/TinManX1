# Strength Lens

Strength Lens is an advisory visualization and metadata lane for TinManX1.

It is designed to help a user reason about print orientation, material assumptions, load-axis sensitivity, process confidence, and continuous-fiber planning metadata. It is not a finite-element solver and must not be presented as certified engineering output.

## Included Work

- Codex-named Strength Lens sidecar script
- Prepare-view Strength Lens controls in the source patch
- `Auto`, `X`, `Y`, and `Z` load-axis selection
- default FDM model that treats X/Y behavior differently from Z layer bonding
- advisory support for isotropic and continuous-fiber assumptions
- smoke guard for Strength Lens and Fibre metadata sidecars

## Guardrails

- Keep output labeled as planning evidence, not safety factor.
- Do not claim certification without printer/material/process coupon evidence.
- Preserve source credits for expert-channel, mechanics, and simulation-language references.
- Keep proprietary Rocket/FibreSeek assets out of public distribution.
