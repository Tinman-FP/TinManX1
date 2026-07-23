#!/usr/bin/env python3
"""Compare Rocket and TinManX1 FibreSeek G-code without importing Rocket assets.

The goal is a neutral validation report: command families, thermal setpoints,
tool ownership, cut/load behavior, fiber route metadata, and high-level print
summary values. TinManX1's stricter contract audit remains the source of truth
for whether TinManX1 output is release-safe.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import tempfile
import textwrap
from collections import Counter
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

try:
    from audit_fiberseek_gcode_contract import audit_gcode
except Exception:  # pragma: no cover - comparison can still run without audit.
    audit_gcode = None


COMMAND_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\b")
CUT_RE = re.compile(r"^\s*;\s*CUT\s+DISTANCE\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", re.IGNORECASE)
M1001_RE = re.compile(r"^\s*M1001\s+L([-+]?(?:\d+(?:\.\d*)?|\.\d+))\b", re.IGNORECASE)
ROUTE_RE = re.compile(
    r"^\s*;\s*ORCA_CODEX_FIBER_ROUTE(?:_START)?\s+"
    r".*?\blayer=(?P<layer>\d+)\s+z=(?P<z>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"kind=(?P<kind>\S+)\s+(?:fiber_)?length=(?P<length>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\b.*?\s+"
    r"warnings=(?P<warnings>.*)\s*$"
)
SUMMARY_RE = re.compile(r"^\s*;\s*([^:=]+?)\s*[:=]\s*(.+?)\s*$")
TEMP_COMMAND_RE = re.compile(r"^\s*(M10[49]|M1[49]0|M19[01])\b(?P<body>[^;]*)", re.IGNORECASE)
PARAM_RE = re.compile(r"\b([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))\b", re.IGNORECASE)
TIME_VALUE_RE = re.compile(
    r"(?:(?P<days>\d+(?:\.\d+)?)\s*d(?:ays?)?)?\s*"
    r"(?:(?P<hours>\d+(?:\.\d+)?)\s*h(?:ours?)?)?\s*"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?\s*"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?)?",
    re.IGNORECASE,
)
PRINTINFO_RE = re.compile(r"^\s*;\s*PRINTINFO:\s*(\{.*\})\s*$")

CRITICAL_COMMANDS = (
    "SET_PRINT_STATS_INFO",
    "SET_PRESSURE_ADVANCE",
    "SET_VELOCITY_LIMIT",
    "SET_TOOL_CORNER_VELOCITY",
    "T0",
    "T1",
    "M1001",
    "M2800",
    "M1002",
    "M104",
    "M109",
    "M106",
    "M140",
    "M190",
    "M141",
    "M191",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rocket_gcode", nargs="?", type=Path, help="Rocket FibreSeek G-code.")
    parser.add_argument("tinmanx1_gcode", nargs="?", type=Path, help="TinManX1 FibreSeek G-code.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable comparison JSON.")
    parser.add_argument("--layer-csv", type=Path, help="Write a Z-bucket route/load comparison CSV.")
    parser.add_argument("--route-csv", type=Path, help="Write one reconstructed M1001..M1002 block per CSV row.")
    parser.add_argument("--no-tinman-audit", action="store_true", help="Skip the TinManX1 contract audit.")
    parser.add_argument("--single-source", metavar="LABEL", help="Summarize one G-code file without pairwise Rocket/TinManX1 findings.")
    parser.add_argument("--self-test", action="store_true", help="Run the built-in comparison smoke test.")
    return parser.parse_args()


def command_of(line: str) -> str | None:
    code = line.split(";", 1)[0].strip()
    if not code:
        return None
    match = COMMAND_RE.match(code)
    return match.group(1).upper() if match else None


def exact_command(line: str) -> str:
    return line.split(";", 1)[0].strip()


def parse_float_values(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)]


def parse_summary(lines: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in lines:
        match = SUMMARY_RE.match(line)
        if not match:
            continue
        key = re.sub(r"[^a-z0-9]+", "_", match.group(1).strip().lower()).strip("_")
        if key:
            values.setdefault(key, []).append(match.group(2).strip())
    return values


def parse_config_comments(lines: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in lines:
        match = re.match(r"^\s*;\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$", line)
        if match:
            values[match.group(1)] = match.group(2)
    return values


def infer_printing_mode(summary: dict[str, list[str]], config: dict[str, str]) -> str:
    for key in ("printing_mode", "print_mode"):
        values = summary.get(key)
        if values:
            return values[-1]
    explicit = (config.get("fiber_printing_mode") or config.get("printing_mode") or "").strip()
    if explicit:
        return explicit
    if fiber_requested(config):
        return "Plastic + Continuous Fiber Overlay"
    return "Plastic"


def parse_printinfo(lines: list[str]) -> dict[str, Any]:
    for line in lines:
        match = PRINTINFO_RE.match(line)
        if not match:
            continue
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}
    return {}


def parse_tool_motion_metrics(lines: list[str]) -> dict[str, dict[str, float | int]]:
    """Summarize extrusion axes by active tool and reinforced-route state.

    Rocket's Seeker 3 output uses a composite slot where one motion line can
    carry plastic matrix and continuous fiber together. The exact axis letters
    are firmware/profile dependent, but the presence and scale of positive
    U/V motion and P ratio tags are a strong signal for composite extrusion.
    """

    tool = "none"
    in_route = False
    position: dict[str, float | None] = {
        "X": None,
        "Y": None,
        "Z": None,
        "E": 0.0,
        "U": 0.0,
        "V": 0.0,
        "P": 0.0,
    }
    metrics: dict[str, dict[str, float | int]] = {}

    def bucket() -> dict[str, float | int]:
        key = f"{tool}_{'route' if in_route else 'nonroute'}"
        if key not in metrics:
            metrics[key] = {
                "motion_count": 0,
                "xy_mm": 0.0,
                "e_positive": 0.0,
                "u_positive": 0.0,
                "v_positive": 0.0,
                "p_sum": 0.0,
                "p_count": 0,
            }
        return metrics[key]

    for line in lines:
        code = exact_command(line)
        upper = code.upper()
        if upper.startswith("T0"):
            tool = "T0"
        elif upper.startswith("T1"):
            tool = "T1"
        if upper.startswith("M1001"):
            in_route = True
        elif upper.startswith("M1002"):
            in_route = False
        if not upper.startswith(("G0", "G1")):
            continue
        values = {key.upper(): float(value) for key, value in PARAM_RE.findall(code)}
        if not values:
            continue
        item = bucket()
        item["motion_count"] = int(item["motion_count"]) + 1
        old_x, old_y = position["X"], position["Y"]
        new_x = values.get("X", old_x)
        new_y = values.get("Y", old_y)
        if old_x is not None and old_y is not None and new_x is not None and new_y is not None and ("X" in values or "Y" in values):
            item["xy_mm"] = float(item["xy_mm"]) + math.hypot(float(new_x) - float(old_x), float(new_y) - float(old_y))
        for axis, metric_key in (("E", "e_positive"), ("U", "u_positive"), ("V", "v_positive")):
            if axis not in values:
                continue
            previous = float(position.get(axis) or 0.0)
            delta = values[axis] - previous
            if delta > 0:
                item[metric_key] = float(item[metric_key]) + delta
        if "P" in values:
            item["p_sum"] = float(item["p_sum"]) + values["P"]
            item["p_count"] = int(item["p_count"]) + 1
        for axis, value in values.items():
            if axis in position:
                position[axis] = value

    rounded: dict[str, dict[str, float | int]] = {}
    for key, item in metrics.items():
        rounded[key] = {
            metric: round(value, 3) if isinstance(value, float) else value
            for metric, value in item.items()
        }
    return rounded


def parse_cut_distances(lines: list[str]) -> list[float]:
    distances: list[float] = []
    for line in lines:
        match = CUT_RE.match(line)
        if match:
            distances.append(float(match.group(1)))
    return distances


def parse_m1001_loads(lines: list[str]) -> list[float]:
    loads: list[float] = []
    for line in lines:
        match = M1001_RE.match(line)
        if match:
            loads.append(float(match.group(1)))
    return loads


def parse_layer_from_comment(line: str) -> int | None:
    stripped = line.strip()
    match = re.match(r"^;\s*LAYER\s*:\s*(\d+)\b", stripped, re.IGNORECASE)
    if match:
        return int(match.group(1))
    if stripped.startswith("; ORCA_CODEX_FIBER_LAYER "):
        match = re.search(r"\blayer=(\d+)\b", stripped)
        return int(match.group(1)) if match else None
    match = re.search(r"\bCURRENT_LAYER=(\d+)\b", stripped, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def percentile(sorted_values: list[float], ratio: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * ratio
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return sorted_values[lower]
    blend = index - lower
    return sorted_values[lower] * (1.0 - blend) + sorted_values[upper] * blend


def distribution(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"count": 0, "total": 0.0, "min": None, "p10": None, "p50": None, "p90": None, "max": None}
    ordered = sorted(values)
    return {
        "count": len(values),
        "total": round(sum(values), 3),
        "min": round(ordered[0], 3),
        "p10": round(percentile(ordered, 0.10) or 0.0, 3),
        "p50": round(percentile(ordered, 0.50) or 0.0, 3),
        "p90": round(percentile(ordered, 0.90) or 0.0, 3),
        "max": round(ordered[-1], 3),
    }


def extend_bbox(block: dict[str, Any], x: float | None, y: float | None) -> None:
    if x is None or y is None:
        return
    x_value = float(x)
    y_value = float(y)
    block["bbox_min_x"] = x_value if block.get("bbox_min_x") is None else min(float(block["bbox_min_x"]), x_value)
    block["bbox_max_x"] = x_value if block.get("bbox_max_x") is None else max(float(block["bbox_max_x"]), x_value)
    block["bbox_min_y"] = y_value if block.get("bbox_min_y") is None else min(float(block["bbox_min_y"]), y_value)
    block["bbox_max_y"] = y_value if block.get("bbox_max_y") is None else max(float(block["bbox_max_y"]), y_value)


def route_shape_class(block: dict[str, Any]) -> str:
    xy_mm = float(block.get("xy_mm") or 0.0)
    if xy_mm <= 0.1:
        return "no_xy_motion"
    closure_gap = block.get("closure_gap")
    if isinstance(closure_gap, (int, float)):
        if float(closure_gap) <= 1.0:
            return "closed_loop"
        if float(closure_gap) <= 3.0:
            return "near_closed_loop"
    if xy_mm < 55.0:
        return "short_open_path"
    span_x = float(block.get("span_x") or 0.0)
    span_y = float(block.get("span_y") or 0.0)
    if min(span_x, span_y) <= 1.0:
        return "line_or_tail"
    return "open_path"


def finalize_route_block(block: dict[str, Any]) -> dict[str, Any]:
    start_x = block.get("start_x")
    start_y = block.get("start_y")
    end_x = block.get("end_x")
    end_y = block.get("end_y")
    if all(isinstance(value, (int, float)) for value in (start_x, start_y, end_x, end_y)):
        block["closure_gap"] = math.hypot(float(end_x) - float(start_x), float(end_y) - float(start_y))
    else:
        block["closure_gap"] = None

    bbox_min_x = block.get("bbox_min_x")
    bbox_max_x = block.get("bbox_max_x")
    bbox_min_y = block.get("bbox_min_y")
    bbox_max_y = block.get("bbox_max_y")
    if all(isinstance(value, (int, float)) for value in (bbox_min_x, bbox_max_x)):
        block["span_x"] = float(bbox_max_x) - float(bbox_min_x)
    else:
        block["span_x"] = None
    if all(isinstance(value, (int, float)) for value in (bbox_min_y, bbox_max_y)):
        block["span_y"] = float(bbox_max_y) - float(bbox_min_y)
    else:
        block["span_y"] = None
    if isinstance(block.get("span_x"), (int, float)) and isinstance(block.get("span_y"), (int, float)):
        block["bbox_area"] = float(block["span_x"]) * float(block["span_y"])
    else:
        block["bbox_area"] = None

    xy_mm = float(block.get("xy_mm") or 0.0)
    if xy_mm > 1e-9:
        block["load_per_xy"] = float(block.get("load") or 0.0) / xy_mm
        block["u_per_xy"] = float(block.get("u_positive") or 0.0) / xy_mm
        block["v_per_xy"] = float(block.get("v_positive") or 0.0) / xy_mm
    else:
        block["load_per_xy"] = None
        block["u_per_xy"] = None
        block["v_per_xy"] = None

    for key in (
        "xy_mm",
        "extruding_xy_mm",
        "fiber_xy_mm",
        "matrix_xy_mm",
        "e_xy_mm",
        "travel_xy_mm",
        "e_positive",
        "u_positive",
        "v_positive",
        "p_sum",
        "start_x",
        "start_y",
        "end_x",
        "end_y",
        "bbox_min_x",
        "bbox_max_x",
        "bbox_min_y",
        "bbox_max_y",
        "span_x",
        "span_y",
        "bbox_area",
        "closure_gap",
        "load_per_xy",
        "u_per_xy",
        "v_per_xy",
    ):
        if isinstance(block.get(key), float):
            block[key] = round(float(block[key]), 3)
    block["cut_distances"] = [round(float(value), 4) for value in block["cut_distances"]]
    block["shape_class"] = route_shape_class(block)
    return block


def parse_m1001_events(lines: list[str]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    current_layer: int | None = None
    current_z: float | None = None
    for index, line in enumerate(lines):
        parsed_layer = parse_layer_from_comment(line)
        if parsed_layer is not None:
            current_layer = parsed_layer
            continue
        code = exact_command(line)
        command = command_of(line)
        if command in {"G0", "G1"}:
            values = {key.upper(): float(value) for key, value in PARAM_RE.findall(code)}
            if "Z" in values:
                current_z = values["Z"]
        match = M1001_RE.match(line)
        if not match:
            continue
        after: list[str] = []
        for nearby in lines[index + 1 : index + 8]:
            command = command_of(nearby)
            if command in CRITICAL_COMMANDS or command in {"G0", "G1"}:
                after.append(command)
            if command == "M1002":
                break
        events.append({"line": index + 1, "layer": current_layer, "z": current_z, "load": float(match.group(1)), "after": after[:6]})
    return events


def parse_fiber_route_blocks(lines: list[str]) -> list[dict[str, Any]]:
    """Reconstruct M1001..M1002 reinforced blocks from generic G-code.

    TinManX1 emits explicit route comments, but Rocket does not. This parser
    follows the machine contract itself so both files can be compared on the
    same axis: how many reinforced blocks exist, where they occur, how long the
    XY motion is, and how much positive plastic/fiber axis motion appears
    inside each block.
    """

    current_tool = "none"
    current_layer: int | None = None
    current_z: float | None = None
    position: dict[str, float | None] = {"X": None, "Y": None, "Z": None, "E": 0.0, "U": 0.0, "V": 0.0}
    active: dict[str, Any] | None = None
    blocks: list[dict[str, Any]] = []

    for index, line in enumerate(lines):
        parsed_layer = parse_layer_from_comment(line)
        if parsed_layer is not None:
            current_layer = parsed_layer

        code = exact_command(line)
        command = command_of(line)
        if command in {"T0", "T1"}:
            current_tool = command

        m1001 = M1001_RE.match(line)
        if m1001:
            if active is not None:
                active["warnings"].append("nested_m1001_before_m1002")
                active["end_line"] = index
                blocks.append(finalize_route_block(active))
            start_x = position["X"]
            start_y = position["Y"]
            active = {
                "start_line": index + 1,
                "end_line": None,
                "tool": current_tool,
                "layer": current_layer,
                "z": current_z,
                "load": float(m1001.group(1)),
                "motion_count": 0,
                "xy_motion_count": 0,
                "extruding_xy_motion_count": 0,
                "fiber_xy_motion_count": 0,
                "matrix_xy_motion_count": 0,
                "e_xy_motion_count": 0,
                "travel_xy_motion_count": 0,
                "arc_motion_count": 0,
                "xy_mm": 0.0,
                "extruding_xy_mm": 0.0,
                "fiber_xy_mm": 0.0,
                "matrix_xy_mm": 0.0,
                "e_xy_mm": 0.0,
                "travel_xy_mm": 0.0,
                "e_positive": 0.0,
                "u_positive": 0.0,
                "v_positive": 0.0,
                "p_count": 0,
                "p_sum": 0.0,
                "m2800_count": 0,
                "cut_distances": [],
                "start_x": float(start_x) if start_x is not None else None,
                "start_y": float(start_y) if start_y is not None else None,
                "end_x": float(start_x) if start_x is not None else None,
                "end_y": float(start_y) if start_y is not None else None,
                "bbox_min_x": None,
                "bbox_max_x": None,
                "bbox_min_y": None,
                "bbox_max_y": None,
                "warnings": [],
            }
            extend_bbox(active, start_x, start_y)

        if active is not None:
            if command == "M2800":
                active["m2800_count"] += 1
            cut_match = CUT_RE.match(line)
            if cut_match:
                active["cut_distances"].append(float(cut_match.group(1)))

        if active is not None and command in {"G2", "G3"}:
            active["arc_motion_count"] += 1
            active["warnings"].append("arc_motion_in_fiber_block")

        if command in {"G0", "G1", "G2", "G3"}:
            values = {key.upper(): float(value) for key, value in PARAM_RE.findall(code)}
            if values:
                old_x, old_y = position["X"], position["Y"]
                new_x = values.get("X", old_x)
                new_y = values.get("Y", old_y)
                if "Z" in values:
                    current_z = values["Z"]
                if active is not None:
                    active["motion_count"] += 1
                    material_axis_delta = 0.0
                    positive_axes: set[str] = set()
                    for axis, metric_key in (("E", "e_positive"), ("U", "u_positive"), ("V", "v_positive")):
                        if axis not in values:
                            continue
                        previous = float(position.get(axis) or 0.0)
                        delta = values[axis] - previous
                        if delta > 0:
                            active[metric_key] += delta
                            material_axis_delta += delta
                            positive_axes.add(axis)
                    if (
                        old_x is not None
                        and old_y is not None
                        and new_x is not None
                        and new_y is not None
                        and ("X" in values or "Y" in values)
                    ):
                        segment_mm = math.hypot(float(new_x) - float(old_x), float(new_y) - float(old_y))
                        active["xy_motion_count"] += 1
                        active["xy_mm"] += segment_mm
                        active["end_x"] = float(new_x)
                        active["end_y"] = float(new_y)
                        extend_bbox(active, old_x, old_y)
                        extend_bbox(active, new_x, new_y)
                        if material_axis_delta > 0:
                            active["extruding_xy_motion_count"] += 1
                            active["extruding_xy_mm"] += segment_mm
                        else:
                            active["travel_xy_motion_count"] += 1
                            active["travel_xy_mm"] += segment_mm
                        if "U" in positive_axes:
                            active["fiber_xy_motion_count"] += 1
                            active["fiber_xy_mm"] += segment_mm
                        if "V" in positive_axes:
                            active["matrix_xy_motion_count"] += 1
                            active["matrix_xy_mm"] += segment_mm
                        if "E" in positive_axes:
                            active["e_xy_motion_count"] += 1
                            active["e_xy_mm"] += segment_mm
                    if "P" in values:
                        active["p_count"] += 1
                        active["p_sum"] += values["P"]
                for axis, value in values.items():
                    if axis in position:
                        position[axis] = value

        if command == "M1002" and active is not None:
            active["end_line"] = index + 1
            blocks.append(finalize_route_block(active))
            active = None

    if active is not None:
        active["warnings"].append("missing_m1002")
        blocks.append(finalize_route_block(active))
    return blocks


def summarize_m1001_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    loads = [float(event["load"]) for event in events]
    by_layer: dict[int, dict[str, float | int]] = {}
    by_z: dict[float, dict[str, float | int]] = {}
    signatures: Counter[str] = Counter()
    for event in events:
        layer = event.get("layer")
        if isinstance(layer, int):
            item = by_layer.setdefault(layer, {"count": 0, "load": 0.0})
            item["count"] = int(item["count"]) + 1
            item["load"] = float(item["load"]) + float(event["load"])
        z_value = event.get("z")
        if isinstance(z_value, (int, float)):
            z_key = round(float(z_value), 3)
            item = by_z.setdefault(z_key, {"count": 0, "load": 0.0})
            item["count"] = int(item["count"]) + 1
            item["load"] = float(item["load"]) + float(event["load"])
        signatures[" ".join(event["after"]) or "<none>"] += 1
    top_layers = sorted(
        (
            {"layer": layer, "count": int(item["count"]), "load": round(float(item["load"]), 3)}
            for layer, item in by_layer.items()
        ),
        key=lambda item: item["load"],
        reverse=True,
    )[:10]
    top_z = sorted(
        (
            {"z": z_value, "count": int(item["count"]), "load": round(float(item["load"]), 3)}
            for z_value, item in by_z.items()
        ),
        key=lambda item: item["load"],
        reverse=True,
    )[:10]
    by_layer_full = [
        {"layer": layer, "count": int(item["count"]), "load": round(float(item["load"]), 3)}
        for layer, item in sorted(by_layer.items())
    ]
    by_z_full = [
        {"z": z_value, "count": int(item["count"]), "load": round(float(item["load"]), 3)}
        for z_value, item in sorted(by_z.items())
    ]
    return {
        "load_distribution": distribution(loads),
        "layers_with_m1001": len(by_layer),
        "z_levels_with_m1001": len(by_z),
        "top_load_layers": top_layers,
        "top_load_z": top_z,
        "by_layer": by_layer_full,
        "by_z": by_z_full,
        "sequence_signatures": dict(signatures.most_common(8)),
    }


def summarize_route_blocks(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    loads = [float(block.get("load") or 0.0) for block in blocks]
    xy_lengths = [float(block.get("xy_mm") or 0.0) for block in blocks]
    extruding_xy_lengths = [float(block.get("extruding_xy_mm") or 0.0) for block in blocks]
    fiber_xy_lengths = [float(block.get("fiber_xy_mm") or 0.0) for block in blocks]
    matrix_xy_lengths = [float(block.get("matrix_xy_mm") or 0.0) for block in blocks]
    e_xy_lengths = [float(block.get("e_xy_mm") or 0.0) for block in blocks]
    travel_xy_lengths = [float(block.get("travel_xy_mm") or 0.0) for block in blocks]
    closure_gaps = [float(block["closure_gap"]) for block in blocks if isinstance(block.get("closure_gap"), (int, float))]
    span_x_values = [float(block["span_x"]) for block in blocks if isinstance(block.get("span_x"), (int, float))]
    span_y_values = [float(block["span_y"]) for block in blocks if isinstance(block.get("span_y"), (int, float))]
    bbox_area_values = [float(block["bbox_area"]) for block in blocks if isinstance(block.get("bbox_area"), (int, float))]
    load_per_xy_values = [float(block["load_per_xy"]) for block in blocks if isinstance(block.get("load_per_xy"), (int, float))]
    u_per_xy_values = [float(block["u_per_xy"]) for block in blocks if isinstance(block.get("u_per_xy"), (int, float))]
    v_per_xy_values = [float(block["v_per_xy"]) for block in blocks if isinstance(block.get("v_per_xy"), (int, float))]
    u_values = [float(block.get("u_positive") or 0.0) for block in blocks]
    v_values = [float(block.get("v_positive") or 0.0) for block in blocks]
    motion_counts = [float(block.get("motion_count") or 0.0) for block in blocks]
    xy_motion_counts = [float(block.get("xy_motion_count") or 0.0) for block in blocks]
    arc_motion_counts = [float(block.get("arc_motion_count") or 0.0) for block in blocks]
    by_layer: dict[int, dict[str, float | int]] = {}
    by_z: dict[float, dict[str, float | int]] = {}
    by_tool: dict[str, dict[str, float | int]] = {}
    warnings: Counter[str] = Counter()
    shape_counts: Counter[str] = Counter()

    for block in blocks:
        shape_class = str(block.get("shape_class") or "unknown")
        shape_counts[shape_class] += 1
        closed_increment = 1 if shape_class == "closed_loop" else 0
        no_xy_increment = 1 if shape_class == "no_xy_motion" else 0
        layer = block.get("layer")
        if isinstance(layer, int):
            item = by_layer.setdefault(
                layer,
                {
                    "count": 0,
                    "load": 0.0,
                    "xy_mm": 0.0,
                    "extruding_xy_mm": 0.0,
                    "fiber_xy_mm": 0.0,
                    "matrix_xy_mm": 0.0,
                    "e_xy_mm": 0.0,
                    "travel_xy_mm": 0.0,
                    "u_positive": 0.0,
                    "v_positive": 0.0,
                    "closed_count": 0,
                    "no_xy_count": 0,
                },
            )
            item["count"] = int(item["count"]) + 1
            item["load"] = float(item["load"]) + float(block.get("load") or 0.0)
            item["xy_mm"] = float(item["xy_mm"]) + float(block.get("xy_mm") or 0.0)
            item["extruding_xy_mm"] = float(item["extruding_xy_mm"]) + float(block.get("extruding_xy_mm") or 0.0)
            item["fiber_xy_mm"] = float(item["fiber_xy_mm"]) + float(block.get("fiber_xy_mm") or 0.0)
            item["matrix_xy_mm"] = float(item["matrix_xy_mm"]) + float(block.get("matrix_xy_mm") or 0.0)
            item["e_xy_mm"] = float(item["e_xy_mm"]) + float(block.get("e_xy_mm") or 0.0)
            item["travel_xy_mm"] = float(item["travel_xy_mm"]) + float(block.get("travel_xy_mm") or 0.0)
            item["u_positive"] = float(item["u_positive"]) + float(block.get("u_positive") or 0.0)
            item["v_positive"] = float(item["v_positive"]) + float(block.get("v_positive") or 0.0)
            item["closed_count"] = int(item["closed_count"]) + closed_increment
            item["no_xy_count"] = int(item["no_xy_count"]) + no_xy_increment
        z_value = block.get("z")
        if isinstance(z_value, (int, float)):
            z_key = round(float(z_value), 3)
            item = by_z.setdefault(
                z_key,
                {
                    "count": 0,
                    "load": 0.0,
                    "xy_mm": 0.0,
                    "extruding_xy_mm": 0.0,
                    "fiber_xy_mm": 0.0,
                    "matrix_xy_mm": 0.0,
                    "e_xy_mm": 0.0,
                    "travel_xy_mm": 0.0,
                    "u_positive": 0.0,
                    "v_positive": 0.0,
                    "closed_count": 0,
                    "no_xy_count": 0,
                },
            )
            item["count"] = int(item["count"]) + 1
            item["load"] = float(item["load"]) + float(block.get("load") or 0.0)
            item["xy_mm"] = float(item["xy_mm"]) + float(block.get("xy_mm") or 0.0)
            item["extruding_xy_mm"] = float(item["extruding_xy_mm"]) + float(block.get("extruding_xy_mm") or 0.0)
            item["fiber_xy_mm"] = float(item["fiber_xy_mm"]) + float(block.get("fiber_xy_mm") or 0.0)
            item["matrix_xy_mm"] = float(item["matrix_xy_mm"]) + float(block.get("matrix_xy_mm") or 0.0)
            item["e_xy_mm"] = float(item["e_xy_mm"]) + float(block.get("e_xy_mm") or 0.0)
            item["travel_xy_mm"] = float(item["travel_xy_mm"]) + float(block.get("travel_xy_mm") or 0.0)
            item["u_positive"] = float(item["u_positive"]) + float(block.get("u_positive") or 0.0)
            item["v_positive"] = float(item["v_positive"]) + float(block.get("v_positive") or 0.0)
            item["closed_count"] = int(item["closed_count"]) + closed_increment
            item["no_xy_count"] = int(item["no_xy_count"]) + no_xy_increment
        tool = str(block.get("tool") or "none")
        tool_item = by_tool.setdefault(
            tool,
            {
                "count": 0,
                "load": 0.0,
                "xy_mm": 0.0,
                "extruding_xy_mm": 0.0,
                "fiber_xy_mm": 0.0,
                "matrix_xy_mm": 0.0,
                "e_xy_mm": 0.0,
                "travel_xy_mm": 0.0,
                "u_positive": 0.0,
                "v_positive": 0.0,
                "closed_count": 0,
                "no_xy_count": 0,
            },
        )
        tool_item["count"] = int(tool_item["count"]) + 1
        tool_item["load"] = float(tool_item["load"]) + float(block.get("load") or 0.0)
        tool_item["xy_mm"] = float(tool_item["xy_mm"]) + float(block.get("xy_mm") or 0.0)
        tool_item["extruding_xy_mm"] = float(tool_item["extruding_xy_mm"]) + float(block.get("extruding_xy_mm") or 0.0)
        tool_item["fiber_xy_mm"] = float(tool_item["fiber_xy_mm"]) + float(block.get("fiber_xy_mm") or 0.0)
        tool_item["matrix_xy_mm"] = float(tool_item["matrix_xy_mm"]) + float(block.get("matrix_xy_mm") or 0.0)
        tool_item["e_xy_mm"] = float(tool_item["e_xy_mm"]) + float(block.get("e_xy_mm") or 0.0)
        tool_item["travel_xy_mm"] = float(tool_item["travel_xy_mm"]) + float(block.get("travel_xy_mm") or 0.0)
        tool_item["u_positive"] = float(tool_item["u_positive"]) + float(block.get("u_positive") or 0.0)
        tool_item["v_positive"] = float(tool_item["v_positive"]) + float(block.get("v_positive") or 0.0)
        tool_item["closed_count"] = int(tool_item["closed_count"]) + closed_increment
        tool_item["no_xy_count"] = int(tool_item["no_xy_count"]) + no_xy_increment
        warnings.update(block.get("warnings") or [])

    def rounded_items(values: dict[Any, dict[str, float | int]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, item in sorted(values.items()):
            row = {"key": key}
            row.update(
                {
                    metric: round(value, 3) if isinstance(value, float) else value
                    for metric, value in item.items()
                }
            )
            rows.append(row)
        return rows

    return {
        "count": len(blocks),
        "load_distribution": distribution(loads),
        "xy_distribution": distribution(xy_lengths),
        "extruding_xy_distribution": distribution(extruding_xy_lengths),
        "fiber_xy_distribution": distribution(fiber_xy_lengths),
        "matrix_xy_distribution": distribution(matrix_xy_lengths),
        "e_xy_distribution": distribution(e_xy_lengths),
        "travel_xy_distribution": distribution(travel_xy_lengths),
        "closure_gap_distribution": distribution(closure_gaps),
        "span_x_distribution": distribution(span_x_values),
        "span_y_distribution": distribution(span_y_values),
        "bbox_area_distribution": distribution(bbox_area_values),
        "load_per_xy_distribution": distribution(load_per_xy_values),
        "u_per_xy_distribution": distribution(u_per_xy_values),
        "v_per_xy_distribution": distribution(v_per_xy_values),
        "u_positive_distribution": distribution(u_values),
        "v_positive_distribution": distribution(v_values),
        "motion_count_distribution": distribution(motion_counts),
        "xy_motion_count_distribution": distribution(xy_motion_counts),
        "arc_motion_count_distribution": distribution(arc_motion_counts),
        "arc_motion_count_total": int(sum(arc_motion_counts)),
        "shape_counts": dict(shape_counts.most_common()),
        "closed_route_count": int(shape_counts.get("closed_loop", 0)),
        "no_xy_block_count": int(shape_counts.get("no_xy_motion", 0)),
        "blocks_with_cut": sum(1 for block in blocks if block.get("cut_distances")),
        "blocks_with_material_xy": sum(1 for block in blocks if float(block.get("extruding_xy_mm") or 0.0) > 0.0),
        "blocks_with_fiber_xy": sum(1 for block in blocks if float(block.get("fiber_xy_mm") or 0.0) > 0.0),
        "by_tool": {
            tool: {
                metric: round(value, 3) if isinstance(value, float) else value
                for metric, value in item.items()
            }
            for tool, item in sorted(by_tool.items())
        },
        "by_layer": [
            {"layer": row.pop("key"), **row}
            for row in rounded_items(by_layer)
        ],
        "by_z": [
            {"z": row.pop("key"), **row}
            for row in rounded_items(by_z)
        ],
        "warning_counts": dict(warnings.most_common()),
    }


def summarize_routes(routes: list[dict[str, Any]]) -> dict[str, Any]:
    lengths = [float(route["length"]) for route in routes]
    by_kind: dict[str, list[float]] = {}
    by_layer: dict[int, dict[str, float | int]] = {}
    by_z: dict[float, dict[str, float | int]] = {}
    layers = {int(route["layer"]) for route in routes if route.get("layer") is not None}
    z_levels = {round(float(route["z"]), 3) for route in routes if route.get("z") is not None}
    for route in routes:
        by_kind.setdefault(str(route["kind"]), []).append(float(route["length"]))
        layer = route.get("layer")
        if isinstance(layer, int):
            item = by_layer.setdefault(layer, {"count": 0, "length": 0.0})
            item["count"] = int(item["count"]) + 1
            item["length"] = float(item["length"]) + float(route["length"])
        z_value = route.get("z")
        if isinstance(z_value, (int, float)):
            item = by_z.setdefault(round(float(z_value), 3), {"count": 0, "length": 0.0})
            item["count"] = int(item["count"]) + 1
            item["length"] = float(item["length"]) + float(route["length"])
    return {
        "count": len(routes),
        "length_distribution": distribution(lengths),
        "layers_with_routes": len(layers),
        "z_levels_with_routes": len(z_levels),
        "by_kind": {kind: distribution(values) for kind, values in sorted(by_kind.items())},
        "by_layer": [
            {"layer": layer, "count": int(item["count"]), "length": round(float(item["length"]), 3)}
            for layer, item in sorted(by_layer.items())
        ],
        "by_z": [
            {"z": z_value, "count": int(item["count"]), "length": round(float(item["length"]), 3)}
            for z_value, item in sorted(by_z.items())
        ],
    }


def parse_routes(lines: list[str]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = ROUTE_RE.match(line)
        if not match:
            continue
        warnings_text = match.group("warnings").strip()
        warnings = [] if warnings_text in {"", "none"} else [item.strip() for item in warnings_text.split(",") if item.strip()]
        routes.append(
            {
                "line": index + 1,
                "layer": int(match.group("layer")),
                "z": float(match.group("z")),
                "kind": match.group("kind"),
                "length": float(match.group("length")),
                "warnings": warnings,
            }
        )
    return routes


def parse_temperatures(lines: list[str]) -> dict[str, list[dict[str, float | int | None]]]:
    temperatures: dict[str, list[dict[str, float | int | None]]] = {}
    for line in lines:
        match = TEMP_COMMAND_RE.match(exact_command(line))
        if not match:
            continue
        command = match.group(1).upper()
        params = {key.upper(): float(value) for key, value in PARAM_RE.findall(match.group("body"))}
        if "S" not in params:
            continue
        temperatures.setdefault(command, []).append(
            {
                "s": params["S"],
                "t": int(params["T"]) if "T" in params else None,
                "p": int(params["P"]) if "P" in params else None,
            }
        )
    return temperatures


def layer_indexes(lines: list[str]) -> set[int]:
    indexes: set[int] = set()
    for line in lines:
        parsed_layer = parse_layer_from_comment(line)
        if parsed_layer is not None:
            indexes.add(parsed_layer)
    return indexes


def parse_seconds(text: str) -> float | None:
    lowered = text.lower()
    if not any(token in lowered for token in ("d", "day", "h", "hour", "min", "sec", "s")):
        return None
    match = TIME_VALUE_RE.search(lowered)
    if not match or not any(match.groupdict().values()):
        return None
    days = float(match.group("days") or 0)
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def extract_summary_number(summary: dict[str, list[str]], key_tokens: tuple[str, ...]) -> float | None:
    for key, values in summary.items():
        if all(token in key for token in key_tokens):
            for value in values:
                numbers = parse_float_values(value)
                if numbers:
                    return numbers[0]
    return None


def extract_summary_total(summary: dict[str, list[str]], key_tokens: tuple[str, ...]) -> float | None:
    for key, values in summary.items():
        if all(token in key for token in key_tokens):
            for value in values:
                numbers = parse_float_values(value)
                if numbers:
                    return sum(numbers)
    return None


def extract_time_seconds(summary: dict[str, list[str]]) -> float | None:
    preferred_keys = (
        "estimated_printing_time_normal_mode",
        "printing_time",
        "print_time",
        "time",
    )
    ordered_items = [(key, summary[key]) for key in preferred_keys if key in summary]
    ordered_items.extend((key, values) for key, values in summary.items() if key not in preferred_keys)
    for key, values in ordered_items:
        if "time" not in key:
            continue
        if "first_layer" in key:
            continue
        for value in values:
            parsed = parse_seconds(value)
            if parsed is not None:
                return parsed
            numbers = parse_float_values(value)
            if numbers and any(unit in value.lower() for unit in ("sec", "second")):
                return numbers[0]
    return None


def printinfo_summary_values(printinfo: dict[str, Any]) -> dict[str, float | None]:
    if not printinfo:
        return {}
    extruders = printinfo.get("extruders") if isinstance(printinfo.get("extruders"), dict) else {}
    fiber_g = 0.0
    filament_g = 0.0
    for extruder in extruders.values():
        if not isinstance(extruder, dict):
            continue
        polymer = extruder.get("p")
        fiber = extruder.get("f")
        if isinstance(polymer, dict):
            filament_g += float(polymer.get("weight") or 0.0)
        if isinstance(fiber, dict):
            fiber_g += float(fiber.get("weight") or 0.0)
    model_info = printinfo.get("model_info") if isinstance(printinfo.get("model_info"), dict) else {}
    return {
        "print_time_seconds": float(printinfo["time"]) if isinstance(printinfo.get("time"), (int, float)) else None,
        "fiber_used_g": fiber_g if fiber_g > 0 else None,
        "filament_used_g": filament_g if filament_g > 0 else None,
        "total_layers": float(model_info["total_layers"]) if isinstance(model_info.get("total_layers"), (int, float)) else None,
        "layer_height": float(model_info["macro_layer_height"]) if isinstance(model_info.get("macro_layer_height"), (int, float)) else None,
        "max_z_height": float(model_info["total_height"]) if isinstance(model_info.get("total_height"), (int, float)) else None,
    }


def first_config_float(config: dict[str, str], key: str) -> float | None:
    if key not in config:
        return None
    values = parse_float_values(config[key])
    return values[0] if values else None


def has_fiberseek_context(config: dict[str, str]) -> bool:
    haystack = " ".join(
        config.get(key, "")
        for key in (
            "printer_settings_id",
            "printer_model",
            "printer_variant",
            "filament_settings_id",
            "filament_ids",
            "filament_type",
        )
    ).lower()
    return (
        "fibreseek" in haystack
        or "fiberseek" in haystack
        or "seeker 3" in haystack
        or "seek3" in haystack
        or "cfc" in haystack
    )


def process_supports_fiberseek(config: dict[str, str]) -> bool:
    process_id = (config.get("print_settings_id") or "").lower()
    payload = (config.get("fiber_reinforcement_payload") or "").strip()
    return bool(payload) or any(
        token in process_id
        for token in (
            "fibreseek",
            "fiberseek",
            "continuous fiber",
            "continuous fibre",
            "composite fiber",
            "composite fibre",
            "rocket compare",
            "rocket exact",
        )
    )


def fiber_requested(config: dict[str, str]) -> bool:
    requested_values = [
        config.get("fiber_enabled", ""),
        config.get("fiber_generate_perimeters", ""),
        config.get("fiber_generate_infill", ""),
    ]
    return any(value.strip().lower() in {"1", "true", "yes", "on"} for value in requested_values if value is not None)


def command_sequence_signature(lines: list[str]) -> list[str]:
    signature: list[str] = []
    previous = None
    for line in lines:
        command = command_of(line)
        if command not in CRITICAL_COMMANDS:
            continue
        normalized = command
        code = exact_command(line).upper()
        if command in {"T0", "T1"}:
            normalized = code.split()[0]
        elif command in {"M104", "M109"}:
            target = re.search(r"\bT(\d+)\b", code)
            normalized = f"{command}T{target.group(1)}" if target else command
        elif command in {"M140", "M141", "M106"}:
            stop = re.search(r"\bS0(?:\.0+)?\b", code)
            normalized = f"{command}_OFF" if stop else command
        if normalized != previous:
            signature.append(normalized)
            previous = normalized
    return signature[:80]


def summarize_gcode(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    commands = Counter(command for line in lines if (command := command_of(line)))
    routes = parse_routes(lines)
    route_layers = sorted({route["layer"] for route in routes})
    route_warnings = Counter(warning for route in routes for warning in route["warnings"])
    summary = parse_summary(lines)
    config = parse_config_comments(lines)
    printinfo = parse_printinfo(lines)
    printinfo_values = printinfo_summary_values(printinfo)
    cut_distances = parse_cut_distances(lines)
    m1001_loads = parse_m1001_loads(lines)
    m1001_events = parse_m1001_events(lines)
    route_blocks = parse_fiber_route_blocks(lines)
    layer_ids = layer_indexes(lines)
    temperatures = parse_temperatures(lines)
    total_layers = (
        printinfo_values.get("total_layers")
        or extract_summary_number(summary, ("total", "layer", "number"))
        or extract_summary_number(summary, ("layer_count",))
    )
    layer_height = printinfo_values.get("layer_height") or first_config_float(config, "layer_height")
    max_z_height = printinfo_values.get("max_z_height") or extract_summary_number(summary, ("max_z_height",))

    return {
        "path": str(path),
        "line_count": len(lines),
        "config": config,
        "printinfo_present": bool(printinfo),
        "printing_mode": infer_printing_mode(summary, config),
        "command_counts": {command: commands.get(command, 0) for command in CRITICAL_COMMANDS},
        "all_command_counts": dict(sorted(commands.items())),
        "critical_sequence": command_sequence_signature(lines),
        "tool_motion_metrics": parse_tool_motion_metrics(lines),
        "bare_tool_commands": Counter(line.strip() for line in lines if line.strip() in {"T0", "T1"}),
        "managed_tool_commands": Counter(
            line.strip()
            for line in lines
            if line.strip() in {"T0 ; switch extruder type to:FIBER", "T0 R ; switch extruder type to:FIBER", "T1 ; switch extruder type to:PLASTIC"}
        ),
        "route_count": len(routes),
        "fiber_layers": len(route_layers),
        "route_length_mm": round(sum(route["length"] for route in routes), 3),
        "route_warning_counts": dict(sorted(route_warnings.items())),
        "cut_distance_values": sorted(set(round(value, 4) for value in cut_distances)),
        "cut_distance_count": len(cut_distances),
        "m1001_count": len(m1001_loads),
        "m1001_load_total": round(sum(m1001_loads), 3),
        "m1001_load_min": round(min(m1001_loads), 3) if m1001_loads else None,
        "m1001_load_max": round(max(m1001_loads), 3) if m1001_loads else None,
        "m1001": summarize_m1001_events(m1001_events),
        "fiber_route_blocks": summarize_route_blocks(route_blocks),
        "route": summarize_routes(routes),
        "layers_seen": len(layer_ids),
        "total_layers": total_layers,
        "layer_height": layer_height,
        "max_z_height": max_z_height,
        "temperatures": temperatures,
        "summary_values": {
            "print_time_seconds": printinfo_values.get("print_time_seconds") or extract_time_seconds(summary),
            "fiber_used_mm": extract_summary_number(summary, ("fiber", "used", "mm")),
            "fiber_used_g": printinfo_values.get("fiber_used_g") or extract_summary_number(summary, ("fiber", "used", "g")),
            "matrix_path_mm": extract_summary_number(summary, ("fiber", "matrix", "path", "mm")),
            "filament_used_g": (
                printinfo_values.get("filament_used_g")
                or extract_summary_number(summary, ("total", "filament", "used", "g"))
                or extract_summary_total(summary, ("filament", "used", "g"))
            ),
            "estimated_printing_time": extract_time_seconds({"time": summary.get("estimated_printing_time_normal_mode", [])}),
        },
    }


def compare_lists(label: str, rocket: list[Any], tinman: list[Any], findings: list[str]) -> None:
    if rocket != tinman:
        findings.append(f"{label} differs: Rocket={rocket} TinManX1={tinman}")


def compare_temperature_sets(rocket: dict[str, Any], tinman: dict[str, Any], findings: list[str]) -> None:
    for command in ("M104", "M109", "M140", "M190", "M141", "M191"):
        rocket_values = rocket["temperatures"].get(command, [])
        tinman_values = tinman["temperatures"].get(command, [])
        sort_key = lambda item: (
            "" if item[0] is None else str(item[0]),
            "" if item[1] is None else str(item[1]),
            item[2],
        )
        rocket_set = sorted({(item.get("t"), item.get("p"), round(float(item["s"]), 3)) for item in rocket_values}, key=sort_key)
        tinman_set = sorted({(item.get("t"), item.get("p"), round(float(item["s"]), 3)) for item in tinman_values}, key=sort_key)
        if rocket_set != tinman_set:
            findings.append(f"{command} setpoints differ: Rocket={rocket_set} TinManX1={tinman_set}")


def ratio_percent(value: float | int | None, baseline: float | int | None) -> float | None:
    if value is None or baseline is None:
        return None
    baseline_float = float(baseline)
    if abs(baseline_float) <= 1e-9:
        return None
    return 100.0 * float(value) / baseline_float


def count_fraction(count: float | int | None, total: float | int | None) -> float:
    if count is None or total is None or float(total) <= 0.0:
        return 0.0
    return float(count) / float(total)


def compare_gcodes(rocket_path: Path, tinman_path: Path, run_tinman_audit: bool) -> dict[str, Any]:
    rocket = summarize_gcode(rocket_path)
    tinman = summarize_gcode(tinman_path)
    findings: list[str] = []
    advisories: list[str] = []

    for command in CRITICAL_COMMANDS:
        if rocket["command_counts"].get(command, 0) > 0 and tinman["command_counts"].get(command, 0) == 0:
            findings.append(f"TinManX1 is missing command family present in Rocket: {command}")

    if tinman["route_count"] == 0 and tinman["command_counts"].get("M1001", 0) == 0:
        findings.append("TinManX1 has no parsed fiber routes or M1001 fiber-load commands")
    if tinman["command_counts"].get("M1001", 0) != tinman["command_counts"].get("M2800", 0):
        findings.append("TinManX1 M1001 and M2800 counts differ")
    if tinman["command_counts"].get("M1001", 0) != tinman["command_counts"].get("M1002", 0):
        findings.append("TinManX1 M1001 and M1002 counts differ")
    tinman_arc_motion_count = tinman.get("fiber_route_blocks", {}).get("arc_motion_count_total", 0)
    if tinman_arc_motion_count:
        findings.append(
            "TinManX1 emits G2/G3 arc motion inside CFC route blocks before FibreSeek arc support is validated: "
            f"{tinman_arc_motion_count} arc moves"
        )

    compare_lists("CUT DISTANCE values", rocket["cut_distance_values"], tinman["cut_distance_values"], findings)
    compare_temperature_sets(rocket, tinman, findings)

    rocket_mode = (rocket.get("printing_mode") or "").strip()
    tinman_mode = (tinman.get("printing_mode") or "").strip()
    if "composite only" in rocket_mode.lower() and "composite only" not in tinman_mode.lower():
        findings.append(
            "Manufacturing mode mismatch: Rocket is PRINTING_MODE Composite Only, "
            f"but TinManX1 is {tinman_mode or '<unknown>'}. This is not a profile-only comparison."
        )
        load_ratio = ratio_percent(tinman.get("m1001_load_total"), rocket.get("m1001_load_total"))
        if load_ratio is not None and load_ratio < 75.0:
            findings.append(
                "TinManX1 emits much less reinforced-route load than Rocket in composite-only mode: "
                f"{load_ratio:.1f}% of Rocket M1001 load total"
            )
        rocket_fiber_xy = rocket.get("fiber_route_blocks", {}).get("fiber_xy_distribution", {}).get("total")
        tinman_fiber_xy = tinman.get("fiber_route_blocks", {}).get("fiber_xy_distribution", {}).get("total")
        fiber_xy_ratio = ratio_percent(tinman_fiber_xy, rocket_fiber_xy)
        if fiber_xy_ratio is not None and fiber_xy_ratio < 75.0:
            findings.append(
                "TinManX1 emits much less U-positive fiber-road XY than Rocket in composite-only mode: "
                f"{fiber_xy_ratio:.1f}% of Rocket U-positive route XY"
            )

    rocket_blocks = rocket.get("fiber_route_blocks", {})
    tinman_blocks = tinman.get("fiber_route_blocks", {})
    rocket_shape_counts = rocket_blocks.get("shape_counts", {})
    tinman_shape_counts = tinman_blocks.get("shape_counts", {})
    rocket_block_count = rocket_blocks.get("count", 0)
    tinman_block_count = tinman_blocks.get("count", 0)
    rocket_open_fraction = count_fraction(rocket_shape_counts.get("open_path"), rocket_block_count)
    tinman_closed_fraction = count_fraction(tinman_shape_counts.get("closed_loop"), tinman_block_count)
    if rocket_open_fraction >= 0.5 and tinman_closed_fraction >= 0.5:
        findings.append(
            "Reconstructed route-shape mismatch: Rocket is open-composite-road dominated "
            f"({rocket_open_fraction:.1%} open paths), but TinManX1 is closed-overlay-loop dominated "
            f"({tinman_closed_fraction:.1%} closed loops)"
        )

    tinman_config = tinman["config"]
    if has_fiberseek_context(tinman_config) and fiber_requested(tinman_config) and not process_supports_fiberseek(tinman_config):
        findings.append(
            "TinManX1 FibreSeek/CFC job uses a non-FibreSeek process profile: "
            f"{tinman_config.get('print_settings_id') or '<missing>'}"
        )
    if has_fiberseek_context(tinman_config) and fiber_requested(tinman_config) and not (tinman_config.get("fiber_reinforcement_payload") or "").strip():
        advisories.append("TinManX1 fiber_reinforcement_payload is empty; material-specific planner tuning was not applied")

    rocket_layers = rocket.get("total_layers")
    tinman_layers = tinman.get("total_layers")
    if rocket_layers and tinman_layers:
        baseline = max(abs(float(rocket_layers)), 1.0)
        if abs(float(tinman_layers) - float(rocket_layers)) / baseline > 0.15:
            findings.append(f"Total layer count differs materially: Rocket={rocket_layers:g} TinManX1={tinman_layers:g}")
    rocket_layer_height = rocket.get("layer_height")
    tinman_layer_height = tinman.get("layer_height")
    if rocket_layer_height and tinman_layer_height and abs(float(rocket_layer_height) - float(tinman_layer_height)) > 0.02:
        findings.append(f"Layer height differs: Rocket={rocket_layer_height:g} TinManX1={tinman_layer_height:g}")

    if tinman["bare_tool_commands"]:
        findings.append(f"TinManX1 contains bare tool commands: {dict(tinman['bare_tool_commands'])}")
    if not tinman["managed_tool_commands"]:
        findings.append("TinManX1 does not contain managed FibreSeek tool-change comments")

    route_delta = tinman["route_count"] - rocket["route_count"]
    if rocket["route_count"] and abs(route_delta) > max(10, rocket["route_count"] * 0.25):
        advisories.append(f"Parsed fiber route count differs materially: Rocket={rocket['route_count']} TinManX1={tinman['route_count']}")
    elif not rocket["route_count"] and rocket["command_counts"].get("M1001", 0):
        advisories.append("Rocket has M1001 fiber-load commands but no TinManX1-style route metadata; compare load totals and preview visually")

    for key in ("print_time_seconds", "fiber_used_mm", "fiber_used_g", "filament_used_g"):
        rocket_value = rocket["summary_values"].get(key)
        tinman_value = tinman["summary_values"].get(key)
        if rocket_value is None or tinman_value is None:
            continue
        baseline = max(abs(float(rocket_value)), 1.0)
        delta = float(tinman_value) - float(rocket_value)
        if abs(delta) / baseline > 0.15:
            advisories.append(f"{key} differs by more than 15%: Rocket={rocket_value} TinManX1={tinman_value}")

    tinman_audit: dict[str, Any] | None = None
    if run_tinman_audit and audit_gcode is not None:
        metrics, failures, audit_advisories = audit_gcode(tinman_path, None, False)
        tinman_audit = {"status": "fail" if failures else "pass", "metrics": metrics, "failures": failures, "advisories": audit_advisories}
        findings.extend(f"TinManX1 audit: {failure}" for failure in failures)
        advisories.extend(f"TinManX1 audit: {advisory}" for advisory in audit_advisories)
    elif run_tinman_audit:
        advisories.append("TinManX1 contract audit was unavailable")

    return {
        "status": "review" if findings else "pass",
        "rocket": rocket,
        "tinmanx1": tinman,
        "findings": findings,
        "advisories": advisories,
        "tinmanx1_audit": tinman_audit,
    }


def summarize_single_source(path: Path, label: str) -> dict[str, Any]:
    source = summarize_gcode(path)
    return {
        "status": "pass",
        "source_label": label,
        "source": source,
        "findings": [],
        "advisories": [],
    }


def seconds_label(value: float | None) -> str:
    if value is None:
        return "n/a"
    minutes, seconds = divmod(int(round(value)), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {seconds}s" if hours else f"{minutes}m {seconds}s"


def print_markdown(payload: dict[str, Any]) -> None:
    rocket = payload["rocket"]
    tinman = payload["tinmanx1"]
    status = "passed" if payload["status"] == "pass" else "needs review"
    print(f"FibreSeek G-code comparison {status}.")
    print()
    print("| Metric | Rocket | TinManX1 |")
    print("| --- | ---: | ---: |")
    rows = [
        ("Lines", rocket["line_count"], tinman["line_count"]),
        ("Printing mode", rocket.get("printing_mode", "n/a"), tinman.get("printing_mode", "n/a")),
        ("Configured total layers", rocket.get("total_layers", "n/a"), tinman.get("total_layers", "n/a")),
        ("Layer height", rocket.get("layer_height", "n/a"), tinman.get("layer_height", "n/a")),
        ("Max Z", rocket.get("max_z_height", "n/a"), tinman.get("max_z_height", "n/a")),
        ("TinManX1 process", "", tinman["config"].get("print_settings_id", "n/a")),
        ("Codex route metadata count", rocket["route_count"], tinman["route_count"]),
        ("Codex route metadata layers", rocket["fiber_layers"], tinman["fiber_layers"]),
        ("Codex route metadata length mm", rocket["route_length_mm"], tinman["route_length_mm"]),
        ("M1001 commands", rocket["command_counts"]["M1001"], tinman["command_counts"]["M1001"]),
        ("M2800 commands", rocket["command_counts"]["M2800"], tinman["command_counts"]["M2800"]),
        ("M1002 commands", rocket["command_counts"]["M1002"], tinman["command_counts"]["M1002"]),
        ("Cut values", rocket["cut_distance_values"], tinman["cut_distance_values"]),
        ("M1001 load total", rocket["m1001_load_total"], tinman["m1001_load_total"]),
        (
            "M1001 load p50/p90",
            f"{rocket['m1001']['load_distribution']['p50']} / {rocket['m1001']['load_distribution']['p90']}",
            f"{tinman['m1001']['load_distribution']['p50']} / {tinman['m1001']['load_distribution']['p90']}",
        ),
        (
            "Layers with M1001",
            rocket["m1001"]["layers_with_m1001"],
            tinman["m1001"]["layers_with_m1001"],
        ),
        (
            "Z levels with M1001",
            rocket["m1001"]["z_levels_with_m1001"],
            tinman["m1001"]["z_levels_with_m1001"],
        ),
        (
            "Route length p50/p90",
            f"{rocket['route']['length_distribution']['p50']} / {rocket['route']['length_distribution']['p90']}",
            f"{tinman['route']['length_distribution']['p50']} / {tinman['route']['length_distribution']['p90']}",
        ),
        (
            "Reconstructed fiber block count",
            rocket["fiber_route_blocks"]["count"],
            tinman["fiber_route_blocks"]["count"],
        ),
        (
            "Fiber block XY p50/p90",
            f"{rocket['fiber_route_blocks']['xy_distribution']['p50']} / {rocket['fiber_route_blocks']['xy_distribution']['p90']}",
            f"{tinman['fiber_route_blocks']['xy_distribution']['p50']} / {tinman['fiber_route_blocks']['xy_distribution']['p90']}",
        ),
        (
            "Fiber block extruding XY total",
            rocket["fiber_route_blocks"]["extruding_xy_distribution"]["total"],
            tinman["fiber_route_blocks"]["extruding_xy_distribution"]["total"],
        ),
        (
            "Fiber block U-positive XY total",
            rocket["fiber_route_blocks"]["fiber_xy_distribution"]["total"],
            tinman["fiber_route_blocks"]["fiber_xy_distribution"]["total"],
        ),
        (
            "Fiber block V-positive XY total",
            rocket["fiber_route_blocks"]["matrix_xy_distribution"]["total"],
            tinman["fiber_route_blocks"]["matrix_xy_distribution"]["total"],
        ),
        (
            "Fiber block closure p50/p90",
            f"{rocket['fiber_route_blocks']['closure_gap_distribution']['p50']} / {rocket['fiber_route_blocks']['closure_gap_distribution']['p90']}",
            f"{tinman['fiber_route_blocks']['closure_gap_distribution']['p50']} / {tinman['fiber_route_blocks']['closure_gap_distribution']['p90']}",
        ),
        (
            "Fiber block closed loops",
            rocket["fiber_route_blocks"]["closed_route_count"],
            tinman["fiber_route_blocks"]["closed_route_count"],
        ),
        (
            "Fiber block shape classes",
            rocket["fiber_route_blocks"]["shape_counts"],
            tinman["fiber_route_blocks"]["shape_counts"],
        ),
        (
            "Fiber block motion p50/p90",
            f"{rocket['fiber_route_blocks']['motion_count_distribution']['p50']} / {rocket['fiber_route_blocks']['motion_count_distribution']['p90']}",
            f"{tinman['fiber_route_blocks']['motion_count_distribution']['p50']} / {tinman['fiber_route_blocks']['motion_count_distribution']['p90']}",
        ),
        (
            "T0 route XY mm",
            rocket["tool_motion_metrics"].get("T0_route", {}).get("xy_mm", "n/a"),
            tinman["tool_motion_metrics"].get("T0_route", {}).get("xy_mm", "n/a"),
        ),
        (
            "T0 route U+",
            rocket["tool_motion_metrics"].get("T0_route", {}).get("u_positive", "n/a"),
            tinman["tool_motion_metrics"].get("T0_route", {}).get("u_positive", "n/a"),
        ),
        (
            "T0 route V+",
            rocket["tool_motion_metrics"].get("T0_route", {}).get("v_positive", "n/a"),
            tinman["tool_motion_metrics"].get("T0_route", {}).get("v_positive", "n/a"),
        ),
        (
            "T0 route P tags",
            rocket["tool_motion_metrics"].get("T0_route", {}).get("p_count", "n/a"),
            tinman["tool_motion_metrics"].get("T0_route", {}).get("p_count", "n/a"),
        ),
        ("Print time", seconds_label(rocket["summary_values"].get("print_time_seconds")), seconds_label(tinman["summary_values"].get("print_time_seconds"))),
        ("Fiber used g", rocket["summary_values"].get("fiber_used_g", "n/a"), tinman["summary_values"].get("fiber_used_g", "n/a")),
        ("Filament used g", rocket["summary_values"].get("filament_used_g", "n/a"), tinman["summary_values"].get("filament_used_g", "n/a")),
    ]
    for label, rocket_value, tinman_value in rows:
        print(f"| {label} | {rocket_value} | {tinman_value} |")

    print()
    print("Critical command counts:")
    for command in CRITICAL_COMMANDS:
        print(f"- {command}: Rocket {rocket['command_counts'][command]}, TinManX1 {tinman['command_counts'][command]}")

    if payload["findings"]:
        print()
        print("Findings:")
        for finding in payload["findings"]:
            print(f"- {finding}")
    if payload["advisories"]:
        print()
        print("Advisories:")
        for advisory in payload["advisories"]:
            print(f"- {advisory}")
    if payload.get("tinmanx1_audit"):
        print()
        print(f"TinManX1 contract audit: {payload['tinmanx1_audit']['status']}")


def print_single_markdown(payload: dict[str, Any]) -> None:
    source = payload["source"]
    label = payload["source_label"]
    print(f"FibreSeek G-code summary for {label}.")
    print()
    print("| Metric | Value |")
    print("| --- | ---: |")
    rows = [
        ("Path", source["path"]),
        ("Lines", source["line_count"]),
        ("Printing mode", source.get("printing_mode", "n/a")),
        ("Configured total layers", source.get("total_layers", "n/a")),
        ("Layer height", source.get("layer_height", "n/a")),
        ("Max Z", source.get("max_z_height", "n/a")),
        ("Codex route metadata count", source["route_count"]),
        ("Codex route metadata layers", source["fiber_layers"]),
        ("Codex route metadata length mm", source["route_length_mm"]),
        ("M1001 commands", source["command_counts"]["M1001"]),
        ("M2800 commands", source["command_counts"]["M2800"]),
        ("M1002 commands", source["command_counts"]["M1002"]),
        ("Cut values", source["cut_distance_values"]),
        ("M1001 load total", source["m1001_load_total"]),
        ("M1001 load p50/p90", f"{source['m1001']['load_distribution']['p50']} / {source['m1001']['load_distribution']['p90']}"),
        ("Layers with M1001", source["m1001"]["layers_with_m1001"]),
        ("Z levels with M1001", source["m1001"]["z_levels_with_m1001"]),
        ("Reconstructed fiber block count", source["fiber_route_blocks"]["count"]),
        ("Fiber block XY p50/p90", f"{source['fiber_route_blocks']['xy_distribution']['p50']} / {source['fiber_route_blocks']['xy_distribution']['p90']}"),
        ("Fiber block extruding XY total", source["fiber_route_blocks"]["extruding_xy_distribution"]["total"]),
        ("Fiber block U-positive XY total", source["fiber_route_blocks"]["fiber_xy_distribution"]["total"]),
        ("Fiber block V-positive XY total", source["fiber_route_blocks"]["matrix_xy_distribution"]["total"]),
        ("Fiber block closure p50/p90", f"{source['fiber_route_blocks']['closure_gap_distribution']['p50']} / {source['fiber_route_blocks']['closure_gap_distribution']['p90']}"),
        ("Fiber block closed loops", source["fiber_route_blocks"]["closed_route_count"]),
        ("Fiber block shape classes", source["fiber_route_blocks"]["shape_counts"]),
        ("Print time", seconds_label(source["summary_values"].get("print_time_seconds"))),
        ("Fiber used g", source["summary_values"].get("fiber_used_g", "n/a")),
        ("Filament used g", source["summary_values"].get("filament_used_g", "n/a")),
    ]
    for label_text, value in rows:
        print(f"| {label_text} | {value} |")

    print()
    print("Critical command counts:")
    for command in CRITICAL_COMMANDS:
        print(f"- {command}: {source['command_counts'][command]}")


def _index_by_z(items: list[dict[str, Any]]) -> dict[float, dict[str, Any]]:
    indexed: dict[float, dict[str, Any]] = {}
    for item in items:
        z_value = item.get("z")
        if isinstance(z_value, (int, float)):
            indexed[round(float(z_value), 3)] = item
    return indexed


def write_layer_csv(payload: dict[str, Any], path: Path) -> None:
    rocket_m1001 = _index_by_z(payload["rocket"]["m1001"].get("by_z", []))
    tinman_m1001 = _index_by_z(payload["tinmanx1"]["m1001"].get("by_z", []))
    rocket_blocks = _index_by_z(payload["rocket"]["fiber_route_blocks"].get("by_z", []))
    tinman_blocks = _index_by_z(payload["tinmanx1"]["fiber_route_blocks"].get("by_z", []))
    rocket_routes = _index_by_z(payload["rocket"]["route"].get("by_z", []))
    tinman_routes = _index_by_z(payload["tinmanx1"]["route"].get("by_z", []))
    z_values = sorted(set(rocket_m1001) | set(tinman_m1001) | set(rocket_blocks) | set(tinman_blocks) | set(rocket_routes) | set(tinman_routes))

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "z",
                "rocket_m1001_count",
                "rocket_m1001_load",
                "tinman_m1001_count",
                "tinman_m1001_load",
                "rocket_block_count",
                "rocket_block_xy_mm",
                "rocket_block_extruding_xy_mm",
                "rocket_block_fiber_xy_mm",
                "rocket_block_matrix_xy_mm",
                "rocket_block_closed_count",
                "rocket_block_no_xy_count",
                "tinman_block_count",
                "tinman_block_xy_mm",
                "tinman_block_extruding_xy_mm",
                "tinman_block_fiber_xy_mm",
                "tinman_block_matrix_xy_mm",
                "tinman_block_closed_count",
                "tinman_block_no_xy_count",
                "rocket_route_count",
                "rocket_route_length",
                "tinman_route_count",
                "tinman_route_length",
                "tinman_load_percent_of_rocket",
                "tinman_block_xy_percent_of_rocket",
                "tinman_block_fiber_xy_percent_of_rocket",
            ],
        )
        writer.writeheader()
        for z_value in z_values:
            rocket_load = float(rocket_m1001.get(z_value, {}).get("load") or 0.0)
            tinman_load = float(tinman_m1001.get(z_value, {}).get("load") or 0.0)
            writer.writerow(
                {
                    "z": z_value,
                    "rocket_m1001_count": int(rocket_m1001.get(z_value, {}).get("count") or 0),
                    "rocket_m1001_load": round(rocket_load, 3),
                    "tinman_m1001_count": int(tinman_m1001.get(z_value, {}).get("count") or 0),
                    "tinman_m1001_load": round(tinman_load, 3),
                    "rocket_block_count": int(rocket_blocks.get(z_value, {}).get("count") or 0),
                    "rocket_block_xy_mm": round(float(rocket_blocks.get(z_value, {}).get("xy_mm") or 0.0), 3),
                    "rocket_block_extruding_xy_mm": round(float(rocket_blocks.get(z_value, {}).get("extruding_xy_mm") or 0.0), 3),
                    "rocket_block_fiber_xy_mm": round(float(rocket_blocks.get(z_value, {}).get("fiber_xy_mm") or 0.0), 3),
                    "rocket_block_matrix_xy_mm": round(float(rocket_blocks.get(z_value, {}).get("matrix_xy_mm") or 0.0), 3),
                    "rocket_block_closed_count": int(rocket_blocks.get(z_value, {}).get("closed_count") or 0),
                    "rocket_block_no_xy_count": int(rocket_blocks.get(z_value, {}).get("no_xy_count") or 0),
                    "tinman_block_count": int(tinman_blocks.get(z_value, {}).get("count") or 0),
                    "tinman_block_xy_mm": round(float(tinman_blocks.get(z_value, {}).get("xy_mm") or 0.0), 3),
                    "tinman_block_extruding_xy_mm": round(float(tinman_blocks.get(z_value, {}).get("extruding_xy_mm") or 0.0), 3),
                    "tinman_block_fiber_xy_mm": round(float(tinman_blocks.get(z_value, {}).get("fiber_xy_mm") or 0.0), 3),
                    "tinman_block_matrix_xy_mm": round(float(tinman_blocks.get(z_value, {}).get("matrix_xy_mm") or 0.0), 3),
                    "tinman_block_closed_count": int(tinman_blocks.get(z_value, {}).get("closed_count") or 0),
                    "tinman_block_no_xy_count": int(tinman_blocks.get(z_value, {}).get("no_xy_count") or 0),
                    "rocket_route_count": int(rocket_routes.get(z_value, {}).get("count") or 0),
                    "rocket_route_length": round(float(rocket_routes.get(z_value, {}).get("length") or 0.0), 3),
                    "tinman_route_count": int(tinman_routes.get(z_value, {}).get("count") or 0),
                    "tinman_route_length": round(float(tinman_routes.get(z_value, {}).get("length") or 0.0), 3),
                    "tinman_load_percent_of_rocket": round(100.0 * tinman_load / rocket_load, 3) if rocket_load > 0 else "",
                    "tinman_block_xy_percent_of_rocket": round(
                        100.0
                        * float(tinman_blocks.get(z_value, {}).get("xy_mm") or 0.0)
                        / float(rocket_blocks.get(z_value, {}).get("xy_mm") or 0.0),
                        3,
                    )
                    if float(rocket_blocks.get(z_value, {}).get("xy_mm") or 0.0) > 0
                    else "",
                    "tinman_block_fiber_xy_percent_of_rocket": round(
                        100.0
                        * float(tinman_blocks.get(z_value, {}).get("fiber_xy_mm") or 0.0)
                        / float(rocket_blocks.get(z_value, {}).get("fiber_xy_mm") or 0.0),
                        3,
                    )
                    if float(rocket_blocks.get(z_value, {}).get("fiber_xy_mm") or 0.0) > 0
                    else "",
                }
            )


def write_route_csv(payload: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "source",
        "index",
        "tool",
        "layer",
        "z",
        "start_line",
        "end_line",
        "shape_class",
        "load",
        "xy_mm",
        "extruding_xy_mm",
        "fiber_xy_mm",
        "matrix_xy_mm",
        "e_xy_mm",
        "travel_xy_mm",
        "closure_gap",
        "span_x",
        "span_y",
        "bbox_area",
        "xy_motion_count",
        "motion_count",
        "u_positive",
        "v_positive",
        "e_positive",
        "p_count",
        "m2800_count",
        "cut_distances",
        "warnings",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for source_key, source_label in (("rocket", "Rocket"), ("tinmanx1", "TinManX1")):
            source_path = Path(str(payload[source_key]["path"]))
            blocks = parse_fiber_route_blocks(source_path.read_text(encoding="utf-8", errors="ignore").splitlines())
            for index, block in enumerate(blocks, start=1):
                writer.writerow(
                    {
                        "source": source_label,
                        "index": index,
                        "tool": block.get("tool"),
                        "layer": block.get("layer"),
                        "z": block.get("z"),
                        "start_line": block.get("start_line"),
                        "end_line": block.get("end_line"),
                        "shape_class": block.get("shape_class"),
                        "load": block.get("load"),
                        "xy_mm": block.get("xy_mm"),
                        "extruding_xy_mm": block.get("extruding_xy_mm"),
                        "fiber_xy_mm": block.get("fiber_xy_mm"),
                        "matrix_xy_mm": block.get("matrix_xy_mm"),
                        "e_xy_mm": block.get("e_xy_mm"),
                        "travel_xy_mm": block.get("travel_xy_mm"),
                        "closure_gap": block.get("closure_gap"),
                        "span_x": block.get("span_x"),
                        "span_y": block.get("span_y"),
                        "bbox_area": block.get("bbox_area"),
                        "xy_motion_count": block.get("xy_motion_count"),
                        "motion_count": block.get("motion_count"),
                        "u_positive": block.get("u_positive"),
                        "v_positive": block.get("v_positive"),
                        "e_positive": block.get("e_positive"),
                        "p_count": block.get("p_count"),
                        "m2800_count": block.get("m2800_count"),
                        "cut_distances": "|".join(str(value) for value in block.get("cut_distances") or []),
                        "warnings": "|".join(str(value) for value in block.get("warnings") or []),
                    }
                )


def write_single_route_csv(payload: dict[str, Any], path: Path) -> None:
    fieldnames = [
        "source",
        "index",
        "tool",
        "layer",
        "z",
        "start_line",
        "end_line",
        "shape_class",
        "load",
        "xy_mm",
        "extruding_xy_mm",
        "fiber_xy_mm",
        "matrix_xy_mm",
        "e_xy_mm",
        "travel_xy_mm",
        "closure_gap",
        "span_x",
        "span_y",
        "bbox_area",
        "xy_motion_count",
        "motion_count",
        "u_positive",
        "v_positive",
        "e_positive",
        "p_count",
        "m2800_count",
        "cut_distances",
        "warnings",
    ]
    blocks = parse_fiber_route_blocks(Path(str(payload["source"]["path"])).read_text(encoding="utf-8", errors="ignore").splitlines())
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, block in enumerate(blocks, start=1):
            writer.writerow(
                {
                    "source": payload["source_label"],
                    "index": index,
                    "tool": block.get("tool"),
                    "layer": block.get("layer"),
                    "z": block.get("z"),
                    "start_line": block.get("start_line"),
                    "end_line": block.get("end_line"),
                    "shape_class": block.get("shape_class"),
                    "load": block.get("load"),
                    "xy_mm": block.get("xy_mm"),
                    "extruding_xy_mm": block.get("extruding_xy_mm"),
                    "fiber_xy_mm": block.get("fiber_xy_mm"),
                    "matrix_xy_mm": block.get("matrix_xy_mm"),
                    "e_xy_mm": block.get("e_xy_mm"),
                    "travel_xy_mm": block.get("travel_xy_mm"),
                    "closure_gap": block.get("closure_gap"),
                    "span_x": block.get("span_x"),
                    "span_y": block.get("span_y"),
                    "bbox_area": block.get("bbox_area"),
                    "xy_motion_count": block.get("xy_motion_count"),
                    "motion_count": block.get("motion_count"),
                    "u_positive": block.get("u_positive"),
                    "v_positive": block.get("v_positive"),
                    "e_positive": block.get("e_positive"),
                    "p_count": block.get("p_count"),
                    "m2800_count": block.get("m2800_count"),
                    "cut_distances": "|".join(str(value) for value in block.get("cut_distances") or []),
                    "warnings": "|".join(str(value) for value in block.get("warnings") or []),
                }
            )


def run_self_test() -> int:
    rocket_text = textwrap.dedent(
        """\
        ; estimated printing time (normal mode) = 1h 2m 3s
        ; filament used [g] = 12.5
        M104 S270 T0
        M140 S75
        M141 S0
        M190 S75
        M191 S0
        M104 S250 T1
        M109 S250 T1
        T1 ; switch extruder type to:PLASTIC
        T0 R ; switch extruder type to:FIBER
        M109 S270 T0
        M1001 L126
        M2800
        ;CUT DISTANCE 54.8
        M1002
        T1 ; switch extruder type to:PLASTIC
        M104 S0 T1
        M104 S0 T0
        M140 S0
        M141 S0
        """
    )
    tinman_text = textwrap.dedent(
        """\
        ; ORCA_CODEX_NATIVE_FIBER_PLANNER_MERGED
        ; continuous_fiber_used_g = 1.2
        ; filament used [g] = 12.0
        ; estimated printing time (normal mode) = 1h 1m 0s
        ; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_START
        SET_PRINT_STATS_INFO TOTAL_LAYER=1
        SET_PRESSURE_ADVANCE EXTRUDER=extruder ADVANCE=0
        SET_VELOCITY_LIMIT MINIMUM_CRUISE_RATIO=0.8
        SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1
        SET_TOOL_CORNER_VELOCITY T=0 SCV=1
        M104 S270 T0
        M140 S75
        M141 S0
        ; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_END
        M190 S75
        M191 S0
        M104 S250 T1
        ; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL
        T1 ; switch extruder type to:PLASTIC
        MOVE_TO_BRUSH_STATION
        CLEAN_NOZZLE
        MOVE_OUT_BRUSH_STATION
        M109 S250 T1
        ; ORCA_CODEX_NATIVE_FIBER_PLANNER_START
        T0 R ; switch extruder type to:FIBER
        M109 S270 T0
        ; ORCA_CODEX_FIBER_PRIME_START
        M1001 L100
        M2800
        ;CUT DISTANCE 54.8
        G1 V10 F600
        M1002
        ; ORCA_CODEX_FIBER_PRIME_END
        ; ORCA_CODEX_FIBER_LAYER layer=0 z=0.2 routes=1
        ; ORCA_CODEX_FIBER_ROUTE layer=0 z=0.2 kind=perimeter length=71.2 warnings=none
        M1001 L126
        M2800
        ;CUT DISTANCE 54.8
        G1 V10 F600
        M1002
        T1 ; switch extruder type to:PLASTIC
        ; ORCA_CODEX_NATIVE_FIBER_PLANNER_END
        ; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_START
        M104 S0 T1
        M104 S0 T0
        M106 P2 S0
        M140 S0
        M141 S0
        ; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_END
        ; EXECUTABLE_BLOCK_END
        """
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        rocket_path = Path(tmpdir) / "rocket.gcode"
        tinman_path = Path(tmpdir) / "tinman.gcode"
        rocket_path.write_text(rocket_text, encoding="utf-8")
        tinman_path.write_text(tinman_text, encoding="utf-8")
        payload = compare_gcodes(rocket_path, tinman_path, run_tinman_audit=True)
    if payload["tinmanx1"]["route_count"] != 1:
        print("self-test failed: TinManX1 route count was not parsed", file=sys.stderr)
        return 1
    if payload["tinmanx1_audit"] is None or payload["tinmanx1_audit"]["status"] != "pass":
        print("self-test failed: TinManX1 audit did not pass", file=sys.stderr)
        return 1
    if any("CUT DISTANCE" in finding for finding in payload["findings"]):
        print("self-test failed: matching cut distance was flagged", file=sys.stderr)
        return 1
    arc_blocks = parse_fiber_route_blocks(
        [
            "T0",
            "M1001 L90",
            "G2 X10 Y0 I5 J0 U1 V0.1",
            "M2800",
            ";CUT DISTANCE 54.8",
            "M1002",
        ]
    )
    arc_summary = summarize_route_blocks(arc_blocks)
    if arc_summary["arc_motion_count_total"] != 1 or arc_summary["warning_counts"].get("arc_motion_in_fiber_block") != 1:
        print("self-test failed: fiber-block arc motion was not detected", file=sys.stderr)
        return 1
    loop_summary = summarize_route_blocks(
        parse_fiber_route_blocks(
            [
                "G1 X0 Y0",
                "T0",
                "M1001 L4",
                "G1 X1 Y0 U1 V0.1",
                "G1 X1 Y1 U2 V0.2",
                "G1 X0 Y1 U3 V0.3",
                "G1 X0 Y0 U4 V0.4",
                "M2800",
                ";CUT DISTANCE 54.8",
                "M1002",
            ]
        )
    )
    if loop_summary["closed_route_count"] != 1 or loop_summary["shape_counts"].get("closed_loop") != 1:
        print("self-test failed: closed fiber-block loop was not classified", file=sys.stderr)
        return 1
    print("FibreSeek G-code comparison self-test passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()
    if args.single_source:
        if args.rocket_gcode is None or args.tinmanx1_gcode is not None:
            print("--single-source requires exactly one G-code path", file=sys.stderr)
            return 2
        if args.layer_csv:
            print("--layer-csv is only available for paired Rocket/TinManX1 comparisons", file=sys.stderr)
            return 2
        payload = summarize_single_source(args.rocket_gcode, args.single_source)
        if args.route_csv:
            write_single_route_csv(payload, args.route_csv)
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print_single_markdown(payload)
        return 0
    if args.rocket_gcode is None or args.tinmanx1_gcode is None:
        print("rocket_gcode and tinmanx1_gcode are required unless --self-test is used", file=sys.stderr)
        return 2
    payload = compare_gcodes(args.rocket_gcode, args.tinmanx1_gcode, run_tinman_audit=not args.no_tinman_audit)
    if args.layer_csv:
        write_layer_csv(payload, args.layer_csv)
    if args.route_csv:
        write_route_csv(payload, args.route_csv)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_markdown(payload)
    return 1 if payload["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
