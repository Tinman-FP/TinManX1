#!/usr/bin/env python3
"""Audit installed TinManX1 Codex filament chamber control and cost metadata.

This intentionally operates on the workstation-local OrcaSlicer-Codex
Application Support catalog. The public repo carries source generators, but
the active TinManX1 UI also depends on live system and user preset sidecars.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_BACKUP_ROOT = Path("work/tinmanx1-filament-audit-backups")
CATALOG_PATH = Path("resources/profiles/polymaker/polymaker_material_catalog.json")


@dataclass(frozen=True)
class PriceSource:
    cost: float
    source: str
    url: str = ""
    note: str = ""


EXACT_PRICE_OVERRIDES: dict[tuple[str, str], PriceSource] = {
    ("3D-Fuel Pro", "PCTG-CF"): PriceSource(54.95, "3D-Fuel Pro PCTG-CF10 1 kg spool", "https://www.3dfuel.com/products/pro-pctg-cf10-carbon-fiber-1-75mm"),
    ("Bambu", "ABS"): PriceSource(19.99, "Bambu Lab ABS 1 kg MSRP", "https://us.store.bambulab.com/products/abs-filament"),
    ("Bambu", "ABS-GF"): PriceSource(29.99, "Bambu Lab ABS-GF 1 kg MSRP", "https://us.store.bambulab.com/products/abs-gf"),
    ("Bambu", "ASA-CF"): PriceSource(36.99, "Bambu Lab ASA-CF 1 kg MSRP", "https://us.store.bambulab.com/products/asa-cf"),
    ("Bambu", "PAHT-CF"): PriceSource(94.99, "Bambu Lab PAHT-CF 1 kg MSRP", "https://us.store.bambulab.com/products/paht-cf"),
    ("Bambu", "PETG-CF"): PriceSource(31.99, "Bambu Lab PETG-CF 1 kg MSRP", "https://us.store.bambulab.com/products/petg-cf"),
    ("Bambu", "PPA-CF"): PriceSource(199.99, "Bambu Lab PPA-CF MSRP converted from 0.75 kg spool", "https://us.store.bambulab.com/products/ppa-cf", "MSRP $149.99 / 0.75 kg"),
    ("Bambu", "PPS-CF"): PriceSource(173.32, "Bambu Lab PPS-CF MSRP converted from 0.75 kg spool", "https://us.store.bambulab.com/products/pps-cf", "MSRP $129.99 / 0.75 kg"),
    ("Elegoo", "TPU"): PriceSource(19.99, "Elegoo TPU 95A current installed baseline"),
    ("Inland", "ABS"): PriceSource(20.00, "Inland ABS current installed baseline"),
    ("Polymaker", "HT-PLA-CF"): PriceSource(
        29.99,
        "Polymaker PolyLite PLA-CF 1 kg MSRP used for Codex HT-PLA-CF alias",
        "https://shop.polymaker.com/products/polylite-pla-cf",
    ),
    ("Push Plastic", "PC-PBT"): PriceSource(39.99, "Push Plastic PC+PBT 1 kg spool", "https://www.pushplastic.com/products/pc-pbt-filament-1-75mm-1kg"),
    ("Push Plastic", "PC-PBT-CF"): PriceSource(99.98, "Push Plastic Carbon Fiber PC+PBT 500 g spool, normalized to 1 kg", "https://www.pushplastic.com/products/carbon-fiber-pc-pbt-filament-1-75mm-500g"),
    ("QIDI", "ABS-GF"): PriceSource(59.99, "QIDI ABS-GF25 1 kg Amazon listing", "https://www.amazon.com/QIDI-TECHNOLOGY-Filament-ABS-GF25-Interlayer/dp/B0BXSMBGCJ"),
    ("QIDI", "PPS-GF"): PriceSource(79.99, "QIDI PPS-GF20 converted from 750 g spool", "https://us.qidi3d.com/products/pps-gf20", "$59.99 / 0.75 kg"),
    ("RatRig Punk", "ABS"): PriceSource(24.99, "RatRig Punk ABS current installed baseline"),
    ("SainSmart", "PE"): PriceSource(69.00, "SainSmart PEBA current installed baseline"),
}


GENERIC_PRICE_AVERAGES: dict[str, PriceSource] = {
    "ABS": PriceSource(22.00, "Generic 1 kg retail average"),
    "ABS-CF": PriceSource(42.00, "Generic 1 kg retail average"),
    "ABS-GF": PriceSource(45.00, "Generic 1 kg retail average"),
    "ASA": PriceSource(27.00, "Generic 1 kg retail average"),
    "ASA-CF": PriceSource(40.00, "Generic 1 kg retail average"),
    "ASA-GF": PriceSource(50.00, "Generic 1 kg retail average"),
    "HIPS": PriceSource(30.00, "Generic 1 kg retail average"),
    "PA": PriceSource(35.00, "Generic 1 kg retail average"),
    "PA-CF": PriceSource(80.00, "Generic 1 kg retail average"),
    "PA-GF": PriceSource(60.00, "Generic 1 kg retail average"),
    "PA12-CF": PriceSource(110.00, "Generic 1 kg retail average"),
    "PA6-CF": PriceSource(70.00, "Generic 1 kg retail average"),
    "PA6-GF": PriceSource(60.00, "Generic 1 kg retail average"),
    "PA612-CF": PriceSource(80.00, "Generic 1 kg retail average"),
    "PA612-ESD": PriceSource(120.00, "Generic 1 kg retail average"),
    "PAHT": PriceSource(55.00, "Generic 1 kg retail average"),
    "PAHT-CF": PriceSource(85.00, "Generic 1 kg retail average"),
    "PC": PriceSource(40.00, "Generic 1 kg retail average"),
    "PC-CF": PriceSource(75.00, "Generic 1 kg retail average"),
    "PC-PBT": PriceSource(39.99, "Generic 1 kg retail average"),
    "PC-PBT-CF": PriceSource(99.98, "Push Plastic Carbon Fiber PC+PBT 500 g spool, normalized to 1 kg", "https://www.pushplastic.com/products/carbon-fiber-pc-pbt-filament-1-75mm-500g"),
    "PCTG": PriceSource(30.00, "Generic 1 kg retail average"),
    "PCTG-CF": PriceSource(54.95, "Generic 1 kg retail average"),
    "PE": PriceSource(69.00, "Generic 1 kg retail average"),
    "PET-CF": PriceSource(45.00, "Generic 1 kg retail average"),
    "PET-GF": PriceSource(30.00, "Generic 1 kg retail average"),
    "PETG": PriceSource(20.00, "Generic 1 kg retail average"),
    "PETG-CF": PriceSource(35.00, "Generic 1 kg retail average"),
    "PETG-ESD": PriceSource(60.00, "Generic 1 kg retail average"),
    "PLA": PriceSource(20.00, "Generic 1 kg retail average"),
    "PLA-CF": PriceSource(30.00, "Generic 1 kg retail average"),
    "PLA-GF": PriceSource(30.00, "Generic 1 kg retail average"),
    "HT-PLA-CF": PriceSource(29.99, "Polymaker PolyLite PLA-CF 1 kg MSRP used for Codex HT-PLA-CF alias", "https://shop.polymaker.com/products/polylite-pla-cf"),
    "HT-PLA-GF": PriceSource(29.99, "Polymaker HT-PLA-GF 1 kg MSRP", "https://shop.polymaker.com/products/polymaker-ht-pla-gf"),
    "PPA-CF": PriceSource(145.00, "Generic 1 kg retail average"),
    "PPS": PriceSource(120.00, "Generic 1 kg retail average"),
    "PPS-CF": PriceSource(140.00, "Generic 1 kg retail average"),
    "PPS-GF": PriceSource(80.00, "Generic 1 kg retail average"),
    "PVB": PriceSource(49.00, "Generic 1 kg retail average"),
    "TPU": PriceSource(25.00, "Generic 1 kg retail average"),
}

CHAMBER_BY_TYPE = {
    "PCTG": 45,
    "PCTG-CF": 45,
}

POLYMAKER_NAME_ALIASES = {
    "COPE CODEX-POLYMAKER": "Panchroma CoPE",
    "PA12-CF CODEX-FIBERON": "Fiberon PA12-CF10",
    "PA6-CF CODEX-FIBERON": "Fiberon PA6-CF20",
    "PA6-GF CODEX-FIBERON": "Fiberon PA6-GF25",
    "PA612-CF CODEX-FIBERON": "Fiberon PA612-CF15",
    "PET-CF CODEX-FIBERON": "Fiberon PET-CF17",
    "PETG-CF CODEX-FIBERON": "Fiberon PETG-rCF08",
    "PETG-ESD CODEX-FIBERON": "Fiberon PETG-ESD",
    "HT-PLA-CF CODEX-POLYMAKER": "PolyLite PLA-CF",
    "HT-PLA-GF CODEX-POLYMAKER": "Polymaker HT-PLA-GF",
    "PPS-CF CODEX-FIBERON": "Fiberon PPS-CF10",
    "PPS-GF CODEX-FIBERON": "Fiberon PPS-GF20",
}


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def scalar(value: Any, fallback: str = "") -> str:
    for item in as_list(value):
        if item is None:
            continue
        text = str(item)
        if text:
            return text
    return fallback


def set_like_existing(profile: dict[str, Any], key: str, value: str) -> None:
    if isinstance(profile.get(key), list) or key not in profile:
        profile[key] = [value]
    else:
        profile[key] = value


def floatish(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(scalar(value, str(fallback)))
    except (TypeError, ValueError):
        return fallback


def money(value: float) -> str:
    rounded = round(value, 2)
    return str(int(rounded)) if rounded.is_integer() else f"{rounded:.2f}"


def profile_brand(name: str) -> str:
    match = re.search(r"\bCodex-(.*?) - ", name)
    return match.group(1) if match else ""


def profile_type(profile: dict[str, Any]) -> str:
    name = scalar(profile.get("name")).upper()
    if name.startswith("PC-PBT-CF CODEX-"):
        return "PC-PBT-CF"
    return scalar(profile.get("filament_type")).upper()


def load_polymaker_prices(catalog_path: Path) -> dict[tuple[str, str], PriceSource]:
    catalog = load_json(catalog_path)
    prices: dict[tuple[str, str], PriceSource] = {}
    for entry in catalog.get("materials", []):
        settings = entry.get("settings") or {}
        source = settings.get("priceSource") or {}
        cost = floatish(settings.get("filament_cost"))
        if cost <= 0:
            continue
        price = PriceSource(
            cost,
            source.get("source") or "Polymaker shop current product feed",
            source.get("sourceUrl", ""),
            f"{source.get('variantTitle', '')}; {source.get('retailPriceUsd', '')}/{source.get('spoolWeightKg', '')}kg",
        )
        material = entry["material"]
        prices[(entry["systemName"], "name")] = price
        prices[(entry["userName"], "name")] = price
        prices[(material, "material")] = price

    alias_by_type = {
        "ASA-CF": "Fiberon ASA-CF08",
        "PA12-CF": "Fiberon PA12-CF10",
        "PA6-CF": "Fiberon PA6-CF20",
        "PA-GF": "Fiberon PA6-GF25",
        "PA6-GF": "Fiberon PA6-GF25",
        "PA612-CF": "Fiberon PA612-CF15",
        "PA612-ESD": "Fiberon PA612-ESD",
        "PET-CF": "Fiberon PET-CF17",
        "PET-GF": "Fiberon PET-GF15",
        "PETG-CF": "Fiberon PETG-rCF08",
        "PETG-ESD": "Fiberon PETG-ESD",
        "PPS-CF": "Fiberon PPS-CF10",
        "PPS-GF": "Fiberon PPS-GF20",
    }
    for ftype, material in alias_by_type.items():
        if (material, "material") in prices:
            prices[(f"Fiberon:{ftype}", "brand_type")] = prices[(material, "material")]
            prices[(f"Polymaker:{ftype}", "brand_type")] = prices[(material, "material")]
    return prices


def price_for_profile(profile: dict[str, Any], polymaker_prices: dict[tuple[str, str], PriceSource]) -> PriceSource | None:
    name = scalar(profile.get("name"))
    ftype = profile_type(profile)
    brand = profile_brand(name)

    if (name, "name") in polymaker_prices:
        return polymaker_prices[(name, "name")]
    upper_name = name.upper()
    for needle, material in POLYMAKER_NAME_ALIASES.items():
        if needle in upper_name and (material, "material") in polymaker_prices:
            return polymaker_prices[(material, "material")]
    if (f"{brand}:{ftype}", "brand_type") in polymaker_prices:
        return polymaker_prices[(f"{brand}:{ftype}", "brand_type")]
    if (brand, ftype) in EXACT_PRICE_OVERRIDES:
        return EXACT_PRICE_OVERRIDES[(brand, ftype)]
    if brand in {"Generic", "FibreSeek", "Codex", ""}:
        return GENERIC_PRICE_AVERAGES.get(ftype)
    return GENERIC_PRICE_AVERAGES.get(ftype)


def is_managed_codex_profile(profile: dict[str, Any], path: Path) -> bool:
    name = scalar(profile.get("name"), path.stem)
    if "Codex-" in name or name.startswith("Codex "):
        return True
    if " @Codex" in name:
        return True
    return False


def desired_chamber(profile: dict[str, Any]) -> float:
    current = floatish(profile.get("chamber_temperature", profile.get("chamber_temperatures")), 0.0)
    if current > 0:
        return current
    return float(CHAMBER_BY_TYPE.get(profile_type(profile), 0))


def allows_passive_chamber_target(profile: dict[str, Any]) -> bool:
    name = scalar(profile.get("name"))
    return name == "PC-PBT-CF Codex-Push Plastic - Prusa CORE One L @Codex"


def apply_profile_audit(profile: dict[str, Any], polymaker_prices: dict[tuple[str, str], PriceSource]) -> list[str]:
    changes: list[str] = []
    chamber = desired_chamber(profile)
    active = scalar(profile.get("activate_chamber_temp_control"))
    if chamber > 0:
        if floatish(profile.get("chamber_temperature", profile.get("chamber_temperatures"))) <= 0:
            set_like_existing(profile, "chamber_temperature", money(chamber))
            changes.append(f"chamber={money(chamber)}")
        if active != "1" and not allows_passive_chamber_target(profile):
            set_like_existing(profile, "activate_chamber_temp_control", "1")
            changes.append("active_chamber=1")

    price = price_for_profile(profile, polymaker_prices)
    if price:
        current_cost = floatish(profile.get("filament_cost"))
        if abs(current_cost - price.cost) > 0.005:
            set_like_existing(profile, "filament_cost", money(price.cost))
            changes.append(f"cost={money(price.cost)}")
        if price.url:
            set_like_existing(profile, "filament_price_source_url", price.url)
        set_like_existing(profile, "filament_price_source", price.source)
        if price.note:
            set_like_existing(profile, "filament_price_source_note", price.note)
    return changes


def filament_json_paths(app_support: Path) -> list[Path]:
    paths = sorted((app_support / "system" / "Codex" / "filament").glob("*.json"))
    user_root = app_support / "user"
    if user_root.is_dir():
        for user_dir in sorted(path / "filament" for path in user_root.iterdir() if (path / "filament").is_dir()):
            paths.extend(sorted(user_dir.glob("*.json")))
    return paths


def backup_live_state(app_support: Path, backup_root: Path) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    for source in (
        app_support / "system" / "Codex.json",
        app_support / "OrcaSlicer.conf",
    ):
        if source.is_file():
            shutil.copy2(source, backup / source.name)
    system_filament = app_support / "system" / "Codex" / "filament"
    if system_filament.is_dir():
        shutil.copytree(system_filament, backup / "system" / "Codex" / "filament")
    user_root = app_support / "user"
    if user_root.is_dir():
        for user_dir in sorted(path / "filament" for path in user_root.iterdir() if (path / "filament").is_dir()):
            target = backup / user_dir.relative_to(app_support)
            shutil.copytree(user_dir, target)
    return backup


def audit(app_support: Path, backup_root: Path, catalog_path: Path, dry_run: bool) -> tuple[int, dict[str, int], Path | None]:
    if not (app_support / "system" / "Codex" / "filament").is_dir():
        raise SystemExit(f"missing Codex filament directory under {app_support}")
    polymaker_prices = load_polymaker_prices(catalog_path)
    paths = filament_json_paths(app_support)
    changed: dict[Path, dict[str, Any]] = {}
    change_counts: dict[str, int] = {}
    for path in paths:
        profile = load_json(path)
        if not is_managed_codex_profile(profile, path):
            continue
        changes = apply_profile_audit(profile, polymaker_prices)
        if changes:
            changed[path] = profile
            for change in changes:
                change_counts[change.split("=", 1)[0]] = change_counts.get(change.split("=", 1)[0], 0) + 1

    backup = None
    if changed and not dry_run:
        backup = backup_live_state(app_support, backup_root)
        for path, profile in changed.items():
            write_json(path, profile)
    return len(changed), change_counts, backup


def validate(app_support: Path) -> None:
    failures: list[str] = []
    for path in sorted((app_support / "system" / "Codex" / "filament").glob("*.json")):
        profile = load_json(path)
        if not is_managed_codex_profile(profile, path):
            continue
        name = scalar(profile.get("name"), path.stem)
        cost = floatish(profile.get("filament_cost"), -1)
        chamber = floatish(profile.get("chamber_temperature", profile.get("chamber_temperatures")), 0)
        active = scalar(profile.get("activate_chamber_temp_control"))
        if cost <= 0:
            failures.append(f"{name}: filament_cost={cost:g}")
        if chamber > 0 and active != "1" and not allows_passive_chamber_target(profile):
            failures.append(f"{name}: chamber={chamber:g} but active={active!r}")
    if failures:
        raise SystemExit("Codex filament audit validation failed:\n" + "\n".join(failures[:40]))
    print(
        "Codex filament audit validation passed: system profiles have positive costs and "
        "active chamber control where supported."
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path, default=ROOT / DEFAULT_BACKUP_ROOT)
    parser.add_argument("--catalog", type=Path, default=ROOT / CATALOG_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.validate:
        validate(args.app_support)
        return 0
    changed, change_counts, backup = audit(args.app_support, args.backup_root, args.catalog, args.dry_run)
    verb = "would update" if args.dry_run else "updated"
    print(f"{verb} {changed} installed filament preset JSON file(s)")
    for key, count in sorted(change_counts.items()):
        print(f"{key}: {count}")
    if backup:
        print(f"Backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
