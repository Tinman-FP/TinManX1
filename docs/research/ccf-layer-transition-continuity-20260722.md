# Continuous Fiber Layer-Transition Research - 2026-07-22

## Question

Can TinManX1 continue a continuous carbon fiber route through a layer change
without cutting the fiber, then restart deposition on the next layer?

## Short Answer

Yes, but not as a general-purpose travel move. It appears feasible only when the
layer change is itself a printable, polymer-supported, in-material fiber move.
For the FibreSeek style of 3-axis continuous-fiber printing, the practical form
is a short ramp, helix, or planned two-layer loop that keeps feeding matrix and
fiber while Z increases. A pure Z lift with live fiber feed, or a travel move
through air while the fiber remains connected, should be treated as invalid.

This would be new behavior relative to the Rocket and TinManX1 G-code inspected
so far. In the current propeller comparison:

| File | Fiber routes | Routes crossing more than one Z level |
| --- | ---: | ---: |
| Rocket Heavy/Fortified | 3047 | 0 |
| Rocket Medium/Reinforced | 1419 | 0 |
| TinManX1 Heavy | 1540 | 0 |
| TinManX1 Medium | 612 | 0 |

Rocket and TinManX1 currently close each fiber route on one layer, cut/release,
and start a new route for the next layer. A multi-layer route would be an
innovation path, not Rocket parity.

## External Evidence

### Commercial planar CFF/CFC systems

Markforged-style continuous fiber printing is commonly described as a
dual-nozzle process where normal thermoplastic creates the part and a second
nozzle lays/inlays continuous reinforcement. A Berkeley Markforged X7 protocol
notes that continuous fibers can be integrated on selected layers, but that
continuous fiber layers are printed only in the XY plane:

- https://me.berkeley.edu/wp-content/uploads/2025/05/Markforged-X7-Protocol-2024.pdf
- https://markforged.com/resources/learn/design-for-additive-manufacturing-plastics-composites/understanding-3d-printing-strength/3d-printing-carbon-fiber-and-other-composites

That supports the conservative assumption that common commercial systems do not
freely carry continuous fiber from one layer to another in normal slicing.

Anisoprint Aura exposes machine-level concepts that match our FibreSeek work:
cut distance, fiber restart length, cut G-code, Z-lift on restart, macrolayer
height, and solid plastic below fiber. Those settings assume fiber routes have
starts/cuts/restarts, and they reinforce the requirement that unsupported fiber
must have plastic beneath it:

- https://www.ddmlab.ru/wp-content/uploads/2019/02/Aura-User-Manual.pdf
- https://support.anisoprint.com/aura/settings-review/

### Multi-layer continuous fiber path research

The most directly relevant public work is the University of Calgary/CANCOM
paper "Developing a New Additive Manufacturing Toolpath Strategy for Continuous
Fibre Composites." It states that conventional layer-by-layer slicers force
fiber cuts after each layer and that this creates weak points. Their
multi-layer continuous fiber path (ML-CFP) strategy connects fiber across more
than one layer and places cut points strategically in low-stress regions.

Critical manufacturing lesson: they report that ideal zero-cut printing is
theoretically possible for their compression specimen, but in practice poor
fiber tensioning caused buildup and jamming after two successive loops. They
reduced the experiment to one two-layer connected route at a time, which still
reduced cuts from 36 to 9 for an 18-layer specimen.

- https://www.cacsma.ca/wp-content/uploads/2024/10/CANCOM_2022_paper_51.pdf
- https://ucalgary.scholaris.ca/items/97fa127e-f39d-4a18-b896-ebc8a2f324ee
- https://4spepublications.onlinelibrary.wiley.com/doi/10.1002/pc.29195

This is the strongest evidence that TinManX1 should prototype two-layer
continuous fiber linking before attempting full-part zero-cut routing.

### No-cutter/coaxial-nozzle evidence

Todoroki et al. describe a coaxial double-nozzle continuous-fiber printer that
did not include a fiber cutter. For unidirectional test specimens, the nozzle
was raised at the specimen end and the upper-layer path began without cutting
the fiber, connecting fibers through the stack at the ends.

- https://additive-manufacturing.or.jp/wp-content/uploads/2024/07/AAM_paper24001_En.pdf

That proves layer-to-layer no-cut movement can be printed physically, but their
geometry is simple and they trimmed the connected ends after printing. For a
finished part, TinManX1 needs to keep these transitions inside usable geometry
or in sacrificial features.

### Non-planar and multi-axis work

Several current research projects go further by using curved layers, spatial
toolpaths, or multi-axis robots. These strongly support the concept that fiber
orientation and continuity should be optimized in 3D, but most require hardware
abilities beyond the current 3-axis FibreSeek machine.

- Spatial printing with continuous fiber:
  https://arxiv.org/abs/2311.17265
- SpatialFiberPrinting dataset and waypoint format:
  https://github.com/GuoxinFang/SpatialFiberPrinting
- High-density spatial fiber toolpath generation:
  https://github.com/zhangty019/HighDensity_ToolpathGene4CFRTP
- Multi-layer continuous carbon fiber optimization:
  https://arxiv.org/abs/2404.11404
- Field-based CCF toolpath generation:
  https://arxiv.org/abs/2112.12057
- Learning-based toolpath planning with CCF examples:
  https://github.com/yuminghuang1995/RL3DPToolpathPlanner

The key lesson for TinManX1 is not "make everything non-planar now." The lesson
is that continuity, smoothness, bend radius, and load-path alignment matter more
than simply maximizing fiber grams.

### Other GitHub slicer references

ThenTech/CF-Slicer is a useful educational slicer reference for ordinary STL to
G-code mechanics, holes, infill, and visualization. It does not appear to be a
continuous-fiber route planner.

- https://github.com/ThenTech/CF-Slicer

## Practical Feasibility on FibreSeek

### What should be allowed

1. Ramped layer transition inside solid material.
   The composite nozzle keeps depositing plastic plus fiber while moving in XY
   and increasing Z by one layer height. This is the safest first prototype.

2. Two-layer connected loops.
   A route on layer N is joined to a route on layer N+1 through a ramped
   connector in a low-stress, solid region. This follows the Calgary ML-CFP
   lesson and limits tension buildup.

3. Helical/perimeter-style climbs for simple geometry.
   Tubes, bosses, rings, and some hole reinforcements may support a gentle
   helical climb with no cut.

4. Sacrificial tabs for research coupons.
   When the best transition location is outside the final part, add a removable
   tab and trim it later. This should not be used by default for production
   functional prints.

### What should not be allowed

1. No live-fiber pure Z lifts.
   A vertical move does not lay fiber into a supported bead and risks dragging,
   buckling, or creating an unbonded tow.

2. No live-fiber travel through air or across internal voids.
   The fiber would either bridge empty space, tear out, or create unusable
   geometry.

3. No arbitrary multi-layer chaining.
   The Calgary work found tension buildup and jamming after trying to continue
   too long. Start with two-layer links.

4. No default production enablement until machine testing.
   This should be an experimental planner mode with a hard fallback to
   layer-local cut/restart routes.

## Geometry Rules for a TinManX1 Prototype

Initial conservative rules:

- Link only adjacent fiber layers.
- Link only within a single connected island of solid material.
- Require the ramp swept volume to remain inside the part on both the source
  and target layers.
- Require plastic support below and carrier polymer during the ramp.
- Forbid links through holes, pockets, bridges, sparse infill voids, support
  regions, or air.
- Prefer low-stress or low-utility regions for the transition.
- Keep the transition away from outer show surfaces unless the user opts in.
- Use a ramp XY length of at least 5 mm for a 0.2 to 0.24 mm Z rise as a first
  safe setting. This is well above the geometric minimum implied by a 10 to 12
  mm bend-radius target and gives plastic time to wet/support the tow.
- Count the ramp length into the continuous route length and M1001 load.
- Do not emit M2800/M1002 between linked layers.

## G-code/Contract Questions to Test

The current Rocket/TinMan contract is route-based:

- `M1001 L...` starts a fiber route.
- Composite moves use X/Y plus U fiber feed and V/P matrix/feed tags.
- Cut/release commands occur before `M1002`.

A no-cut layer link would require one `M1001` block containing coordinated
X/Y/Z/U/V movement and delaying cutter/release until the final linked route
ends. Before enabling this on real prints, TinManX1 must prove:

1. FibreSeek firmware accepts Z movement inside an active `M1001` route.
2. U/V feed remains synchronized through a Z-changing move.
3. The cutter state remains stable if M2800 is delayed across a layer boundary.
4. Preview, summaries, and audits understand a route spanning more than one Z.
5. The machine does not lose fiber tension or create a buildup at the ramp.

## Recommended TinManX1 Roadmap

Phase 0: Synthetic dry-run G-code

- Generate a small 80 x 20 x 3 mm coupon.
- Print normal plastic base layers.
- Emit one composite route on layer N, ramp up at the end while feeding
  plastic plus fiber, print a second route on layer N+1, then cut once.
- Do the same coupon with normal cut/restart as a control.
- First run this through preview and contract audit only. Do not make it a
  default production profile.

Phase 1: Planner sidecar

- Add route-link candidate generation after normal route planning.
- Score route end points and next-layer start points by distance, stress/utility
  heuristic, hidden-surface preference, and ramp legality.
- Emit a sidecar explaining each accepted/rejected layer link.

Phase 2: Experimental setting

- Add an advanced setting: "Continuous fiber layer linking."
- Values: Off, Two-layer experimental, Helical/perimeter experimental.
- Default Off.

Phase 3: Real coupon test after machine arrival

- Compare:
  - cut every layer,
  - two-layer links,
  - three-layer links,
  - helical/perimeter climb.
- Inspect for jamming, fiber fray, bulges, delamination, and dimensional error.
- Tensile/flexural testing should compare cut count versus strength, not just
  fiber mass.

## Verdict

This is worth pursuing. The evidence says multi-layer continuous fiber paths are
possible and can improve part performance by reducing weak cut points. The same
evidence says full zero-cut routing is risky without tension control and can jam
the printhead.

For TinManX1, the right innovation is an experimental two-layer continuous fiber
linker: ramp the fiber from one layer to the next inside solid material, cut
only after the linked pair, and fall back automatically whenever the geometry or
machine contract is not clearly safe.
