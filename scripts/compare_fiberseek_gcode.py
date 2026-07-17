#!/usr/bin/env python3
"""Compare Rocket and TinManX1 FibreSeek G-code without importing Rocket assets.

The goal is a neutral validation report: command families, thermal setpoints,
tool ownership, cut/load behavior, fiber route metadata, and high-level print
summary values. TinManX1's stricter contract audit remains the source of truth
for whether TinManX1 output is release-safe.
"""

from __future__ import annotations

import argparse
import json
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
    r"^\s*;\s*ORCA_CODEX_FIBER_ROUTE\s+"
    r"layer=(?P<layer>\d+)\s+z=(?P<z>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"kind=(?P<kind>\S+)\s+length=(?P<length>[-+]?(?:\d+(?:\.\d*)?|\.\d+))\s+"
    r"warnings=(?P<warnings>.*)\s*$"
)
SUMMARY_RE = re.compile(r"^\s*;\s*([^:=]+?)\s*[:=]\s*(.+?)\s*$")
TEMP_COMMAND_RE = re.compile(r"^\s*(M10[49]|M1[49]0|M19[01])\b(?P<body>[^;]*)", re.IGNORECASE)
PARAM_RE = re.compile(r"\b([A-Z])([-+]?(?:\d+(?:\.\d*)?|\.\d+))\b", re.IGNORECASE)
TIME_VALUE_RE = re.compile(
    r"(?:(?P<hours>\d+(?:\.\d+)?)\s*h(?:ours?)?)?\s*"
    r"(?:(?P<minutes>\d+(?:\.\d+)?)\s*m(?:in(?:utes?)?)?)?\s*"
    r"(?:(?P<seconds>\d+(?:\.\d+)?)\s*s(?:ec(?:onds?)?)?)?",
    re.IGNORECASE,
)

CRITICAL_COMMANDS = (
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
    parser.add_argument("--no-tinman-audit", action="store_true", help="Skip the TinManX1 contract audit.")
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
        stripped = line.strip()
        if stripped.startswith(";LAYER:"):
            values = parse_float_values(stripped)
            if values:
                indexes.add(int(values[0]))
        elif stripped.startswith("; ORCA_CODEX_FIBER_LAYER "):
            match = re.search(r"\blayer=(\d+)\b", stripped)
            if match:
                indexes.add(int(match.group(1)))
    return indexes


def parse_seconds(text: str) -> float | None:
    lowered = text.lower()
    if not any(token in lowered for token in ("h", "hour", "min", "sec", "s")):
        return None
    match = TIME_VALUE_RE.search(lowered)
    if not match or not any(match.groupdict().values()):
        return None
    hours = float(match.group("hours") or 0)
    minutes = float(match.group("minutes") or 0)
    seconds = float(match.group("seconds") or 0)
    return hours * 3600 + minutes * 60 + seconds


def extract_summary_number(summary: dict[str, list[str]], key_tokens: tuple[str, ...]) -> float | None:
    for key, values in summary.items():
        if all(token in key for token in key_tokens):
            for value in values:
                numbers = parse_float_values(value)
                if numbers:
                    return numbers[0]
    return None


def extract_time_seconds(summary: dict[str, list[str]]) -> float | None:
    for key, values in summary.items():
        if "time" not in key:
            continue
        for value in values:
            parsed = parse_seconds(value)
            if parsed is not None:
                return parsed
            numbers = parse_float_values(value)
            if numbers and any(unit in value.lower() for unit in ("sec", "second")):
                return numbers[0]
    return None


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
    cut_distances = parse_cut_distances(lines)
    m1001_loads = parse_m1001_loads(lines)
    layer_ids = layer_indexes(lines)
    temperatures = parse_temperatures(lines)

    return {
        "path": str(path),
        "line_count": len(lines),
        "command_counts": {command: commands.get(command, 0) for command in CRITICAL_COMMANDS},
        "all_command_counts": dict(sorted(commands.items())),
        "critical_sequence": command_sequence_signature(lines),
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
        "layers_seen": len(layer_ids),
        "temperatures": temperatures,
        "summary_values": {
            "print_time_seconds": extract_time_seconds(summary),
            "fiber_used_mm": extract_summary_number(summary, ("fiber", "used", "mm")),
            "fiber_used_g": extract_summary_number(summary, ("fiber", "used", "g")),
            "filament_used_g": extract_summary_number(summary, ("filament", "used", "g")),
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
        rocket_set = sorted({(item.get("t"), item.get("p"), round(float(item["s"]), 3)) for item in rocket_values})
        tinman_set = sorted({(item.get("t"), item.get("p"), round(float(item["s"]), 3)) for item in tinman_values})
        if rocket_set != tinman_set:
            findings.append(f"{command} setpoints differ: Rocket={rocket_set} TinManX1={tinman_set}")


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

    compare_lists("CUT DISTANCE values", rocket["cut_distance_values"], tinman["cut_distance_values"], findings)
    compare_temperature_sets(rocket, tinman, findings)

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
        ("Fiber routes", rocket["route_count"], tinman["route_count"]),
        ("Fiber layers", rocket["fiber_layers"], tinman["fiber_layers"]),
        ("Route length mm", rocket["route_length_mm"], tinman["route_length_mm"]),
        ("M1001 commands", rocket["command_counts"]["M1001"], tinman["command_counts"]["M1001"]),
        ("M2800 commands", rocket["command_counts"]["M2800"], tinman["command_counts"]["M2800"]),
        ("M1002 commands", rocket["command_counts"]["M1002"], tinman["command_counts"]["M1002"]),
        ("Cut values", rocket["cut_distance_values"], tinman["cut_distance_values"]),
        ("M1001 load total", rocket["m1001_load_total"], tinman["m1001_load_total"]),
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
        SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1
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
    print("FibreSeek G-code comparison self-test passed.")
    return 0


def main() -> int:
    args = parse_args()
    if args.self_test:
        return run_self_test()
    if args.rocket_gcode is None or args.tinmanx1_gcode is None:
        print("rocket_gcode and tinmanx1_gcode are required unless --self-test is used", file=sys.stderr)
        return 2
    payload = compare_gcodes(args.rocket_gcode, args.tinmanx1_gcode, run_tinman_audit=not args.no_tinman_audit)
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print_markdown(payload)
    return 1 if payload["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
