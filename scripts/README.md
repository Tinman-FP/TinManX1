# Scripts

Top-level scripts:

- `collect_baseline_manifest.py` records a local installed-app manifest. Review output before committing because local runs may include private paths or machine details.
- `verify_orcaslicer_codex.py` validates an installed TinManX1 app on a local machine.
- `install_orcaslicer_codex_app.py` supports local app installation workflows.

`source-helpers/` contains helper scripts that are also present in the source patches:

- Arc Support transform and in-place adapter helpers
- Strength Lens sidecar
- Fibre metadata sidecar
- Native FibreSeek planner, contract audit, Rocket/TinManX1 comparison helper, wiring check, and smoke guard
- Wave, Arc, and Strength/Fibre smoke guards

Public scripts default away from real printer hosts where possible. Pass explicit host details only in a private local environment.
