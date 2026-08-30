#!/usr/bin/env python3
"""Build and install the curated TinMan Codex machine-profile catalog.

TinManX1 keeps upstream machine presets as inheritance bases, but exposes only
four selector-facing variants for each curated machine: 0.4, 0.6, 0.8, and
1.0 mm. Every conventional printer/nozzle variant receives distinct Tank,
Quality, Fast, and Draft processes, while FibreSeek keeps its purpose-built
continuous-fiber modes. FibreSeek filament compatibility is also migrated to
the canonical machine names so its
plastic and continuous-fiber profiles remain selectable after the old machine
names are hidden.

With --apply-live the script also creates a recoverable backup, mirrors the
generated resources into the installed app and Application Support, removes
legacy user machine copies, migrates their connection details into a private
per-machine overlay, and rewrites the enabled-model list to the curated catalog.
It intentionally does not alter filament tuning values.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
PROFILES_ROOT = REPO_ROOT / "resources" / "profiles"
DEFAULT_APP_SUPPORT = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_APP_PROFILES = Path("/Applications/TinManX1.app/Contents/Resources/profiles")
DEFAULT_BACKUP_ROOT = Path.home() / ".tinmanx1" / "machine-profile-cleanup-backups"

NOZZLES = ("0.4", "0.6", "0.8", "1.0")
CONTRACT_VERSION = "5"
NAMESPACE = uuid.UUID("c1f4d9e2-7a3b-5c8d-9e0f-1a2b3c4d5e6f")
ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
CONNECTION_SECTION = "tinman_machine_connections"
CONNECTION_OPTIONS = (
    "bbl_use_printhost",
    "host_type",
    "printer_agent",
    "print_host",
    "print_host_webui",
    "printhost_apikey",
    "flashforge_serial_number",
    "printhost_cafile",
    "printhost_port",
    "printhost_authorization_type",
    "printhost_user",
    "printhost_password",
    "printhost_ssl_ignore_revoke",
)


@dataclass(frozen=True)
class MachineFamily:
    vendor: str
    model: str
    source_names: dict[str, str]
    aliases: tuple[str, ...] = ()
    composite_second_nozzle: str | None = None
    high_flow_nozzles: bool = True

    def canonical_name(self, nozzle: str) -> str:
        return f"{self.model} {nozzle} nozzle - TinMan Codex"

    def source_name(self, nozzle: str) -> str:
        return self.source_names.get(nozzle, self.source_names["0.8"])


def source_series(pattern: str) -> dict[str, str]:
    return {nozzle: pattern.format(nozzle=nozzle) for nozzle in NOZZLES[:-1]}


@dataclass(frozen=True)
class ProcessMode:
    name: str
    layer_factor: float
    wall_loops: int
    shell_layers: int
    infill_density: str
    infill_pattern: str
    speed_scale: float
    acceleration_scale: float


PROCESS_MODES = (
    ProcessMode("Quality", 0.50, 4, 5, "25%", "crosshatch", 1.00, 1.00),
    ProcessMode("Fast", 0.60, 3, 4, "18%", "rectilinear", 1.55, 1.55),
    ProcessMode("Draft", 0.70, 2, 3, "12%", "rectilinear", 2.00, 2.00),
    ProcessMode("Tank", 0.40, 6, 8, "45%", "gyroid", 0.65, 0.60),
)
QUALITY_MODE = PROCESS_MODES[0]


FAMILIES = (
    MachineFamily("BBL", "Bambu Lab H2D", source_series("Bambu Lab H2D {nozzle} nozzle")),
    MachineFamily(
        "BBL",
        "Bambu Lab X1 Carbon",
        source_series("Bambu Lab X1 Carbon {nozzle} nozzle"),
        aliases=("Bambu Lab X1 Carbon Tinman",),
    ),
    MachineFamily("Creality", "Creality K2 Plus", source_series("Creality K2 Plus {nozzle} nozzle")),
    MachineFamily(
        "Elegoo",
        "Elegoo Centauri Carbon",
        source_series("Elegoo Centauri Carbon {nozzle} nozzle"),
        aliases=("Elegoo Centauri Carbon 2", "Centauri COSMOS Tinman"),
    ),
    MachineFamily(
        "Prusa",
        "Prusa CORE One L",
        {
            "0.4": "Prusa CORE One L HF 0.4 nozzle",
            "0.6": "Prusa CORE One L HF 0.6 nozzle",
            # Prusa has no native 1.0 mm CORE One L preset. The generated
            # 1.0 profile falls back to this HF 0.8 machine contract and
            # overrides its complete nozzle geometry below.
            "0.8": "Prusa CORE One L HF 0.8 nozzle",
        },
        aliases=("Prusa CORE One L HF",),
    ),
    MachineFamily(
        "Qidi",
        "Qidi X-Plus 4",
        source_series("Qidi X-Plus 4 {nozzle} nozzle"),
        aliases=("QIDI Plus 4", "Qidi Plus 4", "CURRENT QIDI"),
    ),
    MachineFamily(
        "Qidi",
        "QidiMaxEz",
        {nozzle: f"QidiMaxEz {nozzle}" for nozzle in NOZZLES},
        aliases=("Qidi Max EZ", "Max EZ"),
    ),
    MachineFamily(
        "Ratrig",
        "RatRig V-Core 4 IDEX 500",
        source_series("RatRig V-Core 4 IDEX 500 {nozzle} nozzle"),
    ),
    MachineFamily(
        "Ratrig",
        "RatRig V-Core 4 IDEX 500 COPY MODE",
        source_series("RatRig V-Core 4 IDEX 500 COPY MODE {nozzle} nozzle"),
    ),
    MachineFamily(
        "Ratrig",
        "RatRig V-Core 4 IDEX 500 MIRROR MODE",
        source_series("RatRig V-Core 4 IDEX 500 MIRROR MODE {nozzle} nozzle"),
    ),
    MachineFamily(
        "Snapmaker",
        "Snapmaker U1",
        {nozzle: f"Snapmaker U1 ({nozzle} nozzle)" for nozzle in NOZZLES[:-1]},
        aliases=("CURRENT Snapmaker U1", "CURRENT U1", "fdm_U1"),
        high_flow_nozzles=False,
    ),
    MachineFamily("Sovol", "Sovol SV08 MAX", source_series("Sovol SV08 MAX {nozzle} nozzle")),
    MachineFamily(
        "TinManX1",
        "FibreSeek Seeker 3",
        {
            "0.4": "FibreSeek Seeker 3 0.4+0.7 composite nozzle",
            "0.6": "FibreSeek Seeker 3 0.6+0.7 composite nozzle",
            "0.8": "FibreSeek Seeker 3 0.8+0.7 composite nozzle",
        },
        aliases=("FibreSeek Seeker 3 - Codex",),
        composite_second_nozzle="0.7",
    ),
)

INDEX_VERSIONS = {
    "BBL": "02.01.00.20",
    "Creality": "02.03.02.76",
    "Elegoo": "02.04.00.07",
    "Prusa": "02.04.00.06",
    "Qidi": "02.04.02.13",
    "Ratrig": "02.04.00.03",
    "Snapmaker": "02.04.00.08",
    "Sovol": "02.04.00.02",
    "TinManX1": "02.04.00.16",
}

PROFILE_INDENTS: dict[str, int | str] = {
    "Elegoo": 4,
    "Qidi": 2,
    "TinManX1": 2,
}

PROFILE_FILE_INDENTS: dict[str, int | str] = {
    "Elegoo/machine/ECC/Elegoo Centauri Carbon.json": "\t",
    "Qidi/machine/Qidi X-Plus 4.json": 4,
    "Qidi/machine/QidiMaxEz.json": 4,
    "Snapmaker/machine/Snapmaker U1.json": 4,
}

DEFAULT_CODEX_FILAMENTS = {
    "Bambu Lab H2D": "PLA Codex-Polymaker - Bambu H2D @Codex",
    "Bambu Lab X1 Carbon": "PLA Codex-Polymaker - Bambu X1C HF @Codex",
    "Creality K2 Plus": "PLA Codex-Polymaker - Creality K2 Plus @Codex",
    "Elegoo Centauri Carbon": "PLA Codex-Polymaker - Elegoo Centauri @Codex",
    "Prusa CORE One L": "PLA Codex-Polymaker - Prusa Core One @Codex",
    "Qidi X-Plus 4": "PLA Codex-Polymaker - Qidi X-Plus 4 @Codex",
    "QidiMaxEz": "PLA Codex-Polymaker - Qidi X-Plus 4 @Codex",
    "RatRig V-Core 4 IDEX 500": "PLA Codex-Polymaker - RatRig V-Core 4 @Codex",
    "RatRig V-Core 4 IDEX 500 COPY MODE": "PLA Codex-Polymaker - RatRig V-Core 4 @Codex",
    "RatRig V-Core 4 IDEX 500 MIRROR MODE": "PLA Codex-Polymaker - RatRig V-Core 4 @Codex",
    "Snapmaker U1": "PLA Codex-Polymaker - Snapmaker U1 @Codex",
    "Sovol SV08 MAX": "PLA Codex-Polymaker - Sovol SV08 MAX @Codex",
}


# Prusa uses one deliberately conservative first-layer contract across every
# standard CORE One L nozzle. Keep these values separate from the generic
# nozzle-scaled TinMan modes so catalog regeneration cannot change bed contact.
PRUSA_CORE_ONE_L_FIRST_LAYER = {
    "0.4": {
        "initial_layer_print_height": "0.20",
        "line_width": "0.45",
        "initial_layer_line_width": "0.50",
        "outer_wall_line_width": "0.45",
        "inner_wall_line_width": "0.45",
        "top_surface_line_width": "0.42",
        "sparse_infill_line_width": "0.45",
        "internal_solid_infill_line_width": "0.45",
        "support_line_width": "0.40",
        "initial_layer_speed": "45",
        "initial_layer_infill_speed": "100",
    },
    "0.6": {
        "initial_layer_print_height": "0.20",
        "line_width": "0.68",
        "initial_layer_line_width": "0.68",
        "outer_wall_line_width": "0.68",
        "inner_wall_line_width": "0.68",
        "top_surface_line_width": "0.55",
        "sparse_infill_line_width": "0.68",
        "internal_solid_infill_line_width": "0.68",
        "support_line_width": "0.50",
        "initial_layer_speed": "45",
        "initial_layer_infill_speed": "70",
    },
    "0.8": {
        "initial_layer_print_height": "0.20",
        "line_width": "0.90",
        "initial_layer_line_width": "1.00",
        "outer_wall_line_width": "0.90",
        "inner_wall_line_width": "0.90",
        "top_surface_line_width": "0.75",
        "sparse_infill_line_width": "0.90",
        "internal_solid_infill_line_width": "0.90",
        "support_line_width": "0.65",
        "initial_layer_speed": "45",
        "initial_layer_infill_speed": "55",
    },
    # Prusa does not publish a standard 1.0 mm CORE One L profile. These
    # dimensions conservatively extend its 0.8 mm ratios while retaining the
    # exact 0.20 mm / 500 mm/s^2 first-layer motion contract.
    "1.0": {
        "initial_layer_print_height": "0.20",
        "line_width": "1.10",
        "initial_layer_line_width": "1.20",
        "outer_wall_line_width": "1.10",
        "inner_wall_line_width": "1.10",
        "top_surface_line_width": "0.95",
        "sparse_infill_line_width": "1.10",
        "internal_solid_infill_line_width": "1.10",
        "support_line_width": "0.80",
        "initial_layer_speed": "45",
        "initial_layer_infill_speed": "45",
    },
}

PRUSA_CORE_ONE_L_PROCESS_BASES = {
    "0.4": {
        "Tank": "0.25mm STRUCTURAL @CORE One L HF 0.4",
        "Quality": "0.25mm STRUCTURAL @CORE One L HF 0.4",
        "Fast": "0.25mm SPEED @CORE One L HF 0.4",
        "Draft": "0.28mm DRAFT @CORE One L HF 0.4",
    },
    "0.6": {
        "Tank": "0.32mm STRUCTURAL @CORE One L HF 0.6",
        "Quality": "0.32mm STRUCTURAL @CORE One L HF 0.6",
        "Fast": "0.40mm SPEED @CORE One L HF 0.6",
        "Draft": "0.40mm SPEED @CORE One L HF 0.6",
    },
    "0.8": {
        "Tank": "0.30mm STRUCTURAL @CORE One L HF 0.8",
        "Quality": "0.40mm STRUCTURAL @CORE One L HF 0.8",
        "Fast": "0.40mm SPEED @CORE One L HF 0.8",
        "Draft": "0.55mm SPEED @CORE One L HF 0.8",
    },
    "1.0": {
        "Tank": "0.40mm STRUCTURAL @CORE One L HF 0.8",
        "Quality": "0.40mm STRUCTURAL @CORE One L HF 0.8",
        "Fast": "0.55mm SPEED @CORE One L HF 0.8",
        "Draft": "0.55mm SPEED @CORE One L HF 0.8",
    },
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    indent: int | str = 4
    try:
        relative = path.relative_to(PROFILES_ROOT)
        if "TinMan Codex" not in relative.parts:
            vendor_key = path.stem if len(relative.parts) == 1 else relative.parts[0]
            indent = PROFILE_FILE_INDENTS.get(
                relative.as_posix(), PROFILE_INDENTS.get(vendor_key, "\t")
            )
    except ValueError:
        pass
    path.write_text(json.dumps(data, indent=indent, ensure_ascii=True) + "\n")


def setting_id(vendor: str, profile_type: str, name: str) -> str:
    value = int.from_bytes(uuid.uuid5(NAMESPACE, f"{vendor}/{profile_type}/{name}").bytes, "big")
    digits: list[str] = []
    for _ in range(16):
        digits.append(ALPHABET[value % 62])
        value //= 62
    return "".join(reversed(digits))


def indexed_profiles(vendor: str, profile_type: str) -> dict[str, tuple[Path, dict[str, Any]]]:
    result: dict[str, tuple[Path, dict[str, Any]]] = {}
    root = PROFILES_ROOT / vendor / profile_type
    if not root.is_dir():
        return result
    for path in sorted(root.rglob("*.json")):
        try:
            data = load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        name = data.get("name")
        if name:
            result[str(name)] = (path, data)
    return result


def nozzle_arrays(source: dict[str, Any], family: MachineFamily, nozzle: str) -> tuple[list[str], list[str], list[str]]:
    count = len(source.get("nozzle_diameter") or []) or 1
    diameters = [nozzle] * count
    if family.composite_second_nozzle and count >= 2:
        diameters[1] = family.composite_second_nozzle

    minimum = [f"{float(value) * 0.20:.2f}" for value in diameters]
    maximum = [f"{float(value) * 0.70:.2f}" for value in diameters]
    if family.composite_second_nozzle and count >= 2:
        minimum[1] = "0.14"
        maximum[1] = "0.40"
    return diameters, minimum, maximum


def nozzle_flow_types(family: MachineFamily, count: int) -> list[str]:
    flow_type = "High Flow" if family.high_flow_nozzles else "Standard"
    return [flow_type] * count


def process_score(
    data: dict[str, Any],
    family: MachineFamily,
    source_machine: str,
    nozzle: str,
    composite: bool,
) -> float:
    compatible = data.get("compatible_printers") or []
    name = str(data.get("name", ""))
    condition = str(data.get("compatible_printers_condition", ""))
    explicitly_compatible = source_machine in compatible
    conditionally_compatible = (
        f"nozzle_diameter[0]=={nozzle}" in condition
        and family.model.removeprefix("Prusa ").replace("PRUSA ", "")[:10].lower() in name.lower()
    )
    if not explicitly_compatible and not conditionally_compatible:
        return -10_000
    score = 0.0
    if composite and "Plastic + Continuous Fiber Medium" in name:
        score += 200
    for token, points in (("Standard", 60), ("Quality", 55), ("Optimal", 45), ("Fine", 10)):
        if token in name:
            score += points
    for token, points in (("Draft", 30), ("Support", 50), ("Strength", 15), ("Copy", 20)):
        if token in name:
            score -= points
    try:
        layer_height_value = data.get("layer_height")
        if not layer_height_value:
            layer_match = re.match(r"(\d+(?:\.\d+)?)mm", name)
            layer_height_value = layer_match.group(1) if layer_match else 0
        layer_height = float(layer_height_value)
        score -= abs(layer_height - float(nozzle) * 0.5) * 100
    except (TypeError, ValueError):
        score -= 100
    return score


def choose_source_process(
    process_profiles: dict[str, tuple[Path, dict[str, Any]]],
    family: MachineFamily,
    source_machine: str,
    nozzle: str,
    composite: bool,
) -> tuple[str, dict[str, Any]]:
    candidates = [
        (process_score(data, family, source_machine, nozzle, composite), name, data)
        for name, (_, data) in process_profiles.items()
    ]
    candidates = [candidate for candidate in candidates if candidate[0] > -10_000]
    if not candidates:
        raise RuntimeError(f"no process profile is compatible with {source_machine}")
    _, name, data = max(candidates, key=lambda item: (item[0], item[1]))
    return name, data


def process_modes(family: MachineFamily) -> tuple[ProcessMode | None, ...]:
    # Continuous-fiber profiles have their own light/medium/heavy process
    # contract. Every conventional printer exposes the same four predictable
    # plastic-printing modes for every supported nozzle.
    return (None,) if family.composite_second_nozzle else PROCESS_MODES


def process_name(
    family: MachineFamily,
    nozzle: str,
    mode: ProcessMode | None = None,
) -> str:
    layer = 0.20 if family.composite_second_nozzle else float(nozzle) * 0.5
    label = "Plastic + Continuous Fiber Medium" if family.composite_second_nozzle else "Quality"
    if mode is not None:
        layer = float(nozzle) * mode.layer_factor
        label = mode.name
    return f"{layer:.2f}mm {label} @{family.canonical_name(nozzle)}"


def default_process_name(family: MachineFamily, nozzle: str) -> str:
    mode = None if family.composite_second_nozzle else QUALITY_MODE
    return process_name(family, nozzle, mode)


def prusa_core_one_l_source_process_name(nozzle: str, mode: ProcessMode) -> str:
    return PRUSA_CORE_ONE_L_PROCESS_BASES[nozzle][mode.name]


def mode_settings(
    mode: ProcessMode,
    nozzle: str,
    family: MachineFamily | None = None,
) -> dict[str, str]:
    diameter = float(nozzle)
    nozzle_speed_scale = {"0.4": 1.00, "0.6": 0.80, "0.8": 0.65, "1.0": 0.55}[nozzle]
    speed = mode.speed_scale * nozzle_speed_scale
    acceleration = mode.acceleration_scale

    def scaled(value: float, factor: float = speed) -> str:
        return str(max(1, round(value * factor)))

    def dimension(factor: float) -> str:
        return f"{diameter * factor:.2f}"

    settings = {
        "layer_height": f"{diameter * mode.layer_factor:.2f}",
        "initial_layer_print_height": f"{diameter * 0.50:.2f}",
        "line_width": dimension(1.05),
        "initial_layer_line_width": dimension(1.10),
        "outer_wall_line_width": dimension(1.00),
        "inner_wall_line_width": dimension(1.05),
        "top_surface_line_width": dimension(1.00),
        "sparse_infill_line_width": dimension(1.10),
        "internal_solid_infill_line_width": dimension(1.05),
        "support_line_width": dimension(1.00),
        "wall_loops": str(mode.wall_loops),
        "top_shell_layers": str(mode.shell_layers),
        "bottom_shell_layers": str(mode.shell_layers),
        "sparse_infill_density": mode.infill_density,
        "sparse_infill_pattern": mode.infill_pattern,
        "outer_wall_speed": scaled(60),
        "inner_wall_speed": scaled(100),
        "small_perimeter_speed": scaled(50),
        "sparse_infill_speed": scaled(130),
        "internal_solid_infill_speed": scaled(90),
        "top_surface_speed": scaled(45),
        "gap_infill_speed": scaled(60),
        "bridge_speed": scaled(30),
        "support_speed": scaled(60),
        "initial_layer_speed": scaled(30),
        "default_acceleration": scaled(5000, acceleration),
        "outer_wall_acceleration": scaled(2000, acceleration),
        "inner_wall_acceleration": scaled(4000, acceleration),
        "top_surface_acceleration": scaled(1500, acceleration),
        "internal_solid_infill_acceleration": scaled(4000, acceleration),
        "sparse_infill_acceleration": scaled(6000, acceleration),
        "bridge_acceleration": scaled(1800, acceleration),
        "initial_layer_acceleration": scaled(1200, acceleration),
        "travel_acceleration": scaled(8000, acceleration),
    }

    if family is not None and family.model in {"Qidi X-Plus 4", "QidiMaxEz"}:
        # Every installed Plus 4 / Max EZ nozzle is high flow. Spend that
        # capacity mainly on hidden toolpaths so surface quality remains the
        # limiting contract. The mechanically identical Plus 4 and Max EZ use
        # the same reviewed 10,000 mm/s^2 acceleration table.
        speed_factors = {
            "outer_wall_speed": 1.10,
            "inner_wall_speed": 1.20,
            "small_perimeter_speed": 1.10,
            "sparse_infill_speed": 1.20,
            "internal_solid_infill_speed": 1.15,
            "top_surface_speed": 1.08,
            "gap_infill_speed": 1.15,
            "support_speed": 1.15,
        }
        for key, factor in speed_factors.items():
            settings[key] = str(max(1, round(float(settings[key]) * factor)))

        plus4_acceleration = {
            "Tank": ("3500", "1400", "2800", "1200", "2800", "4200", "1500", "700", "7000"),
            "Quality": ("6000", "2400", "4800", "1800", "4800", "7200", "2000", "900", "9000"),
            "Fast": ("8000", "3200", "6500", "2400", "6500", "9000", "2500", "1000", "10000"),
            "Draft": ("9000", "3600", "7500", "2800", "7500", "10000", "2800", "1200", "10000"),
        }
        acceleration_keys = (
            "default_acceleration",
            "outer_wall_acceleration",
            "inner_wall_acceleration",
            "top_surface_acceleration",
            "internal_solid_infill_acceleration",
            "sparse_infill_acceleration",
            "bridge_acceleration",
            "initial_layer_acceleration",
            "travel_acceleration",
        )
        settings.update(dict(zip(acceleration_keys, plus4_acceleration[mode.name])))
        if family.model == "QidiMaxEz":
            settings["travel_speed"] = "500"
        return settings

    if family is None or family.model != "Prusa CORE One L":
        return settings

    settings.update(PRUSA_CORE_ONE_L_FIRST_LAYER[nozzle])
    is_speed_mode = mode.name in {"Fast", "Draft"}
    large_nozzle = nozzle in {"0.8", "1.0"}
    if nozzle == "0.4" and mode.name == "Fast":
        # The generic matrix left the 0.4 HF profile below the hotend's useful
        # range even on hidden paths. These remain below Prusa's corresponding
        # HF SPEED values, while exterior and top-surface speeds stay unchanged.
        settings.update(
            {
                "inner_wall_speed": "180",
                "sparse_infill_speed": "275",
                "internal_solid_infill_speed": "170",
                "gap_infill_speed": "100",
            }
        )
    elif nozzle == "0.4" and mode.name == "Draft":
        # Match Prusa's HF Draft sparse-infill ceiling while retaining the
        # slower TinMan exterior-wall speed.
        settings["sparse_infill_speed"] = "300"
    settings.update(
        {
            "default_acceleration": "3000",
            "outer_wall_acceleration": (
                "1500" if not is_speed_mode else ("2500" if large_nozzle else "3000")
            ),
            "inner_wall_acceleration": (
                "2500" if not is_speed_mode else ("3000" if large_nozzle else "6000")
            ),
            "top_surface_acceleration": "1500" if is_speed_mode and large_nozzle else "2000",
            "internal_solid_infill_acceleration": (
                "4000" if not is_speed_mode else ("5000" if large_nozzle else "6000")
            ),
            "sparse_infill_acceleration": "7000" if is_speed_mode else "6000",
            "bridge_acceleration": "1000" if large_nozzle else "1500",
            "initial_layer_acceleration": "500",
            "travel_acceleration": "6000",
        }
    )
    if is_speed_mode and large_nozzle:
        settings["outer_wall_line_width"] = "1.00" if nozzle == "0.8" else "1.20"
        settings["inner_wall_line_width"] = settings["outer_wall_line_width"]
    support_interface_speed = {"0.4": "25", "0.6": "25", "0.8": "30", "1.0": "35"}
    support_xy_distance = {"0.4": "0.30", "0.6": "0.40", "0.8": "0.50", "1.0": "0.60"}
    branch_diameter = {"0.4": "3", "0.6": "4", "0.8": "5.5", "1.0": "6.5"}
    tip_diameter = {"0.4": "0.8", "0.6": "1.2", "0.8": "1.6", "1.0": "2.0"}
    settings.update(
        {
            "support_interface_speed": support_interface_speed[nozzle],
            "support_object_xy_distance": support_xy_distance[nozzle],
            "support_remove_small_overhang": "0",
            "support_type": "tree(auto)",
            "support_style": "tree_hybrid",
            "support_threshold_angle": "30",
            "tree_support_branch_diameter": branch_diameter[nozzle],
            "tree_support_tip_diameter": tip_diameter[nozzle],
            "tree_support_wall_count": "2",
            "seam_position": "aligned_back",
        }
    )
    if nozzle == "0.6" and mode.name == "Tank":
        settings["wall_loops"] = "5"
    return settings


def canonical_process(
    family: MachineFamily,
    nozzle: str,
    source_name: str,
    source: dict[str, Any],
    mode: ProcessMode | None = None,
) -> dict[str, Any]:
    name = process_name(family, nozzle, mode)
    data: dict[str, Any] = {
        "type": "process",
        "name": name,
        "inherits": source_name,
        "from": "system",
        "instantiation": "true",
        "print_settings_id": name,
        "compatible_printers": [family.canonical_name(nozzle)],
        "setting_id": setting_id(family.vendor, "process", name),
    }
    if mode is not None:
        data.update(mode_settings(mode, nozzle, family))
    elif nozzle == "1.0":
        data.update(
            {
                "layer_height": "0.5",
                "initial_layer_print_height": "0.4",
                "line_width": "1.05",
                "initial_layer_line_width": "1.10",
                "outer_wall_line_width": "1.00",
                "inner_wall_line_width": "1.10",
                "top_surface_line_width": "1.00",
                "sparse_infill_line_width": "1.10",
                "internal_solid_infill_line_width": "1.10",
                "support_line_width": "1.00",
            }
        )
    return data


def canonical_machine(
    family: MachineFamily,
    nozzle: str,
    source_name: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    name = family.canonical_name(nozzle)
    diameters, minimum, maximum = nozzle_arrays(source, family, nozzle)
    data = {
        "type": "machine",
        "name": name,
        "inherits": source_name,
        "from": "system",
        "instantiation": "true",
        "printer_model": family.model,
        "printer_variant": nozzle,
        "printer_settings_id": name,
        "nozzle_diameter": diameters,
        "default_nozzle_volume_type": nozzle_flow_types(family, len(diameters)),
        "min_layer_height": minimum,
        "max_layer_height": maximum,
        "default_print_profile": process_name(
            family, nozzle, None if family.composite_second_nozzle else QUALITY_MODE
        ),
        "setting_id": setting_id(family.vendor, "machine", name),
    }
    if family.model == "Bambu Lab X1 Carbon":
        # Do not rely on the upstream X1C inheritance chain for the installed
        # hardware declaration: every X1C nozzle in this fleet is hardened and
        # high flow, including the generated 1.0 mm profile.
        data["nozzle_type"] = ["hardened_steel"] * len(diameters)
    if default_filament := DEFAULT_CODEX_FILAMENTS.get(family.model):
        data["default_filament_profile"] = [default_filament]
    if family.model in {"Qidi X-Plus 4", "QidiMaxEz"}:
        # The user's Max EZ and Plus 4 are mechanically identical. Keep both
        # canonical slicer contracts aligned with their 10,000 mm/s^2 live
        # Klipper limit; velocity remains owned by each machine base.
        data.update(
            {
                "machine_max_acceleration_x": ["10000"],
                "machine_max_acceleration_y": ["10000"],
                "machine_max_acceleration_z": ["500"],
                "machine_max_acceleration_e": ["5000"],
                "machine_max_acceleration_extruding": ["10000"],
                "machine_max_acceleration_retracting": ["10000"],
                "machine_max_acceleration_travel": ["10000"],
                "machine_max_speed_x": ["600"],
                "machine_max_speed_y": ["600"],
                "machine_max_speed_z": ["20"],
                "machine_max_speed_e": ["80"],
                "machine_max_jerk_x": ["9"],
                "machine_max_jerk_y": ["9"],
                "machine_max_jerk_z": ["4"],
                "machine_max_jerk_e": ["4"],
            }
        )
    return data


def profile_data_for_item(vendor: str, item: dict[str, Any]) -> dict[str, Any] | None:
    sub_path = item.get("sub_path")
    if not sub_path:
        return None
    path = PROFILES_ROOT / vendor / str(sub_path)
    try:
        return load_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def update_model_nozzles(vendor: str, index: dict[str, Any], family: MachineFamily) -> None:
    for item in index.get("machine_model_list", []):
        if item.get("name") != family.model:
            continue
        path = PROFILES_ROOT / vendor / str(item["sub_path"])
        data = load_json(path)
        data["nozzle_diameter"] = ";".join(NOZZLES)
        write_json(path, data)
        return
    raise RuntimeError(f"{vendor} index has no machine model entry for {family.model}")


def update_fibreseek_filament_compatibility(index: dict[str, Any], family: MachineFamily) -> None:
    """Replace hidden FibreSeek machine aliases with the four canonical names."""
    canonical = [family.canonical_name(nozzle) for nozzle in NOZZLES]
    for item in index.get("filament_list", []):
        data = profile_data_for_item(family.vendor, item)
        if data is None:
            continue
        compatible = data.get("compatible_printers")
        if not isinstance(compatible, list):
            continue
        if not any(family_for_name(str(name)) == family for name in compatible):
            continue
        preserved = [
            str(name)
            for name in compatible
            if family_for_name(str(name)) != family
        ]
        updated = list(dict.fromkeys([*preserved, *canonical]))
        if updated != compatible:
            data["compatible_printers"] = updated
            write_json(PROFILES_ROOT / family.vendor / str(item["sub_path"]), data)


def generate_repo_catalog() -> tuple[int, int]:
    families_by_vendor: dict[str, list[MachineFamily]] = {}
    for family in FAMILIES:
        families_by_vendor.setdefault(family.vendor, []).append(family)

    machine_count = 0
    process_count = 0
    for vendor, families in families_by_vendor.items():
        index_path = PROFILES_ROOT / f"{vendor}.json"
        index = load_json(index_path)
        machine_profiles = indexed_profiles(vendor, "machine")
        process_profiles = indexed_profiles(vendor, "process")
        target_models = {family.model for family in families}

        # This directory is generated output. Clear only its JSON products so
        # renamed or retired modes cannot linger as hidden stale presets.
        generated_process_dir = PROFILES_ROOT / vendor / "process" / "TinMan Codex"
        if generated_process_dir.is_dir():
            for path in generated_process_dir.glob("*.json"):
                path.unlink()

        kept_machines = []
        for item in index.get("machine_list", []):
            data = profile_data_for_item(vendor, item)
            if data and data.get("printer_model") in target_models and data.get("printer_variant"):
                continue
            if " - TinMan Codex" in str(item.get("name", "")):
                continue
            kept_machines.append(item)

        kept_processes = [
            item for item in index.get("process_list", [])
            if " - TinMan Codex" not in str(item.get("name", ""))
        ]

        for family in families:
            update_model_nozzles(vendor, index, family)
            if family.composite_second_nozzle:
                update_fibreseek_filament_compatibility(index, family)

            # Orca resolves `inherits` only against presets declared in the
            # vendor index. Keep the minimum source presets indexed as hidden
            # implementation details; the compiled combo-box predicate keeps
            # them out of both printer selectors.
            source_nozzles: dict[str, str] = {}
            for nozzle in NOZZLES:
                source_nozzles.setdefault(family.source_name(nozzle), nozzle)
            for source_name, source_nozzle in source_nozzles.items():
                source_entry = machine_profiles.get(source_name)
                if source_entry is None:
                    raise RuntimeError(f"missing {vendor} machine source: {source_name}")
                source_path, source_data = source_entry
                if source_data.get("printer_variant") != source_nozzle:
                    source_data["printer_variant"] = source_nozzle
                    write_json(source_path, source_data)
                if not any(item.get("name") == source_name for item in kept_machines):
                    kept_machines.append(
                        {
                            "name": source_name,
                            "sub_path": source_path.relative_to(PROFILES_ROOT / vendor).as_posix(),
                        }
                    )

            for nozzle in NOZZLES:
                source_machine_name = family.source_name(nozzle)
                source_entry = machine_profiles.get(source_machine_name)
                if source_entry is None:
                    raise RuntimeError(f"missing {vendor} machine source: {source_machine_name}")
                _, source_machine = source_entry

                process_source_nozzle = (
                    nozzle if nozzle != "1.0" or "1.0" in family.source_names else "0.8"
                )
                process_source_machine = family.source_name(process_source_nozzle)
                source_process_name, source_process = choose_source_process(
                    process_profiles,
                    family,
                    process_source_machine,
                    process_source_nozzle,
                    family.composite_second_nozzle is not None,
                )

                machine = canonical_machine(family, nozzle, source_machine_name, source_machine)
                machine_rel = Path("machine") / "TinMan Codex" / f"{machine['name']}.json"
                write_json(PROFILES_ROOT / vendor / machine_rel, machine)
                kept_machines.append({"name": machine["name"], "sub_path": machine_rel.as_posix()})
                machine_count += 1
                for mode in process_modes(family):
                    selected_process_name = source_process_name
                    selected_process = source_process
                    if family.model == "Prusa CORE One L" and mode is not None:
                        selected_process_name = prusa_core_one_l_source_process_name(nozzle, mode)
                        preferred_entry = process_profiles.get(selected_process_name)
                        if preferred_entry is None:
                            raise RuntimeError(
                                f"missing Prusa CORE One L process source: {selected_process_name}"
                            )
                        _, selected_process = preferred_entry
                    process = canonical_process(
                        family, nozzle, selected_process_name, selected_process, mode
                    )
                    process_rel = Path("process") / "TinMan Codex" / f"{process['name']}.json"
                    write_json(PROFILES_ROOT / vendor / process_rel, process)
                    kept_processes.append(
                        {"name": process["name"], "sub_path": process_rel.as_posix()}
                    )
                    process_count += 1

        index["version"] = INDEX_VERSIONS[vendor]
        index["tinman_codex_machine_contract"] = CONTRACT_VERSION
        index["machine_list"] = kept_machines
        index["process_list"] = kept_processes
        write_json(index_path, index)

    return machine_count, process_count


def family_for_name(name: str) -> MachineFamily | None:
    lowered = name.lower()
    matches: list[tuple[int, MachineFamily]] = []
    for family in FAMILIES:
        tokens = (family.model, *family.aliases)
        for token in tokens:
            if token.lower() in lowered:
                matches.append((len(token), family))
    return max(matches, default=(0, None), key=lambda item: item[0])[1]


def nozzle_from_name(name: str) -> str | None:
    match = re.search(r"(?<!\d)(0\.[468]|1\.0)(?:\+0\.7)?(?:\s*mm)?(?:\s*nozzle)?", name, re.IGNORECASE)
    return match.group(1) if match else None


def serialized_connection_value(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def default_webui_for_family(family: MachineFamily, address: str) -> str:
    """Return the printer UI origin while keeping the control API address separate."""
    if family.vendor != "Creality" or not address:
        return address

    candidate = address if "://" in address else f"http://{address}"
    parsed = urlsplit(candidate)
    if parsed.port is not None or (parsed.path and parsed.path != "/"):
        return candidate

    hostname = parsed.hostname or ""
    if not hostname:
        return candidate
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:4408"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials += f":{parsed.password}"
        netloc = f"{credentials}@{netloc}"
    return urlunsplit((parsed.scheme or "http", netloc, "/", parsed.query, parsed.fragment))


def collect_live_connections(app_support: Path, conf: dict[str, Any]) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Resolve one current address and any explicit host options per family."""
    addresses: dict[str, str] = {}
    details: dict[str, dict[str, str]] = {}
    overlay = conf.get(CONNECTION_SECTION)
    if isinstance(overlay, dict):
        for family in FAMILIES:
            prefix = f"{family.model}::"
            family_details = {
                key[len(prefix):]: str(value)
                for key, value in overlay.items()
                if key.startswith(prefix) and key[len(prefix):] in CONNECTION_OPTIONS
            }
            if family_details:
                details[family.model] = family_details
                address = family_details.get("print_host") or family_details.get("print_host_webui")
                if address:
                    addresses[family.model] = address

    # Saved user copies contain the richest connection settings, so retain
    # those before the obsolete presets are removed from the visible catalog.
    for path in sorted((app_support / "user").glob("*/machine/*.json")):
        try:
            data = load_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        family = family_for_name(f"{path.stem} {data.get('printer_model', '')}")
        if not family:
            continue
        host = str(data.get("print_host") or data.get("print_host_webui") or "")
        if not host:
            continue
        family_details = details.setdefault(family.model, {})
        for option in CONNECTION_OPTIONS:
            if option in data:
                value = serialized_connection_value(data[option])
                if value:
                    family_details[option] = value
        addresses[family.model] = host

    ip_addresses = conf.get("ip_address")
    if not isinstance(ip_addresses, dict):
        ip_addresses = {}
    # Prefer an existing canonical mapping, then recover any older alias.
    for family in FAMILIES:
        if family.model in addresses:
            continue
        for nozzle in NOZZLES:
            address = str(ip_addresses.get(family.canonical_name(nozzle), ""))
            if address:
                addresses[family.model] = address
                break
        if family.model in addresses:
            continue
        for name, value in ip_addresses.items():
            if family_for_name(str(name)) == family and value:
                addresses[family.model] = str(value)
                break

    # Local device discovery fills families that never had a preset-side host,
    # notably the serial-bound Bambu machines.
    bambu_types = {"O1D": "Bambu Lab H2D", "BL-P001": "Bambu Lab X1 Carbon"}
    local_machines = conf.get("local_machines")
    if isinstance(local_machines, dict):
        for machine in local_machines.values():
            if not isinstance(machine, dict):
                continue
            printer_type = str(machine.get("printer_type", ""))
            family = family_for_name(f"{machine.get('dev_name', '')} {printer_type}")
            if family is None and printer_type in bambu_types:
                family = next(item for item in FAMILIES if item.model == bambu_types[printer_type])
            address = str(machine.get("dev_ip", ""))
            if family and address and family.model not in addresses:
                addresses[family.model] = address

    return addresses, details


def backup_live_state(app_support: Path, backup_root: Path) -> Path:
    backup = backup_root / datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    backup.mkdir(parents=True, exist_ok=False)
    for rel in (Path("OrcaSlicer.conf"), Path("printers")):
        source = app_support / rel
        target = backup / rel
        if source.is_dir():
            shutil.copytree(source, target)
        elif source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for machine_dir in sorted((app_support / "user").glob("*/machine")):
        shutil.copytree(machine_dir, backup / machine_dir.relative_to(app_support))
    for vendor in sorted({family.vendor for family in FAMILIES}):
        rels = [
            Path("system") / f"{vendor}.json",
            Path("system") / vendor / "machine" / "TinMan Codex",
            Path("system") / vendor / "process" / "TinMan Codex",
        ]
        machine_profiles = indexed_profiles(vendor, "machine")
        for family in (item for item in FAMILIES if item.vendor == vendor):
            for source_name in dict.fromkeys(family.source_name(nozzle) for nozzle in NOZZLES):
                source_entry = machine_profiles.get(source_name)
                if source_entry is not None:
                    source_path, _ = source_entry
                    rels.append(Path("system") / vendor / source_path.relative_to(PROFILES_ROOT / vendor))
        if vendor == "TinManX1":
            rels.append(Path("system") / vendor / "filament")
        for rel in rels:
            source = app_support / rel
            target = backup / rel
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    return backup


def mirror_generated_profiles(target_root: Path) -> None:
    for vendor in sorted({family.vendor for family in FAMILIES}):
        source_index = PROFILES_ROOT / f"{vendor}.json"
        machine_profiles = indexed_profiles(vendor, "machine")
        target_index = target_root / f"{vendor}.json"
        target_index.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_index, target_index)
        for profile_type in ("machine", "process"):
            source_dir = PROFILES_ROOT / vendor / profile_type / "TinMan Codex"
            target_dir = target_root / vendor / profile_type / "TinMan Codex"
            if target_dir.exists():
                shutil.rmtree(target_dir)
            target_dir.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source_dir, target_dir)
        if vendor == "TinManX1":
            source_dir = PROFILES_ROOT / vendor / "filament"
            target_dir = target_root / vendor / "filament"
            target_dir.mkdir(parents=True, exist_ok=True)
            for source in source_dir.glob("*.json"):
                shutil.copy2(source, target_dir / source.name)
        for family in (item for item in FAMILIES if item.vendor == vendor):
            index = load_json(source_index)
            for source_name in dict.fromkeys(family.source_name(nozzle) for nozzle in NOZZLES):
                source_entry = machine_profiles.get(source_name)
                if source_entry is None:
                    continue
                source_path, _ = source_entry
                rel = source_path.relative_to(PROFILES_ROOT / vendor)
                (target_root / vendor / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_root / vendor / rel)
            for model_item in index.get("machine_model_list", []):
                if model_item.get("name") != family.model:
                    continue
                rel = Path(str(model_item["sub_path"]))
                (target_root / vendor / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(PROFILES_ROOT / vendor / rel, target_root / vendor / rel)


def rewrite_printer_compatibility(app_support: Path) -> int:
    changed = 0
    printers_dir = app_support / "printers"
    if not printers_dir.is_dir():
        return changed
    for path in sorted(printers_dir.glob("*.json")):
        data = load_json(path)
        dirty = False
        for record in data.values():
            if not isinstance(record, dict):
                continue
            compatible = record.get("compatible_machine")
            if isinstance(compatible, str):
                family = family_for_name(compatible)
                nozzle = nozzle_from_name(compatible) or "0.4"
                if family:
                    record["compatible_machine"] = family.canonical_name(nozzle)
                    dirty = True
            elif isinstance(compatible, list):
                rewritten = []
                for name in compatible:
                    family = family_for_name(str(name))
                    nozzle = nozzle_from_name(str(name)) or "0.4"
                    rewritten.append(family.canonical_name(nozzle) if family else name)
                if rewritten != compatible:
                    record["compatible_machine"] = rewritten
                    dirty = True
        if dirty:
            write_json(path, data)
            changed += 1
    return changed


def rewrite_live_config(app_support: Path) -> tuple[int, int]:
    conf_path = app_support / "OrcaSlicer.conf"
    conf = load_json(conf_path)
    addresses, connection_details = collect_live_connections(app_support, conf)
    conf["models"] = [
        {"model": family.model, "nozzle_diameter": ";".join(NOZZLES), "vendor": family.vendor}
        for family in FAMILIES
    ]

    states: dict[str, dict[str, Any]] = {}
    for state in conf.get("orca_presets", []):
        if not isinstance(state, dict):
            continue
        old_name = str(state.get("machine", ""))
        family = family_for_name(old_name)
        nozzle = nozzle_from_name(old_name)
        if not family or nozzle not in NOZZLES:
            continue
        updated = copy.deepcopy(state)
        updated["machine"] = family.canonical_name(nozzle)
        process = str(updated.get("process", ""))
        if f"@{updated['machine']}" not in process:
            updated["process"] = default_process_name(family, nozzle)
        states[updated["machine"]] = updated
    conf["orca_presets"] = [states[name] for name in sorted(states)]

    current = str((conf.get("presets") or {}).get("machine", ""))
    current_family = family_for_name(current) or next(family for family in FAMILIES if family.model == "Qidi X-Plus 4")
    current_nozzle = nozzle_from_name(current) or "0.6"
    conf.setdefault("presets", {})["machine"] = current_family.canonical_name(current_nozzle)

    # Orca persists nozzle-flow selections separately from machine presets and
    # gives those saved values precedence over default_nozzle_volume_type. Keep
    # both canonical and hidden inheritance-base entries aligned with the
    # actual TinMan hardware so an old Standard value cannot revive the Bambu
    # mismatch warning after a restart.
    nozzle_volume_types = conf.get("nozzle_volume_types")
    if not isinstance(nozzle_volume_types, dict):
        nozzle_volume_types = {}
        conf["nozzle_volume_types"] = nozzle_volume_types
    for family in FAMILIES:
        machine_profiles = indexed_profiles(family.vendor, "machine")
        for nozzle in NOZZLES:
            names = (family.canonical_name(nozzle), family.source_name(nozzle))
            for name in names:
                entry = machine_profiles.get(name)
                if entry is None:
                    continue
                _, machine_data = entry
                count = len(machine_data.get("nozzle_diameter") or []) or 1
                nozzle_volume_types[name] = ",".join(nozzle_flow_types(family, count))

    pack = conf.get("tinmanx1_profile_pack")
    if not isinstance(pack, dict):
        pack = {"legacy_value": pack} if pack not in (None, "") else {}
        conf["tinmanx1_profile_pack"] = pack
    pack["machine_contract_version"] = CONTRACT_VERSION
    pack["machine_contract_applied_at"] = int(time.time())

    ip_addresses = conf.get("ip_address")
    if not isinstance(ip_addresses, dict):
        ip_addresses = {}
        conf["ip_address"] = ip_addresses
    overlay = conf.get(CONNECTION_SECTION)
    if not isinstance(overlay, dict):
        overlay = {}
        conf[CONNECTION_SECTION] = overlay
    for family in FAMILIES:
        address = addresses.get(family.model)
        if not address:
            continue
        for nozzle in NOZZLES:
            ip_addresses[family.canonical_name(nozzle)] = address
        # Bambu devices remain serial-bound in local_machines. Their canonical
        # address aliases are useful, but third-party print-host settings are not.
        if family.vendor == "BBL":
            continue
        family_details = connection_details.get(family.model, {})
        family_details.setdefault("print_host", address)
        current_webui = family_details.get("print_host_webui", "")
        family_details["print_host_webui"] = default_webui_for_family(
            family, current_webui or address
        )
        for option, value in family_details.items():
            if option in CONNECTION_OPTIONS:
                overlay[f"{family.model}::{option}"] = value
    write_json(conf_path, conf)

    removed = 0
    for machine_dir in sorted((app_support / "user").glob("*/machine")):
        for path in machine_dir.iterdir():
            if path.is_file() and path.suffix in {".json", ".info"}:
                path.unlink()
                removed += 1
    printer_files = rewrite_printer_compatibility(app_support)
    return removed, printer_files


def apply_live(app_support: Path, app_profiles: Path, backup_root: Path) -> tuple[Path, int, int]:
    backup = backup_live_state(app_support, backup_root)
    mirror_generated_profiles(app_support / "system")
    if app_profiles.is_dir():
        mirror_generated_profiles(app_profiles)
    removed, printer_files = rewrite_live_config(app_support)
    return backup, removed, printer_files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply-live", action="store_true")
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--app-profiles", type=Path, default=DEFAULT_APP_PROFILES)
    parser.add_argument("--backup-root", type=Path, default=DEFAULT_BACKUP_ROOT)
    args = parser.parse_args()

    machines, processes = generate_repo_catalog()
    print(f"generated machine profiles: {machines}")
    print(f"generated canonical processes: {processes}")
    if args.apply_live:
        backup, removed, printer_files = apply_live(args.app_support, args.app_profiles, args.backup_root)
        print(f"backup: {backup}")
        print(f"legacy user machine sidecars removed: {removed}")
        print(f"physical-printer records updated: {printer_files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
