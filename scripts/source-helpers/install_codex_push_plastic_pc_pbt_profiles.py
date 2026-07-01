#!/usr/bin/env python3
"""Install Push Plastic PC-PBT into the local Codex filament catalog.

The Codex filament catalog is workstation-local Application Support state, so
the public release package carries this installer instead of publishing the
full private catalog. The installer derives the PC-PBT entries from the
existing PC Codex-Generic profiles so compatible printer buckets, machine
specific start/end gcode, and local machine naming stay aligned. It also
updates the enabled filament list and mirrors active user preset sidecars,
matching how existing Codex filaments are exposed in TinManX1.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import time
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
MATERIAL = "PC-PBT"
SOURCE = "Push Plastic"
TARGET_PREFIX = f"{MATERIAL} Codex-{SOURCE}"
TEMPLATE_PREFIX = "PC Codex-Generic"
GROUPS = [
    "Creality K2 Plus",
    "Elegoo Centauri",
    "Prusa Core One",
    "Qidi X-Plus 4",
    "RatRig V-Core 4",
    "Snapmaker U1",
    "Sovol SV08 MAX",
    "Universal",
]


@dataclass
class InstallResult:
    system_profiles: list[Path]
    user_profiles: list[Path]
    user_infos: list[Path]
    enabled_count: int

PC_PBT_SETTINGS: dict[str, Any] = {
    "default_filament_colour": ["#1F1F1F"],
    "filament_cost": ["40"],
    "filament_density": ["1.2"],
    "filament_flow_ratio": ["1"],
    "filament_max_volumetric_speed": ["6"],
    "filament_type": [MATERIAL],
    "filament_vendor": ["Codex"],
    "nozzle_temperature": ["255"],
    "nozzle_temperature_initial_layer": ["255"],
    "nozzle_temperature_range_low": ["245"],
    "nozzle_temperature_range_high": ["260"],
    "hot_plate_temp": ["110"],
    "hot_plate_temp_initial_layer": ["110"],
    "eng_plate_temp": ["110"],
    "eng_plate_temp_initial_layer": ["110"],
    "textured_plate_temp": ["110"],
    "textured_plate_temp_initial_layer": ["110"],
    "activate_chamber_temp_control": ["1"],
    "chamber_temperature": ["55"],
    "fan_min_speed": ["10"],
    "fan_max_speed": ["25"],
    "overhang_fan_speed": ["25"],
    "overhang_fan_threshold": ["25%"],
    "required_nozzle_HRC": ["0"],
    "temperature_vitrification": ["110"],
    "slow_down_for_layer_cooling": ["1"],
    "slow_down_layer_time": ["8"],
    "slow_down_min_speed": ["10"],
    "is_custom_defined": "0",
    "from": "system",
    "instantiation": "true",
    "type": "filament",
    "version": "2.3.1.10",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def profile_ids(name: str) -> tuple[str, str]:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return f"codex-{digest[:12]}", f"CODX{digest[:8].upper()}"


def system_name(group: str) -> str:
    return f"{TARGET_PREFIX} - {group} @Codex"


def user_name(group: str) -> str:
    return f"{TARGET_PREFIX} - {group}"


def target_items() -> list[dict[str, str]]:
    return [
        {
            "name": system_name(group),
            "sub_path": f"filament/{system_name(group)}.json",
        }
        for group in GROUPS
    ]


def enabled_names() -> list[str]:
    return [system_name(group) for group in GROUPS]


def user_filament_dirs(app_support: Path) -> list[Path]:
    root = app_support / "user"
    if not root.is_dir():
        return []
    return sorted(path / "filament" for path in root.iterdir() if (path / "filament").is_dir())


def backup_catalog(
    index_path: Path,
    filament_dir: Path,
    app_support: Path,
    backup_root: Path,
) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(index_path, backup / "Codex.json")
    shutil.copytree(filament_dir, backup / "filament")
    conf_path = app_support / "OrcaSlicer.conf"
    if conf_path.is_file():
        shutil.copy2(conf_path, backup / "OrcaSlicer.conf")
    for user_dir in user_filament_dirs(app_support):
        relative_user_dir = user_dir.relative_to(app_support)
        for group in GROUPS:
            stem = user_name(group)
            for suffix in (".json", ".info"):
                source = user_dir / f"{stem}{suffix}"
                if source.is_file():
                    target = backup / relative_user_dir / source.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    return backup


def generated_system_profiles(filament_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    generated: list[tuple[Path, dict[str, Any]]] = []
    for group in GROUPS:
        template_path = filament_dir / f"{TEMPLATE_PREFIX} - {group} @Codex.json"
        if not template_path.is_file():
            raise SystemExit(f"missing template profile: {template_path}")
        name = system_name(group)
        setting_id, filament_id = profile_ids(name)
        profile = load_json(template_path)
        profile.update(PC_PBT_SETTINGS)
        profile["name"] = name
        profile["filament_settings_id"] = [name]
        profile["setting_id"] = setting_id
        profile["filament_id"] = filament_id
        generated.append((filament_dir / f"{name}.json", profile))
    return generated


def generated_user_profile(system_profile: dict[str, Any], group: str) -> dict[str, Any]:
    name = user_name(group)
    _, filament_id = profile_ids(name)
    profile = copy.deepcopy(system_profile)
    profile["name"] = name
    profile["from"] = "User"
    profile["filament_settings_id"] = [name]
    profile["filament_id"] = filament_id
    profile["renamed_from"] = f"Push Plastic PC-PBT - {group} Codex"
    profile.pop("setting_id", None)
    return profile


def user_info_text(user_dir: Path, group: str, updated_time: int) -> str:
    user_folder = user_dir.parent.name
    user_id = user_folder if user_folder.isdigit() else ""
    base_id = "codex-" + hashlib.sha1(f"pc-pbt:{group}:user".encode("utf-8")).hexdigest()[:12]
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


def update_enabled_filaments(app_support: Path, dry_run: bool) -> int:
    conf_path = app_support / "OrcaSlicer.conf"
    if not conf_path.is_file():
        return 0
    conf = load_json(conf_path)
    filaments = list(conf.get("filaments") or [])
    names = enabled_names()
    existing_count = sum(1 for name in names if name in filaments)
    filaments = [name for name in filaments if name not in names]
    insert_after = f"{TEMPLATE_PREFIX} - Universal @Codex"
    try:
        insert_at = filaments.index(insert_after) + 1
    except ValueError:
        insert_at = len(filaments)
    for offset, name in enumerate(names):
        filaments.insert(insert_at + offset, name)
    if not dry_run:
        conf["filaments"] = filaments
        conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=True) + "\n")
    return len(names) - existing_count


def install(app_support: Path, backup_root: Path, dry_run: bool = False) -> InstallResult:
    system_root = app_support / "system"
    index_path = system_root / "Codex.json"
    filament_dir = system_root / "Codex" / "filament"
    if not index_path.is_file():
        raise SystemExit(f"missing Codex index: {index_path}")
    if not filament_dir.is_dir():
        raise SystemExit(f"missing Codex filament directory: {filament_dir}")

    generated = generated_system_profiles(filament_dir)

    index = load_json(index_path)
    existing = [
        item for item in index.get("filament_list", [])
        if not item.get("name", "").startswith(TARGET_PREFIX)
    ]
    insert_after = max(
        (i for i, item in enumerate(existing) if item.get("name", "").startswith(TEMPLATE_PREFIX)),
        default=len(existing) - 1,
    )
    index["version"] = "00.00.01.02"
    index["filament_list"] = (
        existing[: insert_after + 1]
        + target_items()
        + existing[insert_after + 1 :]
    )

    user_profiles: list[Path] = []
    user_infos: list[Path] = []
    user_generated: list[tuple[Path, dict[str, Any], Path, str]] = []
    updated_time = int(time.time())
    for user_dir in user_filament_dirs(app_support):
        for group, (_, system_profile) in zip(GROUPS, generated):
            profile_path = user_dir / f"{user_name(group)}.json"
            info_path = user_dir / f"{user_name(group)}.info"
            user_profiles.append(profile_path)
            user_infos.append(info_path)
            user_generated.append(
                (
                    profile_path,
                    generated_user_profile(system_profile, group),
                    info_path,
                    user_info_text(user_dir, group, updated_time),
                )
            )

    enabled_count = update_enabled_filaments(app_support, dry_run=True)

    if dry_run:
        return InstallResult(
            system_profiles=[path for path, _ in generated],
            user_profiles=user_profiles,
            user_infos=user_infos,
            enabled_count=enabled_count,
        )

    backup_catalog(index_path, filament_dir, app_support, backup_root)
    for path, profile in generated:
        write_json(path, profile)
    write_json(index_path, index)
    for profile_path, profile, info_path, info_text in user_generated:
        write_json(profile_path, profile)
        info_path.write_text(info_text)
    enabled_count = update_enabled_filaments(app_support, dry_run=False)
    return InstallResult(
        system_profiles=[path for path, _ in generated],
        user_profiles=user_profiles,
        user_infos=user_infos,
        enabled_count=enabled_count,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backup_root = args.backup_root or (args.app_support / "_codex_pc_pbt_profile_backups")
    result = install(args.app_support, backup_root, args.dry_run)
    verb = "would install" if args.dry_run else "installed"
    print(f"{verb} {len(result.system_profiles)} Push Plastic PC-PBT Codex system profiles")
    print(f"{verb} {len(result.user_profiles)} active user preset JSON files")
    print(f"{verb} {len(result.user_infos)} active user preset info files")
    print(f"{verb} {result.enabled_count} enabled OrcaSlicer.conf filament entries")
    for path in result.system_profiles + result.user_profiles + result.user_infos:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
