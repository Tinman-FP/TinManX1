#!/usr/bin/env python3
"""Generate and install current Polymaker Universal Codex filament profiles.

The generated catalog is based on Polymaker's official preset index.  The
repo carries a snapshot so live installs do not depend on the network, while
`--refresh-catalog` can be used to update the snapshot from the official
Polymaker preset repository.
"""

from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
OFFICIAL_REPO_RAW = "https://raw.githubusercontent.com/Polymaker3D/Polymaker-Preset/main"
POLYMAKER_SHOP_PRODUCTS_URL = "https://shop.polymaker.com/products.json?limit=250"
POLYMAKER_SHOP_BASE_URL = "https://shop.polymaker.com/products"
CATALOG_PATH = Path("resources/profiles/polymaker/polymaker_material_catalog.json")
GENERATED_MARKER = "TinManX1 Codex Polymaker official catalog"

PROFILE_FIELDS = [
    "default_filament_colour",
    "filament_cost",
    "filament_density",
    "filament_flow_ratio",
    "filament_is_support",
    "filament_max_volumetric_speed",
    "filament_soluble",
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
    "chamber_temperature",
    "chamber_temperatures",
    "fan_min_speed",
    "fan_max_speed",
    "overhang_fan_speed",
    "overhang_fan_threshold",
    "required_nozzle_HRC",
    "temperature_vitrification",
    "filament_notes",
    "filament_retraction_length",
    "filament_retraction_speed",
    "filament_deretraction_speed",
]

SOURCE_PRIORITY = [
    ("OrcaSlicer", "Snapmaker", "U1"),
    ("Orcaslicer", "BBL", "X1"),
    ("OrcaSlicer", "", ""),
    ("Orcaslicer", "", ""),
    ("BambuStudio", "BBL", "X2D"),
    ("BambuStudio", "BBL", "P2S"),
    ("BambuStudio", "BBL", "H2D"),
    ("BambuStudio", "", ""),
    ("PrusaSlicer", "", ""),
    ("ElegooSlicer", "", ""),
]

SHOP_PRODUCT_HANDLES = {
    "Fiberon ASA-CF08": "fiberon-asa-cf08",
    "Fiberon PA12-CF10": "fiberon-pa12-cf10",
    "Fiberon PA6-CF20": "fiberon-pa6-cf20",
    "Fiberon PA6-GF25": "fiberon-pa6-gf25",
    "Fiberon PA612-CF15": "fiberon-pa612-cf",
    "Fiberon PA612-ESD": "fiberon-pa612-esd",
    "Fiberon PET-CF17": "fiberon-pet-cf17",
    "Fiberon PET-GF15": "fiberon-pet-gf15",
    "Fiberon PETG-ESD": "fiberon-petg-esd",
    "Fiberon PETG-rCF08": "fiberon-petg-rcf08",
    "Fiberon PPS-CF10": "fiberon-pps-cf10",
    "Fiberon PPS-GF20": "fiberon-pps-gf20",
    "Panchroma CoPE": "panchroma-cope",
    "Panchroma PLA": "panchroma-pla",
    "Panchroma PLA Celestial": "panchroma-celestial",
    "Panchroma PLA Galaxy": "panchroma-galaxy",
    "Panchroma PLA Glow": "panchroma-glow",
    "Panchroma PLA Luminous": "panchroma-luminous",
    "Panchroma PLA Marble": "panchroma-marble",
    "Panchroma PLA Matte": "panchroma-matte",
    "Panchroma PLA Metallic": "panchroma-metallic",
    "Panchroma PLA Neon": "panchroma-neon",
    "Panchroma PLA Satin": "panchroma-satin",
    "Panchroma PLA Silk": "panchroma-silk",
    "Panchroma PLA Starlight": "panchroma-starlight",
    "Panchroma PLA Translucent": "panchroma-translucent",
    "Panchroma PLA UV Shift": "panchroma-uv-shift",
    "PolyCast": "polycast",
    "PolyFlex TPU95": "polyflex-tpu95",
    "PolyFlex TPU95-HF": "polyflex-tpu95-hf",
    "PolyLite ABS": "polylite-abs",
    "PolyLite CosPLA": "polylite-cospla",
    "PolyLite LW-PLA": "polylite-lw-pla",
    "PolyLite PC": "polylite-pc",
    "PolyLite PETG": "polymaker-petg",
    "PolyLite PETG Translucent": "polylite-translucent-petg",
    "PolyLite PLA": "polylite-pla",
    "PolyLite PLA Galaxy": "panchroma-galaxy",
    "PolyLite PLA Glow": "panchroma-glow",
    "PolyLite PLA Luminous": "panchroma-luminous",
    "PolyLite PLA Neon": "panchroma-neon",
    "PolyLite PLA Pro": "polylite-pla-pro",
    "PolyLite PLA Pro Metallic": "polylite-metallic-pla-pro",
    "PolyLite PLA Starlight": "panchroma-starlight",
    "PolyLite PLA Translucent": "panchroma-translucent",
    "PolyLite PLA-CF": "polylite-pla-cf",
    "PolyMax PC": "polymax-pc",
    "PolyMax PETG": "polymax-petg",
    "PolyMax PLA": "polymax-pla",
    "PolySmooth": "polysmooth",
    "PolySupport": "polysupport-for-pla",
    "PolySupport for PA12": "polysupport",
    "PolyTerra PLA": "panchroma-matte",
    "PolyTerra PLA Marble": "panchroma-marble",
    "PolyTerra PLA+": "polylite-pla-pro",
    "Polymaker ABS Max": "polymaker-abs-max",
    "Polymaker ABS Pro": "polymaker-abs-pro",
    "Polymaker ABS Pro Galaxy": "polymaker-abs-pro",
    "Polymaker ASA": "polymaker-asa",
    "Polymaker HT-PLA": "polymaker-ht-pla",
    "Polymaker HT-PLA-GF": "polymaker-ht-pla-gf",
    "Polymaker PETG": "polymaker-petg",
    "Polymaker PETG Galaxy": "polymaker-petg",
    "Polymaker PLA": "polylite-pla",
    "Polymaker PLA Pro": "polymaker-pla-pro",
    "Polymaker PLA Pro Metallic": "polylite-metallic-pla-pro",
}


@dataclass
class InstallResult:
    system_profiles: list[Path]
    user_profiles: list[Path]
    user_infos: list[Path]
    enabled_added: int
    backup_path: Path | None


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any], *, indent: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=True) + "\n")


def official_json(path: str) -> Any:
    with urlopen(f"{OFFICIAL_REPO_RAW}/{quote(path)}", timeout=45) as response:
        return json.load(response)


def shop_products_by_handle() -> dict[str, dict[str, Any]]:
    with urlopen(POLYMAKER_SHOP_PRODUCTS_URL, timeout=45) as response:
        products = json.load(response)["products"]
    return {product["handle"]: product for product in products}


def variant_price_usd(variant: dict[str, Any]) -> float:
    price = float(variant["price"])
    return price / 100.0 if price > 1000 else price


def variant_weight_kg(variant: dict[str, Any]) -> float | None:
    title = str(variant.get("title") or "")
    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)\s*kg\b", title, flags=re.IGNORECASE)
    if not match:
        return None
    return float(match.group(1))


def variant_matches_material(material: str, variant: dict[str, Any]) -> bool:
    title = str(variant.get("title") or "").lower()
    material_lower = material.lower()
    if "1.75mm" not in title:
        return False
    if "galaxy" in material_lower and "galaxy" not in title:
        return False
    if "marble" in material_lower and "marble" not in title:
        return False
    if "metallic" in material_lower and "metallic" not in title:
        return False
    if "translucent" in material_lower and "translucent" not in title and "clear" not in title:
        return False
    if "uv shift" in material_lower and "uv shift" not in title:
        return False
    return True


def current_shop_price_source(material: str, products: dict[str, dict[str, Any]]) -> dict[str, Any]:
    handle = SHOP_PRODUCT_HANDLES.get(material)
    if not handle:
        raise SystemExit(f"no Polymaker shop handle mapped for {material}")
    product = products.get(handle)
    if not product:
        raise SystemExit(f"Polymaker shop feed missing handle {handle} for {material}")

    candidates = [
        variant
        for variant in product.get("variants", [])
        if variant_matches_material(material, variant) and variant_weight_kg(variant)
    ]
    if not candidates:
        candidates = [
            variant
            for variant in product.get("variants", [])
            if "1.75mm" in str(variant.get("title") or "").lower() and variant_weight_kg(variant)
        ]
    if not candidates:
        raise SystemExit(f"no priced 1.75mm spool variant found for {material} ({handle})")

    # Prefer real 1 kg retail spools. If the product is only sold as 0.5 kg or
    # 0.75 kg, convert that listed spool to dollars/kg instead of using bulk 3 kg
    # prices, matching the user's 1 kg-spool costing assumption.
    candidates.sort(
        key=lambda variant: (
            0 if abs((variant_weight_kg(variant) or 0) - 1.0) < 0.001 else 1,
            0 if (variant_weight_kg(variant) or 0) <= 1.0 else 1,
            abs((variant_weight_kg(variant) or 0) - 1.0),
            0 if variant.get("available") else 1,
            variant_price_usd(variant),
        )
    )
    variant = candidates[0]
    weight = variant_weight_kg(variant) or 1.0
    retail_price = variant_price_usd(variant)
    return {
        "source": "Polymaker shop current product feed",
        "sourceUrl": f"{POLYMAKER_SHOP_BASE_URL}/{handle}",
        "feedUrl": POLYMAKER_SHOP_PRODUCTS_URL,
        "productHandle": handle,
        "productTitle": product.get("title", ""),
        "variantTitle": variant.get("title", ""),
        "variantAvailable": bool(variant.get("available")),
        "spoolWeightKg": f"{weight:g}",
        "retailPriceUsd": f"{retail_price:.2f}",
        "costUsdPerKg": f"{retail_price / weight:.2f}",
    }


def apply_current_shop_price(material: str, settings: dict[str, Any], products: dict[str, dict[str, Any]]) -> None:
    price_source = current_shop_price_source(material, products)
    settings["filament_cost"] = first_numeric(price_source["costUsdPerKg"], "0")
    settings["priceSource"] = price_source


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def first_value(value: Any, fallback: str = "0") -> str:
    for item in as_list(value):
        if item is None:
            continue
        text = str(item)
        if text and text.lower() != "nil":
            return text
    return fallback


def first_numeric(value: Any, fallback: str = "0") -> str:
    raw = first_value(value, fallback)
    try:
        number = float(raw)
    except ValueError:
        return fallback
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def filament_source_vendor(material: str) -> str:
    return "Fiberon" if material.startswith("Fiberon ") else "Polymaker"


def filament_type_from_material(material: str, source_type: Any) -> str:
    upper = material.upper()
    if material.startswith("Fiberon "):
        fiberon_tokens = (
            ("PETG-RCF", "PETG-CF"),
            ("ASA-CF", "ASA-CF"),
            ("PPS-CF", "PPS-CF"),
            ("PPS-GF", "PPS-GF"),
            ("PA612-CF", "PA612-CF"),
            ("PA612-ESD", "PA612-ESD"),
            ("PA12-CF", "PA12-CF"),
            ("PA6-CF", "PA6-CF"),
            ("PA6-GF", "PA6-GF"),
            ("PET-CF", "PET-CF"),
            ("PET-GF", "PET-GF"),
            ("PETG-ESD", "PETG-ESD"),
        )
        for needle, replacement in fiberon_tokens:
            if needle in upper:
                return replacement
    for token in ("PPS-CF", "PPS-GF", "PA612-CF", "PA612-ESD", "PA12-CF", "PA6-CF", "PA6-GF", "PETG-CF", "PET-CF", "PET-GF", "ASA-CF", "PLA-CF", "PLA-GF"):
        if token in upper:
            return token
    if "HT-PLA-GF" in upper:
        return "PLA-GF"
    explicit = first_value(source_type, "")
    if explicit:
        return explicit
    for token in ("ABS", "ASA", "PC", "PETG", "PLA", "TPU", "PA", "PPS"):
        if token in upper:
            return token
    return material


def material_profile_name(material: str, *, system: bool) -> str:
    vendor = filament_source_vendor(material)
    suffix = " @Codex" if system else ""
    return f"{material} Codex-{vendor} - Universal{suffix}"


def target_system_names(materials: list[str]) -> list[str]:
    return [material_profile_name(material, system=True) for material in materials]


def profile_ids(name: str) -> tuple[str, str]:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"codex-poly-{digest[:12]}", f"CODXPOLY{digest[:8].upper()}"


def source_matches(preset: dict[str, Any], rule: tuple[str, str, str]) -> bool:
    slicer, brand, model = rule
    if preset.get("slicer") != slicer:
        return False
    if brand and preset.get("brand") != brand:
        return False
    if model and preset.get("model") != model:
        return False
    return True


def choose_source_preset(material: str, presets: list[dict[str, Any]]) -> dict[str, Any]:
    choices = [preset for preset in presets if preset.get("material") == material]
    if not choices:
        raise SystemExit(f"official index has no presets for {material}")
    for rule in SOURCE_PRIORITY:
        matches = [preset for preset in choices if source_matches(preset, rule)]
        if matches:
            return sorted(matches, key=lambda item: item["path"])[0]
    return sorted(choices, key=lambda item: (item.get("slicer", ""), item.get("brand", ""), item.get("model", ""), item["path"]))[0]


def is_abrasive(material: str, source: dict[str, Any]) -> bool:
    if first_numeric(source.get("required_nozzle_HRC"), "0") not in {"0", "3"}:
        return True
    lowered = material.lower()
    return any(token in lowered for token in ("-cf", "-gf", " cf", " gf", "glow", "luminous"))


def normalize_source_settings(
    material: str,
    source_preset: dict[str, Any],
    source_profile: dict[str, Any],
    source_index_updated_at: str,
) -> dict[str, Any]:
    chamber = first_numeric(source_profile.get("chamber_temperature", source_profile.get("chamber_temperatures")), "0")
    abrasive = is_abrasive(material, source_profile)
    source_hrc = first_numeric(source_profile.get("required_nozzle_HRC"), "40" if abrasive else "3")
    required_hrc = "40" if abrasive and source_hrc in {"0", "3"} else source_hrc
    settings = {
        "filament_type": filament_type_from_material(material, source_profile.get("filament_type")),
        "filament_vendor": filament_source_vendor(material),
        "profile_source_vendor": first_value(source_profile.get("filament_vendor"), "Polymaker"),
        "filament_density": first_numeric(source_profile.get("filament_density"), "1.24"),
        "filament_cost": first_numeric(source_profile.get("filament_cost"), "0"),
        "filament_flow_ratio": first_numeric(source_profile.get("filament_flow_ratio"), "1"),
        "filament_max_volumetric_speed": first_numeric(source_profile.get("filament_max_volumetric_speed"), "8"),
        "filament_is_support": first_numeric(source_profile.get("filament_is_support"), "0"),
        "filament_soluble": first_numeric(source_profile.get("filament_soluble"), "0"),
        "nozzle_temperature": first_numeric(source_profile.get("nozzle_temperature"), "220"),
        "nozzle_temperature_initial_layer": first_numeric(source_profile.get("nozzle_temperature_initial_layer"), first_numeric(source_profile.get("nozzle_temperature"), "220")),
        "nozzle_temperature_range_low": first_numeric(source_profile.get("nozzle_temperature_range_low"), "180"),
        "nozzle_temperature_range_high": first_numeric(source_profile.get("nozzle_temperature_range_high"), first_numeric(source_profile.get("nozzle_temperature_initial_layer"), "240")),
        "cool_plate_temp": first_numeric(source_profile.get("cool_plate_temp"), "0"),
        "cool_plate_temp_initial_layer": first_numeric(source_profile.get("cool_plate_temp_initial_layer"), first_numeric(source_profile.get("cool_plate_temp"), "0")),
        "eng_plate_temp": first_numeric(source_profile.get("eng_plate_temp"), first_numeric(source_profile.get("hot_plate_temp"), "0")),
        "eng_plate_temp_initial_layer": first_numeric(source_profile.get("eng_plate_temp_initial_layer"), first_numeric(source_profile.get("hot_plate_temp_initial_layer"), "0")),
        "hot_plate_temp": first_numeric(source_profile.get("hot_plate_temp"), first_numeric(source_profile.get("textured_plate_temp"), "0")),
        "hot_plate_temp_initial_layer": first_numeric(source_profile.get("hot_plate_temp_initial_layer"), first_numeric(source_profile.get("textured_plate_temp_initial_layer"), "0")),
        "textured_plate_temp": first_numeric(source_profile.get("textured_plate_temp"), first_numeric(source_profile.get("hot_plate_temp"), "0")),
        "textured_plate_temp_initial_layer": first_numeric(source_profile.get("textured_plate_temp_initial_layer"), first_numeric(source_profile.get("hot_plate_temp_initial_layer"), "0")),
        "chamber_temperature": chamber,
        "activate_chamber_temp_control": "1" if float(chamber) > 0 else "0",
        "fan_min_speed": first_numeric(source_profile.get("fan_min_speed"), "0"),
        "fan_max_speed": first_numeric(source_profile.get("fan_max_speed"), "100"),
        "overhang_fan_speed": first_numeric(source_profile.get("overhang_fan_speed"), first_numeric(source_profile.get("fan_max_speed"), "100")),
        "overhang_fan_threshold": first_value(source_profile.get("overhang_fan_threshold"), "25%"),
        "required_nozzle_HRC": required_hrc,
        "temperature_vitrification": first_numeric(source_profile.get("temperature_vitrification"), "0"),
        "filament_notes": first_value(source_profile.get("filament_notes"), ""),
        "filament_retraction_length": first_numeric(source_profile.get("filament_retraction_length"), "1"),
        "filament_retraction_speed": first_numeric(source_profile.get("filament_retraction_speed"), "30"),
        "filament_deretraction_speed": first_numeric(source_profile.get("filament_deretraction_speed"), "30"),
    }
    settings["source"] = {
        "slicer": source_preset["slicer"],
        "brand": source_preset["brand"],
        "model": source_preset["model"],
        "path": source_preset["path"],
        "filename": source_preset["filename"],
        "updatedAt": source_preset["updatedAt"],
        "indexUpdatedAt": source_index_updated_at,
    }
    settings["rawProfileSubset"] = {
        key: source_profile[key]
        for key in PROFILE_FIELDS
        if key in source_profile
    }
    return settings


def refresh_catalog(path: Path) -> dict[str, Any]:
    index = official_json("index.json")
    shop_products = shop_products_by_handle()
    presets = index["presets"]
    materials = []
    for material in index["materials"]:
        source_preset = choose_source_preset(material, presets)
        source_profile = official_json(source_preset["path"])
        settings = normalize_source_settings(
            material,
            source_preset,
            source_profile,
            index.get("updatedAt", ""),
        )
        apply_current_shop_price(material, settings, shop_products)
        materials.append(
            {
                "material": material,
                "systemName": material_profile_name(material, system=True),
                "userName": material_profile_name(material, system=False),
                "settings": settings,
            }
        )

    catalog = {
        "name": "TinManX1 Polymaker Universal Codex material catalog",
        "source": "Polymaker3D/Polymaker-Preset official index",
        "sourceUrl": f"{OFFICIAL_REPO_RAW}/index.json",
        "sourceIndexVersion": index.get("version"),
        "sourceIndexUpdatedAt": index.get("updatedAt"),
        "generatedAt": datetime.now().isoformat(timespec="seconds"),
        "materialCount": len(materials),
        "materials": materials,
    }
    write_json(path, catalog)
    return catalog


def load_catalog(path: Path) -> dict[str, Any]:
    if not path.is_absolute():
        path = ROOT / path
    if not path.is_file():
        raise SystemExit(f"missing Polymaker catalog: {path}. Run --refresh-catalog first.")
    return load_json(path)


def arr(value: Any) -> list[str]:
    return [str(value)]


def generated_profile(entry: dict[str, Any], *, system: bool) -> dict[str, Any]:
    material = entry["material"]
    settings = entry["settings"]
    name = entry["systemName"] if system else entry["userName"]
    setting_id, filament_id = profile_ids(name)
    profile = {
        "type": "filament",
        "name": name,
        "from": "system" if system else "User",
        "instantiation": "true",
        "filament_vendor": arr(settings["filament_vendor"]),
        "filament_type": arr(settings["filament_type"]),
        "filament_settings_id": arr(name),
        "filament_id": filament_id,
        "setting_id": setting_id,
        "default_filament_colour": arr("#202020" if is_abrasive(material, settings) else "#E6E6E6"),
        "filament_diameter": arr("1.75"),
        "filament_density": arr(settings["filament_density"]),
        "filament_cost": arr(settings["filament_cost"]),
        "filament_flow_ratio": arr(settings["filament_flow_ratio"]),
        "filament_max_volumetric_speed": arr(settings["filament_max_volumetric_speed"]),
        "filament_is_support": arr(settings["filament_is_support"]),
        "filament_soluble": arr(settings["filament_soluble"]),
        "nozzle_temperature": arr(settings["nozzle_temperature"]),
        "nozzle_temperature_initial_layer": arr(settings["nozzle_temperature_initial_layer"]),
        "nozzle_temperature_range_low": arr(settings["nozzle_temperature_range_low"]),
        "nozzle_temperature_range_high": arr(settings["nozzle_temperature_range_high"]),
        "cool_plate_temp": arr(settings["cool_plate_temp"]),
        "cool_plate_temp_initial_layer": arr(settings["cool_plate_temp_initial_layer"]),
        "eng_plate_temp": arr(settings["eng_plate_temp"]),
        "eng_plate_temp_initial_layer": arr(settings["eng_plate_temp_initial_layer"]),
        "hot_plate_temp": arr(settings["hot_plate_temp"]),
        "hot_plate_temp_initial_layer": arr(settings["hot_plate_temp_initial_layer"]),
        "textured_plate_temp": arr(settings["textured_plate_temp"]),
        "textured_plate_temp_initial_layer": arr(settings["textured_plate_temp_initial_layer"]),
        "chamber_temperature": arr(settings["chamber_temperature"]),
        "activate_chamber_temp_control": arr(settings["activate_chamber_temp_control"]),
        "fan_min_speed": arr(settings["fan_min_speed"]),
        "fan_max_speed": arr(settings["fan_max_speed"]),
        "overhang_fan_speed": arr(settings["overhang_fan_speed"]),
        "overhang_fan_threshold": arr(settings["overhang_fan_threshold"]),
        "required_nozzle_HRC": arr(settings["required_nozzle_HRC"]),
        "temperature_vitrification": arr(settings["temperature_vitrification"]),
        "filament_retraction_length": arr(settings["filament_retraction_length"]),
        "filament_retraction_speed": arr(settings["filament_retraction_speed"]),
        "filament_deretraction_speed": arr(settings["filament_deretraction_speed"]),
        "compatible_printers": [],
        "is_custom_defined": "0",
        "version": "2.4.2.0",
        "description": (
            f"{GENERATED_MARKER}; material={material}; official source="
            f"{settings['source']['path']}; source updated={settings['source']['updatedAt']}"
        ),
        "filament_notes": arr(settings["filament_notes"]),
        "polymaker_source_material": arr(material),
        "polymaker_source_preset_path": arr(settings["source"]["path"]),
        "polymaker_source_index_updated_at": arr(settings["source"].get("indexUpdatedAt", "")),
        "filament_price_source_url": arr(settings.get("priceSource", {}).get("sourceUrl", "")),
        "filament_price_source_variant": arr(settings.get("priceSource", {}).get("variantTitle", "")),
    }
    if not system:
        profile["renamed_from"] = f"{material} Polymaker official Universal"
        profile.pop("setting_id", None)
    return profile


def target_items(catalog: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "name": entry["systemName"],
            "sub_path": f"filament/{entry['systemName']}.json",
        }
        for entry in catalog["materials"]
    ]


def user_filament_dirs(app_support: Path) -> list[Path]:
    root = app_support / "user"
    if not root.is_dir():
        return []
    return sorted(path / "filament" for path in root.iterdir() if (path / "filament").is_dir())


def user_info_text(user_dir: Path, material: str, updated_time: int) -> str:
    user_folder = user_dir.parent.name
    user_id = user_folder if user_folder.isdigit() else ""
    base_id = "codex-poly-" + hashlib.sha1(f"polymaker:{material}:user".encode("utf-8")).hexdigest()[:12]
    return "\n".join(
        [
            "sync_info = ",
            f"user_id = {user_id}",
            "setting_id = ",
            f"base_id = {base_id}",
            f"updated_time = {updated_time}",
            "",
        ]
    )


def backup_catalog(index_path: Path, filament_dir: Path, app_support: Path, backup_root: Path, catalog: dict[str, Any]) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(index_path, backup / "Codex.json")
    conf_path = app_support / "OrcaSlicer.conf"
    if conf_path.is_file():
        shutil.copy2(conf_path, backup / "OrcaSlicer.conf")
    target_names = set(target_system_names([entry["material"] for entry in catalog["materials"]]))
    target_user_names = {entry["userName"] for entry in catalog["materials"]}
    for name in target_names:
        source = filament_dir / f"{name}.json"
        if source.is_file():
            target = backup / "system" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for user_dir in user_filament_dirs(app_support):
        relative_user_dir = user_dir.relative_to(app_support)
        for stem in target_user_names:
            for suffix in (".json", ".info"):
                source = user_dir / f"{stem}{suffix}"
                if source.is_file():
                    target = backup / relative_user_dir / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    return backup


def update_enabled_filaments(app_support: Path, catalog: dict[str, Any], dry_run: bool) -> int:
    conf_path = app_support / "OrcaSlicer.conf"
    if not conf_path.is_file():
        return 0
    conf = load_json(conf_path)
    filaments = list(conf.get("filaments") or [])
    names = target_system_names([entry["material"] for entry in catalog["materials"]])
    existing_count = sum(1 for name in names if name in filaments)
    filaments = [name for name in filaments if name not in names]
    insert_at = max(
        (
            index
            for index, name in enumerate(filaments)
            if any(token in name for token in ("Codex-Polymaker", "Codex-Fiberon", "Polymaker", "Fiberon"))
        ),
        default=len(filaments) - 1,
    ) + 1
    for offset, name in enumerate(names):
        filaments.insert(insert_at + offset, name)
    if not dry_run:
        conf["filaments"] = filaments
        write_json(conf_path, conf)
    return len(names) - existing_count


def install(app_support: Path, backup_root: Path, catalog: dict[str, Any], dry_run: bool = False) -> InstallResult:
    system_root = app_support / "system"
    index_path = system_root / "Codex.json"
    filament_dir = system_root / "Codex" / "filament"
    if not index_path.is_file():
        raise SystemExit(f"missing Codex index: {index_path}")
    if not filament_dir.is_dir():
        raise SystemExit(f"missing Codex filament directory: {filament_dir}")

    system_profiles = [(filament_dir / f"{entry['systemName']}.json", generated_profile(entry, system=True)) for entry in catalog["materials"]]
    index = load_json(index_path)
    target_names = set(target_system_names([entry["material"] for entry in catalog["materials"]]))
    existing = [item for item in index.get("filament_list", []) if item.get("name") not in target_names]
    insert_after = max(
        (
            i
            for i, item in enumerate(existing)
            if any(token in item.get("name", "") for token in ("Codex-Polymaker", "Codex-Fiberon"))
        ),
        default=len(existing) - 1,
    )
    index["version"] = "00.00.01.03"
    index["filament_list"] = existing[: insert_after + 1] + target_items(catalog) + existing[insert_after + 1 :]

    updated_time = int(time.time())
    user_profiles: list[Path] = []
    user_infos: list[Path] = []
    user_generated: list[tuple[Path, dict[str, Any], Path, str]] = []
    for user_dir in user_filament_dirs(app_support):
        for entry in catalog["materials"]:
            profile = generated_profile(entry, system=False)
            profile_path = user_dir / f"{entry['userName']}.json"
            info_path = user_dir / f"{entry['userName']}.info"
            user_profiles.append(profile_path)
            user_infos.append(info_path)
            user_generated.append((profile_path, profile, info_path, user_info_text(user_dir, entry["material"], updated_time)))

    backup_path = None
    if not dry_run:
        backup_path = backup_catalog(index_path, filament_dir, app_support, backup_root, catalog)
        write_json(index_path, index)
        for path, profile in system_profiles:
            write_json(path, profile, indent=4)
        for profile_path, profile, info_path, info_text in user_generated:
            write_json(profile_path, profile, indent=4)
            info_path.write_text(info_text)
    enabled_added = update_enabled_filaments(app_support, catalog, dry_run)
    return InstallResult(
        system_profiles=[path for path, _ in system_profiles],
        user_profiles=user_profiles,
        user_infos=user_infos,
        enabled_added=enabled_added,
        backup_path=backup_path,
    )


def validate(app_support: Path, catalog: dict[str, Any]) -> None:
    index_path = app_support / "system" / "Codex.json"
    filament_dir = app_support / "system" / "Codex" / "filament"
    conf_path = app_support / "OrcaSlicer.conf"
    index = load_json(index_path)
    index_names = {item.get("name") for item in index.get("filament_list", [])}
    conf_names = set(load_json(conf_path).get("filaments") or []) if conf_path.is_file() else set()
    missing_index = []
    missing_files = []
    missing_enabled = []
    missing_users = []
    for entry in catalog["materials"]:
        name = entry["systemName"]
        if name not in index_names:
            missing_index.append(name)
        if not (filament_dir / f"{name}.json").is_file():
            missing_files.append(name)
        if conf_names and name not in conf_names:
            missing_enabled.append(name)
        for user_dir in user_filament_dirs(app_support):
            user_name = entry["userName"]
            if not (user_dir / f"{user_name}.json").is_file() or not (user_dir / f"{user_name}.info").is_file():
                missing_users.append(f"{user_dir.parent.name}/{user_name}")
    if missing_index or missing_files or missing_enabled or missing_users:
        raise SystemExit(
            "Polymaker install validation failed:\n"
            f"missing index={missing_index[:5]}\n"
            f"missing files={missing_files[:5]}\n"
            f"missing enabled={missing_enabled[:5]}\n"
            f"missing users={missing_users[:5]}"
        )
    print(
        "Polymaker Codex catalog validation passed: "
        f"{len(catalog['materials'])} materials, "
        f"{len(user_filament_dirs(app_support))} user preset folder(s)."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path, default=ROOT / "work" / "tinmanx1-polymaker-catalog-backups")
    parser.add_argument("--catalog", type=Path, default=ROOT / CATALOG_PATH)
    parser.add_argument("--refresh-catalog", action="store_true")
    parser.add_argument("--install", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    catalog_path = args.catalog if args.catalog.is_absolute() else ROOT / args.catalog
    if args.refresh_catalog:
        catalog = refresh_catalog(catalog_path)
        print(
            "Refreshed Polymaker catalog: "
            f"{catalog['materialCount']} materials from official index {catalog['sourceIndexUpdatedAt']}."
        )
    else:
        catalog = load_catalog(catalog_path)

    if args.install:
        result = install(args.app_support, args.backup_root, catalog, dry_run=args.dry_run)
        print(
            "Polymaker Codex install "
            f"{'dry run ' if args.dry_run else ''}prepared {len(result.system_profiles)} system profiles, "
            f"{len(result.user_profiles)} user profiles, {len(result.user_infos)} user info sidecars, "
            f"enabled_added={result.enabled_added}."
        )
        if result.backup_path:
            print(f"Backup: {result.backup_path}")

    if args.validate:
        validate(args.app_support, catalog)

    if not (args.refresh_catalog or args.install or args.validate):
        print(f"Catalog: {catalog_path}")
        print(f"Materials: {catalog['materialCount']}")
        print(f"Source index updated: {catalog.get('sourceIndexUpdatedAt')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
