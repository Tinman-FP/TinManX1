# FibreSeek Layup Editor Contract

TinManX1's native planner already accepts `fiber_reinforcement_payload` JSON for layer/Z-specific continuous-fiber rules. The layup editor contract turns that expert JSON shape into a stable UI target.

## Scope

- The editor writes only the process setting `fiber_reinforcement_payload`.
- The payload root is `layup_bands`.
- Bands can enable or disable fiber by layer or Z range.
- Bands can override strength mode, generated-rib pattern, perimeter/infill intent, spacing, density, angles, route caps, priority, seam placement, and prime-line values.
- The raw JSON field should remain available as an expert escape hatch.

## Contract File

The public contract lives at:

```bash
checks/contracts/fiber_layup_editor_contract.json
```

It defines:

- built-in templates: `balanced`, `perimeter-shell`, `tetragrid-core`, and `first-layer-off-tetragrid`
- allowed band fields and types
- allowed prime-line fields and types
- choice values for strength, pattern, and fiber seam placement
- validation rules the UI should enforce before saving

## Validation

Run:

```bash
python3 scripts/source-helpers/validate_tinmanx1_fiber_layup_editor_contract.py
```

The validator checks the contract against `build_tinmanx1_fiber_layup_payload.py` and then sends each template plus one full-field payload through the native planner parser. This keeps the UI contract, payload helper, and planner parser aligned.

## First UI Increment

The first in-app editor should be small:

- template menu
- editable band table
- optional prime-line expander
- compact JSON preview
- apply button that writes `fiber_reinforcement_payload`

It should not emit machine commands, start prints, or bypass the existing planner, preview, summary, and G-code audit path.
