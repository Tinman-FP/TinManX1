#!/usr/bin/env python3
"""Verify the four-nozzle TinMan Codex machine-profile contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PROFILES_ROOT = ROOT / "resources" / "profiles"
HELPER = ROOT / "scripts" / "source-helpers" / "normalize_tinman_machine_catalog.py"
APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
CONTRACT_SOURCE = ROOT / "src" / "libslic3r" / "TinManMachineProfileContract.cpp"
APP_CONFIG_SOURCE = ROOT / "src" / "libslic3r" / "AppConfig.cpp"
PRESET_SOURCE = ROOT / "src" / "libslic3r" / "Preset.cpp"
BUNDLE_SOURCE = ROOT / "src" / "libslic3r" / "PresetBundle.cpp"
COMBO_SOURCE = ROOT / "src" / "slic3r" / "GUI" / "PresetComboBoxes.cpp"
PLATER_SOURCE = ROOT / "src" / "slic3r" / "GUI" / "Plater.cpp"
CONTRACT = runpy.run_path(str(HELPER))
FAMILIES = CONTRACT["FAMILIES"]
NOZZLES = CONTRACT["NOZZLES"]
CONTRACT_VERSION = CONTRACT["CONTRACT_VERSION"]
PROCESS_MODES = CONTRACT["PROCESS_MODES"]
QUALITY_MODE = CONTRACT["QUALITY_MODE"]
process_modes = CONTRACT["process_modes"]
process_name = CONTRACT["process_name"]
mode_settings = CONTRACT["mode_settings"]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_repo() -> list[str]:
    errors: list[str] = []

    mode_by_name = {mode.name: mode for mode in PROCESS_MODES}
    if set(mode_by_name) != {"Tank", "Quality", "Fast", "Draft"}:
        errors.append("process mode contract must contain Tank, Quality, Fast, and Draft")
    else:
        tank = mode_by_name["Tank"]
        quality = mode_by_name["Quality"]
        fast = mode_by_name["Fast"]
        draft = mode_by_name["Draft"]
        if not (tank.layer_factor < quality.layer_factor < fast.layer_factor < draft.layer_factor):
            errors.append("process layer heights do not progress from Tank to Draft")
        if not (tank.wall_loops > quality.wall_loops > fast.wall_loops > draft.wall_loops):
            errors.append("process wall strength does not progress from Tank to Draft")
        if not (tank.speed_scale < quality.speed_scale < fast.speed_scale < draft.speed_scale):
            errors.append("process speed does not progress from Tank to Draft")
        densities = {
            name: int(mode_by_name[name].infill_density.removesuffix("%"))
            for name in mode_by_name
        }
        if not (
            densities["Tank"]
            > densities["Quality"]
            > densities["Fast"]
            > densities["Draft"]
        ):
            errors.append("process infill strength does not progress from Tank to Draft")

    source_contracts = (
        (CONTRACT_SOURCE, "tinmanx_apply_machine_catalog", 1),
        (CONTRACT_SOURCE, "tinmanx_process_preset_allowed", 1),
        (APP_CONFIG_SOURCE, "tinmanx_apply_machine_catalog(*this)", 2),
        (BUNDLE_SOURCE, "tinmanx_apply_machine_catalog", 2),
        (COMBO_SOURCE, "tinmanx_machine_preset_allowed", 2),
        (PRESET_SOURCE, "tinmanx_process_preset_allowed", 1),
    )
    for path, marker, minimum in source_contracts:
        if not path.is_file():
            errors.append(f"missing machine-contract source: {path.relative_to(ROOT)}")
            continue
        count = path.read_text().count(marker)
        if count < minimum:
            errors.append(
                f"{path.relative_to(ROOT)} does not enforce {marker} in all required paths"
            )

    # System inheritance bases must load before canonical child profiles are
    # resolved. Visibility belongs in selectors, never in PresetCollection.
    if PRESET_SOURCE.is_file() and "tinmanx_machine_preset_allowed" in PRESET_SOURCE.read_text():
        errors.append("Preset.cpp filters machine presets before inheritance resolution")

    if PLATER_SOURCE.is_file():
        plater_source = PLATER_SOURCE.read_text()
        if "panel_nozzle_dia->Show(!isDual);" not in plater_source:
            errors.append("Plater.cpp does not expose the shared multi-extruder nozzle selector")
        if "if (use_split_nozzle_controls)" not in plater_source:
            errors.append("Plater.cpp does not reserve split nozzle controls for Bambu printers")

    families_by_vendor: dict[str, list[Any]] = {}
    for family in FAMILIES:
        families_by_vendor.setdefault(family.vendor, []).append(family)

    names: set[str] = set()
    for vendor, families in families_by_vendor.items():
        index_path = PROFILES_ROOT / f"{vendor}.json"
        index = load_json(index_path)
        if index.get("tinman_codex_machine_contract") != CONTRACT_VERSION:
            errors.append(f"{vendor}.json does not declare machine contract {CONTRACT_VERSION}")

        machine_items = index.get("machine_list", [])
        process_items = index.get("process_list", [])
        model_items = {item.get("name"): item for item in index.get("machine_model_list", [])}

        for family in families:
            model_item = model_items.get(family.model)
            if not model_item:
                errors.append(f"{vendor}: missing model entry for {family.model}")
                continue
            model_data = load_json(PROFILES_ROOT / vendor / model_item["sub_path"])
            if model_data.get("nozzle_diameter") != ";".join(NOZZLES):
                errors.append(f"{family.model}: model nozzle list is not the four-nozzle contract")

            expected_names = {family.canonical_name(nozzle) for nozzle in NOZZLES}
            indexed_names = {
                item.get("name") for item in machine_items if item.get("name") in expected_names
            }
            missing = expected_names - indexed_names
            if missing:
                errors.append(f"{family.model}: missing indexed machine profiles {sorted(missing)}")

            required_sources = {family.source_name(nozzle) for nozzle in NOZZLES}
            indexed_sources = {item.get("name") for item in machine_items} & required_sources
            missing_sources = required_sources - indexed_sources
            if missing_sources:
                errors.append(
                    f"{family.model}: missing indexed inheritance bases {sorted(missing_sources)}"
                )
            source_nozzles: dict[str, str] = {}
            for nozzle in NOZZLES:
                source_nozzles.setdefault(family.source_name(nozzle), nozzle)
            for source_name, source_nozzle in source_nozzles.items():
                source_item = next(
                    (entry for entry in machine_items if entry.get("name") == source_name), None
                )
                if source_item is None:
                    continue
                source_data = load_json(PROFILES_ROOT / vendor / source_item["sub_path"])
                if source_data.get("printer_variant") != source_nozzle:
                    errors.append(
                        f"{source_name}: inheritance base has invalid printer_variant "
                        f"{source_data.get('printer_variant')!r}"
                    )

            unexpected_noncanonical: list[str] = []
            for item in machine_items:
                sub_path = item.get("sub_path")
                if not sub_path:
                    continue
                path = PROFILES_ROOT / vendor / sub_path
                if not path.is_file():
                    continue
                data = load_json(path)
                if (
                    data.get("printer_model") == family.model
                    and data.get("printer_variant")
                    and data.get("name") not in expected_names
                    and data.get("name") not in required_sources
                ):
                    unexpected_noncanonical.append(str(data.get("name")))
            if unexpected_noncanonical:
                errors.append(
                    f"{family.model}: index contains unnecessary noncanonical variants "
                    f"{sorted(unexpected_noncanonical)}"
                )

            for nozzle in NOZZLES:
                name = family.canonical_name(nozzle)
                if name in names:
                    errors.append(f"duplicate canonical machine name: {name}")
                names.add(name)
                item = next((entry for entry in machine_items if entry.get("name") == name), None)
                if not item:
                    continue
                data = load_json(PROFILES_ROOT / vendor / item["sub_path"])
                if data.get("inherits") not in required_sources:
                    errors.append(f"{name}: inheritance base is not indexed")
                if data.get("printer_settings_id") != name:
                    errors.append(f"{name}: printer_settings_id mismatch")
                if data.get("printer_variant") != nozzle:
                    errors.append(f"{name}: printer_variant mismatch")
                diameters = data.get("nozzle_diameter") or []
                if not diameters or diameters[0] != nozzle:
                    errors.append(f"{name}: primary nozzle diameter mismatch")
                if family.composite_second_nozzle and (
                    len(diameters) < 2 or diameters[1] != family.composite_second_nozzle
                ):
                    errors.append(f"{name}: fixed FibreSeek fiber nozzle is not 0.7 mm")

                expected_process = data.get("default_print_profile")
                process_item = next(
                    (entry for entry in process_items if entry.get("name") == expected_process), None
                )
                if not process_item:
                    errors.append(f"{name}: default process is not indexed")
                    continue
                process = load_json(PROFILES_ROOT / vendor / process_item["sub_path"])
                if process.get("compatible_printers") != [name]:
                    errors.append(f"{name}: default process compatibility mismatch")

                expected_modes = process_modes(family)
                expected_processes = {
                    process_name(family, nozzle, mode): mode for mode in expected_modes
                }
                indexed_processes = {
                    item.get("name"): item
                    for item in process_items
                    if item.get("name") in expected_processes
                }
                missing_processes = set(expected_processes) - set(indexed_processes)
                if missing_processes:
                    errors.append(
                        f"{name}: missing canonical processes {sorted(missing_processes)}"
                    )
                if not family.composite_second_nozzle and expected_process != process_name(
                    family, nozzle, QUALITY_MODE
                ):
                    errors.append(f"{name}: Quality is not the default process")
                for candidate_name, mode in expected_processes.items():
                    candidate_item = indexed_processes.get(candidate_name)
                    if candidate_item is None:
                        continue
                    candidate = load_json(
                        PROFILES_ROOT / vendor / candidate_item["sub_path"]
                    )
                    if candidate.get("compatible_printers") != [name]:
                        errors.append(f"{candidate_name}: compatibility mismatch")
                    if mode is not None:
                        expected_settings = mode_settings(mode, nozzle)
                        mismatches = {
                            key: (candidate.get(key), value)
                            for key, value in expected_settings.items()
                            if candidate.get(key) != value
                        }
                        if mismatches:
                            errors.append(
                                f"{candidate_name}: process contract mismatch {mismatches}"
                            )

    if len(names) != len(FAMILIES) * len(NOZZLES):
        errors.append(
            f"expected {len(FAMILIES) * len(NOZZLES)} canonical machine names, found {len(names)}"
        )
    return errors


def validate_live(app_support: Path) -> list[str]:
    errors: list[str] = []
    conf_path = app_support / "OrcaSlicer.conf"
    if not conf_path.is_file():
        return [f"missing live config: {conf_path}"]
    conf = load_json(conf_path)
    expected_models = {
        (family.vendor, family.model, ";".join(NOZZLES)) for family in FAMILIES
    }
    actual_models = {
        (item.get("vendor"), item.get("model"), item.get("nozzle_diameter"))
        for item in conf.get("models", [])
    }
    if actual_models != expected_models:
        errors.append("live enabled-model list does not match the curated contract")

    for vendor in sorted({family.vendor for family in FAMILIES}):
        repo_index = PROFILES_ROOT / f"{vendor}.json"
        live_index = app_support / "system" / f"{vendor}.json"
        if not live_index.is_file() or digest(repo_index) != digest(live_index):
            errors.append(f"live {vendor}.json differs from the repository contract")
        for profile_type in ("machine", "process"):
            repo_dir = PROFILES_ROOT / vendor / profile_type / "TinMan Codex"
            live_dir = app_support / "system" / vendor / profile_type / "TinMan Codex"
            for repo_path in sorted(repo_dir.glob("*.json")):
                live_path = live_dir / repo_path.name
                if not live_path.is_file() or digest(repo_path) != digest(live_path):
                    errors.append(f"live profile differs: {vendor}/{profile_type}/{repo_path.name}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--app-support", type=Path, default=APP_SUPPORT)
    args = parser.parse_args()

    errors = validate_repo()
    if args.live:
        errors.extend(validate_live(args.app_support))
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    scope = "repository and live catalog" if args.live else "repository catalog"
    print(f"TinMan Codex machine profile verification passed: {len(FAMILIES)} models, {len(NOZZLES)} nozzles, {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
