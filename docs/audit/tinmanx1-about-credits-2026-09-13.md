# About Branding and Credits

## Findings

The installed About dialog had a TinManX1 window title but displayed inherited
Orca artwork, emphasized the upstream version, and linked to Orca's website.
Its branded SVG relied on text elements that NanoSVG does not render. The body
acknowledged upstream lineage but did not identify project stewardship or expose
the existing feature attribution in its license dialog.

## Changes

- Use the existing TinManX1 PNG logo and native product, revision, build, and
  upstream-version labels. The name no longer depends on SVG text rendering.
- Link to the TinManX1 repository and expose Credits and Licenses.
- Credit William Tinney / Tinman-FP and OpenAI Codex with their distinct roles.
- Retain upstream slicer acknowledgments, the existing library list, and AGPL
  information. Add the previously documented feature authors and research
  references without implying vendor endorsement or proprietary code reuse.
- Keep the PrusaSlicer 3.0.0-alpha11 inspiration distinct from a full rebase.
- Update the published Wave Overhang paper reference and named authors in the
  source attribution ledger.
- Keep the splash and About revision synchronized at
  `v2026.09.13-about-credits.1`.

No slicing algorithms, printer connections, filament tuning, or printer/process
profiles are changed.

## Verification

`checks/test_about_dialog_contract.py` reproduces the missing brand/credits
before the change and passes afterward. CI runs it with the existing build
identity, handoff, release, profile, and FibreSeek checks. These source checks
are guards, not substitutes for visually checking the native About and scrolling
Credits and Licenses dialogs in an installed build.
