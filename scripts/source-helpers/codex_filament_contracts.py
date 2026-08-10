#!/usr/bin/env python3
"""Apply the reviewed Bambu/Micro Swiss contract to Codex filament presets."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_CONTRACT = SCRIPT_DIR.parent / "profile-contracts" / "bambu_studio_2.7.1_filament_contract.json"

# These are material-behaviour settings. Printer start/end G-code, identity,
# pricing, colour and density deliberately remain owned by the Codex preset.
REFERENCE_FIELDS = (
    "filament_flow_ratio",
    "filament_max_volumetric_speed",
    "nozzle_temperature",
    "nozzle_temperature_initial_layer",
    "nozzle_temperature_range_low",
    "nozzle_temperature_range_high",
    "cool_plate_temp",
    "cool_plate_temp_initial_layer",
    "eng_plate_temp",
    "eng_plate_temp_initial_layer",
    "hot_plate_temp",
    "hot_plate_temp_initial_layer",
    "textured_plate_temp",
    "textured_plate_temp_initial_layer",
    "fan_min_speed",
    "fan_max_speed",
    "fan_cooling_layer_time",
    "full_fan_speed_layer",
    "overhang_fan_speed",
    "overhang_fan_threshold",
    "slow_down_layer_time",
    "slow_down_min_speed",
    "slow_down_for_layer_cooling",
    "close_fan_the_first_x_layers",
    "reduce_fan_stop_start_freq",
    "additional_cooling_fan_speed",
    "filament_shrink",
    "filament_shrinkage_compensation_z",
)

MICRO_SWISS_BUCKETS = {
    "Bambu X1C HF",
    "Creality K2 Plus",
    "Elegoo Centauri",
    "Prusa Core One",
    "Qidi X-Plus 4",
    "RatRig V-Core 4",
    "Sovol SV08 MAX",
}

ACTIVE_CHAMBER_BUCKETS = {
    "Bambu H2D",
    "Creality K2 Plus",
    "Prusa Core One",
    "Qidi X-Plus 4",
    "RatRig V-Core 4",
    "Sovol SV08 MAX",
}

PASSIVE_CHAMBER_BUCKETS = {
    "Bambu X1C HF",
    "Elegoo Centauri",
    "Snapmaker U1",
}

NO_ACTIVE_CHAMBER_MATERIALS = {
    "HT-PLA-CF",
    "HT-PLA-GF",
    "PEBA",
    "PLA",
    "PLA-CF",
    "PLA-GF",
    "PolySmooth",
    "TPU",
}

# Targets here cover families without an exact heated-H2D reference and retain
# the field-validated PCTG/PET-CF values established on the user's machines.
FALLBACK_CHAMBER_TARGETS = {
    "ABS": 60,
    "ABS-CF": 60,
    "ABS-GF": 60,
    "ASA": 60,
    "ASA-CF": 60,
    "HIPS": 50,
    "PA": 55,
    "PA-CF": 55,
    "PA-GF": 55,
    "PA12-CF": 55,
    "PA6-CF": 55,
    "PA6-GF": 55,
    "PA612-CF": 55,
    "PA612-ESD": 55,
    "PAHT": 55,
    "PAHT-CF": 55,
    "PAKV": 55,
    "PC": 55,
    "PC+PBT": 55,
    "PC-CF": 55,
    "PC-PBT": 55,
    "PCTG": 45,
    "PCTG-CF": 45,
    "PET-CF": 50,
    "PET-GF": 50,
    "PPA-CF": 60,
    "PPS": 60,
    "PPS-CF": 60,
    "PPS-GF": 60,
}

# This tune came from physical Plus 4 prints and intentionally wins over the
# much faster Fiberon Bambu preset on every non-H2D machine.
FIBERON_PET_CF_FIELD_TUNE = {
    "filament_flow_ratio": ["1.00"],
    "filament_max_volumetric_speed": ["3.2"],
    "nozzle_temperature": ["280"],
    "nozzle_temperature_initial_layer": ["285"],
    "nozzle_temperature_range_low": ["260"],
    "nozzle_temperature_range_high": ["300"],
    "fan_min_speed": ["0"],
    "fan_max_speed": ["20"],
    "overhang_fan_speed": ["35"],
    "overhang_fan_threshold": ["25%"],
    "slow_down_layer_time": ["25"],
    "slow_down_min_speed": ["6"],
    "enable_pressure_advance": ["1"],
    "pressure_advance": ["0.028"],
}

# A plate-sized 0.6 mm X1C print exposed two problems in the generic Bambu
# baseline: the fixed PA value overrode flow-dynamics calibration, and the
# first cooled layer remained too soft at the perimeter. Keep the conservative
# Bambu flow ceiling while applying the measured X1C correction.
X1C_PCTG_FIELD_TUNE = {
    "nozzle_temperature": ["250"],
    "nozzle_temperature_initial_layer": ["255"],
    "fan_min_speed": ["20"],
    "close_fan_the_first_x_layers": ["2"],
    "enable_pressure_advance": ["0"],
    "pressure_advance": ["0.03"],
}


def load_contract(path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    return json.loads(path.read_text())


def scalar(value: Any, high_flow: bool = False) -> str | None:
    if isinstance(value, list):
        if not value:
            return None
        return str(value[-1] if high_flow and len(value) > 1 else value[0])
    if value is None:
        return None
    return str(value)


def vector(value: Any, high_flow: bool = False) -> list[str]:
    selected = scalar(value, high_flow=high_flow)
    return [] if selected is None else [selected]


def positive_int(value: Any) -> int:
    selected = scalar(value)
    if selected is None:
        return 0
    try:
        return max(0, int(round(float(selected))))
    except ValueError:
        return 0


def reference_for_bucket(
    contract: dict[str, Any],
    entry: dict[str, Any],
    bucket: str,
) -> dict[str, Any] | None:
    if bucket == "Bambu H2D":
        name = entry.get("h2d") or entry.get("x1c")
    else:
        name = entry.get("x1c") or entry.get("h2d")
    return (contract.get("references") or {}).get(name) if name else None


def chamber_target(material: str, entry: dict[str, Any], contract: dict[str, Any]) -> int:
    if material in NO_ACTIVE_CHAMBER_MATERIALS:
        return 0
    if material in {"PCTG", "PCTG-CF", "PET-CF"}:
        return FALLBACK_CHAMBER_TARGETS[material]
    h2d_name = entry.get("h2d")
    h2d = (contract.get("references") or {}).get(h2d_name, {})
    target = positive_int((h2d.get("values") or {}).get("chamber_temperatures"))
    if entry.get("mode") == "exact" and h2d_name:
        return target
    return target or FALLBACK_CHAMBER_TARGETS.get(material, 0)


def apply_contract(
    profile: dict[str, Any],
    material: str,
    manufacturer: str,
    bucket: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    """Return a normalized profile without changing Codex-owned identity data."""
    data = copy.deepcopy(profile)
    entry = (contract.get("profiles") or {}).get(f"{material}|{manufacturer}", {})
    reference = reference_for_bucket(contract, entry, bucket)

    if entry.get("mode") == "exact" and reference:
        values = reference.get("values") or {}
        if bucket == "Bambu H2D":
            for key in REFERENCE_FIELDS:
                if key in values:
                    data[key] = copy.deepcopy(values[key])
        else:
            high_flow = bucket in MICRO_SWISS_BUCKETS
            for key in REFERENCE_FIELDS:
                if key in values:
                    data[key] = vector(values[key], high_flow=high_flow)

    if material == "PET-CF" and manufacturer == "Fiberon" and bucket != "Bambu H2D":
        data.update(copy.deepcopy(FIBERON_PET_CF_FIELD_TUNE))

    if material == "PCTG" and manufacturer == "Generic" and bucket == "Bambu X1C HF":
        data.update(copy.deepcopy(X1C_PCTG_FIELD_TUNE))

    target = chamber_target(material, entry, contract) if bucket in ACTIVE_CHAMBER_BUCKETS else 0
    active = "1" if target > 0 else "0"
    data["activate_chamber_temp_control"] = [active]
    data["chamber_temperature"] = [str(target)]
    data["chamber_temperatures"] = [str(target)]
    return data
