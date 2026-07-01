#!/usr/bin/env python3
"""Install Push Plastic PC-PBT into the local Codex filament catalog.

The Codex filament catalog is workstation-local Application Support state, so
the public release package carries this installer instead of publishing the
full private catalog. The installer derives the PC-PBT entries from the
existing PC Codex-Generic profiles so compatible printer buckets, machine
specific start/end gcode, and local machine naming stay aligned.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime
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


def target_items() -> list[dict[str, str]]:
    return [
        {
            "name": f"{TARGET_PREFIX} - {group} @Codex",
            "sub_path": f"filament/{TARGET_PREFIX} - {group} @Codex.json",
        }
        for group in GROUPS
    ]


def backup_catalog(index_path: Path, filament_dir: Path, backup_root: Path) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    shutil.copy2(index_path, backup / "Codex.json")
    shutil.copytree(filament_dir, backup / "filament")
    return backup


def install(app_support: Path, backup_root: Path, dry_run: bool = False) -> list[Path]:
    system_root = app_support / "system"
    index_path = system_root / "Codex.json"
    filament_dir = system_root / "Codex" / "filament"
    if not index_path.is_file():
        raise SystemExit(f"missing Codex index: {index_path}")
    if not filament_dir.is_dir():
        raise SystemExit(f"missing Codex filament directory: {filament_dir}")

    generated: list[tuple[Path, dict[str, Any]]] = []
    for group in GROUPS:
        template_path = filament_dir / f"{TEMPLATE_PREFIX} - {group} @Codex.json"
        if not template_path.is_file():
            raise SystemExit(f"missing template profile: {template_path}")
        name = f"{TARGET_PREFIX} - {group} @Codex"
        setting_id, filament_id = profile_ids(name)
        profile = load_json(template_path)
        profile.update(PC_PBT_SETTINGS)
        profile["name"] = name
        profile["filament_settings_id"] = [name]
        profile["setting_id"] = setting_id
        profile["filament_id"] = filament_id
        generated.append((filament_dir / f"{name}.json", profile))

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

    if dry_run:
        return [path for path, _ in generated]

    backup_catalog(index_path, filament_dir, backup_root)
    for path, profile in generated:
        write_json(path, profile)
    write_json(index_path, index)
    return [path for path, _ in generated]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    backup_root = args.backup_root or (args.app_support / "_codex_pc_pbt_profile_backups")
    paths = install(args.app_support, backup_root, args.dry_run)
    verb = "would install" if args.dry_run else "installed"
    print(f"{verb} {len(paths)} Push Plastic PC-PBT Codex profiles")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
