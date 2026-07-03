#!/usr/bin/env python3
"""Audit installed TinManX1 filament profile trees for effective material cost.

Orca-style presets commonly keep machine-specific filament JSON files thin and
inherit their material cost from a parent preset.  This helper validates that
every selectable/material filament preset resolves to a positive cost through
that inheritance chain and fills missing costs with the current known vendor
price, then a 1 kg generic material average when the preset is generic or the
vendor is not mapped.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_ROOTS = [
    Path("/Applications/TinManX1.app/Contents/Resources/profiles"),
    Path.home() / "Library/Application Support/OrcaSlicer-Codex/system",
]
DEFAULT_BACKUP_ROOT = Path("work/tinmanx1-filament-price-tree-backups")
CATALOG_PATH = Path("resources/profiles/polymaker/polymaker_material_catalog.json")


@dataclass(frozen=True)
class PriceSource:
    cost: float
    source: str
    url: str = ""
    note: str = ""


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())


def load_codex_audit_module() -> Any:
    helper = Path(__file__).with_name("audit_codex_filament_chamber_and_cost.py")
    spec = importlib.util.spec_from_file_location("audit_codex_filament_chamber_and_cost", helper)
    if spec is None or spec.loader is None:
        raise SystemExit(f"unable to load {helper}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


CODEX_AUDIT = load_codex_audit_module()


def merged_generic_prices() -> dict[str, PriceSource]:
    prices = {
        key: PriceSource(value.cost, value.source, value.url, value.note)
        for key, value in CODEX_AUDIT.GENERIC_PRICE_AVERAGES.items()
    }
    prices.update(
        {
            "BVOH": PriceSource(55.00, "Generic 1 kg retail average"),
            "COPE": PriceSource(19.99, "Generic 1 kg retail average"),
            "EVA": PriceSource(30.00, "Generic 1 kg retail average"),
            "PE-CF": PriceSource(90.00, "Generic 1 kg retail average"),
            "PHA": PriceSource(25.00, "Generic 1 kg retail average"),
            "PLA-SILK": PriceSource(22.00, "Generic 1 kg retail average"),
            "PP": PriceSource(35.00, "Generic 1 kg retail average"),
            "PPA-GF": PriceSource(120.00, "Generic 1 kg retail average"),
            "PVA": PriceSource(55.00, "Generic 1 kg retail average"),
            "SBS": PriceSource(30.00, "Generic 1 kg retail average"),
            "TPU-95A": PriceSource(25.00, "Generic 1 kg retail average"),
        }
    )
    return prices


GENERIC_PRICE_AVERAGES = merged_generic_prices()

EXACT_PRICE_OVERRIDES = {
    (brand.upper(), material.upper()): PriceSource(value.cost, value.source, value.url, value.note)
    for (brand, material), value in CODEX_AUDIT.EXACT_PRICE_OVERRIDES.items()
}
EXACT_PRICE_OVERRIDES.update(
    {
        ("BAMBU", "PLA"): PriceSource(
            19.99,
            "Bambu Lab PLA Basic 1 kg MSRP",
            "https://us.store.bambulab.com/products/pla-basic-filament",
        ),
        ("BAMBU LAB", "PLA"): PriceSource(
            19.99,
            "Bambu Lab PLA Basic 1 kg MSRP",
            "https://us.store.bambulab.com/products/pla-basic-filament",
        ),
        ("BAMBU", "PETG"): PriceSource(
            23.49,
            "Bambu Lab PETG HF 1 kg Amazon listing",
            "https://www.amazon.com/Bambu-Lab-PETG-1-75mm-1kg/dp/B0FPKG85B3",
        ),
        ("BAMBU LAB", "PETG"): PriceSource(
            23.49,
            "Bambu Lab PETG HF 1 kg Amazon listing",
            "https://www.amazon.com/Bambu-Lab-PETG-1-75mm-1kg/dp/B0FPKG85B3",
        ),
        ("BAMBU", "ASA"): PriceSource(
            27.99,
            "Bambu Lab ASA 1 kg US-store price",
            "https://us.store.bambulab.com/products/asa-filament",
        ),
        ("BAMBU LAB", "ASA"): PriceSource(
            27.99,
            "Bambu Lab ASA 1 kg US-store price",
            "https://us.store.bambulab.com/products/asa-filament",
        ),
        ("QIDI", "ASA"): PriceSource(
            29.99,
            "QIDI ASA 1 kg US-store price",
            "https://us.qidi3d.com/products/qidi-asa-filament",
        ),
        ("QIDI", "ASA-CF"): PriceSource(
            45.99,
            "QIDI ASA-CF20 Core 1 kg US-store price",
            "https://us.qidi3d.com/products/asa-cf20-core",
        ),
        ("FLASHFORGE", "ASA"): PriceSource(
            29.99,
            "Flashforge ASA 1 kg direct price",
            "https://www.flashforge.com/products/asa",
        ),
        ("FLASHFORGE", "ASA-CF"): PriceSource(
            25.99,
            "Flashforge ASA-CF 1 kg direct price",
            "https://www.flashforge.com/products/asa-cf",
        ),
    }
)

PRODUCT_PRICE_OVERRIDES = {
    "OVERTURE PLA": PriceSource(
        13.98,
        "OVERTURE PLA 1 kg Amazon listing",
        "https://www.amazon.com/OVERTURE-Professional-Toughness-Dimensional-Probability/dp/B0991SNS5C",
    ),
    "OVERTURE PLA PLUS": PriceSource(
        24.99,
        "OVERTURE PLA+ 1 kg Amazon listing",
        "https://www.amazon.com/OVERTURE-Professional-Toughness-Dimensional-Probability/dp/B0991SNS5C",
    ),
    "OVERTURE PLA+": PriceSource(
        24.99,
        "OVERTURE PLA+ 1 kg Amazon listing",
        "https://www.amazon.com/OVERTURE-Professional-Toughness-Dimensional-Probability/dp/B0991SNS5C",
    ),
    "OVERTURE MATTE PLA": PriceSource(
        14.39,
        "OVERTURE Matte PLA 1 kg Amazon listing",
        "https://www.amazon.com/OVERTURE-Filament-Printer-Dimensional-Accuracy/dp/B08L14B9FJ",
    ),
    "OVERTURE PETG": PriceSource(
        15.69,
        "OVERTURE PETG 1 kg Amazon listing",
        "https://www.amazon.com/OVERTURE-Filament-Dimensional-Accuracy-Printers/dp/B08F6JN4PR",
    ),
    "ESUN PLA+": PriceSource(
        16.99,
        "eSUN PLA+ 1 kg Amazon listing",
        "https://www.amazon.com/eSUN-Filament-Dimensional-Accuracy-Cardboard/dp/B0D25PGVYH",
    ),
    "ESUN PLA PLUS": PriceSource(
        16.99,
        "eSUN PLA+ 1 kg Amazon listing",
        "https://www.amazon.com/eSUN-Filament-Dimensional-Accuracy-Cardboard/dp/B0D25PGVYH",
    ),
}

PRODUCT_MATERIAL_ALIASES = {
    "POLYLITE ABS": "POLYLITE ABS",
    "POLYLITE ASA": "POLYMAKER ASA",
    "POLYLITE PETG": "POLYLITE PETG",
    "POLYLITE PLA": "POLYLITE PLA",
    "POLYTERRA PLA": "POLYTERRA PLA",
    "POLYMAKER PETG": "POLYMAKER PETG",
    "POLYMAKER PLA": "POLYMAKER PLA",
}

MATERIAL_NAME_MAP = {
    "ABS": "ABS",
    "ABS CF": "ABS-CF",
    "ABS GF": "ABS-GF",
    "ASA": "ASA",
    "ASA AERO": "ASA",
    "ASA CF": "ASA-CF",
    "ASA CF20": "ASA-CF",
    "ASA GF": "ASA-GF",
    "BVOH": "BVOH",
    "COPE": "COPE",
    "EVA": "EVA",
    "HIPS": "HIPS",
    "PA": "PA",
    "PA CF": "PA-CF",
    "PA GF": "PA-GF",
    "PA12 CF": "PA12-CF",
    "PA6 CF": "PA6-CF",
    "PA6 GF": "PA6-GF",
    "PA612 CF": "PA612-CF",
    "PAHT": "PAHT",
    "PAHT CF": "PAHT-CF",
    "PC": "PC",
    "PC CF": "PC-CF",
    "PC PBT": "PC-PBT",
    "PCTG": "PCTG",
    "PCTG CF": "PCTG-CF",
    "PE": "PE",
    "PE CF": "PE-CF",
    "PET": "PETG",
    "PET CF": "PET-CF",
    "PET GF": "PET-GF",
    "PETG": "PETG",
    "PETG CF": "PETG-CF",
    "PHA": "PHA",
    "PLA": "PLA",
    "PLA CF": "PLA-CF",
    "PLA GF": "PLA-GF",
    "PLA SILK": "PLA-SILK",
    "PP": "PP",
    "PPA CF": "PPA-CF",
    "PPA GF": "PPA-GF",
    "PPS": "PPS",
    "PPS CF": "PPS-CF",
    "PPS GF": "PPS-GF",
    "PVA": "PVA",
    "PVB": "PVB",
    "SBS": "SBS",
    "TPU": "TPU",
    "TPU 95A": "TPU-95A",
}

MATERIAL_SCAN_ORDER = sorted(MATERIAL_NAME_MAP, key=len, reverse=True)


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


def normalize(text: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9+]+", " ", text.upper())
    return re.sub(r"\s+", " ", normalized).strip()


def base_product_name(profile: dict[str, Any], path: Path) -> str:
    name = scalar(profile.get("name"), path.stem)
    name = re.split(r"\s+@", name, maxsplit=1)[0]
    name = re.sub(r"@\S+$", "", name)
    name = re.sub(r"\b(?:0\.\d+|1\.75|2\.85)\s*(?:NOZZLE|MM)?\b", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\b(?:HF|HS|ALL|BASE|SYSTEM)\b$", "", name, flags=re.IGNORECASE)
    return normalize(name)


def first_known_vendor(profile: dict[str, Any], path: Path) -> str:
    vendor = normalize(scalar(profile.get("filament_vendor")))
    if vendor and vendor != "GENERIC":
        if vendor == "BAMBU LAB":
            return "BAMBU LAB"
        return vendor
    product = base_product_name(profile, path)
    for candidate in (
        "BAMBU LAB",
        "BAMBU",
        "QIDI",
        "FLASHFORGE",
        "OVERTURE",
        "ESUN",
        "POLYMAKER",
        "POLYLITE",
        "POLYTERRA",
        "PUSH PLASTIC",
        "CREALITY",
        "SOVOL",
        "LULZBOT",
    ):
        if re.search(rf"\b{re.escape(candidate)}\b", product):
            if candidate in {"POLYLITE", "POLYTERRA"}:
                return "POLYMAKER"
            return candidate
    return vendor or "GENERIC"


def infer_material(profile: dict[str, Any], path: Path) -> str:
    search_bits = [
        path.stem,
        scalar(profile.get("name")),
        scalar(profile.get("inherits")),
        scalar(profile.get("filament_type")),
    ]
    search = normalize(" ".join(bit for bit in search_bits if bit))
    fdm_match = re.search(r"\bFDM FILAMENT ([A-Z0-9]+(?: [A-Z0-9]+)?)\b", search)
    if fdm_match:
        token = fdm_match.group(1)
        if token in MATERIAL_NAME_MAP:
            return MATERIAL_NAME_MAP[token]
    for token in MATERIAL_SCAN_ORDER:
        if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", search):
            return MATERIAL_NAME_MAP[token]
    return ""


def load_polymaker_product_prices(catalog_path: Path) -> dict[str, PriceSource]:
    catalog = load_json(catalog_path)
    prices: dict[str, PriceSource] = {}
    for entry in catalog.get("materials", []):
        settings = entry.get("settings") or {}
        source = settings.get("priceSource") or {}
        cost = floatish(settings.get("filament_cost"))
        if cost <= 0:
            continue
        material = normalize(entry.get("material", ""))
        prices[material] = PriceSource(
            cost,
            source.get("source") or "Polymaker shop current product feed",
            source.get("sourceUrl", ""),
            f"{source.get('variantTitle', '')}; {source.get('retailPriceUsd', '')}/{source.get('spoolWeightKg', '')}kg",
        )
    return prices


def price_for_profile(
    profile: dict[str, Any],
    path: Path,
    polymaker_prices: dict[str, PriceSource],
) -> PriceSource | None:
    product = base_product_name(profile, path)
    material = infer_material(profile, path)
    vendor = first_known_vendor(profile, path)

    if product in PRODUCT_PRICE_OVERRIDES:
        return PRODUCT_PRICE_OVERRIDES[product]
    if product in PRODUCT_MATERIAL_ALIASES and PRODUCT_MATERIAL_ALIASES[product] in polymaker_prices:
        return polymaker_prices[PRODUCT_MATERIAL_ALIASES[product]]
    if product in polymaker_prices:
        return polymaker_prices[product]
    if product.startswith("POLY") and product in PRODUCT_MATERIAL_ALIASES:
        return polymaker_prices.get(PRODUCT_MATERIAL_ALIASES[product])
    if (vendor, material) in EXACT_PRICE_OVERRIDES:
        return EXACT_PRICE_OVERRIDES[(vendor, material)]
    if vendor == "BAMBU LAB" and ("BAMBU", material) in EXACT_PRICE_OVERRIDES:
        return EXACT_PRICE_OVERRIDES[("BAMBU", material)]
    return GENERIC_PRICE_AVERAGES.get(material)


def filament_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for vendor_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        filament_dir = vendor_dir / "filament"
        if filament_dir.is_dir():
            paths.extend(sorted(filament_dir.glob("*.json")))
    return paths


def is_abstract_template(path: Path, profile: dict[str, Any]) -> bool:
    name = scalar(profile.get("name"), path.stem)
    normalized = normalize(name)
    if path.name == "filaments_color_codes.json":
        return True
    if normalized in {"FDM FILAMENT COMMON", "FDM FILAMENT DUAL COMMON"}:
        return True
    if normalized.endswith("FILAMENT BASE") and not infer_material(profile, path):
        return True
    return False


def profile_map(paths: list[Path]) -> dict[Path, dict[str, Any]]:
    return {path: load_json(path) for path in paths}


def key_map(records: dict[Path, dict[str, Any]]) -> dict[str, Path]:
    keys: dict[str, Path] = {}
    for path, profile in records.items():
        for key in {path.stem, scalar(profile.get("name"))}:
            if key:
                keys[key] = path
    return keys


def resolve_cost(
    path: Path,
    records: dict[Path, dict[str, Any]],
    keys: dict[str, Path],
    seen: set[Path] | None = None,
) -> float:
    seen = seen or set()
    if path in seen:
        return 0.0
    seen.add(path)
    profile = records[path]
    direct = floatish(profile.get("filament_cost"), 0.0)
    if direct > 0:
        return direct
    parent_name = scalar(profile.get("inherits"))
    if not parent_name:
        return 0.0
    parent_path = keys.get(parent_name)
    if not parent_path:
        return 0.0
    return resolve_cost(parent_path, records, keys, seen)


def record_change(
    changes: dict[Path, dict[str, Any]],
    path: Path,
    profile: dict[str, Any],
    price: PriceSource,
) -> None:
    set_like_existing(profile, "filament_cost", money(price.cost))
    if price.url:
        set_like_existing(profile, "filament_price_source_url", price.url)
    set_like_existing(profile, "filament_price_source", price.source)
    if price.note:
        set_like_existing(profile, "filament_price_source_note", price.note)
    changes[path] = profile


def backup_changed_files(root: Path, paths: list[Path], backup_root: Path) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S") / root.name
    for path in paths:
        target = backup / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    return backup


@dataclass
class AuditResult:
    root: Path
    total: int
    changed: int
    missing: list[str]
    backup: Path | None


def audit_root(
    root: Path,
    catalog_path: Path,
    backup_root: Path,
    apply_changes: bool,
    refresh_known: bool,
) -> AuditResult:
    if not root.is_dir():
        raise SystemExit(f"profile root not found: {root}")
    polymaker_prices = load_polymaker_product_prices(catalog_path)
    records = profile_map(filament_paths(root))
    keys = key_map(records)
    changes: dict[Path, dict[str, Any]] = {}
    missing: list[str] = []
    total = 0

    for path, profile in records.items():
        if is_abstract_template(path, profile):
            continue
        material = infer_material(profile, path)
        if not material:
            continue
        total += 1
        price = price_for_profile(profile, path, polymaker_prices)
        direct = floatish(profile.get("filament_cost"), 0.0)
        effective = resolve_cost(path, records, keys)

        if direct > 0 and price and refresh_known and abs(direct - price.cost) > 0.005:
            record_change(changes, path, profile, price)
            continue
        if effective <= 0 and price:
            record_change(changes, path, profile, price)
            continue
        if effective <= 0:
            missing.append(str(path.relative_to(root)))

    backup = None
    if changes and apply_changes:
        backup = backup_changed_files(root, sorted(changes), backup_root)
        for path, profile in sorted(changes.items()):
            write_json(path, profile)

    if apply_changes and changes:
        records = profile_map(filament_paths(root))
        keys = key_map(records)
        missing = []
        for path, profile in records.items():
            if is_abstract_template(path, profile) or not infer_material(profile, path):
                continue
            if resolve_cost(path, records, keys) <= 0:
                missing.append(str(path.relative_to(root)))

    return AuditResult(root, total, len(changes), missing, backup)


def validate_roots(roots: list[Path], catalog_path: Path) -> None:
    failures: list[str] = []
    for root in roots:
        result = audit_root(root, catalog_path, ROOT / DEFAULT_BACKUP_ROOT, False, False)
        failures.extend(f"{root}: {entry}" for entry in result.missing)
        print(f"{root}: validated {result.total} material filament profiles, missing effective cost={len(result.missing)}")
    if failures:
        raise SystemExit("Filament price-tree validation failed:\n" + "\n".join(failures[:80]))
    print("Filament price-tree validation passed: every material filament profile resolves to a positive cost.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", action="append", type=Path, dest="profile_roots")
    parser.add_argument("--catalog", type=Path, default=ROOT / CATALOG_PATH)
    parser.add_argument("--backup-root", type=Path, default=ROOT / DEFAULT_BACKUP_ROOT)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--refresh-known", action="store_true", help="refresh direct positive prices when a mapped current source exists")
    parser.add_argument("--validate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    roots = args.profile_roots or DEFAULT_PROFILE_ROOTS
    if args.validate:
        validate_roots(roots, args.catalog)
        return 0
    for root in roots:
        result = audit_root(root, args.catalog, args.backup_root, args.apply, args.refresh_known)
        verb = "updated" if args.apply else "would update"
        print(f"{root}: {verb} {result.changed} of {result.total} material filament profiles")
        if result.backup:
            print(f"Backup: {result.backup}")
        if result.missing:
            print("Remaining missing effective costs:")
            for entry in result.missing[:80]:
                print(f"  {entry}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
