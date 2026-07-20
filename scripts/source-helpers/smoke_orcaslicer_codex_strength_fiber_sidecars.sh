#!/usr/bin/env bash
set -euo pipefail
unset PYTHONHOME
unset PYTHONPATH
unset PYTHONEXECUTABLE

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/TinManX1-strength-fiber.XXXXXX")"
trap 'rm -rf "$tmp_dir"' EXIT

config_json="$tmp_dir/config.json"
slice_result="$tmp_dir/slice-result.json"
fiber_overlay="$tmp_dir/fiber-overlay.json"
strength_overlay="$tmp_dir/strength-overlay.json"

python3 - "$config_json" "$slice_result" <<'PY'
import json
import pathlib
import sys

config_path = pathlib.Path(sys.argv[1])
slice_path = pathlib.Path(sys.argv[2])

config = {
    "fiber_enabled": True,
    "fiber_shared_nozzle": False,
    "fiber_slot_roles": "polymer;composite;fiber_drive",
    "filament_type": ["PLA", "PETG-CF", "continuous_carbon"],
    "filament_settings_id": ["PLA Basic", "PETG-CF", "Codex Continuous Carbon"],
    "filament_colour": ["#eeeeee", "#222222", "#111111"],
    "nozzle_diameter": [0.4, 0.4, 0.35],
    "composite_enabled": [False, True, True],
    "fiber_name": ["", "", "Codex Continuous Carbon"],
    "fiber_type": ["", "", "continuous_carbon"],
    "fiber_diameter": [0.0, 0.0, 0.35],
    "fiber_material_kind": ["polymer", "composite", "continuous_fiber"],
    "fiber_source_material_id": ["pla-basic", "petg-cf", "codex-ccf"],
}

slice_result = {
    "slice_result_schema_version": "1.0.0",
    "filament_settings_id": ["PETG-CF", "Codex Continuous Carbon"],
    "material_strength": {
        "primary_material_id": "PETG-CF",
        "print_axis_tensile_strength_mpa": {"xy": 58, "z": 31},
        "estimated": True,
    },
}

config_path.write_text(json.dumps(config, indent=2, sort_keys=True), encoding="utf-8")
slice_path.write_text(json.dumps(slice_result, indent=2, sort_keys=True), encoding="utf-8")
PY

"$repo_root/scripts/orcaslicer_codex_fiber_metadata_sidecar.py" \
  --config-json "$config_json" \
  --out "$fiber_overlay" \
  --force-fallback

"$repo_root/scripts/orcaslicer_codex_strength_lens_sidecar.py" \
  --slice-result "$slice_result" \
  --fiber-preview-overlay "$fiber_overlay" \
  --out "$strength_overlay" \
  --load-case bending \
  --force-fallback

python3 - "$fiber_overlay" "$strength_overlay" <<'PY'
import json
import pathlib
import sys

fiber = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
strength = json.loads(pathlib.Path(sys.argv[2]).read_text(encoding="utf-8"))

fiber_contract = fiber.get("contract", {})
fiber_summary = fiber.get("summary", {})
if fiber_contract.get("id") != "orcaslicer_codex_fiber_metadata_sidecar":
    raise SystemExit("FibreSeek sidecar contract id mismatch")
if fiber.get("command_emission_allowed") is not False or fiber.get("live_machine_side_effects") is not False:
    raise SystemExit("FibreSeek sidecar must not allow command emission or live side effects")
if fiber.get("upload_or_start_print_allowed") is not False:
    raise SystemExit("FibreSeek sidecar must not allow upload/start print")
if fiber_summary.get("continuous_fiber_lane_count") != 1:
    raise SystemExit("FibreSeek sidecar should report one continuous-fiber lane")
if "no_live_machine_commands" not in fiber.get("guardrails", []):
    raise SystemExit("FibreSeek sidecar missing no-live-machine guardrail")
if fiber_summary.get("validation_blocked_gate_count", 0) <= 0:
    raise SystemExit("FibreSeek sidecar should keep hardware validation gates blocked")

strength_contract = strength.get("contract", {})
strength_summary = strength.get("summary", {})
viewport = strength.get("viewport_render_plan", {})
if strength_contract.get("id") != "orcaslicer_codex_strength_lens_sidecar":
    raise SystemExit("Strength Lens sidecar contract id mismatch")
if strength.get("advisory_only") is not True or strength_contract.get("slicing_or_gcode_modified") is not False:
    raise SystemExit("Strength Lens must be advisory-only and non-mutating")
if viewport.get("active_lens") != "orientation_risk":
    raise SystemExit("Strength Lens viewport should default to orientation risk")
if viewport.get("load_case_kind") != "bending":
    raise SystemExit("Strength Lens viewport should preserve the selected bending load case")
if viewport.get("continuous_fiber_lane_count") != 1:
    raise SystemExit("Strength Lens should carry FibreSeek continuous-fiber lane count")
if viewport.get("print_approval") is not False or viewport.get("machine_ready_structural_approval") is not False:
    raise SystemExit("Strength Lens must not approve prints or structural readiness")
if strength_summary.get("advisory_only") is not True:
    raise SystemExit("Strength Lens summary missing advisory-only state")
PY

python3 - "$repo_root" <<'PY'
import pathlib
import sys

repo_root = pathlib.Path(sys.argv[1])
checks = {
    "scripts/orcaslicer_codex_strength_lens_sidecar.py": [
        "orcaslicer_codex_strength_lens_sidecar",
        "ORCASLICER_CODEX_STRENGTH_LENS_BUILDER",
        "advisory_only",
    ],
    "scripts/orcaslicer_codex_fiber_metadata_sidecar.py": [
        "orcaslicer_codex_fiber_metadata_sidecar",
        "ORCASLICER_CODEX_FIBER_PREVIEW_BUILDER",
        "no_live_machine_commands",
    ],
    "src/libslic3r/PrintConfig.cpp": [
        "strength_lens_enabled",
        "fiber_enabled",
        "fiber_reinforcement_payload",
    ],
    "src/slic3r/GUI/GUI_Factories.cpp": [
        "strength_lens_enabled",
        "fiber_reinforcement_mode",
    ],
}
for relative, needles in checks.items():
    text = (repo_root / relative).read_text(encoding="utf-8", errors="replace")
    for needle in needles:
        if needle not in text:
            raise SystemExit(f"{relative} missing {needle}")
PY

echo "TinManX1 Strength/Fibre sidecar smoke passed"
