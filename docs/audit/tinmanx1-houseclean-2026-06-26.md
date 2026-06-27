# TinManX1 Houseclean Audit - 2026-06-26

This note records the local validation performed before publishing the TinManX1 public package.

## Source Cleanup

- Startup splash now loads the same `TinManX1.png` artwork used by the login/register home screen.
- The stale external fiber planner bridge was removed from the G-code export path.
- TinManX1-facing labels replaced old pre-rebrand labels across helper scripts, summaries, logs, and patched UI surfaces.
- Generated cache files, conflict markers, and stale backup folders were checked and removed where present.

## Validation Commands

```bash
python3 -m py_compile resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py scripts/smoke_orcaslicer_codex_native_fiber_planner.py
python3 scripts/smoke_orcaslicer_codex_native_fiber_planner.py
bash scripts/smoke_orcaslicer_codex_arc_support_runtime.sh
bash scripts/smoke_orcaslicer_codex_strength_fiber_sidecars.sh
python3 scripts/smoke_orcaslicer_codex_wave_overhang_scaffold.py
ninja -C build/arm64 src/OrcaSlicer.app/Contents/MacOS/OrcaSlicer
```

The final installed app binary and bundled planner resource were hash-matched against the rebuilt source artifacts before packaging.
