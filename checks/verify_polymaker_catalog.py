#!/usr/bin/env python3
"""Validate the bundled TinManX1 Polymaker material catalog."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "resources" / "profiles" / "polymaker" / "polymaker_material_catalog.json"

EXPECTED_MATERIALS = {
    "Fiberon ASA-CF08",
    "Fiberon PA12-CF10",
    "Fiberon PA6-CF20",
    "Fiberon PA6-GF25",
    "Fiberon PA612-CF15",
    "Fiberon PA612-ESD",
    "Fiberon PET-CF17",
    "Fiberon PET-GF15",
    "Fiberon PETG-ESD",
    "Fiberon PETG-rCF08",
    "Fiberon PPS-CF10",
    "Fiberon PPS-GF20",
    "Panchroma CoPE",
    "Panchroma PLA",
    "Panchroma PLA Celestial",
    "Panchroma PLA Galaxy",
    "Panchroma PLA Glow",
    "Panchroma PLA Luminous",
    "Panchroma PLA Marble",
    "Panchroma PLA Matte",
    "Panchroma PLA Metallic",
    "Panchroma PLA Neon",
    "Panchroma PLA Satin",
    "Panchroma PLA Silk",
    "Panchroma PLA Starlight",
    "Panchroma PLA Translucent",
    "Panchroma PLA UV Shift",
    "PolyCast",
    "PolyFlex TPU95",
    "PolyFlex TPU95-HF",
    "PolyLite ABS",
    "PolyLite CosPLA",
    "PolyLite LW-PLA",
    "PolyLite PC",
    "PolyLite PETG",
    "PolyLite PETG Translucent",
    "PolyLite PLA",
    "PolyLite PLA Galaxy",
    "PolyLite PLA Glow",
    "PolyLite PLA Luminous",
    "PolyLite PLA Neon",
    "PolyLite PLA Pro",
    "PolyLite PLA Pro Metallic",
    "PolyLite PLA Starlight",
    "PolyLite PLA Translucent",
    "PolyLite PLA-CF",
    "PolyMax PC",
    "PolyMax PETG",
    "PolyMax PLA",
    "PolySmooth",
    "PolySupport",
    "PolySupport for PA12",
    "PolyTerra PLA",
    "PolyTerra PLA Marble",
    "PolyTerra PLA+",
    "Polymaker ABS Max",
    "Polymaker ABS Pro",
    "Polymaker ABS Pro Galaxy",
    "Polymaker ASA",
    "Polymaker HT-PLA",
    "Polymaker HT-PLA-GF",
    "Polymaker PETG",
    "Polymaker PETG Galaxy",
    "Polymaker PLA",
    "Polymaker PLA Pro",
    "Polymaker PLA Pro Metallic",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def numeric(settings: dict, key: str) -> float:
    try:
        return float(settings[key])
    except (KeyError, TypeError, ValueError) as exc:
        fail(f"{settings.get('source', {}).get('path', '<unknown>')} has invalid {key}: {exc}")


def abrasive(material: str) -> bool:
    lowered = material.lower()
    return any(token in lowered for token in ("-cf", "-gf", " rcf", "glow", "luminous"))


def main() -> int:
    catalog = json.loads(CATALOG.read_text())
    materials = {entry["material"] for entry in catalog.get("materials", [])}
    if materials != EXPECTED_MATERIALS:
        fail(f"material set mismatch: missing={sorted(EXPECTED_MATERIALS - materials)} extra={sorted(materials - EXPECTED_MATERIALS)}")
    if catalog.get("materialCount") != len(EXPECTED_MATERIALS):
        fail(f"catalog materialCount should be {len(EXPECTED_MATERIALS)}, got {catalog.get('materialCount')}")
    if not catalog.get("sourceIndexUpdatedAt"):
        fail("catalog missing sourceIndexUpdatedAt")

    for entry in catalog["materials"]:
        material = entry["material"]
        if not entry.get("systemName", "").endswith(" @Codex"):
            fail(f"{material} systemName should end with @Codex")
        settings = entry.get("settings") or {}
        source = settings.get("source") or {}
        for key in ("slicer", "brand", "model", "path", "updatedAt", "indexUpdatedAt"):
            if not source.get(key):
                fail(f"{material} source missing {key}")
        price_source = settings.get("priceSource") or {}
        for key in ("sourceUrl", "productHandle", "variantTitle", "spoolWeightKg", "retailPriceUsd", "costUsdPerKg"):
            if not price_source.get(key):
                fail(f"{material} priceSource missing {key}")
        for key in (
            "filament_density",
            "filament_cost",
            "filament_flow_ratio",
            "filament_max_volumetric_speed",
            "nozzle_temperature",
            "nozzle_temperature_initial_layer",
            "hot_plate_temp",
            "textured_plate_temp",
            "fan_max_speed",
        ):
            numeric(settings, key)
        if numeric(settings, "nozzle_temperature") <= 0:
            fail(f"{material} nozzle temperature must be positive")
        if numeric(settings, "filament_cost") <= 0:
            fail(f"{material} filament cost must be positive")
        if abrasive(material) and numeric(settings, "required_nozzle_HRC") < 40:
            fail(f"{material} should require a hardened nozzle")

    print(
        "Polymaker catalog verification passed: "
        f"{len(EXPECTED_MATERIALS)} materials from official index {catalog['sourceIndexUpdatedAt']}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
