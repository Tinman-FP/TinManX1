#!/usr/bin/env python3
"""Validate TinManX1 FibreSeek profile-pack invariants.

This is a regression gate for the settings we derived from the Rocket
comparison work. It intentionally checks behavior-facing fields instead of
only confirming that JSON files exist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())
PROFILE_ROOT = ROOT / "resources" / "profiles" / "TinManX1"
INDEX_PATH = ROOT / "resources" / "profiles" / "TinManX1.json"

MATERIALS = {
    "ABS",
    "ASA",
    "PPA-CF",
    "PPS-CF",
    "ABS-CF",
    "ABS-GF",
    "ASA-GF",
    "PP",
    "PCTG",
    "PCTG-CF",
    "Push Plastic PC-PBT",
    "PA-CF",
    "PETG",
    "PET GF",
}
FIBERS = {
    "X-CCF": {"diameter": 0.25, "linear_density": 102},
    "CGF": {"diameter": 0.35, "linear_density": 170},
    "CKF": {"diameter": 0.25, "linear_density": 72},
    "CBF": {"diameter": 0.25, "linear_density": 95},
}
PROCESS_MODES = {"Light": "light", "Medium": "medium", "Heavy": "heavy"}
PLASTIC_NOZZLES = {"0.4", "0.6", "0.8"}
COMPOSITE_NOZZLE = "0.7"


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        fail(f"missing file: {path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path.relative_to(ROOT)}: {exc}")
    raise AssertionError("unreachable")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scalar_value(value: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else None
    return value


def require_key(data: dict[str, Any], key: str, path: Path) -> Any:
    if key not in data:
        fail(f"{path.relative_to(ROOT)} missing {key}")
    return data[key]


def require_string(data: dict[str, Any], key: str, path: Path, *, nonempty: bool = True) -> str:
    value = scalar_value(require_key(data, key, path))
    if not isinstance(value, str):
        fail(f"{path.relative_to(ROOT)} {key} should be a string")
    if nonempty and not value:
        fail(f"{path.relative_to(ROOT)} {key} is empty")
    return value


def require_float(data: dict[str, Any], key: str, path: Path, expected: float | None = None) -> float:
    raw = scalar_value(require_key(data, key, path))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        fail(f"{path.relative_to(ROOT)} {key} is not numeric: {raw!r}")
    if expected is not None and abs(value - expected) > 1e-6:
        fail(f"{path.relative_to(ROOT)} {key} expected {expected:g}, got {value:g}")
    return value


def require_int(data: dict[str, Any], key: str, path: Path, expected: int | None = None) -> int:
    value = int(require_float(data, key, path))
    if expected is not None and value != expected:
        fail(f"{path.relative_to(ROOT)} {key} expected {expected}, got {value}")
    return value


def require_boolish(data: dict[str, Any], key: str, path: Path, expected: str) -> None:
    value = str(scalar_value(require_key(data, key, path)))
    if value != expected:
        fail(f"{path.relative_to(ROOT)} {key} expected {expected}, got {value}")


def require_choice(data: dict[str, Any], key: str, path: Path, choices: set[str]) -> str:
    value = require_string(data, key, path)
    if value not in choices:
        fail(f"{path.relative_to(ROOT)} {key} should be one of {sorted(choices)}, got {value!r}")
    return value


def require_json_object(data: dict[str, Any], key: str, path: Path) -> dict[str, Any]:
    value = require_string(data, key, path, nonempty=False)
    try:
        payload = json.loads(value or "{}")
    except json.JSONDecodeError as exc:
        fail(f"{path.relative_to(ROOT)} {key} is not valid JSON: {exc}")
    if not isinstance(payload, dict):
        fail(f"{path.relative_to(ROOT)} {key} should be a JSON object")
    return payload


def check_index() -> dict[str, Any]:
    index = load_json(INDEX_PATH)
    if index.get("name") != "TinManX1":
        fail("profile index name is not TinManX1")
    if not index.get("version"):
        fail("profile index has no version")

    filament_names = {item.get("name") for item in index.get("filament_list", [])}
    process_names = {item.get("name") for item in index.get("process_list", [])}
    machine_names = {item.get("name") for item in index.get("machine_list", [])}

    for material in MATERIALS:
        for fiber in FIBERS:
            expected = f"CFC {material} + {fiber} @FibreSeek Seeker 3"
            if expected not in filament_names:
                fail(f"profile index missing CFC filament {expected}")

    for nozzle in PLASTIC_NOZZLES:
        composite_machine = f"FibreSeek Seeker 3 {nozzle}+{COMPOSITE_NOZZLE} composite nozzle"
        if composite_machine not in machine_names:
            fail(f"profile index missing composite machine {composite_machine}")
        for mode in PROCESS_MODES:
            process = f"0.20mm Plastic + Continuous Fiber {mode} @FibreSeek Seeker 3 {nozzle}+{COMPOSITE_NOZZLE} nozzle"
            if process not in process_names:
                fail(f"profile index missing process {process}")

    return index


def check_machine_common() -> None:
    path = PROFILE_ROOT / "machine" / "TinManX1 FibreSeek machine common.json"
    data = load_json(path)

    require_float(data, "composite_nozzle_diameter", path, 0.7)
    require_float(data, "fiber_cut_distance", path, 58)
    require_float(data, "fiber_restart_length", path, 55)
    require_float(data, "fiber_nozzle_contact_radius", path, 1.2)
    require_float(data, "fiber_nozzle_contact_radius_extended", path, 1.8)
    require_int(data, "fiber_postprocessor_type", path, 3)
    require_int(data, "fiber_motion_blocks_buffer_size", path, 16)
    require_float(data, "fiber_plastic_extruder_heatup_speed", path, 5.5)
    require_float(data, "fiber_composite_extruder_heatup_speed", path, 3.2)
    require_int(data, "fiber_plastic_extruder_fan_index", path, 1)
    require_int(data, "fiber_composite_extruder_fan_index", path, 2)
    require_int(data, "fiber_plastic_extruder_has_fan", path, 1)
    require_int(data, "fiber_composite_extruder_has_fan", path, 1)
    require_float(data, "fiber_bed_heatup_speed", path, 0.9)
    require_float(data, "fiber_chamber_heatup_speed", path, 1.0)

    cut_gcode = require_string(data, "fiber_cut_gcode", path)
    for needle in ("M2800", "M400", "CUT DISTANCE 54.8"):
        if needle not in cut_gcode:
            fail(f"{path.relative_to(ROOT)} fiber_cut_gcode missing {needle}")

    after = require_string(data, "fiber_toolchange_gcode_after", path)
    for needle in ("SAVE_NOZZLE_TO_CLEAN", "RESTORE_NOZZLE_TO_PRINT", "G0 X304 Y285 F30000", "G0 Y335 F600"):
        if needle not in after:
            fail(f"{path.relative_to(ROOT)} fiber_toolchange_gcode_after missing {needle}")

    before_layer = require_string(data, "before_layer_change_gcode", path)
    if "G92 E0" not in before_layer:
        fail(f"{path.relative_to(ROOT)} before_layer_change_gcode must reset relative E")
    layer_change = require_string(data, "layer_change_gcode", path)
    if layer_change.strip() != "G92 E0":
        fail(f"{path.relative_to(ROOT)} layer_change_gcode must be exactly G92 E0 for Orca validation")

    payload = json.loads(require_string(data, "fiber_machine_contract_payload", path))
    if payload.get("composite_extruder", {}).get("cut_distance") != 58:
        fail(f"{path.relative_to(ROOT)} machine contract payload has wrong cut distance")


def check_composite_machines() -> None:
    for nozzle in PLASTIC_NOZZLES:
        path = PROFILE_ROOT / "machine" / f"FibreSeek Seeker 3 {nozzle}+{COMPOSITE_NOZZLE} composite nozzle.json"
        data = load_json(path)
        require_boolish(data, "fiber_enabled", path, "1")
        require_boolish(data, "fiber_shared_nozzle", path, "1")
        if as_list(data.get("nozzle_diameter")) != [nozzle, COMPOSITE_NOZZLE]:
            fail(f"{path.relative_to(ROOT)} nozzle_diameter should be [{nozzle}, {COMPOSITE_NOZZLE}]")
        if as_list(data.get("filament_map")) != ["1", "2"]:
            fail(f"{path.relative_to(ROOT)} filament_map should isolate slot 2 for CFC")


def check_filaments() -> tuple[int, int]:
    plastic_count = 0
    cfc_count = 0
    composite_printer_names = {
        *(f"FibreSeek Seeker 3 {nozzle}+{COMPOSITE_NOZZLE} composite nozzle" for nozzle in PLASTIC_NOZZLES),
        "FibreSeek Seeker 3 - Codex",
    }

    for path in sorted((PROFILE_ROOT / "filament").glob("*.json")):
        data = load_json(path)
        name = data.get("name", path.stem)
        is_cfc = name.startswith("CFC ")
        if is_cfc:
            cfc_count += 1
            require_boolish(data, "composite_enabled", path, "1")
            require_string(data, "fiber_name", path)
            require_string(data, "fiber_type", path)
            require_string(data, "fiber_manufacturer", path)
            require_string(data, "fiber_plastic_name", path)
            require_string(data, "fiber_plastic_type", path)
            require_string(data, "fiber_plastic_manufacturer", path)
            require_float(data, "fiber_plastic_diameter", path, 1.75)
            require_float(data, "fiber_plastic_density", path)
            require_float(data, "fiber_plastic_spool_weight", path)
            require_float(data, "fiber_nozzle_temperature_preheat", path)
            require_float(data, "fiber_nozzle_temperature_standby", path)
            require_float(data, "fiber_first_layers_height", path)
            require_float(data, "fiber_plastic_extrusion_speed", path)
            require_float(data, "fiber_extrusion_speed", path)
            require_float(data, "fiber_restart_pause", path, 0)
            fiber_suffix = next((suffix for suffix in FIBERS if f" + {suffix} @" in name), None)
            if fiber_suffix is None:
                fail(f"{path.relative_to(ROOT)} CFC profile name does not include a known fiber suffix")
            require_float(data, "fiber_diameter", path, FIBERS[fiber_suffix]["diameter"])
            require_float(data, "fiber_linear_density", path, FIBERS[fiber_suffix]["linear_density"])
            if set(as_list(data.get("compatible_printers"))) != composite_printer_names:
                fail(f"{path.relative_to(ROOT)} CFC profile should only be compatible with composite machines")
        else:
            plastic_count += 1
            if "composite_enabled" in data and str(scalar_value(data.get("composite_enabled"))) != "0":
                fail(f"{path.relative_to(ROOT)} non-CFC profile should not be composite-enabled")

    expected_cfc = len(MATERIALS) * len(FIBERS)
    if cfc_count != expected_cfc:
        fail(f"expected {expected_cfc} CFC filament profiles, found {cfc_count}")
    return plastic_count, cfc_count


def check_processes() -> int:
    count = 0
    for nozzle in PLASTIC_NOZZLES:
        for mode_label, mode_value in PROCESS_MODES.items():
            path = PROFILE_ROOT / "process" / (
                f"0.20mm Plastic + Continuous Fiber {mode_label} @FibreSeek Seeker 3 "
                f"{nozzle}+{COMPOSITE_NOZZLE} nozzle.json"
            )
            data = load_json(path)
            count += 1
            if data.get("fiber_reinforcement_mode") != mode_value:
                fail(f"{path.relative_to(ROOT)} has wrong fiber_reinforcement_mode")
            bridge_width = require_float(data, "bridge_line_width", path)
            if bridge_width > float(nozzle):
                fail(f"{path.relative_to(ROOT)} bridge_line_width exceeds plastic nozzle diameter")
            require_int(data, "fiber_start_layer", path, 4)
            require_float(data, "fiber_min_radius", path, 12)
            require_float(data, "fiber_min_route_length", path, 55)
            require_float(data, "fiber_perimeter_min_route_length", path, 55)
            require_float(data, "fiber_mechanical_min_route_length", path, 55)
            require_float(data, "fiber_max_arc_segment_length", path, 3)
            require_float(data, "fiber_start_length", path, 15)
            require_float(data, "fiber_slow_length", path, 10)
            require_float(data, "fiber_start_max_speed", path, 5)
            require_float(data, "fiber_start_min_speed", path, 3)
            require_float(data, "fiber_start_min_limit_speed", path, 3)
            require_float(data, "fiber_normal_max_speed", path, 30)
            require_float(data, "fiber_normal_min_speed", path, 5)
            require_float(data, "fiber_normal_min_limit_speed", path, 3)
            require_float(data, "fiber_finish_max_speed", path, 15)
            require_float(data, "fiber_finish_min_speed", path, 5)
            require_float(data, "fiber_finish_min_limit_speed", path, 3)
            require_float(data, "fiber_tension_release_fraction", path, 0)
            require_float(data, "fiber_feedrate_percent", path, 100)
            require_float(data, "fiber_correction_move_speed", path, 2)
            require_float(data, "fiber_correction_move_feedrate_percent", path, 0)
            require_float(data, "fiber_after_cut_plastic_extrusion_multiplier", path, 0.72)
            require_int(data, "fiber_routes_per_cut", path, 1)
            require_float(data, "fiber_infill_density", path, 0)
            require_string(data, "fiber_infill_angles", path, nonempty=False)
            require_choice(data, "fiber_seam_position", path, {"source", "nearest", "aligned", "rear", "random"})
            require_float(data, "fiber_seam_angle", path, 0)
            require_json_object(data, "fiber_reinforcement_payload", path)
            require_int(data, "fiber_outer_perimeter_loops", path, 1)
            require_int(data, "fiber_inner_perimeter_loops", path, 1)
            require_int(data, "fiber_plastic_outer_loops_with_fiber", path, 2)
            require_int(data, "fiber_plastic_inner_loops_with_fiber", path, 0)

    for path in sorted((PROFILE_ROOT / "process").glob("*Plastic Only*.json")):
        data = load_json(path)
        nozzle = path.stem.rsplit(" ", 2)[1]
        bridge_width = require_float(data, "bridge_line_width", path)
        if bridge_width > float(nozzle):
            fail(f"{path.relative_to(ROOT)} bridge_line_width exceeds plastic nozzle diameter")
        if str(data.get("fiber_generate_perimeters", "0")) != "0" or str(data.get("fiber_generate_infill", "0")) != "0":
            fail(f"{path.relative_to(ROOT)} plastic-only process should not generate fiber")
    return count


def main() -> int:
    check_index()
    check_machine_common()
    check_composite_machines()
    plastic_count, cfc_count = check_filaments()
    process_count = check_processes()
    print(
        "TinManX1 FibreSeek profile lint passed: "
        f"{plastic_count} plastic/base filament files, {cfc_count} CFC filament files, "
        f"{process_count} fiber process profiles."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
