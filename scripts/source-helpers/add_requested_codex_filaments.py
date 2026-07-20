#!/usr/bin/env python3
"""Seed requested Codex filament families into the live TinManX1 catalog."""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
SCRIPT_DIR = Path(__file__).resolve().parent
NORMALIZER_PATH = SCRIPT_DIR / "normalize_codex_filament_catalog.py"


def load_normalizer() -> Any:
    spec = importlib.util.spec_from_file_location("normalize_codex_filament_catalog", NORMALIZER_PATH)
    if spec is None or spec.loader is None:
        raise SystemExit(f"could not load normalizer: {NORMALIZER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


NORMALIZER = load_normalizer()
TARGET_BUCKETS: dict[str, tuple[str, ...]] = NORMALIZER.TARGET_BUCKETS
SYSTEM_SUFFIX = NORMALIZER.SYSTEM_SUFFIX
BLACK = NORMALIZER.BLACK


@dataclass(frozen=True)
class MaterialSpec:
    material: str
    manufacturer: str
    template_prefixes: tuple[str, ...]
    settings: dict[str, list[str] | str]


MATERIALS = [
    MaterialSpec(
        material="PAKV",
        manufacturer="Filamatrix",
        template_prefixes=("PA-CF Codex-Fiberon", "PA Codex-Generic"),
        settings={
            "nozzle_temperature": ["255"],
            "nozzle_temperature_initial_layer": ["255"],
            "nozzle_temperature_range_low": ["240"],
            "nozzle_temperature_range_high": ["270"],
            "hot_plate_temp": ["75"],
            "hot_plate_temp_initial_layer": ["75"],
            "textured_plate_temp": ["75"],
            "textured_plate_temp_initial_layer": ["75"],
            "eng_plate_temp": ["75"],
            "eng_plate_temp_initial_layer": ["75"],
            "activate_chamber_temp_control": ["1"],
            "chamber_temperature": ["45"],
            "fan_min_speed": ["0"],
            "fan_max_speed": ["20"],
            "overhang_fan_speed": ["20"],
            "filament_flow_ratio": ["1.00"],
            "filament_max_volumetric_speed": ["8"],
            "filament_cost": ["69.99"],
            "filament_density": ["1.08"],
            "required_nozzle_HRC": ["40"],
            "temperature_vitrification": ["80"],
            "slow_down_for_layer_cooling": ["1"],
            "slow_down_min_speed": ["10"],
        },
    ),
    MaterialSpec(
        material="PET-CF",
        manufacturer="Elegoo",
        template_prefixes=("PET-CF Codex-Fiberon", "PETG-CF Codex-Generic", "PETG-CF Codex-Fiberon"),
        settings={
            "nozzle_temperature": ["275"],
            "nozzle_temperature_initial_layer": ["275"],
            "nozzle_temperature_range_low": ["260"],
            "nozzle_temperature_range_high": ["290"],
            "hot_plate_temp": ["100"],
            "hot_plate_temp_initial_layer": ["100"],
            "textured_plate_temp": ["100"],
            "textured_plate_temp_initial_layer": ["100"],
            "eng_plate_temp": ["100"],
            "eng_plate_temp_initial_layer": ["100"],
            "activate_chamber_temp_control": ["1"],
            "chamber_temperature": ["50"],
            "fan_min_speed": ["0"],
            "fan_max_speed": ["20"],
            "overhang_fan_speed": ["20"],
            "filament_flow_ratio": ["1.03"],
            "filament_max_volumetric_speed": ["6"],
            "filament_cost": ["29.99"],
            "filament_density": ["1.34"],
            "required_nozzle_HRC": ["40"],
            "temperature_vitrification": ["80"],
            "slow_down_for_layer_cooling": ["1"],
            "slow_down_min_speed": ["8"],
        },
    ),
    MaterialSpec(
        material="PC+PBT",
        manufacturer="Push Plastic",
        template_prefixes=("PC-PBT Codex-Push Plastic", "PC Codex-Generic"),
        settings={
            "nozzle_temperature": ["250"],
            "nozzle_temperature_initial_layer": ["250"],
            "nozzle_temperature_range_low": ["235"],
            "nozzle_temperature_range_high": ["255"],
            "hot_plate_temp": ["115"],
            "hot_plate_temp_initial_layer": ["115"],
            "textured_plate_temp": ["115"],
            "textured_plate_temp_initial_layer": ["115"],
            "eng_plate_temp": ["115"],
            "eng_plate_temp_initial_layer": ["115"],
            "activate_chamber_temp_control": ["1"],
            "chamber_temperature": ["55"],
            "fan_min_speed": ["10"],
            "fan_max_speed": ["25"],
            "overhang_fan_speed": ["25"],
            "filament_flow_ratio": ["1.00"],
            "filament_max_volumetric_speed": ["6"],
            "filament_cost": ["39.99"],
            "filament_density": ["1.20"],
            "required_nozzle_HRC": ["0"],
            "temperature_vitrification": ["110"],
            "slow_down_for_layer_cooling": ["1"],
            "slow_down_min_speed": ["10"],
        },
    ),
    MaterialSpec(
        material="HT-PLA-GF",
        manufacturer="Polymaker",
        template_prefixes=("PLA-GF Codex-Polymaker", "PLA Codex-Polymaker"),
        settings={
            "nozzle_temperature": ["220"],
            "nozzle_temperature_initial_layer": ["220"],
            "nozzle_temperature_range_low": ["210"],
            "nozzle_temperature_range_high": ["230"],
            "hot_plate_temp": ["50"],
            "hot_plate_temp_initial_layer": ["50"],
            "textured_plate_temp": ["50"],
            "textured_plate_temp_initial_layer": ["50"],
            "eng_plate_temp": ["50"],
            "eng_plate_temp_initial_layer": ["50"],
            "activate_chamber_temp_control": ["0"],
            "chamber_temperature": ["0"],
            "fan_min_speed": ["100"],
            "fan_max_speed": ["100"],
            "overhang_fan_speed": ["100"],
            "filament_flow_ratio": ["1.04"],
            "filament_max_volumetric_speed": ["15"],
            "filament_cost": ["29.99"],
            "filament_density": ["1.34"],
            "required_nozzle_HRC": ["40"],
            "temperature_vitrification": ["60"],
            "filament_retraction_length": ["1"],
            "filament_retraction_speed": ["30"],
        },
    ),
    MaterialSpec(
        material="HT-PLA-CF",
        manufacturer="Polymaker",
        template_prefixes=("PLA-CF Codex-Polymaker", "PLA Codex-Polymaker"),
        settings={
            "nozzle_temperature": ["225"],
            "nozzle_temperature_initial_layer": ["225"],
            "nozzle_temperature_range_low": ["190"],
            "nozzle_temperature_range_high": ["230"],
            "hot_plate_temp": ["55"],
            "hot_plate_temp_initial_layer": ["55"],
            "textured_plate_temp": ["55"],
            "textured_plate_temp_initial_layer": ["55"],
            "eng_plate_temp": ["0"],
            "eng_plate_temp_initial_layer": ["0"],
            "activate_chamber_temp_control": ["0"],
            "chamber_temperature": ["0"],
            "fan_min_speed": ["100"],
            "fan_max_speed": ["100"],
            "overhang_fan_speed": ["100"],
            "filament_flow_ratio": ["0.99"],
            "filament_max_volumetric_speed": ["15"],
            "filament_cost": ["29.99"],
            "filament_density": ["1.29"],
            "required_nozzle_HRC": ["40"],
            "temperature_vitrification": ["64"],
            "filament_retraction_length": ["1"],
            "filament_retraction_speed": ["30"],
            "description": (
                "TinManX1 Codex Polymaker HT-PLA-CF working profile; "
                "baseline=Polymaker PolyLite PLA-CF official settings with "
                "HT-PLA material naming requested for TinManX1."
            ),
            "filament_notes": [
                "Polymaker currently publishes HT-PLA and HT-PLA-GF in the HT family; this Codex HT-PLA-CF preset uses Polymaker PLA-CF print settings with a conservative 15 mm3/s volumetric cap."
            ],
            "polymaker_source_material": ["PolyLite PLA-CF"],
            "polymaker_source_preset_path": ["TinManX1 Codex profile derived from the installed PolyLite PLA-CF Codex profile"],
            "filament_price_source_url": ["https://shop.polymaker.com/products/polylite-pla-cf"],
            "filament_price_source_variant": ["1.75mm / 1kg / Black"],
        },
    ),
    MaterialSpec(
        material="PEBA",
        manufacturer="SainSmart",
        template_prefixes=("PEBA Codex-SainSmart", "TPU Codex-Polymaker", "PA Codex-Generic"),
        settings={
            "nozzle_temperature": ["230"],
            "nozzle_temperature_initial_layer": ["230"],
            "nozzle_temperature_range_low": ["220"],
            "nozzle_temperature_range_high": ["240"],
            "hot_plate_temp": ["50"],
            "hot_plate_temp_initial_layer": ["50"],
            "textured_plate_temp": ["40"],
            "textured_plate_temp_initial_layer": ["40"],
            "eng_plate_temp": ["30"],
            "eng_plate_temp_initial_layer": ["30"],
            "activate_chamber_temp_control": ["0"],
            "chamber_temperature": ["0"],
            "fan_min_speed": ["15"],
            "fan_max_speed": ["25"],
            "overhang_fan_speed": ["35"],
            "filament_flow_ratio": ["1.03"],
            "filament_max_volumetric_speed": ["5.5"],
            "filament_cost": ["69"],
            "filament_density": ["1"],
            "required_nozzle_HRC": ["0"],
            "temperature_vitrification": ["110"],
            "slow_down_for_layer_cooling": ["1"],
            "slow_down_min_speed": ["10"],
        },
    ),
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def stable_ids(name: str) -> tuple[str, str]:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"codex-{digest[:12]}", f"CODX{digest[:8].upper()}"


def system_name(spec: MaterialSpec, bucket: str) -> str:
    return f"{spec.material} Codex-{spec.manufacturer} - {bucket}{SYSTEM_SUFFIX}"


def find_template(filament_dir: Path, spec: MaterialSpec, bucket: str) -> dict[str, Any]:
    attempted: list[Path] = []
    for prefix in spec.template_prefixes:
        path = filament_dir / f"{prefix} - {bucket}{SYSTEM_SUFFIX}.json"
        attempted.append(path)
        if path.is_file():
            return load_json(path)
    attempted_text = "\n  ".join(str(path) for path in attempted)
    raise SystemExit(f"missing template for {spec.material} / {bucket}:\n  {attempted_text}")


def generated_profile(filament_dir: Path, spec: MaterialSpec, bucket: str) -> tuple[Path, dict[str, Any]]:
    name = system_name(spec, bucket)
    setting_id, filament_id = stable_ids(name)
    profile = copy.deepcopy(find_template(filament_dir, spec, bucket))
    profile.update(spec.settings)
    profile["name"] = name
    profile["filament_settings_id"] = [name]
    profile["filament_vendor"] = ["Codex"]
    profile["filament_type"] = [spec.material]
    profile["default_filament_colour"] = [BLACK]
    profile["filament_colour"] = [BLACK]
    profile["from"] = "system"
    profile["type"] = "filament"
    profile["instantiation"] = "true"
    profile["setting_id"] = setting_id
    profile["filament_id"] = filament_id
    profile["is_custom_defined"] = "0"
    return filament_dir / f"{name}.json", profile


def install(app_support: Path, dry_run: bool) -> list[Path]:
    filament_dir = app_support / "system/Codex/filament"
    if not filament_dir.is_dir():
        raise SystemExit(f"missing Codex filament catalog: {filament_dir}")

    generated: list[tuple[Path, dict[str, Any]]] = []
    for spec in MATERIALS:
        for bucket in TARGET_BUCKETS:
            generated.append(generated_profile(filament_dir, spec, bucket))

    if not dry_run:
        for path, profile in generated:
            write_json(path, profile)
    return [path for path, _ in generated]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths = install(args.app_support, args.dry_run)
    verb = "would seed" if args.dry_run else "seeded"
    print(f"{verb} {len(paths)} requested Codex filament profiles")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
