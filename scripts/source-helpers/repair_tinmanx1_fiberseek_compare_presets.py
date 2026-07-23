#!/usr/bin/env python3
"""Repair copied TinManX1 FibreSeek Rocket Compare process presets.

User copies of Rocket Compare process presets may predate newer FibreSeek keys.
When that happens, Orca/TinMan can merge the copied preset with default values
instead of the intended composite-only compare values. This tool makes those
copies explicit by copying the fiber_* block from the matching bundled profile.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path
from typing import Any


DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
DEFAULT_APP_PROFILES = Path("/Applications/TinManX1.app/Contents/Resources/profiles/TinManX1")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--profile-root", type=Path, default=DEFAULT_APP_PROFILES)
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def dump_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def preset_identity(payload: dict[str, Any], path: Path) -> str:
    values: list[str] = []
    for key in ("name", "print_settings_id", "inherits"):
        value = payload.get(key)
        if isinstance(value, str):
            values.append(value)
    values.append(path.stem)
    return "\n".join(values)


def base_name_for(payload: dict[str, Any], path: Path) -> str | None:
    inherits = payload.get("inherits")
    if isinstance(inherits, str) and "Rocket Compare Composite Only" in inherits:
        return inherits
    for key in ("name", "print_settings_id"):
        value = payload.get(key)
        if isinstance(value, str) and "Rocket Compare Composite Only" in value:
            if value.endswith(" - Copy"):
                return value[: -len(" - Copy")]
            return value
    stem = path.stem
    if "Rocket Compare Composite Only" in stem:
        if stem.endswith(" - Copy"):
            return stem[: -len(" - Copy")]
        return stem
    return None


def bundled_process_profiles(profile_root: Path) -> dict[str, dict[str, Any]]:
    process_root = profile_root / "process"
    profiles: dict[str, dict[str, Any]] = {}
    if not process_root.is_dir():
        return profiles
    for path in process_root.glob("*Rocket Compare Composite Only*.json"):
        payload = load_json(path)
        if not payload:
            continue
        name = payload.get("name")
        if isinstance(name, str):
            profiles[name] = payload
        profiles[path.stem] = payload
    return profiles


def repair_payload(payload: dict[str, Any], base_payload: dict[str, Any]) -> bool:
    changed = False
    for key, value in base_payload.items():
        if not key.startswith("fiber_"):
            continue
        if payload.get(key) != value:
            payload[key] = value
            changed = True
    notes = base_payload.get("notes")
    if isinstance(notes, str) and payload.get("notes") != notes:
        payload["notes"] = notes
        changed = True
    return changed


def main() -> int:
    args = parse_args()
    app_support = args.app_support.expanduser()
    profile_root = args.profile_root.expanduser()
    user_root = app_support / "user"
    summary_path = args.summary.expanduser() if args.summary else None
    backup_dir = args.backup_dir.expanduser() if args.backup_dir else None

    bases = bundled_process_profiles(profile_root)
    scanned = 0
    matched = 0
    changed = 0
    missing_base: list[str] = []
    changed_files: list[str] = []

    if user_root.is_dir():
        for path in user_root.glob("*/process/*.json"):
            payload = load_json(path)
            if not payload:
                continue
            identity = preset_identity(payload, path)
            if "Rocket Compare Composite Only" not in identity:
                continue
            scanned += 1
            base_name = base_name_for(payload, path)
            base_payload = bases.get(base_name or "")
            if not base_payload:
                missing_base.append(str(path))
                continue
            matched += 1
            next_payload = dict(payload)
            if not repair_payload(next_payload, base_payload):
                continue
            changed += 1
            changed_files.append(str(path))
            if not args.dry_run:
                if backup_dir:
                    backup_path = backup_dir / path.relative_to(user_root)
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, backup_path)
                else:
                    suffix = ".backup-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
                    shutil.copy2(path, path.with_suffix(path.suffix + suffix))
                dump_json(path, next_payload)

    summary = {
        "status": "passed",
        "dry_run": args.dry_run,
        "app_support": str(app_support),
        "profile_root": str(profile_root),
        "scanned_count": scanned,
        "matched_count": matched,
        "changed_count": changed,
        "changed_files": changed_files,
        "missing_base_count": len(missing_base),
        "missing_base_files": missing_base[:50],
    }
    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(
        "TinManX1 FibreSeek compare preset repair: "
        f"scanned={scanned} matched={matched} changed={changed} missing_base={len(missing_base)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
