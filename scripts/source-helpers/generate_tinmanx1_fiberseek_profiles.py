#!/usr/bin/env python3
"""Generate TinManX1 FibreSeek system presets.

The values here are TinManX1-native presets derived from the sanitized
FibreSeek/Rocket comparison work and generic Orca material baselines. The
generator intentionally writes normal plastic profiles separately from
plastic-plus-continuous-fiber profiles so the UI can group the process lanes
cleanly.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from pathlib import Path
import sys


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())
HELPER_DIR = Path(__file__).resolve().parent
PROFILE_ROOT = ROOT / "resources" / "profiles"
PACK_ROOT = PROFILE_ROOT / "TinManX1"
PACK_VERSION = "02.04.00.13"
MACHINE_MODEL = "FibreSeek Seeker 3"
LEGACY_COMPOSITE_MACHINE_NAMES = ["FibreSeek Seeker 3 - Codex"]


MATERIALS = {
    "ABS": {
        "color": "#8A8A8A",
        "fiber_color": "#2F2F2F",
        "density": 1.04,
        "cost": 22,
        "temp": 250,
        "temp_first": 255,
        "bed": 100,
        "bed_first": 105,
        "chamber": 50,
        "fan": 10,
        "fan_max": 20,
        "flow": 1.00,
        "mvs": 15,
        "fiber_temp": 260,
        "fiber_temp_first": 265,
        "fiber_fan": 15,
        "fiber_flow": 0.85,
        "fiber_mvs": 12,
    },
    "ASA": {
        "color": "#E5A04C",
        "fiber_color": "#3B3B3B",
        "density": 1.07,
        "cost": 28,
        "temp": 260,
        "temp_first": 265,
        "bed": 105,
        "bed_first": 110,
        "chamber": 55,
        "fan": 10,
        "fan_max": 25,
        "flow": 1.00,
        "mvs": 15,
        "fiber_temp": 270,
        "fiber_temp_first": 275,
        "fiber_fan": 15,
        "fiber_flow": 0.85,
        "fiber_mvs": 12,
    },
    "PPA-CF": {
        "color": "#2E2E2E",
        "fiber_color": "#1F1F1F",
        "density": 1.25,
        "cost": 80,
        "temp": 295,
        "temp_first": 300,
        "bed": 110,
        "bed_first": 115,
        "chamber": 60,
        "fan": 10,
        "fan_max": 25,
        "flow": 0.96,
        "mvs": 8,
        "fiber_temp": 300,
        "fiber_temp_first": 305,
        "fiber_fan": 15,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
    "PPS-CF": {
        "color": "#262626",
        "fiber_color": "#151515",
        "density": 1.26,
        "cost": 120,
        "temp": 330,
        "temp_first": 335,
        "bed": 110,
        "bed_first": 115,
        "chamber": 60,
        "fan": 0,
        "fan_max": 15,
        "flow": 0.96,
        "mvs": 4,
        "fiber_temp": 335,
        "fiber_temp_first": 340,
        "fiber_fan": 10,
        "fiber_flow": 0.82,
        "fiber_mvs": 6,
    },
    "ABS-CF": {
        "color": "#363636",
        "fiber_color": "#181818",
        "density": 1.12,
        "cost": 48,
        "temp": 255,
        "temp_first": 260,
        "bed": 100,
        "bed_first": 105,
        "chamber": 50,
        "fan": 5,
        "fan_max": 15,
        "flow": 0.98,
        "mvs": 10,
        "fiber_temp": 265,
        "fiber_temp_first": 270,
        "fiber_fan": 10,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
    "ABS-GF": {
        "color": "#777777",
        "fiber_color": "#3A3A3A",
        "density": 1.08,
        "cost": 42,
        "temp": 260,
        "temp_first": 265,
        "bed": 105,
        "bed_first": 110,
        "chamber": 50,
        "fan": 10,
        "fan_max": 20,
        "flow": 0.95,
        "mvs": 8,
        "fiber_temp": 270,
        "fiber_temp_first": 275,
        "fiber_fan": 15,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
    "ASA-GF": {
        "color": "#9B9B8B",
        "fiber_color": "#444438",
        "density": 1.15,
        "cost": 52,
        "temp": 260,
        "temp_first": 265,
        "bed": 105,
        "bed_first": 110,
        "chamber": 65,
        "fan": 10,
        "fan_max": 20,
        "flow": 0.95,
        "mvs": 8,
        "fiber_temp": 270,
        "fiber_temp_first": 275,
        "fiber_fan": 15,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
    "PP": {
        "color": "#F2F2F2",
        "fiber_color": "#555555",
        "density": 0.90,
        "cost": 35,
        "temp": 225,
        "temp_first": 230,
        "bed": 70,
        "bed_first": 70,
        "chamber": 35,
        "fan": 0,
        "fan_max": 10,
        "flow": 1.00,
        "mvs": 10,
        "fiber_temp": 235,
        "fiber_temp_first": 240,
        "fiber_fan": 5,
        "fiber_flow": 0.85,
        "fiber_mvs": 10,
    },
    "PETG": {
        "color": "#FCD02E",
        "fiber_color": "#F67C01",
        "manufacturer": "FIBRESEEK",
        "fiber_plastic_name": "CFC PETG",
        "fiber_plastic_density": 1.27,
        "density": 1.27,
        "cost": 20,
        "temp": 250,
        "temp_first": 250,
        "bed": 75,
        "bed_first": 75,
        "chamber": 0,
        "temp_wait": 150,
        "fan": 50,
        "fan_max": 90,
        "flow": 1.00,
        "mvs": 15,
        "retraction_length": 1.0,
        "retraction_speed": 20,
        "retraction_minimum_travel": 5,
        "z_hop": 0.4,
        "fiber_temp": 270,
        "fiber_temp_first": 270,
        "fiber_fan": 80,
        "fiber_flow": 0.80,
        "fiber_mvs": 10,
        "fiber_retraction_length": 1.0,
        "fiber_retraction_speed": 10,
        "fiber_z_hop": 1.0,
        "fiber_temp_standby": 180,
        "fiber_plastic_extrusion_speed": 10,
        "fiber_extrusion_speed": 25,
        "fiber_overrides": {
            "CGF": {
                "fiber_fan": 100,
                "fiber_flow": 0.68,
            },
        },
    },
    "PET GF": {
        "color": "#FFF06292",
        "fiber_color": "#F67C01",
        "density": 1.43,
        "cost": 24,
        "temp": 300,
        "temp_first": 300,
        "bed": 75,
        "bed_first": 75,
        "chamber": 25,
        "fan": 40,
        "fan_max": 60,
        "flow": 1.00,
        "mvs": 15,
        "retraction_length": 0.5,
        "retraction_speed": 20,
        "retraction_minimum_travel": 0,
        "z_hop": 0.4,
        "fiber_temp": 270,
        "fiber_temp_first": 270,
        "fiber_fan": 80,
        "fiber_flow": 0.80,
        "fiber_mvs": 10,
        "fiber_retraction_length": 1.0,
        "fiber_retraction_speed": 10,
        "fiber_z_hop": 1.0,
        "fiber_overrides": {
            "CGF": {
                "fiber_fan": 100,
                "fiber_flow": 0.68,
            },
        },
    },
    "PCTG": {
        "color": "#64B5F6",
        "fiber_color": "#203040",
        "density": 1.27,
        "cost": 35,
        "temp": 260,
        "temp_first": 265,
        "bed": 80,
        "bed_first": 80,
        "chamber": 45,
        "fan": 20,
        "fan_max": 35,
        "flow": 0.97,
        "mvs": 12,
        "fiber_temp": 270,
        "fiber_temp_first": 275,
        "fiber_fan": 25,
        "fiber_flow": 0.85,
        "fiber_mvs": 12,
    },
    "PCTG-CF": {
        "color": "#2B3A42",
        "fiber_color": "#101820",
        "density": 1.18,
        "cost": 55,
        "temp": 260,
        "temp_first": 265,
        "bed": 80,
        "bed_first": 80,
        "chamber": 45,
        "fan": 5,
        "fan_max": 15,
        "flow": 0.98,
        "mvs": 8,
        "fiber_temp": 270,
        "fiber_temp_first": 275,
        "fiber_fan": 10,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
    "PA-CF": {
        "color": "#2D2D2D",
        "fiber_color": "#111111",
        "density": 1.17,
        "cost": 70,
        "temp": 300,
        "temp_first": 305,
        "bed": 80,
        "bed_first": 85,
        "chamber": 50,
        "fan": 20,
        "fan_max": 35,
        "flow": 0.95,
        "mvs": 8,
        "fiber_temp": 305,
        "fiber_temp_first": 310,
        "fiber_fan": 20,
        "fiber_flow": 0.82,
        "fiber_mvs": 8,
    },
}


PLASTIC_NOZZLES = {
    "0.4": {"layer": "0.20", "line_width": "0.42", "max_layer": "0.30", "min_layer": "0.08"},
    "0.6": {"layer": "0.20", "line_width": "0.62", "max_layer": "0.42", "min_layer": "0.12"},
    "0.8": {"layer": "0.32", "line_width": "0.82", "max_layer": "0.56", "min_layer": "0.16"},
}
COMPOSITE_NOZZLE = "0.7"
COMPOSITE_LINE_WIDTH = "0.80"


FIBER_MODES = {
    "Light": {
        "mode": "light",
        "spacing": "2.40",
        "layer_step": "8",
        "max_routes": "2",
        "routes_per_cut": "1",
        "infill_source": "plastic_traces",
        "generate_perimeters": "1",
        "generate_infill": "1",
    },
    "Medium": {
        "mode": "medium",
        "spacing": "1.60",
        "layer_step": "4",
        "max_routes": "4",
        "routes_per_cut": "1",
        "infill_source": "plastic_traces",
        "generate_perimeters": "1",
        "generate_infill": "1",
    },
    "Heavy": {
        "mode": "heavy",
        "spacing": "0.80",
        "layer_step": "2",
        "max_routes": "8",
        "routes_per_cut": "1",
        "infill_source": "generated_ribs",
        "generate_perimeters": "1",
        "generate_infill": "1",
    },
}


CONTINUOUS_FIBERS = [
    {
        "label": "X-CCF Carbon fiber 0.25 mm",
        "profile_suffix": "X-CCF",
        "type": "carbon_fiber",
        "manufacturer": "fibreseek",
        "source_id": "tinmanx1-x-ccf-025",
        "color": "#111111",
        "diameter": 0.25,
        "linear_density": 102.0,
        "cost": 180,
        "confidence": "Rocket PETG baseline",
    },
    {
        "label": "CGF Glass fiber 0.35 mm",
        "profile_suffix": "CGF",
        "type": "glass_fiber",
        "manufacturer": "TinManX1",
        "source_id": "tinmanx1-cgf-035",
        "color": "#E8F4FF",
        "diameter": 0.35,
        "linear_density": 170.0,
        "cost": 45,
        "confidence": "TinManX1 estimate",
    },
    {
        "label": "CKF Kevlar fiber 0.25 mm",
        "profile_suffix": "CKF",
        "type": "aramid_fiber",
        "manufacturer": "TinManX1",
        "source_id": "tinmanx1-ckf-025",
        "color": "#D8A300",
        "diameter": 0.25,
        "linear_density": 72.0,
        "cost": 160,
        "confidence": "TinManX1 estimate",
    },
    {
        "label": "CBF Basalt fiber 0.25 mm",
        "profile_suffix": "CBF",
        "type": "basalt_fiber",
        "manufacturer": "TinManX1",
        "source_id": "tinmanx1-cbf-025",
        "color": "#3F3530",
        "diameter": 0.25,
        "linear_density": 95.0,
        "cost": 150,
        "confidence": "TinManX1 estimate",
    },
]


def arr(value):
    return [str(value)]


def write_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n")


def load_layup_payload_helper():
    helper_path = HELPER_DIR / "build_tinmanx1_fiber_layup_payload.py"
    spec = importlib.util.spec_from_file_location("tinmanx1_layup_payload_helper", helper_path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"Unable to load layup payload helper: {helper_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def layup_payload_for_template(template: str) -> str:
    if template == "none":
        return "{}"
    helper = load_layup_payload_helper()
    payload = {"layup_bands": [helper.normalize_band(dict(item)) for item in helper.TEMPLATES[template]]}
    helper.assert_planner_accepts(payload)
    return helper.compact_json(payload)


def material_slug(material: str) -> str:
    return material.replace("/", "-").replace(" ", "-")


def plastic_machine_name(nozzle: str) -> str:
    return f"{MACHINE_MODEL} {nozzle} nozzle"


def composite_machine_name(plastic_nozzle: str) -> str:
    return f"{MACHINE_MODEL} {plastic_nozzle}+{COMPOSITE_NOZZLE} composite nozzle"


def plastic_filament_name(material: str) -> str:
    return f"TinManX1 {material} @FibreSeek Seeker 3"


def composite_filament_name(material: str, fiber: dict | None = None) -> str:
    fiber = fiber or CONTINUOUS_FIBERS[0]
    return f"CFC {material} + {fiber['profile_suffix']} @FibreSeek Seeker 3"


def all_machine_names() -> list[str]:
    names = [plastic_machine_name(n) for n in PLASTIC_NOZZLES]
    names.extend(composite_machine_name(n) for n in PLASTIC_NOZZLES)
    return names


def compatible_plastic_printers() -> list[str]:
    return [plastic_machine_name(n) for n in PLASTIC_NOZZLES]


def compatible_composite_printers() -> list[str]:
    return [composite_machine_name(n) for n in PLASTIC_NOZZLES] + LEGACY_COMPOSITE_MACHINE_NAMES


def compatible_filament_printers() -> list[str]:
    return compatible_plastic_printers() + compatible_composite_printers()


def compatible_process_printers(plastic_nozzle: str, fiber: bool) -> list[str]:
    names = [composite_machine_name(plastic_nozzle)] if fiber else [
        plastic_machine_name(plastic_nozzle),
        composite_machine_name(plastic_nozzle),
    ]
    if plastic_nozzle == "0.4":
        names.extend(LEGACY_COMPOSITE_MACHINE_NAMES)
    return names


def fiber_value(values: dict, fiber: dict, key: str):
    overrides = values.get("fiber_overrides", {}).get(fiber["profile_suffix"], {})
    return overrides.get(key, values[key])


def with_optional_filament_retraction(profile: dict, values: dict, prefix: str = "") -> dict:
    fields = {
        "retraction_length": "filament_retraction_length",
        "retraction_speed": "filament_retraction_speed",
        "retraction_minimum_travel": "filament_retraction_minimum_travel",
        "z_hop": "filament_z_hop",
    }
    for source, target in fields.items():
        key = f"{prefix}{source}"
        if key in values:
            profile[target] = arr(values[key])
    return profile


def filament_base(material: str, values: dict) -> dict:
    chamber_temperature = int(values["chamber"])
    profile = {
        "type": "filament",
        "name": f"TinManX1 {material} base",
        "from": "system",
        "instantiation": "false",
        "filament_vendor": arr("TinManX1"),
        "filament_type": arr(material),
        "default_filament_colour": arr(values["color"]),
        "filament_diameter": arr("1.75"),
        "filament_density": arr(values["density"]),
        "filament_cost": arr(values["cost"]),
        "filament_flow_ratio": arr(f"{values['flow']:.2f}"),
        "filament_max_volumetric_speed": arr(values["mvs"]),
        "filament_is_support": arr("0"),
        "filament_soluble": arr("0"),
        "nozzle_temperature": arr(values["temp"]),
        "nozzle_temperature_initial_layer": arr(values["temp_first"]),
        "nozzle_temperature_range_low": arr(max(180, values["temp"] - 20)),
        "nozzle_temperature_range_high": arr(values["temp_first"] + 20),
        "hot_plate_temp": arr(values["bed"]),
        "hot_plate_temp_initial_layer": arr(values["bed_first"]),
        "eng_plate_temp": arr(values["bed"]),
        "eng_plate_temp_initial_layer": arr(values["bed_first"]),
        "textured_plate_temp": arr(values["bed"]),
        "textured_plate_temp_initial_layer": arr(values["bed_first"]),
        "chamber_temperature": arr(chamber_temperature),
        "activate_chamber_temp_control": arr("1" if chamber_temperature else "0"),
        "fan_min_speed": arr(values["fan"]),
        "fan_max_speed": arr(values["fan_max"]),
        "slow_down_for_layer_cooling": arr("1" if values["fan"] else "0"),
        "enable_pressure_advance": arr("1"),
        "pressure_advance": arr("0.020"),
        "required_nozzle_HRC": arr("3" if ("CF" in material or "GF" in material) else "0"),
        "plastic_spool_weight": arr("1000"),
        "composite_enabled": arr("0"),
        "fiber_name": arr(""),
        "fiber_type": arr(""),
        "fiber_manufacturer": arr(""),
        "fiber_diameter": arr("0"),
        "fiber_linear_density": arr("0"),
        "fiber_spool_length_km": arr("0"),
        "fiber_cost": arr("0"),
        "fiber_plastic_name": arr(""),
        "fiber_plastic_type": arr(""),
        "fiber_plastic_manufacturer": arr(""),
        "fiber_plastic_diameter": arr("0"),
        "fiber_plastic_density": arr("0"),
        "fiber_plastic_cost": arr("0"),
        "fiber_plastic_spool_weight": arr("0"),
        "fiber_nozzle_temperature_preheat": arr("0"),
        "fiber_nozzle_temperature_standby": arr(values.get("temp_wait", 150)),
        "fiber_first_layers_height": arr("0"),
        "fiber_plastic_extrusion_speed": arr("0"),
        "fiber_extrusion_speed": arr("0"),
        "fiber_restart_pause": arr("0"),
        "fiber_finish_ironing_distance": arr("0"),
        "fiber_priming_line_height": arr("0"),
        "fiber_material_kind": arr("plastic"),
        "fiber_source_material_id": arr(f"tinmanx1-{material_slug(material).lower()}"),
    }
    return with_optional_filament_retraction(profile, values)


def plastic_filament(material: str) -> dict:
    return {
        "type": "filament",
        "name": plastic_filament_name(material),
        "inherits": f"TinManX1 {material} base",
        "from": "system",
        "setting_id": f"TMX-FS3-{material_slug(material)}-P",
        "filament_id": f"tinmanx1-fs3-{material_slug(material).lower()}-plastic",
        "instantiation": "true",
        "filament_vendor": arr("TinManX1"),
        "filament_type": arr(material),
        "compatible_printers": compatible_filament_printers(),
    }


def composite_filament(material: str, values: dict, fiber: dict) -> dict:
    confidence = (
        "Known FibreSeek/Rocket baseline"
        if material == "PETG" and fiber["profile_suffix"] == "X-CCF"
        else "TinManX1 estimate"
    )
    baseline_note = (
        "Known FibreSeek/Rocket baseline only for CFC PETG + X-CCF; "
        "other matrix/fiber combinations are conservative TinManX1 estimates for coupon tuning."
    )
    profile = {
        "type": "filament",
        "name": composite_filament_name(material, fiber),
        "inherits": f"TinManX1 {material} base",
        "from": "system",
        "setting_id": f"TMX-FS3-{material_slug(material)}-{fiber['profile_suffix'].upper()}",
        "filament_id": f"tinmanx1-fs3-{material_slug(material).lower()}-{fiber['profile_suffix'].lower()}",
        "instantiation": "true",
        # The add-filament catalog reads these fields before inheritance is applied.
        "filament_vendor": arr("TinManX1"),
        "filament_type": arr("CFC"),
        "description": f"{composite_filament_name(material, fiber)}. {confidence}. {baseline_note}",
        "default_filament_colour": arr(fiber["color"]),
        "filament_flow_ratio": arr(f"{fiber_value(values, fiber, 'fiber_flow'):.2f}"),
        "filament_max_volumetric_speed": arr(fiber_value(values, fiber, "fiber_mvs")),
        "nozzle_temperature": arr(fiber_value(values, fiber, "fiber_temp")),
        "nozzle_temperature_initial_layer": arr(fiber_value(values, fiber, "fiber_temp_first")),
        "nozzle_temperature_range_low": arr(max(180, fiber_value(values, fiber, "fiber_temp") - 20)),
        "nozzle_temperature_range_high": arr(fiber_value(values, fiber, "fiber_temp_first") + 20),
        "fan_min_speed": arr(fiber_value(values, fiber, "fiber_fan")),
        "fan_max_speed": arr(max(fiber_value(values, fiber, "fiber_fan"), values["fan_max"])),
        "composite_enabled": arr("1"),
        "fiber_name": arr(fiber["label"]),
        "fiber_type": arr(fiber["type"]),
        "fiber_manufacturer": arr(fiber["manufacturer"]),
        "fiber_diameter": arr(fiber["diameter"]),
        "fiber_linear_density": arr(fiber["linear_density"]),
        "fiber_spool_length_km": arr("0.5"),
        "fiber_cost": arr(fiber["cost"]),
        "fiber_plastic_name": arr(values.get("fiber_plastic_name", material)),
        "fiber_plastic_type": arr(material),
        "fiber_plastic_manufacturer": arr(values.get("manufacturer", "TinManX1")),
        "fiber_plastic_diameter": arr("1.75"),
        "fiber_plastic_density": arr(values.get("fiber_plastic_density", values["density"])),
        "fiber_plastic_cost": arr(values.get("fiber_plastic_cost", values["cost"])),
        "fiber_plastic_spool_weight": arr("1000"),
        "fiber_nozzle_temperature_preheat": arr(fiber_value(values, fiber, "fiber_temp")),
        "fiber_nozzle_temperature_standby": arr(values.get("fiber_temp_standby", 150)),
        "fiber_first_layers_height": arr("0.25"),
        "fiber_plastic_extrusion_speed": arr(values.get("fiber_plastic_extrusion_speed", 8)),
        "fiber_extrusion_speed": arr(values.get("fiber_extrusion_speed", 25)),
        "fiber_restart_pause": arr("0"),
        "fiber_finish_ironing_distance": arr("8"),
        "fiber_priming_line_height": arr("0.2"),
        "fiber_material_kind": arr("composite_matrix"),
        "fiber_source_material_id": arr(f"tinmanx1-{material_slug(material).lower()}-{fiber['profile_suffix'].lower()}"),
        "compatible_printers": compatible_composite_printers(),
    }
    return with_optional_filament_retraction(profile, values, prefix="fiber_")


def machine_model() -> dict:
    variants = list(PLASTIC_NOZZLES)
    variants.extend(f"{nozzle}+{COMPOSITE_NOZZLE}" for nozzle in PLASTIC_NOZZLES)
    return {
        "type": "machine_model",
        "name": MACHINE_MODEL,
        "model_id": "TinManX1-FibreSeek-Seeker-3",
        "nozzle_diameter": ";".join(variants),
        "machine_tech": "FFF",
        "family": "TinManX1",
        "default_materials": ";".join(
            [
                plastic_filament_name("PCTG"),
                composite_filament_name("PCTG"),
                plastic_filament_name("ABS"),
                composite_filament_name("ABS"),
                plastic_filament_name("PA-CF"),
                composite_filament_name("PA-CF"),
            ]
        ),
    }


def machine_common() -> dict:
    return {
        "type": "machine",
        "name": "TinManX1 FibreSeek machine common",
        "from": "system",
        "instantiation": "false",
        "printer_model": MACHINE_MODEL,
        "gcode_flavor": "marlin",
        "single_extruder_multi_material": "0",
        "printable_area": ["0x0", "305x0", "305x305", "0x305"],
        "printable_height": "245",
        "machine_max_speed_x": arr("500"),
        "machine_max_speed_y": arr("500"),
        "machine_max_speed_z": arr("5"),
        "machine_max_acceleration_x": arr("5000"),
        "machine_max_acceleration_y": arr("5000"),
        "machine_max_acceleration_z": arr("100"),
        "machine_max_acceleration_e": arr("8000"),
        "machine_max_acceleration_extruding": arr("5000"),
        "machine_max_acceleration_retracting": arr("8000"),
        "machine_max_acceleration_travel": arr("5000"),
        "machine_max_jerk_x": arr("20"),
        "machine_max_jerk_y": arr("20"),
        "machine_max_jerk_z": arr("10"),
        "machine_max_jerk_e": arr("10"),
        "retraction_length": arr("1.0"),
        "retraction_minimum_travel": arr("3"),
        "retraction_speed": arr("30"),
        "deretraction_speed": arr("30"),
        "z_hop": arr("0.5"),
        "machine_start_gcode": "G92 E0\nG0 Z10 F900\n",
        "machine_end_gcode": "M400\nG90\nG0 X300 Y280 F6000\nG91\nG0 Z10 F900\n",
        "before_layer_change_gcode": ";BEFORE_LAYER_CHANGE\n;[layer_z]\nG92 E0\n",
        "layer_change_gcode": "G92 E0",
        "use_relative_e_distances": "1",
        "support_chamber_temp_control": "1",
        "fiber_enabled": "0",
        "fiber_shared_nozzle": "0",
        "plastic_nozzle_diameter": "0.4",
        "composite_nozzle_diameter": COMPOSITE_NOZZLE,
        "fiber_plastic_extruder_offset_x": "0",
        "fiber_plastic_extruder_offset_y": "0",
        "fiber_plastic_extruder_offset_z": "0",
        "fiber_composite_extruder_offset_x": "0",
        "fiber_composite_extruder_offset_y": "0",
        "fiber_composite_extruder_offset_z": "0",
        "fiber_plastic_extruder_heatup_speed": "5.5",
        "fiber_composite_extruder_heatup_speed": "3.2",
        "fiber_plastic_extruder_has_fan": "1",
        "fiber_composite_extruder_has_fan": "1",
        "fiber_plastic_extruder_fan_index": "1",
        "fiber_composite_extruder_fan_index": "2",
        "fiber_bed_heatup_speed": "0.9",
        "fiber_chamber_heatup_speed": "1.0",
        "fiber_motion_blocks_buffer_size": "16",
        "fiber_cut_distance": "58",
        "fiber_restart_length": "55",
        "fiber_cut_gcode": "M2800\nM400\n;CUT DISTANCE 54.8",
        "fiber_nozzle_contact_radius": "1.2",
        "fiber_nozzle_contact_radius_extended": "1.8",
        "fiber_toolchange_gcode_before": "G0 Y280 F10000\nM106 P1 S255\nM400\n",
        "fiber_toolchange_gcode_after": (
            "SAVE_NOZZLE_TO_CLEAN\n"
            "T1\n"
            "G0 X304 Y285 F30000\n"
            "G0 Y290 F1200\n"
            "G0 Y335 F600\n"
            "G0 Y320 F10000\n"
            "G0 Y335 F10000\n"
            "G0 Y320 F10000\n"
            "G0 Y335 F10000\n"
            "G4 P1000\n"
            "G0 X289 F600\n"
            "G0 X306 F600\n"
            "G0 X289 F600\n"
            "G0 X306 F600\n"
            "G4 P2000\n"
            "G0 Y285 F1200\n"
            "M400\n"
            "RESTORE_NOZZLE_TO_PRINT\n"
            "M106 P1 S0"
        ),
        "fiber_slot_roles": "plastic,composite",
        "continuous_fiber_name": "X-CCF Carbon fiber 0.25 mm",
        "continuous_fiber_type": "carbon_fiber",
        "continuous_fiber_material_kind": "continuous_fiber",
        "continuous_fiber_source_material_id": "tinmanx1-x-ccf-025",
        "continuous_fiber_diameter": "0.25",
        "continuous_fiber_linear_density": "102",
        "fiber_postprocessor_type": "3",
        "fiber_machine_contract_payload": json.dumps(
            {
                "machine": MACHINE_MODEL,
                "plastic_extruder": {"heatup_speed_c_per_s": 5.5, "fan_index": 1, "has_fan": True},
                "composite_extruder": {
                    "heatup_speed_c_per_s": 3.2,
                    "fan_index": 2,
                    "has_fan": True,
                    "nozzle_diameter": float(COMPOSITE_NOZZLE),
                    "cut_distance": 58,
                    "restart_length": 55,
                    "contact_radius": 1.2,
                    "contact_radius_extended": 1.8,
                },
                "thermal": {"bed_heatup_speed_c_per_s": 0.9, "chamber_heatup_speed_c_per_s": 1.0},
                "motion": {"blocks_buffer_size": 16, "travel_speed_xy": 500, "travel_speed_z": 5},
            },
            sort_keys=True,
        ),
    }


def plastic_machine(nozzle: str, spec: dict) -> dict:
    return {
        "type": "machine",
        "name": plastic_machine_name(nozzle),
        "inherits": "TinManX1 FibreSeek machine common",
        "from": "system",
        "setting_id": f"TMX-FS3-M-P{nozzle}",
        "instantiation": "true",
        "printer_model": MACHINE_MODEL,
        "printer_variant": nozzle,
        "nozzle_diameter": arr(nozzle),
        "max_layer_height": arr(spec["max_layer"]),
        "min_layer_height": arr(spec["min_layer"]),
        "default_print_profile": f"{spec['layer']}mm Plastic Only @FibreSeek Seeker 3 {nozzle} nozzle",
        "default_filament_profile": arr(plastic_filament_name("PCTG")),
        "plastic_nozzle_diameter": nozzle,
        "fiber_enabled": "0",
    }


def composite_machine(plastic_nozzle: str, spec: dict) -> dict:
    return {
        "type": "machine",
        "name": composite_machine_name(plastic_nozzle),
        "inherits": "TinManX1 FibreSeek machine common",
        "from": "system",
        "setting_id": f"TMX-FS3-M-X{plastic_nozzle}-{COMPOSITE_NOZZLE}",
        "instantiation": "true",
        "printer_model": MACHINE_MODEL,
        "printer_variant": f"{plastic_nozzle}+{COMPOSITE_NOZZLE}",
        "extruder_colour": ["#D84B4B", "#111111"],
        "extruder_offset": ["0x0", "0x0"],
        "extruder_type": ["Direct Drive", "Direct Drive"],
        "extruder_variant_list": ["Direct Drive Standard", "Direct Drive Standard"],
        "printer_extruder_id": ["1", "2"],
        "printer_extruder_variant": ["Direct Drive Standard", "Direct Drive Standard"],
        "nozzle_diameter": [plastic_nozzle, COMPOSITE_NOZZLE],
        "filament_map": ["1", "2"],
        "max_layer_height": [spec["max_layer"], "0.40"],
        "min_layer_height": [spec["min_layer"], "0.14"],
        "retraction_length": ["1.0", "1.0"],
        "default_print_profile": f"0.20mm Plastic + Continuous Fiber Medium @FibreSeek Seeker 3 {plastic_nozzle}+{COMPOSITE_NOZZLE} nozzle",
        "default_filament_profile": [plastic_filament_name("PCTG"), composite_filament_name("PCTG")],
        "plastic_nozzle_diameter": plastic_nozzle,
        "composite_nozzle_diameter": COMPOSITE_NOZZLE,
        "fiber_enabled": "1",
        "fiber_shared_nozzle": "1",
    }


def process_common() -> dict:
    return {
        "type": "process",
        "name": "TinManX1 FibreSeek process common",
        "from": "system",
        "instantiation": "false",
        "adaptive_layer_height": "0",
        "bottom_surface_pattern": "monotonic",
        "bottom_shell_layers": "3",
        "top_shell_layers": "4",
        "top_shell_thickness": "0.8",
        "bridge_flow": "0.95",
        "brim_width": "5",
        "brim_object_gap": "0.1",
        "print_sequence": "by layer",
        "default_acceleration": "1500",
        "top_surface_acceleration": "1200",
        "travel_acceleration": "3000",
        "inner_wall_acceleration": "1500",
        "outer_wall_acceleration": "1200",
        "wall_infill_order": "inner wall/outer wall/infill",
        "infill_direction": "45",
        "sparse_infill_density": "15%",
        "sparse_infill_pattern": "crosshatch",
        "initial_layer_acceleration": "500",
        "initial_layer_print_height": "0.2",
        "infill_wall_overlap": "20%",
        "ironing_type": "no ironing",
        "reduce_infill_retraction": "1",
        "filename_format": "{input_filename_base}_{nozzle_diameter[0]}n_{layer_height}mm_{filament_type[initial_tool]}_{printer_model}_{print_time}.gcode",
        "detect_overhang_wall": "1",
        "wall_loops": "3",
        "raft_layers": "0",
        "seam_position": "aligned",
        "skirt_distance": "2",
        "skirt_height": "1",
        "skirt_loops": "0",
        "minimum_sparse_infill_area": "15",
        "spiral_mode": "0",
        "enable_support": "0",
        "resolution": "0.012",
        "support_type": "normal(auto)",
        "support_style": "default",
        "support_top_z_distance": "0.2",
        "support_object_xy_distance": "0.35",
        "tree_support_branch_angle": "45",
        "tree_support_wall_count": "0",
        "detect_thin_wall": "0",
        "top_surface_pattern": "monotonicline",
        "initial_layer_speed": "35",
        "initial_layer_infill_speed": "45",
        "outer_wall_speed": "60",
        "inner_wall_speed": "90",
        "internal_solid_infill_speed": "90",
        "top_surface_speed": "55",
        "gap_infill_speed": "90",
        "sparse_infill_speed": "90",
        "travel_speed": "220",
        "travel_speed_z": "5",
        "enable_prime_tower": "0",
        "xy_hole_compensation": "0",
        "xy_contour_compensation": "0",
        "enable_arc_fitting": "0",
        "fiber_generate_perimeters": "0",
        "fiber_generate_infill": "0",
        "fiber_reinforcement_mode": "light",
    }


def plastic_process(nozzle: str, spec: dict) -> dict:
    layer = spec["layer"]
    width = spec["line_width"]
    return {
        "type": "process",
        "name": f"{layer}mm Plastic Only @FibreSeek Seeker 3 {nozzle} nozzle",
        "inherits": "TinManX1 FibreSeek process common",
        "from": "system",
        "setting_id": f"TMX-FS3-PROC-P{nozzle}",
        "instantiation": "true",
        "layer_height": layer,
        "first_layer_height": "0.2",
        "line_width": width,
        "outer_wall_line_width": width,
        "inner_wall_line_width": width,
        "sparse_infill_line_width": width,
        "internal_solid_infill_line_width": width,
        "top_surface_line_width": width,
        "support_line_width": width,
        "bridge_line_width": nozzle,
        "compatible_printers": compatible_process_printers(nozzle, fiber=False),
    }


def fiber_process(plastic_nozzle: str, spec: dict, mode_label: str, mode: dict, layup_payload: str = "{}") -> dict:
    width = spec["line_width"]
    return {
        "type": "process",
        "name": f"0.20mm Plastic + Continuous Fiber {mode_label} @FibreSeek Seeker 3 {plastic_nozzle}+{COMPOSITE_NOZZLE} nozzle",
        "inherits": "TinManX1 FibreSeek process common",
        "from": "system",
        "setting_id": f"TMX-FS3-PROC-X{plastic_nozzle}-{mode_label.upper()}",
        "instantiation": "true",
        "layer_height": "0.2",
        "first_layer_height": "0.2",
        "line_width": width,
        "outer_wall_line_width": width,
        "inner_wall_line_width": width,
        "sparse_infill_line_width": width,
        "internal_solid_infill_line_width": width,
        "top_surface_line_width": width,
        "support_line_width": width,
        "bridge_line_width": plastic_nozzle,
        "wall_loops": "3",
        "sparse_infill_density": "18%",
        "sparse_infill_pattern": "grid",
        "top_shell_layers": "4",
        "bottom_shell_layers": "3",
        "fiber_generate_perimeters": mode["generate_perimeters"],
        "fiber_generate_infill": mode["generate_infill"],
        "fiber_reinforcement_mode": mode["mode"],
        "fiber_start_layer": "4",
        "fiber_print_order_code": "1",
        "fiber_min_radius": "12",
        "fiber_max_arc_segment_length": "3",
        "fiber_start_length": "15",
        "fiber_slow_length": "10",
        "fiber_tension_length": "0",
        "fiber_tension_feedrate": "0",
        "fiber_tension_release_fraction": "0",
        "fiber_feedrate_percent": "100",
        "fiber_start_max_speed": "5",
        "fiber_start_min_speed": "3",
        "fiber_start_min_limit_speed": "3",
        "fiber_normal_max_speed": "30",
        "fiber_normal_min_speed": "5",
        "fiber_normal_min_limit_speed": "3",
        "fiber_finish_max_speed": "15",
        "fiber_finish_min_speed": "5",
        "fiber_finish_min_limit_speed": "3",
        "fiber_override_correction_speed": "0",
        "fiber_correction_move_speed": "2",
        "fiber_correction_move_feedrate_percent": "0",
        "fiber_after_cut_plastic_extrusion_multiplier": "0.72",
        "fiber_z_hop_after_cut": "0",
        "fiber_first_layer_flow_ratio": "0",
        "fiber_first_layer_line_width": "0",
        "fiber_first_layer_height": "0",
        "fiber_first_layer_speed_ratio": "0",
        "fiber_infill_pattern": "solid",
        "fiber_infill_density": "0",
        "fiber_infill_angles": "",
        "fiber_infill_source_policy": mode["infill_source"],
        "fiber_seam_position": "source",
        "fiber_seam_angle": "0",
        "fiber_line_width": COMPOSITE_LINE_WIDTH,
        "fiber_infill_spacing": mode["spacing"],
        "fiber_macro_layer_height": "0.2",
        "fiber_layer_step": mode["layer_step"],
        "fiber_min_route_length": "55",
        "fiber_perimeter_min_route_length": "55",
        "fiber_mechanical_min_route_length": "55",
        "fiber_perimeter_inset": "0.85",
        "fiber_infill_inset": "1.2",
        "fiber_print_speed": "30",
        "fiber_start_speed": "5",
        "fiber_max_routes_per_layer": mode["max_routes"],
        "fiber_routes_per_cut": mode["routes_per_cut"],
        "fiber_outer_perimeter_loops": "1",
        "fiber_inner_perimeter_loops": "1",
        "fiber_plastic_outer_loops_with_fiber": "2",
        "fiber_plastic_inner_loops_with_fiber": "0",
        "fiber_reinforcement_payload": layup_payload,
        "compatible_printers": compatible_process_printers(plastic_nozzle, fiber=True),
    }


def build_pack(layup_template: str = "none"):
    layup_payload = layup_payload_for_template(layup_template)
    if PACK_ROOT.exists():
        shutil.rmtree(PACK_ROOT)

    top = {
        "name": "TinManX1",
        "version": PACK_VERSION,
        "force_update": "0",
        "description": "TinManX1 FibreSeek Seeker 3 plastic and continuous-fiber profiles",
        "machine_model_list": [
            {"name": MACHINE_MODEL, "sub_path": f"machine/{MACHINE_MODEL}.json"}
        ],
        "process_list": [
            {"name": "TinManX1 FibreSeek process common", "sub_path": "process/TinManX1 FibreSeek process common.json"}
        ],
        "filament_list": [],
        "machine_list": [
            {"name": "TinManX1 FibreSeek machine common", "sub_path": "machine/TinManX1 FibreSeek machine common.json"}
        ],
    }

    write_json(PACK_ROOT / "machine" / f"{MACHINE_MODEL}.json", machine_model())
    write_json(PACK_ROOT / "machine" / "TinManX1 FibreSeek machine common.json", machine_common())
    write_json(PACK_ROOT / "process" / "TinManX1 FibreSeek process common.json", process_common())

    for nozzle, spec in PLASTIC_NOZZLES.items():
        m = plastic_machine(nozzle, spec)
        path = f"machine/{m['name']}.json"
        top["machine_list"].append({"name": m["name"], "sub_path": path})
        write_json(PACK_ROOT / path, m)

        cm = composite_machine(nozzle, spec)
        cpath = f"machine/{cm['name']}.json"
        top["machine_list"].append({"name": cm["name"], "sub_path": cpath})
        write_json(PACK_ROOT / cpath, cm)

        p = plastic_process(nozzle, spec)
        ppath = f"process/{p['name']}.json"
        top["process_list"].append({"name": p["name"], "sub_path": ppath})
        write_json(PACK_ROOT / ppath, p)

        for label, mode in FIBER_MODES.items():
            fp = fiber_process(nozzle, spec, label, mode, layup_payload)
            fpath = f"process/{fp['name']}.json"
            top["process_list"].append({"name": fp["name"], "sub_path": fpath})
            write_json(PACK_ROOT / fpath, fp)

    for material, values in MATERIALS.items():
        base = filament_base(material, values)
        base_path = f"filament/{base['name']}.json"
        top["filament_list"].append({"name": base["name"], "sub_path": base_path})
        write_json(PACK_ROOT / base_path, base)

        pf = plastic_filament(material)
        pf_path = f"filament/{pf['name']}.json"
        top["filament_list"].append({"name": pf["name"], "sub_path": pf_path})
        write_json(PACK_ROOT / pf_path, pf)

        for fiber in CONTINUOUS_FIBERS:
            cf = composite_filament(material, values, fiber)
            cf_path = f"filament/{cf['name']}.json"
            top["filament_list"].append({"name": cf["name"], "sub_path": cf_path})
            write_json(PACK_ROOT / cf_path, cf)

    write_json(PROFILE_ROOT / "TinManX1.json", top)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fiber-layup-template",
        choices=["none", "balanced", "perimeter-shell", "tetragrid-core", "first-layer-off-tetragrid"],
        default="none",
        help="Optional advanced layup payload template to write into continuous-fiber process profiles.",
    )
    args = parser.parse_args()
    build_pack(args.fiber_layup_template)
