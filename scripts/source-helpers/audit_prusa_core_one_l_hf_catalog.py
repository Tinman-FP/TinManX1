#!/usr/bin/env python3
"""Audit the curated Prusa CORE One L all-HF profile contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
PROFILES = ROOT / "resources/profiles"
PRUSA = PROFILES / "Prusa"
CODEX_FILAMENTS = PROFILES / "Codex/filament"
NOZZLES = ("0.4", "0.6", "0.8", "1.0")
MODES = ("Tank", "Quality", "Fast", "Draft")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def scalar(value: Any, fallback: str = "") -> str:
    if isinstance(value, list):
        return str(value[0]) if value else fallback
    return fallback if value is None else str(value)


def indexed(kind: str) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in (PRUSA / kind).rglob("*.json"):
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if name := data.get("name"):
            profiles[str(name)] = data
    return profiles


def resolved(name: str, profiles: dict[str, dict[str, Any]], seen: tuple[str, ...] = ()) -> dict[str, Any]:
    if name in seen:
        raise RuntimeError(f"inheritance cycle: {' -> '.join((*seen, name))}")
    data = profiles[name]
    output: dict[str, Any] = {}
    parent = data.get("inherits")
    if parent and parent in profiles:
        output.update(resolved(str(parent), profiles, (*seen, name)))
    output.update(data)
    return output


def canonical_machine(nozzle: str) -> str:
    return f"Prusa CORE One L {nozzle} nozzle - TinMan Codex"


def main() -> int:
    failures: list[str] = []
    machines = indexed("machine")
    processes = indexed("process")

    curated_processes: dict[str, dict[str, dict[str, Any]]] = {
        nozzle: {} for nozzle in NOZZLES
    }
    for nozzle in NOZZLES:
        name = canonical_machine(nozzle)
        if name not in machines:
            failures.append(f"missing machine: {name}")
            continue
        direct = machines[name]
        effective = resolved(name, machines)
        if "HF" not in str(direct.get("inherits", "")):
            failures.append(f"{name}: non-HF machine base {direct.get('inherits')!r}")
        if "HF_NOZZLE" not in scalar(effective.get("printer_notes")):
            failures.append(f"{name}: effective printer_notes lacks HF_NOZZLE")
        if scalar(direct.get("nozzle_diameter")) != nozzle:
            failures.append(f"{name}: wrong nozzle diameter {direct.get('nozzle_diameter')!r}")
        if set(direct.get("default_nozzle_volume_type") or []) != {"High Flow"}:
            failures.append(f"{name}: nozzle volume type is not High Flow")

        for mode in MODES:
            matches = [
                data
                for process_name, data in processes.items()
                if process_name.endswith(f"@{name}") and f" {mode} @" in process_name
            ]
            if len(matches) != 1:
                failures.append(f"{name}: expected one {mode} process, found {len(matches)}")
                continue
            process = matches[0]
            curated_processes[nozzle][mode] = process
            if "HF" not in str(process.get("inherits", "")):
                failures.append(
                    f"{process['name']}: non-HF process base {process.get('inherits')!r}"
                )
            expected_support = {
                "support_type": "tree(auto)",
                "support_style": "tree_hybrid",
                "support_remove_small_overhang": "0",
                "tree_support_wall_count": "2",
                "seam_position": "aligned_back",
            }
            for key, expected in expected_support.items():
                if scalar(process.get(key)) != expected:
                    failures.append(
                        f"{process['name']}: {key}={process.get(key)!r}, expected {expected!r}"
                    )
            machine_accel = float(scalar(effective.get("machine_max_acceleration_x"), "0"))
            for key in (
                "default_acceleration",
                "outer_wall_acceleration",
                "inner_wall_acceleration",
                "top_surface_acceleration",
                "internal_solid_infill_acceleration",
                "sparse_infill_acceleration",
                "bridge_acceleration",
                "initial_layer_acceleration",
                "travel_acceleration",
            ):
                value = float(scalar(process.get(key), "0"))
                if value <= 0 or value > machine_accel:
                    failures.append(
                        f"{process['name']}: {key}={value:g} outside 0..{machine_accel:g}"
                    )

    filament_paths = sorted(CODEX_FILAMENTS.glob("* - Prusa Core One @Codex.json"))
    filament_paths += sorted(CODEX_FILAMENTS.glob("* - Prusa CORE One L @Codex.json"))
    canonical = {canonical_machine(nozzle) for nozzle in NOZZLES}
    max_mvs = 0.0
    for path in filament_paths:
        data = load_json(path)
        compatible = set(data.get("compatible_printers") or [])
        missing = canonical - compatible
        if missing:
            failures.append(f"{path.name}: missing {sorted(missing)}")
        try:
            mvs = float(scalar(data.get("filament_max_volumetric_speed")))
            flow = float(scalar(data.get("filament_flow_ratio")))
            temperature = float(scalar(data.get("nozzle_temperature")))
        except ValueError:
            failures.append(f"{path.name}: non-numeric flow or temperature contract")
            continue
        if min(mvs, flow, temperature) <= 0:
            failures.append(f"{path.name}: non-positive flow or temperature contract")
        max_mvs = max(max_mvs, mvs)

    for nozzle, modes in curated_processes.items():
        if set(modes) != set(MODES):
            continue
        for key in ("outer_wall_speed", "inner_wall_speed", "sparse_infill_speed"):
            values = [float(scalar(modes[mode].get(key))) for mode in MODES]
            if values != sorted(values):
                failures.append(f"{nozzle}: {key} is not ordered Tank<=Quality<=Fast<=Draft: {values}")
        for mode in ("Fast", "Draft"):
            process = modes[mode]
            layer = float(scalar(process.get("layer_height")))
            width = float(scalar(process.get("sparse_infill_line_width")))
            speed = float(scalar(process.get("sparse_infill_speed")))
            demand = layer * width * speed
            if demand + 0.05 < max_mvs:
                failures.append(
                    f"{process['name']}: hidden-path demand {demand:.2f} mm3/s "
                    f"does not expose the catalog ceiling {max_mvs:.2f} mm3/s"
                )

    pc_pbt_cf = load_json(
        CODEX_FILAMENTS / "PC-PBT-CF Codex-Push Plastic - Prusa CORE One L @Codex.json"
    )
    start = scalar(pc_pbt_cf.get("filament_start_gcode"))
    required = {
        "M572 S": "nozzle-aware M572 pressure advance",
        "==0.6}0.025": "0.6 mm PA 0.025",
        "M142 S45": "45 C heatbreak target",
    }
    for token, description in required.items():
        if token not in start:
            failures.append(f"PC-PBT-CF: missing {description}")
    if scalar(pc_pbt_cf.get("chamber_temperature")) != "40":
        failures.append("PC-PBT-CF: chamber target is not 40 C")

    if failures:
        print(f"FAIL: {len(failures)} Prusa CORE One L HF contract issue(s)")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print(
        "PASS: 4 HF machines, 16 HF processes, "
        f"{len(filament_paths)} compatible Codex filaments; "
        f"Fast/Draft hidden paths expose the {max_mvs:g} mm3/s catalog ceiling"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
