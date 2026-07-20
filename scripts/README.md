# Scripts

Top-level scripts:

- `collect_baseline_manifest.py` records a local installed-app manifest. Review output before committing because local runs may include private paths or machine details.
- `verify_orcaslicer_codex.py` validates an installed TinManX1 app on a local machine.
- `install_orcaslicer_codex_app.py` supports local app installation workflows.

`source-helpers/` contains helper scripts that are also present in the source patches:

- Arc Support transform and in-place adapter helpers
- Strength Lens sidecar
- Fibre metadata sidecar
- Native FibreSeek planner, profile generator/lint helpers, contract audit, Rocket/TinManX1 comparison helper, wiring check, and smoke guard
- Native FibreSeek golden fixture comparison for deterministic planner regression checks
- Native FibreSeek layup payload builder for generating validated advanced `fiber_reinforcement_payload` JSON and optional generated-profile layup defaults
- Native FibreSeek layup editor contract validator for future UI work
- Wave, Arc, and Strength/Fibre smoke guards
- Local-only TinManX1 Bambu network plug-in installer. It copies plug-in binaries from an existing local BambuStudio/OrcaSlicer install into the TinManX1 data directory and updates `OrcaSlicer.conf`; native networking binaries remain excluded from the repository.
- Local-only TinManX1 Bambu LAN binding repair helper. It matches local printer TLS certificate CNs to saved Bambu serial numbers and updates stale `local_machines` IPs without reading or printing access codes.

Public scripts default away from real printer hosts where possible. Pass explicit host details only in a private local environment.
