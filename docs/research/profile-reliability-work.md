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
- Complete within the documented scope: recoverable config/import/cloud writes,
  cloud account-session rejection, deterministic print/tower state, reversible
  model-dependent normalization, and material-only height-range inheritance.
- Next after the user's return: finish the installed GUI smoke test after macOS
  Keychain authorization, including end-to-end printer switch/cancel and a
  representative mixed-tool slice. Do not bypass that authorization while away.
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

The complete 267-step GUI build and installation passed. Signature, all 936
resource profile checksums, and user JSON/info hashes passed. The reference
saved-project G-code changed only its two timestamp comments. Thirteen offline
printer-integration cases passed 77 assertions. Installed startup reached a macOS
Keychain authorization prompt; a process sample shows the main thread waiting in
wxSecretStore::Load / SecKeychainFindGenericPassword, not preset loading. No
credentials or Keychain permissions were changed. The test launch was closed;
this revision's interactive About/project smoke remains unverified.

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

### Cloud Recovery Milestone

Revision `v2026.09.05-cloud-recovery.1`, package `2026.9.5.10`.

Six offline cloud-import fixtures reproduced 37 failing assertions. The expanded
suite passes 12 cases and 124 assertions. The standard native suite passes 229
cases and 237,145 assertions. No live login or synchronization is used in tests.

- Remote updates previously merged unsaved editor tuning into the stored preset,
  then marked that preset for automatic disk persistence. Remote data now stays
  in the stored baseline, while actual local edits remain in the editor until an
  explicit save. Clean updates advance the editor and its saved comparison
  baseline together. Matching values become clean without a false dirty warning.
- Actual config differences determine whether changes need preservation, rather
  than trusting a stale dirty flag. The GUI snapshot path uses the same check,
  recomputes dirty status after restoration, and restores snapshots after an
  ordinary synchronization exception before reporting partial success.
- Repeated responses retain pending local-write markers. Failed metadata writes
  leave in-memory metadata unchanged. Unassigned file paths cannot write a stray
  .info file. Invalid timestamps, protected identity collisions, cyclic parents,
  missing parents, and insertion into an unselected catalog are handled without
  overwriting valid data. Subscribed bundle identities remain independently
  updatable. Import locks use RAII and diagnostics publish only after success.
- Tests include process values, independent standard/high-flow material vectors,
  mixed four-nozzle printer vectors, save/reload, stale flags, rejected-input
  retry, selection preservation, and protected system/default/project/external
  identities.

This is not a whole-bundle transaction or an asynchronous account-generation
barrier. Vendor installation and earlier successful records may have effects
before a later error. The existing server-driven deletion policy is not rewritten
here. The complete application build, installation, signature and all 936
resource-profile checksums passed. Reference G-code differed only in two
timestamp comments. Interactive verification remains limited by the documented
Keychain authorization prompt; the installed application is closed. Both quick
GitHub workflows passed. The expanded FFF failure is addressed separately below.

### Defined Print Origin Milestone

Revision `v2026.09.05-print-origin.1`, package `2026.9.5.11`.

The expanded FFF suite exposed a brim coordinate-range exception. A newly
default-constructed Print left its Eigen plate-origin vector uninitialized;
PrintInstance::shift_without_plate_offset read that value before callers had
necessarily assigned an origin. The same declaration exists in the work-window
baseline. A placement-construction test with deliberately nonzero backing bytes
reproduced the missing initialization deterministically before the fix.

The member now starts at Vec3d::Zero(). Explicit origins still round-trip and
clear() retains the assigned plate origin. The regression test passes and the
entire standard FFF suite now passes 38 cases and 568 assertions, including both
brim configurations that previously threw. The complete 180-step application
build passed; the saved-project G-code differed only in its two timestamp
comments, and the standard native suite passed 229 cases / 237,145 assertions.
No tuning values or coordinate clamping changed.

Eigen documents that its [default matrix constructor does not initialize coefficients](https://eigen.tuxfamily.org/dox/group__TutorialMatrixClass.html).
This fix initializes the member directly instead of relying on allocation history
or a build-wide Eigen macro.

### Wipe Tower State Milestone

Revision `v2026.09.05-tower-state.1`, package `2026.9.5.12`.

Four generated state fixtures reproduced 23 failed assertions: new collision
geometry was uninitialized, reset retained old height/taper/bounds, and switching
tower implementation retained incompatible wall/rib/rotation data. These are
derived values, not user profile settings. They now start empty and reset at
print clearing and tower regeneration; each setter replaces the incompatible
data from the other implementation. Type 1 also publishes its measured height.

An expanded real two-material test exposed another baseline uninitialized field,
Print::m_isBBLPrinter. It could select Type 1 despite a Type 2 setting. The field
now defaults to false; explicit GUI/CLI assignments and clear() retention are
unchanged. The test processes Type 1, Type 2, Type 1 again, and finally no tower.
It checks real walls, taper, bounds, height and collision layers at each stage.

Eight focused tower cases pass 100 assertions. Missing taper tables use a
constant-depth rectangle, equivalent to an explicit constant-depth table.
Non-finite or nonpositive layer height on a nonempty tower produces a slicing
error rather than a non-advancing loop; zero-height empty towers return no paths.
Rotated path bounds allow one scaled coordinate unit of rounding. These changes
do not redesign the tower or claim a complete geometric validation audit.

PrusaSlicer alpha11's [Print.cpp](https://github.com/prusa3d/PrusaSlicer/blob/6f510128d7c2e543b62919b74bea7e876f564205/src/libslic3r/src/libslic3r/Print.cpp)
replaces its optional tower result before regenerating it. Its value-initialized
data fields and explicit absence are useful lifecycle guidance. TinManX1 retains
both existing tower implementations and its current GUI/framework. The complete
180-step application build, installation, signature and 936 resource-profile
checksums passed. Standard FFF tests passed 46 cases / 670 assertions; standard
native tests passed 229 cases / 237,145 assertions. The saved-project G-code
differed only in two timestamp comments. The application remains closed because
interactive startup awaits the user's Keychain authorization.

### Cloud Library Milestone

Revision `v2026.09.05-cloud-library.1`, package `2026.9.5.13`.

Seven offline deletion cases pass 30 assertions. Five initial cases reproduced
seven failed assertions before the corrections. Deletion now checks actual editor
differences, preserves the selected identity when an earlier deque entry is
erased, and never deletes externally imported files during cloud reconciliation.
Pending local writes and local-only presets stay intact. A clean cloud-deleted
preset still disappears even if a stale dirty flag was set. Empty file paths
cannot remove an unrelated working-directory .info file. Mixed-tool and
standard/high-flow material vectors are covered without modifying real profiles.

The full-library HTTP path previously reused the incremental synchronization
cursor, accepted a response missing its upserts array as an empty library, and
published records one by one. It now requests a cursor-free snapshot, validates
the complete response privately, and swaps the output only after success.
HTTP 304 is not an empty full library. Missing lists, malformed records, duplicate
names/identities, conflicting account metadata, invalid timestamps and explicit
incomplete-page indicators reject the response without publishing partial data.
An explicit valid empty upserts array remains a legitimate empty library.

Account-session stamps prevent a response fetched before an account change from
being published. The queued GUI refresh checks the agent, account revision and
active profile folder again before profile/vendor mutations. An ordinary token
refresh for the same logged-in account retains the stamp; logout or account
replacement invalidates it. Default sync result scalars are initialized, including
the incremental HTTP 304 response cursor. Other providers retain their interface
compatibility; the generation-aware implementation is the Orca profile service.

Ten parser/session-stamp cases pass 104 assertions, including large timestamps,
nullable material values, mixed nozzle vectors, failure retry and unchanged caller
output after a malformed later record. Authentication fixtures now explicitly
disable persistence as well as notification; no live authentication or credential
store access is needed to exercise the session revision logic.

Limits: this validates the client's expected snapshot contract, not the server's
truthfulness about completeness. It is not a transaction across every vendor,
profile collection, metadata file and incremental-sync worker. Existing logout
confirmation ordering and incremental cursor persistence need a separate audit.
Deletion failures are not a paired-file power-loss transaction. The complete
application build passed, followed by 246 standard native cases / 237,279
assertions, 46 existing standard FFF cases / 670 assertions, and 15 offline GUI
utility cases / 97 assertions. The reference G-code differs only in two timestamp
comments, and all 936 repository/installed resource profiles match the manifest.
The newly added material-transition regression is handled in the next milestone;
it reproduces an existing prime-tower normalization issue, not a cloud change.

### Current Model State Milestone

Revision `v2026.09.05-model-state.1`, package `2026.9.5.14`.

A reproducible test showed that adding a second material after a single-material
slice left the requested prime tower disabled. The initial normalization used
the old model's material count, and the second pass could only disable the
already-normalized value. It also ran before region assignments were refreshed.

The two model-dependent inputs are retained privately, then resolved again after
the current volumes, regions and support assignments exist. Actual derived
changes invalidate the relevant slicing/support stages and update object defaults,
object instances and the full config consistently. The pre-projection config used
for later filament-map recalculation stays consistent too; tests reproduced 12
stale-value assertions before that additional correction. Unchanged reapplication
remains a no-op, and an explicitly disabled tower never becomes enabled.

Two expanded cases pass 108 assertions across both tower styles, whole-volume and
height-range material assignments, single/multiple/single cycles, independent
support-layer settings, sequential object-count changes and repeated no-op calls.
The full standard FFF suite passes 48 cases / 778 assertions. The complete Mac
build passed, as did 246 native cases / 237,279 assertions. Reference G-code still
differs only in the two timestamp comments. No real profile tuning changed.

The height-range fixture also exposed a separate null dereference when an imported
range changes material but omits layer_height. The transition test supplies an
explicit height here; inheritance for an absent range height is the next focused
correction rather than being silently claimed fixed by the tower change.

### Height-Range Inheritance Milestone

Revision `v2026.09.05-layer-ranges.1`, package `2026.9.5.15`.

A real FFF material-range fixture crashed in layer_height_profile_from_ranges
because it dereferenced an absent layer_height option. The Mac crash report
identified that exact function. A range that only changes material now inherits
the object's normal layer height without inserting an override into the model.
Explicit overrides retain their transitions. Wrong option types and nonpositive
or non-finite explicit heights produce SlicingError instead of propagating unsafe
heights into layer generation; four invalid-value checks failed before the guard.

This follows the explicit optional override/default selection in PrusaSlicer 3
alpha11's [LayerHeight.cpp](https://github.com/prusa3d/PrusaSlicer/blob/6f510128d7c2e543b62919b74bea7e876f564205/src/slic3r-biz-algorithms/src/Slic3r/Biz/Algorithms/LayerHeight.cpp).
TinManX1 keeps its existing geometry representation and algorithm. The range
comparison also recognizes two absent overrides as equal. Without that change,
the expanded FFF tests reproduced two unnecessary full invalidations on identical
reapplication. Presence changes and real height changes still invalidate.

Four focused geometry cases pass 31 assertions. The expanded real tower/material
cycle passes 200 assertions across two cases, including explicit and inherited
range heights. The complete Mac application build passed; all 250 standard native
cases / 237,310 assertions and 48 standard FFF cases / 870 assertions passed.
The reference saved-project G-code still differs only in two timestamp comments.
Final independent checks also pass: five nozzle-capability tests, nine motion
envelope tests, eight build-identity fixtures, and eight CCF golden fixtures with
70 routes. Installed-package signature/identity and GitHub status are checked
separately after committing the final code.

### Incremental Sync and Native Branding Milestone

Revision `v2026.09.05-branding-sync.1`, package `2026.9.5.16`.
The preceding `layer-ranges.1` revision completed its entire cross-platform
GitHub workflow successfully, including macOS Universal, Windows, Linux,
Flatpak, and unit tests.

An offline extraction of the existing incremental-sync parser reproduced 31
failed assertions across four cases. Its `json.value(key, 0)` calls inferred a
32-bit result even though the destination was 64-bit: a cursor of 1,788,633,045,717
became 1,926,650,581. The same pattern affected conflict and upload timestamps.
Checked protocol decoding now preserves nonnegative 64-bit values and rejects
invalid numeric types or overflow. A malformed later profile cannot publish a
partial parsed page. Optional timestamps and deletion lists remain supported;
continuation pages with a valid cursor remain legal.

Cursor reload now starts from zero and accepts only a complete nonnegative
decimal value (including legacy LF/CRLF endings). Tests reproduced stale state
when changing to an account with no cursor file and when removing the current
file. Account replacement now binds the session and its cursor under the same
lock; token refresh retains the active position. Incremental responses are
checked against the requesting session before callbacks and cursor publication.
An expired-cursor retry leaves the durable file intact until an accepted result
replaces it. Cursor saves use the existing checked atomic-replacement helper;
failure is reported and the caller restores the prior in-memory cursor.

Five focused cases pass 114 assertions, covering large and invalid timestamps,
malformed/optional page fields, account switching, token refresh, newline
compatibility, blocked destinations, and repeatable saves. The complete offline
GUI utility suite passes 20 cases / 211 assertions. The complete Mac build and
250 standard native cases / 237,310 assertions and 48 FFF cases / 870 assertions
pass. All 936 resource profiles and the saved user-profile checksum baseline
remain unchanged. These are offline fixtures,
not a claim that every cloud-server, cancellation, or account-switch race has
been integration-tested. The whole-bundle and logout-ordering limitations remain.

The macOS menu used wxWidgets' fallback display name derived from the compatibility
key. Setting `SetAppDisplayName(SLIC3R_APP_NAME)` fixes the native Hide/Quit labels
without changing `SetAppName(SLIC3R_APP_KEY)`, profile directories, or credentials.
The installed application was visually checked: Hide TinManX1 and Quit TinManX1
are present, and About displays the new revision and PrusaSlicer credit. Native
splash text and both light/dark artwork variants credit improvements inspired by
PrusaSlicer 3.0.0-alpha11. OrcaSlicer 2.4.2 remains identified as the actual base;
the UI does not misrepresent this work as a complete PrusaSlicer 3 rebase.
The release verifier now guards the native display-name call and these credits.

## Overnight M1: Purge Layout Ownership (September 6 UTC)

The new overnight authorization runs through September 6, 2026, 12:00 UTC
(8 AM Eastern). No live printer operations or interactive acceptance checks are
part of the unattended work. The installed branding-sync build remains in place;
verified candidates are built in the source build directory without interrupting
the user's open application.

`update_multi_material_filament_presets()` previously rebuilt the purge matrix
only when the logical material count changed. Switching between one, two, and
four physical tools while retaining four materials updated the multiplier count
but left the matrix at its old dimensions. A second defect removed the tail of
the load/unload volume list when deleting an earlier material, associating the
remaining materials with the wrong purge pairs. Two regression cases reproduced
eight failing assertions before the fix: six tool transitions and two deletion
positions.

The routine now treats material rows/pairs and physical-tool planes separately.
Existing manual matrix cells and multipliers are retained wherever their original
indices remain valid; newly added cells use the existing material-volume rule,
without increasing tuned values or introducing new defaults. Deletion remaps
both volume pairs and matrix rows/columns. When the tool-count minimum adds a
replacement slot, its cells are initialized instead of indexing beyond the old
matrix. Incomplete/non-square matrix layouts are rebuilt from material volumes;
incomplete volume pairs recover to complete pairs. The three purge arrays are
staged before their swaps. This is not a claim that the entire preset bundle or
GUI selection workflow is transactional.

Five focused cases pass 3,507 assertions, including 27 material-count transitions,
nine tool-count transitions, first/middle/last deletion, minimum-slot replacement,
incomplete arrays, and repeat-call stability. The complete Mac build passed, as
did 255 standard native cases / 240,817 assertions, 48 FFF cases / 870 assertions,
and 20 offline GUI utility cases / 211 assertions. Release and FibreSeek release
checks passed. The trusted 167-layer reference slice still estimates 3h 45m 38s;
its G-code differs from branding-sync only in the two generation timestamp
comments. All 936 resource profiles and the saved user-profile checksum baseline
remain unchanged. Revision: `v2026.09.06-purge-layout.1`, package `2026.9.6.1`;
both splash and About artwork variants were updated, retaining native revision
rendering and accurate Prusa credit.

Remaining material-slot work is separate: palette resizing can overwrite existing
multi-color data, and deletion/resizing at the tool-count minimum can leave the
palette and mapping lengths behind the material list. Those paths need their own
reproductions and tests before changes. The dormant filament-option initializer
is still intentionally untouched.

## Overnight M2: Material Slot Alignment

Two additional cases reproduced 82 failed assertions before changes: both resize
overloads replaced existing multi-color entries with their primary color even
when the requested count did not change, and palette/tool-map lengths could lag
behind the material list at the physical-tool minimum. With an incomplete primary
color list, deletion also truncated an otherwise complete tool map. Inspection
identified unchecked indexing of a short caller-supplied new-color list and
unchecked deletion of an unavailable or last material slot.

The string-color overload now delegates to the vector-color implementation.
The requested material count respects the existing physical-tool minimum before
resizing, and supplied colors apply only to genuinely new, available slots. Slot
array normalization happens after the final material count is known, preserving
existing multi-color entries, modes, and tool mappings. Deletion erases each array
independently; missing tails are initialized without truncating unrelated state.
Unavailable/last-slot deletion is a logged no-op. Empty palettes use the existing
configuration default. Physical nozzle geometry, process settings, material
tuning, and the dormant filament-option initializer are unchanged. Array staging
does not make the whole selection/editor/connection workflow transactional.

Five new cases pass 958 assertions, covering 24 resize scenarios, complete/short
palettes, first/middle/last deletion on two- and four-tool fixtures, partial color
requests, unavailable deletion, empty arrays, and mixed 0.6/0.4/0.4/0.6 nozzle
geometry preservation. Together with M1, the ten targeted cases pass 4,465
assertions. The complete Mac build, 260 standard native cases / 241,775 assertions,
48 FFF cases / 870 assertions, and 20 offline utility cases / 211 assertions pass.
Release/FibreSeek checks and all 936 resource profiles pass; saved user-profile
checksums are unchanged. The reference slice again differs only in its two
timestamp comments, with identical 167 layers and 3h 45m 38s estimate.

Revision `v2026.09.06-material-slots.1`, package `2026.9.6.2`, updates the splash
and About revision and retains the accurate Orca base/Prusa inspiration credit.
The installed app is intentionally not replaced while the user is absent. The
next acceptance work remains complete GUI switching/cancellation and saved-project
round trips with real multi-tool projects, not just these synthetic array tests.
GitHub's older branding-sync build run was cancelled when superseded by the new
push, not reported as a compiler/test failure; matching latest-head CI must still
be checked before claiming cross-platform success for the overnight work.

## Overnight M3: Comparison Transfer Cancellation

`Tab::transfer_options()` ignored the result of selecting the comparison's
destination. If its unsaved-changes dialog was cancelled, the caller still
applied cached options to the previously active editor. It also used fallback
preset lookup for missing comparison entries, and the all-profile comparison
loop continued with later types after cancellation.

A headless extraction of that transfer control flow reproduced five failed
assertions in two cases: cancellation and a callback returning success without
actually selecting the requested destination. This was an offline reproduction,
not an interactive GUI test. The new core `transfer_preset_options()` is used
directly by the comparison UI. It resolves source/destination without fallback,
captures source values before any selection dialog, validates requested option
indices, honors cancellation, and rechecks the destination afterward. A candidate
config receives all selected values before publication, so a bad later value
cannot partially overwrite the editor. Selection exceptions are reported without
applying the captured values. Comparison transfers no longer use the persistent
tab transfer cache. The caller returns success/failure, and multi-profile
comparison stops at the first cancelled or rejected transfer.

Fourteen focused cases pass 93 assertions, including missing/hidden profiles,
changed destinations, source changes during confirmation, unrelated destination
edits, current-editor transfers, individual mixed-nozzle/material-variant entries,
tool-count transfer/cancellation, malformed indices, invalid values, empty
requests, missing handlers, and selection exceptions. The complete Mac build
passed. All standard local suites passed: native 274 cases / 241,868 assertions;
FFF 48 / 870; offline utilities 20 / 211; SLA 21 / 13,360; nesting 14 / 488.
That is 377 cases / 256,797 assertions, excluding the separately documented
pre-existing hidden legacy failure and network-dependent tests. Release/FibreSeek
checks, the 936-profile manifest, and saved-profile checksums passed. The reference
G-code differs only in its two timestamp comments.

Revision `v2026.09.06-preset-transfer.1`, package `2026.9.6.3`, updates splash/About
revision text. The local candidate remains staged rather than replacing the
installed app. Important limits remain: earlier successful transfers or explicit
saves are not rolled back when a later profile is cancelled; this is not a whole
bundle transaction. The separate unsaved-changes transfer cache used during
multi-dialog printer selection still needs its own lifetime/cancellation audit.
Actual comparison-dialog and mixed-tool project UI acceptance remains pending
until the user is present.

## Overnight M4: Cancelled Selection Transfers

Code review of the separate unsaved-changes selection path found that one dialog
could stage a process transfer, then a later filament dialog could cancel the
printer switch without removing that pending transfer. A future accepted switch
could apply the old values. The configuration, selected-option list, and pending
extruder count now form one cache state. A confirmation scope snapshots existing
tab caches and restores them on cancellation or an exception during confirmation.
It preserves transfers deliberately postponed by an outer setup/project workflow
rather than clearing every cache indiscriminately. Explicit rollback occurs before
cancelled-selection UI notifications, with no dependent-tab cache application.
Once confirmations and deletion have succeeded, the existing application path
owns the caches; the guard does not resurrect them after consumption.

Review also found dependent edited presets were discarded before final target
validation or a requested deletion could fail. Those discards are now deferred
until the accepted branch. Explicit successful saves made in earlier dialogs are
still retained. This is not a whole-bundle selection transaction: a failure during
the later selection/application phase is not rolled back by this confirmation
scope, nor are independent asynchronous collection changes made transactional.

Six new native cases exercise cancellation followed by a future application,
pre-existing mixed-nozzle cache restoration, explicit/idempotent rollback,
successful commit and consumption, exceptions, nested scopes, and null/duplicate
tab entries. They pass 41 assertions; combined with the earlier comparison tests,
20 cases pass 134 assertions. These tests exercise the production cache guard,
not actual wxWidgets dialogs. The dependent-discard ordering change was reviewed
and compiled, but requires the same interactive cancellation/target-disappearance
acceptance checks as the surrounding selector workflow.

Both complete Mac builds passed. Standard offline suites passed: native 280 cases
/ 241,909 assertions, FFF 48 / 870, offline utilities 20 / 211, SLA 21 / 13,462,
nesting 14 / 488. Total: 383 cases / 256,940 assertions. Release and FibreSeek
checks passed, the 936-profile manifest and saved-profile checksums are unchanged,
and the reference slice still has 167 layers and an estimate of 3h 45m 38s. Its
G-code differs from M3 only in the two generated timestamp comments.

Revision `v2026.09.06-selection-cancel.1`, package `2026.9.6.4`, updates splash/About
revision text. The candidate remains staged; `/Applications/TinManX1.app` is not
replaced. Logs are `/tmp/tinman-transfer-cache-*.log`, with the reference output in
`/tmp/tinman-transfer-cache-slice/plate_1.gcode`.

M3 commit `5cb8db1405` completed the entire GitHub platform matrix successfully
in run `34006710543`. After waiting for that result rather than cancelling the
build, M4 was published as `c43d437440` to the existing `tinman` branch. PR #21
verification comment: `5556896216`. M4's helper and shell checks passed; its full
matrix is run `34011615809`, still pending at the next checkpoint.

## Overnight M5: Indexed Setup Transfers

The setup-wizard keep-modifications path removed `#index` from dirty option keys
before caching them. Keeping a change to one nozzle or material variant could
therefore copy the old printer's entire array over other destination entries.
The current unsaved-changes UI keeps all displayed dirty items, not individually
checkable sub-items; the problem is the expansion from those dirty indices to
unchanged indices in the previous printer's array. Ordinary new-project partial
selection is currently dormant (`has_unselected_options()` always returns false),
so this change is not described as fixing an active partial-selection UI there.

A headless extraction of the previous wizard normalization and tab cache staging
reproduced three failures: a four-nozzle destination lost its unselected values,
a four-entry material variant array did the same, and a late invalid option
partially replaced a previously pending cache. Three cases / eight assertions
had six failures. These were an extracted code-path reproduction, not a live
wizard run. The GUI now preserves the indexed keys and delegates staging to
`PresetTransferCache::stage_options`, which constructs the new config and key
list before swapping them into the pending cache. Old unselected cache values
are dropped, while a separately requested tool count is retained.

Five new production-helper cases pass 16 assertions. Explicit whole-array copies
still work, individual nozzle/material entries preserve other destination values,
failed preparation keeps the previous cache, and repeated or empty preparation
has defined replacement behavior. All transfer-related tests together pass
25 cases / 150 assertions.

The complete Mac build passed. Standard offline suites passed: native 285 cases /
241,925 assertions, FFF 48 / 870, offline utilities 20 / 211, SLA 21 / 13,547,
nesting 14 / 488. Total: 388 cases / 257,041 assertions. Release/FibreSeek checks,
the 936-profile manifest, and saved-profile checksums passed. The reference slice
still has 167 layers and an estimate of 3h 45m 38s; G-code differs from M4 only in
the two timestamp comments. Logs are `/tmp/tinman-setup-transfer-*.log`; the slice
is `/tmp/tinman-setup-transfer-slice/plate_1.gcode`.

Revision `v2026.09.06-indexed-transfer.1`, package `2026.9.6.5`, updates splash/About
revision text. The candidate remains staged, not installed. The verified local
M5 commit `ae6fafb69b` is queued for publication after M4's run `34011615809`
finishes, to avoid cancelling another platform matrix. Further locally verified
milestones are batched into that next push rather than making each small change
wait for a separate full platform build. Each milestone still completes its local
implementation, review, build, offline tests, and work record before the next one.

Remaining limitations include actual wizard acceptance, rollback of postponed
transfers if the outer wizard fails after staging, and destination validation
when a kept index no longer exists on a smaller tool layout. Cache preparation
is atomic; later application of an entire bundle is not. Do not claim these
native helper tests validate the complete interactive setup/project workflow.

## Overnight M6: Explicit Comparison Tool Counts

Direct tests of the production comparison-transfer helper found that both whole
nozzle arrays and indexed nozzle edits could change the destination's tool count
without transferring `extruders_count`. This bypassed the normal resizing of
companion tool settings. A separate test found that a requested FFF tool count
was accepted for an SLA-tagged destination. Three cases covering generated layout
combinations had 26 failures out of 81 assertions before the change.

The candidate now records the destination nozzle count after confirmation and
requires an explicit tool-count transfer for any resulting count change. An
explicit count still uses `set_num_extruders` to resize companion settings. FFF
counts are rejected for an SLA destination before entering that resize path.
The final candidate count is checked before publication, so unsupported changes
leave the destination config intact and provide an explanation. This check is
specific to printer/nozzle topology; it does not indiscriminately prohibit
expansion of broadcast material-variant arrays.

Four new cases pass 84 assertions: all 1/2/4-tool source/destination combinations
with and without explicit count transfer, all four indexed source nozzles into
a two-tool destination, an SLA-tagged destination, and a destination resized
during confirmation. All transfer-related tests together pass 29 cases / 234
assertions. The earlier whole-array cache test now uses an already-four-tool
destination so it tests value copying without implying permission to change
physical topology.

The complete Mac build passed. Standard offline suites passed: native 289 cases /
242,009 assertions, FFF 48 / 870, offline utilities 20 / 211, SLA 21 / 13,447,
nesting 14 / 488. Total: 392 cases / 257,025 assertions. Release/FibreSeek checks,
the 936-profile manifest, and saved-profile checksums passed. Reference G-code
differs only in its two timestamp comments, with 167 layers and an estimate of
3h 45m 38s. Logs are `/tmp/tinman-transfer-layout-*.log`; the slice is
`/tmp/tinman-transfer-layout-slice/plate_1.gcode`.

Revision `v2026.09.06-transfer-layout.1`, package `2026.9.6.6`, updates splash/About
revision text. The candidate is staged, not installed. M5 and M6 are queued for
one publication after M4's run `34011615809` completes; check that run and publish
the reviewed local commits to `tinman`, then record the matching CI and PR
verification. No pending platform run is described as passed.

Publication follow-up: M4's entire matrix completed successfully. M5/M6 were
published together through `75b3946597`; PR #21 verification comment is
`5557475078`. The matching M6 full build is `34016724153`, still in progress
without failed jobs at the M7 checkpoint. The queue note above records the
earlier local checkpoint, not the current branch state.

Scope remains explicit: M6 guards the comparison helper, not the separate wizard
cache-application path. A destination successfully selected by the callback is
not switched back if its requested transfer is subsequently rejected. The
whole selection workflow is still not transactional. Remaining work includes
wizard failure cleanup, topology-aware application of postponed wizard changes,
and interactive comparison/setup/project acceptance with the user present.

## Overnight M7: Mixed-Tool Archive Verification

The portable 3MF test now exercises three synthetic layout shapes: four mixed
0.6/0.4/0.4/0.6 nozzles, two 0.6/0.8 IDEX-shaped tools, and 0.4/0.7 plastic/fiber
tools. These are schema fixtures inspired by U1, Rat Rig, and Seeker layouts,
not loaded production machine profiles or live printer tests. Each shape is
combined with the four existing valid/empty embedded-profile identity cases.
Each of those 12 scenarios writes, reloads, writes again, and reloads again:
24 real archive save/reload cycles, with 23,304 assertions in the expanded case.

The assertions cover geometry and instances, object material selection, physical
nozzle arrays, material identities/palettes, logical-material-to-tool maps, per-tool
purge matrices and multipliers, per-material purge pairs, and CCF settings. The
plastic/fiber fields use the Seeker profile's separate plastic/composite nozzle
schema, including shared-nozzle state and nondefault cut/restart values that
would reveal accidental normalization. CCF values are checked in both full
project config and embedded printer profiles. Embedded profile tuning is checked
after both generations, and private connection fields remain excluded.

No runtime defect was observed in this pass and no serializer/loader behavior
was changed. The changes add regression coverage and update the visible build
identity to `v2026.09.06-archive-checks.1`, package `2026.9.6.7`. Archive preservation
does not by itself prove the GUI's final effective configuration after project
selection, or prove that these synthetic fixtures are printable configurations.

The complete Mac build passed. Standard offline suites passed: native 289 cases /
261,599 assertions, FFF 48 / 870, offline utilities 20 / 211, SLA 21 / 13,478,
nesting 14 / 488. Total: 392 cases / 276,646 assertions. Release/FibreSeek checks,
the 936-profile manifest, and saved-profile checksums passed. Reference G-code
still differs only in two timestamp comments, with 167 layers and an estimate
of 3h 45m 38s. Logs are `/tmp/tinman-mixed-archive-*.log`; the slice is
`/tmp/tinman-mixed-archive-slice/plate_1.gcode`.

M7 remains staged, not installed, with publication queued after the active M6
matrix (`34016724153`). Consult current Git branch/CI state and PR #21 for later
publication updates rather than treating these timestamped checkpoint notes as
permanent queue state.

Further read-only audit confirmed the logout issue needs a deliberate design:
`GUI_App::request_user_logout` currently signs out before checking modified
profiles, ignores the confirmation result, and does not apply its postponed
keep-changes flag before replacing the library. The same entry point serves
manual logout, token expiry, and stealth-mode entry. Simply allowing Cancel to
block all sign-outs would also change forced-authentication/privacy behavior.
No logout code was changed overnight without testing those distinctions. A
future fix must separate authentication invalidation from preservation of the
open project's edits, handle failed saves, and test account switching and stale
callbacks alongside actual dialogs.

## Review Conclusions

The useful Prusa 3 ideas were explicit ownership and scope, private candidate
construction before publication, optional derived results, and normal inheritance
when an override is absent. Those principles were adapted into the existing
C++/wxWidgets system, not used as a reason to discard working CCF, IDEX, mixed
tools, printer integrations, or tuned profiles. The native overview describes
where global values came from; its documented scope is not a claim about every
object/plate/layer override. Incremental build identity changes now rebuild only
their actual consumers. No general slicing-speed percentage is claimed.

Remaining high-value work is deliberately explicit:

- Finish the interactive switching/import/save/close checks with the user present.
  Native tests and CLI output are not a substitute for the blocked GUI checks.
- Add real plate/object/volume/layer provenance and declaration ownership at the
  loader, avoiding a second resolver or guessed ancestry.
- Finish incremental cloud HTTP/cancellation integration checks, logout confirmation
  ordering, and whole-bundle commit boundaries. The branding-sync milestone covers
  cursor parsing/persistence/account binding, not every server or callback race.
- Audit filament-vector ownership before changing the dormant filament-option
  initialization path. Its option list mixes physical-tool and material concerns;
  enabling it blindly could damage mixed-tool profiles.
- Keep the pre-existing hidden sinking-object convex-hull test failure tracked
  separately. The standard native/FFF suites above are green; the complete hidden
  legacy test universe is not claimed green.

Private profile backups remain outside Git. The saved user-profile checksum
baseline remained unchanged through the final source checks. No live printer
connection, heater, motion, upload, or print command was used during this window.
