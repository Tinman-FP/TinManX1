# Profile Reliability Work

Authorized work window: September 5, 2026, 18:30 UTC through September 6,
2026, 00:30 UTC. Preserve tuned profiles, private connections, and ongoing
hardware jobs. Never send prints or motion/heater commands during this work.

Baseline: `a70a0d0d5a`, profile-foundation.1, installed full Apple Silicon build.

## Work Queue

- Complete: optional trace of the actual full-config resolver, with native
  Setting Origins UI, missing-profile warnings, and output-equivalence tests.
- Implemented: printer-selection preflight, duplicate dispatch, and physical
  connection cancellation fixes. Next: staged selection/rollback. Audit mutable fields and asynchronous callbacks
  before relying on a copied PresetBundle as a transaction snapshot.
- Next: layer/plate/object/volume-aware provenance using the real PrintApply
  merge stages, not a guessed override order.
- Next: exact inherited-key declaration provenance at load time. Flattened
  preset equality alone cannot prove which ancestor supplied a value.
- Required per installed milestone: native regression tests, real saved-project
  CLI G-code comparison, unchanged profile manifest, UI smoke test, updated
  splash revision, complete build, install, and reviewed GitHub push.

## Resolver Trace Design

The optional observer records existing merge operations rather than reimplementing
the resolver. Without a trace pointer, no history is collected. A trace contains
only settings present in the final global bundle. Connection credentials and
transport options are excluded. No automatic file export or telemetry is added.

Each merge records its resolved preset owner, logical material slot, parent name,
and applicable tool-variant projection. Actual differences from the stored preset
identify unsaved edits, independently of the aggregate dirty flag. The UI labels
the scope as global bundle: plate/object/volume/layer overrides and live printer
telemetry are not claimed. A parent label describes a relationship, not proof of
which ancestor originally declared an equal value.

Default CLI normative checks reject projects containing post-processing hooks.
For local regression fixtures containing our trusted auto-PA script, inspect the
hook and use `--normative-check=0`; do not change the project to bypass the check.
CLI slicing writes only to temporary output directories; it never starts prints.

## Progress

Implementation and tests are on the existing
`agent/snapmaker-live-filament-sync` branch. Private saved projects and settings
backups remain outside the public repository. The first milestone is
`v2026.09.05-profile-resolution.1`, package `2026.9.5.3`.

### Native Verification, First Milestone

- Nine provenance cases pass with 183,180 assertions. Every report entry matches
  the final untraced config; all 13 curated families and four nozzle variants are
  covered. Mixed four-tool routing, SLA, actual unsaved changes, empty/missing
  material fallbacks, credential exclusion, and absent metadata are included.
- Broader profile/configuration/hardware/CCF run: 84 cases, 184,174 assertions,
  all passed. The complete Apple Silicon GUI/CLI/test build passed, including
  an incremental rebuild for the final edits.
- Printer-selector dispatch previously invoked Tab::select_preset twice for one
  printer choice, and ignored cancellation before updating plate/config state.
  The printer branch now selects once and returns on cancellation. Stale model
  and preset choices are guarded; empty dependent-tab and optional variant fields
  no longer get dereferenced unchecked. This is not full transaction support.
- Previous physical-printer context is retained through both selectors. The old
  cancellation path restored it and then immediately unselected it.
- A real saved project produces identical G-code before/after, except its two
  generated timestamp comments: 167 layers, 3h 45m 38s. This is one fixture, not
  exhaustive output equivalence for every feature.
- All 936 profile manifest entries are unchanged. Release verification, five
  nozzle-capability cases, nine motion-envelope cases, and eight CCF golden
  fixtures (70 routes) passed. No machine was commanded or sent a print.
- Installed UI verified: overview, filter by nozzle_temperature, actual ordered
  override history, and warnings. Native About text now includes the revision,
  because SVG text alone was not visible through the app's image renderer.
- Prepare and preset-editor controls opened, but their custom preset dropdowns
  did not respond to CUA clicks. End-to-end switch/cancel smoke is therefore
  still unverified; native tests do not substitute for that missing GUI check.
- The full legacy suite has a separately reproduced pre-existing sinking-object
  convex-hull failure. Only the focused suites above are claimed green.

### Follow-up Risks Found During Review

- Single-material selection currently mutates the logical slot and exports
  selections before the preset dialog can be canceled. It needs staged commit;
  this milestone intentionally does not claim to fix that path.
- Some local-preset parse failures remove the JSON and .info files in
  PresetCollection::load_presets. A robust recovery pass should retain/quarantine
  malformed files rather than delete them; add failure-injection fixtures first.
- PresetBundle::operator= does not copy every mutable field. Do not introduce
  whole-bundle transaction rollback without a field-by-field ownership audit.
