# PrusaSlicer 3.0 Evaluation and TinManX1 Adoption

Review date: 2026-09-05. Reference: `version_3.0.0-alpha11`, commit
`6f510128d7c2e543b62919b74bea7e876f564205`. TinMan baseline: `e280f7eac4`.

## Decision

Adopt the architectural separation, not the unfinished application wholesale.
Keep TinMan's working slicing engine, preset compatibility, network integrations,
CCF planner, wave overhangs, calibration, and existing project recovery while
introducing independently testable changes.

Prusa explicitly describes this release as unfinished and not feature complete.
Its third-party printer profiles and some existing workflows are not available
yet. That rules out replacing the TinMan application with this alpha while also
promising no loss of functionality. See the [official release notes](https://github.com/prusa3d/PrusaSlicer/releases/tag/version_3.0.0-alpha11).

## Source Findings

### Separate hardware from tuning

Prusa models printer hardware independently of material/process selection.
Tools have individual nozzle properties; feeder addresses describe topology
instead of assuming that every material slot is a physical extruder.
The profile model separates printer, print, tool-print, and material kinds.
This matches TinMan's real need for mixed U1 nozzles, IDEX, Bambu material lanes,
and the Seeker's distinct plastic/fiber tools.

Sources: [HwConfig.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Preset/HwConfig.hpp),
[Types.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Preset/Types.hpp).

TinMan already normalizes logical materials and physical tools separately in
`TinManMachineProfileContract` and `PresetBundle`. The weakness found here was
that printer identity, alias, nozzle capability, and tool-count tables were
maintained separately from the generator's family table. Changing one did not
guarantee that the other changed.

### Resolve values with their origins

Prusa uses conditional profile trees and an evaluation layer. Hardware features
can select applicable variants, and evaluated settings retain information about
where values originated. This can replace combinatorial duplication without
discarding explicit user overrides. Stable identifiers should be distinct from
display labels.

Sources: [PresetTree.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Preset/PresetTree.hpp),
[EvaluatedPreset.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Preset/EvaluatedPreset.hpp),
[PresetCollectionEvaluator.cpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-shared/src/Slic3r/Biz/Preset/PresetCollectionEvaluator.cpp).

TinMan must not replace the tuned material JSON files with generic values.
A future resolver must first produce identical effective configurations from
the existing inheritance tree. Only then should redundant storage be removed.
Per-setting provenance is not implemented by this release's overview dialog:
it shows resolved values and printer/process preset origin, not a complete
inheritance trace for every setting.

### Give each project and bed its own context

Prusa's project-scoped services and explicit bed domain reduce dependence on
global active-project state. This is the important prerequisite for reliable
tabbed projects and concurrent beds. Merely adding visible tabs to TinMan's
current singleton-oriented GUI would not provide that isolation.

Sources: [Project.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Project.hpp),
[Bed.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-domain/include/Slic3r/Domain/Bed.hpp),
[ProjectScoped.hpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-shared/include/Slic3r/Biz/ProjectScoped.hpp).

TinMan's `GUI_App`, `MainFrame`, `Plater`, `PresetBundle`, and device callbacks
still share active state. A multi-project migration needs explicit ownership,
job cancellation, and late-callback tests before enabling parallel project UI.

### Make configuration contextual and inspectable

Prusa's UI separates object contents from configuration. Material filtering,
favorites, and context-sensitive controls make settings easier to find.
Its UI implementation crosses domain, business, application, rendering, and
platform layers; copying the sidebar alone would omit those contracts.

Sources: [SidebarPrint.cpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-shared/src/Slic3r/App/SidebarPrint.cpp),
[MaterialSelectionDialog.cpp](https://github.com/prusa3d/PrusaSlicer/blob/version_3.0.0-alpha11/src/slic3r-shared/src/Slic3r/App/MaterialSelectionDialog.cpp).

TinMan retains its current editors and adds a read-only **Help > Profile
Overview**. It exposes printer/process origin, actual configured tool diameters,
material-to-tool mapping, temperatures, flow, PA, and key process settings from
the resolved preset bundle. Values are configured targets, not live telemetry.
Tool numbers in this dialog are one-based, matching `filament_map`.
Object/region overrides and final G-code are outside this bundle-level view.

## Implemented in Profile Foundation 1

- One checked-in hardware JSON catalog feeds the runtime and profile generator.
- CMake embeds that exact JSON into the binary and reconfigures when it changes.
- There is no handwritten fallback table and no startup dependence on the
  resource path having already been initialized.
- Parsing rejects unsupported schemas, malformed counts, ambiguous aliases,
  duplicate identities, and unknown capabilities/transports.
- The existing canonical names, nozzle variants, connection overlays, and
  mixed-tool normalization remain in place. New stable catalog IDs do not
  rename presets or migrate private connection keys.
- Profile Overview is a native, read-only modal; existing editors remain intact.
- Catalog verification now checks generated tool counts against runtime data.
- Native tests cover every curated family/nozzle and malformed catalog inputs.
- Release checks verify profile checksums and updated splash/about revision.
- Startup uses locally cached recent-project thumbnails. A sampled freeze in
  `FileHistory::LoadThumbnails` was blocked in `fopen` on a cloud-backed project.
  Startup no longer opens those archives merely to render the recent list.
  Explicit project opens/saves refresh a bounded, atomic local PNG cache;
  uncached entries retain their names and use a placeholder until opened.
  Thumbnail indices are bounds-checked and remain aligned when history reorders.

The catalog is build-time application policy, not a new user preset format or
a hot-reloaded machine-discovery database. Unknown user printers keep the
existing pass-through behavior. A physical printer reporting different hardware
still uses TinMan's existing synchronization paths.

## Next Phases and Acceptance Gates

1. **Configuration provenance:** build a read-only resolver report with values
   and origins across system, user, project, plate, object, and tool overrides.
   Require golden effective-config comparisons before replacing any loader.
2. **Transactional selection:** change printer, process, compatible materials,
   nozzle routing, and connection identity as one validated snapshot. A failure
   must leave the previous selection usable. Test rapid switching and late
   network callbacks without needing a connection-test button.
3. **Per-tool process editing:** expose nozzle-specific settings while explicitly
   resolving shared layer height and cross-tool constraints. Test U1 mixed
   diameters, both IDEX modes, and Seeker plastic/CCF with real project fixtures.
4. **Contextual UI:** introduce favorites and better material filtering against
   the proven resolver. Keep current advanced settings and import/export paths.
5. **Project isolation:** extract project-scoped services, then add tabbed
   projects and bed-level slicing jobs with memory/concurrency limits.

Each phase needs saved-project round trips, effective-config/G-code comparisons,
selection/restart checks, cancellation/shutdown tests, and measured performance.
No unmeasured slicing-speed improvement is claimed for the catalog refactor.

## Verification Record

- Complete Apple Silicon Release build, including the GUI and native tests.
- 75 focused native cases passed (994 assertions, including schema overflow
  coverage): catalog, presets, configuration, connection contracts, mixed tools,
  and the continuous-fiber planner.
- Thumbnail-cache test passed (6 assertions), including lookup while the
  original project does not exist, atomic replacement, and invalid/oversized data.
- Nozzle capability tests (5) and motion-envelope tests (9) passed.
- CCF helper smoke fixtures and golden comparison passed (8 golden fixtures,
  70 routes). Maintained-helper lint and release checks passed.
- All 936 tracked profile-resource checksums remained unchanged, including the
  installed resources. No tuning reset or profile regeneration was performed.
- Installed application cold-start and saved-project opening passed; the native
  Profile Overview displayed the preserved CORE One L nozzle and PC settings.
- A local saved-project CLI comparison against the pre-change application
  produced 96,323-line, 167-layer G-code with identical content except the two
  generation timestamp comments (both estimates: 3h 45m 38s). The CLI's default
  normative check rejects projects containing post-processing scripts; this
  comparison used `--normative-check=0` after inspecting the trusted local
  auto-PA hook. No project settings were changed and no print was sent.
- A broader run including 3MF geometry exposed one existing convex-hull test
  failure. The retained older native test binary reproduces the identical
  coordinates and assertion failure. It is not fixed by this profile/UI change;
  the full test suite is not claimed to be green.
- This is local Mac verification, not hardware print validation or a claim that
  all cross-platform CI and every printer connection have been exercised.

## Compatibility and Credit

No Prusa 3MF schema migration, YAML preset migration, GUI toolkit replacement,
or slicing algorithm transplant is included here. Those are separate changes
with substantially larger regression risk. Preserve the existing AGPL notices
and credit Prusa Research, PrusaSlicer, Slic3r, Bambu Studio, OrcaSlicer/SoftFever,
and the existing contributors. This tranche is an original implementation
informed by the inspected architecture, not copied Prusa UI/source code.
Requirements and product direction: William Tinney / Tinman-FP. Engineering,
research, implementation, and verification assistance: OpenAI Codex.
