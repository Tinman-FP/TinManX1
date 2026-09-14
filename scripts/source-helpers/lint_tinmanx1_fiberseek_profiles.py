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
    "PLA",
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
    "Push Plastic PC-PBT-CF",
    "PA-CF",
    "PETG",
    "PET GF",
}
REQUIRED_MATERIAL_TUNING = {
    "PETG + X-CCF",
    "PET GF + X-CCF",
    "PET GF + CGF",
    "PA-CF + X-CCF",
    "PPS-CF + X-CCF",
    "PLA + X-CCF",
}
FIBERS = {
    "X-CCF": {"diameter": 0.25, "linear_density": 102},
    "CGF": {"diameter": 0.35, "linear_density": 170},
    "CKF": {"diameter": 0.25, "linear_density": 72},
    "CBF": {"diameter": 0.25, "linear_density": 95},
}
PROCESS_MODES = {"Light": "light", "Medium": "medium", "Heavy": "heavy"}
PROCESS_LAYER_STEPS = {"Light": 3, "Medium": 2, "Heavy": 1}
PROCESS_FIBER_EXPECTED = {
    "Light": {
        "fiber_min_radius": 12,
        "fiber_max_arc_segment_length": 3,
        "fiber_start_length": 15,
        "fiber_slow_length": 5,
        "fiber_start_max_speed": 5,
        "fiber_start_min_speed": 3,
        "fiber_start_min_limit_speed": 3,
        "fiber_normal_max_speed": 30,
        "fiber_normal_min_speed": 5,
        "fiber_normal_min_limit_speed": 3,
        "fiber_finish_max_speed": 15,
        "fiber_finish_min_speed": 5,
        "fiber_finish_min_limit_speed": 3,
        "fiber_after_cut_plastic_extrusion_multiplier": 0.58,
        "fiber_line_width": 0.68,
        "fiber_outer_perimeter_loops": 1,
        "fiber_inner_perimeter_loops": 1,
        "fiber_plastic_outer_loops_with_fiber": 2,
        "fiber_plastic_inner_loops_with_fiber": 0,
    },
    "Medium": {
        "fiber_min_radius": 12,
        "fiber_max_arc_segment_length": 3,
        "fiber_start_length": 15,
        "fiber_slow_length": 10,
        "fiber_start_max_speed": 5,
        "fiber_start_min_speed": 3,
        "fiber_start_min_limit_speed": 3,
        "fiber_normal_max_speed": 30,
        "fiber_normal_min_speed": 5,
        "fiber_normal_min_limit_speed": 3,
        "fiber_finish_max_speed": 15,
        "fiber_finish_min_speed": 5,
        "fiber_finish_min_limit_speed": 8,
        "fiber_after_cut_plastic_extrusion_multiplier": 0.72,
        "fiber_line_width": 0.80,
        "fiber_outer_perimeter_loops": 2,
        "fiber_inner_perimeter_loops": 2,
        "fiber_plastic_outer_loops_with_fiber": 0,
        "fiber_plastic_inner_loops_with_fiber": 0,
    },
    "Heavy": {
        "fiber_min_radius": 10,
        "fiber_max_arc_segment_length": 4,
        "fiber_start_length": 5,
        "fiber_slow_length": 5,
        "fiber_start_max_speed": 2,
        "fiber_start_min_speed": 2,
        "fiber_start_min_limit_speed": 2,
        "fiber_normal_max_speed": 40,
        "fiber_normal_min_speed": 5,
        "fiber_normal_min_limit_speed": 3,
        "fiber_finish_max_speed": 15,
        "fiber_finish_min_speed": 3,
        "fiber_finish_min_limit_speed": 3,
        "fiber_after_cut_plastic_extrusion_multiplier": 0.72,
        "fiber_line_width": 0.70,
        "fiber_outer_perimeter_loops": 2,
        "fiber_inner_perimeter_loops": 2,
        "fiber_plastic_outer_loops_with_fiber": 0,
        "fiber_plastic_inner_loops_with_fiber": 0,
    },
}
PROCESS_ROUTE_CAPS = {"Light": 2, "Medium": 6, "Heavy": 10}
ROCKET_COMPARE_EXPECTED = {
    "Light": {
        "fiber_generate_perimeters": "0",
        "fiber_generate_infill": "0",
        "fiber_infill_pattern": "isogrid",
        "fiber_infill_density": 0,
        "fiber_infill_angles": "",
        "fiber_max_routes_per_layer": 32,
    },
    "Medium": {
        "fiber_generate_perimeters": "1",
        "fiber_generate_infill": "1",
        "fiber_infill_pattern": "isogrid",
        "fiber_infill_density": 20,
        "fiber_infill_angles": "0,60,120",
        "fiber_max_routes_per_layer": 80,
    },
    "Heavy": {
        "fiber_generate_perimeters": "1",
        "fiber_generate_infill": "1",
        "fiber_infill_pattern": "solid",
        "fiber_infill_density": 0,
        "fiber_infill_angles": "0,90,0",
        "fiber_max_routes_per_layer": 180,
    },
}
PLASTIC_NOZZLES = ("0.4", "0.6", "0.8")
CANONICAL_NOZZLES = (*PLASTIC_NOZZLES, "1.0")
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

    for nozzle in CANONICAL_NOZZLES:
        composite_machine = f"FibreSeek Seeker 3 {nozzle} nozzle - TinMan Codex"
        if composite_machine not in machine_names:
            fail(f"profile index missing composite machine {composite_machine}")
    for nozzle in PLASTIC_NOZZLES:
        for mode in PROCESS_MODES:
            for prefix in ("0.20mm Plastic + Continuous Fiber", "0.20mm Rocket Compare Composite Only"):
                process = f"{prefix} {mode} @FibreSeek Seeker 3 {nozzle}+{COMPOSITE_NOZZLE} nozzle"
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
    for nozzle in CANONICAL_NOZZLES:
        source_nozzle = nozzle if nozzle != "1.0" else "0.8"
        source_path = PROFILE_ROOT / "machine" / f"FibreSeek Seeker 3 {source_nozzle}+{COMPOSITE_NOZZLE} composite nozzle.json"
        source = load_json(source_path)
        if source.get("printer_variant") != source_nozzle:
            fail(f"{source_path.relative_to(ROOT)} has invalid printer_variant")
        require_boolish(source, "fiber_enabled", source_path, "1")
        require_boolish(source, "fiber_shared_nozzle", source_path, "1")
        if as_list(source.get("filament_map")) != ["1", "2"]:
            fail(f"{source_path.relative_to(ROOT)} filament_map should isolate slot 2 for CFC")

        path = PROFILE_ROOT / "machine" / "TinMan Codex" / (
            f"FibreSeek Seeker 3 {nozzle} nozzle - TinMan Codex.json"
        )
        data = load_json(path)
        if data.get("inherits") != source.get("name"):
            fail(f"{path.relative_to(ROOT)} should inherit the validated composite machine")
        if as_list(data.get("nozzle_diameter")) != [nozzle, COMPOSITE_NOZZLE]:
            fail(f"{path.relative_to(ROOT)} nozzle_diameter should be [{nozzle}, {COMPOSITE_NOZZLE}]")


def check_filaments() -> tuple[int, int]:
    plastic_count = 0
    cfc_count = 0
    composite_printer_names = {
        *(f"FibreSeek Seeker 3 {nozzle} nozzle - TinMan Codex" for nozzle in CANONICAL_NOZZLES),
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
    common_path = PROFILE_ROOT / "process" / "TinManX1 FibreSeek process common.json"
    common = load_json(common_path)
    require_choice(
        common,
        "fiber_manufacturing_mode",
        common_path,
        {"plastic_plus_fiber_overlay", "composite_only"},
    )
    if common["fiber_manufacturing_mode"] != "plastic_plus_fiber_overlay":
        fail(
            f"{common_path.relative_to(ROOT)} fiber_manufacturing_mode should default to "
            "plastic_plus_fiber_overlay so process profiles opt into composite-road planning deliberately"
        )

    count = 0
    for nozzle in PLASTIC_NOZZLES:
        for mode_label, mode_value in PROCESS_MODES.items():
            for prefix, compare_mode in (
                ("0.20mm Plastic + Continuous Fiber", False),
                ("0.20mm Rocket Compare Composite Only", True),
            ):
                path = PROFILE_ROOT / "process" / (
                    f"{prefix} {mode_label} @FibreSeek Seeker 3 "
                    f"{nozzle}+{COMPOSITE_NOZZLE} nozzle.json"
                )
                data = load_json(path)
                count += 1
                if data.get("fiber_reinforcement_mode") != mode_value:
                    fail(f"{path.relative_to(ROOT)} has wrong fiber_reinforcement_mode")
                require_string(data, "fiber_manufacturing_mode", path)
                if data["fiber_manufacturing_mode"] != "composite_only":
                    fail(f"{path.relative_to(ROOT)} must set fiber_manufacturing_mode=composite_only")
                solid_payload = require_json_object(data, "fiber_infill_solid_payload", path)
                if solid_payload.get("angle_list_raw") != "0/90/0":
                    fail(f"{path.relative_to(ROOT)} solid payload must preserve 0/90/0 solid angles")
                require_float(solid_payload, "extrusion_width_mm", path, 0.7)
                require_float(solid_payload, "min_segment_length_mm", path, 10)
                require_int(data, "fiber_layer_step", path, PROCESS_LAYER_STEPS[mode_label])
                bridge_width = require_float(data, "bridge_line_width", path)
                if bridge_width > float(nozzle):
                    fail(f"{path.relative_to(ROOT)} bridge_line_width exceeds plastic nozzle diameter")
                require_int(data, "fiber_start_layer", path, 4)
                expected = PROCESS_FIBER_EXPECTED[mode_label]
                for key, value in expected.items():
                    require_float(data, key, path, value)
                require_float(data, "fiber_min_route_length", path, 55)
                require_float(data, "fiber_perimeter_min_route_length", path, 55)
                require_float(data, "fiber_mechanical_min_route_length", path, 55)
                require_float(data, "fiber_tension_release_fraction", path, 0)
                require_float(data, "fiber_feedrate_percent", path, 100)
                require_float(data, "fiber_correction_move_speed", path, 2)
                require_float(data, "fiber_correction_move_feedrate_percent", path, 0)
                for printer_only_key in ("fiber_cut_distance", "fiber_restart_length", "fiber_cut_gcode"):
                    if printer_only_key in data:
                        fail(
                            f"{path.relative_to(ROOT)} contains printer-only key "
                            f"{printer_only_key}"
                        )
                require_int(data, "fiber_routes_per_cut", path, 1)
                if compare_mode:
                    compare_expected = ROCKET_COMPARE_EXPECTED[mode_label]
                    require_boolish(data, "fiber_generate_perimeters", path, compare_expected["fiber_generate_perimeters"])
                    require_boolish(data, "fiber_generate_infill", path, compare_expected["fiber_generate_infill"])
                    pattern = require_choice(data, "fiber_infill_pattern", path, {"solid", "rhombic", "isogrid", "anisogrid", "tetragrid"})
                    if pattern != compare_expected["fiber_infill_pattern"]:
                        fail(
                            f"{path.relative_to(ROOT)} fiber_infill_pattern expected "
                            f"{compare_expected['fiber_infill_pattern']}, got {pattern}"
                        )
                    require_float(data, "fiber_infill_density", path, compare_expected["fiber_infill_density"])
                    angles = require_string(data, "fiber_infill_angles", path, nonempty=False)
                    if angles != compare_expected["fiber_infill_angles"]:
                        fail(
                            f"{path.relative_to(ROOT)} fiber_infill_angles expected "
                            f"{compare_expected['fiber_infill_angles']!r}, got {angles!r}"
                        )
                    require_int(data, "fiber_max_routes_per_layer", path, compare_expected["fiber_max_routes_per_layer"])
                else:
                    require_boolish(data, "fiber_generate_perimeters", path, "1")
                    require_boolish(data, "fiber_generate_infill", path, "1")
                    require_choice(data, "fiber_infill_pattern", path, {"solid"})
                    require_float(data, "fiber_infill_density", path, 0)
                    require_string(data, "fiber_infill_angles", path, nonempty=False)
                    require_int(data, "fiber_max_routes_per_layer", path, PROCESS_ROUTE_CAPS[mode_label])
                require_choice(data, "fiber_seam_position", path, {"source", "nearest", "aligned", "rear", "random"})
                require_float(data, "fiber_seam_angle", path, 0)
                payload = require_json_object(data, "fiber_reinforcement_payload", path)
                tuning = payload.get("material_tuning")
                if not isinstance(tuning, dict):
                    fail(f"{path.relative_to(ROOT)} fiber_reinforcement_payload missing material_tuning map")
                missing_tuning = REQUIRED_MATERIAL_TUNING.difference(tuning)
                if missing_tuning:
                    fail(
                        f"{path.relative_to(ROOT)} material_tuning missing "
                        + ", ".join(sorted(missing_tuning))
                    )
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
