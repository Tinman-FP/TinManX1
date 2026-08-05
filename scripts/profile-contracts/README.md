# TinManX1 Filament Reference Contracts

`bambu_studio_2.7.1_filament_contract.json` is a resolved snapshot of selected
material-behaviour fields from Bambu Studio `02.07.01.62`. It records an
explicit decision for every Codex material/manufacturer pair.

- `exact` entries may import the listed temperature, flow, plate, cooling and
  shrink settings.
- `analog` entries are comparison-only. TinManX1 preserves the manufacturer
  recipe because similar material names do not establish equivalent chemistry.
- X1C profiles use the high-flow value from Bambu's standard/high-flow vectors.
- H2D profiles preserve Bambu's complete vectors and use H2D chamber targets.
- Active chamber control is enabled only for machine families with active heat.
  X1C, Elegoo Centauri and Snapmaker U1 Codex profiles always keep it disabled.
- Field-validated PCTG, PET-CF and Fiberon PET-CF settings remain explicit
  TinManX1 overrides.

Regenerate and audit the snapshot with:

```bash
python3 scripts/source-helpers/audit_bambu_codex_filament_contracts.py \
  --write-contract scripts/profile-contracts/bambu_studio_2.7.1_filament_contract.json
```

Micro Swiss nozzle capability was checked against the official FlowTech CHT,
CM2 and printer-specific FlowTech product documentation. A nozzle rating is not
treated as permission to exceed a printer hotend or firmware temperature limit.

Sources:

- https://github.com/bambulab/BambuStudio
- https://store.micro-swiss.com/products/flowtech-cht-high-flow-nozzles
- https://store.micro-swiss.com/products/micro-swiss-cm2-nozzle-for-flowtech-hotend
- https://store.micro-swiss.com/products/flowtech-hotend-for-bambu-lab-x1-and-p1-printers
