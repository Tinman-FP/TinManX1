# Release Scope

This release is a public source patchset and documentation package. It is not a binary application release.

## Included

- TinManX1 source patch on the Orca Slicer 2.4.0 source line
- helper scripts, smoke checks, FibreSeek G-code audit/comparison tooling, and wiring checks
- manifest helper notes for the local TinManX1 app workflow
- feature notes for native continuous fiber, Strength Lens, Wave Overhangs, Arc Supports, and backend improvements
- source-credit and research ledgers

## Excluded

- compiled app bundles
- native networking plugin binaries
- private printer profiles and credentials
- proprietary Rocket or FibreSeek assets
- full local Git history from experimental worktrees

## Validation Status

The feature-port notes record local smoke checks and installed-app verification for the private working copy. Public consumers should treat the patch as experimental source material and rerun their own build, smoke, and real-printer validation.

Strength Lens is advisory. It does not calculate certified stress, displacement, safety factor, or engineering allowables.

Wave Overhangs and Arc Supports are experimental toolpath-transform lanes. They require operator review and material/printer validation before use on real hardware.

Native FibreSeek planning is a standalone experimental path. It emits continuous-fiber G-code and summaries, but it does not ship proprietary continuous-fiber assets or certify hardware readiness.
