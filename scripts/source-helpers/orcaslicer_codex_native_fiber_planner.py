#!/usr/bin/env python3
"""Plan FibreSeek continuous-fiber paths from TinManX1 G-code.

This is TinManX1's native continuous-fiber planner. It reads the polymer
G-code that the slicer already generated, reconstructs layer geometry from
extrusion moves, and emits FibreSeek-style continuous-fiber command blocks
plus a JSON summary. The planner prefers already validated wall and infill
traces, then falls back to generated clipped paths when the model has no
usable polymer trace for a requested reinforcement family.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable, Sequence

try:
    from shapely.geometry import GeometryCollection, LineString, MultiLineString, MultiPoint, MultiPolygon, Point, Polygon
except Exception as exc:  # pragma: no cover - exercised on machines without shapely.
    raise SystemExit(
        "The native FibreSeek planner needs shapely. Install it with "
        "`python3 -m pip install shapely` or set ORCASLICER_CODEX_PYTHON to a Python that has it."
    ) from exc


PARAM_RE = re.compile(r"([A-Za-z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))")
CONFIG_RE = re.compile(r"^;\s*([A-Za-z0-9_]+)\s*=\s*(.*)$")
EPSILON = 1e-6
PATTERN_CODE_MAP = {
    "0": "solid",
    "1": "rhombic",
    "2": "isogrid",
    "3": "anisogrid",
    "4": "tetragrid",
}
PATTERN_NAMES = {"solid", "rhombic", "isogrid", "anisogrid", "tetragrid", "crosshatch", "grid"}
PATTERN_ANGLE_MAP = {
    "solid": [0.0, 90.0],
    "rhombic": [45.0, 135.0],
    "isogrid": [0.0, 60.0, 120.0],
    "anisogrid": [0.0, 45.0, 135.0],
    "tetragrid": [0.0, 45.0, 90.0, 135.0],
    "crosshatch": [0.0, 90.0],
    "grid": [0.0, 90.0],
}
PERIMETER_TRACE_ROLES = {"Inner wall"}
HOLE_TRACE_ROLES = {"Inner wall", "Outer wall"}
INFILL_TRACE_ROLES = {"Sparse infill", "Internal solid infill", "Internal Bridge", "Bottom surface"}
EXPLICIT_FIBER_INFILL_TRACE_ROLES = {
    "Fiber infill",
    "Fibre infill",
    "Continuous fiber infill",
    "Continuous fibre infill",
}
TRACE_KIND_BY_ROLE = {
    "Inner wall": "perimeter_trace",
    "Sparse infill": "sparse_infill_trace",
    "Internal solid infill": "solid_infill_trace",
    "Internal Bridge": "bridge_infill_trace",
    "Bottom surface": "solid_infill_trace",
    "Fiber infill": "fiber_infill_trace",
    "Fibre infill": "fiber_infill_trace",
    "Continuous fiber infill": "fiber_infill_trace",
    "Continuous fibre infill": "fiber_infill_trace",
}
ROUTE_PRIORITY = {
    "perimeter_trace": 0,
    "stitched_perimeter_trace": 0,
    "outer_perimeter_loop": 1,
    "hole_reinforcement_loop": 2,
    "hole_cluster_reinforcement_loop": 2,
    "hole_perimeter_loop": 3,
    "outer_perimeter_chord": 3,
    "hole_perimeter_chord": 4,
    "sparse_infill_trace": 10,
    "solid_infill_trace": 11,
    "bridge_infill_trace": 12,
    "fiber_infill_trace": 13,
    "infill_chord": 20,
}
INFILL_SOURCE_POLICIES = {"explicit", "generated-ribs", "plastic-traces"}


@dataclass
class ExtrusionPath:
    layer_index: int
    z: float
    role: str
    points: list[tuple[float, float]]

    @property
    def length(self) -> float:
        return polyline_length(self.points)


@dataclass
class LayerGeometry:
    index: int
    z: float = 0.0
    height: float = 0.0
    extrusion_paths: list[ExtrusionPath] = field(default_factory=list)


@dataclass
class ParsedGCode:
    source: Path
    lines: list[str]
    layers: list[LayerGeometry]
    config_comments: dict[str, str]


@dataclass
class PlannerConfig:
    cut_distance: float = 58.0
    restart_length: float = 55.0
    start_length: float = 15.0
    slow_length: float = 10.0
    fiber_diameter: float = 0.25
    fiber_linear_density: float = 102.0
    fiber_p_value: float = 0.041
    fiber_v_per_mm: float = 0.041
    fiber_width: float = 0.80
    min_radius: float = 12.0
    max_arc_segment_length: float = 3.0
    mechanical_min_route_length: float = 55.0
    min_route_length: float = 10.0
    perimeter_min_route_length: float = 55.0
    thin_feature_min_route_lengths: list[float] = field(default_factory=lambda: [5.0, 2.0])
    infill_spacing: float = 4.0
    infill_density_percent: float = 0.0
    perimeter_inset: float = 0.85
    infill_inset: float = 1.20
    travel_feedrate: float = 30000.0
    z_feedrate: float = 600.0
    fiber_feedrate: float = 1800.0
    fiber_slow_feedrate: float = 300.0
    fiber_finish_feedrate: float = 900.0
    fiber_cut_tail_feedrate: float = 180.0
    restart_feedrate: float = 1500.0
    priming_feedrate: float = 600.0
    tension_length: float = 0.0
    tension_feedrate: float = 0.0
    tension_release_fraction: float = 0.0
    feedrate_percent: float = 100.0
    correction_move_feedrate: float = 0.0
    correction_move_feedrate_percent: float = 0.0
    after_cut_plastic_extrusion_multiplier: float = 0.72
    generate_perimeters: bool = False
    generate_infill: bool = False
    infill_source_policy: str = "explicit"
    reinforcement_mode: str = "light"
    pattern: str = "solid"
    input_source: str = "gcode-comments"
    angles: list[float] = field(default_factory=list)
    layer_step: int = 1
    macro_layer_height: float = 0.2
    infill_trace_stride: int = 1
    fiber_seam_position: str = "source"
    fiber_seam_angle: float = 0.0
    perimeter_routes_per_layer: int = 4
    hole_reinforcement_routes_per_layer: int = 0
    hole_reinforcement_max_laps: int = 3
    hole_reinforcement_max_radius_factor: float = 2.3
    hole_reinforcement_alternate_regions: bool = True
    infill_routes_per_layer: int = 8
    max_routes_per_layer: int = 80
    routes_per_cut: int = 1
    fiber_start_layer: int = 0
    fiber_path_phase: int = 0
    layup_bands: list[dict] = field(default_factory=list)
    layup_band_name: str = ""
    layup_payload_warnings: list[str] = field(default_factory=list)
    fiber_tool_command: str = "T0 ; switch extruder type to:FIBER"
    plastic_tool_command: str = "T1 ; switch extruder type to:PLASTIC"
    cut_gcode: list[str] = field(default_factory=lambda: ["M2800", "M400", ";CUT DISTANCE 54.8"])
    plastic_nozzle_temperature: float = 260.0
    fiber_nozzle_temperature: float = 275.0
    plastic_standby_temperature: float = 150.0
    fiber_standby_temperature: float = 180.0
    bed_temperature: float = 80.0
    chamber_temperature: float = 0.0
    toolchange_z_lift: float = 5.0
    fiber_transition_fan_speed: int = 38
    fiber_laydown_fan_speed: int = 63
    active_tool_fan_speed: int = 255
    fiber_prime_enabled: bool = True
    fiber_prime_line_center_x: float = 152.5
    fiber_prime_line_y: float = 119.0
    fiber_prime_line_length: float = 90.0
    fiber_prime_line_height: float = 0.2
    fiber_prime_travel_z: float = 1.2
    fiber_prime_dwell_ms: int = 1000


MODE_ALIASES = {
    "0": "light",
    "1": "medium",
    "2": "heavy",
    "speedy": "light",
    "light": "light",
    "fiberreinforcementmode::light": "light",
    "reinforced": "medium",
    "medium": "medium",
    "fiberreinforcementmode::medium": "medium",
    "fortify": "heavy",
    "fortified": "heavy",
    "heavy": "heavy",
    "fiberreinforcementmode::heavy": "heavy",
}


@dataclass
class FiberRoute:
    layer_index: int
    z: float
    kind: str
    angle: float | None
    points: list[tuple[float, float]]
    source_role: str
    warnings: list[str] = field(default_factory=list)

    @property
    def length(self) -> float:
        return polyline_length(self.points)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--in-gcode", required=True, type=Path, help="Input TinManX1 polymer G-code.")
    parser.add_argument("--out", required=True, type=Path, help="Output G-code path.")
    parser.add_argument("--summary-out", type=Path, help="Optional JSON planner summary.")
    parser.add_argument(
        "--emit-mode",
        choices=("fiber-only", "append-after-layer"),
        default=os.environ.get("ORCASLICER_CODEX_NATIVE_FIBER_EMIT_MODE", "fiber-only"),
        help="Write only the fiber stream, or append fiber blocks after each polymer layer.",
    )
    parser.add_argument(
        "--angles",
        help="Comma-separated infill angles. Overrides the profile pattern mapping.",
    )
    parser.add_argument(
        "--fiber-reinforcement-mode",
        help="Live slicer reinforcement mode override: light, medium, or heavy.",
    )
    parser.add_argument(
        "--fiber-generate-perimeters",
        help="Live slicer perimeter reinforcement override: 1/0, true/false, yes/no, or on/off.",
    )
    parser.add_argument(
        "--fiber-generate-infill",
        help="Live slicer infill reinforcement override: 1/0, true/false, yes/no, or on/off.",
    )
    parser.add_argument(
        "--fiber-infill-pattern",
        help="Live slicer fiber infill pattern override.",
    )
    parser.add_argument(
        "--fiber-infill-source",
        choices=tuple(sorted(INFILL_SOURCE_POLICIES)),
        help=(
            "Source for continuous-fiber infill: explicit uses existing fiber "
            "traces, generated-ribs creates new clipped ribs, plastic-traces "
            "converts ordinary polymer infill paths."
        ),
    )
    parser.add_argument("--spacing", type=float, help="Fiber infill spacing in mm.")
    parser.add_argument("--density", type=float, help="Generated fiber infill density percentage.")
    parser.add_argument(
        "--fiber-seam-position",
        choices=("source", "nearest", "aligned", "rear", "random"),
        help="Closed-loop continuous-fiber seam/start placement.",
    )
    parser.add_argument("--fiber-seam-angle", type=float, help="Angle used by aligned fiber seam placement.")
    parser.add_argument("--layer-step", type=int, help="Plan every Nth layer.")
    parser.add_argument("--fiber-start-layer", type=int, help="First visible layer allowed to receive fiber.")
    parser.add_argument("--min-route-length", type=float, help="Minimum route length in mm.")
    parser.add_argument("--line-width", type=float, help="Fiber route line width in mm.")
    parser.add_argument("--perimeter-inset", type=float, help="Fiber perimeter inset in mm.")
    parser.add_argument("--infill-inset", type=float, help="Fiber infill inset in mm.")
    parser.add_argument("--fiber-print-speed", type=float, help="Normal fiber deposition speed in mm/s.")
    parser.add_argument("--fiber-start-speed", type=float, help="Initial fiber deposition speed in mm/s.")
    parser.add_argument(
        "--max-routes-per-layer",
        type=int,
        help="Safety cap for generated routes per layer.",
    )
    parser.add_argument(
        "--fiber-routes-per-cut",
        type=int,
        help="Number of same-layer fiber routes grouped into one cut/restart cycle.",
    )
    parser.add_argument(
        "--no-perimeters",
        action="store_true",
        help="Disable boundary-parallel straight perimeter reinforcement routes.",
    )
    parser.add_argument("--no-infill", action="store_true", help="Disable continuous-fiber infill routes.")
    return parser.parse_args()


def parse_params(line: str) -> dict[str, float]:
    code = line.split(";", 1)[0]
    return {key.upper(): float(value) for key, value in PARAM_RE.findall(code)}


def gcode_command(line: str) -> str:
    code = line.split(";", 1)[0].strip()
    if not code:
        return ""
    return code.split(None, 1)[0].upper()


def polyline_length(points: Sequence[tuple[float, float]]) -> float:
    if len(points) < 2:
        return 0.0
    return sum(distance(a, b) for a, b in zip(points, points[1:]))


def distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def fmt_float(value: float, places: int = 3) -> str:
    if places == 0:
        return str(int(round(value)))
    text = f"{value:.{places}f}"
    text = text.rstrip("0").rstrip(".")
    return text if text and text != "-0" else "0"


def fmt_axis(letter: str, value: float, places: int = 3) -> str:
    return f"{letter}{fmt_float(value, places)}"


def parse_gcode(path: Path) -> ParsedGCode:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    layers: list[LayerGeometry] = []
    config_comments: dict[str, str] = {}

    abs_xyz = True
    abs_e = True
    current_x: float | None = None
    current_y: float | None = None
    current_z = 0.0
    current_e = 0.0
    current_role = "unknown"
    active_points: list[tuple[float, float]] = []
    active_role = "unknown"
    active_layer_index = -1

    def current_layer() -> LayerGeometry | None:
        return layers[-1] if layers else None

    def flush_active() -> None:
        nonlocal active_points, active_role, active_layer_index
        if len(active_points) >= 2 and active_layer_index >= 0:
            layer = layers[active_layer_index]
            path_obj = ExtrusionPath(
                layer_index=layer.index,
                z=layer.z,
                role=active_role,
                points=active_points,
            )
            if path_obj.length > 0.05:
                layer.extrusion_paths.append(path_obj)
        active_points = []
        active_role = current_role
        active_layer_index = layers[-1].index if layers else -1

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        config_match = CONFIG_RE.match(line)
        if config_match:
            config_comments[config_match.group(1)] = config_match.group(2)

        if line.startswith(";LAYER_CHANGE"):
            flush_active()
            layers.append(LayerGeometry(index=len(layers), z=current_z))
            active_layer_index = layers[-1].index
            continue

        if line.startswith(";Z:"):
            try:
                current_z = float(line.split(":", 1)[1].strip())
                layer = current_layer()
                if layer is not None:
                    layer.z = current_z
            except ValueError:
                pass
            continue

        if line.startswith(";HEIGHT:"):
            try:
                layer = current_layer()
                if layer is not None:
                    layer.height = float(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            continue

        if line.startswith(";TYPE:"):
            flush_active()
            current_role = line.split(":", 1)[1].strip()
            active_role = current_role
            active_layer_index = layers[-1].index if layers else -1
            continue

        command = gcode_command(line)
        if command == "G90":
            abs_xyz = True
            flush_active()
            continue
        if command == "G91":
            abs_xyz = False
            flush_active()
            continue
        if command == "M82":
            abs_e = True
            flush_active()
            continue
        if command == "M83":
            abs_e = False
            flush_active()
            continue
        if command == "G92":
            params = parse_params(line)
            if "E" in params:
                current_e = params["E"]
            flush_active()
            continue

        if command not in {"G0", "G00", "G1", "G01"}:
            continue

        params = parse_params(line)
        target_x = current_x
        target_y = current_y
        target_z = current_z
        if "X" in params:
            target_x = params["X"] if abs_xyz or current_x is None else current_x + params["X"]
        if "Y" in params:
            target_y = params["Y"] if abs_xyz or current_y is None else current_y + params["Y"]
        if "Z" in params:
            target_z = params["Z"] if abs_xyz else current_z + params["Z"]

        e_delta = 0.0
        if "E" in params:
            if abs_e:
                e_delta = params["E"] - current_e
                current_e = params["E"]
            else:
                e_delta = params["E"]
                current_e += params["E"]

        xy_ready = current_x is not None and current_y is not None and target_x is not None and target_y is not None
        xy_distance = distance((current_x, current_y), (target_x, target_y)) if xy_ready else 0.0
        layer = current_layer()
        is_extrusion = command in {"G1", "G01"} and e_delta > EPSILON and xy_distance > 0.01

        if is_extrusion and layer is not None and xy_ready:
            if active_layer_index != layer.index or active_role != current_role:
                flush_active()
                active_role = current_role
                active_layer_index = layer.index
            start = (float(current_x), float(current_y))
            end = (float(target_x), float(target_y))
            if not active_points:
                active_points = [start]
            elif distance(active_points[-1], start) > 0.05:
                flush_active()
                active_role = current_role
                active_layer_index = layer.index
                active_points = [start]
            active_points.append(end)
        else:
            flush_active()

        if target_x is not None:
            current_x = target_x
        if target_y is not None:
            current_y = target_y
        current_z = target_z

    flush_active()
    return ParsedGCode(source=path, lines=lines, layers=layers, config_comments=config_comments)


def parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    text = value.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def parse_reinforcement_mode(value: str | None, default: str = "light") -> str:
    if not value:
        return default
    text = value.strip().lower()
    if text in MODE_ALIASES:
        return MODE_ALIASES[text]
    numeric_match = re.fullmatch(r"[-+]?\d+(?:\.0+)?", text)
    if numeric_match:
        return MODE_ALIASES.get(str(int(float(text))), default)
    return default


def parse_infill_source_policy(value: str | None, default: str = "explicit") -> str:
    if not value:
        return default
    text = value.strip().lower().replace("_", "-").replace(" ", "-")
    aliases = {
        "explicit-only": "explicit",
        "fiber-only": "explicit",
        "fibre-only": "explicit",
        "generated": "generated-ribs",
        "generated-rib": "generated-ribs",
        "ribs": "generated-ribs",
        "generated-ribs": "generated-ribs",
        "plastic": "plastic-traces",
        "plastic-trace": "plastic-traces",
        "plastic-traces": "plastic-traces",
        "polymer": "plastic-traces",
        "polymer-trace": "plastic-traces",
        "polymer-traces": "plastic-traces",
    }
    return aliases.get(text, default)


def parse_first_float(value: str | None, default: float, prefer_last_nonzero: bool = False) -> float:
    if value is None:
        return default
    matches = [float(item) for item in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)]
    if not matches:
        return default
    if prefer_last_nonzero:
        for item in reversed(matches):
            if abs(item) > EPSILON:
                return item
        return default
    return matches[0]


def parse_float_values(value: str | None) -> list[float]:
    if value is None:
        return []
    return [float(item) for item in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)]


def first_positive_value(values: Sequence[float], default: float) -> float:
    for value in values:
        if value > EPSILON:
            return value
    return default


def last_positive_value(values: Sequence[float], default: float) -> float:
    for value in reversed(values):
        if value > EPSILON:
            return value
    return default


def last_value(values: Sequence[float], default: float) -> float:
    return values[-1] if values else default


def parse_first_positive_float(value: str | None, default: float) -> float:
    parsed = parse_first_float(value, default)
    return parsed if parsed > EPSILON else default


def parse_first_positive_int(value: str | None, default: int) -> int:
    parsed = int(round(parse_first_float(value, float(default))))
    return parsed if parsed > 0 else default


def parse_first_nonnegative_int(value: str | None, default: int) -> int:
    parsed = int(round(parse_first_float(value, float(default))))
    return parsed if parsed >= 0 else default


def speed_mm_s_to_feedrate(value: str | None, default_feedrate: float) -> float:
    speed = parse_first_float(value, default_feedrate / 60.0)
    return speed * 60.0 if speed > EPSILON else default_feedrate


def cut_gcode_from_value(value: str | None, cut_distance: float) -> list[str]:
    if not value:
        return ["M2800", "M400", f";CUT DISTANCE {fmt_float(max(cut_distance - 3.2, 0.0), 1)}"]
    expanded = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    commands = [line.strip() for line in expanded.splitlines() if line.strip()]
    return commands or ["M2800", "M400", f";CUT DISTANCE {fmt_float(max(cut_distance - 3.2, 0.0), 1)}"]


def cut_distance_from_gcode(commands: Sequence[str]) -> float | None:
    for command in commands:
        match = re.search(r"\bCUT\s+DISTANCE\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+))", command, flags=re.IGNORECASE)
        if not match:
            continue
        value = float(match.group(1))
        if value > EPSILON:
            return value
    return None


def pattern_from_comments(comments: dict[str, str], default: str) -> str:
    for key in ("fiber_infill_pattern", "fiber_infill_pattern_guess", "fiber_infill_pattern_code"):
        value = comments.get(key)
        if not value:
            continue
        text = value.strip().lower()
        if text in PATTERN_CODE_MAP:
            return PATTERN_CODE_MAP[text]
        if text in PATTERN_NAMES:
            return text
    return default


def normalized_pattern(value: object, default: str) -> str:
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in PATTERN_CODE_MAP:
        return PATTERN_CODE_MAP[text]
    if text in PATTERN_NAMES:
        return text
    return default


def angles_for_pattern(pattern: str, explicit: str | None) -> list[float]:
    if explicit:
        return [float(item.strip()) for item in explicit.split(",") if item.strip()]
    normalized = pattern.strip().lower()
    if normalized in PATTERN_ANGLE_MAP:
        return list(PATTERN_ANGLE_MAP[normalized])
    if normalized in {"triangular", "tetrahedral"}:
        return list(PATTERN_ANGLE_MAP["isogrid"])
    if normalized in {"anisotropic", "load", "load-aligned"}:
        return [0.0]
    return list(PATTERN_ANGLE_MAP["solid"])


def spacing_from_density(fiber_width: float, density_percent: float, current_spacing: float) -> float:
    if density_percent <= EPSILON:
        return current_spacing
    return max(fiber_width * 100.0 / density_percent, fiber_width)


def normalized_fiber_seam_position(value: object, default: str = "source") -> str:
    if value is None:
        return default
    text = str(value).strip().lower().replace("_", "-")
    aliases = {
        "": default,
        "source": "source",
        "native": "source",
        "default": "source",
        "nearest": "nearest",
        "nearest-travel": "nearest",
        "aligned": "aligned",
        "angle": "aligned",
        "rear": "rear",
        "back": "rear",
        "aligned-back": "rear",
        "random": "random",
        "scatter": "random",
    }
    return aliases.get(text, default)


def parse_json_like_payload(value: str | None) -> tuple[dict, list[str]]:
    if not value or not value.strip():
        return {}, []
    text = value.strip()
    if text in {"{}", "null", "None"}:
        return {}, []
    warnings: list[str] = []
    candidates = [text]
    if "\\\"" in text or "\\n" in text:
        candidates.append(text.replace("\\\"", '"').replace("\\n", "\n"))
    if len(text) >= 2 and text[0] == text[-1] == '"':
        try:
            decoded = json.loads(text)
            if isinstance(decoded, dict):
                return decoded, warnings
            if isinstance(decoded, str):
                candidates.append(decoded)
        except Exception:
            pass
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception as exc:
            warnings.append(f"fiber_reinforcement_payload_parse_error:{exc.__class__.__name__}")
            continue
        if isinstance(parsed, dict):
            return parsed, warnings
        warnings.append("fiber_reinforcement_payload_not_object")
    return {}, warnings[:1] or ["fiber_reinforcement_payload_parse_error"]


def payload_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled", "enable"}:
        return True
    if text in {"0", "false", "no", "off", "disabled", "disable"}:
        return False
    return default


def payload_float(value: object, default: float) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def payload_positive_float(value: object, default: float) -> float:
    parsed = payload_float(value, default)
    return parsed if parsed > EPSILON else default


def payload_int(value: object, default: int) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def payload_positive_int(value: object, default: int) -> int:
    parsed = payload_int(value, default)
    return parsed if parsed > 0 else default


def payload_angles(value: object) -> list[float] | None:
    if value is None:
        return None
    if isinstance(value, str):
        pieces = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        pieces = list(value)
    else:
        pieces = [value]
    angles: list[float] = []
    for item in pieces:
        try:
            angles.append(float(item))
        except (TypeError, ValueError):
            continue
    return angles or None


def payload_value(mapping: dict, *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def safe_warning_name(value: object) -> str:
    text = str(value).strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text[:48] or "unnamed"


def apply_mode_defaults(cfg: PlannerConfig, fiber_enabled: bool) -> None:
    if cfg.reinforcement_mode == "light":
        cfg.infill_spacing = 7.5
        cfg.layer_step = 3
        cfg.macro_layer_height = 0.6
        cfg.infill_trace_stride = 3
        cfg.perimeter_routes_per_layer = 1
        cfg.hole_reinforcement_routes_per_layer = 1
        cfg.infill_routes_per_layer = 2
        cfg.max_routes_per_layer = 32
        if fiber_enabled and not cfg.generate_perimeters and not cfg.generate_infill:
            cfg.generate_perimeters = True
    elif cfg.reinforcement_mode == "medium":
        cfg.infill_spacing = 4.5
        cfg.layer_step = 2
        cfg.macro_layer_height = 0.4
        cfg.infill_trace_stride = 2
        cfg.perimeter_routes_per_layer = 2
        cfg.hole_reinforcement_routes_per_layer = 3
        cfg.infill_routes_per_layer = 4
        cfg.max_routes_per_layer = 80
        if fiber_enabled and not cfg.generate_perimeters and not cfg.generate_infill:
            cfg.generate_perimeters = True
            cfg.generate_infill = True
    elif cfg.reinforcement_mode == "heavy":
        cfg.infill_spacing = 2.8
        cfg.layer_step = 1
        cfg.macro_layer_height = 0.2
        cfg.infill_trace_stride = 1
        cfg.perimeter_routes_per_layer = 4
        cfg.hole_reinforcement_routes_per_layer = 6
        cfg.infill_routes_per_layer = 8
        cfg.max_routes_per_layer = 180
        if fiber_enabled and not cfg.generate_perimeters and not cfg.generate_infill:
            cfg.generate_perimeters = True
            cfg.generate_infill = True


def normalized_layup_bands(payload: dict) -> list[dict]:
    raw = payload_value(payload, "z_bands", "bands", "layup_bands", "layup")
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw_bands = [raw]
    elif isinstance(raw, (list, tuple)):
        raw_bands = list(raw)
    else:
        return []
    return [band for band in raw_bands if isinstance(band, dict)]


def apply_layup_payload_overrides(cfg: PlannerConfig, payload: dict, explicit_angles: str | None = None) -> None:
    if not payload:
        return
    if payload_value(payload, "pattern", "infill_pattern") is not None:
        cfg.pattern = normalized_pattern(payload_value(payload, "pattern", "infill_pattern"), cfg.pattern)
        cfg.angles = angles_for_pattern(cfg.pattern, explicit_angles)
    angles = payload_angles(payload_value(payload, "angles", "angle_list", "fiber_angles"))
    if angles:
        cfg.angles = angles
    if payload_value(payload, "perimeters", "generate_perimeters", "fiber_perimeters") is not None:
        cfg.generate_perimeters = payload_bool(
            payload_value(payload, "perimeters", "generate_perimeters", "fiber_perimeters"),
            cfg.generate_perimeters,
        )
    if payload_value(payload, "infill", "generate_infill", "fiber_infill") is not None:
        cfg.generate_infill = payload_bool(payload_value(payload, "infill", "generate_infill", "fiber_infill"), cfg.generate_infill)
    cfg.infill_spacing = payload_positive_float(payload_value(payload, "spacing", "infill_spacing"), cfg.infill_spacing)
    cfg.infill_density_percent = payload_float(payload_value(payload, "density", "infill_density"), cfg.infill_density_percent)
    if cfg.infill_density_percent > EPSILON:
        cfg.infill_density_percent = min(max(cfg.infill_density_percent, 0.0), 100.0)
        cfg.infill_spacing = spacing_from_density(cfg.fiber_width, cfg.infill_density_percent, cfg.infill_spacing)
    cfg.fiber_seam_position = normalized_fiber_seam_position(
        payload_value(payload, "seam_position", "fiber_seam_position", "seam"),
        cfg.fiber_seam_position,
    )
    cfg.fiber_seam_angle = payload_float(payload_value(payload, "seam_angle", "fiber_seam_angle"), cfg.fiber_seam_angle)
    cfg.layer_step = payload_positive_int(payload_value(payload, "layer_step", "every_n_layers"), cfg.layer_step)
    cfg.macro_layer_height = payload_float(payload_value(payload, "macro_layer_height", "z_spacing"), cfg.macro_layer_height)
    cfg.max_routes_per_layer = payload_positive_int(payload_value(payload, "max_routes_per_layer"), cfg.max_routes_per_layer)
    cfg.perimeter_routes_per_layer = payload_positive_int(payload_value(payload, "perimeter_routes_per_layer"), cfg.perimeter_routes_per_layer)
    cfg.hole_reinforcement_routes_per_layer = payload_positive_int(
        payload_value(payload, "hole_routes_per_layer", "hole_reinforcement_routes_per_layer"),
        cfg.hole_reinforcement_routes_per_layer,
    )
    cfg.infill_routes_per_layer = payload_positive_int(payload_value(payload, "infill_routes_per_layer"), cfg.infill_routes_per_layer)


def apply_fiber_prime_payload_overrides(cfg: PlannerConfig, payload: dict) -> None:
    raw_prime = payload_value(payload, "fiber_prime", "prime_line", "prime")
    if raw_prime is None:
        return
    if isinstance(raw_prime, bool):
        cfg.fiber_prime_enabled = raw_prime
        return
    if not isinstance(raw_prime, dict):
        cfg.fiber_prime_enabled = payload_bool(raw_prime, cfg.fiber_prime_enabled)
        return

    cfg.fiber_prime_enabled = payload_bool(payload_value(raw_prime, "enabled"), cfg.fiber_prime_enabled)
    cfg.fiber_prime_line_center_x = payload_positive_float(
        payload_value(raw_prime, "center_x", "x", "line_center_x"),
        cfg.fiber_prime_line_center_x,
    )
    cfg.fiber_prime_line_y = payload_positive_float(
        payload_value(raw_prime, "y", "line_y", "center_y"),
        cfg.fiber_prime_line_y,
    )
    cfg.fiber_prime_line_length = payload_positive_float(
        payload_value(raw_prime, "length", "line_length"),
        cfg.fiber_prime_line_length,
    )
    cfg.fiber_prime_line_height = payload_positive_float(
        payload_value(raw_prime, "height", "z", "line_height"),
        cfg.fiber_prime_line_height,
    )
    cfg.fiber_prime_travel_z = payload_positive_float(
        payload_value(raw_prime, "travel_z", "safe_z"),
        cfg.fiber_prime_travel_z,
    )
    cfg.fiber_prime_dwell_ms = payload_positive_int(
        payload_value(raw_prime, "dwell_ms", "dwell"),
        cfg.fiber_prime_dwell_ms,
    )


def layer_matches_layup_band(layer: LayerGeometry, band: dict) -> bool:
    visible_layer = layer.index + 1
    start_layer = payload_int(payload_value(band, "from_layer", "start_layer", "min_layer"), 1)
    end_layer = payload_int(payload_value(band, "to_layer", "end_layer", "max_layer"), 0)
    if visible_layer < start_layer:
        return False
    if end_layer > 0 and visible_layer > end_layer:
        return False
    from_z = payload_value(band, "from_z", "min_z", "start_z")
    to_z = payload_value(band, "to_z", "max_z", "end_z")
    if from_z is not None and layer.z + EPSILON < payload_float(from_z, layer.z):
        return False
    if to_z is not None and layer.z - EPSILON > payload_float(to_z, layer.z):
        return False
    return True


def layup_band_for_layer(layer: LayerGeometry, cfg: PlannerConfig) -> dict | None:
    best: tuple[int, int, dict] | None = None
    for order, band in enumerate(cfg.layup_bands):
        if not layer_matches_layup_band(layer, band):
            continue
        priority = payload_int(payload_value(band, "priority"), 0)
        candidate = (priority, order, band)
        if best is None or candidate[:2] >= best[:2]:
            best = candidate
    return best[2] if best is not None else None


def config_for_layup_band(layer: LayerGeometry, cfg: PlannerConfig, explicit_angles: str | None = None) -> tuple[PlannerConfig, bool]:
    band = layup_band_for_layer(layer, cfg)
    if band is None:
        return cfg, True
    enabled = payload_bool(payload_value(band, "enabled", "fiber_enabled"), True)
    route_cfg = replace(cfg)
    route_cfg.layup_band_name = str(payload_value(band, "name", "label") or "")
    mode = payload_value(band, "mode", "reinforcement_mode")
    if mode is not None:
        route_cfg.reinforcement_mode = parse_reinforcement_mode(str(mode), route_cfg.reinforcement_mode)
        apply_mode_defaults(route_cfg, enabled)
    apply_layup_payload_overrides(route_cfg, band, explicit_angles)
    return route_cfg, enabled


def planner_config(parsed: ParsedGCode, args: argparse.Namespace) -> PlannerConfig:
    comments = parsed.config_comments
    cfg = PlannerConfig()
    raw_reinforcement_mode = comments.get("fiber_reinforcement_mode") or ""
    print_settings_id = comments.get("print_settings_id") or ""
    legacy_rocket_compare_overrides = (
        "rocket compare" in print_settings_id.lower()
        or raw_reinforcement_mode.strip().lower() in {"speedy", "reinforced", "fortify"}
    )
    cfg.reinforcement_mode = parse_reinforcement_mode(comments.get("fiber_reinforcement_mode"), cfg.reinforcement_mode)
    if args.fiber_reinforcement_mode:
        cfg.reinforcement_mode = parse_reinforcement_mode(args.fiber_reinforcement_mode, cfg.reinforcement_mode)
        cfg.input_source = "live-slicer-config"
    cfg.cut_distance = parse_first_positive_float(comments.get("fiber_cut_distance"), cfg.cut_distance)
    cfg.restart_length = parse_first_positive_float(comments.get("fiber_restart_length"), cfg.restart_length)
    cfg.start_length = parse_first_positive_float(comments.get("fiber_start_length"), cfg.start_length)
    cfg.slow_length = parse_first_positive_float(comments.get("fiber_slow_length"), cfg.slow_length)
    cfg.fiber_diameter = parse_first_float(comments.get("fiber_diameter"), cfg.fiber_diameter, prefer_last_nonzero=True)
    cfg.fiber_linear_density = parse_first_float(comments.get("fiber_linear_density"), cfg.fiber_linear_density, prefer_last_nonzero=True)
    cfg.fiber_width = parse_first_positive_float(comments.get("fiber_line_width"), cfg.fiber_width)
    cfg.fiber_p_value = round(math.pi * (cfg.fiber_diameter / 2.0) ** 2 * 0.835, 5)
    cfg.fiber_v_per_mm = cfg.fiber_p_value
    profile_min_radius = parse_first_positive_float(comments.get("fiber_min_radius"), cfg.min_radius)
    cfg.min_radius = max(profile_min_radius, cfg.min_radius)
    cfg.mechanical_min_route_length = parse_first_positive_float(
        comments.get("fiber_mechanical_min_route_length") or comments.get("fiber_hardware_min_route_length"),
        cfg.mechanical_min_route_length,
    )
    max_arc_segment_length = parse_first_positive_float(comments.get("fiber_max_arc_segment_length"), cfg.max_arc_segment_length)
    if not (legacy_rocket_compare_overrides and abs(max_arc_segment_length - 1.0) <= EPSILON):
        cfg.max_arc_segment_length = max_arc_segment_length
    cfg.min_route_length = parse_first_positive_float(comments.get("fiber_min_route_length"), cfg.min_route_length)
    cfg.perimeter_min_route_length = parse_first_positive_float(
        comments.get("fiber_minimum_perimeter_length") or comments.get("fiber_perimeter_min_route_length"),
        cfg.perimeter_min_route_length,
    )
    cfg.perimeter_inset = parse_first_positive_float(comments.get("fiber_perimeter_inset"), cfg.perimeter_inset)
    cfg.infill_inset = parse_first_positive_float(comments.get("fiber_infill_inset"), cfg.infill_inset)
    cfg.fiber_feedrate = speed_mm_s_to_feedrate(
        comments.get("fiber_normal_max_speed") or comments.get("fiber_print_speed"),
        cfg.fiber_feedrate,
    )
    cfg.fiber_slow_feedrate = speed_mm_s_to_feedrate(
        comments.get("fiber_start_max_speed") or comments.get("fiber_start_speed"),
        cfg.fiber_slow_feedrate,
    )
    cfg.fiber_finish_feedrate = speed_mm_s_to_feedrate(comments.get("fiber_finish_max_speed"), cfg.fiber_finish_feedrate)
    cfg.fiber_cut_tail_feedrate = speed_mm_s_to_feedrate(
        comments.get("fiber_start_min_speed")
        or comments.get("fiber_start_min_limit_speed")
        or comments.get("fiber_finish_min_limit_speed"),
        cfg.fiber_cut_tail_feedrate,
    )
    cfg.tension_length = parse_first_float(comments.get("fiber_tension_length"), cfg.tension_length)
    cfg.tension_feedrate = parse_first_float(comments.get("fiber_tension_feedrate"), cfg.tension_feedrate)
    cfg.tension_release_fraction = parse_first_float(
        comments.get("fiber_tension_release_fraction"),
        cfg.tension_release_fraction,
    )
    cfg.feedrate_percent = parse_first_positive_float(comments.get("fiber_feedrate_percent"), cfg.feedrate_percent)
    cfg.fiber_v_per_mm = cfg.fiber_p_value * (cfg.feedrate_percent / 100.0)
    cfg.correction_move_feedrate = speed_mm_s_to_feedrate(
        comments.get("fiber_correction_move_speed"),
        cfg.correction_move_feedrate,
    ) if parse_bool(comments.get("fiber_override_correction_speed"), False) else 0.0
    cfg.correction_move_feedrate_percent = parse_first_float(
        comments.get("fiber_correction_move_feedrate_percent"),
        cfg.correction_move_feedrate_percent,
    )
    after_cut_plastic_extrusion_multiplier = parse_first_positive_float(
        comments.get("fiber_after_cut_plastic_extrusion_multiplier"),
        cfg.after_cut_plastic_extrusion_multiplier,
    )
    if not (legacy_rocket_compare_overrides and abs(after_cut_plastic_extrusion_multiplier - 1.0) <= EPSILON):
        cfg.after_cut_plastic_extrusion_multiplier = after_cut_plastic_extrusion_multiplier
    spacing_override = parse_first_float(comments.get("fiber_infill_spacing"), 0.0)
    density_override = parse_first_float(comments.get("fiber_infill_density"), 0.0)
    angle_override = args.angles or comments.get("fiber_infill_angles") or comments.get("fiber_angles")
    cfg.fiber_seam_position = normalized_fiber_seam_position(
        comments.get("fiber_seam_position") or comments.get("fiber_seam_mode"),
        cfg.fiber_seam_position,
    )
    cfg.fiber_seam_angle = parse_first_float(comments.get("fiber_seam_angle"), cfg.fiber_seam_angle)
    layer_step_override = parse_first_positive_int(comments.get("fiber_layer_step"), 0)
    cfg.fiber_start_layer = parse_first_nonnegative_int(comments.get("fiber_start_layer"), cfg.fiber_start_layer)
    macro_layer_height_override = parse_first_float(comments.get("fiber_macro_layer_height"), 0.0)
    max_routes_override = parse_first_positive_int(comments.get("fiber_max_routes_per_layer"), 0)
    routes_per_cut_override = parse_first_positive_int(comments.get("fiber_routes_per_cut"), 0)
    cfg.pattern = pattern_from_comments(comments, cfg.pattern)
    if args.fiber_infill_pattern:
        pattern_override = args.fiber_infill_pattern.strip().lower()
        if pattern_override in PATTERN_CODE_MAP:
            cfg.pattern = PATTERN_CODE_MAP[pattern_override]
        elif pattern_override in PATTERN_NAMES:
            cfg.pattern = pattern_override
        cfg.input_source = "live-slicer-config"
    cfg.generate_perimeters = parse_bool(comments.get("fiber_generate_perimeters"), cfg.generate_perimeters)
    cfg.generate_infill = parse_bool(comments.get("fiber_generate_infill"), cfg.generate_infill)
    cfg.infill_source_policy = parse_infill_source_policy(
        comments.get("fiber_infill_source_policy") or comments.get("fiber_infill_source"),
        cfg.infill_source_policy,
    )
    cfg.cut_gcode = cut_gcode_from_value(comments.get("fiber_cut_gcode"), cfg.cut_distance)
    macro_cut_distance = cut_distance_from_gcode(cfg.cut_gcode)
    if macro_cut_distance is not None:
        cfg.cut_distance = macro_cut_distance
    cfg.angles = angles_for_pattern(cfg.pattern, angle_override)

    nozzle_temperatures = parse_float_values(comments.get("nozzle_temperature"))
    initial_nozzle_temperatures = parse_float_values(comments.get("nozzle_temperature_initial_layer"))
    if len(nozzle_temperatures) >= 2:
        cfg.plastic_nozzle_temperature = first_positive_value([nozzle_temperatures[0]], cfg.plastic_nozzle_temperature)
        cfg.fiber_nozzle_temperature = first_positive_value([nozzle_temperatures[1]], cfg.fiber_nozzle_temperature)
    elif nozzle_temperatures:
        cfg.plastic_nozzle_temperature = first_positive_value(nozzle_temperatures, cfg.plastic_nozzle_temperature)
    if len(initial_nozzle_temperatures) >= 2:
        cfg.plastic_nozzle_temperature = first_positive_value([initial_nozzle_temperatures[0]], cfg.plastic_nozzle_temperature)
        cfg.fiber_nozzle_temperature = first_positive_value([initial_nozzle_temperatures[1]], cfg.fiber_nozzle_temperature)

    standby_temperatures = parse_float_values(comments.get("fiber_nozzle_temperature_standby"))
    if len(standby_temperatures) >= 2:
        cfg.plastic_standby_temperature = first_positive_value([standby_temperatures[0]], cfg.plastic_standby_temperature)
        cfg.fiber_standby_temperature = first_positive_value([standby_temperatures[1]], cfg.fiber_standby_temperature)
    elif standby_temperatures:
        cfg.fiber_standby_temperature = first_positive_value(standby_temperatures, cfg.fiber_standby_temperature)

    bed_values = (
        parse_float_values(comments.get("hot_plate_temp_initial_layer"))
        or parse_float_values(comments.get("hot_plate_temp"))
        or parse_float_values(comments.get("first_layer_bed_temperature"))
    )
    cfg.bed_temperature = last_positive_value(bed_values, cfg.bed_temperature)
    chamber_values = parse_float_values(comments.get("chamber_temperature"))
    cfg.chamber_temperature = last_value(chamber_values, cfg.chamber_temperature)

    fiber_enabled = parse_bool(comments.get("fiber_enabled"), False)
    apply_mode_defaults(cfg, fiber_enabled)

    if spacing_override > EPSILON:
        cfg.infill_spacing = max(spacing_override, cfg.fiber_width)
    if density_override > EPSILON:
        cfg.infill_density_percent = min(max(density_override, 0.0), 100.0)
        cfg.infill_spacing = spacing_from_density(cfg.fiber_width, cfg.infill_density_percent, cfg.infill_spacing)
    if macro_layer_height_override > EPSILON:
        cfg.macro_layer_height = macro_layer_height_override
    if layer_step_override > 0:
        cfg.layer_step = layer_step_override
        cfg.macro_layer_height = 0.0
    if max_routes_override > 0:
        cfg.max_routes_per_layer = max_routes_override
    if routes_per_cut_override > 0:
        cfg.routes_per_cut = routes_per_cut_override

    payload, payload_warnings = parse_json_like_payload(comments.get("fiber_reinforcement_payload"))
    cfg.layup_payload_warnings = payload_warnings
    cfg.layup_bands = normalized_layup_bands(payload)
    cfg.fiber_prime_line_height = parse_first_positive_float(
        comments.get("fiber_priming_line_height"),
        cfg.fiber_prime_line_height,
    )
    apply_layup_payload_overrides(cfg, payload, angle_override)
    apply_fiber_prime_payload_overrides(cfg, payload)
    if args.fiber_infill_pattern:
        cfg.pattern = normalized_pattern(args.fiber_infill_pattern, cfg.pattern)
        cfg.angles = angles_for_pattern(cfg.pattern, angle_override)
        cfg.input_source = "live-slicer-config"

    if args.fiber_generate_perimeters is not None:
        cfg.generate_perimeters = parse_bool(args.fiber_generate_perimeters, cfg.generate_perimeters)
        cfg.input_source = "live-slicer-config"
    if args.fiber_generate_infill is not None:
        cfg.generate_infill = parse_bool(args.fiber_generate_infill, cfg.generate_infill)
        cfg.input_source = "live-slicer-config"
    if args.fiber_infill_source is not None:
        cfg.infill_source_policy = args.fiber_infill_source
        cfg.input_source = "live-slicer-config"

    if args.line_width is not None:
        cfg.fiber_width = max(args.line_width, 0.01)
        cfg.infill_spacing = max(cfg.infill_spacing, cfg.fiber_width)
    if args.spacing is not None:
        cfg.infill_spacing = max(args.spacing, cfg.fiber_width)
    if getattr(args, "density", None) is not None:
        cfg.infill_density_percent = min(max(args.density, 0.0), 100.0)
        cfg.infill_spacing = spacing_from_density(cfg.fiber_width, cfg.infill_density_percent, cfg.infill_spacing)
    if getattr(args, "fiber_seam_position", None) is not None:
        cfg.fiber_seam_position = normalized_fiber_seam_position(args.fiber_seam_position, cfg.fiber_seam_position)
        cfg.input_source = "live-slicer-config"
    if getattr(args, "fiber_seam_angle", None) is not None:
        cfg.fiber_seam_angle = args.fiber_seam_angle
        cfg.input_source = "live-slicer-config"
    if args.layer_step is not None:
        cfg.layer_step = max(args.layer_step, 1)
        cfg.macro_layer_height = 0.0
    if args.fiber_start_layer is not None:
        cfg.fiber_start_layer = max(args.fiber_start_layer, 0)
        cfg.input_source = "live-slicer-config"
    if args.min_route_length is not None:
        cfg.min_route_length = max(args.min_route_length, 0.1)
    if args.perimeter_inset is not None:
        cfg.perimeter_inset = max(args.perimeter_inset, 0.0)
    if args.infill_inset is not None:
        cfg.infill_inset = max(args.infill_inset, 0.0)
    if args.fiber_print_speed is not None and args.fiber_print_speed > EPSILON:
        cfg.fiber_feedrate = args.fiber_print_speed * 60.0
    if args.fiber_start_speed is not None and args.fiber_start_speed > EPSILON:
        cfg.fiber_slow_feedrate = args.fiber_start_speed * 60.0
    if args.max_routes_per_layer is not None:
        cfg.max_routes_per_layer = max(args.max_routes_per_layer, 1)
    if args.fiber_routes_per_cut is not None:
        cfg.routes_per_cut = max(args.fiber_routes_per_cut, 1)
    if args.no_perimeters:
        cfg.generate_perimeters = False
    if args.no_infill:
        cfg.generate_infill = False

    return cfg


def closed_outer_polygons(layer: LayerGeometry) -> list[Polygon]:
    contours: list[Polygon] = []
    for extrusion_path in layer.extrusion_paths:
        if extrusion_path.role != "Outer wall" or len(extrusion_path.points) < 4:
            continue
        points = list(extrusion_path.points)
        if distance(points[0], points[-1]) > 1.2:
            continue
        points[-1] = points[0]
        try:
            polygon = Polygon(points)
        except Exception:
            continue
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if polygon.is_empty or polygon.area < 1.0:
            continue
        if isinstance(polygon, Polygon):
            contours.append(polygon)
        elif isinstance(polygon, MultiPolygon):
            contours.extend([item for item in polygon.geoms if item.area >= 1.0])

    if not contours:
        return []

    contours = sorted(contours, key=lambda item: item.area, reverse=True)
    parents: list[int | None] = [None] * len(contours)
    for index, polygon in enumerate(contours):
        point = polygon.representative_point()
        containers = [
            candidate_index
            for candidate_index, candidate in enumerate(contours)
            if candidate_index != index
            and candidate.area > polygon.area + EPSILON
            and candidate.contains(point)
        ]
        if containers:
            parents[index] = min(containers, key=lambda candidate_index: contours[candidate_index].area)

    depths: list[int | None] = [None] * len(contours)

    def contour_depth(index: int) -> int:
        if depths[index] is not None:
            return depths[index]
        parent = parents[index]
        depths[index] = 0 if parent is None else contour_depth(parent) + 1
        return depths[index]

    for index in range(len(contours)):
        contour_depth(index)

    def filled_ancestor(index: int) -> int | None:
        parent = parents[index]
        while parent is not None:
            if contour_depth(parent) % 2 == 0:
                return parent
            parent = parents[parent]
        return None

    holes_by_shell: dict[int, list[Polygon]] = {}
    for index, polygon in enumerate(contours):
        if contour_depth(index) % 2 == 1:
            shell = filled_ancestor(index)
            if shell is not None:
                holes_by_shell.setdefault(shell, []).append(polygon)

    regions: list[Polygon] = []
    for index, polygon in enumerate(contours):
        if contour_depth(index) % 2 != 0:
            continue
        holes = [list(hole.exterior.coords) for hole in holes_by_shell.get(index, [])]
        try:
            region = Polygon(list(polygon.exterior.coords), holes)
        except Exception:
            continue
        if not region.is_valid:
            region = region.buffer(0)
        if region.is_empty:
            continue
        if isinstance(region, Polygon):
            if region.area >= 1.0:
                regions.append(region)
        elif isinstance(region, MultiPolygon):
            regions.extend([item for item in region.geoms if item.area >= 1.0])

    return sorted(regions, key=lambda item: item.area, reverse=True)


def polygon_parts(geometry, min_area: float = 1.0) -> list[Polygon]:
    if geometry.is_empty:
        return []
    if isinstance(geometry, Polygon):
        return [geometry] if geometry.area > min_area else []
    if isinstance(geometry, MultiPolygon):
        return [item for item in geometry.geoms if item.area > min_area]
    if isinstance(geometry, GeometryCollection):
        parts: list[Polygon] = []
        for item in geometry.geoms:
            parts.extend(polygon_parts(item, min_area))
        return parts
    return []


def largest_polygon(geometry) -> Polygon | None:
    items = polygon_parts(geometry)
    return max(items, key=lambda item: item.area) if items else None


def geometry_segments(geometry) -> Iterable[LineString]:
    if geometry.is_empty:
        return
    if isinstance(geometry, LineString):
        if geometry.length > EPSILON:
            yield geometry
    elif isinstance(geometry, MultiLineString):
        for item in geometry.geoms:
            if item.length > EPSILON:
                yield item
    elif isinstance(geometry, GeometryCollection):
        for item in geometry.geoms:
            yield from geometry_segments(item)


def normalized_route_points(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    normalized: list[tuple[float, float]] = []
    for point in points:
        current = (float(point[0]), float(point[1]))
        if normalized and distance(normalized[-1], current) <= EPSILON:
            continue
        normalized.append(current)
    if len(normalized) > 2 and distance(normalized[0], normalized[-1]) <= 0.05:
        normalized[-1] = normalized[0]
    return normalized


def path_is_closed(points: Sequence[tuple[float, float]]) -> bool:
    return len(points) > 2 and distance(points[0], points[-1]) <= 0.05


def circumradius(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    ab = distance(a, b)
    bc = distance(b, c)
    ca = distance(c, a)
    if ab <= EPSILON or bc <= EPSILON or ca <= EPSILON:
        return math.inf
    area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
    if area2 <= EPSILON:
        return math.inf
    return (ab * bc * ca) / (2.0 * area2)


def route_warnings_for_length(length: float, cfg: PlannerConfig) -> list[str]:
    warnings: list[str] = []
    if length < standalone_cuttable_min_route_length(cfg):
        warnings.append("shorter_than_cut_window")
    if length < cfg.start_length:
        warnings.append("shorter_than_start_length")
    if cfg.tension_length > EPSILON and length < cfg.tension_length:
        warnings.append("shorter_than_tension_requirement")
    return warnings


def hardware_min_route_length(cfg: PlannerConfig) -> float:
    return max(
        cfg.mechanical_min_route_length,
        cfg.min_route_length,
    )


def standalone_cuttable_min_route_length(cfg: PlannerConfig) -> float:
    return max(
        hardware_min_route_length(cfg),
        cfg.cut_distance + cfg.slow_length + max(cfg.tension_length, 0.0),
    )


def route_warnings_for_path(points: Sequence[tuple[float, float]], cfg: PlannerConfig) -> list[str]:
    warnings = route_warnings_for_length(polyline_length(points), cfg)
    if cfg.min_radius <= EPSILON or len(points) < 3:
        return warnings

    closed = path_is_closed(points)
    base_points = list(points[:-1] if closed else points)
    if len(base_points) < 3:
        return warnings

    indexes = range(len(base_points)) if closed else range(1, len(base_points) - 1)
    for index in indexes:
        a = base_points[index - 1]
        b = base_points[index]
        c = base_points[(index + 1) % len(base_points)]
        if circumradius(a, b, c) + EPSILON < cfg.min_radius:
            warnings.append("below_min_bend_radius")
            break
    return warnings


def select_longest_routes(routes: Sequence[FiberRoute], limit: int) -> list[FiberRoute]:
    if limit <= 0:
        return []
    return sorted(routes, key=lambda route: route.length, reverse=True)[:limit]


def median_float(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) * 0.5


def append_warning_once(route: FiberRoute, warning: str) -> None:
    if warning not in route.warnings:
        route.warnings.append(warning)


def route_spatial_center(points: Sequence[tuple[float, float]]) -> tuple[float, float] | None:
    base = route_base_points(points)
    if len(base) < 2:
        return None
    try:
        center = LineString(base + ([base[0]] if path_is_closed(points) else [])).centroid
    except Exception:
        return None
    return (float(center.x), float(center.y))


def route_extent(points: Sequence[tuple[float, float]]) -> float:
    base = route_base_points(points)
    if not base:
        return 0.0
    xs = [point[0] for point in base]
    ys = [point[1] for point in base]
    return max(max(xs) - min(xs), max(ys) - min(ys))


def layer_part_center(polygons: Sequence[Polygon]) -> tuple[float, float] | None:
    if not polygons:
        return None
    polygon = max(polygons, key=lambda item: item.area)
    center = polygon.centroid
    return (float(center.x), float(center.y))


def select_spatially_phased_routes(
    routes: Sequence[FiberRoute],
    limit: int,
    cfg: PlannerConfig,
    part_center: tuple[float, float] | None,
    warning_prefix: str,
) -> list[FiberRoute]:
    ordered = list(routes)
    if limit <= 0:
        return []
    if (
        not cfg.hole_reinforcement_alternate_regions
        or part_center is None
        or len(ordered) < 3
    ):
        return ordered[:limit]

    records: list[dict] = []
    for order, route in enumerate(ordered):
        if not path_is_closed(route.points):
            continue
        center = route_spatial_center(route.points)
        if center is None:
            continue
        records.append(
            {
                "route": route,
                "order": order,
                "center": center,
                "distance": distance(center, part_center),
                "extent": route_extent(route.points),
                "band": "neutral",
            }
        )

    if len(records) < 3:
        return ordered[:limit]

    nonzero_distances = [
        record["distance"]
        for record in records
        if record["distance"] > max(cfg.fiber_width, 0.5)
    ]
    if not nonzero_distances:
        return ordered[:limit]

    median_peripheral_distance = median_float(nonzero_distances)
    median_extent = median_float([record["extent"] for record in records])
    core_distance_limit = max(cfg.min_radius * 0.75, median_peripheral_distance * 0.35, cfg.fiber_width * 6.0)
    core_extent_limit = max(cfg.min_radius * 4.0, median_extent * 1.6)

    core_records = [
        record
        for record in records
        if record["distance"] <= core_distance_limit + EPSILON
        and record["extent"] <= core_extent_limit + EPSILON
    ]
    core_records.sort(key=lambda record: (record["distance"], record["extent"], record["order"]))
    if len(core_records) > 1:
        core_records = core_records[:1]
    core_ids = {id(record["route"]) for record in core_records}
    for record in core_records:
        record["band"] = "core"

    peripheral_records: list[dict] = []
    for record in records:
        if id(record["route"]) in core_ids:
            continue
        angle = math.atan2(record["center"][1] - part_center[1], record["center"][0] - part_center[0])
        if angle < 0.0:
            angle += math.tau
        record["angle"] = angle
        record["band"] = f"sector_{int(math.degrees(angle) // 45) % 8}"
        peripheral_records.append(record)

    peripheral_records.sort(key=lambda record: (record["angle"], record["distance"], record["order"]))

    chosen: list[dict] = []
    chosen_ids: set[int] = set()

    def add_records(candidates: Sequence[dict], remaining: int) -> None:
        if remaining <= 0:
            return
        for candidate in candidates:
            route_id = id(candidate["route"])
            if route_id in chosen_ids:
                continue
            chosen.append(candidate)
            chosen_ids.add(route_id)
            if len(chosen) >= limit:
                return

    if limit > 1:
        add_records(core_records, min(len(core_records), max(1, limit - 1)))

    remaining = limit - len(chosen)
    if peripheral_records and remaining > 0:
        start = cfg.fiber_path_phase % len(peripheral_records)
        stride = max(1, math.ceil(len(peripheral_records) / remaining))
        phased_peripherals: list[dict] = []
        used_indexes: set[int] = set()
        probe = 0
        while len(phased_peripherals) < len(peripheral_records) and probe < len(peripheral_records) * 2:
            index = (start + probe * stride) % len(peripheral_records)
            if index not in used_indexes:
                phased_peripherals.append(peripheral_records[index])
                used_indexes.add(index)
            probe += 1
        if len(phased_peripherals) < len(peripheral_records):
            for index, record in enumerate(peripheral_records):
                if index not in used_indexes:
                    phased_peripherals.append(record)
        add_records(phased_peripherals, remaining)

    if len(chosen) < limit:
        add_records(core_records, limit - len(chosen))

    if not chosen:
        return ordered[:limit]

    phase = cfg.fiber_path_phase
    for record in chosen:
        route = record["route"]
        append_warning_once(route, f"{warning_prefix}_region_phase_{phase}")
        append_warning_once(route, f"{warning_prefix}_region_{record['band']}")
    return [record["route"] for record in chosen]


def route_base_points(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    if path_is_closed(points):
        return list(points[:-1])
    return list(points)


def rotated_closed_route(points: Sequence[tuple[float, float]], start_index: int) -> list[tuple[float, float]]:
    base = route_base_points(points)
    if not base:
        return []
    start_index = start_index % len(base)
    return base[start_index:] + base[:start_index] + [base[start_index]]


def repeated_closed_route(points: Sequence[tuple[float, float]], laps: int) -> list[tuple[float, float]]:
    base = route_base_points(points)
    if not base:
        return []
    laps = max(laps, 1)
    repeated = base + [base[0]]
    for _ in range(1, laps):
        repeated.extend(base[1:])
        repeated.append(base[0])
    return repeated


def closed_route_start_index_for_angle(points: Sequence[tuple[float, float]], angle_degrees: float) -> int:
    base = route_base_points(points)
    if not base:
        return 0
    center = route_spatial_center(points)
    if center is None:
        return 0
    radians = math.radians(angle_degrees)
    direction = (math.cos(radians), math.sin(radians))
    return max(
        range(len(base)),
        key=lambda index: (
            (base[index][0] - center[0]) * direction[0] + (base[index][1] - center[1]) * direction[1],
            -index,
        ),
    )


def deterministic_closed_route_start_index(route: FiberRoute, route_ordinal: int) -> int:
    base = route_base_points(route.points)
    if not base:
        return 0
    seed = (
        (route.layer_index + 1) * 2654435761
        + (route_ordinal + 1) * 40503
        + len(route.kind) * 97
        + int(round(route.length * 100.0))
    )
    return seed % len(base)


def fiber_seam_rotated_route(
    route: FiberRoute,
    cfg: PlannerConfig,
    previous_endpoint: tuple[float, float] | None,
    route_ordinal: int,
) -> FiberRoute:
    position = normalized_fiber_seam_position(cfg.fiber_seam_position)
    if position == "source" or not path_is_closed(route.points):
        return route

    base = route_base_points(route.points)
    if not base:
        return route

    start_index = 0
    if position == "nearest":
        if previous_endpoint is not None:
            start_index = min(range(len(base)), key=lambda index: (distance(base[index], previous_endpoint), index))
        else:
            start_index = closed_route_start_index_for_angle(route.points, cfg.fiber_seam_angle)
    elif position == "aligned":
        start_index = closed_route_start_index_for_angle(route.points, cfg.fiber_seam_angle)
    elif position == "rear":
        start_index = closed_route_start_index_for_angle(route.points, 90.0)
    elif position == "random":
        start_index = deterministic_closed_route_start_index(route, route_ordinal)

    points = rotated_closed_route(route.points, start_index)
    if not points:
        return route
    warnings = list(route.warnings)
    warning = f"fiber_seam_{position}"
    if warning not in warnings:
        warnings.append(warning)
    if position == "aligned":
        angle_warning = f"fiber_seam_angle_{fmt_float(cfg.fiber_seam_angle, 0)}"
        if angle_warning not in warnings:
            warnings.append(angle_warning)
    return replace(route, points=points, warnings=warnings)


def apply_fiber_seam_placement(layer_routes: Sequence[FiberRoute], cfg: PlannerConfig) -> list[FiberRoute]:
    if normalized_fiber_seam_position(cfg.fiber_seam_position) == "source":
        return list(layer_routes)
    rotated: list[FiberRoute] = []
    previous_endpoint: tuple[float, float] | None = None
    for route_ordinal, route in enumerate(layer_routes):
        adjusted = fiber_seam_rotated_route(route, cfg, previous_endpoint, route_ordinal)
        rotated.append(adjusted)
        if adjusted.points:
            previous_endpoint = adjusted.points[-1]
    return rotated


def extend_closed_route_to_min_length(
    route: FiberRoute,
    minimum_length: float,
    warning_prefix: str,
) -> FiberRoute | None:
    if route.length + EPSILON >= minimum_length:
        return route
    if not path_is_closed(route.points) or route.length <= EPSILON:
        return None

    laps = max(2, math.ceil(minimum_length / route.length))
    points = repeated_closed_route(route.points, laps)
    if polyline_length(points) + EPSILON < minimum_length:
        return None

    warnings = [warning for warning in route.warnings if warning != "shorter_than_cut_window"]
    warnings.append(f"{warning_prefix}_{laps}x_lap")
    warnings.append(f"standalone_cut_window_min_{fmt_float(minimum_length, 0)}mm")
    return FiberRoute(
        layer_index=route.layer_index,
        z=route.z,
        kind=route.kind,
        angle=route.angle,
        points=points,
        source_role=route.source_role,
        warnings=warnings,
    )


def clustered_points(
    points: Sequence[tuple[float, float]],
    max_distance: float,
) -> list[list[tuple[float, float]]]:
    clusters: list[list[tuple[float, float]]] = []
    for point in points:
        matching_indexes = [
            index
            for index, cluster in enumerate(clusters)
            if any(distance(point, existing) <= max_distance + EPSILON for existing in cluster)
        ]
        if not matching_indexes:
            clusters.append([point])
            continue
        first_index = matching_indexes[0]
        clusters[first_index].append(point)
        for index in reversed(matching_indexes[1:]):
            clusters[first_index].extend(clusters.pop(index))
    return clusters


def smooth_cluster_halo(
    centers: Sequence[tuple[float, float]],
    radius: float,
    cfg: PlannerConfig,
) -> list[tuple[float, float]]:
    if not centers:
        return []
    resolution = max(8, int(math.ceil((math.pi * radius / 2.0) / max(cfg.max_arc_segment_length, 0.5))))
    geometry = MultiPoint(list(centers)).convex_hull.buffer(radius, resolution=resolution, join_style=1)
    if geometry.is_empty:
        return []
    if isinstance(geometry, MultiPolygon):
        geometry = max(geometry.geoms, key=lambda item: item.area)
    if not isinstance(geometry, Polygon):
        return []
    return normalized_route_points([(float(x), float(y)) for x, y in geometry.exterior.coords])


def smooth_circular_trace_route(
    points: Sequence[tuple[float, float]],
    cfg: PlannerConfig,
) -> list[tuple[float, float]]:
    base = route_base_points(points)
    if len(base) < 8:
        return []
    line = LineString(base + [base[0]])
    center = line.centroid
    distances = [distance((float(center.x), float(center.y)), point) for point in base]
    radius = max(max(distances), cfg.min_radius)
    if radius + EPSILON < cfg.min_radius:
        return []

    max_segment = max(cfg.max_arc_segment_length, 0.5)
    segments = max(24, int(math.ceil((2.0 * math.pi * radius) / max_segment)))
    start_angle = math.atan2(base[0][1] - center.y, base[0][0] - center.x)
    signed_area = 0.0
    for start, end in zip(base, base[1:] + [base[0]]):
        signed_area += start[0] * end[1] - end[0] * start[1]
    direction = 1.0 if signed_area >= 0.0 else -1.0
    smooth = [
        (
            float(center.x) + radius * math.cos(start_angle + direction * 2.0 * math.pi * index / segments),
            float(center.y) + radius * math.sin(start_angle + direction * 2.0 * math.pi * index / segments),
        )
        for index in range(segments)
    ]
    smooth.append(smooth[0])
    return normalized_route_points(smooth)


def smooth_circular_orbit_route(
    center: tuple[float, float],
    radius: float,
    cfg: PlannerConfig,
    start_angle: float = 0.0,
) -> list[tuple[float, float]]:
    if radius + EPSILON < cfg.min_radius:
        return []
    max_segment = max(cfg.max_arc_segment_length, 0.5)
    segments = max(24, int(math.ceil((2.0 * math.pi * radius) / max_segment)))
    points = [
        (
            center[0] + radius * math.cos(start_angle + 2.0 * math.pi * index / segments),
            center[1] + radius * math.sin(start_angle + 2.0 * math.pi * index / segments),
        )
        for index in range(segments)
    ]
    points.append(points[0])
    return normalized_route_points(points)


def nearest_route_connection(
    first: FiberRoute,
    second: FiberRoute,
) -> tuple[float, int, int, tuple[float, float], tuple[float, float]]:
    first_points = route_base_points(first.points)
    second_points = route_base_points(second.points)
    best: tuple[float, int, int, tuple[float, float], tuple[float, float]] | None = None
    for first_index, first_point in enumerate(first_points):
        for second_index, second_point in enumerate(second_points):
            gap = distance(first_point, second_point)
            if best is None or gap < best[0]:
                best = (gap, first_index, second_index, first_point, second_point)
    if best is None:
        return (math.inf, 0, 0, (0.0, 0.0), (0.0, 0.0))
    return best


def connector_is_printable(
    start: tuple[float, float],
    end: tuple[float, float],
    polygons: Sequence[Polygon],
) -> bool:
    connector = LineString([start, end])
    if connector.length <= EPSILON:
        return True
    return any(polygon.buffer(0.05).covers(connector) for polygon in polygons)


def route_is_printable(
    points: Sequence[tuple[float, float]],
    polygons: Sequence[Polygon],
) -> bool:
    if len(points) < 2:
        return False
    route = LineString(points)
    if route.length <= EPSILON:
        return False
    return any(polygon.buffer(0.05).covers(route) for polygon in polygons)


def grouped_hole_loop_infos(
    closed_loops: Sequence[dict],
    cfg: PlannerConfig,
) -> list[dict]:
    groups: list[list[dict]] = []
    center_tolerance = max(0.45, cfg.fiber_width * 0.6)
    radius_tolerance = max(cfg.fiber_width * 3.0, 3.0)
    for loop_info in sorted(closed_loops, key=lambda item: item["equivalent_radius"]):
        for group in groups:
            if (
                distance(loop_info["center"], group[0]["center"]) <= center_tolerance + EPSILON
                and abs(loop_info["equivalent_radius"] - group[0]["equivalent_radius"]) <= radius_tolerance + EPSILON
            ):
                group.append(loop_info)
                break
        else:
            groups.append([loop_info])

    grouped: list[dict] = []
    max_void_radius = cfg.min_radius * cfg.hole_reinforcement_max_radius_factor
    for group in groups:
        support_loop = max(group, key=lambda item: item["equivalent_radius"])
        outer_loops = [
            item
            for item in group
            if item.get("role") == "Outer wall"
            and item.get("polygon") is not None
            and item["equivalent_radius"] <= max_void_radius + EPSILON
        ]
        void_loop = max(outer_loops, key=lambda item: item["equivalent_radius"]) if outer_loops else min(
            (item for item in group if item.get("polygon") is not None and item["equivalent_radius"] <= max_void_radius + EPSILON),
            key=lambda item: item["equivalent_radius"],
            default=None,
        )
        grouped_info = dict(support_loop)
        grouped_info["void_polygon"] = void_loop.get("polygon") if void_loop else None
        grouped_info["void_radius"] = void_loop.get("equivalent_radius", support_loop["equivalent_radius"]) if void_loop else support_loop["equivalent_radius"]
        grouped_info["roles"] = sorted({str(item.get("role", "")) for item in group if item.get("role")})
        grouped.append(grouped_info)
    return grouped


def route_avoids_hole_voids(
    points: Sequence[tuple[float, float]],
    hole_infos: Sequence[dict],
    cfg: PlannerConfig,
) -> bool:
    if len(points) < 2:
        return False
    route = LineString(points)
    clearance = max(cfg.fiber_width * 0.35, 0.25)
    for hole_info in hole_infos:
        void_polygon = hole_info.get("void_polygon")
        if void_polygon is None or void_polygon.is_empty:
            continue
        if route.distance(void_polygon) <= clearance + EPSILON:
            return False
    return True


def expanded_hole_orbit_route(
    layer: LayerGeometry,
    hole_info: dict,
    hole_infos: Sequence[dict],
    cfg: PlannerConfig,
    minimum_hardware_length: float,
    skipped: dict[str, int],
) -> FiberRoute | None:
    center = hole_info["center"]
    route_radius = max(
        cfg.min_radius + 0.25,
        (minimum_hardware_length / (2.0 * math.pi)) + 0.25,
        hole_info["equivalent_radius"] + max(cfg.fiber_width, 0.5),
    )
    max_radius = min(cfg.min_radius * cfg.hole_reinforcement_max_radius_factor, cfg.min_radius + max(cfg.fiber_width * 6.0, 4.0))
    attempts = 0
    while route_radius <= max_radius + EPSILON:
        points = smooth_circular_orbit_route(center, route_radius, cfg)
        attempts += 1
        if len(points) >= 4 and polyline_length(points) + EPSILON >= minimum_hardware_length:
            try:
                route_polygon = Polygon(points)
            except Exception:
                route_polygon = None
            encloses_neighbor = (
                route_polygon is not None
                and any(
                    other is not hole_info
                    and other["equivalent_radius"] + EPSILON < cfg.min_radius
                    and route_polygon.contains(Point(other["center"]))
                    for other in hole_infos
                )
            )
            warnings = route_warnings_for_path(points, cfg)
            if not encloses_neighbor and route_avoids_hole_voids(points, hole_infos, cfg):
                warnings.append("hole_reinforcement")
                warnings.append("expanded_hole_orbit")
                warnings.append(f"mechanical_min_route_{fmt_float(minimum_hardware_length, 0)}mm")
                return FiberRoute(
                    layer_index=layer.index,
                    z=layer.z,
                    kind="hole_reinforcement_loop",
                    angle=None,
                    points=points,
                    source_role="Inner wall",
                    warnings=warnings,
                )
        route_radius += max(cfg.fiber_width, 0.5)

    if attempts:
        skipped["hole_reinforcement_expanded_orbit_skipped"] += 1
    return None


def local_hole_cluster_reinforcement_routes(
    layer: LayerGeometry,
    hole_infos: Sequence[dict],
    cfg: PlannerConfig,
    minimum_hardware_length: float,
    skipped: dict[str, int],
) -> list[tuple[float, float, FiberRoute]]:
    small_holes = [
        hole_info
        for hole_info in hole_infos
        if hole_info["equivalent_radius"] + EPSILON < cfg.min_radius and hole_info.get("void_polygon") is not None
    ]
    if len(small_holes) < 2:
        return []

    cluster_distance = max(cfg.min_radius * 2.35, cfg.fiber_width * 12.0)
    clusters: list[list[dict]] = []
    for hole_info in small_holes:
        matching_indexes = [
            index
            for index, cluster in enumerate(clusters)
            if any(distance(hole_info["center"], existing["center"]) <= cluster_distance + EPSILON for existing in cluster)
        ]
        if not matching_indexes:
            clusters.append([hole_info])
            continue
        first_index = matching_indexes[0]
        clusters[first_index].append(hole_info)
        for index in reversed(matching_indexes[1:]):
            clusters[first_index].extend(clusters.pop(index))

    candidates: list[tuple[float, float, FiberRoute]] = []
    max_center_span = max(cfg.min_radius * 3.5, 24.0)
    max_route_span = max_center_span + (2.0 * (cfg.min_radius + max(cfg.fiber_width * 6.0, 4.0)))
    base_radius = cfg.min_radius + 0.25
    for cluster in clusters:
        if len(cluster) < 2:
            continue
        xs = [item["center"][0] for item in cluster]
        ys = [item["center"][1] for item in cluster]
        center_span = max(max(xs) - min(xs), max(ys) - min(ys))
        if center_span > max_center_span + EPSILON:
            skipped["hole_cluster_reinforcement_skipped"] += 1
            continue

        route_radius = base_radius
        route: FiberRoute | None = None
        while route_radius <= cfg.min_radius + max(cfg.fiber_width * 6.0, 4.0) + EPSILON:
            points = smooth_cluster_halo([item["center"] for item in cluster], route_radius, cfg)
            if len(points) < 4:
                route_radius += max(cfg.fiber_width, 0.5)
                continue
            route_length = polyline_length(points)
            bounds = LineString(points).bounds
            route_span = max(bounds[2] - bounds[0], bounds[3] - bounds[1])
            warnings = route_warnings_for_path(points, cfg)
            if (
                route_length + EPSILON >= minimum_hardware_length
                and route_span <= max_route_span + EPSILON
                and route_avoids_hole_voids(points, hole_infos, cfg)
            ):
                warnings.append("hole_reinforcement")
                warnings.append("local_hole_cluster_halo")
                warnings.append(f"hole_cluster_{len(cluster)}x")
                warnings.append(f"mechanical_min_route_{fmt_float(minimum_hardware_length, 0)}mm")
                route = FiberRoute(
                    layer_index=layer.index,
                    z=layer.z,
                    kind="hole_cluster_reinforcement_loop",
                    angle=None,
                    points=points,
                    source_role="Inner wall",
                    warnings=warnings,
                )
                break
            route_radius += max(cfg.fiber_width, 0.5)

        if route is None:
            skipped["hole_cluster_reinforcement_skipped"] += 1
            continue
        candidates.append((min(item["length"] for item in cluster), route.length, route))
    return candidates


def loop_nearest_point_index(points: Sequence[tuple[float, float]], target: tuple[float, float]) -> int:
    base = route_base_points(points)
    if not base:
        return 0
    return min(range(len(base)), key=lambda index: distance(base[index], target))


def internal_void_shell_groups(
    closed_loops: Sequence[dict],
    hole_infos: Sequence[dict],
    minimum_shell_radius: float,
) -> list[tuple[Polygon, list[dict]]]:
    shells: list[Polygon] = []
    for loop_info in closed_loops:
        polygon = loop_info.get("polygon")
        if polygon is None or polygon.is_empty:
            continue
        if loop_info["equivalent_radius"] < minimum_shell_radius:
            continue
        shells.append(polygon)

    if not shells:
        return []

    grouped: dict[int, tuple[Polygon, list[dict]]] = {}
    shell_buffers = [(shell, shell.buffer(0.05)) for shell in shells]
    for hole_info in hole_infos:
        center = Point(hole_info["center"])
        containing_shells = [
            shell
            for shell, shell_buffer in shell_buffers
            if shell_buffer.covers(center)
        ]
        if not containing_shells:
            continue
        shell = min(containing_shells, key=lambda polygon: polygon.area)
        key = id(shell)
        if key not in grouped:
            grouped[key] = (shell, [])
        grouped[key][1].append(hole_info)

    return [
        (shell, group)
        for shell, group in grouped.values()
        if len(group) >= 4
    ]


def stitched_internal_void_routes(
    layer: LayerGeometry,
    closed_loops: Sequence[dict],
    hole_infos: Sequence[dict],
    cfg: PlannerConfig,
    minimum_hardware_length: float,
    skipped: dict[str, int],
    part_center: tuple[float, float] | None,
) -> list[tuple[float, float, FiberRoute]]:
    if cfg.hole_reinforcement_routes_per_layer <= 0 or not cfg.hole_reinforcement_alternate_regions:
        return []

    internal_holes = [
        hole_info
        for hole_info in hole_infos
        if hole_info.get("loop")
        and hole_info.get("void_polygon") is not None
        and "Outer wall" in hole_info.get("roles", [])
        and hole_info["equivalent_radius"] + EPSILON < cfg.min_radius
    ]
    if len(internal_holes) < 4:
        return []

    shell_groups = internal_void_shell_groups(closed_loops, internal_holes, cfg.min_radius)
    if not shell_groups:
        return []

    candidates: list[tuple[float, float, FiberRoute]] = []
    for shell_polygon, grouped_holes in shell_groups:
        shell_center = (float(shell_polygon.centroid.x), float(shell_polygon.centroid.y))
        candidates.extend(
            stitched_internal_void_group_routes(
                layer,
                grouped_holes,
                shell_polygon,
                cfg,
                minimum_hardware_length,
                skipped,
                shell_center,
            )
        )

    skipped["internal_void_stitch_routes"] += len(candidates)
    return candidates


def stitched_internal_void_group_routes(
    layer: LayerGeometry,
    internal_holes: Sequence[dict],
    shell_polygon: Polygon,
    cfg: PlannerConfig,
    minimum_hardware_length: float,
    skipped: dict[str, int],
    part_center: tuple[float, float],
) -> list[tuple[float, float, FiberRoute]]:
    if len(internal_holes) < 4:
        return []

    core = min(
        internal_holes,
        key=lambda hole_info: (
            distance(hole_info["center"], part_center),
            -hole_info["equivalent_radius"],
        ),
    )
    if distance(core["center"], part_center) > max(cfg.min_radius * 0.65, cfg.fiber_width * 5.0):
        return []

    peripherals = [
        hole_info
        for hole_info in internal_holes
        if hole_info is not core
        and distance(hole_info["center"], core["center"]) > max(cfg.fiber_width * 4.0, 2.0)
    ]
    if len(peripherals) < 3:
        return []

    shell_buffer = shell_polygon.buffer(max(cfg.fiber_width * 0.45, 0.25))

    peripherals.sort(
        key=lambda hole_info: math.atan2(
            hole_info["center"][1] - core["center"][1],
            hole_info["center"][0] - core["center"][0],
        )
    )
    phase = cfg.fiber_path_phase % len(peripherals)
    routes_this_layer = 2 if cfg.reinforcement_mode == "heavy" else 1
    routes_this_layer = min(routes_this_layer, len(peripherals), max(cfg.hole_reinforcement_routes_per_layer, 1))

    core_loop = normalized_route_points(core["loop"])
    if len(core_loop) < 4 or not path_is_closed(core_loop):
        return []

    candidates: list[tuple[float, float, FiberRoute]] = []
    selected_holes = [peripherals[(phase + offset) % len(peripherals)] for offset in range(routes_this_layer)]
    for hole_info in selected_holes:
        satellite_loop = normalized_route_points(hole_info["loop"])
        if len(satellite_loop) < 4 or not path_is_closed(satellite_loop):
            skipped["internal_void_stitch_skipped"] += 1
            continue

        core_index = loop_nearest_point_index(core_loop, hole_info["center"])
        core_route = rotated_closed_route(core_loop, core_index)
        core_anchor = core_route[0]
        satellite_index = loop_nearest_point_index(satellite_loop, core_anchor)
        satellite_route = rotated_closed_route(satellite_loop, satellite_index)
        satellite_anchor = satellite_route[0]

        connector = LineString([core_anchor, satellite_anchor])
        blocks_unselected_hole = False
        for other in internal_holes:
            if other is core or other is hole_info:
                continue
            void_polygon = other.get("void_polygon")
            if void_polygon is not None and connector.distance(void_polygon) <= max(cfg.fiber_width * 0.2, 0.08):
                blocks_unselected_hole = True
                break
        if blocks_unselected_hole:
            skipped["internal_void_stitch_skipped"] += 1
            continue

        satellite_laps = 1
        points: list[tuple[float, float]] = []
        while satellite_laps <= max(cfg.hole_reinforcement_max_laps + 2, 5):
            repeated_satellite = repeated_closed_route(satellite_route, satellite_laps)
            points = list(core_route)
            if distance(points[-1], satellite_anchor) > EPSILON:
                points.append(satellite_anchor)
            points.extend(repeated_satellite[1:])
            if distance(points[-1], core_anchor) > EPSILON:
                points.append(core_anchor)
            points = normalized_route_points(points)
            if polyline_length(points) + EPSILON >= minimum_hardware_length:
                break
            satellite_laps += 1

        route_length = polyline_length(points)
        if route_length + EPSILON < minimum_hardware_length:
            skipped["internal_void_stitch_skipped"] += 1
            continue

        route_line = LineString(points)
        if not shell_buffer.covers(route_line):
            skipped["internal_void_stitch_skipped"] += 1
            continue

        warnings = route_warnings_for_path(points, cfg)
        warnings.append("hole_reinforcement")
        warnings.append("internal_void_stitch")
        warnings.append(f"internal_void_phase_{cfg.fiber_path_phase}")
        angle = math.atan2(hole_info["center"][1] - core["center"][1], hole_info["center"][0] - core["center"][0])
        if angle < 0.0:
            angle += math.tau
        warnings.append(f"internal_void_sector_{int(math.degrees(angle) // 45) % 8}")
        if satellite_laps > 1:
            warnings.append(f"internal_void_satellite_{satellite_laps}x_lap")
        warnings.append(f"mechanical_min_route_{fmt_float(minimum_hardware_length, 0)}mm")
        route = FiberRoute(
            layer_index=layer.index,
            z=layer.z,
            kind="hole_cluster_reinforcement_loop",
            angle=None,
            points=points,
            source_role="Inner wall",
            warnings=warnings,
        )
        candidates.append((hole_info["length"], route.length, route))

    return candidates


def stitched_short_perimeter_routes(
    layer: LayerGeometry,
    routes: Sequence[FiberRoute],
    polygons: Sequence[Polygon],
    cfg: PlannerConfig,
) -> list[FiberRoute]:
    minimum_hardware_length = hardware_min_route_length(cfg)
    max_connector_gap = min(max(cfg.fiber_width * 4.0, 2.5), max(cfg.min_radius * 0.5, 2.5))
    candidates = [
        route
        for route in routes
        if route.kind == "perimeter_trace"
        and route.source_role in PERIMETER_TRACE_ROLES
        and route.length + EPSILON < minimum_hardware_length
        and route.length + EPSILON >= cfg.perimeter_min_route_length
        and path_is_closed(route.points)
    ]
    candidates.sort(key=lambda route: route.length, reverse=True)

    stitched: list[FiberRoute] = []
    used: set[int] = set()
    for first_index, first in enumerate(candidates):
        if first_index in used:
            continue
        best: tuple[float, int, int, int, tuple[float, float], tuple[float, float]] | None = None
        for second_index in range(first_index + 1, len(candidates)):
            if second_index in used:
                continue
            second = candidates[second_index]
            gap, first_point_index, second_point_index, first_point, second_point = nearest_route_connection(first, second)
            if gap > max_connector_gap + EPSILON:
                continue
            if first.length + second.length + gap + EPSILON < minimum_hardware_length:
                continue
            if not connector_is_printable(first_point, second_point, polygons):
                continue
            candidate = (gap, second_index, first_point_index, second_point_index, first_point, second_point)
            if best is None or candidate < best:
                best = candidate
        if best is None:
            continue
        gap, second_index, first_point_index, second_point_index, first_point, second_point = best
        first_points = rotated_closed_route(first.points, first_point_index)
        second_points = rotated_closed_route(candidates[second_index].points, second_point_index)
        stitched_points = normalized_route_points(first_points + [second_point] + second_points)
        warnings = route_warnings_for_path(stitched_points, cfg)
        warnings.append("stitched_short_perimeter_route")
        warnings.append(f"stitched_connector_{fmt_float(gap, 2)}mm")
        stitched.append(
            FiberRoute(
                layer_index=layer.index,
                z=layer.z,
                kind="stitched_perimeter_trace",
                angle=None,
                points=stitched_points,
                source_role="Inner wall",
                warnings=warnings,
            )
        )
        used.add(first_index)
        used.add(second_index)
    return stitched


def perimeter_routes(layer: LayerGeometry, polygon: Polygon, cfg: PlannerConfig) -> list[FiberRoute]:
    routes: list[FiberRoute] = []
    boundary = polygon.buffer(-cfg.perimeter_inset, join_style=1)
    boundary_polygons = polygon_parts(boundary) or [polygon]

    def append_ring_routes(
        coords: Sequence[tuple[float, float]],
        kind: str,
        source_role: str,
    ) -> None:
        points = normalized_route_points([(float(x), float(y)) for x, y in coords])
        if len(points) < 2:
            return
        length = polyline_length(points)
        if length >= cfg.perimeter_min_route_length:
            routes.append(
                FiberRoute(
                    layer_index=layer.index,
                    z=layer.z,
                    kind=kind,
                    angle=None,
                    points=points,
                    source_role=source_role,
                    warnings=route_warnings_for_path(points, cfg),
                )
            )

    for boundary_polygon in boundary_polygons:
        append_ring_routes(list(boundary_polygon.exterior.coords), "outer_perimeter_loop", "Outer wall")
        for interior in boundary_polygon.interiors:
            append_ring_routes(list(interior.coords), "hole_perimeter_loop", "Inner wall")
    return routes


def hole_reinforcement_routes(
    layer: LayerGeometry,
    polygon: Polygon,
    cfg: PlannerConfig,
    skipped: dict[str, int],
    part_center: tuple[float, float] | None = None,
) -> list[FiberRoute]:
    if cfg.hole_reinforcement_routes_per_layer <= 0:
        return []

    candidates: list[tuple[float, FiberRoute]] = []
    minimum_hardware_length = hardware_min_route_length(cfg)
    boundary = polygon.buffer(-cfg.perimeter_inset, join_style=1)
    boundary_polygons = polygon_parts(boundary) or [polygon]
    seen: set[tuple[float, float, float]] = set()

    for boundary_polygon in boundary_polygons:
        for interior in boundary_polygon.interiors:
            loop = normalized_route_points([(float(x), float(y)) for x, y in interior.coords])
            if len(loop) < 4 or not path_is_closed(loop):
                continue
            loop_length = polyline_length(loop)
            if loop_length <= EPSILON:
                continue

            centroid = Polygon(loop).centroid if len(loop) >= 4 else LineString(loop).centroid
            key = (round(float(centroid.x), 2), round(float(centroid.y), 2), round(loop_length, 1))
            if key in seen:
                continue
            seen.add(key)

            laps = max(1, math.ceil(minimum_hardware_length / loop_length))
            if laps > cfg.hole_reinforcement_max_laps:
                skipped["hole_reinforcement_skipped_by_max_laps"] += 1
                continue

            points = repeated_closed_route(loop, laps)
            if polyline_length(points) + EPSILON < minimum_hardware_length:
                skipped["hole_reinforcement_skipped_by_hardware_min_length"] += 1
                continue

            warnings = route_warnings_for_path(points, cfg)
            warnings.append("hole_reinforcement")
            if laps > 1:
                warnings.append(f"hole_reinforcement_{laps}x_lap")
            warnings.append(f"mechanical_min_route_{fmt_float(minimum_hardware_length, 0)}mm")
            candidates.append(
                (
                    loop_length,
                    FiberRoute(
                        layer_index=layer.index,
                        z=layer.z,
                        kind="hole_reinforcement_loop",
                        angle=None,
                        points=points,
                        source_role="Inner wall",
                        warnings=warnings,
                    ),
                )
            )

    candidates.sort(key=lambda item: (item[0], -item[1].length))
    selected = select_spatially_phased_routes(
        [route for _, route in candidates],
        cfg.hole_reinforcement_routes_per_layer,
        cfg,
        part_center or (float(polygon.centroid.x), float(polygon.centroid.y)),
        "hole_reinforcement",
    )
    skipped["hole_reinforcement_routes"] += len(selected)
    return selected


def traced_hole_reinforcement_routes(
    layer: LayerGeometry,
    polygons: Sequence[Polygon],
    cfg: PlannerConfig,
    skipped: dict[str, int],
    part_center: tuple[float, float] | None = None,
) -> list[FiberRoute]:
    if cfg.hole_reinforcement_routes_per_layer <= 0:
        return []

    candidates_by_center: dict[tuple[int, int], tuple[tuple[float, float], float, FiberRoute]] = {}
    minimum_hardware_length = hardware_min_route_length(cfg)
    max_hole_radius = cfg.min_radius * cfg.hole_reinforcement_max_radius_factor
    closed_loops: list[dict] = []
    for extrusion_path in layer.extrusion_paths:
        if extrusion_path.role not in HOLE_TRACE_ROLES:
            continue
        loop = normalized_route_points(extrusion_path.points)
        if len(loop) < 4 or not path_is_closed(loop):
            continue
        loop_length = polyline_length(loop)
        if loop_length <= EPSILON:
            continue
        centroid = LineString(loop).centroid
        center = (float(centroid.x), float(centroid.y))
        equivalent_radius = loop_length / (2.0 * math.pi)
        polygon = None
        try:
            candidate_polygon = Polygon(loop)
            if candidate_polygon.is_valid and not candidate_polygon.is_empty:
                polygon = candidate_polygon
        except Exception:
            polygon = None
        closed_loops.append(
            {
                "loop": loop,
                "length": loop_length,
                "center": center,
                "equivalent_radius": equivalent_radius,
                "polygon": polygon,
                "role": extrusion_path.role,
            }
        )

    grouped_holes = grouped_hole_loop_infos(closed_loops, cfg)
    cluster_candidates = stitched_internal_void_routes(
        layer,
        closed_loops,
        grouped_holes,
        cfg,
        minimum_hardware_length,
        skipped,
        part_center or layer_part_center(polygons),
    )
    for hole_info in grouped_holes:
        if hole_info["equivalent_radius"] + EPSILON >= cfg.min_radius:
            continue
        if hole_info["equivalent_radius"] > max_hole_radius + EPSILON:
            skipped["hole_reinforcement_skipped_by_radius"] += 1
            continue
        route = expanded_hole_orbit_route(layer, hole_info, grouped_holes, cfg, minimum_hardware_length, skipped)
        if route is None:
            continue
        center = hole_info["center"]
        center_key = (round(center[0] / 2.0), round(center[1] / 2.0))
        candidate_score = (route.length, -hole_info["length"])
        existing = candidates_by_center.get(center_key)
        if existing is None or candidate_score < existing[0]:
            candidates_by_center[center_key] = (candidate_score, hole_info["length"], route)

    for loop_info in closed_loops:
        loop = loop_info["loop"]
        loop_length = loop_info["length"]
        center = loop_info["center"]
        equivalent_radius = loop_info["equivalent_radius"]
        polygon = loop_info["polygon"]
        if loop_info.get("role") not in PERIMETER_TRACE_ROLES:
            continue
        if equivalent_radius + EPSILON < cfg.min_radius or equivalent_radius > max_hole_radius + EPSILON:
            skipped["hole_reinforcement_skipped_by_radius"] += 1
            continue
        if polygon is not None:
            encloses_distinct_loop = any(
                other is not loop_info
                and other["equivalent_radius"] < equivalent_radius + EPSILON
                and distance(center, other["center"]) > max(cfg.min_radius, cfg.fiber_width * 8.0)
                and polygon.contains(Point(other["center"]))
                for other in closed_loops
            )
            if encloses_distinct_loop:
                skipped["hole_reinforcement_skipped_by_enclosing_loop"] += 1
                continue

        smooth_loop = smooth_circular_trace_route(loop, cfg)
        if len(smooth_loop) < 4:
            skipped["hole_reinforcement_skipped_by_smoothing"] += 1
            continue

        smooth_loop_length = polyline_length(smooth_loop)
        laps = max(1, math.ceil(minimum_hardware_length / smooth_loop_length))
        if laps > cfg.hole_reinforcement_max_laps:
            skipped["hole_reinforcement_skipped_by_max_laps"] += 1
            continue

        points = repeated_closed_route(smooth_loop, laps)
        route_length = polyline_length(points)
        if route_length + EPSILON < minimum_hardware_length:
            skipped["hole_reinforcement_skipped_by_hardware_min_length"] += 1
            continue
        if not route_is_printable(points, polygons):
            skipped["hole_reinforcement_skipped_by_unprintable_path"] += 1
            continue

        warnings = route_warnings_for_path(points, cfg)

        center_key = (round(center[0] / 2.0), round(center[1] / 2.0))
        warnings.append("hole_reinforcement")
        warnings.append("inner_wall_hole_trace")
        if laps > 1:
            warnings.append(f"hole_reinforcement_{laps}x_lap")
        warnings.append(f"mechanical_min_route_{fmt_float(minimum_hardware_length, 0)}mm")
        route = FiberRoute(
            layer_index=layer.index,
            z=layer.z,
            kind="hole_reinforcement_loop",
            angle=None,
            points=points,
            source_role="Inner wall",
            warnings=warnings,
        )
        candidate_score = (route_length, -loop_length)
        existing = candidates_by_center.get(center_key)
        if existing is None or candidate_score < existing[0]:
            candidates_by_center[center_key] = (candidate_score, loop_length, route)

    selected_cluster_routes = select_spatially_phased_routes(
        [
            route
            for _, _, route in sorted(
                cluster_candidates,
                key=lambda item: (item[1], item[0]),
            )
        ],
        cfg.hole_reinforcement_routes_per_layer,
        cfg,
        part_center or layer_part_center(polygons),
        "hole_reinforcement",
    )

    remaining_route_limit = max(cfg.hole_reinforcement_routes_per_layer - len(selected_cluster_routes), 0)
    candidate_records = list(candidates_by_center.values())
    ordered_candidates = [
        route
        for _, _, route in sorted(
            candidate_records,
            key=lambda item: (item[1], item[2].length),
        )
    ]
    selected_regular_routes = select_spatially_phased_routes(
        ordered_candidates,
        remaining_route_limit,
        cfg,
        part_center or layer_part_center(polygons),
        "hole_reinforcement",
    )
    selected = selected_cluster_routes + selected_regular_routes
    skipped["hole_reinforcement_routes"] += len(selected)
    skipped["hole_cluster_reinforcement_routes"] += sum(1 for route in selected if route.kind == "hole_cluster_reinforcement_loop")
    return selected


def traced_path_routes(
    layer: LayerGeometry,
    roles: set[str],
    cfg: PlannerConfig,
    stride: int = 1,
    min_length: float | None = None,
) -> list[FiberRoute]:
    routes: list[FiberRoute] = []
    accepted_by_role: dict[str, int] = {}
    stride = max(stride, 1)
    route_min_length = cfg.min_route_length if min_length is None else min_length
    for extrusion_path in layer.extrusion_paths:
        if extrusion_path.role not in roles:
            continue
        points = normalized_route_points(extrusion_path.points)
        length = polyline_length(points)
        if len(points) < 2 or length < route_min_length:
            continue
        warnings = route_warnings_for_path(points, cfg)
        accepted_index = accepted_by_role.get(extrusion_path.role, 0)
        accepted_by_role[extrusion_path.role] = accepted_index + 1
        if accepted_index % stride != 0:
            continue
        routes.append(
            FiberRoute(
                layer_index=layer.index,
                z=layer.z,
                kind=TRACE_KIND_BY_ROLE.get(extrusion_path.role, "polymer_trace"),
                angle=None,
                points=points,
                source_role=extrusion_path.role,
                warnings=warnings,
            )
        )
    return routes


def clipped_infill_routes(layer: LayerGeometry, polygon: Polygon, cfg: PlannerConfig) -> list[FiberRoute]:
    routes: list[FiberRoute] = []
    infill_parts = polygon_parts(polygon.buffer(-cfg.infill_inset, join_style=1))
    if not infill_parts:
        return routes
    infill_area = infill_parts[0] if len(infill_parts) == 1 else MultiPolygon(infill_parts)
    minx, miny, maxx, maxy = infill_area.bounds
    diagonal = math.hypot(maxx - minx, maxy - miny) + cfg.infill_spacing * 4.0
    origin = ((minx + maxx) / 2.0, (miny + maxy) / 2.0)

    layer_angles = cfg.angles
    if cfg.pattern.strip().lower() == "solid" and len(cfg.angles) > 1:
        layer_angles = [cfg.angles[layer.index % len(cfg.angles)]]

    for angle in layer_angles:
        radians = math.radians(angle)
        direction = (math.cos(radians), math.sin(radians))
        normal = (-direction[1], direction[0])
        projections = [
            corner[0] * normal[0] + corner[1] * normal[1]
            for corner in ((minx, miny), (minx, maxy), (maxx, miny), (maxx, maxy))
        ]
        start_projection = math.floor(min(projections) / cfg.infill_spacing) * cfg.infill_spacing
        end_projection = math.ceil(max(projections) / cfg.infill_spacing) * cfg.infill_spacing
        index = 0
        projection = start_projection
        while projection <= end_projection + EPSILON:
            origin_projection = origin[0] * normal[0] + origin[1] * normal[1]
            offset = projection - origin_projection
            center = (origin[0] + normal[0] * offset, origin[1] + normal[1] * offset)
            line = LineString(
                [
                    (center[0] - direction[0] * diagonal, center[1] - direction[1] * diagonal),
                    (center[0] + direction[0] * diagonal, center[1] + direction[1] * diagonal),
                ]
            )
            clipped = line.intersection(infill_area)
            for segment in geometry_segments(clipped):
                coords = normalized_route_points([(float(x), float(y)) for x, y in segment.coords])
                length = polyline_length(coords)
                if len(coords) < 2 or length < cfg.min_route_length:
                    continue
                if (index + layer.index) % 2:
                    coords.reverse()
                routes.append(
                    FiberRoute(
                        layer_index=layer.index,
                        z=layer.z,
                        kind="infill_chord",
                        angle=angle,
                        points=coords,
                        source_role="generated_infill",
                        warnings=route_warnings_for_path(coords, cfg),
                    )
                )
                index += 1
            projection += cfg.infill_spacing
    return sorted(routes, key=lambda route: route.length, reverse=True)


def selected_layer_indexes(layers: Sequence[LayerGeometry], cfg: PlannerConfig) -> set[int]:
    if cfg.macro_layer_height <= EPSILON:
        return {
            layer.index
            for layer in layers
            if cfg.layer_step <= 1 or layer.index % cfg.layer_step == 0
        }
    if not layers:
        return set()

    z_layers = sorted((layer.z, layer.index) for layer in layers)
    if len(z_layers) <= 1:
        return {z_layers[0][1]}

    first_z = z_layers[0][0]
    last_z = z_layers[-1][0]
    selected: set[int] = set()
    cursor = 0
    target_z = first_z
    while target_z <= last_z + cfg.macro_layer_height * 0.5 + EPSILON:
        while cursor + 1 < len(z_layers) and z_layers[cursor + 1][0] <= target_z:
            cursor += 1
        candidates = [z_layers[cursor]]
        if cursor + 1 < len(z_layers):
            candidates.append(z_layers[cursor + 1])
        _, selected_index = min(candidates, key=lambda item: (abs(item[0] - target_z), item[1]))
        selected.add(selected_index)
        target_z += cfg.macro_layer_height
    return selected


def plan_routes(parsed: ParsedGCode, cfg: PlannerConfig) -> tuple[list[FiberRoute], dict[str, int]]:
    routes: list[FiberRoute] = []
    skipped: dict[str, int] = {
        "layers_without_outer_polygon": 0,
        "layers_skipped_by_step": 0,
        "layers_skipped_by_macro_height": 0,
        "layers_skipped_by_start_guard": 0,
        "layers_skipped_by_top_guard": 0,
        "layers_skipped_by_layup_band": 0,
        "layers_without_hardware_printable_routes": 0,
        "routes_skipped_by_hardware_min_length": 0,
        "routes_skipped_by_cut_window_min_length": 0,
        "routes_capped": 0,
        "thin_feature_min_route_fallback_layers": 0,
        "short_perimeter_stitched_routes": 0,
        "hole_reinforcement_routes": 0,
        "hole_cluster_reinforcement_routes": 0,
        "hole_cluster_reinforcement_skipped": 0,
        "hole_reinforcement_expanded_orbit_skipped": 0,
        "hole_reinforcement_skipped_by_smoothing": 0,
        "hole_reinforcement_skipped_by_enclosing_loop": 0,
        "hole_reinforcement_skipped_by_hardware_min_length": 0,
        "hole_reinforcement_skipped_by_max_laps": 0,
        "hole_reinforcement_skipped_by_radius": 0,
        "hole_reinforcement_skipped_by_unprintable_path": 0,
        "internal_void_stitch_routes": 0,
        "internal_void_stitch_skipped": 0,
        "infill_requested_without_explicit_source_layers": 0,
        "infill_explicit_fallback_to_plastic_trace_layers": 0,
        "infill_explicit_fallback_to_generated_ribs_layers": 0,
    }
    base_selected_layers = selected_layer_indexes(parsed.layers, cfg)
    first_allowed_index = max(cfg.fiber_start_layer - 1, 0) if cfg.fiber_start_layer > 0 else 0
    top_guard_start = max(len(parsed.layers) - cfg.fiber_start_layer, first_allowed_index)
    next_phase = 0

    def filter_hardware_printable(layer_routes: Sequence[FiberRoute], route_cfg: PlannerConfig) -> list[FiberRoute]:
        kept: list[FiberRoute] = []
        minimum_hardware_length = hardware_min_route_length(route_cfg)
        minimum_standalone_length = standalone_cuttable_min_route_length(route_cfg)
        for route in layer_routes:
            if route.length + EPSILON < minimum_hardware_length:
                skipped["routes_skipped_by_hardware_min_length"] += 1
                continue
            if route.length + EPSILON < minimum_standalone_length:
                extended_route = extend_closed_route_to_min_length(
                    route,
                    minimum_standalone_length,
                    "cut_window_extended_closed_route",
                )
                if extended_route is None:
                    skipped["routes_skipped_by_cut_window_min_length"] += 1
                    continue
                route = extended_route
            kept.append(route)
        return kept

    def routes_for_layer(layer: LayerGeometry, polygons: Sequence[Polygon], route_cfg: PlannerConfig) -> list[FiberRoute]:
        layer_routes: list[FiberRoute] = []
        perimeter_trace_routes: list[FiberRoute] = []
        infill_trace_routes: list[FiberRoute] = []
        part_center = layer_part_center(polygons)
        if route_cfg.generate_perimeters:
            perimeter_trace_candidates = traced_path_routes(
                layer,
                PERIMETER_TRACE_ROLES,
                route_cfg,
                min_length=route_cfg.perimeter_min_route_length,
            )
            stitched_perimeter_routes = stitched_short_perimeter_routes(
                layer,
                perimeter_trace_candidates,
                polygons,
                route_cfg,
            )
            if stitched_perimeter_routes:
                skipped["short_perimeter_stitched_routes"] += len(stitched_perimeter_routes)
            perimeter_trace_candidates = sorted(
                perimeter_trace_candidates + stitched_perimeter_routes,
                key=lambda route: route.length,
                reverse=True,
            )
            perimeter_trace_routes = select_spatially_phased_routes(
                perimeter_trace_candidates,
                route_cfg.perimeter_routes_per_layer,
                route_cfg,
                part_center,
                "perimeter_trace",
            )
            layer_routes.extend(perimeter_trace_routes)
            layer_routes.extend(traced_hole_reinforcement_routes(layer, polygons, route_cfg, skipped, part_center))
            for polygon in polygons[:1]:
                layer_routes.extend(hole_reinforcement_routes(layer, polygon, route_cfg, skipped, part_center))
        if route_cfg.generate_infill:
            if route_cfg.infill_source_policy == "generated-ribs":
                for polygon in polygons[:1]:
                    infill_trace_routes.extend(clipped_infill_routes(layer, polygon, route_cfg))
            elif route_cfg.infill_source_policy == "plastic-traces":
                infill_trace_routes = traced_path_routes(
                    layer,
                    INFILL_TRACE_ROLES,
                    route_cfg,
                    stride=route_cfg.infill_trace_stride,
                )
            else:
                infill_trace_routes = traced_path_routes(
                    layer,
                    EXPLICIT_FIBER_INFILL_TRACE_ROLES,
                    route_cfg,
                    stride=route_cfg.infill_trace_stride,
                )
                if not infill_trace_routes:
                    skipped["infill_requested_without_explicit_source_layers"] += 1
                    infill_trace_routes = traced_path_routes(
                        layer,
                        INFILL_TRACE_ROLES,
                        route_cfg,
                        stride=route_cfg.infill_trace_stride,
                    )
                    if infill_trace_routes:
                        skipped["infill_explicit_fallback_to_plastic_trace_layers"] += 1
                        for route in infill_trace_routes:
                            route.warnings.append("explicit_fiber_infill_missing_used_plastic_traces")
                    else:
                        for polygon in polygons[:1]:
                            infill_trace_routes.extend(clipped_infill_routes(layer, polygon, route_cfg))
                        if infill_trace_routes:
                            skipped["infill_explicit_fallback_to_generated_ribs_layers"] += 1
                            for route in infill_trace_routes:
                                route.warnings.append("explicit_fiber_infill_missing_used_generated_ribs")
            infill_trace_routes = select_longest_routes(infill_trace_routes, route_cfg.infill_routes_per_layer)
            layer_routes.extend(infill_trace_routes)
        for polygon in polygons[:1]:
            if route_cfg.generate_perimeters and not perimeter_trace_routes:
                fallback_perimeters = sorted(perimeter_routes(layer, polygon, route_cfg), key=lambda route: route.length, reverse=True)
                layer_routes.extend(
                    select_spatially_phased_routes(
                        fallback_perimeters,
                        route_cfg.perimeter_routes_per_layer,
                        route_cfg,
                        part_center,
                        "perimeter_trace",
                    )
                )
        layer_routes.sort(key=lambda route: (ROUTE_PRIORITY.get(route.kind, 99), -route.length))
        return apply_fiber_seam_placement(layer_routes, route_cfg)

    for layer in parsed.layers:
        if cfg.fiber_start_layer > 0 and layer.index < first_allowed_index:
            skipped["layers_skipped_by_start_guard"] += 1
            continue
        if cfg.fiber_start_layer > 0 and layer.index >= top_guard_start:
            skipped["layers_skipped_by_top_guard"] += 1
            continue
        layer_base_cfg, layup_enabled = config_for_layup_band(layer, cfg)
        if not layup_enabled:
            skipped["layers_skipped_by_layup_band"] += 1
            continue
        layer_selected = selected_layer_indexes(parsed.layers, layer_base_cfg) if cfg.layup_bands else base_selected_layers
        if layer.index not in layer_selected:
            if layer_base_cfg.macro_layer_height > EPSILON:
                skipped["layers_skipped_by_macro_height"] += 1
            else:
                skipped["layers_skipped_by_step"] += 1
            continue
        polygons = closed_outer_polygons(layer)
        if not polygons:
            skipped["layers_without_outer_polygon"] += 1
            continue
        layer_phase = next_phase
        next_phase += 1
        route_cfg = replace(layer_base_cfg, fiber_path_phase=layer_phase)
        layer_routes = routes_for_layer(layer, polygons, route_cfg)
        layer_routes = filter_hardware_printable(layer_routes, route_cfg)
        if not layer_routes and (route_cfg.generate_perimeters or route_cfg.generate_infill):
            for fallback_min_length in route_cfg.thin_feature_min_route_lengths:
                if fallback_min_length >= route_cfg.min_route_length - EPSILON:
                    continue
                fallback_cfg = replace(route_cfg, min_route_length=fallback_min_length, fiber_path_phase=layer_phase)
                layer_routes = routes_for_layer(layer, polygons, fallback_cfg)
                layer_routes = filter_hardware_printable(layer_routes, fallback_cfg)
                if layer_routes:
                    skipped["thin_feature_min_route_fallback_layers"] += 1
                    warning = f"thin_feature_min_route_fallback_to_{fmt_float(fallback_min_length, 1)}mm"
                    for route in layer_routes:
                        route.warnings.append(warning)
                    break
        if not layer_routes and (route_cfg.generate_perimeters or route_cfg.generate_infill):
            skipped["layers_without_hardware_printable_routes"] += 1
        if route_cfg.layup_band_name:
            band_warning = f"layup_band_{safe_warning_name(route_cfg.layup_band_name)}"
            for route in layer_routes:
                append_warning_once(route, band_warning)
        if len(layer_routes) > route_cfg.max_routes_per_layer:
            skipped["routes_capped"] += len(layer_routes) - route_cfg.max_routes_per_layer
            layer_routes = layer_routes[: route_cfg.max_routes_per_layer]
        routes.extend(layer_routes)
    return routes, skipped


def point_at_distance(points: Sequence[tuple[float, float]], target_distance: float) -> tuple[float, float]:
    if not points:
        return (0.0, 0.0)
    if target_distance <= 0:
        return points[0]
    walked = 0.0
    for start, end in zip(points, points[1:]):
        segment_length = distance(start, end)
        if walked + segment_length >= target_distance:
            ratio = (target_distance - walked) / segment_length if segment_length > EPSILON else 0.0
            return (start[0] + (end[0] - start[0]) * ratio, start[1] + (end[1] - start[1]) * ratio)
        walked += segment_length
    return points[-1]


def emit_cut_gcode(lines: list[str], cfg: PlannerConfig) -> None:
    lines.append("; Start to cut")
    for command in cfg.cut_gcode:
        lines.append(command)


def route_approach_feedrate(cfg: PlannerConfig) -> float:
    if cfg.correction_move_feedrate_percent > EPSILON:
        return max(cfg.fiber_feedrate * cfg.correction_move_feedrate_percent / 100.0, 1.0)
    if cfg.correction_move_feedrate > EPSILON:
        return cfg.correction_move_feedrate
    return cfg.travel_feedrate


def emit_path_moves(lines: list[str], route: FiberRoute, cfg: PlannerConfig, emit_cut: bool = True) -> None:
    points = route.points
    total_length = route.length
    cut_at = max(total_length - cfg.cut_distance, 0.0)
    cut_emitted = not emit_cut
    walked = 0.0

    def emit_move(target: tuple[float, float], segment_length: float) -> None:
        if segment_length <= EPSILON:
            return
        after_cut = cut_emitted and walked >= cut_at - EPSILON
        if after_cut:
            feed = cfg.fiber_cut_tail_feedrate
        else:
            feed = cfg.fiber_slow_feedrate if walked < cfg.slow_length else cfg.fiber_feedrate
        v_multiplier = cfg.after_cut_plastic_extrusion_multiplier if after_cut else 1.0
        v_value = segment_length * cfg.fiber_v_per_mm * v_multiplier
        lines.append(f";VG1 {fmt_axis('X', target[0])} {fmt_axis('Y', target[1])} E{fmt_float(segment_length, 5)} F{fmt_float(feed, 0)}")
        command = f"G1 {fmt_axis('X', target[0])} {fmt_axis('Y', target[1])} V{fmt_float(v_value, 5)}"
        if not after_cut:
            command += f" U{fmt_float(segment_length, 5)} P{fmt_float(cfg.fiber_p_value, 5)}"
        command += f" F{fmt_float(feed, 0)}"
        lines.append(command)

    for start, end in zip(points, points[1:]):
        segment_length = distance(start, end)
        if segment_length <= EPSILON:
            continue
        if not cut_emitted and cut_at > walked + EPSILON and cut_at < walked + segment_length - EPSILON:
            mid = point_at_distance(points, cut_at)
            first_length = distance(start, mid)
            emit_move(mid, first_length)
            walked += first_length
            emit_cut_gcode(lines, cfg)
            cut_emitted = True
            second_length = distance(mid, end)
            emit_move(end, second_length)
            walked += second_length
            continue
        if not cut_emitted and cut_at <= walked + EPSILON:
            emit_cut_gcode(lines, cfg)
            cut_emitted = True
        emit_move(end, segment_length)
        walked += segment_length

    if not cut_emitted:
        emit_cut_gcode(lines, cfg)


def emit_route(
    route: FiberRoute,
    cfg: PlannerConfig,
    *,
    start_group: bool = True,
    end_group: bool = True,
    emit_cut: bool = True,
) -> list[str]:
    if len(route.points) < 2:
        return []
    start = route.points[0]
    estimated_load = math.ceil(route.length + cfg.cut_distance)
    warning_text = ",".join(route.warnings) if route.warnings else "none"
    lines = [
        f"; ORCA_CODEX_FIBER_ROUTE layer={route.layer_index} z={fmt_float(route.z)} "
        f"kind={route.kind} length={fmt_float(route.length, 3)} warnings={warning_text}",
        ";TYPE:Custom",
        f";WIDTH:{fmt_float(cfg.fiber_width, 3)}",
        ";HEIGHT:0.2",
        f"G0 {fmt_axis('X', start[0])} {fmt_axis('Y', start[1])} F{fmt_float(route_approach_feedrate(cfg), 0)}",
        f"G0 {fmt_axis('Z', route.z)} F{fmt_float(cfg.z_feedrate, 0)}",
    ]
    if start_group:
        lines.extend(
            [
                f"M1001 L{estimated_load}",
                f"G1 F{fmt_float(cfg.restart_feedrate, 0)} U{fmt_float(cfg.restart_length, 3)} ; Extrude restart",
                f"G1 F{fmt_float(cfg.priming_feedrate, 0)} V{fmt_float(cfg.start_length * cfg.fiber_v_per_mm, 5)} ; Extrude restart",
                "G4 P0",
            ]
        )
    lines.append(f"; SEAM Fiber at X{fmt_float(start[0])} Y{fmt_float(start[1])} Z{fmt_float(route.z)}")
    emit_path_moves(lines, route, cfg, emit_cut=emit_cut)
    if end_group:
        lines.extend(
            [
                "; Cutting completed.",
                f"G1 F{fmt_float(cfg.priming_feedrate, 0)} V-1 ; Retract",
                "M1002",
            ]
        )
    return lines


def emit_layer_routes(layer_routes: Sequence[FiberRoute], cfg: PlannerConfig) -> list[str]:
    lines: list[str] = []
    group_size = max(cfg.routes_per_cut, 1)
    for start_index in range(0, len(layer_routes), group_size):
        group = layer_routes[start_index : start_index + group_size]
        for route_index, route in enumerate(group):
            lines.extend(
                emit_route(
                    route,
                    cfg,
                    start_group=route_index == 0,
                    end_group=route_index == len(group) - 1,
                    emit_cut=route_index == 0,
                )
            )
    return lines


def fmt_temp(value: float) -> str:
    return fmt_float(value, 0)


def emit_fiberseek_start_contract(parsed: ParsedGCode, cfg: PlannerConfig) -> list[str]:
    lines = [
        "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_START",
        f"SET_PRINT_STATS_INFO TOTAL_LAYER={len(parsed.layers)}",
        "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1",
        f"M104 S{fmt_temp(cfg.fiber_nozzle_temperature)} T0",
        f"M140 S{fmt_temp(cfg.bed_temperature)}",
        f"M141 S{fmt_temp(cfg.chamber_temperature)}",
    ]
    lines.append("; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_END")
    return lines


def normalize_polymer_start_line(raw_line: str, cfg: PlannerConfig, before_first_layer: bool) -> list[str]:
    stripped = raw_line.strip()
    if not before_first_layer:
        return [raw_line]
    if re.match(r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?!.*\bT\d+)", stripped, flags=re.IGNORECASE):
        return [f"M104 S{fmt_temp(cfg.plastic_nozzle_temperature)} T1 ; set plastic nozzle temperature"]
    if stripped == "T0":
        return [
            "; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL",
            cfg.plastic_tool_command,
            f"M109 S{fmt_temp(cfg.plastic_nozzle_temperature)} T1",
            "M106 P1 S0",
        ]
    if stripped.startswith("M141 ") or stripped.startswith("M191 "):
        return []
    if stripped.startswith("M190 "):
        return [raw_line, f"M191 S{fmt_temp(cfg.chamber_temperature)}"]
    return [raw_line]


def fiber_tool_select_command(cfg: PlannerConfig, reset_feeder: bool = False) -> str:
    if not reset_feeder:
        return cfg.fiber_tool_command
    tool = cfg.fiber_tool_command.split(";", 1)[0].strip() or "T0"
    return f"{tool} R ; switch extruder type to:FIBER"


def emit_change_to_fiber(cfg: PlannerConfig, z: float, reset_feeder: bool = False) -> list[str]:
    safe_z = max(z + cfg.toolchange_z_lift, cfg.toolchange_z_lift)
    return [
        "; Start change extruder",
        "M400",
        f"M104 S{fmt_temp(cfg.fiber_nozzle_temperature)} T0",
        "G1 F1800 E-15 ; Retract",
        f"G0 Z{fmt_float(safe_z)} F{fmt_float(cfg.z_feedrate, 0)}",
        f"M104 S{fmt_temp(cfg.plastic_standby_temperature)} T1",
        f"M106 P1 S{cfg.fiber_transition_fan_speed}",
        "MOVE_TO_BRUSH_STATION",
        "CLEAN_NOZZLE",
        "MOVE_OUT_BRUSH_STATION",
        fiber_tool_select_command(cfg, reset_feeder=reset_feeder),
        f"M106 P2 S{cfg.active_tool_fan_speed}",
        f"M109 S{fmt_temp(cfg.fiber_nozzle_temperature)} T0",
        "M106 P1 S0",
        "; End change extruder",
        f"M106 P2 S{cfg.fiber_laydown_fan_speed}",
    ]


def emit_fiber_prime_line(cfg: PlannerConfig) -> list[str]:
    line_length = max(cfg.fiber_prime_line_length, cfg.cut_distance + 1.0)
    start_x = cfg.fiber_prime_line_center_x - (line_length / 2.0)
    end_x = start_x + line_length
    approach_x = start_x - 1.0
    y = cfg.fiber_prime_line_y
    line_z = cfg.fiber_prime_line_height
    travel_z = max(cfg.fiber_prime_travel_z, line_z + 0.2)
    cut_at = max(line_length - cfg.cut_distance, 0.0)
    first_segment = max(cut_at, 0.0)
    second_segment = max(line_length - first_segment, 0.0)

    lines = [
        "; ORCA_CODEX_FIBER_PRIME_START",
        ";TYPE:Custom",
        f";WIDTH:{fmt_float(cfg.fiber_width, 3)}",
        f";HEIGHT:{fmt_float(line_z, 3)}",
        f"G0 Z{fmt_float(travel_z)} F{fmt_float(cfg.z_feedrate, 0)}",
        f"G0 X{fmt_float(approach_x)} Y{fmt_float(y)} F{fmt_float(cfg.travel_feedrate, 0)}",
        f"M1001 L{math.ceil(line_length)}",
        f"G1 F{fmt_float(cfg.restart_feedrate, 0)} U{fmt_float(min(cfg.restart_length, 55.0), 3)} ; Extrude restart",
        f"G0 X{fmt_float(start_x)} Z{fmt_float(line_z)} F{fmt_float(cfg.travel_feedrate, 0)}",
        f"G1 F720 V{fmt_float(cfg.start_length, 3)} ; Extrude restart",
        f"G4 P{cfg.fiber_prime_dwell_ms}",
    ]

    def emit_prime_segment(target_x: float, length: float, feedrate: float, feed_fiber: bool = True) -> None:
        if length <= EPSILON:
            return
        v_multiplier = 1.0 if feed_fiber else cfg.after_cut_plastic_extrusion_multiplier
        command = f"G1 X{fmt_float(target_x)} V{fmt_float(length * cfg.fiber_v_per_mm * v_multiplier, 5)}"
        if feed_fiber:
            command += f" U{fmt_float(length, 5)} P{fmt_float(cfg.fiber_p_value, 5)}"
        command += f" F{fmt_float(feedrate, 0)}"
        lines.append(command)

    if first_segment <= EPSILON:
        emit_cut_gcode(lines, cfg)
        emit_prime_segment(end_x, second_segment, cfg.fiber_cut_tail_feedrate, feed_fiber=False)
    else:
        emit_prime_segment(start_x + first_segment, first_segment, cfg.fiber_slow_feedrate)
        emit_cut_gcode(lines, cfg)
        emit_prime_segment(end_x, second_segment, cfg.fiber_cut_tail_feedrate, feed_fiber=False)

    lines.extend(
        [
            "; Cutting completed.",
            f"G1 F{fmt_float(cfg.priming_feedrate, 0)} V-1 ; Retract",
            f"G0 X{fmt_float(max(start_x, end_x - 1.2))} F{fmt_float(cfg.priming_feedrate, 0)}",
            "M1002",
            "; ORCA_CODEX_FIBER_PRIME_END",
        ]
    )
    return lines


def emit_change_to_plastic(cfg: PlannerConfig, z: float) -> list[str]:
    safe_z = max(z + cfg.toolchange_z_lift, cfg.toolchange_z_lift)
    return [
        "; Start change extruder",
        "M400",
        f"M104 S{fmt_temp(cfg.plastic_nozzle_temperature)} T1",
        "G1 F600 V-14 ; Retract",
        f"G0 Z{fmt_float(safe_z)} F{fmt_float(cfg.z_feedrate, 0)}",
        cfg.plastic_tool_command,
        f"M106 P1 S{cfg.active_tool_fan_speed}",
        "MOVE_TO_BRUSH_STATION",
        f"M109 S{fmt_temp(cfg.plastic_nozzle_temperature)} T1",
        "CLEAN_NOZZLE",
        "MOVE_OUT_BRUSH_STATION",
        f"M104 S{fmt_temp(cfg.fiber_standby_temperature)} T0",
        "M106 P2 S0",
        "; End change extruder",
    ]


def emit_fiberseek_shutdown(cfg: PlannerConfig) -> list[str]:
    return [
        "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_START",
        "M400",
        "M104 S0 T1",
        "M104 S0 T0",
        "M106 P2 S0",
        "M140 S0",
        "M141 S0",
        "M400",
        "G90",
        "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_END",
    ]


def emit_fiber_block(
    routes: Sequence[FiberRoute],
    cfg: PlannerConfig,
    include_preamble: bool,
    include_footer: bool,
    managed_toolchanges: bool = False,
    prime_before_routes: bool = False,
) -> list[str]:
    lines: list[str] = []
    if not routes:
        return lines
    if include_preamble:
        summary = route_summary(routes)
        used_g = fiber_mass_g(summary["total_length_mm"], cfg)
        lines.extend(
            [
                "; ORCA_CODEX_NATIVE_FIBER_PLANNER_START",
                "; Generated with TinManX1 native FibreSeek planner",
                f"; generated_at = {datetime.now(timezone.utc).isoformat()}",
                f"; ORCA_CODEX_NATIVE_FIBER_INPUT source={cfg.input_source} mode={cfg.reinforcement_mode} perimeters={int(cfg.generate_perimeters)} infill={int(cfg.generate_infill)} pattern={cfg.pattern}",
                f"; fiber_reinforcement_mode = {cfg.reinforcement_mode}",
                f"; continuous_fiber_route_count = {summary['count']}",
                f"; continuous_fiber_layers = {summary['layers_with_routes']}",
                f"; continuous_fiber_used_mm = {fmt_float(summary['total_length_mm'], 3)}",
                f"; continuous_fiber_used_g = {fmt_float(used_g, 4)}",
                "G21",
                "G90",
                "M83 ; use relative distances for extrusion",
            ]
        )
    first_z = routes[0].z
    if managed_toolchanges:
        lines.extend(emit_change_to_fiber(cfg, first_z, reset_feeder=prime_before_routes))
    else:
        lines.append(fiber_tool_select_command(cfg, reset_feeder=prime_before_routes))
    if prime_before_routes and cfg.fiber_prime_enabled:
        lines.extend(emit_fiber_prime_line(cfg))
    last_layer: int | None = None
    current_layer_routes: list[FiberRoute] = []
    for route in routes:
        if last_layer != route.layer_index:
            if current_layer_routes:
                lines.extend(emit_layer_routes(current_layer_routes, cfg))
            lines.append(f"; ORCA_CODEX_FIBER_LAYER {route.layer_index} Z{fmt_float(route.z)}")
            current_layer_routes = []
            last_layer = route.layer_index
        current_layer_routes.append(route)
    if current_layer_routes:
        lines.extend(emit_layer_routes(current_layer_routes, cfg))
    if managed_toolchanges:
        lines.extend(emit_change_to_plastic(cfg, routes[-1].z))
    else:
        lines.append(cfg.plastic_tool_command)
    if include_footer:
        lines.append("; ORCA_CODEX_NATIVE_FIBER_PLANNER_END")
    return lines


def emit_fiber_only(routes: Sequence[FiberRoute], cfg: PlannerConfig) -> str:
    return "\n".join(
        emit_fiber_block(
            routes,
            cfg,
            include_preamble=True,
            include_footer=True,
            prime_before_routes=cfg.fiber_prime_enabled,
        )
    ) + "\n"


def metadata_value_replacements(cfg: PlannerConfig) -> dict[str, str]:
    start_max_speed = cfg.fiber_slow_feedrate / 60.0
    normal_max_speed = cfg.fiber_feedrate / 60.0
    finish_max_speed = cfg.fiber_finish_feedrate / 60.0
    min_speed = cfg.fiber_cut_tail_feedrate / 60.0
    return {
        "fiber_reinforcement_mode": cfg.reinforcement_mode,
        "fiber_after_cut_plastic_extrusion_multiplier": fmt_float(cfg.after_cut_plastic_extrusion_multiplier),
        "fiber_max_arc_segment_length": fmt_float(cfg.max_arc_segment_length),
        "fiber_slow_length": fmt_float(cfg.slow_length),
        "fiber_min_route_length": fmt_float(cfg.min_route_length),
        "fiber_mechanical_min_route_length": fmt_float(cfg.mechanical_min_route_length),
        "fiber_perimeter_min_route_length": fmt_float(cfg.perimeter_min_route_length),
        "fiber_start_layer": str(max(1, cfg.fiber_start_layer)),
        "fiber_layer_step": str(max(1, cfg.layer_step)),
        "fiber_nozzle_temperature_standby": (
            f"{fmt_temp(cfg.plastic_standby_temperature)},{fmt_temp(cfg.fiber_standby_temperature)}"
        ),
        "fiber_start_max_speed": fmt_float(start_max_speed),
        "fiber_start_min_speed": fmt_float(min_speed),
        "fiber_start_min_limit_speed": fmt_float(min_speed),
        "fiber_normal_max_speed": fmt_float(normal_max_speed),
        "fiber_normal_min_speed": fmt_float(start_max_speed),
        "fiber_normal_min_limit_speed": fmt_float(min_speed),
        "fiber_finish_max_speed": fmt_float(finish_max_speed),
        "fiber_finish_min_speed": fmt_float(start_max_speed),
        "fiber_finish_min_limit_speed": fmt_float(min_speed),
    }


def normalize_metadata_line(raw_line: str, cfg: PlannerConfig) -> str:
    match = re.match(r"^(\s*;\s*)([A-Za-z0-9_]+)(\s*=\s*)(.*)$", raw_line)
    if not match:
        return raw_line
    replacements = metadata_value_replacements(cfg)
    key = match.group(2)
    if key not in replacements:
        return raw_line
    return f"{match.group(1)}{key}{match.group(3)}{replacements[key]}"


def emit_append_after_layer(parsed: ParsedGCode, routes: Sequence[FiberRoute], cfg: PlannerConfig) -> str:
    by_layer: dict[int, list[FiberRoute]] = {}
    for route in routes:
        by_layer.setdefault(route.layer_index, []).append(route)

    summary = route_summary(routes)
    used_g = fiber_mass_g(summary["total_length_mm"], cfg)
    output: list[str] = [
        "; ORCA_CODEX_NATIVE_FIBER_PLANNER_MERGED",
        "; Experimental merged output. Validate tool ownership before live printing.",
        f"; ORCA_CODEX_NATIVE_FIBER_INPUT source={cfg.input_source} mode={cfg.reinforcement_mode} perimeters={int(cfg.generate_perimeters)} infill={int(cfg.generate_infill)} pattern={cfg.pattern}",
        f"; fiber_reinforcement_mode = {cfg.reinforcement_mode}",
        f"; continuous_fiber_route_count = {summary['count']}",
        f"; continuous_fiber_layers = {summary['layers_with_routes']}",
        f"; continuous_fiber_used_mm = {fmt_float(summary['total_length_mm'], 3)}",
        f"; continuous_fiber_used_g = {fmt_float(used_g, 4)}",
    ]
    output.extend(emit_fiberseek_start_contract(parsed, cfg))
    current_layer: int | None = None
    inserted_header = False
    fiber_prime_inserted = False
    flushed_layers: set[int] = set()
    footer_inserted = False
    shutdown_inserted = False
    has_current_layer_stats = any(
        re.match(r"^\s*SET_PRINT_STATS_INFO\s+CURRENT_LAYER=", raw_line, flags=re.IGNORECASE)
        for raw_line in parsed.lines
    )
    pending_layer_stats: str | None = None
    auxiliary_fans_off_inserted = False
    auxiliary_fans_full_inserted = False

    end_insert_index = len(parsed.lines)
    for index, raw_line in enumerate(parsed.lines):
        if raw_line.strip() == "; filament end gcode":
            end_insert_index = index
            if index >= 1 and parsed.lines[index - 1].strip() == ";TYPE:Custom":
                end_insert_index = index - 1
            if end_insert_index >= 1 and parsed.lines[end_insert_index - 1].strip() == "M106 S0":
                end_insert_index -= 1
            break
        if raw_line.strip() == "; EXECUTABLE_BLOCK_END":
            end_insert_index = index
            break

    def flush_layer(layer_index: int | None) -> None:
        nonlocal inserted_header, footer_inserted, fiber_prime_inserted
        if layer_index is None or layer_index not in by_layer or layer_index in flushed_layers:
            return
        if not inserted_header:
            output.extend(
                [
                    "; ORCA_CODEX_NATIVE_FIBER_PLANNER_START",
                    "; Generated with TinManX1 native FibreSeek planner",
                    f"; generated_at = {datetime.now(timezone.utc).isoformat()}",
                    "G21",
                    "G90",
                    "M83 ; use relative distances for extrusion",
                ]
            )
            inserted_header = True
        prime_before_routes = cfg.fiber_prime_enabled and not fiber_prime_inserted
        output.extend(
            emit_fiber_block(
                by_layer[layer_index],
                cfg,
                include_preamble=False,
                include_footer=False,
                managed_toolchanges=True,
                prime_before_routes=prime_before_routes,
            )
        )
        if prime_before_routes:
            fiber_prime_inserted = True
        flushed_layers.add(layer_index)

    def maybe_insert_footer() -> None:
        nonlocal footer_inserted
        if inserted_header and not footer_inserted:
            output.append("; ORCA_CODEX_NATIVE_FIBER_PLANNER_END")
            footer_inserted = True

    def maybe_insert_fiberseek_layer_fans(raw_line: str) -> None:
        nonlocal auxiliary_fans_off_inserted, auxiliary_fans_full_inserted
        match = re.match(r"^\s*SET_PRINT_STATS_INFO\s+CURRENT_LAYER=(\d+)\b", raw_line, flags=re.IGNORECASE)
        if not match:
            return
        layer_number = int(match.group(1))
        if layer_number <= 1 and not auxiliary_fans_off_inserted:
            output.extend(["M106 P3 S0", "M106 P5 S0"])
            auxiliary_fans_off_inserted = True
        if layer_number >= 5 and not auxiliary_fans_full_inserted:
            output.extend(["M106 P3 S255", "M106 P5 S255"])
            auxiliary_fans_full_inserted = True

    for line_index, raw_line in enumerate(parsed.lines):
        if line_index == end_insert_index:
            flush_layer(current_layer)
            maybe_insert_footer()
        if raw_line.startswith(";LAYER_CHANGE"):
            flush_layer(current_layer)
            current_layer = (current_layer + 1) if current_layer is not None else 0
            if not has_current_layer_stats:
                pending_layer_stats = f"SET_PRINT_STATS_INFO CURRENT_LAYER={current_layer + 1}"
        if raw_line.strip() == "; EXECUTABLE_BLOCK_END" and inserted_header and not shutdown_inserted:
            output.extend(emit_fiberseek_shutdown(cfg))
            shutdown_inserted = True
        metadata_line = normalize_metadata_line(raw_line, cfg)
        for normalized_line in normalize_polymer_start_line(metadata_line, cfg, current_layer is None):
            output.append(normalized_line)
            maybe_insert_fiberseek_layer_fans(normalized_line)
        if pending_layer_stats is not None:
            output.append(pending_layer_stats)
            maybe_insert_fiberseek_layer_fans(pending_layer_stats)
            pending_layer_stats = None
    flush_layer(current_layer)
    maybe_insert_footer()
    if inserted_header and not shutdown_inserted:
        output.extend(emit_fiberseek_shutdown(cfg))
    return "\n".join(output) + "\n"


def command_counts(gcode: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for raw_line in gcode.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";"):
            continue
        command = line.split(None, 1)[0]
        counts[command] = counts.get(command, 0) + 1
    return dict(sorted(counts.items()))


def route_summary(routes: Sequence[FiberRoute]) -> dict:
    by_kind: dict[str, int] = {}
    warning_counts: dict[str, int] = {}
    by_layer: dict[int, int] = {}
    total_length = 0.0
    for route in routes:
        by_kind[route.kind] = by_kind.get(route.kind, 0) + 1
        by_layer[route.layer_index] = by_layer.get(route.layer_index, 0) + 1
        total_length += route.length
        for warning in route.warnings:
            warning_counts[warning] = warning_counts.get(warning, 0) + 1
    return {
        "count": len(routes),
        "by_kind": dict(sorted(by_kind.items())),
        "layers_with_routes": len(by_layer),
        "total_length_mm": round(total_length, 3),
        "warning_counts": dict(sorted(warning_counts.items())),
        "max_routes_on_layer": max(by_layer.values()) if by_layer else 0,
    }


def fiber_mass_g(total_length_mm: float, cfg: PlannerConfig) -> float:
    if cfg.fiber_linear_density <= EPSILON:
        return 0.0
    return total_length_mm * cfg.fiber_linear_density / 1_000_000.0


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def main() -> int:
    args = parse_args()
    source = args.in_gcode.expanduser().resolve()
    if not source.exists():
        raise SystemExit(f"Input G-code does not exist: {source}")

    parsed = parse_gcode(source)
    cfg = planner_config(parsed, args)
    routes, skipped = plan_routes(parsed, cfg)

    if args.emit_mode == "append-after-layer":
        gcode = emit_append_after_layer(parsed, routes, cfg)
    else:
        gcode = emit_fiber_only(routes, cfg)

    output = args.out.expanduser().resolve()
    write_text_atomic(output, gcode)

    routes_summary = route_summary(routes)
    routes_summary["total_mass_g"] = round(fiber_mass_g(routes_summary["total_length_mm"], cfg), 4)

    summary = {
        "planner": "orcaslicer_codex_native_fiber_planner",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_gcode": str(source),
        "output": str(output),
        "emit_mode": args.emit_mode,
        "parsed": {
            "line_count": len(parsed.lines),
            "layer_count": len(parsed.layers),
            "extrusion_path_count": sum(len(layer.extrusion_paths) for layer in parsed.layers),
            "fiber_profile_keys": sorted(key for key in parsed.config_comments if key.startswith("fiber_")),
        },
        "config": {
            "cut_distance": cfg.cut_distance,
            "restart_length": cfg.restart_length,
            "start_length": cfg.start_length,
            "slow_length": cfg.slow_length,
            "fiber_diameter": cfg.fiber_diameter,
            "fiber_linear_density": cfg.fiber_linear_density,
            "fiber_p_value": cfg.fiber_p_value,
            "fiber_v_per_mm": cfg.fiber_v_per_mm,
            "min_radius": cfg.min_radius,
            "max_arc_segment_length": cfg.max_arc_segment_length,
            "min_route_length": cfg.min_route_length,
            "mechanical_min_route_length": cfg.mechanical_min_route_length,
            "hardware_min_route_length": hardware_min_route_length(cfg),
            "standalone_cuttable_min_route_length": standalone_cuttable_min_route_length(cfg),
            "perimeter_min_route_length": cfg.perimeter_min_route_length,
            "thin_feature_min_route_lengths": cfg.thin_feature_min_route_lengths,
            "start_length": cfg.start_length,
            "fiber_width": cfg.fiber_width,
            "fiber_feedrate": cfg.fiber_feedrate,
            "fiber_slow_feedrate": cfg.fiber_slow_feedrate,
            "fiber_finish_feedrate": cfg.fiber_finish_feedrate,
            "fiber_cut_tail_feedrate": cfg.fiber_cut_tail_feedrate,
            "feedrate_percent": cfg.feedrate_percent,
            "tension_length": cfg.tension_length,
            "tension_feedrate": cfg.tension_feedrate,
            "tension_release_fraction": cfg.tension_release_fraction,
            "correction_move_feedrate": cfg.correction_move_feedrate,
            "correction_move_feedrate_percent": cfg.correction_move_feedrate_percent,
            "after_cut_plastic_extrusion_multiplier": cfg.after_cut_plastic_extrusion_multiplier,
            "plastic_nozzle_temperature": cfg.plastic_nozzle_temperature,
            "fiber_nozzle_temperature": cfg.fiber_nozzle_temperature,
            "plastic_standby_temperature": cfg.plastic_standby_temperature,
            "fiber_standby_temperature": cfg.fiber_standby_temperature,
            "bed_temperature": cfg.bed_temperature,
            "chamber_temperature": cfg.chamber_temperature,
            "infill_spacing": cfg.infill_spacing,
            "infill_density_percent": cfg.infill_density_percent,
            "perimeter_inset": cfg.perimeter_inset,
            "infill_inset": cfg.infill_inset,
            "generate_perimeters": cfg.generate_perimeters,
            "generate_infill": cfg.generate_infill,
            "infill_source_policy": cfg.infill_source_policy,
            "reinforcement_mode": cfg.reinforcement_mode,
            "pattern": cfg.pattern,
            "input_source": cfg.input_source,
            "angles": cfg.angles,
            "layup_band_count": len(cfg.layup_bands),
            "layup_band_names": [str(payload_value(band, "name", "label") or "") for band in cfg.layup_bands],
            "layup_payload_warnings": cfg.layup_payload_warnings,
            "layer_step": cfg.layer_step,
            "macro_layer_height": cfg.macro_layer_height,
            "infill_trace_stride": cfg.infill_trace_stride,
            "perimeter_routes_per_layer": cfg.perimeter_routes_per_layer,
            "hole_reinforcement_routes_per_layer": cfg.hole_reinforcement_routes_per_layer,
            "hole_reinforcement_max_laps": cfg.hole_reinforcement_max_laps,
            "infill_routes_per_layer": cfg.infill_routes_per_layer,
            "fiber_start_layer": cfg.fiber_start_layer,
            "fiber_first_allowed_layer_index": max(cfg.fiber_start_layer - 1, 0) if cfg.fiber_start_layer > 0 else 0,
            "fiber_top_guard_layers": cfg.fiber_start_layer,
            "max_routes_per_layer": cfg.max_routes_per_layer,
            "routes_per_cut": cfg.routes_per_cut,
        },
        "routes": routes_summary,
        "skipped": skipped,
        "gcode_size_bytes": len(gcode.encode("utf-8")),
        "line_count": gcode.count("\n"),
        "command_counts": command_counts(gcode),
        "safety": {
            "external_planner_dependency": False,
            "upload_or_start_print": False,
            "live_machine_side_effects": False,
            "experimental_merged_output": args.emit_mode == "append-after-layer",
        },
    }
    if args.summary_out:
        summary_path = args.summary_out.expanduser().resolve()
        write_text_atomic(summary_path, json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output), "routes": len(routes), "emit_mode": args.emit_mode}, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
