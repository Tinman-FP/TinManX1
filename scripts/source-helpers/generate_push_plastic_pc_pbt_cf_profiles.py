#!/usr/bin/env python3
"""Generate and install Push Plastic Carbon Fiber PC+PBT profiles.

Push Plastic publishes a 250-260 C nozzle range, 90-100 C bed range, and a
hardened 0.4 mm or larger nozzle requirement (0.6 mm recommended).  The Codex
profiles retain each printer bucket's compatibility and machine-owned gcode,
then apply that material contract consistently.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "resources/profiles"
CODEX_DIR = PROFILES / "Codex/filament"
TINMAN_DIR = PROFILES / "TinManX1/filament"
DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_BACKUP_ROOT = Path.home() / ".tinmanx1/pc-pbt-cf-profile-backups"

MATERIAL = "PC-PBT-CF"
MANUFACTURER = "Push Plastic"
PRICE_PER_KG = "99.98"
PRODUCT_URL = "https://www.pushplastic.com/products/carbon-fiber-pc-pbt-filament-1-75mm-500g"
PRICE_SOURCE = "Push Plastic Carbon Fiber PC+PBT 500 g spool, normalized to 1 kg"

GROUPS = (
    ("Bambu H2D", "Bambu H2D"),
    ("Bambu X1C HF", "Bambu X1C HF"),
    ("Creality K2 Plus", "Creality K2 Plus"),
    ("Elegoo Centauri", "Elegoo Centauri"),
    ("Prusa Core One", "Prusa CORE One L"),
    ("Qidi X-Plus 4", "Qidi X-Plus 4"),
    ("RatRig V-Core 4", "RatRig V-Core 4"),
    ("Snapmaker U1", "Snapmaker U1"),
    ("Sovol SV08 MAX", "Sovol SV08 MAX"),
)

FIBERSEEK_SOURCE_STEMS = (
    "TinManX1 Push Plastic PC-PBT base",
    "TinManX1 Push Plastic PC-PBT @FibreSeek Seeker 3",
    "CFC Push Plastic PC-PBT + X-CCF @FibreSeek Seeker 3",
    "CFC Push Plastic PC-PBT + CGF @FibreSeek Seeker 3",
    "CFC Push Plastic PC-PBT + CKF @FibreSeek Seeker 3",
    "CFC Push Plastic PC-PBT + CBF @FibreSeek Seeker 3",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def scalar(value: Any, fallback: str = "") -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    return fallback if value is None else str(value)


def stable_ids(name: str) -> tuple[str, str]:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"codex-{digest[:12]}", f"CODX{digest[:8].upper()}"


def codex_name(display_group: str) -> str:
    return f"{MATERIAL} Codex-{MANUFACTURER} - {display_group} @Codex"


def material_settings(active_chamber: bool, flow_ratio: str, *, prusa: bool) -> dict[str, Any]:
    settings: dict[str, Any] = {
        "default_filament_colour": ["#161616"],
        "filament_cost": [PRICE_PER_KG],
        "filament_density": ["1.2"],
        "filament_flow_ratio": [flow_ratio],
        "filament_max_volumetric_speed": ["6"],
        "filament_type": ["PC" if prusa else MATERIAL],
        "filament_vendor": ["Codex"],
        "nozzle_temperature": ["255"],
        "nozzle_temperature_initial_layer": ["260"],
        "nozzle_temperature_range_low": ["250"],
        "nozzle_temperature_range_high": ["260"],
        "hot_plate_temp": ["100"],
        "hot_plate_temp_initial_layer": ["100"],
        "eng_plate_temp": ["100"],
        "eng_plate_temp_initial_layer": ["100"],
        "textured_plate_temp": ["100"],
        "textured_plate_temp_initial_layer": ["100"],
        "activate_chamber_temp_control": ["1" if active_chamber else "0"],
        "chamber_temperature": ["55" if active_chamber else "0"],
        "chamber_temperatures": ["55" if active_chamber else "0"],
        "fan_min_speed": ["10"],
        "fan_max_speed": ["25"],
        "overhang_fan_speed": ["25"],
        "required_nozzle_HRC": ["40"],
        "filament_price_source": [PRICE_SOURCE],
        "filament_price_source_url": [PRODUCT_URL],
        "description": (
            "Push Plastic Carbon Fiber PC+PBT profile based on the manufacturer's "
            "250-260 C nozzle, 90-100 C bed, and hardened-nozzle guidance."
        ),
        "filament_notes": [
            "Dry before printing. Use a hardened 0.4 mm or larger nozzle; Push Plastic recommends 0.6 mm."
        ],
    }
    return settings


def generate_codex_profiles() -> list[tuple[str, dict[str, Any]]]:
    generated: list[tuple[str, dict[str, Any]]] = []
    for source_group, display_group in GROUPS:
        source_path = CODEX_DIR / f"PC-PBT Codex-Push Plastic - {source_group} @Codex.json"
        cf_path = CODEX_DIR / f"PC-CF Codex-Generic - {source_group} @Codex.json"
        source = load_json(source_path)
        cf_source = load_json(cf_path)
        name = codex_name(display_group)
        setting_id, filament_id = stable_ids(name)
        active_chamber = scalar(source.get("activate_chamber_temp_control")) == "1"
        flow_ratio = scalar(cf_source.get("filament_flow_ratio"), "1")
        source.update(
            material_settings(
                active_chamber,
                flow_ratio,
                prusa=source_group == "Prusa Core One",
            )
        )
        source.update(
            {
                "name": name,
                "filament_settings_id": [name],
                "setting_id": setting_id,
                "filament_id": filament_id,
                "from": "system",
                "type": "filament",
                "instantiation": "true",
            }
        )
        generated.append((name, source))
    return generated


def replace_pc_pbt(value: Any) -> Any:
    if isinstance(value, str):
        return value.replace("PC-PBT", "PC-PBT-CF").replace("pc-pbt", "pc-pbt-cf")
    if isinstance(value, list):
        return [replace_pc_pbt(item) for item in value]
    if isinstance(value, dict):
        return {key: replace_pc_pbt(item) for key, item in value.items()}
    return value


def generate_fiberseek_profiles() -> list[tuple[str, dict[str, Any]]]:
    generated: list[tuple[str, dict[str, Any]]] = []
    for stem in FIBERSEEK_SOURCE_STEMS:
        source = replace_pc_pbt(load_json(TINMAN_DIR / f"{stem}.json"))
        name = str(source["name"])
        source.update(
            {
                "filament_cost": [PRICE_PER_KG],
                "filament_density": ["1.2"],
                "filament_flow_ratio": ["0.98"],
                "filament_max_volumetric_speed": ["6"],
                "nozzle_temperature": ["255"],
                "nozzle_temperature_initial_layer": ["260"],
                "nozzle_temperature_range_low": ["250"],
                "nozzle_temperature_range_high": ["260"],
                "hot_plate_temp": ["100"],
                "hot_plate_temp_initial_layer": ["100"],
                "cool_plate_temp": ["100"],
                "cool_plate_temp_initial_layer": ["100"],
                "eng_plate_temp": ["100"],
                "eng_plate_temp_initial_layer": ["100"],
                "textured_plate_temp": ["100"],
                "textured_plate_temp_initial_layer": ["100"],
                "chamber_temperature": ["55"],
                "activate_chamber_temp_control": ["1"],
                "required_nozzle_HRC": ["40"],
                "filament_price_source": [PRICE_SOURCE],
                "filament_price_source_url": [PRODUCT_URL],
            }
        )
        if name.startswith("CFC "):
            source["fiber_plastic_cost"] = [PRICE_PER_KG]
            source["fiber_plastic_density"] = ["1.2"]
            source["fiber_nozzle_temperature_preheat"] = ["260"]
        generated.append((name, source))
    return generated


def merge_manifest(path: Path, names: list[str]) -> None:
    data = load_json(path)
    targets = set(names)
    items = [item for item in data.get("filament_list", []) if item.get("name") not in targets]
    for name in names:
        source_name = name.replace("PC-PBT-CF", "PC-PBT")
        source_name = source_name.replace("Prusa CORE One L", "Prusa Core One")
        insert_at = next(
            (index + 1 for index, item in enumerate(items) if item.get("name") == source_name),
            len(items),
        )
        items.insert(insert_at, {"name": name, "sub_path": f"filament/{name}.json"})
    data["filament_list"] = items
    indent = 2 if path.name == "TinManX1.json" else 4
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=True) + "\n")


def write_repo() -> tuple[list[str], list[str]]:
    codex = generate_codex_profiles()
    fiberseek = generate_fiberseek_profiles()
    for name, profile in codex:
        write_json(CODEX_DIR / f"{name}.json", profile)
    for name, profile in fiberseek:
        write_json(TINMAN_DIR / f"{name}.json", profile)
    merge_manifest(PROFILES / "Codex.json", [name for name, _ in codex])
    merge_manifest(PROFILES / "TinManX1.json", [name for name, _ in fiberseek])
    return [name for name, _ in codex], [name for name, _ in fiberseek]


def user_dirs(app_support: Path) -> list[Path]:
    root = app_support / "user"
    if not root.is_dir():
        return []
    return sorted(path / "filament" for path in root.iterdir() if (path / "filament").is_dir())


def user_profile(system_profile: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(system_profile)
    system_name = str(data["name"])
    name = system_name.removesuffix(" @Codex")
    _, filament_id = stable_ids(name)
    data["name"] = name
    data["filament_settings_id"] = [name]
    data["filament_id"] = filament_id
    data["from"] = "User"
    data.pop("setting_id", None)
    return data


def info_text(user_dir: Path, name: str) -> str:
    user_folder = user_dir.parent.name
    user_id = user_folder if user_folder.isdigit() else ""
    base_id = "codex-" + hashlib.sha1(f"{user_folder}:{name}".encode("utf-8")).hexdigest()[:12]
    return "\n".join(
        (
            "sync_info = ",
            f"user_id = {user_id}",
            "setting_id = ",
            f"base_id = {base_id}",
            f"updated_time = {int(time.time())}",
            "",
        )
    )


def install_live(app_support: Path, backup_root: Path) -> int:
    dirs = user_dirs(app_support)
    conf_path = app_support / "OrcaSlicer.conf"
    if not conf_path.is_file() or not dirs:
        raise SystemExit(f"TinManX1 user catalog is unavailable under {app_support}")
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(conf_path, backup / "OrcaSlicer.conf")
    profiles = generate_codex_profiles()
    for directory in dirs:
        target_backup = backup / directory.relative_to(app_support)
        for system_name, profile in profiles:
            name = system_name.removesuffix(" @Codex")
            for suffix in (".json", ".info"):
                target = directory / f"{name}{suffix}"
                if target.is_file():
                    target_backup.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, target_backup / target.name)
            write_json(directory / f"{name}.json", user_profile(profile))
            (directory / f"{name}.info").write_text(info_text(directory, name))

    conf = load_json(conf_path)
    enabled = list(conf.get("filaments") or [])
    names = [name for name, _ in profiles]
    enabled = [name for name in enabled if name not in names]
    enabled.extend(names)
    conf["filaments"] = sorted(dict.fromkeys(enabled), key=str.lower)
    write_json(conf_path, conf)
    return len(dirs) * len(profiles)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-repo", action="store_true")
    parser.add_argument("--install-live", action="store_true")
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    args = parser.parse_args()
    if not args.write_repo and not args.install_live:
        parser.error("select --write-repo and/or --install-live")
    if args.write_repo:
        codex, fiberseek = write_repo()
        print(f"generated {len(codex)} Codex and {len(fiberseek)} FibreSeek source profiles")
    if args.install_live:
        count = install_live(args.app_support, args.backup_root)
        print(f"installed {count} active user profile copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
