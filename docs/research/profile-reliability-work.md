# Profile Reliability Work

Authorized work window: September 5, 2026, 18:30 UTC through September 6,
2026, 00:30 UTC. Preserve tuned profiles, private connections, and ongoing
hardware jobs. Never send prints or motion/heater commands during this work.

Baseline: `a70a0d0d5a`, profile-foundation.1, installed full Apple Silicon build.

## Work Queue

- Complete: optional trace of the actual full-config resolver, with native
  Setting Origins UI, missing-profile warnings, and output-equivalence tests.
- Complete within the documented scope: printer-selection preflight, duplicate
  dispatch, deferred material/color effects, staged preset/connection saves, and
  native cancellation checks. Whole-bundle rollback and asynchronous catalog
  generation barriers still require a field-by-field ownership audit.
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

- The fourth milestone defers logical-slot, color, and selection-export effects
  until after the preset dialog accepts the choice. See its scope below; this is
  still not a whole-bundle transaction.
- Fixed in the second milestone: local-preset parse failures removed JSON and
  .info files. Failed loads now retain the original files in place and log the
  reason. They are not silently converted to usable, partially loaded presets.
- PresetBundle::operator= does not copy every mutable field. Do not introduce
  whole-bundle transaction rollback without a field-by-field ownership audit.

### Recovery Milestone

Revision `v2026.09.05-profile-recovery.1`, package `2026.9.5.4`.

Three test cases (with generated failures and sections) reproduced 32 failing
assertions on the previous implementation. All 121 assertions now pass:

- Malformed JSON, invalid numeric data, non-object JSON, and an invalid version
  are skipped without deleting either the preset or its sync metadata. Healthy
  sibling profiles still load. Retrying leaves the original bytes intact, and
  repairing the same file allows it to load with its retained identity.
- The POSIX rename wrapper used to unlink the destination before renaming and
  reported `-1` instead of `errno`. It now uses the operating system's replace
  semantics directly. Missing sources, same-file rename, and file/directory
  mismatches are tested. The Windows implementation is unchanged.
- AppConfig no longer marks a failed final replacement clean. It logs the error,
  retains the temporary file, and remains dirty so the save can be retried.

The file replacement behavior follows the platform contracts in
[Apple's rename documentation](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/rename.2.html)
and the [Linux man-pages project](https://man7.org/linux/man-pages/man2/rename.2.html).
This is atomic namespace replacement on supported local filesystems, not a claim
of power-loss durability, network-filesystem guarantees, or a transaction across
JSON and .info together.

Focused native regression: 91 cases and 184,310 assertions passed. Complete
Apple Silicon build passed; the installed About dialog showed the correct
recovery revision and commit. Signature verification and all 936 installed
profile checksums passed. Saved-project G-code differed only in timestamps.
The verified commit was pushed; fast GitHub checks passed. The cross-platform
build was still running, not claimed complete.

### Preset Save Milestone

Revision `v2026.09.05-preset-save.1`, package `2026.9.5.5`.

Three initial failure cases reproduced 11 failing assertions: serialization could
truncate an existing file, failed saves changed the selected/stored preset and
cleared unsaved edits, and a damaged child reload replaced its tuned values with
parent defaults. The expanded suite passes 259 assertions across 11 cases.
The broader profile/config/hardware/CCF/AppConfig/file suite passes 102 cases,
184,569 assertions. The complete Apple Silicon build passed. Installed startup,
About revision/commit, signature, all 936 profile checksums, and the saved-project
G-code comparison passed (only timestamps differed). The reviewed commit was
pushed, and both quick GitHub workflows passed. Cross-platform builds remained
in progress.

- JSON is serialized before any file is opened. JSON and .info each use a unique,
  exclusively created, same-directory temporary, checked write/close, then
  replacement. Temporary permissions are private before writing; existing file
  permission bits are preserved. Non-regular targets, including symlinks, are
  rejected rather than silently replacing them. Failed temporary writes are
  cleaned up. UTF-8 paths, binary data, missing directories, and blocked targets
  are covered. Exclusive creation follows the standard `x` mode documented by
  [Microsoft](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/fopen-wfopen?view=msvc-170).
- A candidate preset is saved before insertion, stored-config replacement, or
  selection. Failed saves retain the current selection and editor state. Partial
  option saves stage their changes too. Protected identities return failure.
- Valid child reloads still inherit updated parent settings while preserving
  their overrides. Invalid child reloads leave the in-memory config intact.
- Save errors stop the tab-switch/close/new-project paths and are reported by
  calibration and printer-creation dialogs. Sync metadata writes report failure
  without throwing into background callers. Pending downloaded profiles retain
  their local-save marker until persistence succeeds. Save-related collection
  locks use RAII so exceptions cannot leave those locks held.
- Successful print/material/printer overwrite, Save As, detach, identity,
  inherited-diff round trips, and project-embedded saves are covered. No tuning
  values, process defaults, or hardware commands are changed.

Limits: JSON and .info are individually replaced, not an atomic pair. If JSON
replacement succeeds but .info fails, the JSON may already contain the new
values while the editor remains dirty for retry. Batch saves may have completed
earlier profiles before a later failure. These changes are not fsync durability,
network-filesystem guarantees, or full application transactions. Physical-printer
save UI and printer/material selection transactions remain separate audit work.

### Selection Commit Milestone

Revision `v2026.09.05-selection-commit.1`, package `2026.9.5.6`.

- Filament color is captured as a pending value, without applying it or queuing
  color events. Single-material selection first completes the tab's confirmation
  path; only accepted choices apply the material/color, flushing updates, dirty
  status, and persisted selection. Tab selectors use a success-returning callback
  instead of assuming the choice was accepted. Multi-material choices retain
  their existing independent-slot behavior without replacing the active editor.
- A native slot commit validates the requested printer identity, slot range, and
  actual visible preset. It stages allocations before swapping in the slot and
  project palette. Other material slots, active editor edits, process settings,
  printer settings, and connection selection remain unchanged. No compatibility
  filter is added: deliberately selecting a visible incompatible preset retains
  its existing warning behavior.
- Physical-printer selection now distinguishes not-applicable, accepted, and
  canceled outcomes. Cancellation does not continue into downstream plate/config
  updates. Stale associations cannot silently use a different nozzle preset.
- Confirmation is only requested when it is required. The old dependent-preset
  expression could show a dialog for a compatible material and then ignore
  Cancel. Explicit force-selection skips the dialog instead of showing it and
  ignoring its answer. The requested preset is revalidated after dialogs.
- Physical-printer parsing no longer drops the first two characters of a bare
  connection name to invent a preset name. Missing suffixes return no preset.

Four native cases pass 115 assertions, including all four logical slots, retained
editor edits, material-only choices, missing/hidden profiles, changed printer,
invalid slot, invalid color vector, and physical-name parsing. The broader suite
passes 106 cases and 184,684 assertions. The complete Apple Silicon build passed.
The installed About dialog showed revision selection-commit.1 and commit
7bd68c03db. Signature verification and all 936 installed profile checksums passed;
saved-project G-code differed only in two timestamp comments. The verified commit
was pushed to GitHub. A native new-project cancellation smoke on the preceding
preset-save build retained a temporary 0.35 mm edit; it was restored to 0.36 mm
without saving, and user preset-file checksums were unchanged.

Limits: this is a logical slot/palette commit and deferred GUI effects, not a
transaction across all preset collections or an asynchronous catalog generation
barrier. The custom dropdowns still do not respond to the available CUA
automation; native tests and code review do not replace that missing interactive
switch/cancel test. Successful explicit Save actions in an earlier confirmation
are not undone if a later confirmation is canceled.

### Connection Save Milestone

Revision `v2026.09.05-connection-save.1`, package `2026.9.5.7`.

Three generated-fixture tests reproduced 14 failing assertions: failed physical
connection saves mutated the stored record or selection, moved the draft's
config away, and malformed connection JSON was published as a default record.
Those initial 36 assertions pass after candidate-first persistence and explicit
parse-status checks. Eight connection/ancestor-save cases now pass 173 assertions;
the broader suite passes 114 cases and 184,857 assertions. Successful save and
rename round trips preserve credentials, selected identity and nozzle
associations. Failed imports, overwrites, renames, stale association requests,
malformed files and retries are covered. The complete 858-step Apple Silicon
build and final focused suite passed. The installed About dialog displayed
connection-save.1 and 75f92cef84. A temporary host edit was canceled in the native
connection dialog; reopening showed the original host, without a save or network
test. The dialog opened and closed cleanly. All user profile JSON/info hashes,
936 installed resource checksums, signature validation, and saved-project G-code
comparison passed (only two timestamp comments changed). The verified commit was
pushed to GitHub.

Additional GUI audit findings: Save As deleted the existing local/cloud profile
inside its name-confirmation dialog, before saving the replacement. Physical
connection associations were also changed before the new preset existed. The
connection dialog edited the live printer config directly, cached its values
before saving, and ignored the save result. Confirmation now gathers pending
requests only. The connection dialog uses a private draft and rejects saves if
the original printer changed in the meantime. Caller-side checks delay both the
connection backup and agent refresh until preset persistence succeeds. The
dialog's options group has explicit ownership and is released before its draft.
Connection association changes run after preset saves in direct Save As,
tab-switch, new-project and close paths. Errors report partial success rather
than implying that an earlier successful save was rolled back.

Removing the early-delete behavior exposed an existing inheritance defect:
overwriting an ancestor with a descendant could make the ancestor inherit
itself. A generated matrix reproduced 12 failing assertions. Such overwrites now
retain the target's previous ancestry while preserving the incoming effective
values and existing identity. Remaining cycles are rejected before writing.

Limits: connection JSON and application backup are separate saves, not a
multi-file transaction. A successful renamed-file write followed by failure to
remove its original reports an error and retains both files for recovery. New
collection insertion after persistence is not an out-of-memory transaction.
Normal authentication actions retain their existing external effects; no live
login, network test, upload or printer command is used for this milestone's QA.

Prusa 3 alpha11's physical-printer code is not being copied wholesale. Its
separate hardware configuration and connection identity are useful boundaries,
but PhysicalPrinterStorage::save_one writes directly and reports no success to
its caller. PhysicalPrinterInteractor updates memory before that write. Also,
load_all calls consolidate_files after skipping invalid files, and consolidation
removes files whose stems are not present in the loaded map. TinManX1 should not
adopt those failure-handling behaviors. Inspection source is the previously
recorded 6f510128d7c2e543b62919b74bea7e876f564205 checkout, under
src/slic3r-shared/src/Slic3r/Biz/PhysicalPrinter.

### Build Identity Milestone

Revision `v2026.09.05-build-identity.1`, package `2026.9.5.8`.

The commit hash was a global compiler definition and the revision was in the
common precompiled version header. Every commit/revision therefore invalidated
almost the entire local build. Build identity now has its own generated header,
included only by About, startup/splash, troubleshooting, and Windows crash
reporting. Core slicing and profile code no longer depends on volatile metadata.
The troubleshooting commit link now points to TinManX1, not the upstream Orca
repository where these commits do not exist.

Eight disposable CMake/Git fixtures pass. They cover archive fallback, verified
explicit hashes, invalid hashes, unchanged configure timestamps, revision-only
changes, commits, detached HEAD, linked worktrees, and packed refs with reflogs
disabled. Commit/revision changes update the displayed build ID and recompile
the metadata consumer while preserving the unrelated core object timestamp.
The next no-op build does no work. These fixtures are now a public-helper CI step.
The shallow-checkout fixture initially failed and now preserves CI's explicitly
declared full commit ID when the corresponding object is not present locally.
An unknown abbreviated ID is rejected instead of guessed. Archive/shallow IDs
are supplied build metadata, not a claim that the local object was verified.
The complete application migration build passed in 602 seconds with 858 steps,
and the focused native suite passed 114 cases and 184,857 assertions. The next
real application metadata-only rebuild automatically picked up commit b4c59e63c5,
scheduled eight steps, and finished in 17 seconds. The installed native About
dialog showed that commit and build-identity.1. Signature, 936 profile checksums,
and real saved-project G-code verification passed (only two timestamps changed).
The milestone was pushed and both quick GitHub workflows passed. This is a
measured incremental-build improvement, not a runtime slicing-speed increase.

This uses CMake's documented [configuration dependencies](https://cmake.org/cmake/help/latest/prop_dir/CMAKE_CONFIGURE_DEPENDS.html)
and [content-stable configure_file output](https://cmake.org/cmake/help/latest/command/configure_file.html).
Git's [git-path resolution](https://git-scm.com/docs/git-rev-parse) locates private
worktree HEAD and shared refs. Missing loose refs use their nearest existing
directory as a configure dependency so their later creation is noticed. This
can cause an extra configure after Git bookkeeping changes, but unchanged
metadata does not trigger a compilation. No runtime slicing speed claim is made.

### Project Recovery Milestone

Revision `v2026.09.05-project-recovery.1`, package `2026.9.5.9`.

Four generated-fixture tests first reproduced ten failures: standalone embedded
roots were not exported, newly sorted profiles changed the selected identity,
archive-order inheritance failed, and printer credentials entered profile
exports. A real 3MF round-trip then reproduced 15 additional assertions at the
archive-writing boundary. Those cases now pass. Eleven native cases pass 3,805
assertions, including independent standard/high-flow material values and nullable
inherited overrides. The standard native suite passes 217 cases and 237,021
assertions; it excludes the previously documented hidden sinking-object test.
Complete GUI build and installed smoke verification follow.

- Embedded roots export their effective values, and loaded roots apply defaults
  plus their own settings. Named missing/cyclic parents are not guessed; their
  input records remain intact and are logged/skipped. Parent-child chains load
  even when archive entries arrive in reverse order. Empty identities, duplicate
  entries, unrelated types, and empty filament identity arrays are guarded.
- Project imports stage private candidates and preserve input configs. Import
  diagnostics previously used new with free and were aliased by Preset copies.
  They now have immutable shared ownership; reports clone their owned values,
  and published presets do not keep transient diagnostics. Copies, destruction,
  successful reporting and malformed-input retry have focused coverage.
- Sorting preserves the selected identity without discarding editor changes.
  This covers project imports and ordinary saved-profile loading, including
  generic-first material ordering. Import/export locks and temporary exported
  profile ownership use RAII.
- Embedded printer exports and both project-config archive writers omit the
  known runtime connection options. Existing profile JSON and AppConfig
  connections remain unchanged. The writer no longer replaces a source preset's
  file path with its temporary path, and failed archive additions propagate.
- Real 3MF tests retain geometry and tuned process/material/printer values,
  reject empty identities without crashing, and verify that known connection
  keys are absent from both global and embedded configs. Filtering is not a
  general scanner for arbitrary user-authored secrets in custom G-code or text.

This remains staged per-collection import, not an all-or-nothing transaction
across every collection or an out-of-memory/power-loss guarantee. Earlier healthy
imports may remain available when a later malformed record reports an error.
No filament tuning, machine capability, or process defaults are changed.
