# FibreSeek External Slicer Survey - 2026-07-21

This note records a clean-room review of two public slicer projects the user
identified as additional reference material for TinManX1's native FibreSeek
continuous-fiber planner. These projects are useful for architecture and
geometry-pipeline lessons, but neither was found to implement FibreSeek-style
continuous carbon fiber lifecycle behavior.

## Sources Reviewed

| Project | Reviewed commit | License observed | Observed scope |
| --- | --- | --- | --- |
| [fractalrobotics/Fractal-Cortex](https://github.com/fractalrobotics/Fractal-Cortex) | `d14de3212ac387bc0813bc4ceea5790ebe91e600` | GPL-3.0 | Multidirectional 5-axis FDM slicer |
| [ThenTech/CF-Slicer](https://github.com/ThenTech/CF-Slicer) | `9e80f8c924ab1c5e81a8f7216ffa67f2dc0aed28` | No license file found | Educational computational-fabrication FDM slicer |

Local clean-room clones were placed in:

`work/external-ccf-slicer-research-20260721`

## Fractal-Cortex Findings

Fractal-Cortex is the more useful architecture reference. Its README describes
it as a multidirectional 5-axis FDM slicer, not a continuous-fiber slicer. The
algorithm is implemented mainly in `fractal-cortex/slicing_functions.py`.

Useful observed patterns:

- 3-axis slicing uses `trimesh.section_multiplane` with a normal build-plate
  direction.
- 5-axis slicing uses the same sectioning concept with arbitrary slice-plane
  normals and user-defined slice-plane starts.
- The model is split into chunk volumes with `mesh.slice_plane(..., cap=True)`.
  Later chunks are subtracted from earlier chunks so the print order avoids
  in-process part collision.
- Each non-Z chunk is transformed into a local XY slicing frame, sliced and
  filled there, then transformed back into printer coordinates for preview and
  G-code.
- The geometry pipeline uses Shapely polygon offsets for shell generation and
  repeated `make_valid` / small-buffer repair when polygon unions or
  differences fail.
- Surface/solid regions are detected by comparing adjacent layer areas, then
  exposed top and bottom regions are thickened by the requested shell count.
- Solid infill uses alternating +45 / -45 degree hatch families. Sparse
  triangular infill uses 0 / 60 / 120 degree families.
- Infill is clipped to valid area, short fragments are filtered, and paths are
  ordered with a nearest-neighbor pass seeded from the final shell endpoint.
- Expensive independent steps are parallelized per layer with
  `ProcessPoolExecutor`; layer-overlap classification stays serial because it
  depends on adjacent layers.
- Preview geometry and G-code consume the same shell/infill path collections.
  That is a strong guardrail for avoiding preview/G-code drift.

TinManX1 implications:

- Keep a native route object as the single source of truth for planner,
  preview, summary, and G-code. This directly supports the regressions we have
  already fought where the summary showed fiber but preview or G-code did not.
- Preserve per-path role metadata through every transform. A route should keep
  layer, island, tool, fiber/plastic role, strength band, accepted/rejected
  state, fallback reason, and lifecycle phase.
- Make geometry repair staged and diagnostic. Fractal-Cortex's "try normal,
  repair, then conservatively skip" pattern is safer than silently producing
  ghost paths.
- Parallelize route candidate generation and geometry clipping only after the
  correctness model is stable. Per-layer and per-island work are the natural
  parallel boundaries.
- The chunk/transform model is a useful future reference if TinManX1 ever adds
  non-planar or directional composite placement. It is not directly applicable
  to the current FibreSeek 3 hardware, which remains planar CFC plus plastic.

## CF-Slicer Findings

Despite the name, CF-Slicer appears to mean "Computational Fabrication" slicer,
not carbon-fiber slicer. Its README credits Group 3, Lieven Libberecht and
William Thenaers. It is a C# WPF slicer that outputs basic FDM G-code.

Useful observed patterns:

- The main pipeline slices the model, erodes contours by nozzle radius, detects
  floors and roofs by comparing adjacent layers, propagates roof/floor
  thickness, adds shells, clips dense and sparse infill, adds support infill,
  then sorts paths.
- `Polygon2D` carries explicit role flags such as contour, hole, shell, infill,
  surface, floor, roof, support, adhesion, and open/fixed geometry.
- Clipper is used for offsets, intersections, differences, unions, and polygon
  cleanup.
- Infill is generated as global line/polygon patterns, clipped against the
  current inner shell, cleaned, short-filtered, and ordered by closest next
  endpoint.
- Supports optionally stitch zigzag lines together, but the code rejects a
  connector if it crosses non-support geometry.
- The G-code writer emits contours before fill, computes extrusion by volume
  conservation, and has commented-out arc emission because firmware arc support
  was not enabled.
- The README calls out known failure modes: missing points/triangles, wrong
  contour/hole classification, disappearing supports, stringing, removed
  overlapping shells, and phantom surfaces.

TinManX1 implications:

- The role flags are the important lesson. TinManX1 CFC paths must not be
  "just polylines"; they need typed ownership so preview colors, summary mass,
  and writer behavior cannot drift apart.
- Connector legality should be geometry-tested, not guessed by distance alone.
  This aligns with the Rocket/Aura evidence that legal CFC transitions are
  graph edges with explicit endpoint state.
- Short filtering is fine for plastic infill, but it is not enough for CFC.
  TinManX1 should keep its Rocket-style short-candidate recovery and plastic
  fallback behavior rather than simply discarding short fiber geometry.
- Nearest-neighbor ordering is useful as a fallback or route seed, but it is not
  a sufficient CFC planner. FibreSeek needs endpoint-stateful graph selection,
  cut-safe route length checks, restart/cut/tail phases, bend/risk metadata, and
  plastic substitution for rejected candidates.

## What Not To Reuse

- Neither project showed FibreSeek-style continuous-fiber commands, co-extruded
  plastic/fiber lifecycle phases, cut distance handling, restart length, finish
  ironing tail geometry, or composite route substitution semantics.
- Fractal-Cortex is GPL-3.0. CF-Slicer has no license file in the reviewed repo.
  Do not copy source code from either into TinManX1 unless licensing is
  deliberately revisited.
- CF-Slicer is an educational slicer and documents several unresolved geometry
  issues. It should be treated as a conceptual comparison, not as a production
  behavior oracle.

## Actionable Planner Lessons

1. Route object first: one native CFC route model must feed planning, preview,
   summary, diagnostics, and G-code.
2. Keep metadata alive: every candidate and route should carry role, family,
   tool, layer, island, endpoint state, accepted/rejected state, and reason.
3. Geometry repair should be explicit: normal operation, repaired operation,
   fallback/skip, and logged reason.
4. Candidate generation can be parallel by layer/island once the route model is
   stable.
5. Nearest-neighbor path sorting is not enough for CFC. TinManX1 should keep
   moving toward the Rocket-style endpoint-state graph and combination selector.
6. CFC short segments must be recovered or substituted with plastic fallback;
   they should not silently disappear.
7. Preview parity is non-negotiable: if G-code will emit a fiber path, the same
   route object must be visible and counted in the UI.
8. Rocket/Aura remains the primary hardware-contract reference for FibreSeek
   lifecycle commands. These two external slicers are supporting references for
   geometry discipline and planner architecture.
