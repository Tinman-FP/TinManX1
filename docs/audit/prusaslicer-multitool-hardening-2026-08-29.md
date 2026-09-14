# PrusaSlicer Multi-Tool Architecture Audit

## Scope

This audit compared TinManX1 with the official PrusaSlicer 2.9.6 source at tag
`version_2.9.6` (`b028299c770b8380ee81c921a2867d522f288123`). The primary references were:

- `src/libslic3r/Preset.cpp`
- `src/libslic3r/PresetBundle.cpp`
- `src/libslic3r/PrintApply.cpp`
- `src/libslic3r/GCode/ToolOrdering.cpp`

The review focused on physical printer identity, multi-tool printer presets,
per-tool vector sizing, filament selection, and the configuration boundary used
by slicing and tool ordering.

## Useful PrusaSlicer Patterns

PrusaSlicer consistently derives physical extruder count from
`nozzle_diameter.size()` and resizes per-extruder settings as one operation. It
also validates selected material presets before constructing a print config,
resolves renamed machine presets held by physical printers, stores physical
printers in stable collection storage, and filters tool-dependent state against
the current physical count at the `Print::apply` boundary.

These are reliability patterns, not feature code. TinManX1 now applies the same
principles at its own ownership boundaries.

## Required TinManX1 Difference

PrusaSlicer's material selection is primarily organized per physical extruder.
Orca/TinMan additionally supports AMS/CFS-style logical material slots mapped to
physical tools through `filament_map`. Therefore, directly resizing all material
vectors to `nozzle_diameter.size()` would break valid configurations.

TinManX1 must preserve three separate dimensions:

1. Physical tools: `nozzle_diameter`, `nozzle_volume_type`, per-tool flush data,
   and per-tool AMS routing metadata.
2. Logical materials: selected filament presets and all aggregated filament
   options.
3. Routing: a one-based `filament_map` entry for each logical material, with
   every entry inside the current physical-tool range.

For example, a Snapmaker U1 may expose four physical tools while a project uses
only three logical materials. Both vector lengths are correct and must not be
forced to match.

## TinManX1 Changes

- `tinmanx_normalize_multitool_config` enforces the three-dimensional contract
  without conflating tools and materials.
- `PresetBundle` resolves unavailable or renamed filament presets before full
  configuration projection and emits canonical `filament_settings_id` values.
- `Print::apply` repeats the normalization at the final slicing boundary so an
  imported 3MF or direct API caller cannot bypass the contract.
- Mixed-nozzle bridge percentages are validated against the smallest eligible
  nozzle; runtime validation still checks each region's routed physical tool.
- Physical-printer loading and selection now use exact identities, migrate
  renamed machine bindings, preserve selection across sorted inserts, and reject
  empty or entirely stale preset sets.
- Physical-printer deletion no longer removes the next alphabetic printer when
  an exact name is absent, and index adjustment preserves a different selected
  printer.

## Regression Contract

Native tests cover:

- four mixed nozzles with fewer logical materials;
- invalid zero, negative, and out-of-range tool routes;
- missing saved filament profiles during full FFF projection;
- empty and stale physical-printer bindings;
- fallback from an unavailable requested machine preset;
- case-insensitive physical-printer reload without duplicate identities;
- sorted insertion and selection preservation; and
- exact-name deletion behavior.

Profile verification remains responsible for validating bundled machine and
filament catalogs. Runtime normalization is a recovery boundary, not a reason to
ship malformed profiles.

## Future Review Rules

- Never use filament count as physical tool count or the reverse.
- Normalize before any code indexes `filament_map` or a per-tool vector.
- Persist printer selection by canonical name, not collection index.
- Resolve rename metadata before declaring a saved binding stale.
- Add one mixed-nozzle and one stale-preset regression whenever changing preset
  projection, tool ordering, or physical-printer storage.

## Attribution

Architecture reference: Prusa Research and PrusaSlicer contributors under the
project's AGPL licensing terms. TinManX1 adaptation, integration, and regression
work was developed for William Tinney's multi-printer and mixed-tool workflows
with OpenAI Codex engineering assistance.
