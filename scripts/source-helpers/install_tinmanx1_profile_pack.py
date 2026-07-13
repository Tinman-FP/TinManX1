#!/usr/bin/env python3
"""Install the generated TinManX1 FibreSeek profile pack locally."""

from __future__ import annotations

import argparse
import filecmp
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_APP_PROFILES = Path("/Applications/TinManX1.app/Contents/Resources/profiles")
DEFAULT_BACKUP_ROOT = Path("work/tinmanx1-profile-pack-backups")


@dataclass(frozen=True)
class InstallTarget:
    name: str
    root: Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "resources" / "profiles" / "TinManX1.json").is_file():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())
SOURCE_ROOT = ROOT / "resources" / "profiles"


def profile_files() -> list[Path]:
    return [Path("TinManX1.json")] + sorted(path.relative_to(SOURCE_ROOT) for path in (SOURCE_ROOT / "TinManX1").rglob("*.json"))


def backup_target(target: InstallTarget, backup_root: Path) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S") / target.name
    backup.mkdir(parents=True, exist_ok=False)
    for relative in (Path("TinManX1.json"), Path("TinManX1")):
        source = target.root / relative
        if source.is_dir():
            shutil.copytree(source, backup / relative)
        elif source.is_file():
            shutil.copy2(source, backup / relative)
    return backup


def install_target(target: InstallTarget, dry_run: bool) -> tuple[int, int]:
    changed = 0
    missing = 0
    for relative in profile_files():
        source = SOURCE_ROOT / relative
        dest = target.root / relative
        if not dest.exists():
            missing += 1
            changed += 1
            continue
        if not filecmp.cmp(source, dest, shallow=False):
            changed += 1
    if dry_run or changed == 0:
        return changed, missing

    target.root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE_ROOT / "TinManX1.json", target.root / "TinManX1.json")
    if (target.root / "TinManX1").exists():
        shutil.rmtree(target.root / "TinManX1")
    shutil.copytree(SOURCE_ROOT / "TinManX1", target.root / "TinManX1")
    return changed, missing


def validate_target(target: InstallTarget) -> list[str]:
    failures: list[str] = []
    for relative in profile_files():
        source = SOURCE_ROOT / relative
        dest = target.root / relative
        if not dest.exists():
            failures.append(f"{target.name}: missing {relative}")
        elif not filecmp.cmp(source, dest, shallow=False):
            failures.append(f"{target.name}: differs {relative}")
    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--app-profiles", type=Path, default=DEFAULT_APP_PROFILES)
    parser.add_argument("--backup-root", type=Path, default=ROOT / DEFAULT_BACKUP_ROOT)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--validate", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = [
        InstallTarget("app-bundle", args.app_profiles),
        InstallTarget("app-support-system", args.app_support / "system"),
    ]
    if args.validate:
        failures: list[str] = []
        for target in targets:
            failures.extend(validate_target(target))
        if failures:
            raise SystemExit("TinManX1 profile-pack validation failed:\n" + "\n".join(failures[:40]))
        print(f"TinManX1 profile-pack validation passed: {len(profile_files())} files match both live destinations.")
        return 0

    for target in targets:
        changed, missing = install_target(target, dry_run=True)
        print(f"{target.name}: {'would update' if args.dry_run else 'updating'} {changed} file(s), missing={missing}")
        if changed and not args.dry_run:
            backup = backup_target(target, args.backup_root)
            install_target(target, dry_run=False)
            print(f"{target.name} backup: {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
