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
PERIMETER_TRACE_ROLES = {"Inner wall"}
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
    cut_distance: float = 60.0
    restart_length: float = 57.0
    start_length: float = 15.0
    slow_length: float = 5.0
    fiber_diameter: float = 0.25
    fiber_linear_density: float = 102.0
    fiber_p_value: float = 0.041
    fiber_v_per_mm: float = 0.041
    fiber_width: float = 0.80
    min_radius: float = 8.0
    max_arc_segment_length: float = 3.0
    mechanical_min_route_length: float = 90.0
    min_route_length: float = 10.0
    perimeter_min_route_length: float = 55.0
    thin_feature_min_route_lengths: list[float] = field(default_factory=lambda: [5.0, 2.0])
    infill_spacing: float = 4.0
    perimeter_inset: float = 0.85
    infill_inset: float = 1.20
    travel_feedrate: float = 30000.0
    z_feedrate: float = 600.0
    fiber_feedrate: float = 1800.0
    fiber_slow_feedrate: float = 300.0
    restart_feedrate: float = 1500.0
    priming_feedrate: float = 600.0
    tension_length: float = 0.0
    tension_feedrate: float = 0.0
    after_cut_plastic_extrusion_multiplier: float = 1.0
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
    perimeter_routes_per_layer: int = 4
    hole_reinforcement_routes_per_layer: int = 0
    hole_reinforcement_max_laps: int = 3
    hole_reinforcement_max_radius_factor: float = 2.3
    infill_routes_per_layer: int = 8
    max_routes_per_layer: int = 80
    routes_per_cut: int = 1
    fiber_start_layer: int = 0
    fiber_tool_command: str = "T0 ; switch extruder type to:FIBER"
    plastic_tool_command: str = "T1 ; switch extruder type to:PLASTIC"
    cut_gcode: list[str] = field(default_factory=lambda: ["M2800", "M400", ";CUT DISTANCE 56"])


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
        return ["M2800", "M400", f";CUT DISTANCE {fmt_float(max(cut_distance - 4.0, 0.0), 1)}"]
    expanded = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\r\n", "\n")
    commands = [line.strip() for line in expanded.splitlines() if line.strip()]
    return commands or ["M2800", "M400", f";CUT DISTANCE {fmt_float(max(cut_distance - 4.0, 0.0), 1)}"]


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


def angles_for_pattern(pattern: str, explicit: str | None) -> list[float]:
    if explicit:
        return [float(item.strip()) for item in explicit.split(",") if item.strip()]
    normalized = pattern.strip().lower()
    if normalized in {"isogrid", "triangular", "tetrahedral"}:
        return [0.0, 60.0, 120.0]
    if normalized in {"rhombic", "crosshatch", "grid"}:
        return [0.0, 90.0]
    if normalized in {"anisotropic", "load", "load-aligned"}:
        return [0.0]
    return [0.0, 90.0]


def planner_config(parsed: ParsedGCode, args: argparse.Namespace) -> PlannerConfig:
    comments = parsed.config_comments
    cfg = PlannerConfig()
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
    cfg.min_radius = parse_first_positive_float(comments.get("fiber_min_radius"), cfg.min_radius)
    cfg.mechanical_min_route_length = max(
        cfg.mechanical_min_route_length,
        parse_first_positive_float(
            comments.get("fiber_mechanical_min_route_length") or comments.get("fiber_hardware_min_route_length"),
            cfg.mechanical_min_route_length,
        ),
    )
    cfg.max_arc_segment_length = parse_first_positive_float(comments.get("fiber_max_arc_segment_length"), cfg.max_arc_segment_length)
    cfg.min_route_length = parse_first_positive_float(comments.get("fiber_min_route_length"), cfg.min_route_length)
    cfg.perimeter_min_route_length = parse_first_positive_float(
        comments.get("fiber_minimum_perimeter_length") or comments.get("fiber_perimeter_min_route_length"),
        cfg.perimeter_min_route_length,
    )
    cfg.perimeter_inset = parse_first_positive_float(comments.get("fiber_perimeter_inset"), cfg.perimeter_inset)
    cfg.infill_inset = parse_first_positive_float(comments.get("fiber_infill_inset"), cfg.infill_inset)
    cfg.fiber_feedrate = speed_mm_s_to_feedrate(comments.get("fiber_print_speed"), cfg.fiber_feedrate)
    cfg.fiber_slow_feedrate = speed_mm_s_to_feedrate(comments.get("fiber_start_speed"), cfg.fiber_slow_feedrate)
    cfg.tension_length = parse_first_float(comments.get("fiber_tension_length"), cfg.tension_length)
    cfg.tension_feedrate = parse_first_float(comments.get("fiber_tension_feedrate"), cfg.tension_feedrate)
    cfg.after_cut_plastic_extrusion_multiplier = parse_first_float(
        comments.get("fiber_after_cut_plastic_extrusion_multiplier"),
        cfg.after_cut_plastic_extrusion_multiplier,
    )
    spacing_override = parse_first_float(comments.get("fiber_infill_spacing"), 0.0)
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
    cfg.angles = angles_for_pattern(cfg.pattern, args.angles)

    fiber_enabled = parse_bool(comments.get("fiber_enabled"), False)
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

    if spacing_override > EPSILON:
        cfg.infill_spacing = max(spacing_override, cfg.fiber_width)
    if macro_layer_height_override > EPSILON:
        cfg.macro_layer_height = macro_layer_height_override
    if layer_step_override > 0:
        cfg.layer_step = layer_step_override
        cfg.macro_layer_height = 0.0
    if max_routes_override > 0:
        cfg.max_routes_per_layer = max_routes_override
    if routes_per_cut_override > 0:
        cfg.routes_per_cut = routes_per_cut_override

    if args.fiber_generate_perimeters is not None:
        cfg.generate_perimeters = parse_bool(args.fiber_generate_perimeters, cfg.generate_perimeters)
        cfg.input_source = "live-slicer-config"
    if args.fiber_generate_infill is not None:
        cfg.generate_infill = parse_bool(args.fiber_generate_infill, cfg.generate_infill)
        cfg.input_source = "live-slicer-config"
    if args.fiber_infill_source is not None:
        cfg.infill_source_policy = args.fiber_infill_source
        cfg.input_source = "live-slicer-config"

    if args.spacing is not None:
        cfg.infill_spacing = max(args.spacing, cfg.fiber_width)
    if args.layer_step is not None:
        cfg.layer_step = max(args.layer_step, 1)
        cfg.macro_layer_height = 0.0
    if args.fiber_start_layer is not None:
        cfg.fiber_start_layer = max(args.fiber_start_layer, 0)
        cfg.input_source = "live-slicer-config"
    if args.min_route_length is not None:
        cfg.min_route_length = max(args.min_route_length, 0.1)
    if args.line_width is not None:
        cfg.fiber_width = max(args.line_width, 0.01)
        cfg.infill_spacing = max(cfg.infill_spacing, cfg.fiber_width)
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
    cut_window = cfg.cut_distance + cfg.slow_length + max(cfg.tension_length, 0.0)
    if length < cut_window:
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
        cfg.cut_distance + 2.0 * cfg.start_length + max(cfg.tension_length, 0.0),
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
            if "below_min_bend_radius" in warnings:
                skipped["hole_reinforcement_skipped_by_bend_radius"] += 1
                continue
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
    selected = [route for _, route in candidates[: cfg.hole_reinforcement_routes_per_layer]]
    skipped["hole_reinforcement_routes"] += len(selected)
    return selected


def traced_hole_reinforcement_routes(
    layer: LayerGeometry,
    polygons: Sequence[Polygon],
    cfg: PlannerConfig,
    skipped: dict[str, int],
) -> list[FiberRoute]:
    if cfg.hole_reinforcement_routes_per_layer <= 0:
        return []

    candidates_by_center: dict[tuple[int, int], tuple[tuple[float, float], float, FiberRoute]] = {}
    minimum_hardware_length = hardware_min_route_length(cfg)
    max_hole_radius = cfg.min_radius * cfg.hole_reinforcement_max_radius_factor
    closed_loops: list[dict] = []
    for extrusion_path in layer.extrusion_paths:
        if extrusion_path.role not in PERIMETER_TRACE_ROLES:
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
            }
        )

    for loop_info in closed_loops:
        loop = loop_info["loop"]
        loop_length = loop_info["length"]
        center = loop_info["center"]
        equivalent_radius = loop_info["equivalent_radius"]
        polygon = loop_info["polygon"]
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
            skipped["hole_reinforcement_skipped_by_bend_radius"] += 1
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
        if "below_min_bend_radius" in warnings:
            skipped["hole_reinforcement_skipped_by_bend_radius"] += 1
            continue

        center_key = (round(float(centroid.x) / 2.0), round(float(centroid.y) / 2.0))
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

    selected = [
        route
        for _, _, route in sorted(
            candidates_by_center.values(),
            key=lambda item: (item[1], item[2].length),
        )[: cfg.hole_reinforcement_routes_per_layer]
    ]
    skipped["hole_reinforcement_routes"] += len(selected)
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
                warnings=route_warnings_for_path(points, cfg),
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
        "layers_without_hardware_printable_routes": 0,
        "routes_skipped_by_hardware_min_length": 0,
        "routes_capped": 0,
        "thin_feature_min_route_fallback_layers": 0,
        "short_perimeter_stitched_routes": 0,
        "hole_reinforcement_routes": 0,
        "hole_cluster_reinforcement_routes": 0,
        "hole_cluster_reinforcement_skipped": 0,
        "hole_reinforcement_skipped_by_bend_radius": 0,
        "hole_reinforcement_skipped_by_enclosing_loop": 0,
        "hole_reinforcement_skipped_by_hardware_min_length": 0,
        "hole_reinforcement_skipped_by_max_laps": 0,
        "hole_reinforcement_skipped_by_radius": 0,
        "hole_reinforcement_skipped_by_unprintable_path": 0,
        "infill_requested_without_explicit_source_layers": 0,
        "infill_explicit_fallback_to_plastic_trace_layers": 0,
        "infill_explicit_fallback_to_generated_ribs_layers": 0,
    }
    selected_layers = selected_layer_indexes(parsed.layers, cfg)
    minimum_hardware_length = hardware_min_route_length(cfg)
    first_allowed_index = max(cfg.fiber_start_layer - 1, 0) if cfg.fiber_start_layer > 0 else 0
    top_guard_start = max(len(parsed.layers) - cfg.fiber_start_layer, first_allowed_index)

    def filter_hardware_printable(layer_routes: Sequence[FiberRoute]) -> list[FiberRoute]:
        kept: list[FiberRoute] = []
        for route in layer_routes:
            if route.length + EPSILON < minimum_hardware_length:
                skipped["routes_skipped_by_hardware_min_length"] += 1
                continue
            kept.append(route)
        return kept

    def routes_for_layer(layer: LayerGeometry, polygons: Sequence[Polygon], route_cfg: PlannerConfig) -> list[FiberRoute]:
        layer_routes: list[FiberRoute] = []
        perimeter_trace_routes: list[FiberRoute] = []
        infill_trace_routes: list[FiberRoute] = []
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
            perimeter_trace_routes = select_longest_routes(
                perimeter_trace_candidates + stitched_perimeter_routes,
                route_cfg.perimeter_routes_per_layer,
            )
            layer_routes.extend(perimeter_trace_routes)
            layer_routes.extend(traced_hole_reinforcement_routes(layer, polygons, route_cfg, skipped))
            for polygon in polygons[:1]:
                layer_routes.extend(hole_reinforcement_routes(layer, polygon, route_cfg, skipped))
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
                layer_routes.extend(select_longest_routes(perimeter_routes(layer, polygon, route_cfg), route_cfg.perimeter_routes_per_layer))
        layer_routes.sort(key=lambda route: (ROUTE_PRIORITY.get(route.kind, 99), -route.length))
        return layer_routes

    for layer in parsed.layers:
        if cfg.fiber_start_layer > 0 and layer.index < first_allowed_index:
            skipped["layers_skipped_by_start_guard"] += 1
            continue
        if cfg.fiber_start_layer > 0 and layer.index >= top_guard_start:
            skipped["layers_skipped_by_top_guard"] += 1
            continue
        if layer.index not in selected_layers:
            if cfg.macro_layer_height > EPSILON:
                skipped["layers_skipped_by_macro_height"] += 1
            else:
                skipped["layers_skipped_by_step"] += 1
            continue
        polygons = closed_outer_polygons(layer)
        if not polygons:
            skipped["layers_without_outer_polygon"] += 1
            continue
        layer_routes = routes_for_layer(layer, polygons, cfg)
        layer_routes = filter_hardware_printable(layer_routes)
        if not layer_routes and (cfg.generate_perimeters or cfg.generate_infill):
            for fallback_min_length in cfg.thin_feature_min_route_lengths:
                if fallback_min_length >= cfg.min_route_length - EPSILON:
                    continue
                fallback_cfg = replace(cfg, min_route_length=fallback_min_length)
                layer_routes = routes_for_layer(layer, polygons, fallback_cfg)
                layer_routes = filter_hardware_printable(layer_routes)
                if layer_routes:
                    skipped["thin_feature_min_route_fallback_layers"] += 1
                    warning = f"thin_feature_min_route_fallback_to_{fmt_float(fallback_min_length, 1)}mm"
                    for route in layer_routes:
                        route.warnings.append(warning)
                    break
        if not layer_routes and (cfg.generate_perimeters or cfg.generate_infill):
            skipped["layers_without_hardware_printable_routes"] += 1
        if len(layer_routes) > cfg.max_routes_per_layer:
            skipped["routes_capped"] += len(layer_routes) - cfg.max_routes_per_layer
            layer_routes = layer_routes[: cfg.max_routes_per_layer]
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


def emit_path_moves(lines: list[str], route: FiberRoute, cfg: PlannerConfig, emit_cut: bool = True) -> None:
    points = route.points
    total_length = route.length
    cut_at = max(total_length - cfg.cut_distance, 0.0)
    cut_emitted = not emit_cut
    walked = 0.0

    def emit_move(target: tuple[float, float], segment_length: float) -> None:
        if segment_length <= EPSILON:
            return
        feed = cfg.fiber_slow_feedrate if walked < cfg.slow_length else cfg.fiber_feedrate
        v_value = segment_length * cfg.fiber_v_per_mm
        lines.append(f";VG1 {fmt_axis('X', target[0])} {fmt_axis('Y', target[1])} E{fmt_float(segment_length, 5)} F{fmt_float(feed, 0)}")
        command = (
            "G1 "
            f"{fmt_axis('X', target[0])} {fmt_axis('Y', target[1])} "
            f"V{fmt_float(v_value, 5)} U{fmt_float(segment_length, 5)} "
            f"P{fmt_float(cfg.fiber_p_value, 5)} F{fmt_float(feed, 0)}"
        )
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
        f"G0 {fmt_axis('X', start[0])} {fmt_axis('Y', start[1])} F{fmt_float(cfg.travel_feedrate, 0)}",
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


def emit_fiber_block(
    routes: Sequence[FiberRoute],
    cfg: PlannerConfig,
    include_preamble: bool,
    include_footer: bool,
) -> list[str]:
    lines: list[str] = []
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
    lines.append(cfg.fiber_tool_command)
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
    lines.append(cfg.plastic_tool_command)
    if include_footer:
        lines.append("; ORCA_CODEX_NATIVE_FIBER_PLANNER_END")
    return lines


def emit_fiber_only(routes: Sequence[FiberRoute], cfg: PlannerConfig) -> str:
    return "\n".join(emit_fiber_block(routes, cfg, include_preamble=True, include_footer=True)) + "\n"


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
    current_layer: int | None = None
    inserted_header = False
    for raw_line in parsed.lines:
        if raw_line.startswith(";LAYER_CHANGE"):
            if current_layer is not None and current_layer in by_layer:
                output.extend(
                    emit_fiber_block(
                        by_layer[current_layer],
                        cfg,
                        include_preamble=not inserted_header,
                        include_footer=False,
                    )
                )
                inserted_header = True
            current_layer = (current_layer + 1) if current_layer is not None else 0
        output.append(raw_line)
    if current_layer is not None and current_layer in by_layer:
        output.extend(
            emit_fiber_block(
                by_layer[current_layer],
                cfg,
                include_preamble=not inserted_header,
                include_footer=False,
            )
        )
        inserted_header = True
    if inserted_header:
        output.append("; ORCA_CODEX_NATIVE_FIBER_PLANNER_END")
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
            "perimeter_min_route_length": cfg.perimeter_min_route_length,
            "thin_feature_min_route_lengths": cfg.thin_feature_min_route_lengths,
            "start_length": cfg.start_length,
            "fiber_width": cfg.fiber_width,
            "fiber_feedrate": cfg.fiber_feedrate,
            "fiber_slow_feedrate": cfg.fiber_slow_feedrate,
            "tension_length": cfg.tension_length,
            "tension_feedrate": cfg.tension_feedrate,
            "after_cut_plastic_extrusion_multiplier": cfg.after_cut_plastic_extrusion_multiplier,
            "infill_spacing": cfg.infill_spacing,
            "perimeter_inset": cfg.perimeter_inset,
            "infill_inset": cfg.infill_inset,
            "generate_perimeters": cfg.generate_perimeters,
            "generate_infill": cfg.generate_infill,
            "infill_source_policy": cfg.infill_source_policy,
            "reinforcement_mode": cfg.reinforcement_mode,
            "pattern": cfg.pattern,
            "input_source": cfg.input_source,
            "angles": cfg.angles,
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
