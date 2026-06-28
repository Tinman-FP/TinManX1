#!/usr/bin/env python3
"""Audit TinManX1/FibreSeek G-code command contract safety.

This is intentionally stricter about machine sequencing than about geometry
planner warnings. A route may carry a warning for visual/geometry review, but
the tool ownership, cut, restart, and shutdown contract must be mechanically
coherent before a file is considered printable.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any


COMMAND_RE = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\b")
CUT_RE = re.compile(r"^\s*;\s*CUT\s+DISTANCE\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*$", re.IGNORECASE)
M1001_RE = re.compile(r"^\s*M1001\s+L([-+]?\d+(?:\.\d*)?)\b", re.IGNORECASE)
SUMMARY_RE = re.compile(r"^\s*;\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$")
ROUTE_RE = re.compile(
    r"^\s*;\s*ORCA_CODEX_FIBER_ROUTE\s+"
    r"layer=(?P<layer>\d+)\s+z=(?P<z>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"kind=(?P<kind>\S+)\s+length=(?P<length>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"warnings=(?P<warnings>.*)\s*$"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("gcode", type=Path, help="TinManX1/FibreSeek G-code to audit.")
    parser.add_argument(
        "--summary",
        type=Path,
        help="Optional native fiber summary JSON. Defaults to <gcode>.native_fiber.summary.json when present.",
    )
    parser.add_argument(
        "--require-alternation",
        action="store_true",
        help="Require positive/core and negative/core phased perimeter families in this slice.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable audit results.")
    return parser.parse_args()


def command_of(line: str) -> str | None:
    code = line.split(";", 1)[0].strip()
    if not code:
        return None
    match = COMMAND_RE.match(code)
    return match.group(1).upper() if match else None


def exact_command(line: str) -> str:
    return line.split(";", 1)[0].strip()


def marker_indexes(lines: list[str], marker: str) -> list[int]:
    return [index for index, line in enumerate(lines) if line.strip() == marker]


def first_marker(lines: list[str], marker: str) -> int | None:
    indexes = marker_indexes(lines, marker)
    return indexes[0] if indexes else None


def add_failure(failures: list[str], message: str) -> None:
    failures.append(message)


def require_once(lines: list[str], marker: str, failures: list[str]) -> int | None:
    indexes = marker_indexes(lines, marker)
    if len(indexes) != 1:
        add_failure(failures, f"expected exactly one {marker!r}, found {len(indexes)}")
        return indexes[0] if indexes else None
    return indexes[0]


def require_in_order(lines: list[str], needles: list[str], failures: list[str]) -> None:
    cursor = -1
    for needle in needles:
        try:
            cursor = next(index for index in range(cursor + 1, len(lines)) if needle in lines[index])
        except StopIteration:
            add_failure(failures, f"missing or out-of-order sequence item: {needle}")
            return


def require_predicates_in_order(lines: list[str], checks: list[tuple[str, Any]], failures: list[str]) -> None:
    cursor = -1
    for label, predicate in checks:
        try:
            cursor = next(index for index in range(cursor + 1, len(lines)) if predicate(lines[index]))
        except StopIteration:
            add_failure(failures, f"missing or out-of-order sequence item: {label}")
            return


def command_predicate(pattern: str):
    regex = re.compile(pattern, re.IGNORECASE)
    return lambda line: regex.search(exact_command(line)) is not None


def parse_top_summary(lines: list[str]) -> dict[str, list[str]]:
    values: dict[str, list[str]] = {}
    for line in lines:
        match = SUMMARY_RE.match(line)
        if not match:
            continue
        values.setdefault(match.group(1), []).append(match.group(2))
    return values


def parse_routes(lines: list[str]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        match = ROUTE_RE.match(line)
        if not match:
            continue
        warning_text = match.group("warnings").strip()
        warnings = [] if warning_text in {"", "none"} else [item.strip() for item in warning_text.split(",") if item.strip()]
        routes.append(
            {
                "index": index,
                "layer": int(match.group("layer")),
                "z": float(match.group("z")),
                "kind": match.group("kind"),
                "length": float(match.group("length")),
                "warnings": warnings,
            }
        )
    return routes


def load_summary(gcode_path: Path, explicit_summary: Path | None) -> dict[str, Any] | None:
    summary_path = explicit_summary or gcode_path.with_suffix(gcode_path.suffix + ".native_fiber.summary.json")
    if not summary_path.exists():
        return None
    with summary_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def parse_cut_distances(lines: list[str]) -> list[float]:
    distances: list[float] = []
    for line in lines:
        match = CUT_RE.match(line)
        if match:
            distances.append(float(match.group(1)))
    return distances


def parse_numeric_values(value: str) -> list[float]:
    return [float(item) for item in re.findall(r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)", value)]


def parse_m1001_loads(lines: list[str]) -> list[tuple[int, float]]:
    loads: list[tuple[int, float]] = []
    for index, line in enumerate(lines):
        match = M1001_RE.match(line)
        if match:
            loads.append((index, float(match.group(1))))
    return loads


def find_in_window(lines: list[str], start: int, end: int, predicate) -> int | None:
    for index in range(start, end):
        if predicate(lines[index]):
            return index
    return None


def audit_gcode(gcode_path: Path, summary_path: Path | None, require_alternation: bool) -> tuple[dict[str, Any], list[str], list[str]]:
    text = gcode_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    summary = load_summary(gcode_path, summary_path)
    failures: list[str] = []
    advisories: list[str] = []

    command_counts = Counter(command for line in lines if (command := command_of(line)))
    exact_commands = Counter(exact_command(line) for line in lines if exact_command(line))
    routes = parse_routes(lines)
    route_count = len(routes)
    route_layers = sorted({route["layer"] for route in routes})
    cut_distances = parse_cut_distances(lines)
    m1001_loads = parse_m1001_loads(lines)
    prime_start_indexes = marker_indexes(lines, "; ORCA_CODEX_FIBER_PRIME_START")
    prime_end_indexes = marker_indexes(lines, "; ORCA_CODEX_FIBER_PRIME_END")
    prime_count = len(prime_start_indexes)

    route_warning_counts = Counter(warning for route in routes for warning in route["warnings"])
    top_summary = parse_top_summary(lines)

    merged_index = require_once(lines, "; ORCA_CODEX_NATIVE_FIBER_PLANNER_MERGED", failures)
    contract_start_index = require_once(lines, "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_START", failures)
    contract_end_index = require_once(lines, "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_END", failures)
    planner_start_index = require_once(lines, "; ORCA_CODEX_NATIVE_FIBER_PLANNER_START", failures)
    planner_end_index = require_once(lines, "; ORCA_CODEX_NATIVE_FIBER_PLANNER_END", failures)
    shutdown_start_index = require_once(lines, "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_START", failures)
    shutdown_end_index = require_once(lines, "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_END", failures)
    executable_end_index = require_once(lines, "; EXECUTABLE_BLOCK_END", failures)

    if merged_index not in {None, 0}:
        add_failure(failures, "merged FibreSeek marker should be the first line")
    if None not in (contract_start_index, contract_end_index, planner_start_index, planner_end_index, shutdown_start_index, shutdown_end_index, executable_end_index):
        ordered = [
            contract_start_index,
            contract_end_index,
            planner_start_index,
            planner_end_index,
            shutdown_start_index,
            shutdown_end_index,
            executable_end_index,
        ]
        if ordered != sorted(ordered):
            add_failure(failures, "machine contract, planner block, shutdown, and executable end are out of order")

    required_substrings = [
        "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1",
        "; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL",
        "T1 ; switch extruder type to:PLASTIC",
        "MOVE_TO_BRUSH_STATION",
        "CLEAN_NOZZLE",
        "MOVE_OUT_BRUSH_STATION",
        "T0 R ; switch extruder type to:FIBER",
        "M104 S0 T1",
        "M104 S0 T0",
        "M106 P2 S0",
        "M140 S0",
        "M141 S0",
    ]
    for required in required_substrings:
        if required not in text:
            add_failure(failures, f"missing required command or marker: {required}")

    required_patterns = [
        ("fiber nozzle preheat", r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T0\b"),
        ("bed preheat", r"^M140\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b"),
        ("chamber preheat", r"^M141\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b"),
        ("bed wait", r"^M190\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b"),
        ("chamber wait", r"^M191\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b"),
        ("plastic nozzle preheat", r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T1\b"),
        ("plastic nozzle wait", r"^M109\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T1\b"),
        ("fiber nozzle wait", r"^M109\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T0\b"),
    ]
    for label, pattern in required_patterns:
        if not any(command_predicate(pattern)(line) for line in lines):
            add_failure(failures, f"missing required command pattern: {label}")

    chamber_values = [
        value
        for item in top_summary.get("chamber_temperature", [])
        for value in parse_numeric_values(item)
    ]
    if chamber_values:
        expected_chamber = max(chamber_values)
        for label, pattern in (
            ("chamber preheat", r"^M141\s+S([-+]?(?:\d+(?:\.\d*)?|\.\d+))\b"),
            ("chamber wait", r"^M191\s+S([-+]?(?:\d+(?:\.\d*)?|\.\d+))\b"),
        ):
            command_match = next(
                (
                    re.match(pattern, exact_command(line), flags=re.IGNORECASE)
                    for line in lines
                    if re.match(pattern, exact_command(line), flags=re.IGNORECASE)
                ),
                None,
            )
            if command_match is None:
                add_failure(failures, f"missing {label} command for chamber_temperature={expected_chamber:g}")
            else:
                emitted = float(command_match.group(1))
                if abs(emitted - expected_chamber) > 0.001:
                    add_failure(
                        failures,
                        f"{label} S{emitted:g} does not match chamber_temperature={expected_chamber:g}",
                    )

    require_predicates_in_order(
        lines,
        [
            ("machine contract start", lambda line: "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_START" in line),
            ("total layer stats", lambda line: "SET_PRINT_STATS_INFO TOTAL_LAYER=" in line),
            ("square corner velocity", lambda line: "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1" in line),
            ("fiber nozzle preheat", command_predicate(r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T0\b")),
            ("bed preheat", command_predicate(r"^M140\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
            ("chamber preheat", command_predicate(r"^M141\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
            ("machine contract end", lambda line: "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_END" in line),
            ("bed wait", command_predicate(r"^M190\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
            ("chamber wait", command_predicate(r"^M191\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
            ("plastic nozzle preheat", command_predicate(r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T1\b")),
            ("initial plastic tool marker", lambda line: "; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL" in line),
            ("initial plastic tool switch", lambda line: "T1 ; switch extruder type to:PLASTIC" in line),
            ("plastic nozzle wait", command_predicate(r"^M109\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T1\b")),
            ("native planner start", lambda line: "; ORCA_CODEX_NATIVE_FIBER_PLANNER_START" in line),
            ("fiber tool switch", lambda line: "T0 R ; switch extruder type to:FIBER" in line),
            ("fiber nozzle wait", command_predicate(r"^M109\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T0\b")),
            ("fiber prime start", lambda line: "; ORCA_CODEX_FIBER_PRIME_START" in line),
            ("fiber prime M1001", lambda line: "M1001" in line),
            ("fiber prime cut start", lambda line: exact_command(line).upper() == "M2800"),
            ("fiber prime cut distance", lambda line: CUT_RE.match(line) is not None),
            ("fiber prime M1002", lambda line: exact_command(line).upper() == "M1002"),
            ("fiber prime end", lambda line: "; ORCA_CODEX_FIBER_PRIME_END" in line),
            ("fiber layer", lambda line: "; ORCA_CODEX_FIBER_LAYER" in line),
            ("fiber route M1001", lambda line: "M1001" in line),
            ("fiber route cut start", lambda line: exact_command(line).upper() == "M2800"),
            ("fiber route cut distance", lambda line: CUT_RE.match(line) is not None),
            ("fiber route M1002", lambda line: exact_command(line).upper() == "M1002"),
            ("plastic tool return", lambda line: "T1 ; switch extruder type to:PLASTIC" in line),
            ("native planner end", lambda line: "; ORCA_CODEX_NATIVE_FIBER_PLANNER_END" in line),
            ("machine shutdown start", lambda line: "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_START" in line),
            ("shutdown plastic nozzle", lambda line: "M104 S0 T1" in line),
            ("shutdown fiber nozzle", lambda line: "M104 S0 T0" in line),
            ("shutdown chamber", lambda line: "M141 S0" in line),
            ("executable end", lambda line: "; EXECUTABLE_BLOCK_END" in line),
        ],
        failures,
    )

    bare_tool_commands = [line.strip() for line in lines if line.strip() in {"T0", "T1"}]
    if bare_tool_commands:
        add_failure(failures, f"bare tool commands remain in output: {Counter(bare_tool_commands)}")

    if route_count == 0:
        add_failure(failures, "no ORCA_CODEX_FIBER_ROUTE blocks found")
    if route_count > 0 and prime_count != 1:
        add_failure(failures, f"expected exactly one fiber prime block, found {prime_count}")
    if prime_count != len(prime_end_indexes):
        add_failure(failures, f"fiber prime start/end markers do not match: {prime_count}/{len(prime_end_indexes)}")

    initial_plastic_index = first_marker(lines, "; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL")
    if initial_plastic_index is not None:
        for label, predicate in (
            ("plastic nozzle preheat", command_predicate(r"^M104\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\s+T1\b")),
            ("bed wait", command_predicate(r"^M190\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
            ("chamber wait", command_predicate(r"^M191\s+S[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b")),
        ):
            wait_index = next((index for index, line in enumerate(lines) if predicate(line)), None)
            if wait_index is None:
                add_failure(failures, f"missing startup command before initial plastic tool: {label}")
            elif wait_index > initial_plastic_index:
                add_failure(failures, f"startup command {label} appears after initial plastic tool selection")

    expected_macro_groups = route_count + prime_count
    if expected_macro_groups != len(cut_distances):
        add_failure(
            failures,
            f"route+prime count {expected_macro_groups} does not match CUT DISTANCE count {len(cut_distances)}",
        )
    if expected_macro_groups != len(m1001_loads):
        add_failure(failures, f"route+prime count {expected_macro_groups} does not match M1001 count {len(m1001_loads)}")
    if expected_macro_groups != command_counts.get("M1002", 0):
        add_failure(
            failures,
            f"route+prime count {expected_macro_groups} does not match M1002 count {command_counts.get('M1002', 0)}",
        )
    if expected_macro_groups != command_counts.get("M2800", 0):
        add_failure(
            failures,
            f"route+prime count {expected_macro_groups} does not match M2800 count {command_counts.get('M2800', 0)}",
        )

    post_cut_u_lines: list[int] = []
    post_cut_v_only_moves = 0
    for cut_index, line in enumerate(lines):
        if CUT_RE.match(line) is None:
            continue
        for index in range(cut_index + 1, len(lines)):
            command = exact_command(lines[index])
            if command.upper() == "M1002":
                break
            if not command.upper().startswith(("G0", "G1")):
                continue
            if re.search(r"\bU[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b", command, flags=re.IGNORECASE):
                post_cut_u_lines.append(index + 1)
            if command.upper().startswith("G1") and re.search(r"\bV[-+]?(?:\d+(?:\.\d*)?|\.\d+)\b", command, flags=re.IGNORECASE):
                post_cut_v_only_moves += 1
    if post_cut_u_lines:
        add_failure(failures, f"post-cut tail moves still advance U fiber axis at lines {post_cut_u_lines[:8]}")
    if route_count > 0 and post_cut_v_only_moves <= 0:
        add_failure(failures, "no V-only post-cut tail moves found after CUT DISTANCE")

    unique_cut_distances = sorted(set(cut_distances))
    if len(unique_cut_distances) != 1:
        add_failure(failures, f"expected one CUT DISTANCE value, found {unique_cut_distances}")
    cut_distance = unique_cut_distances[0] if unique_cut_distances else None

    for key, expected in (
        ("continuous_fiber_route_count", route_count),
        ("continuous_fiber_layers", len(route_layers)),
    ):
        values = top_summary.get(key, [])
        parsed_values = {int(float(value)) for value in values if re.match(r"^-?\d+(?:\.\d+)?$", value)}
        if values and parsed_values != {expected}:
            add_failure(failures, f"{key} summary values {values} do not match {expected}")

    total_route_length = sum(float(route["length"]) for route in routes)
    used_mm_values = [
        float(value)
        for value in top_summary.get("continuous_fiber_used_mm", [])
        if re.match(r"^-?\d+(?:\.\d+)?$", value)
    ]
    if used_mm_values and any(abs(value - total_route_length) > 1.0 for value in used_mm_values):
        add_failure(failures, f"continuous_fiber_used_mm values {used_mm_values} do not match route sum {total_route_length:.3f}")

    if summary is not None:
        summary_routes = summary.get("routes", {})
        summary_config = summary.get("config", {})
        summary_command_counts = summary.get("command_counts", {})
        if summary_routes.get("count") != route_count:
            add_failure(failures, f"summary route count {summary_routes.get('count')} does not match parsed {route_count}")
        if summary_routes.get("layers_with_routes") != len(route_layers):
            add_failure(
                failures,
                f"summary fiber layers {summary_routes.get('layers_with_routes')} does not match parsed {len(route_layers)}",
            )
        if abs(float(summary_routes.get("total_length_mm", 0.0)) - total_route_length) > 1.0:
            add_failure(
                failures,
                f"summary route length {summary_routes.get('total_length_mm')} does not match parsed {total_route_length:.3f}",
            )
        if cut_distance is not None and abs(float(summary_config.get("cut_distance", cut_distance)) - cut_distance) > 0.001:
            add_failure(
                failures,
                f"summary cut distance {summary_config.get('cut_distance')} does not match emitted CUT DISTANCE {cut_distance}",
            )
        for command in ("M1001", "M1002", "M2800", "T0", "T1"):
            if int(summary_command_counts.get(command, command_counts.get(command, 0))) != command_counts.get(command, 0):
                add_failure(
                    failures,
                    f"summary command count for {command}={summary_command_counts.get(command)} "
                    f"does not match parsed {command_counts.get(command, 0)}",
                )

    t0_switches = [
        index
        for index, line in enumerate(lines)
        if line.strip() in {"T0 ; switch extruder type to:FIBER", "T0 R ; switch extruder type to:FIBER"}
    ]
    t1_switches = [index for index, line in enumerate(lines) if line.strip() == "T1 ; switch extruder type to:PLASTIC"]
    fiber_layers = [index for index, line in enumerate(lines) if line.strip().startswith("; ORCA_CODEX_FIBER_LAYER ")]
    if len(t0_switches) != len(fiber_layers):
        add_failure(failures, f"T0 fiber switch count {len(t0_switches)} does not match fiber layer count {len(fiber_layers)}")
    if len(t1_switches) != len(t0_switches) + 1:
        add_failure(failures, f"T1 plastic switch count {len(t1_switches)} should equal T0 switches plus initial plastic selection")

    for layer_index, fiber_layer_line in enumerate(fiber_layers):
        previous_boundary = fiber_layers[layer_index - 1] if layer_index else (planner_start_index or 0)
        next_boundary = fiber_layers[layer_index + 1] if layer_index + 1 < len(fiber_layers) else (planner_end_index or len(lines))
        previous_t0 = [index for index in t0_switches if previous_boundary < index < fiber_layer_line]
        next_t1 = [index for index in t1_switches if fiber_layer_line < index < next_boundary]
        if not previous_t0:
            add_failure(failures, f"fiber layer at line {fiber_layer_line + 1} has no preceding managed T0 switch")
        if not next_t1:
            add_failure(failures, f"fiber layer at line {fiber_layer_line + 1} has no following managed T1 switch")

    route_indexes = [route["index"] for route in routes]
    route_ends = route_indexes[1:] + [planner_end_index or len(lines)]
    for route, block_end in zip(routes, route_ends):
        block_start = route["index"]
        m1001_index = find_in_window(lines, block_start, block_end, lambda line: M1001_RE.match(line) is not None)
        m2800_index = find_in_window(lines, block_start, block_end, lambda line: line.strip() == "M2800")
        cut_index = find_in_window(lines, block_start, block_end, lambda line: CUT_RE.match(line) is not None)
        m1002_index = find_in_window(lines, block_start, block_end, lambda line: line.strip() == "M1002")
        if None in (m1001_index, m2800_index, cut_index, m1002_index):
            add_failure(failures, f"route at line {block_start + 1} is missing M1001/M2800/CUT/M1002")
            continue
        if not (block_start < m1001_index < m2800_index < cut_index < m1002_index < block_end):
            add_failure(failures, f"route at line {block_start + 1} has out-of-order M1001/M2800/CUT/M1002")
        if cut_distance is not None:
            load_match = M1001_RE.match(lines[m1001_index])
            emitted_load = float(load_match.group(1)) if load_match else 0.0
            required_load = math.ceil(float(route["length"]) + cut_distance)
            if emitted_load + 1e-6 < required_load:
                add_failure(
                    failures,
                    f"route at line {block_start + 1} M1001 L{emitted_load:g} is below required {required_load}",
                )

    if executable_end_index is not None:
        late_fiber_layers = [index + 1 for index, line in enumerate(lines[executable_end_index + 1 :], executable_end_index + 1) if line.strip().startswith("; ORCA_CODEX_FIBER_LAYER ")]
        if late_fiber_layers:
            add_failure(failures, f"fiber layers emitted after EXECUTABLE_BLOCK_END: {late_fiber_layers[:5]}")
        if shutdown_start_index is not None and shutdown_start_index > executable_end_index:
            add_failure(failures, "shutdown block is after EXECUTABLE_BLOCK_END")

    if require_alternation:
        required_warnings = {
            "perimeter_trace_region_phase_0",
            "perimeter_trace_region_phase_1",
            "perimeter_trace_region_core",
            "perimeter_trace_region_sector_4",
            "perimeter_trace_region_sector_7",
            "cut_window_extended_closed_route_2x_lap",
            "standalone_cut_window_min_65mm",
        }
        missing = sorted(warning for warning in required_warnings if route_warning_counts.get(warning, 0) <= 0)
        if missing:
            add_failure(failures, f"required alternating-region route warnings are missing: {missing}")

    if route_warning_counts.get("below_min_bend_radius", 0):
        advisories.append(
            f"{route_warning_counts['below_min_bend_radius']} route(s) are below the selected bend-radius quality target"
        )
    if summary is not None:
        skipped = summary.get("skipped", {})
        if skipped.get("routes_skipped_by_cut_window_min_length", 0):
            advisories.append(f"{skipped['routes_skipped_by_cut_window_min_length']} route candidate(s) were skipped by cut-window length")
        if skipped.get("routes_skipped_by_hardware_min_length", 0):
            advisories.append(f"{skipped['routes_skipped_by_hardware_min_length']} route candidate(s) were skipped by hardware minimum length")

    metrics = {
        "gcode": str(gcode_path),
        "line_count": len(lines),
        "route_count": route_count,
        "prime_blocks": prime_count,
        "fiber_layers": len(route_layers),
        "total_route_length_mm": round(total_route_length, 3),
        "cut_distance_values": unique_cut_distances,
        "command_counts": {
            key: command_counts.get(key, 0)
            for key in ("T0", "T1", "M1001", "M1002", "M2800", "M400", "M104", "M109", "M106", "M140", "M141", "M190", "M191")
        },
        "route_warning_counts": dict(sorted(route_warning_counts.items())),
        "summary_present": summary is not None,
        "post_cut_v_only_moves": post_cut_v_only_moves,
    }
    return metrics, failures, advisories


def main() -> int:
    args = parse_args()
    metrics, failures, advisories = audit_gcode(args.gcode, args.summary, args.require_alternation)
    payload = {
        "status": "fail" if failures else "pass",
        "metrics": metrics,
        "failures": failures,
        "advisories": advisories,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "FAILED" if failures else "passed"
        print(
            "FibreSeek G-code contract audit "
            f"{status}: routes={metrics['route_count']} layers={metrics['fiber_layers']} "
            f"length_mm={metrics['total_route_length_mm']} cut={metrics['cut_distance_values']}"
        )
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        for advisory in advisories:
            print(f"NOTE: {advisory}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
