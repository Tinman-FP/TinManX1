#!/usr/bin/env python3
"""Build validated TinManX1 FibreSeek layup payloads.

The output is intended for the `fiber_reinforcement_payload` process setting.
It keeps advanced layer/Z band data in one JSON value while avoiding hand-built
payload strings in normal workflow notes or profile experiments.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


HELPER_DIR = Path(__file__).resolve().parent
PLANNER_PATH = HELPER_DIR / "orcaslicer_codex_native_fiber_planner.py"

MODES = {"light", "medium", "heavy"}
PATTERNS = {"solid", "rhombic", "isogrid", "anisogrid", "tetragrid", "crosshatch", "grid"}
SEAMS = {"source", "nearest", "aligned", "rear", "random"}
BOOL_TRUE = {"1", "true", "yes", "on", "enabled", "enable"}
BOOL_FALSE = {"0", "false", "no", "off", "disabled", "disable"}
INT_KEYS = {
    "from_layer",
    "to_layer",
    "layer_step",
    "max_routes_per_layer",
    "perimeter_routes_per_layer",
    "hole_routes_per_layer",
    "infill_routes_per_layer",
    "priority",
}
FLOAT_KEYS = {"from_z", "to_z", "spacing", "density", "macro_layer_height", "seam_angle"}
BOOL_KEYS = {"enabled", "perimeters", "infill"}
ANGLE_KEYS = {"angles"}
STRING_KEYS = {"name", "mode", "pattern", "seam_position"}
KEY_ALIASES = {
    "label": "name",
    "start_layer": "from_layer",
    "min_layer": "from_layer",
    "end_layer": "to_layer",
    "max_layer": "to_layer",
    "start_z": "from_z",
    "min_z": "from_z",
    "end_z": "to_z",
    "max_z": "to_z",
    "generate_perimeters": "perimeters",
    "fiber_perimeters": "perimeters",
    "generate_infill": "infill",
    "fiber_infill": "infill",
    "infill_spacing": "spacing",
    "infill_density": "density",
    "fiber_angles": "angles",
    "angle_list": "angles",
    "every_n_layers": "layer_step",
    "fiber_seam_position": "seam_position",
    "fiber_seam_angle": "seam_angle",
    "hole_reinforcement_routes_per_layer": "hole_routes_per_layer",
}

PRIME_INT_KEYS = {"dwell_ms"}
PRIME_FLOAT_KEYS = {"center_x", "y", "length", "height", "travel_z"}
PRIME_BOOL_KEYS = {"enabled"}
PRIME_KEY_ALIASES = {
    "x": "center_x",
    "center_y": "y",
    "line_y": "y",
    "line_length": "length",
    "z": "height",
    "line_height": "height",
    "safe_z": "travel_z",
    "dwell": "dwell_ms",
}

TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "balanced": [
        {
            "name": "Balanced fiber",
            "from_layer": 1,
            "mode": "medium",
            "pattern": "rhombic",
            "perimeters": True,
            "infill": True,
            "priority": 10,
        }
    ],
    "perimeter-shell": [
        {
            "name": "Perimeter shell",
            "from_layer": 1,
            "mode": "medium",
            "pattern": "rhombic",
            "perimeters": True,
            "infill": False,
            "priority": 10,
        }
    ],
    "tetragrid-core": [
        {
            "name": "Tetragrid core",
            "from_layer": 1,
            "mode": "heavy",
            "pattern": "tetragrid",
            "perimeters": False,
            "infill": True,
            "spacing": 8.0,
            "max_routes_per_layer": 80,
            "priority": 10,
        }
    ],
    "first-layer-off-tetragrid": [
        {"name": "No first fiber layer", "from_layer": 1, "to_layer": 1, "enabled": False, "priority": 100},
        {
            "name": "Tetragrid after first layer",
            "from_layer": 2,
            "mode": "heavy",
            "pattern": "tetragrid",
            "perimeters": False,
            "infill": True,
            "spacing": 8.0,
            "max_routes_per_layer": 80,
            "priority": 10,
        },
    ],
}


def parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in BOOL_TRUE:
        return True
    if lowered in BOOL_FALSE:
        return False
    raise ValueError(f"expected boolean value, got {text!r}")


def split_fields(spec: str) -> list[str]:
    delimiter = ";" if ";" in spec else ","
    return [field.strip() for field in spec.split(delimiter) if field.strip()]


def parse_angles(text: str) -> list[float]:
    pieces = [item.strip() for item in text.replace("|", ",").replace("/", ",").split(",") if item.strip()]
    values = [float(item) for item in pieces]
    if not values:
        raise ValueError("angles must contain at least one value")
    return values


def normalize_key(key: str, aliases: dict[str, str]) -> str:
    return aliases.get(key.strip().lower().replace("-", "_"), key.strip().lower().replace("-", "_"))


def parse_key_value_spec(spec: str, *, prime: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {}
    int_keys = PRIME_INT_KEYS if prime else INT_KEYS
    float_keys = PRIME_FLOAT_KEYS if prime else FLOAT_KEYS
    bool_keys = PRIME_BOOL_KEYS if prime else BOOL_KEYS
    aliases = PRIME_KEY_ALIASES if prime else KEY_ALIASES
    valid_keys = int_keys | float_keys | bool_keys | (set() if prime else ANGLE_KEYS | STRING_KEYS)

    for field in split_fields(spec):
        if "=" not in field:
            raise ValueError(f"field {field!r} should be key=value")
        raw_key, raw_value = field.split("=", 1)
        key = normalize_key(raw_key, aliases)
        value = raw_value.strip()
        if key not in valid_keys:
            raise ValueError(f"unsupported {'prime-line' if prime else 'band'} key {raw_key!r}")
        if key in int_keys:
            result[key] = int(float(value))
        elif key in float_keys:
            result[key] = float(value)
        elif key in bool_keys:
            result[key] = parse_bool(value)
        elif key in ANGLE_KEYS:
            result[key] = parse_angles(value)
        else:
            result[key] = value
    return result


def normalize_band(raw: dict[str, Any]) -> dict[str, Any]:
    band = dict(raw)
    if "mode" in band:
        band["mode"] = str(band["mode"]).strip().lower()
        if band["mode"] not in MODES:
            raise ValueError(f"band {band.get('name', '<unnamed>')} has unsupported mode {band['mode']!r}")
    if "pattern" in band:
        band["pattern"] = str(band["pattern"]).strip().lower()
        if band["pattern"] not in PATTERNS:
            raise ValueError(f"band {band.get('name', '<unnamed>')} has unsupported pattern {band['pattern']!r}")
    if "seam_position" in band:
        band["seam_position"] = str(band["seam_position"]).strip().lower()
        if band["seam_position"] not in SEAMS:
            raise ValueError(f"band {band.get('name', '<unnamed>')} has unsupported seam {band['seam_position']!r}")
    for key in ("from_layer", "to_layer", "layer_step", "max_routes_per_layer"):
        if key in band and int(band[key]) < 1:
            raise ValueError(f"band {band.get('name', '<unnamed>')} {key} must be at least 1")
    if band.get("to_layer") and band.get("from_layer") and int(band["to_layer"]) < int(band["from_layer"]):
        raise ValueError(f"band {band.get('name', '<unnamed>')} to_layer is before from_layer")
    for key in ("from_z", "to_z", "spacing", "macro_layer_height"):
        if key in band and float(band[key]) < 0:
            raise ValueError(f"band {band.get('name', '<unnamed>')} {key} must be non-negative")
    if band.get("to_z") is not None and band.get("from_z") is not None and float(band["to_z"]) < float(band["from_z"]):
        raise ValueError(f"band {band.get('name', '<unnamed>')} to_z is before from_z")
    if "density" in band and not 0 <= float(band["density"]) <= 100:
        raise ValueError(f"band {band.get('name', '<unnamed>')} density must be 0-100")
    if band.get("enabled", True) and band.get("perimeters") is False and band.get("infill") is False:
        raise ValueError(f"band {band.get('name', '<unnamed>')} enables neither perimeters nor infill")
    return band


def normalize_prime(raw: dict[str, Any]) -> dict[str, Any]:
    prime = dict(raw)
    for key in PRIME_FLOAT_KEYS:
        if key in prime and float(prime[key]) < 0:
            raise ValueError(f"prime_line {key} must be non-negative")
    if "dwell_ms" in prime and int(prime["dwell_ms"]) < 0:
        raise ValueError("prime_line dwell_ms must be non-negative")
    return prime


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.band:
        bands = [parse_key_value_spec(item) for item in args.band]
    else:
        bands = [dict(item) for item in TEMPLATES[args.template]]
    payload: dict[str, Any] = {"layup_bands": [normalize_band(band) for band in bands]}
    if args.prime_line:
        payload["prime_line"] = normalize_prime(parse_key_value_spec(args.prime_line, prime=True))
    return payload


def compact_json(payload: dict[str, Any], *, pretty: bool = False) -> str:
    if pretty:
        return json.dumps(payload, indent=2, sort_keys=True)
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def load_planner_module() -> Any:
    spec = importlib.util.spec_from_file_location("tinmanx1_native_fiber_planner", PLANNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"unable to load planner module from {PLANNER_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def assert_planner_accepts(payload: dict[str, Any]) -> None:
    planner = load_planner_module()
    parsed, warnings = planner.parse_json_like_payload(compact_json(payload))
    if warnings:
        raise AssertionError(f"planner emitted payload warnings: {warnings}")
    bands = planner.normalized_layup_bands(parsed)
    if len(bands) != len(payload["layup_bands"]):
        raise AssertionError(f"planner saw {len(bands)} band(s), expected {len(payload['layup_bands'])}")


def run_self_test() -> int:
    checked = 0
    for template in TEMPLATES:
        payload = {"layup_bands": [normalize_band(dict(item)) for item in TEMPLATES[template]]}
        assert_planner_accepts(payload)
        checked += 1
    custom = {
        "layup_bands": [
            normalize_band(
                parse_key_value_spec(
                    "name=UI Core;from_layer=4;to_layer=80;mode=heavy;pattern=tetragrid;"
                    "perimeters=0;infill=1;spacing=8;angles=0,45,90,135;max_routes_per_layer=96;priority=25"
                )
            )
        ],
        "prime_line": normalize_prime(
            parse_key_value_spec("enabled=1;center_x=152.5;y=8;length=80;height=0.2;travel_z=5;dwell_ms=250", prime=True)
        ),
    }
    assert_planner_accepts(custom)
    print(f"TinManX1 layup payload helper passed: {checked} template(s) plus custom payload.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", choices=sorted(TEMPLATES), default="balanced", help="Named payload template.")
    parser.add_argument(
        "--band",
        action="append",
        help=(
            "Add one layup band as semicolon-separated key=value pairs. "
            "Example: name=Core;from_layer=4;mode=heavy;pattern=tetragrid;perimeters=0;infill=1;spacing=8"
        ),
    )
    parser.add_argument(
        "--prime-line",
        help="Optional prime_line as key=value pairs, for example: enabled=1;center_x=152.5;y=8;length=80;height=0.2",
    )
    parser.add_argument("--pretty", action="store_true", help="Print formatted JSON.")
    parser.add_argument("--as-gcode-comment", action="store_true", help="Print as a G-code config comment.")
    parser.add_argument("--show-templates", action="store_true", help="List template payloads and exit.")
    parser.add_argument("--self-test", action="store_true", help="Verify helper output against the native planner parser.")
    args = parser.parse_args()

    if args.self_test:
        return run_self_test()
    if args.show_templates:
        for name in sorted(TEMPLATES):
            print(f"{name}: {compact_json({'layup_bands': TEMPLATES[name]})}")
        return 0

    try:
        payload = build_payload(args)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    text = compact_json(payload, pretty=args.pretty)
    if args.as_gcode_comment:
        text = f"; fiber_reinforcement_payload = {text}"
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
