#!/usr/bin/env python3
"""Compare generated Codex filaments with resolved Bambu Studio references.

Bambu filament presets are inheritance fragments and may carry separate values
for standard- and high-flow extruder variants.  This helper resolves those
fragments before comparing them with TinManX1's printer-specific Codex catalog.
It is intentionally report-only until every material family has an explicit,
reviewable reference decision.
"""

from __future__ import annotations

import argparse
import json
import plistlib
from collections import defaultdict
from pathlib import Path
from typing import Any

from codex_filament_contracts import REFERENCE_FIELDS


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BAMBU_ROOT = Path("/Applications/BambuStudio.app/Contents/Resources/profiles/BBL/filament")
DEFAULT_CODEX_ROOT = ROOT / "resources/profiles/Codex/filament"

DEFAULT_OUTPUT = ROOT / "scripts/profile-contracts/bambu_studio_2.7.1_filament_contract.json"


def ref(mode: str, x1c: str | None, h2d: str | None = None) -> tuple[str, str | None, str | None]:
    return mode, x1c, h2d if h2d is not None else x1c


# Every Codex material/vendor pair is an explicit decision. "exact" permits
# selected Bambu material fields to be imported. "analog" is documentation and
# comparison only; the manufacturer recipe remains authoritative.
REFERENCE_SPECS = {
    "ABS|Bambu": ref("exact", "Bambu ABS"),
    "ABS|Inland": ref("analog", "Bambu ABS"),
    "ABS|Polymaker": ref("exact", "PolyLite ABS"),
    "ABS|RatRig Punk": ref("analog", "Bambu ABS"),
    "ABS-CF|Generic": ref("analog", "Bambu ABS-GF"),
    "ABS-GF|Bambu": ref("exact", "Bambu ABS-GF"),
    "ABS-GF|QIDI": ref("analog", "Bambu ABS-GF"),
    "ASA|Generic": ref("exact", "Bambu ASA", "Generic ASA"),
    "ASA|Polymaker": ref("exact", "PolyLite ASA"),
    "ASA-CF|Bambu": ref("exact", "Bambu ASA-CF", ""),
    "ASA-CF|Fiberon": ref("analog", "Bambu ASA-CF", ""),
    "HIPS|Generic": ref("exact", "Generic HIPS"),
    "HT-PLA-CF|Polymaker": ref("analog", "Bambu PLA-CF", "Generic PLA-CF"),
    "HT-PLA-GF|Polymaker": ref("analog", "Bambu PLA-CF", "Generic PLA-CF"),
    "PA|Generic": ref("exact", None, "Generic PA"),
    "PA|Polymaker": ref("analog", None, "Generic PA"),
    "PA-CF|Fiberon": ref("analog", None, "Generic PA-CF"),
    "PA-GF|Fiberon": ref("analog", "Fiberon PA6-GF"),
    "PA12-CF|Fiberon": ref("exact", "Fiberon PA12-CF"),
    "PA12-CF|Fila Matrix": ref("analog", "Fiberon PA12-CF"),
    "PA12-CF|Polymaker": ref("analog", "Fiberon PA12-CF"),
    "PA6-CF|Fiberon": ref("exact", "Fiberon PA6-CF"),
    "PA6-CF|Polymaker": ref("analog", "Bambu PA6-CF"),
    "PA6-GF|Fiberon": ref("exact", "Fiberon PA6-GF"),
    "PA612-CF|Fiberon": ref("exact", "Fiberon PA612-CF"),
    "PA612-ESD|Fiberon": ref("analog", "Fiberon PA612-CF"),
    "PAHT|Bambu": ref("analog", None, "Generic PA"),
    "PAHT|Generic": ref("analog", None, "Generic PA"),
    "PAHT-CF|Bambu": ref("exact", "Bambu PAHT-CF"),
    "PAKV|Filamatrix": ref("analog", None, "Generic PA"),
    "PC|Generic": ref("exact", "Bambu PC", "Generic PC"),
    "PC|Polymaker": ref("analog", "Bambu PC", "Generic PC"),
    "PC+PBT|Push Plastic": ref("analog", "Bambu PC", "Generic PC"),
    "PC-CF|Generic": ref("analog", "Bambu PC", "Generic PC"),
    "PC-PBT|Push Plastic": ref("analog", "Bambu PC", "Generic PC"),
    "PCTG|Generic": ref("exact", "Generic PCTG"),
    "PCTG-CF|3D-Fuel Pro": ref("analog", "Generic PETG-CF"),
    "PEBA|SainSmart": ref("analog", "Bambu TPU 85A"),
    "PET-CF|Elegoo": ref("analog", "Bambu PET-CF"),
    "PET-CF|Fiberon": ref("exact", "Fiberon PET-CF"),
    "PET-GF|Fiberon": ref("analog", "Fiberon PET-CF"),
    "PETG|Fiberon": ref("analog", "Generic PETG HF", "Generic PETG"),
    "PETG|Generic": ref("exact", "Generic PETG HF", "Generic PETG"),
    "PETG|Polymaker": ref("exact", "PolyLite PETG"),
    "PETG-CF|Bambu": ref("exact", "Bambu PETG-CF", "Generic PETG-CF"),
    "PETG-CF|Fiberon": ref("exact", "Fiberon PETG-rCF"),
    "PETG-CF|Generic": ref("exact", "Generic PETG-CF"),
    "PETG-ESD|Fiberon": ref("exact", "Fiberon PETG-ESD"),
    "PLA|Polymaker": ref("exact", "PolyLite PLA"),
    "PLA-CF|Polymaker": ref("analog", "Bambu PLA-CF", "Generic PLA-CF"),
    "PLA-GF|Polymaker": ref("analog", "Bambu PLA-CF", "Generic PLA-CF"),
    "PPA-CF|Bambu": ref("exact", "Bambu PPA-CF"),
    "PPS|Generic": ref("exact", None, "Generic PPS"),
    "PPS-CF|Bambu": ref("exact", None, "Bambu PPS-CF"),
    "PPS-CF|Fiberon": ref("analog", None, "Generic PPS-CF"),
    "PPS-GF|Fiberon": ref("analog", None, "Generic PPS-CF"),
    "PPS-GF|QIDI": ref("analog", None, "Generic PPS-CF"),
    "PolySmooth|Polymaker": ref("analog", "PolyLite PLA"),
    "TPU|Elegoo": ref("analog", "Bambu TPU 95A"),
    "TPU|Polymaker": ref("analog", "Bambu TPU 95A"),
}


def scalar(value: Any, fallback: str = "") -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    if value is None:
        return fallback
    return str(value)


def load_profiles(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Path]]:
    profiles: dict[str, dict[str, Any]] = {}
    paths: dict[str, Path] = {}
    for path in sorted(root.rglob("*.json")):
        data = json.loads(path.read_text())
        name = scalar(data.get("name"), path.stem)
        profiles[name] = data
        paths[name] = path
    return profiles, paths


def resolve_profile(
    name: str,
    profiles: dict[str, dict[str, Any]],
    cache: dict[str, dict[str, Any]],
    stack: tuple[str, ...] = (),
) -> dict[str, Any]:
    if name in cache:
        return cache[name]
    if name in stack:
        raise ValueError("filament inheritance cycle: " + " -> ".join((*stack, name)))
    data = profiles[name]
    parent = scalar(data.get("inherits"))
    merged: dict[str, Any] = {}
    if parent and parent in profiles:
        merged.update(resolve_profile(parent, profiles, cache, (*stack, name)))
    merged.update(data)
    cache[name] = merged
    return merged


def codex_identity(data: dict[str, Any]) -> tuple[str, str, str]:
    name = scalar(data.get("name"))
    material = scalar(data.get("filament_type"))
    manufacturer = name.split(" Codex-", 1)[1].split(" - ", 1)[0]
    bucket = name.rsplit(" - ", 1)[1].removesuffix(" @Codex")
    return material, manufacturer, bucket


def named_reference(
    stem: str | None,
    suffix: str,
    resolved: dict[str, dict[str, Any]],
) -> tuple[str, dict[str, Any]] | None:
    if not stem:
        return None
    name = f"{stem} {suffix}"
    if name not in resolved:
        return None
    values = {
        key: resolved[name][key]
        for key in (*REFERENCE_FIELDS, "chamber_temperatures")
        if key in resolved[name]
    }
    return name, values


def vector_value(data: dict[str, Any], key: str, high_flow: bool) -> str:
    value = data.get(key)
    if not isinstance(value, list):
        return scalar(value)
    if not value:
        return ""
    return str(value[-1] if high_flow and len(value) > 1 else value[0])


def bambu_version(bambu_root: Path) -> str:
    info = bambu_root.parents[3] / "Info.plist"
    if info.is_file():
        data = plistlib.loads(info.read_bytes())
        return str(data.get("CFBundleShortVersionString") or data.get("CFBundleVersion") or "unknown")
    return "unknown"


def build_contract(bambu_root: Path, codex_root: Path) -> tuple[dict[str, Any], list[str]]:
    profiles, _paths = load_profiles(bambu_root)
    cache: dict[str, dict[str, Any]] = {}
    resolved = {name: resolve_profile(name, profiles, cache) for name in profiles}

    codex_groups: dict[tuple[str, str], set[str]] = defaultdict(set)
    for path in sorted(codex_root.glob("*.json")):
        data = json.loads(path.read_text())
        material, manufacturer, bucket = codex_identity(data)
        codex_groups[(material, manufacturer)].add(bucket)

    errors: list[str] = []
    contract_profiles: dict[str, Any] = {}
    contract_references: dict[str, Any] = {}
    for (material, manufacturer), buckets in sorted(codex_groups.items()):
        key = f"{material}|{manufacturer}"
        spec = REFERENCE_SPECS.get(key)
        if not spec:
            errors.append(f"missing explicit reference decision: {key}")
            continue
        mode, x1c_stem, h2d_stem = spec
        x1c = named_reference(x1c_stem, "@BBL X1C", resolved)
        h2d = named_reference(h2d_stem, "@BBL H2D", resolved)
        if x1c_stem and not x1c:
            errors.append(f"missing X1C reference {x1c_stem!r} for {key}")
        if h2d_stem and not h2d:
            errors.append(f"missing H2D reference {h2d_stem!r} for {key}")
        entry: dict[str, Any] = {"mode": mode}
        if x1c:
            entry["x1c"] = x1c[0]
            contract_references[x1c[0]] = {"values": x1c[1]}
        if h2d:
            entry["h2d"] = h2d[0]
            contract_references[h2d[0]] = {"values": h2d[1]}
        contract_profiles[key] = entry

    extra = sorted(set(REFERENCE_SPECS) - set(f"{m}|{v}" for m, v in codex_groups))
    if extra:
        errors.extend(f"reference decision has no Codex profile: {key}" for key in extra)
    return {
        "schema_version": 1,
        "source": {
            "application": "Bambu Studio",
            "version": bambu_version(bambu_root),
            "profile_root": "Contents/Resources/profiles/BBL/filament",
        },
        "reference_fields": list(REFERENCE_FIELDS),
        "references": dict(sorted(contract_references.items())),
        "profiles": contract_profiles,
    }, errors


def report(contract: dict[str, Any], errors: list[str]) -> int:
    exact = 0
    analog = 0
    for key, entry in sorted(contract["profiles"].items()):
        material, manufacturer = key.split("|", 1)
        x1c_name = entry.get("x1c")
        h2d_name = entry.get("h2d")
        x1c = (contract.get("references") or {}).get(x1c_name, {})
        if entry["mode"] == "exact":
            exact += 1
        else:
            analog += 1
        details = ""
        if x1c_name:
            values = x1c["values"]
            details = (
                f" | HF mvs={vector_value(values, 'filament_max_volumetric_speed', True)}"
                f" flow={vector_value(values, 'filament_flow_ratio', True)}"
                f" nozzle={vector_value(values, 'nozzle_temperature', True)}"
            )
        print(
            f"{material:12} {manufacturer:12} | {entry['mode']:6}"
            f" | X1C {x1c_name or '<preserve>'}"
            f" | H2D {h2d_name or '<fallback/preserve>'}{details}"
        )
    print(f"Exact import contracts: {exact}")
    print(f"Analog comparison-only contracts: {analog}")
    for error in errors:
        print(f"ERROR: {error}")
    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bambu-root", type=Path, default=DEFAULT_BAMBU_ROOT)
    parser.add_argument("--codex-root", type=Path, default=DEFAULT_CODEX_ROOT)
    parser.add_argument("--write-contract", type=Path)
    args = parser.parse_args()
    contract, errors = build_contract(args.bambu_root, args.codex_root)
    status = report(contract, errors)
    if args.write_contract and not errors:
        args.write_contract.parent.mkdir(parents=True, exist_ok=True)
        args.write_contract.write_text(json.dumps(contract, indent=2, ensure_ascii=True) + "\n")
        print(f"wrote contract: {args.write_contract}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
