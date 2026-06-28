#!/usr/bin/env python3
"""Compare native FibreSeek planner outputs against public golden fixtures."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = Path(__file__).resolve().parent
DEFAULT_EXPECTED = REPO_ROOT / "checks" / "golden" / "native_fiber_planner_golden.json"
CENTER_KINDS = {
    "hole_cluster_reinforcement_loop",
    "hole_perimeter_loop",
    "hole_reinforcement_loop",
    "outer_perimeter_loop",
    "perimeter_trace",
}


sys.path.insert(0, str(HELPER_DIR))
_smoke_spec = importlib.util.spec_from_file_location(
    "tinmanx1_native_fiber_smoke",
    HELPER_DIR / "smoke_orcaslicer_codex_native_fiber_planner.py",
)
if _smoke_spec is None or _smoke_spec.loader is None:
    raise SystemExit("Unable to load native fiber smoke fixture module.")
smoke = importlib.util.module_from_spec(_smoke_spec)
_smoke_spec.loader.exec_module(smoke)
planner = smoke.planner


def mutate_internal_void(cfg: Any) -> None:
    cfg.perimeter_routes_per_layer = 0


def mutate_alternating_holes(cfg: Any) -> None:
    cfg.perimeter_routes_per_layer = 0
    cfg.hole_reinforcement_routes_per_layer = 3


FIXTURES: dict[str, dict[str, Any]] = {
    "pocket_generated_ribs": {
        "gcode": smoke.SYNTHETIC_GCODE,
        "args": {
            "angles": "0,90",
            "fiber_infill_source": "generated-ribs",
            "spacing": 10.0,
            "layer_step": 1,
            "min_route_length": 1.0,
        },
    },
    "minimum_pocket_55mm": {
        "gcode": smoke.SYNTHETIC_SHORT_POCKET_GCODE,
        "args": {
            "fiber_reinforcement_mode": "heavy",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 1,
        },
    },
    "legal_small_hole": {
        "gcode": smoke.synthetic_legal_small_hole_gcode,
        "args": {
            "fiber_reinforcement_mode": "heavy",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 1,
        },
    },
    "isolated_tiny_hole_orbit": {
        "gcode": smoke.synthetic_isolated_tiny_hole_gcode,
        "args": {
            "fiber_reinforcement_mode": "heavy",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 1,
        },
    },
    "internal_void_stitch_gear": {
        "gcode": smoke.synthetic_internal_void_stitch_gear_gcode,
        "args": {
            "fiber_reinforcement_mode": "heavy",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 1,
        },
        "mutate": mutate_internal_void,
    },
    "alternating_hole_family_medium": {
        "gcode": smoke.synthetic_alternating_hole_family_gcode,
        "args": {
            "fiber_reinforcement_mode": "medium",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 2,
        },
        "mutate": mutate_alternating_holes,
    },
    "radial_small_gear_medium": {
        "gcode": smoke.synthetic_radial_small_gear_hole_gcode,
        "args": {
            "fiber_reinforcement_mode": "medium",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
            "layer_step": 1,
        },
        "mutate": mutate_alternating_holes,
    },
    "fiberseek_contract_heavy": {
        "gcode": smoke.synthetic_fiberseek_contract_gcode,
        "args": {
            "fiber_reinforcement_mode": "heavy",
            "fiber_generate_perimeters": "1",
            "fiber_generate_infill": "0",
        },
        "emit_contract": True,
    },
}


def fixture_gcode(value: str | Callable[[], str]) -> str:
    return value() if callable(value) else value


def rounded_center(route: Any) -> list[float] | None:
    center = planner.route_spatial_center(route.points)
    if center is None:
        return None
    return [round(center[0], 3), round(center[1], 3)]


def summarize_fixture(name: str, spec: dict[str, Any], tmpdir: Path) -> dict[str, Any]:
    fixture = tmpdir / f"{name}.gcode"
    fixture.write_text(fixture_gcode(spec["gcode"]), encoding="utf-8")
    parsed = planner.parse_gcode(fixture)
    cfg = planner.planner_config(parsed, smoke.default_planner_args(**spec.get("args", {})))
    mutate = spec.get("mutate")
    if mutate is not None:
        mutate(cfg)

    routes, skipped = planner.plan_routes(parsed, cfg)
    route_summary = planner.route_summary(routes)
    by_layer: dict[int, int] = {}
    kinds_by_layer: dict[str, dict[str, int]] = {}
    lengths_by_kind: dict[str, float] = {}
    centers_by_layer: dict[str, dict[str, list[list[float]]]] = {}

    for route in routes:
        by_layer[route.layer_index] = by_layer.get(route.layer_index, 0) + 1
        layer_key = str(route.layer_index)
        kinds_by_layer.setdefault(layer_key, {})
        kinds_by_layer[layer_key][route.kind] = kinds_by_layer[layer_key].get(route.kind, 0) + 1
        lengths_by_kind[route.kind] = lengths_by_kind.get(route.kind, 0.0) + route.length
        if route.kind in CENTER_KINDS:
            center = rounded_center(route)
            if center is not None:
                centers_by_layer.setdefault(layer_key, {}).setdefault(route.kind, []).append(center)

    for by_kind in centers_by_layer.values():
        for centers in by_kind.values():
            centers.sort()

    summary: dict[str, Any] = {
        "route_summary": route_summary,
        "total_mass_g": round(planner.fiber_mass_g(route_summary["total_length_mm"], cfg), 4),
        "route_count_by_layer": {str(layer): by_layer[layer] for layer in sorted(by_layer)},
        "route_kinds_by_layer": {
            layer: dict(sorted(kinds.items()))
            for layer, kinds in sorted(kinds_by_layer.items(), key=lambda item: int(item[0]))
        },
        "length_mm_by_kind": {kind: round(length, 3) for kind, length in sorted(lengths_by_kind.items())},
        "centers_by_layer": {
            layer: dict(sorted(kinds.items()))
            for layer, kinds in sorted(centers_by_layer.items(), key=lambda item: int(item[0]))
        },
        "skipped_nonzero": {key: value for key, value in sorted(skipped.items()) if value},
    }

    if spec.get("emit_contract"):
        merged = planner.emit_append_after_layer(parsed, routes, cfg)
        summary["command_counts"] = planner.command_counts(merged)
        summary["fiber_layer_markers"] = merged.count("; ORCA_CODEX_FIBER_LAYER")
        header: dict[str, str] = {}
        for line in merged.splitlines():
            if line.startswith("; continuous_fiber_"):
                key, _, value = line[2:].partition(" = ")
                header[key] = value
        summary["summary_header"] = dict(sorted(header.items()))

    return summary


def build_snapshot() -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        return {
            "schema": 1,
            "description": "Public synthetic golden outputs for the TinManX1 native FibreSeek planner.",
            "fixtures": {
                name: summarize_fixture(name, spec, tmpdir)
                for name, spec in sorted(FIXTURES.items())
            },
        }


def compare_values(expected: Any, actual: Any, path: str, errors: list[str], tolerance: float) -> None:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path}: expected object, got {type(actual).__name__}")
            return
        expected_keys = set(expected)
        actual_keys = set(actual)
        for key in sorted(expected_keys - actual_keys):
            errors.append(f"{path}.{key}: missing actual key")
        for key in sorted(actual_keys - expected_keys):
            errors.append(f"{path}.{key}: unexpected actual key")
        for key in sorted(expected_keys & actual_keys):
            compare_values(expected[key], actual[key], f"{path}.{key}", errors, tolerance)
        return

    if isinstance(expected, list):
        if not isinstance(actual, list):
            errors.append(f"{path}: expected list, got {type(actual).__name__}")
            return
        if len(expected) != len(actual):
            errors.append(f"{path}: expected {len(expected)} item(s), got {len(actual)}")
            return
        for index, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            compare_values(expected_item, actual_item, f"{path}[{index}]", errors, tolerance)
        return

    if isinstance(expected, float):
        if not isinstance(actual, (float, int)):
            errors.append(f"{path}: expected number, got {type(actual).__name__}")
        elif abs(float(expected) - float(actual)) > tolerance:
            errors.append(f"{path}: expected {expected}, got {actual}")
        return

    if expected != actual:
        errors.append(f"{path}: expected {expected!r}, got {actual!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, default=DEFAULT_EXPECTED, help="Golden JSON path.")
    parser.add_argument("--write", action="store_true", help="Rewrite the expected golden JSON instead of comparing.")
    parser.add_argument("--print", action="store_true", help="Print the generated snapshot.")
    parser.add_argument("--tolerance", type=float, default=0.01, help="Allowed drift for rounded float values.")
    args = parser.parse_args()

    snapshot = build_snapshot()
    if args.print:
        print(json.dumps(snapshot, indent=2, sort_keys=True))

    if args.write:
        args.expected.parent.mkdir(parents=True, exist_ok=True)
        args.expected.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"wrote native fiber planner golden snapshot: {args.expected}")
        return 0

    if not args.expected.is_file():
        raise SystemExit(f"Missing golden snapshot: {args.expected}")
    expected = json.loads(args.expected.read_text(encoding="utf-8"))
    errors: list[str] = []
    compare_values(expected, snapshot, "golden", errors, args.tolerance)
    if errors:
        for error in errors[:80]:
            print(f"ERROR: {error}", file=sys.stderr)
        if len(errors) > 80:
            print(f"ERROR: ... {len(errors) - 80} more mismatch(es)", file=sys.stderr)
        print(f"Regenerate intentionally with: {Path(__file__).name} --write", file=sys.stderr)
        return 1

    fixture_count = len(snapshot["fixtures"])
    route_count = sum(item["route_summary"]["count"] for item in snapshot["fixtures"].values())
    print(f"native fiber planner golden passed: {fixture_count} fixture(s), {route_count} route(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
