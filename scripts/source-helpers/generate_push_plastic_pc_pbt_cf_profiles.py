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
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT / "scripts"
PROFILES = ROOT / "resources/profiles"
CODEX_DIR = PROFILES / "Codex/filament"
DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_BACKUP_ROOT = Path.home() / ".tinmanx1/pc-pbt-cf-profile-backups"

sys.path.insert(0, str(SCRIPTS_DIR))

from assign_vendor_setting_ids import generate_preset_setting_id

MATERIAL = "PC-PBT-CF"
MANUFACTURER = "Push Plastic"
PRUSA_CORE_ONE_FILAMENT_TOKEN = "PCPBTCF"
PRICE_PER_KG = "99.98"
PRODUCT_URL = "https://www.pushplastic.com/products/carbon-fiber-pc-pbt-filament-1-75mm-500g"
PRICE_SOURCE = "Push Plastic Carbon Fiber PC+PBT 500 g spool, normalized to 1 kg"

# Prusa's CORE One engineering-filament presets set pressure advance in the
# filament start gcode, with a nozzle-size lookup, rather than Orca's generic
# pressure-advance toggle. Keep the CORE One L on that firmware-native path and
# preserve TinMan's optional chamber-exhaust command after it.
PRUSA_FILAMENT_START_GCODE = """; Filament gcode
M900 K{if nozzle_diameter[filament_extruder_id]==0.4}0.07{elsif nozzle_diameter[filament_extruder_id]==0.3}0.09{elsif nozzle_diameter[filament_extruder_id]==0.35}0.08{elsif nozzle_diameter[filament_extruder_id]==0.6}0.04{elsif nozzle_diameter[filament_extruder_id]==0.5}0.05{elsif nozzle_diameter[filament_extruder_id]==0.8}0.02{else}0{endif}
M572 S{if nozzle_diameter[filament_extruder_id]==0.4}0.05{elsif nozzle_diameter[filament_extruder_id]==0.5}0.035{elsif nozzle_diameter[filament_extruder_id]==0.6}0.025{elsif nozzle_diameter[filament_extruder_id]==0.8}0.016{elsif nozzle_diameter[filament_extruder_id]==0.25}0.14{elsif nozzle_diameter[filament_extruder_id]==0.3}0.09{else}0{endif}
M142 S45 ; set heatbreak target temp
{if activate_air_filtration[current_extruder] && support_air_filtration}
M106 P3 S{during_print_exhaust_fan_speed_num[current_extruder]}
{endif}"""

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
    return generate_preset_setting_id("Codex", "filament", name), f"CODX{digest[:8].upper()}"


def codex_name(display_group: str) -> str:
    return f"{MATERIAL} Codex-{MANUFACTURER} - {display_group} @Codex"


def material_settings(
    active_chamber: bool,
    flow_ratio: str,
    *,
    prusa: bool,
    qidi_high_flow: bool,
) -> dict[str, Any]:
    chamber_target = "40" if prusa else ("55" if active_chamber else "0")
    settings: dict[str, Any] = {
        "default_filament_colour": ["#161616"],
        "filament_cost": [PRICE_PER_KG],
        "filament_density": ["1.2"],
        "filament_flow_ratio": [flow_ratio],
        "filament_max_volumetric_speed": ["10" if prusa else ("8" if qidi_high_flow else "6")],
        # Prusa firmware compares this metadata byte-for-byte with the loaded
        # filament name. Its custom-material field is limited to seven ASCII
        # characters, and the CORE One L uses PCPBTCF for this material.
        "filament_type": [PRUSA_CORE_ONE_FILAMENT_TOKEN if prusa else MATERIAL],
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
        "activate_chamber_temp_control": ["0" if prusa else ("1" if active_chamber else "0")],
        "chamber_temperature": [chamber_target],
        "chamber_temperatures": [chamber_target],
        "fan_min_speed": ["15" if prusa else "10"],
        "fan_max_speed": ["35" if prusa else "25"],
        "overhang_fan_speed": ["45" if prusa else "25"],
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
    if prusa:
        settings.update(
            {
                "slow_down_layer_time": ["20"],
                # This documents the active 0.6 mm value for profile audits;
                # the nozzle-aware M572 command above is what programs it.
                "enable_pressure_advance": ["0"],
                "pressure_advance": ["0.025"],
                "filament_start_gcode": [PRUSA_FILAMENT_START_GCODE],
            }
        )
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
                qidi_high_flow=source_group == "Qidi X-Plus 4",
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


def write_repo() -> list[str]:
    codex = generate_codex_profiles()
    for name, profile in codex:
        write_json(CODEX_DIR / f"{name}.json", profile)
    merge_manifest(PROFILES / "Codex.json", [name for name, _ in codex])
    return [name for name, _ in codex]


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
        codex = write_repo()
        print(f"generated {len(codex)} Codex source profiles")
    if args.install_live:
        count = install_live(args.app_support, args.backup_root)
        print(f"installed {count} active user profile copies")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
