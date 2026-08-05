# FibreSeek Rocket to TinManX1 Settings Gap Analysis

This pass compares the user-changeable Rocket Slicer printer, extruder, plastic,
composite, and process/profile settings against the current TinManX1 profile and
option surface. It is intended as a product checklist, not a source copy. Rocket
wording, images, private IDs, and proprietary assets should not be copied into
public TinManX1 releases.

## Sources Reviewed

- Rocket local backend database and UI bundle setting catalogs, reviewed only as
  local behavioral evidence. Rocket assets, private IDs, and proprietary UI text
  are not copied into TinManX1.
- TinManX1 presets:
  `resources/profiles/TinManX1`
- TinManX1 option definitions and UI placement:
  `src/libslic3r/PrintConfig.cpp`, `src/libslic3r/PrintConfig.hpp`,
  `src/slic3r/GUI/Tab.cpp`, and `src/slic3r/GUI/PresetComboBoxes.cpp`

Rocket's local DB currently ships a narrow baseline: one plastic material
(`PETG`), one composite material (`X-CCF / PETG`), one plastic extruder
(`FFF - 0.4 mm`), one composite extruder (`CFC`), and one process profile
(`PETG + X-CCF / PETG`). Its UI, however, exposes a much larger user-changeable
surface:

- Printer editor: 43 printer fields, plus slot/extruder editors.
- Plastic extruder editor: 8 fields.
- Composite extruder editor: 12 fields.
- Plastic material editor: 38 fields.
- Composite material editor: 44 fields.
- Process/profile editor: 178 fields, including detailed reinforced-entity,
  reinforced-perimeter, and reinforced-infill controls.

TinManX1 currently has 8 FibreSeek machine profiles, 78 filament profiles
(including the generated CFC matrix/fiber combinations), and 13 process profiles.
The core #2 CFC lane is present, but Rocket still exposes several settings that
TinManX1 either fixes internally, inherits indirectly, or does not yet present to
the user.

## Must Have

1. Keep machine, plastic, CFC material, and process as separate concepts.

   TinManX1 should keep the plastic-only and plastic+fiber sections separate.
   Slot #1 should remain plastic-only, and slot #2 should remain CFC-only for
   FibreSeek. The CFC material selected in slot #2 needs to represent both the
   plastic matrix and the continuous fiber, for example `CFC PETG + X-CCF` or
   `CFC ABS-CF + CKF`.

   Current TinManX1 status: mostly present. The CFC profile matrix and slot #2
   filtering exist. This needs regression tests because it has already regressed
   several times.

2. Add a complete FibreSeek machine/extruder contract.

   Rocket separates printer-wide settings from plastic extruder and composite
   extruder settings. TinManX1 needs the same effective data, even if the normal
   UI keeps the dangerous fields in an advanced area.

   Must-have fields: build volume, home positions, XY/Z travel speeds, heated
   bed/chamber flags and heat-up rates, acceleration/jerk/machine limit fields
   used for time estimates, relative extrusion mode, start/end G-code, before
   and after toolchange G-code, plastic extruder XYZ offsets, plastic nozzle
   diameter, plastic heat-up speed, plastic fan presence/index, CFC extruder XYZ
   offsets, CFC nozzle diameter, CFC heat-up speed, CFC fan presence/index, cut
   distance, restart length, cut G-code, contact radius, and extended contact
   radius.

   Current TinManX1 status: nozzle diameters, CFC cut/restart/cut G-code,
   contact radii, toolchange G-code, machine speeds, and acceleration limits are
   present. Missing or flattened areas include extruder heat-up speeds, fan
   indices, explicit CFC/plastic extruder offsets, chamber/table heat-up rates,
   jerk/block-buffer style time-estimation values, and clearer advanced-machine
   grouping.

3. Expand CFC filament profiles into true composite material profiles.

   Rocket's composite material is not just "fiber metadata". It includes fiber
   identity plus the plastic matrix and the composite-lane plastic behavior.

   Must-have fields: fiber name, fiber type, fiber manufacturer, fiber diameter,
   linear density, fiber spool length/cost, plastic matrix name/type/manufacturer,
   plastic diameter, composite plastic flow multiplier, print/preheat/standby
   temperature, first-layer temperature, bed/chamber/first-layer bed temperature,
   print cooling, fan speeds, travel and toolchange retraction, retract speed,
   plastic unretract/extrusion speed, fiber extrusion speed, restart Z-hop,
   restart pause, finish ironing distance, priming line height, plastic density,
   plastic spool cost, and plastic spool weight.

   Current TinManX1 status: CFC profiles exist for the requested matrix/fiber
   combinations and include fiber name/type/diameter/linear density/spool/cost,
   finish ironing distance, priming height, flow ratio, temperatures, fan speeds,
   retraction speed/length, and inherited plastic base data. Missing or weakly
   represented areas include explicit matrix name/manufacturer on the CFC lane,
   plastic diameter/density/cost/spool weight on the CFC lane itself, preheat and
   standby temperature controls, first-layer temp/bed overrides for the composite
   lane, fiber extrusion speed, and restart pause.

4. Preserve all G-code-critical fiber process controls.

   Rocket exposes several reinforced-entity controls that directly affect route
   legality, route timing, or emitted fiber/plastic extrusion.

   Must-have fields: enable fiber, fiber perimeters, fiber infill, start layer
   with matching top shutoff, print order, fiber line width, fiber macro/layer
   spacing, layer step, minimum route length, perimeter minimum length, hardware
   minimum route length, perimeter/infill insets, minimum bend radius as a
   quality/speed target, max arc segment length, route speed controls, start
   length, slow length, tension length/feedrate, tension release, after-cut
   plastic multiplier, Z-hop after cut, routes per cut, max routes per layer,
   correction-move speed/feedrate controls, fiber feedrate percentage, reinforced
   perimeter loop controls, and reinforced infill pattern controls.

   Current TinManX1 status: most of the simplified controls exist in the Fiber
   Settings process block, and the planner now treats bend radius as a selectable
   quality target instead of a hard impossibility gate. Missing or simplified
   areas include Rocket-style start/normal/finish speed phases, correction move
   speed and fiber feedrate, tension release fraction, explicit fiber feedrate
   percentage, separate fiber first-layer controls, and plastic-loop counts
   inside/outside the fiber perimeter.

5. Keep preview, summary, and audit visibility as first-class requirements.

   If TinManX1 emits CFC moves, the preview must show them, the slice summary
   must report them, and the audit script must flag missing or suspicious fiber
   contracts. This should include warnings for wrong slot #2 material type,
   missing CFC profile, missing cut command, route candidates skipped by hardware
   minimum length, and route candidates below the selected bend-radius quality
   target.

   Current TinManX1 status: fiber preview, CFC grams, and G-code contract audits
   exist, but these need to be part of automated release checks to prevent
   regressions.

6. Rewrite explanations for TinManX1 instead of copying Rocket text.

   Rocket's explanations are useful because they identify intent: manufacturer
   values, quality controls, time-estimation values, and route-planning values.
   TinManX1 should provide its own concise tooltips for every user-facing field.
   For bend radius, the tooltip should say it is a selected quality/speed target,
   not a hard physical limit.

## Nice To Have

1. Layup rules and masks.

   Rocket has per-height layup rules and mask workflows with priorities. TinManX1
   already has start-layer control and alternating CFC paths, so this is not
   required for the current FibreSeek workflow. A later TinManX1-native version
   could use Z bands and masks for local reinforcement intent.

   Current TinManX1 status: partial. The visible Fiber Settings page now keeps
   advanced band data in one expert `fiber_reinforcement_payload` JSON field
   instead of many separate band controls. The native planner accepts
   `layup_bands`, `z_bands`, or `bands` entries that can enable or disable fiber
   by layer/Z range and override mode, perimeter/infill intent, pattern, spacing,
   route counts, priority, and optional prime-line data. A richer mask editor can
   be built on top after machine testing.

2. Full reinforced infill pattern library.

   Rocket exposes solid, rhombic grid, isogrid, anisogrid, and tetragrid, with
   density, guide angle, rib angle, rib placement, side angle, and angle-list
   controls. TinManX1 can keep the current streamlined light/medium/heavy layer
   planner now, then add advanced pattern controls once the CFC contract is
   stable.

   Current TinManX1 status: present for the streamlined planner. The UI exposes
   Solid, Rhombic, Isogrid, Anisogrid, and Tetragrid. The native generated-rib
   planner now gives each named pattern a distinct angle family: Solid alternates
   single-family layers, Rhombic uses diamond ribs, Isogrid uses 60-degree ribs,
   Anisogrid is load-biased, and Tetragrid uses four families. The Fiber Settings
   page also exposes generated-rib density and an optional comma-separated angle
   list for custom layups.

3. Separate seam start/distribution controls for plastic and fiber.

   Rocket has separate plastic and fiber seam start/distribution controls. These
   are useful for surface quality and repeatability, but they are not required to
   generate valid FibreSeek G-code.

   Current TinManX1 status: present for fiber routes. Plastic seam controls
   remain Orca/TinManX1 native, and Fiber Settings now adds fiber-only seam
   placement with Source, Nearest, Aligned, Rear, and Random plus an aligned
   angle. Source is default so current output is unchanged unless the user opts
   in.

4. Macro/micro-layer modeling.

   Rocket's profile system models macrolayer height and separate heights for
   external shell, plastic perimeters, infill, support, and fiber. TinManX1 can
   continue using Orca-style layer controls unless testing shows FibreSeek needs
   the full macro/micro model for accurate time or toolpath comparison.

5. Profile diff/import tooling.

   A neutral "Rocket baseline comparison" report would be useful for internal
   validation. It should summarize settings and generated G-code contracts without
   importing Rocket assets, private IDs, or proprietary UI text into public
   releases.

   Current TinManX1 status: present for G-code comparisons. The public
   `scripts/source-helpers/compare_fiberseek_gcode.py` tool compares a local Rocket G-code file
   against a TinManX1 G-code file for critical command families, setpoints, tool
   ownership, cut/load behavior, route metadata, timing, and material summaries.
   It also runs the TinManX1 contract audit by default and keeps Rocket exports
   outside the repo.

6. Automatic bend-radius helper.

   Once the physical machine is available, TinManX1 should offer a helper that
   recommends bend radius from fiber type, speed, temperature, and coupon results.
   Until then, bend radius should remain user selectable.

7. Advanced brim, skirt, support, overhang, and wipe-tower parity.

   Rocket exposes detailed variants of these controls. Orca/TinManX1 already has
   strong equivalents for most plastic-only behavior. Add parity only where a
   FibreSeek apples-to-apples G-code comparison proves a missing command,
   collision behavior, or print-time discrepancy.

## Do Not Need

1. Rocket cloud, account, company, user, project, log, and telemetry fields.

   These do not belong in TinManX1's public profile model.

2. Rocket branding and mode names.

   Do not reuse Rocket-specific names such as Speedy, Reinforced, or Fortify.
   TinManX1 should keep Light, Medium, and Heavy.

3. Rocket proprietary images, animations, UI strings, and database assets.

   Use Rocket only as local behavioral evidence. Public TinManX1 releases should
   keep attribution and clean-room-style summaries, not bundled Rocket assets.

4. Rocket's duplicate `Over` override columns.

   Rocket stores a visible value plus an override value for many DB fields.
   TinManX1 can use Orca's preset inheritance, dirty-option tracking, and system
   preset model instead.

5. Manufacturer-only values in the normal beginner UI.

   Cut distance, cut G-code, contact radius, heat-up speed, fan index, and
   extruder offsets are must-have data, but they should be advanced/profile
   fields. They should not be casual front-page tuning controls.

6. Generic Rocket admin/import/export workflow.

   TinManX1 needs reliable local profiles, release packaging, and optional clean
   profile import/export. It does not need Rocket's account-tied project and
   profile management model.

## Recommended Next Implementation Order

1. Add a FibreSeek Advanced Machine Contract section and profiles for the missing
   machine/extruder fields: heat-up speeds, fan indices, offsets, chamber/table
   heat-up rates, and timing/kinematic metadata.
2. Expand CFC filament profiles so slot #2 can fully represent both matrix and
   fiber behavior without relying on hidden inheritance for critical values.
3. Add the missing G-code-critical process controls: speed phases or an
   equivalent compact model, correction moves, fiber feedrate percentage, tension
   release, fiber first-layer controls, and fiber/plastic perimeter loop counts.
4. Add a profile lint/release check that validates FibreSeek profiles, slot #2
   CFC filtering, required machine contract fields, and visible fiber output.
5. After the above is stable, add nice-to-have layup/mask/pattern/seam features
   based on physical machine testing and saved Rocket/TinManX1 G-code diffs.
