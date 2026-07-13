#!/usr/bin/env python3
"""Repair active chamber-control flags in installed manufacturer profile trees.

The generated TinManX1/Codex profiles are only part of what the UI exposes.
The installed Orca/TinManX1 profile trees also contain machine-specific
filament presets for Prusa CORE One, Qidi X-Plus 4, Sovol SV08 MAX, Creality,
and Bambu H2D. Many of those upstream presets include chamber target
temperatures but leave `activate_chamber_temp_control` unset or disabled.
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


DEFAULT_APP_PROFILES = Path("/Applications/TinManX1.app/Contents/Resources/profiles")
DEFAULT_APP_SUPPORT_SYSTEM = Path.home() / "Library/Application Support/OrcaSlicer-Codex/system"
DEFAULT_BACKUP_ROOT = Path("work/tinmanx1-active-chamber-profile-tree-backups")


@dataclass(frozen=True)
class ProfileRoot:
    label: str
    root: Path


TARGET_TERMS = {
    "BBL": ("H2D", "H2DP"),
    "Creality": ("Creality", "@K1", "@K2", "@Hi", "@Ender-5Max", "@Ender-3 V4", "@Ender-5 Max"),
    "Prusa": ("CORE One",),
    "Qidi": ("X-Plus 4", "Plus 4", "Max EZ", "MaxEZ"),
    "Sovol": ("SV08 MAX",),
}


TREE_FALLBACK_CHAMBERS = {
    "Sovol": {
        "ABS": 35,
        "ASA": 35,
        "PC": 35,
        "PC-CF": 35,
        "ABS-CF": 35,
        "ABS-GF": 35,
    },
    "Qidi": {
        "ABS": 55,
        "ABS-GF": 55,
        "ABS-CF": 55,
        "ASA": 55,
        "ASA-CF": 55,
        "ASA-AERO": 60,
        "PC": 55,
        "PC-CF": 55,
        "PC-ABS": 55,
        "PA": 60,
        "PA-CF": 60,
        "PA-GF": 60,
        "PA12-CF": 60,
        "PAHT": 60,
        "PAHT-CF": 60,
        "PAHT-GF": 60,
        "PPS": 60,
        "PPS-CF": 60,
        "PPS-GF": 55,
        "ULTRAPA": 60,
    },
}

MATERIAL_TOKENS = (
    "PAHT-CF",
    "PAHT-GF",
    "PA12-CF",
    "PA11-CF",
    "PA6-CF",
    "PPA-CF",
    "PPA-GF",
    "PPS-CF",
    "PPS-GF",
    "PETG-CF",
    "PETG-GF",
    "PET-CF",
    "PET-GF",
    "ABS-GF25",
    "ABS-GF10",
    "ABS-GF",
    "ABS-CF",
    "ASA-CF",
    "ASA-AERO",
    "PC-ABS-FR",
    "PC-ABS",
    "PC-CF",
    "PLA-CF",
    "TPU-GF",
    "PA-CF",
    "PA-GF",
    "PAHT",
    "ULTRAPA",
    "PCTG-CF",
    "PCTG",
    "PETG",
    "ASA",
    "ABS",
    "HIPS",
    "TPU",
    "FLEX",
    "PVB",
    "PLA",
    "PVA",
    "PC",
    "PA",
    "PP",
)


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


def scalar(value: Any, fallback: str = "") -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    if value is None:
        return fallback
    return str(value)


def set_profile_value(profile: dict[str, Any], key: str, value: str) -> None:
    if key in profile and not isinstance(profile[key], list):
        profile[key] = value
    else:
        profile[key] = [value]


def numeric_text(value: Any) -> str:
    text = scalar(value)
    try:
        number = float(text)
    except ValueError:
        return ""
    if number <= 0:
        return ""
    return str(int(number)) if number.is_integer() else f"{number:g}"


def positive_chamber(profile: dict[str, Any]) -> str:
    return numeric_text(profile.get("chamber_temperature") or profile.get("chamber_temperatures"))


def profile_text(profile: dict[str, Any]) -> str:
    parts = [scalar(profile.get("name"))]
    parts.extend(str(item) for item in profile.get("compatible_printers", []) if item)
    parts.append(scalar(profile.get("filament_type")))
    parts.append(scalar(profile.get("filament_settings_id")))
    parts.append(scalar(profile.get("inherits")))
    return " ".join(parts)


def profile_applies(vendor: str, profile: dict[str, Any]) -> bool:
    text = profile_text(profile)
    return any(term.lower() in text.lower() for term in TARGET_TERMS[vendor])


def normalize_material_token(token: str) -> str:
    token = token.upper().strip()
    if token in {"FLEX"}:
        return "TPU"
    if token.startswith("ABS-GF"):
        return "ABS-GF"
    if token == "PC-ABS-FR":
        return "PC-ABS"
    if token.startswith("ULTRAPA"):
        return "ULTRAPA"
    return token


def detect_material(profile: dict[str, Any]) -> str:
    typed = normalize_material_token(scalar(profile.get("filament_type")))
    if typed and typed not in {"QIDI", "PRUSA", "BAMBU", "GENERIC", "CREALITY", "SOVOL", "POLYLITE", "HATCHBOX", "OVERTURE", "SUNLU"}:
        return typed
    text = profile_text(profile).upper()
    for token in MATERIAL_TOKENS:
        if re.search(rf"(?<![A-Z0-9]){re.escape(token)}(?![A-Z0-9])", text):
            return normalize_material_token(token)
    return typed


def resolve_inherited_chamber(profile: dict[str, Any], profiles_by_name: dict[str, dict[str, Any]], depth: int = 0) -> str:
    chamber = positive_chamber(profile)
    if chamber:
        return chamber
    if depth >= 8:
        return ""
    parent = scalar(profile.get("inherits"))
    if parent and parent in profiles_by_name:
        return resolve_inherited_chamber(profiles_by_name[parent], profiles_by_name, depth + 1)
    return ""


def desired_chamber(vendor: str, profile: dict[str, Any], profiles_by_name: dict[str, dict[str, Any]]) -> str:
    inherited = resolve_inherited_chamber(profile, profiles_by_name)
    if inherited:
        return inherited
    material = detect_material(profile)
    fallback = TREE_FALLBACK_CHAMBERS.get(vendor, {}).get(material)
    return str(fallback) if fallback else ""


def audit_file(vendor: str, path: Path, profiles_by_name: dict[str, dict[str, Any]]) -> tuple[dict[str, Any] | None, list[str]]:
    profile = load_json(path)
    if not profile_applies(vendor, profile):
        return None, []
    chamber = desired_chamber(vendor, profile, profiles_by_name)
    if not chamber:
        return None, []

    changes: list[str] = []
    current_chamber = positive_chamber(profile)
    if current_chamber != chamber:
        set_profile_value(profile, "chamber_temperature", chamber)
        changes.append("chamber")
    if scalar(profile.get("activate_chamber_temp_control")) != "1":
        set_profile_value(profile, "activate_chamber_temp_control", "1")
        changes.append("active")
    return (profile, changes) if changes else (None, [])


def vendor_profiles(root: Path, vendor: str) -> list[Path]:
    directory = root / vendor / "filament"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def load_vendor_profiles(root: Path, vendor: str) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in vendor_profiles(root, vendor):
        profile = load_json(path)
        profiles[path.stem] = profile
        name = scalar(profile.get("name"))
        if name:
            profiles[name] = profile
    return profiles


def backup_root(target: ProfileRoot, backup_root_path: Path) -> Path:
    backup = backup_root_path / datetime.now().strftime("%Y%m%d_%H%M%S") / target.label
    backup.mkdir(parents=True, exist_ok=False)
    for vendor in TARGET_TERMS:
        source = target.root / vendor / "filament"
        if source.is_dir():
            shutil.copytree(source, backup / vendor / "filament")
    return backup


def audit_target(target: ProfileRoot, backup_root_path: Path, dry_run: bool) -> tuple[int, dict[str, int], Path | None]:
    changed: dict[Path, dict[str, Any]] = {}
    counts: dict[str, int] = {}
    for vendor in TARGET_TERMS:
        profiles_by_name = load_vendor_profiles(target.root, vendor)
        for path in vendor_profiles(target.root, vendor):
            updated, changes = audit_file(vendor, path, profiles_by_name)
            if not updated:
                continue
            changed[path] = updated
            for change in changes:
                counts[f"{vendor}:{change}"] = counts.get(f"{vendor}:{change}", 0) + 1

    backup = None
    if changed and not dry_run:
        backup = backup_root(target, backup_root_path)
        for path, profile in changed.items():
            write_json(path, profile)
    return len(changed), counts, backup


def validate_target(target: ProfileRoot) -> list[str]:
    failures: list[str] = []
    for vendor in TARGET_TERMS:
        profiles_by_name = load_vendor_profiles(target.root, vendor)
        for path in vendor_profiles(target.root, vendor):
            profile = load_json(path)
            if not profile_applies(vendor, profile):
                continue
            chamber = desired_chamber(vendor, profile, profiles_by_name)
            if not chamber:
                continue
            current_chamber = positive_chamber(profile)
            active = scalar(profile.get("activate_chamber_temp_control"))
            if current_chamber != chamber or active != "1":
                name = scalar(profile.get("name"), path.stem)
                failures.append(f"{target.label}/{vendor}: {name}: chamber={current_chamber or '<unset>'} wanted={chamber} active={active or '<unset>'}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-profiles", type=Path, default=DEFAULT_APP_PROFILES)
    parser.add_argument("--app-support-system", type=Path, default=DEFAULT_APP_SUPPORT_SYSTEM)
    parser.add_argument("--backup-root", type=Path, default=ROOT / DEFAULT_BACKUP_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = [
        ProfileRoot("app-bundle", args.app_profiles),
        ProfileRoot("app-support-system", args.app_support_system),
    ]
    if args.validate:
        failures: list[str] = []
        for target in targets:
            failures.extend(validate_target(target))
        if failures:
            raise SystemExit("Active chamber profile-tree validation failed:\n" + "\n".join(failures[:80]))
        print("Active chamber profile-tree validation passed for BBL H2D, Creality, Prusa CORE One, Qidi X-Plus 4, and Sovol SV08 MAX targets.")
        return 0

    for target in targets:
        changed, counts, backup = audit_target(target, args.backup_root, args.dry_run)
        print(f"{target.label}: {'would update' if args.dry_run else 'updated'} {changed} profile file(s)")
        for key, count in sorted(counts.items()):
            print(f"  {key}: {count}")
        if backup:
            print(f"  backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
