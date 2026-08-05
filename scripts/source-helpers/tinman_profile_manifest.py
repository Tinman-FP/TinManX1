#!/usr/bin/env python3
"""Build or verify the TinManX1 shipped-profile checksum manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import shutil
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "resources" / "profiles"
MANIFEST = ROOT / "manifests" / "tinmanx1-profile-resources.sha256"
MACHINE_HELPER = ROOT / "scripts" / "source-helpers" / "normalize_tinman_machine_catalog.py"
PET_CF_HELPER = ROOT / "scripts" / "source-helpers" / "repair_tinman_pet_cf_contract.py"
DEFAULT_APP_PROFILES = Path("/Applications/TinManX1.app/Contents/Resources/profiles")
DEFAULT_SYSTEM_PROFILES = Path.home() / "Library/Application Support/OrcaSlicer-Codex/system"
DEFAULT_BACKUP_ROOT = Path.home() / ".tinmanx1" / "profile-deployment-backups"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def curated_paths() -> list[Path]:
    contract = runpy.run_path(str(MACHINE_HELPER))
    families = contract["FAMILIES"]
    vendors = sorted({family.vendor for family in families})
    paths: set[Path] = {Path("Codex.json"), Path("TinManX1.json")}

    for directory in (PROFILES / "Codex", PROFILES / "TinManX1"):
        paths.update(path.relative_to(PROFILES) for path in directory.rglob("*.json"))

    for vendor in vendors:
        paths.add(Path(f"{vendor}.json"))
        for profile_type in ("machine", "process"):
            directory = PROFILES / vendor / profile_type / "TinMan Codex"
            paths.update(path.relative_to(PROFILES) for path in directory.glob("*.json"))
        index = json.loads((PROFILES / f"{vendor}.json").read_text())
        target_models = {family.model for family in families if family.vendor == vendor}
        for item in index.get("machine_model_list", []):
            if item.get("name") in target_models:
                paths.add(Path(vendor) / item["sub_path"])

    pet_cf_contract = runpy.run_path(str(PET_CF_HELPER))
    for path, _family in pet_cf_contract["candidate_paths"](PROFILES):
        paths.add(path.relative_to(PROFILES))
    return sorted(paths, key=lambda path: path.as_posix())


def manifest_lines() -> list[str]:
    return [f"{digest(PROFILES / path)}  {path.as_posix()}" for path in curated_paths()]


def write_manifest() -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text("\n".join(manifest_lines()) + "\n")


def read_manifest() -> list[tuple[str, Path]]:
    result: list[tuple[str, Path]] = []
    for line in MANIFEST.read_text().splitlines():
        if not line.strip():
            continue
        expected, relative = line.split("  ", 1)
        result.append((expected, Path(relative)))
    return result


def retained_in_system_cache(relative: Path) -> bool:
    # Codex is a filament-import staging vendor with no machine model. Orca
    # imports those presets into user/default and prunes this system copy on a
    # normal launch, so it is durable in the app bundle but not in the cache.
    return relative != Path("Codex.json") and relative.parts[:1] != ("Codex",)


def verify_root(root: Path, label: str, *, system_cache: bool = False) -> list[str]:
    errors: list[str] = []
    for expected, relative in read_manifest():
        if system_cache and not retained_in_system_cache(relative):
            continue
        path = root / relative
        if not path.is_file():
            errors.append(f"{label}: missing {relative.as_posix()}")
        elif digest(path) != expected:
            errors.append(f"{label}: checksum mismatch for {relative.as_posix()}")
    return errors


def sync_root(root: Path, label: str, backup: Path, *, system_cache: bool = False) -> int:
    changed = 0
    for expected, relative in read_manifest():
        if system_cache and not retained_in_system_cache(relative):
            continue
        source = PROFILES / relative
        target = root / relative
        if target.is_file() and digest(target) == expected:
            continue
        if target.is_file():
            backup_path = backup / label / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        changed += 1
    return changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--verify-live", action="store_true")
    parser.add_argument("--sync-live", action="store_true")
    parser.add_argument("--app-profiles", type=Path, default=DEFAULT_APP_PROFILES)
    parser.add_argument("--system-profiles", type=Path, default=DEFAULT_SYSTEM_PROFILES)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    args = parser.parse_args()

    if args.write:
        write_manifest()
    if not MANIFEST.is_file():
        print(f"ERROR: missing manifest: {MANIFEST}", file=sys.stderr)
        return 1

    expected_lines = manifest_lines()
    actual_lines = MANIFEST.read_text().splitlines()
    errors: list[str] = []
    if actual_lines != expected_lines:
        errors.append("repository profile manifest is stale; rerun with --write")
    errors.extend(verify_root(PROFILES, "repository"))
    if args.sync_live and not errors:
        backup = args.backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
        app_changed = sync_root(args.app_profiles, "app-bundle", backup)
        system_changed = sync_root(
            args.system_profiles, "application-support", backup, system_cache=True
        )
        print(f"profile deployment backup: {backup}")
        print(f"app bundle files synchronized: {app_changed}")
        print(f"Application Support files synchronized: {system_changed}")
    if args.verify_live or args.sync_live:
        errors.extend(verify_root(args.app_profiles, "app bundle"))
        errors.extend(
            verify_root(args.system_profiles, "Application Support", system_cache=True)
        )

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    scope = "repository and installed resources" if args.verify_live or args.sync_live else "repository"
    print(f"TinManX1 profile manifest verified: {len(actual_lines)} files, {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
