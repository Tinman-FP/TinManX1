#!/usr/bin/env python3
"""Apply the field-validated TinManX1 PET-CF profile contract.

The July 2026 PET-CF work produced an emergency 300 C / 1.08-flow rescue
profile, followed by a lower-temperature surface-quality tune.  The latter
was initially propagated only to Bambu-named presets, leaving QIDI, Fiberon,
Codex, and installed-cache copies on the obsolete rescue values.  This helper
keeps those owned profile families synchronized without changing unrelated
manufacturer presets such as Elegoo PET-CF.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROFILE_ROOT = ROOT / "resources/profiles"

COMMON_CONTRACT = {
    "filament_flow_ratio": "1.00",
    "filament_max_volumetric_speed": "3.2",
    "nozzle_temperature": "280",
    "nozzle_temperature_initial_layer": "285",
    "nozzle_temperature_range_low": "260",
    "nozzle_temperature_range_high": "300",
    "hot_plate_temp": "80",
    "hot_plate_temp_initial_layer": "80",
    "eng_plate_temp": "80",
    "eng_plate_temp_initial_layer": "80",
    "textured_plate_temp": "80",
    "textured_plate_temp_initial_layer": "80",
    "fan_min_speed": "0",
    "fan_max_speed": "20",
    "overhang_fan_speed": "35",
    "overhang_fan_threshold": "25%",
    "slow_down_layer_time": "25",
    "slow_down_min_speed": "6",
    "enable_pressure_advance": "1",
}

BAMBU_PRESSURE_ADVANCE = "0.022"
FIBERON_PRESSURE_ADVANCE = "0.028"

BAMBU_NOTE = (
    "TinManX1 PET-CF surface tune 2026-07-27: adjusted after rough Bambu "
    "PET-CF prints. Use 285C first layer / 280C print, 80C bed, 50C active "
    "chamber where supported, flow 1.00, max volumetric 3.2 mm3/s, limited "
    "overhang cooling, and pressure advance 0.022. Dry Bambu PET-CF at 80C "
    "for 8-12h before printing; dry longer before changing flow if popping "
    "or pitting remains."
)

FIBERON_NOTE = (
    "TinManX1 PET-CF field tune 2026-08-04: supersedes the July 11 300C / "
    "1.08-flow rescue profile. Use 285C first layer / 280C print, 80C bed, "
    "50C active chamber on supported TinMan machines, flow 1.00, max "
    "volumetric 3.2 mm3/s, limited overhang cooling, and pressure advance "
    "0.028. Fiberon permits room-temperature chambers; the controlled 50C "
    "target is the TinMan field-quality setting. Dry at 100C for 10h."
)

QIDI_NOTE = (
    "TinManX1 QIDI Plus 4 PET-CF field tune 2026-08-04: supersedes the July "
    "11 300C / 1.08-flow rescue profile. Use 285C first layer / 280C print, "
    "80C bed, 50C active chamber, flow 1.00, max volumetric 3.2 mm3/s, and "
    "limited overhang cooling. The nozzle-specific QIDI pressure-advance "
    "value is retained. Dry QIDI PET-CF at 100C for 4-8h and print from a "
    "sealed dry box below 15% RH."
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=4, ensure_ascii=True) + "\n")


def vector_arity(profile: dict[str, Any], key: str) -> int:
    value = profile.get(key)
    return len(value) if isinstance(value, list) and value else 1


def set_vector(profile: dict[str, Any], key: str, value: str) -> None:
    profile[key] = [value] * vector_arity(profile, key)


def apply_contract(
    profile: dict[str, Any],
    *,
    pressure_advance: str | None,
    note: str,
    chamber_control: bool,
) -> None:
    for key, value in COMMON_CONTRACT.items():
        set_vector(profile, key, value)
    if pressure_advance is not None:
        set_vector(profile, "pressure_advance", pressure_advance)
    elif not profile.get("pressure_advance"):
        set_vector(profile, "pressure_advance", FIBERON_PRESSURE_ADVANCE)
    if chamber_control:
        set_vector(profile, "activate_chamber_temp_control", "1")
        set_vector(profile, "chamber_temperature", "50")
        set_vector(profile, "chamber_temperatures", "50")
    else:
        set_vector(profile, "activate_chamber_temp_control", "0")
        set_vector(profile, "chamber_temperature", "0")
        set_vector(profile, "chamber_temperatures", "0")
    set_vector(profile, "filament_notes", note)


def supports_active_chamber(name: str, family: str) -> bool:
    if family == "qidi":
        return True
    if family == "bambu":
        return any(
            machine in name
            for machine in ("BBL H2D", "BBL H2S", "BBL X1E", "BBL X2D")
        )
    if "Codex-Fiberon" not in name:
        return False
    return any(
        machine in name
        for machine in (
            " - Bambu",
            " - Creality K2 Plus",
            " - Prusa Core One",
            " - Qidi X-Plus 4",
            " - RatRig V-Core 4",
            " - Sovol SV08 MAX",
        )
    )


def candidate_paths(profile_root: Path) -> list[tuple[Path, str]]:
    candidates: dict[Path, str] = {}

    bbl = profile_root / "BBL/filament"
    if bbl.is_dir():
        for path in bbl.rglob("Bambu PET-CF*.json"):
            candidates[path] = "bambu"
        for path in bbl.rglob("Fiberon PET-CF*.json"):
            candidates[path] = "fiberon"

    library = profile_root / "OrcaFilamentLibrary/filament"
    if library.is_dir():
        for path in library.rglob("Bambu PET-CF*.json"):
            candidates[path] = "bambu"
        for path in library.rglob("Fiberon PET-CF*.json"):
            candidates[path] = "fiberon"

    qidi = profile_root / "Qidi/filament"
    if qidi.is_dir():
        base = qidi / "QIDI PET-CF.json"
        if base.is_file():
            candidates[base] = "qidi"
        for path in qidi.glob("QIDI PET-CF @Qidi X-Plus 4 * nozzle.json"):
            candidates[path] = "qidi"

    codex = profile_root / "Codex/filament"
    if codex.is_dir():
        for path in codex.glob("PET-CF Codex-Fiberon - *.json"):
            candidates[path] = "fiberon"

    # User preset roots are flat filament directories rather than vendor trees.
    if profile_root.name == "filament":
        for path in profile_root.glob("PET-CF Codex-Fiberon - *.json"):
            candidates[path] = "fiberon"

    return sorted(candidates.items())


def repair_root(profile_root: Path, dry_run: bool) -> tuple[int, int]:
    found = 0
    changed = 0
    for path, family in candidate_paths(profile_root):
        found += 1
        profile = load_json(path)
        before = json.dumps(profile, sort_keys=True)
        name = str(profile.get("name") or path.stem)
        chamber_control = supports_active_chamber(name, family)
        if family == "bambu":
            apply_contract(
                profile,
                pressure_advance=BAMBU_PRESSURE_ADVANCE,
                note=BAMBU_NOTE,
                chamber_control=chamber_control,
            )
        elif family == "fiberon":
            apply_contract(
                profile,
                pressure_advance=FIBERON_PRESSURE_ADVANCE,
                note=FIBERON_NOTE,
                chamber_control=chamber_control,
            )
        else:
            apply_contract(
                profile,
                pressure_advance=None,
                note=QIDI_NOTE,
                chamber_control=chamber_control,
            )
        if json.dumps(profile, sort_keys=True) == before:
            continue
        changed += 1
        print(f"{'would update' if dry_run else 'updated'}: {path}")
        if not dry_run:
            write_json(path, profile)
    return found, changed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile-root", type=Path, action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    roots = args.profile_root or [DEFAULT_PROFILE_ROOT]
    total_found = 0
    total_changed = 0
    for root in roots:
        found, changed = repair_root(root, args.dry_run)
        total_found += found
        total_changed += changed
    print(f"PET-CF profiles matched: {total_found}")
    print(f"PET-CF profiles changed: {total_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
