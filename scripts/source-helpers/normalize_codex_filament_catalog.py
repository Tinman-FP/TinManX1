#!/usr/bin/env python3
"""Normalize the live TinManX1 Codex filament catalog.

This cleanup targets the installed Application Support catalog because that is
the state TinManX1 uses for the filament dropdowns after first launch. It
collapses duplicate Codex presets into one profile per material type,
manufacturer, and printer bucket; prunes broad cross-printer compatibility;
sets a consistent black swatch; and rewrites the enabled filament list so the
UI only exposes the cleaned Codex profiles plus the FibreSeek continuous-fiber
profiles.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR.parent))

from assign_vendor_setting_ids import generate_preset_setting_id
from codex_filament_contracts import apply_contract, load_contract

DEFAULT_BACKUP_ROOT = Path.home() / ".tinmanx1" / "codex-filament-cleanup-backups"
DEFAULT_MIRROR_ROOTS = [
    Path("/Applications/TinManX1.app/Contents/Resources/profiles"),
    REPO_ROOT / "resources" / "profiles",
]

SYSTEM_SUFFIX = " @Codex"
BLACK = "#000000"
PRUSA_PC_PBT_CF_TOKEN = "PCPBTCF"
PROFILE_RE = re.compile(
    r"^(?P<material>.+?) Codex-(?P<manufacturer>.+?) - "
    r"(?P<printer>.+?)(?: \((?P<copy>\d+)\))? @Codex$"
)

TARGET_BUCKETS: dict[str, tuple[str, ...]] = {
    "Bambu H2D": ("Bambu Lab H2D",),
    "Bambu X1C HF": ("Bambu Lab X1 Carbon",),
    "Creality K2 Plus": ("Creality K2 Plus",),
    "Elegoo Centauri": ("Elegoo Centauri",),
    "Prusa Core One": ("Prusa CORE One", "Prusa Core One"),
    "Qidi X-Plus 4": (
        "CURRENT QIDI",
        "QIDI Plus 4",
        "Qidi Plus 4",
        "Qidi X-Plus 4",
        "QidiMaxEz",
    ),
    "RatRig V-Core 4": ("RatRig V-Core 4",),
    "Snapmaker U1": ("CURRENT U1", "Snapmaker U1", "fdm_U1"),
    "Sovol SV08 MAX": ("Sovol SV08 MAX",),
}

CANONICAL_NOZZLES = ("0.4", "0.6", "0.8", "1.0")


def canonical_machine_names(model: str) -> tuple[str, ...]:
    return tuple(f"{model} {nozzle} nozzle - TinMan Codex" for nozzle in CANONICAL_NOZZLES)


CANONICAL_BUCKET_PRINTERS: dict[str, tuple[str, ...]] = {
    "Bambu H2D": canonical_machine_names("Bambu Lab H2D"),
    "Bambu X1C HF": canonical_machine_names("Bambu Lab X1 Carbon"),
    "Creality K2 Plus": canonical_machine_names("Creality K2 Plus"),
    "Elegoo Centauri": canonical_machine_names("Elegoo Centauri Carbon"),
    "Prusa Core One": canonical_machine_names("Prusa CORE One L"),
    "Qidi X-Plus 4": (
        *canonical_machine_names("Qidi X-Plus 4"),
        *canonical_machine_names("QidiMaxEz"),
    ),
    "RatRig V-Core 4": (
        *canonical_machine_names("RatRig V-Core 4 IDEX 500"),
        *canonical_machine_names("RatRig V-Core 4 IDEX 500 COPY MODE"),
        *canonical_machine_names("RatRig V-Core 4 IDEX 500 MIRROR MODE"),
    ),
    "Snapmaker U1": canonical_machine_names("Snapmaker U1"),
    "Sovol SV08 MAX": canonical_machine_names("Sovol SV08 MAX"),
}

LEGACY_BUCKET_EXPANSIONS: dict[str, tuple[str, ...]] = {
    "Bambu": ("Bambu H2D", "Bambu X1C HF"),
}

SOURCE_BUCKET_ALIASES = {
    "Prusa CORE One L": "Prusa Core One",
}

X1C_UNSUPPORTED_MATERIALS = {"PPS", "PPS-CF", "PPS-GF"}

BUCKET_ORDER = {name: index for index, name in enumerate(TARGET_BUCKETS)}
PRODUCT_PREFIXES = (
    "Fiberon ",
    "Panchroma ",
    "PolyLite ",
    "PolyMax ",
    "PolyMide ",
    "PolySonic ",
    "PolySupport ",
    "PolyTerra ",
    "Polymaker ",
)

DECORATIVE_TERMS = (
    "Glow",
    "Marble",
    "Metallic",
    "Starlight",
    "Galaxy",
    "Dual",
    "Silk",
    "Gradient",
    "Translucent",
)


@dataclass(frozen=True)
class ParsedProfile:
    path: Path
    data: dict[str, Any]
    original_name: str
    material_label: str
    material_type: str
    manufacturer: str
    source_bucket: str
    target_bucket: str
    score: int

    @property
    def canonical_name(self) -> str:
        display_bucket = self.target_bucket
        if self.key == ("PC-PBT-CF", "Push Plastic", "Prusa Core One"):
            display_bucket = "Prusa CORE One L"
        return f"{self.material_type} Codex-{self.manufacturer} - {display_bucket}{SYSTEM_SUFFIX}"

    @property
    def user_name(self) -> str:
        return self.canonical_name.removesuffix(SYSTEM_SUFFIX)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.material_type, self.manufacturer, self.target_bucket)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def stable_ids(name: str) -> tuple[str, str]:
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()
    return generate_preset_setting_id("Codex", "filament", name), f"CODX{digest[:8].upper()}"


def list_user_filament_dirs(app_support: Path) -> list[Path]:
    root = app_support / "user"
    if not root.is_dir():
        return []
    return sorted(path / "filament" for path in root.iterdir() if (path / "filament").is_dir())


def clean_material_type(material_label: str, profile: dict[str, Any]) -> str:
    filament_type = profile.get("filament_type")
    type_value = ""
    if isinstance(filament_type, list) and filament_type:
        type_value = str(filament_type[0]).strip()
    elif isinstance(filament_type, str):
        type_value = filament_type.strip()

    label = material_label.strip()
    if label.upper() == "PC-PBT-CF":
        return "PC-PBT-CF"
    if "PEBA" in label.upper():
        return "PEBA"
    if label.startswith(PRODUCT_PREFIXES) and type_value:
        return normalize_type_alias(type_value)
    if label.startswith("Push Plastic ") and "PC-PBT" in label:
        return "PC-PBT"
    if type_value and not type_value.startswith("Push Plastic "):
        if label.upper() == type_value.upper():
            return normalize_type_alias(type_value)
        if "-" in type_value or type_value in {"ABS", "ASA", "HIPS", "PA", "PC", "PCTG", "PETG", "PLA", "PP", "PPS", "TPU"}:
            return normalize_type_alias(type_value)
    return normalize_type_alias(label)


def normalize_type_alias(value: str) -> str:
    value = value.strip()
    aliases = {
        "PET GF": "PET-GF",
        "Push Plastic PC-PBT": "PC-PBT",
        "Push Plastic PC-PBT-CF": "PC-PBT-CF",
        "PE": "PE",
    }
    return aliases.get(value, value)


def product_score(material_label: str, material_type: str) -> int:
    score = 0
    if material_label.upper() == material_type.upper():
        score += 40
    if material_label.startswith("PolyLite "):
        score += 20
    if material_label.startswith("Polymaker "):
        score += 16
    if material_label.startswith("Fiberon "):
        score += 16
    if material_label.startswith("PolyMax "):
        score += 8
    if any(term in material_label for term in DECORATIVE_TERMS):
        score -= 30
    if "Support" in material_label:
        score -= 20
    return score


def parse_profile(path: Path, data: dict[str, Any]) -> ParsedProfile | None:
    name = str(data.get("name") or path.stem)
    match = PROFILE_RE.match(name)
    if not match:
        return None
    source_bucket = SOURCE_BUCKET_ALIASES.get(match.group("printer"), match.group("printer"))
    if source_bucket == "FibreSeek Seeker 3":
        return None
    material_label = match.group("material").strip()
    material_type = clean_material_type(material_label, data)
    manufacturer = match.group("manufacturer").strip()
    compat_count = len(data.get("compatible_printers") or [])
    score = product_score(material_label, material_type)
    if source_bucket != "Universal":
        score += 100
    if not match.group("copy"):
        score += 20
    if compat_count:
        score += 10
    return ParsedProfile(
        path=path,
        data=data,
        original_name=name,
        material_label=material_label,
        material_type=material_type,
        manufacturer=manufacturer,
        source_bucket=source_bucket,
        target_bucket=source_bucket,
        score=score,
    )


def bucket_compatible_printers(bucket: str) -> list[str]:
    return list(CANONICAL_BUCKET_PRINTERS[bucket])


def cloned_for_bucket(profile: ParsedProfile, bucket: str) -> ParsedProfile:
    return ParsedProfile(
        path=profile.path,
        data=profile.data,
        original_name=profile.original_name,
        material_label=profile.material_label,
        material_type=profile.material_type,
        manufacturer=profile.manufacturer,
        source_bucket=profile.source_bucket,
        target_bucket=bucket,
        score=profile.score - 5,
    )


def choose_profiles(filament_dir: Path) -> tuple[list[ParsedProfile], list[str], list[str]]:
    parsed: list[ParsedProfile] = []
    skipped: list[str] = []
    for path in sorted(filament_dir.glob("*.json")):
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError) as exc:
            skipped.append(f"{path.name}: {exc}")
            continue
        profile = parse_profile(path, data)
        if profile is None:
            skipped.append(str(data.get("name") or path.stem))
            continue
        parsed.append(profile)

    candidates: dict[tuple[str, str, str], ParsedProfile] = {}
    universal: list[ParsedProfile] = []
    for profile in parsed:
        if profile.source_bucket == "Universal":
            universal.append(profile)
            continue
        if profile.source_bucket in LEGACY_BUCKET_EXPANSIONS:
            for bucket in LEGACY_BUCKET_EXPANSIONS[profile.source_bucket]:
                if bucket == "Bambu X1C HF" and profile.material_type in X1C_UNSUPPORTED_MATERIALS:
                    continue
                bucketed = cloned_for_bucket(profile, bucket)
                current = candidates.get(bucketed.key)
                if current is None or bucketed.score > current.score or (
                    bucketed.score == current.score
                    and bucketed.original_name < current.original_name
                ):
                    candidates[bucketed.key] = bucketed
            continue
        if profile.target_bucket not in TARGET_BUCKETS:
            skipped.append(profile.original_name)
            continue
        current = candidates.get(profile.key)
        if current is None or profile.score > current.score or (
            profile.score == current.score and profile.original_name < current.original_name
        ):
            candidates[profile.key] = profile

    for profile in sorted(universal, key=lambda item: (-item.score, item.original_name)):
        for bucket in TARGET_BUCKETS:
            if bucket == "Bambu X1C HF" and profile.material_type in X1C_UNSUPPORTED_MATERIALS:
                continue
            bucketed = cloned_for_bucket(profile, bucket)
            candidates.setdefault(bucketed.key, bucketed)

    chosen = sorted(
        candidates.values(),
        key=lambda item: (
            BUCKET_ORDER[item.target_bucket],
            item.material_type.lower(),
            item.manufacturer.lower(),
        ),
    )
    return chosen, [p.original_name for p in universal], skipped


def canonical_profile(
    profile: ParsedProfile,
    compatible_printers: list[str],
    filament_contract: dict[str, Any],
) -> dict[str, Any]:
    data = apply_contract(
        profile.data,
        profile.material_type,
        profile.manufacturer,
        profile.target_bucket,
        filament_contract,
    )
    setting_id, filament_id = stable_ids(profile.canonical_name)
    data["name"] = profile.canonical_name
    data["filament_settings_id"] = [profile.canonical_name]
    data["filament_vendor"] = ["Codex"]
    if profile.key == ("PC-PBT-CF", "Push Plastic", "Prusa Core One"):
        data["filament_type"] = [PRUSA_PC_PBT_CF_TOKEN]
    else:
        data["filament_type"] = [profile.material_type]
    data["default_filament_colour"] = [BLACK]
    data.pop("filament_colour", None)
    data["compatible_printers"] = compatible_printers
    data["from"] = "system"
    data["type"] = "filament"
    data["instantiation"] = "true"
    data["setting_id"] = setting_id
    data["filament_id"] = filament_id
    return data


def user_profile_from_system(system_profile: dict[str, Any], user_name: str) -> dict[str, Any]:
    data = copy.deepcopy(system_profile)
    _, filament_id = stable_ids(user_name)
    data["name"] = user_name
    data["filament_settings_id"] = [user_name]
    data["from"] = "User"
    data["filament_id"] = filament_id
    data.pop("setting_id", None)
    data["renamed_from"] = f"{user_name} Codex normalized"
    return data


def user_info_text(user_dir: Path, user_name: str, updated_time: int) -> str:
    user_folder = user_dir.parent.name
    user_id = user_folder if user_folder.isdigit() else ""
    base_id = "codex-" + hashlib.sha1(f"{user_folder}:{user_name}".encode("utf-8")).hexdigest()[:12]
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


def tinmanx1_enabled_filaments(app_support: Path) -> list[str]:
    names: list[str] = []
    for index_path in (app_support / "system").glob("TinManX1.json"):
        try:
            index = load_json(index_path)
        except (OSError, json.JSONDecodeError):
            continue
        for item in index.get("filament_list", []):
            name = item.get("name")
            if name and name not in names and not name.endswith(" base"):
                names.append(name)
    return sorted(names)


def backup_live_state(app_support: Path, backup_root: Path) -> Path:
    backup = backup_root / datetime.now().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    for rel in (Path("OrcaSlicer.conf"), Path("system/Codex.json"), Path("system/Codex")):
        source = app_support / rel
        target = backup / rel
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for user_dir in list_user_filament_dirs(app_support):
        target = backup / user_dir.relative_to(app_support)
        shutil.copytree(user_dir, target)
    return backup


def ensure_codex_catalog(app_support: Path, dry_run: bool) -> Path:
    live_dir = app_support / "system" / "Codex" / "filament"
    if live_dir.is_dir():
        return live_dir
    repo_vendor = REPO_ROOT / "resources" / "profiles" / "Codex"
    repo_dir = repo_vendor / "filament"
    if not repo_dir.is_dir():
        raise SystemExit(f"missing Codex filament catalog: {repo_dir}")
    if dry_run:
        return repo_dir
    live_vendor = app_support / "system" / "Codex"
    live_vendor.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo_vendor, live_vendor)
    shutil.copy2(
        REPO_ROOT / "resources" / "profiles" / "Codex.json",
        app_support / "system" / "Codex.json",
    )
    return live_dir


def clear_user_filament_sidecars(directory: Path) -> int:
    count = 0
    for path in directory.glob("*"):
        if not path.is_file():
            continue
        if path.suffix in {".json", ".info"}:
            path.unlink()
            count += 1
    return count


def rewrite_catalog(
    app_support: Path,
    chosen: list[ParsedProfile],
    dry_run: bool,
) -> tuple[int, int, int, list[str]]:
    system_root = app_support / "system"
    index_path = system_root / "Codex.json"
    if dry_run and not index_path.is_file():
        index_path = REPO_ROOT / "resources" / "profiles" / "Codex.json"
    filament_dir = system_root / "Codex" / "filament"
    bucket_printers = {
        bucket: bucket_compatible_printers(bucket)
        for bucket in TARGET_BUCKETS
    }
    filament_contract = load_contract()

    canonical: list[tuple[str, dict[str, Any], str]] = []
    for selected in chosen:
        data = canonical_profile(
            selected,
            bucket_printers[selected.target_bucket],
            filament_contract,
        )
        canonical.append((selected.canonical_name, data, selected.user_name))

    index = load_json(index_path)
    index["version"] = "00.00.02.01"
    index["filament_list"] = [
        {"name": name, "sub_path": f"filament/{name}.json"}
        for name, _, _ in canonical
    ]

    conf_path = app_support / "OrcaSlicer.conf"
    enabled_names = [name for name, _, _ in canonical] + tinmanx1_enabled_filaments(app_support)
    enabled_names = sorted(dict.fromkeys(enabled_names), key=lambda value: (value.split(" @")[-1], value.lower()))
    user_dirs = list_user_filament_dirs(app_support)

    if dry_run:
        return len(canonical), len(user_dirs) * len(canonical), len(enabled_names), enabled_names

    for path in filament_dir.glob("*.json"):
        path.unlink()
    for name, data, _ in canonical:
        write_json(filament_dir / f"{name}.json", data)
    write_json(index_path, index)

    updated_time = int(time.time())
    for user_dir in user_dirs:
        clear_user_filament_sidecars(user_dir)
        for _, data, user_name in canonical:
            write_json(user_dir / f"{user_name}.json", user_profile_from_system(data, user_name))
            (user_dir / f"{user_name}.info").write_text(user_info_text(user_dir, user_name, updated_time))

    conf = load_json(conf_path)
    conf["filaments"] = enabled_names
    conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=True) + "\n")
    return len(canonical), len(user_dirs) * len(canonical), len(enabled_names), enabled_names


def mirror_catalog(app_support: Path, mirror_roots: list[Path], dry_run: bool) -> list[Path]:
    source_index = app_support / "system/Codex.json"
    source_dir = app_support / "system/Codex"
    mirrored: list[Path] = []
    for root in mirror_roots:
        if not root.exists():
            continue
        target_index = root / "Codex.json"
        target_dir = root / "Codex"
        mirrored.append(root)
        if dry_run:
            continue
        if target_dir.exists():
            shutil.rmtree(target_dir)
        shutil.copytree(source_dir, target_dir)
        shutil.copy2(source_index, target_index)
    return mirrored


def validate(app_support: Path, enabled_names: list[str]) -> list[str]:
    errors: list[str] = []
    if len(enabled_names) != len(set(enabled_names)):
        errors.append("enabled filament list still contains duplicates")
    bad_suffix = [name for name in enabled_names if re.search(r"\(\d+\)|\(Installed\)", name)]
    if bad_suffix:
        errors.append(f"enabled filament list still contains copy/install suffixes: {bad_suffix[:5]}")
    bad_non_codex = [
        name for name in enabled_names
        if "Codex" not in name and not (name.startswith("TinManX1 ") or name.startswith("CFC "))
    ]
    if bad_non_codex:
        errors.append(f"enabled filament list still contains non-Codex stock profiles: {bad_non_codex[:5]}")

    filament_dir = app_support / "system/Codex/filament"
    seen: set[tuple[str, str, str]] = set()
    for path in filament_dir.glob("*.json"):
        data = load_json(path)
        name = data.get("name", path.stem)
        parsed = PROFILE_RE.match(name)
        if not parsed:
            errors.append(f"unparseable Codex profile name: {name}")
            continue
        key = (parsed.group("material"), parsed.group("manufacturer"), parsed.group("printer"))
        if key in seen:
            errors.append(f"duplicate material/manufacturer/printer key: {key}")
        seen.add(key)
        if data.get("default_filament_colour") != [BLACK] or "filament_colour" in data:
            errors.append(f"profile does not have black swatch: {name}")
        if data.get("filament_vendor") != ["Codex"]:
            errors.append(f"profile vendor is not Codex: {name}")
        if parsed.group("printer") == "Qidi X-Plus 4":
            compatible = data.get("compatible_printers") or []
            if any("Centauri" in item for item in compatible):
                errors.append(f"Qidi profile includes Centauri compatibility: {name}")
            if any("X-Plus 3" in item or "Q1" in item for item in compatible):
                errors.append(f"Qidi profile includes non-Plus-4 Qidi compatibility: {name}")
        expected_compatible = list(CANONICAL_BUCKET_PRINTERS.get(parsed.group("printer"), ()))
        if expected_compatible and data.get("compatible_printers") != expected_compatible:
            errors.append(f"profile does not match canonical machine contract: {name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    parser.add_argument("--mirror-root", type=Path, action="append", default=[])
    parser.add_argument("--skip-default-mirrors", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    app_support = args.app_support
    if not (app_support / "OrcaSlicer.conf").is_file():
        raise SystemExit(f"missing OrcaSlicer.conf under {app_support}")

    filament_dir = ensure_codex_catalog(app_support, args.dry_run)

    chosen, universal, skipped = choose_profiles(filament_dir)
    if not args.dry_run:
        backup = backup_live_state(app_support, args.backup_root)
        print(f"backup: {backup}")
    else:
        print("backup: dry-run")

    system_count, user_count, enabled_count, enabled_names = rewrite_catalog(app_support, chosen, args.dry_run)
    mirror_roots = [] if args.skip_default_mirrors else list(DEFAULT_MIRROR_ROOTS)
    mirror_roots.extend(args.mirror_root)
    mirrored = mirror_catalog(app_support, mirror_roots, args.dry_run)
    errors = [] if args.dry_run else validate(app_support, enabled_names)

    print(f"canonical system profiles: {system_count}")
    print(f"user sidecar profiles: {user_count}")
    print(f"enabled filaments: {enabled_count}")
    print(f"universal profiles consumed as templates: {len(universal)}")
    print(f"skipped/archived Codex profiles: {len(skipped)}")
    print(f"mirrored roots: {len(mirrored)}")
    for root in mirrored:
        print(f"  {root}")
    for name in enabled_names[:20]:
        print(f"enabled: {name}")
    if errors:
        print("validation errors:")
        for error in errors:
            print(f"  {error}")
        return 2
    print("validation: ok" if not args.dry_run else "validation: dry-run")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
