#!/bin/sh
''':'
unset PYTHONHOME
unset PYTHONPATH
unset PYTHONEXECUTABLE
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for PYTHON in \
  "${TINMAN_AUTO_PA_PYTHON:-}" \
  "${ORCASLICER_CODEX_PYTHON:-}" \
  "$(command -v python3 2>/dev/null)" \
  "$(command -v python3.12 2>/dev/null)" \
  "$(command -v python3.11 2>/dev/null)"
do
  if [ -n "${PYTHON}" ] && [ -x "${PYTHON}" ]; then
    exec "${PYTHON}" "$0" "$@"
  fi
done
echo "TinManX1 auto pressure advance postprocessor could not find a usable Python interpreter." >&2
exit 127
':'''
from __future__ import annotations

"""TinManX1 same-print PA/max-flow post-processing adapter.

Orca/TinManX1 post-process scripts receive a single G-code path and are expected
to mutate it in place. This adapter detects the target machine, looks for real
same-print calibration score files, and delegates the actual G-code preparation
to auto_pa.py. If fresh real scores are not present, it preserves the model G-code,
except for safety cleanup around visible lane skirts, and adds a visible audit
stamp instead of silently applying synthetic data.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
AUTO_PA = SCRIPT_DIR / "auto_pa.py"
DEFAULT_DATADIR = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
STAMP_PREFIX = "; TINMAN_AUTO_PA_POSTPROCESS"
LANE_MARKERS = (
    "tinman_auto_pa_lane",
    "tinman_pa_lane",
    "tinman_auto_pressure_advance_lane",
)
DEFAULT_LANE_EDGE_MM = 20.0
EDGE_TOLERANCE_MM = 0.75


TARGETS: dict[str, dict[str, Any]] = {
    "qidi_plus4": {
        "label": "Qidi Plus 4",
        "flavor": "m900",
        "adaptive_reference_k": 0.038,
        "old_max_flow": 20.0,
    },
    "maxez": {
        "label": "Qidi Max EZ",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 20.0,
    },
    "ratrig_vcore4_t0": {
        "label": "RatRig V-Core 4 T0",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 24.0,
    },
    "ratrig_vcore4_t1": {
        "label": "RatRig V-Core 4 T1",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 24.0,
    },
    "prusa_core_one": {
        "label": "Prusa Core One",
        "flavor": "prusa",
        "adaptive_reference_k": 0.040,
        "old_max_flow": 18.0,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, ""))
    except ValueError:
        return default


def datadir() -> Path:
    return Path(os.environ.get("ORCASLICER_CODEX_DATADIR") or DEFAULT_DATADIR).expanduser()


def cache_dir() -> Path:
    override = os.environ.get("TINMAN_AUTO_PA_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return datadir() / "tinman_auto_pa"


def parse_config_value(text: str, key: str) -> str:
    pattern = re.compile(rf"^;\s*{re.escape(key)}\s*=\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
    matches = pattern.findall(text)
    return matches[-1].strip() if matches else ""


def parse_start_value(text: str, key: str) -> str:
    pattern = re.compile(rf"\b{re.escape(key)}=([^\s;]+)", re.IGNORECASE)
    match = pattern.search(text)
    return match.group(1) if match else ""


def parse_print_start_value(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(";"):
            continue
        if stripped.upper().startswith("PRINT_START"):
            value = parse_start_value(stripped, key)
            if value:
                return value
    return parse_start_value(text[:20000], key)


def detect_target(text: str) -> tuple[str, dict[str, str]]:
    printer_settings_id = parse_config_value(text, "printer_settings_id")
    printer_model = parse_config_value(text, "printer_model")
    print_start_tool = parse_print_start_value(text, "TOOL")
    haystack = " ".join([printer_settings_id, printer_model]).lower()
    details = {
        "printer_settings_id": printer_settings_id,
        "printer_model": printer_model,
        "print_start_tool": print_start_tool,
    }
    if "qidi" in haystack and ("plus 4" in haystack or "x-plus 4" in haystack or "xplus4" in haystack):
        return "qidi_plus4", details
    if "qidimaxez" in haystack or "max ez" in haystack:
        return "maxez", details
    if "ratrig" in haystack or "v-core 4" in haystack:
        return ("ratrig_vcore4_t1" if print_start_tool == "1" else "ratrig_vcore4_t0"), details
    if "prusa" in haystack and ("core one" in haystack or "core_one" in haystack):
        return "prusa_core_one", details
    return "", details


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_name(value: str) -> str:
    lowered = value.lower()
    cleaned = re.sub(r"[^a-z0-9]+", "_", lowered)
    return re.sub(r"_+", "_", cleaned).strip("_")


def parse_bed_bounds(text: str, target: str) -> tuple[float, float, float, float] | None:
    value = parse_config_value(text, "bed_shape")
    points: list[tuple[float, float]] = []
    for x, y in re.findall(r"(-?\d+(?:\.\d+)?)x(-?\d+(?:\.\d+)?)", value):
        points.append((float(x), float(y)))
    if points:
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return min(xs), min(ys), max(xs), max(ys)
    if target.startswith("ratrig"):
        return 0.0, 0.0, 500.0, 500.0
    if target in {"qidi_plus4", "maxez"}:
        return 0.0, 0.0, 300.0, 300.0
    return None


def parse_polygon(line: str) -> list[tuple[float, float]]:
    marker = "POLYGON="
    if marker not in line:
        return []
    raw = line.split(marker, 1)[1]
    numbers = [float(value) for value in re.findall(r"-?\d+(?:\.\d+)?", raw)]
    return list(zip(numbers[0::2], numbers[1::2]))


def bbox(points: list[tuple[float, float]]) -> tuple[float, float, float, float] | None:
    if not points:
        return None
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def parse_exclude_objects(text: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        if not stripped.startswith("EXCLUDE_OBJECT_DEFINE "):
            continue
        name_match = re.search(r"\bNAME=([^\s]+)", stripped)
        if not name_match:
            continue
        points = parse_polygon(stripped)
        objects.append(
            {
                "line": line_no,
                "name": name_match.group(1),
                "normalized_name": normalize_name(name_match.group(1)),
                "bbox": bbox(points),
                "polygon_points": len(points),
            }
        )
    return objects


def rects_intersect(
    a: tuple[float, float, float, float],
    b: tuple[float, float, float, float],
    *,
    tolerance: float = 0.05,
) -> bool:
    return not (
        a[2] <= b[0] + tolerance
        or b[2] <= a[0] + tolerance
        or a[3] <= b[1] + tolerance
        or b[3] <= a[1] + tolerance
    )


def edge_name_for_bbox(
    bounds: tuple[float, float, float, float],
    rect: tuple[float, float, float, float],
    edge_mm: float,
) -> str:
    min_x, min_y, max_x, max_y = bounds
    x0, y0, x1, y1 = rect
    limit = edge_mm + EDGE_TOLERANCE_MM
    if y1 <= min_y + limit:
        return "front"
    if y0 >= max_y - limit:
        return "rear"
    if x1 <= min_x + limit:
        return "left"
    if x0 >= max_x - limit:
        return "right"
    return ""


def line_xy_values(line: str) -> dict[str, float]:
    if not re.match(r"^\s*G[01]\b", line, flags=re.IGNORECASE):
        return {}
    return {axis.upper(): float(value) for axis, value in re.findall(r"\b([XY])(-?\d+(?:\.\d+)?)", line, flags=re.IGNORECASE)}


def xy_outside_bounds(x: float, y: float, bounds: tuple[float, float, float, float], tolerance: float = 0.01) -> bool:
    min_x, min_y, max_x, max_y = bounds
    return x < min_x - tolerance or x > max_x + tolerance or y < min_y - tolerance or y > max_y + tolerance


def sanitize_out_of_bounds_skirts(text: str, bounds: tuple[float, float, float, float]) -> tuple[str, dict[str, Any]]:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    report: dict[str, Any] = {
        "removed_blocks": 0,
        "removed_lines": 0,
        "first_removed_line": None,
    }

    i = 0
    while i < len(lines):
        if lines[i].lstrip().lower().startswith(";type:skirt"):
            start = i
            i += 1
            while i < len(lines):
                marker = lines[i].lstrip().lower()
                if (
                    marker.startswith(";type:")
                    or marker.startswith("; printing object ")
                    or marker.startswith("exclude_object_start ")
                    or marker.startswith(";layer_change")
                    or marker.startswith("; stop printing object ")
                ):
                    break
                i += 1

            block = lines[start:i]
            last_x: float | None = None
            last_y: float | None = None
            out_of_bounds = False
            for line in block:
                values = line_xy_values(line)
                if "X" in values:
                    last_x = values["X"]
                if "Y" in values:
                    last_y = values["Y"]
                if last_x is not None and last_y is not None and values and xy_outside_bounds(last_x, last_y, bounds):
                    out_of_bounds = True
                    break

            if out_of_bounds:
                report["removed_blocks"] += 1
                report["removed_lines"] += len(block)
                if report["first_removed_line"] is None:
                    report["first_removed_line"] = start + 1
                continue

            output.extend(block)
            continue

        output.append(lines[i])
        i += 1

    if report["removed_blocks"] == 0:
        return text, report
    return "".join(output), report


def clamp_print_start_bounds(text: str, bounds: tuple[float, float, float, float]) -> tuple[str, dict[str, Any]]:
    min_x, min_y, max_x, max_y = bounds
    report: dict[str, Any] = {"changed": False, "before": {}, "after": {}}
    fields = {
        "X0": (min_x, max_x),
        "Y0": (min_y, max_y),
        "X1": (min_x, max_x),
        "Y1": (min_y, max_y),
    }

    def clamp_line(match: re.Match[str]) -> str:
        line = match.group(0)
        new_line = line
        for key, (lo, hi) in fields.items():
            value_match = re.search(rf"\b{key}=(-?\d+(?:\.\d+)?)", new_line)
            if not value_match:
                continue
            old_value = float(value_match.group(1))
            new_value = min(max(old_value, lo), hi)
            report["before"][key] = old_value
            report["after"][key] = new_value
            if new_value != old_value:
                report["changed"] = True
                new_line = re.sub(rf"\b{key}=-?\d+(?:\.\d+)?", f"{key}={new_value:g}", new_line, count=1)
        return new_line

    updated = re.sub(r"(?m)^(?!\s*;)\s*PRINT_START\b.*$", clamp_line, text, count=1)
    if not report["changed"]:
        report["before"] = {}
        report["after"] = {}
    return updated, report


def count_emitted_layers(text: str) -> int | None:
    layers: list[int] = []
    for match in re.finditer(r"(?m)^(?!\s*;)\s*_ON_LAYER_CHANGE\b[^\n;]*\bLAYER=(\d+)\b", text):
        layers.append(int(match.group(1)))
    if layers:
        return max(layers)

    layer_changes = re.findall(r"(?m)^;LAYER_CHANGE\b", text)
    return len(layer_changes) if layer_changes else None


def normalize_print_start_layer_count(text: str) -> tuple[str, dict[str, Any]]:
    actual_layers = count_emitted_layers(text)
    report: dict[str, Any] = {
        "changed": False,
        "actual": actual_layers,
        "before": None,
        "after": None,
        "updates": [],
    }
    if actual_layers is None or actual_layers <= 0:
        report["reason"] = "no_emitted_layer_count"
        return text, report

    def record_update(kind: str, old_value: int) -> None:
        report["updates"].append({"kind": kind, "before": old_value, "after": actual_layers})
        if report["before"] is None:
            report["before"] = old_value
            report["after"] = actual_layers
        if old_value != actual_layers:
            report["changed"] = True

    def normalize_print_start_line(match: re.Match[str]) -> str:
        line = match.group(0)
        value_match = re.search(r"\bTOTAL_LAYER_COUNT=(-?\d+(?:\.\d+)?)", line)
        if not value_match:
            return line
        old_value = int(float(value_match.group(1)))
        record_update("PRINT_START TOTAL_LAYER_COUNT", old_value)
        if old_value == actual_layers:
            return line
        return re.sub(r"\bTOTAL_LAYER_COUNT=-?\d+(?:\.\d+)?", f"TOTAL_LAYER_COUNT={actual_layers}", line, count=1)

    def normalize_stats_line(match: re.Match[str]) -> str:
        line = match.group(0)
        value_match = re.search(r"\bTOTAL_LAYER=(-?\d+(?:\.\d+)?)", line)
        if not value_match:
            return line
        old_value = int(float(value_match.group(1)))
        record_update("SET_PRINT_STATS_INFO TOTAL_LAYER", old_value)
        if old_value == actual_layers:
            return line
        return re.sub(r"\bTOTAL_LAYER=-?\d+(?:\.\d+)?", f"TOTAL_LAYER={actual_layers}", line, count=1)

    updated = re.sub(r"(?m)^(?!\s*;)\s*PRINT_START\w*\b.*$", normalize_print_start_line, text, count=1)
    updated = re.sub(r"(?m)^(?!\s*;)\s*SET_PRINT_STATS_INFO\b[^\n;]*\bTOTAL_LAYER=-?\d+(?:\.\d+)?[^\n]*$", normalize_stats_line, updated)
    if report["before"] is None and "reason" not in report:
        report["reason"] = "missing_layer_total_metadata"
    return updated, report


def allowed_lane_edges(target: str) -> set[str]:
    if env_flag("TINMAN_AUTO_PA_ALLOW_ANY_EDGE"):
        return set()
    if target == "qidi_plus4":
        return {"front"}
    if target == "maxez" or target.startswith("ratrig"):
        return {"rear"}
    return set()


def validate_visible_lane(text: str, target: str) -> dict[str, Any]:
    required = not env_flag("TINMAN_AUTO_PA_ALLOW_HIDDEN_LANE")
    edge_mm = env_float("TINMAN_AUTO_PA_LANE_EDGE_MM", DEFAULT_LANE_EDGE_MM)
    allowed_edges = allowed_lane_edges(target)
    result: dict[str, Any] = {
        "required": required,
        "ok": True,
        "edge_mm": edge_mm,
        "allowed_edges": sorted(allowed_edges),
        "lane_count": 0,
    }
    if not required:
        result["reason"] = "hidden_lane_allowed_by_env"
        return result

    objects = parse_exclude_objects(text)
    lanes = [obj for obj in objects if any(marker in obj["normalized_name"] for marker in LANE_MARKERS)]
    result["lane_count"] = len(lanes)
    if not lanes:
        result.update({"ok": False, "reason": "missing_visible_lane"})
        return result

    bed = parse_bed_bounds(text, target)
    if bed is None:
        result.update({"ok": False, "reason": "missing_bed_shape"})
        return result
    result["bed_bounds"] = [round(value, 4) for value in bed]

    for lane in lanes:
        rect = lane.get("bbox")
        if rect is None:
            continue
        edge = edge_name_for_bbox(bed, rect, edge_mm)
        overlaps = [
            obj["name"]
            for obj in objects
            if obj is not lane and obj.get("bbox") is not None and rects_intersect(rect, obj["bbox"])
        ]
        edge_allowed = not allowed_edges or edge in allowed_edges
        if edge and edge_allowed and not overlaps:
            return {
                **result,
                "ok": True,
                "selected": {
                    "name": lane["name"],
                    "line": lane["line"],
                    "bbox": [round(value, 4) for value in rect],
                    "edge": edge,
                    "polygon_points": lane["polygon_points"],
                },
            }
        lane["edge"] = edge
        lane["edge_allowed"] = edge_allowed
        lane["overlaps"] = overlaps[:8]

    wrong_edge = any(lane.get("edge") and not lane.get("edge_allowed") for lane in lanes)
    result.update(
        {
            "ok": False,
            "reason": "lane_wrong_edge_for_target" if wrong_edge else "lane_not_in_edge_strip_or_overlaps_model",
            "lanes": lanes[:8],
        }
    )
    return result


def score_context(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("calibration_context", "context", "model_context", "metadata"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def score_allowed(path: Path) -> tuple[bool, str]:
    data = read_json(path)
    context = score_context(data)
    if env_flag("TINMAN_AUTO_PA_ALLOW_SYNTHETIC"):
        return True, "allowed_by_env"
    if data.get("synthetic") is True or context.get("synthetic") is True:
        return False, "synthetic"
    origin = str(context.get("score_origin") or data.get("score_origin") or "").lower()
    if origin == "real":
        return True, "real"
    if origin == "manual" and env_flag("TINMAN_AUTO_PA_ALLOW_MANUAL"):
        return True, "manual_allowed_by_env"
    if not origin:
        return False, "missing_score_origin"
    return False, f"unsupported_score_origin:{origin}"


def candidate_score_paths(target: str, kind: str) -> list[Path]:
    base = cache_dir()
    names = {
        "pa": ["latest_pa_score.json", "latest_beacon_pa_score.json", "pa_score.latest.json"],
        "maxflow": ["latest_maxflow_score.json", "latest_flow_score.json", "maxflow_score.latest.json"],
    }[kind]
    paths: list[Path] = []
    for name in names:
        paths.append(base / target / name)
        paths.append(base / name.replace("latest_", f"{target}_latest_"))
    override = os.environ.get(f"TINMAN_AUTO_PA_{kind.upper()}_SCORE")
    if override:
        paths.insert(0, Path(override).expanduser())
    return paths


def find_score(target: str, kind: str) -> tuple[str, str]:
    rejected: list[str] = []
    for path in candidate_score_paths(target, kind):
        if not path.exists():
            continue
        allowed, reason = score_allowed(path)
        if allowed:
            return str(path), reason
        rejected.append(f"{path}:{reason}")
    return "", ";".join(rejected)


def strip_previous_stamps(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.startswith(STAMP_PREFIX)
    ) + ("\n" if text.endswith("\n") else "")


def parse_previous_stamp(text: str) -> dict[str, str]:
    for line in text.splitlines():
        if not line.startswith(STAMP_PREFIX):
            continue
        fields: dict[str, str] = {}
        for token in line[len(STAMP_PREFIX):].strip().split():
            if "=" not in token:
                continue
            key, value = token.split("=", 1)
            fields[key] = value
        return fields
    return {}


def stamp_file(gcode: Path, fields: dict[str, Any]) -> None:
    text = strip_previous_stamps(gcode.read_text(errors="replace"))
    field_text = " ".join(f"{key}={value}" for key, value in fields.items() if value not in (None, ""))
    stamp = f"{STAMP_PREFIX} {field_text}".rstrip() + "\n"
    if text.startswith("; HEADER_BLOCK_START\n"):
        text = text.replace("; HEADER_BLOCK_START\n", "; HEADER_BLOCK_START\n" + stamp, 1)
    else:
        text = stamp + text
    gcode.write_text(text)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_prepare(gcode: Path, target: str, target_config: dict[str, Any], pa_score: str, maxflow_score: str) -> tuple[int, str, str, Path, Path]:
    output = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.gcode")
    report = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa_prepare.json")
    for path in (output, report):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    cmd = [
        sys.executable,
        str(AUTO_PA),
        "same-print-prepare",
        "--model-input",
        str(gcode),
        "--output",
        str(output),
        "--report",
        str(report),
        "--flavor",
        str(target_config["flavor"]),
        "--adaptive-reference-k",
        str(target_config["adaptive_reference_k"]),
        "--old-max-flow",
        str(target_config["old_max_flow"]),
    ]
    if pa_score:
        cmd.extend(["--pa-score", pa_score])
    else:
        cmd.append("--no-fixed-pa")
    if maxflow_score:
        cmd.extend(["--maxflow-score", maxflow_score])
    else:
        cmd.append("--no-flow-governor")
    if env_flag("TINMAN_AUTO_PA_ALLOW_SYNTHETIC"):
        cmd.append("--allow-synthetic-scores")
    if env_flag("TINMAN_AUTO_PA_ALLOW_MISSING_METADATA"):
        cmd.append("--allow-missing-score-metadata")
    if env_flag("TINMAN_AUTO_PA_ALLOW_MISMATCHED_CONTEXT"):
        cmd.append("--allow-mismatched-score-context")
    if env_flag("TINMAN_AUTO_PA_ALLOW_STALE"):
        cmd.append("--allow-stale-scores")
    if env_flag("TINMAN_AUTO_PA_ANNOTATE"):
        cmd.append("--annotate")
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr, output, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TinManX1 same-print PA/max-flow postprocessor")
    parser.add_argument("gcode", type=Path)
    args = parser.parse_args(argv)

    gcode = args.gcode.resolve()
    report_path = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.json")
    report: dict[str, Any] = {
        "kind": "tinman_auto_pa_postprocess_report",
        "version": 1,
        "gcode": str(gcode),
        "captured_at": utc_now(),
        "status": "unknown",
    }
    if not gcode.exists():
        report["status"] = "error_missing_gcode"
        write_report(report_path, report)
        return 2
    if env_flag("TINMAN_AUTO_PA_DISABLE"):
        report["status"] = "disabled"
        stamp_file(gcode, {"status": "disabled"})
        write_report(report_path, report)
        return 0
    if not AUTO_PA.exists():
        report["status"] = "deferred_missing_auto_pa"
        stamp_file(gcode, {"status": report["status"]})
        write_report(report_path, report)
        return 0

    text = gcode.read_text(errors="replace")
    previous_stamp = parse_previous_stamp(text)
    target, detected = detect_target(text)
    report["detected"] = detected
    report["target"] = target
    if not target:
        report["status"] = "skipped_unknown_target"
        write_report(report_path, report)
        return 0

    text_modified = False
    text, layer_count_report = normalize_print_start_layer_count(text)
    report["print_start_layer_count"] = layer_count_report
    if layer_count_report.get("changed"):
        text_modified = True
    layers_normalized = layer_count_report.get("changed") or previous_stamp.get("layers") == "normalized"

    visible_lane = validate_visible_lane(text, target)
    report["visible_lane"] = visible_lane
    if not visible_lane.get("ok"):
        reason = str(visible_lane.get("reason") or "invalid_visible_lane")
        report["status"] = "deferred_missing_visible_lane" if reason == "missing_visible_lane" else "deferred_visible_lane_invalid"
        if text_modified:
            gcode.write_text(text, encoding="utf-8")
        stamp_file(
            gcode,
            {
                "status": report["status"],
                "target": target,
                "lane": reason,
                "edge_mm": visible_lane.get("edge_mm"),
                "layers": "normalized" if layers_normalized else None,
            },
        )
        write_report(report_path, report)
        return 0

    bed_bounds = parse_bed_bounds(text, target)
    if bed_bounds is not None:
        text, skirt_report = sanitize_out_of_bounds_skirts(text, bed_bounds)
        text, print_start_report = clamp_print_start_bounds(text, bed_bounds) if skirt_report.get("removed_blocks") else (text, {"changed": False})
        report["skirt_sanitizer"] = skirt_report
        report["print_start_bounds"] = print_start_report
        if skirt_report.get("removed_blocks") or print_start_report.get("changed"):
            text_modified = True

    if text_modified:
        gcode.write_text(text, encoding="utf-8")

    pa_score, pa_reason = find_score(target, "pa")
    maxflow_score, maxflow_reason = find_score(target, "maxflow")
    report["pa_score"] = pa_score
    report["pa_score_reason"] = pa_reason
    report["maxflow_score"] = maxflow_score
    report["maxflow_score_reason"] = maxflow_reason
    skirt_removed = report.get("skirt_sanitizer", {}).get("removed_blocks") or previous_stamp.get("skirt") == "removed_oob"
    bounds_clamped = report.get("print_start_bounds", {}).get("changed") or previous_stamp.get("bounds") == "clamped"
    if not pa_score and not maxflow_score:
        report["status"] = "deferred_no_real_scores"
        stamp_file(
            gcode,
            {
                "status": report["status"],
                "target": target,
                "pa_score": "missing",
                "maxflow_score": "missing",
                "skirt": "removed_oob" if skirt_removed else None,
                "bounds": "clamped" if bounds_clamped else None,
                "layers": "normalized" if layers_normalized else None,
            },
        )
        write_report(report_path, report)
        return 0

    original_backup = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.original")
    shutil.copy2(gcode, original_backup)
    rc, stdout, stderr, output, prepare_report = run_prepare(
        gcode,
        target,
        TARGETS[target],
        pa_score,
        maxflow_score,
    )
    report["prepare_returncode"] = rc
    report["prepare_stdout"] = stdout
    report["prepare_stderr"] = stderr
    report["prepare_report"] = str(prepare_report)
    if rc == 0 and output.exists():
        shutil.move(str(output), str(gcode))
        report["status"] = "prepared"
        stamp_file(
            gcode,
            {
                "status": report["status"],
                "target": target,
                "pa_score": "applied" if pa_score else "missing",
                "maxflow_score": "applied" if maxflow_score else "missing",
                "skirt": "removed_oob" if skirt_removed else None,
                "bounds": "clamped" if bounds_clamped else None,
                "layers": "normalized" if layers_normalized else None,
            },
        )
        write_report(report_path, report)
        return 0

    report["status"] = "deferred_prepare_failed"
    shutil.copy2(original_backup, gcode)
    stamp_file(
        gcode,
        {
            "status": report["status"],
            "target": target,
            "strict": int(env_flag("TINMAN_AUTO_PA_STRICT")),
        },
    )
    write_report(report_path, report)
    return 1 if env_flag("TINMAN_AUTO_PA_STRICT") else 0


if __name__ == "__main__":
    sys.exit(main())
