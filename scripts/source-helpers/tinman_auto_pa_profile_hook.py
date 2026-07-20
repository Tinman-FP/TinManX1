#!/usr/bin/env python3
from __future__ import annotations

"""Wire TinManX1 auto-PA post-processing into selected local process presets."""

import argparse
import datetime as dt
import json
import shutil
import stat
from pathlib import Path
from typing import Any


DEFAULT_DATADIR = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
DEFAULT_APP = Path("/Applications/TinManX1.app")
WRAPPER_REL = Path("Contents/Resources/orcaslicer_codex/auto_pa/tinman_auto_pa_postprocess.py")


TARGET_MARKERS = (
    "qidi x-plus 4",
    "qidi xplus4",
    "qidi plus 4",
    "qidi plus4",
    "qidi-xplus-4",
    "qidimaxez",
    "max ez",
    "ratrig v-core 4",
    "rat rig v-core 4",
    "prusa core one",
    "prusa_core_one",
)


def load_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def profile_targets(data: dict[str, Any]) -> bool:
    fields: list[str] = []
    for key in (
        "name",
        "print_settings_id",
        "inherits",
        "compatible_printers",
        "compatible_printers_condition",
        "printer_settings_id",
    ):
        value = data.get(key)
        if isinstance(value, list):
            fields.extend(str(item) for item in value)
        elif value is not None:
            fields.append(str(value))
    haystack = " ".join(fields).lower()
    return any(marker in haystack for marker in TARGET_MARKERS)


def normalize_post_process(value: Any) -> list[str]:
    if isinstance(value, list):
        items = [str(item) for item in value if str(item).strip()]
    elif isinstance(value, str) and value.strip():
        items = [line.strip() for line in value.splitlines() if line.strip()]
    else:
        items = []
    return [item for item in items if "tinman_auto_pa_postprocess.py" not in item]


def process_dirs(datadir: Path, include_system: bool) -> list[Path]:
    roots: list[Path] = []
    user_root = datadir / "user"
    if user_root.exists():
        for child in sorted(user_root.iterdir()):
            process = child / "process"
            if process.is_dir():
                roots.append(process)
    if include_system:
        for process in sorted(datadir.glob("system/*/process")):
            if process.is_dir():
                roots.append(process)
    return roots


def backup_path(backup_root: Path, datadir: Path, source: Path) -> Path:
    try:
        rel = source.relative_to(datadir)
    except ValueError:
        rel = Path(source.name)
    return backup_root / rel


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", type=Path, default=DEFAULT_DATADIR)
    parser.add_argument("--wrapper", type=Path, default=DEFAULT_APP / WRAPPER_REL)
    parser.add_argument("--include-system", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    wrapper = args.wrapper.expanduser().resolve()
    if not wrapper.exists():
        raise SystemExit(f"wrapper not found: {wrapper}")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = args.datadir / f"_tinman_auto_pa_postprocess_backup_{timestamp}"
    changed: list[str] = []
    unchanged: list[str] = []
    skipped: list[str] = []

    for process_dir in process_dirs(args.datadir, args.include_system):
        for path in sorted(process_dir.glob("*.json")):
            data = load_json(path)
            if data is None:
                skipped.append(str(path))
                continue
            if not profile_targets(data):
                continue
            current = normalize_post_process(data.get("post_process"))
            desired = [str(wrapper), *current]
            if data.get("post_process") == desired:
                unchanged.append(str(path))
                continue
            changed.append(str(path))
            if args.dry_run:
                continue
            dst = backup_path(backup_root, args.datadir, path)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            data["post_process"] = desired
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    summary = {
        "dry_run": args.dry_run,
        "datadir": str(args.datadir),
        "wrapper": str(wrapper),
        "include_system": args.include_system,
        "backup_root": "" if args.dry_run or not changed else str(backup_root),
        "changed_count": len(changed),
        "unchanged_count": len(unchanged),
        "skipped_invalid_json_count": len(skipped),
        "changed": changed,
        "unchanged": unchanged,
        "skipped_invalid_json": skipped,
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
