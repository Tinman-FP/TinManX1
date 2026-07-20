#!/usr/bin/env python3
"""Validate the public TinManX1 FibreSeek layup editor contract."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


REPO_ROOT = find_repo_root(Path(__file__).resolve())
HELPER_PATH = REPO_ROOT / "scripts" / "source-helpers" / "build_tinmanx1_fiber_layup_payload.py"
CONTRACT_PATH = REPO_ROOT / "checks" / "contracts" / "fiber_layup_editor_contract.json"


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing contract file: {path.relative_to(REPO_ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid JSON in {path.relative_to(REPO_ROOT)}: {exc}")
    if not isinstance(data, dict):
        fail(f"{path.relative_to(REPO_ROOT)} must contain a JSON object")
    return data


def load_helper() -> Any:
    spec = importlib.util.spec_from_file_location("tinmanx1_layup_payload_helper", HELPER_PATH)
    if spec is None or spec.loader is None:
        fail(f"unable to load payload helper: {HELPER_PATH.relative_to(REPO_ROOT)}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def require_field_keys(fields: list[dict[str, Any]], expected: set[str], label: str) -> None:
    actual = {str(field.get("key")) for field in fields}
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        pieces = []
        if missing:
            pieces.append("missing " + ", ".join(missing))
        if extra:
            pieces.append("unexpected " + ", ".join(extra))
        fail(f"{label} field mismatch: {'; '.join(pieces)}")


def require_choices(fields: list[dict[str, Any]], key: str, expected: set[str]) -> None:
    field = next((item for item in fields if item.get("key") == key), None)
    if field is None:
        fail(f"contract is missing {key} field")
    actual = set(field.get("choices", []))
    if actual != expected:
        fail(f"{key} choices drifted: expected {sorted(expected)}, got {sorted(actual)}")


def full_contract_payload(helper: Any) -> dict[str, Any]:
    band = helper.normalize_band(
        {
            "name": "Full editor contract band",
            "enabled": True,
            "from_layer": 2,
            "to_layer": 80,
            "from_z": 0.4,
            "to_z": 16.0,
            "mode": "heavy",
            "pattern": "tetragrid",
            "perimeters": True,
            "infill": True,
            "spacing": 8.0,
            "density": 20.0,
            "angles": [0.0, 45.0, 90.0, 135.0],
            "layer_step": 2,
            "macro_layer_height": 0.4,
            "max_routes_per_layer": 96,
            "perimeter_routes_per_layer": 2,
            "hole_routes_per_layer": 3,
            "infill_routes_per_layer": 4,
            "priority": 50,
            "seam_position": "aligned",
            "seam_angle": 180.0,
        }
    )
    prime = helper.normalize_prime(
        {
            "enabled": True,
            "center_x": 152.5,
            "y": 8.0,
            "length": 80.0,
            "height": 0.2,
            "travel_z": 5.0,
            "dwell_ms": 250,
        }
    )
    return {"layup_bands": [band], "prime_line": prime}


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    helper = load_helper()

    if contract.get("schema") != 1:
        fail("contract schema must be 1")
    if contract.get("setting_key") != "fiber_reinforcement_payload":
        fail("contract setting_key must be fiber_reinforcement_payload")
    if contract.get("payload_key") != "layup_bands":
        fail("contract payload_key must be layup_bands")

    template_ids = {str(item.get("id")) for item in contract.get("templates", [])}
    helper_templates = set(helper.TEMPLATES)
    if template_ids != helper_templates:
        fail(f"template ids drifted: expected {sorted(helper_templates)}, got {sorted(template_ids)}")

    band_fields = contract.get("band_fields", [])
    if not isinstance(band_fields, list):
        fail("band_fields must be a list")
    expected_band_keys = helper.STRING_KEYS | helper.INT_KEYS | helper.FLOAT_KEYS | helper.BOOL_KEYS | helper.ANGLE_KEYS
    require_field_keys(band_fields, expected_band_keys, "band")
    require_choices(band_fields, "mode", helper.MODES)
    require_choices(band_fields, "pattern", helper.PATTERNS)
    require_choices(band_fields, "seam_position", helper.SEAMS)

    prime_fields = contract.get("prime_line_fields", [])
    if not isinstance(prime_fields, list):
        fail("prime_line_fields must be a list")
    expected_prime_keys = helper.PRIME_INT_KEYS | helper.PRIME_FLOAT_KEYS | helper.PRIME_BOOL_KEYS
    require_field_keys(prime_fields, expected_prime_keys, "prime_line")

    for template in sorted(helper.TEMPLATES):
        payload = {"layup_bands": [helper.normalize_band(dict(item)) for item in helper.TEMPLATES[template]]}
        helper.assert_planner_accepts(payload)
    helper.assert_planner_accepts(full_contract_payload(helper))

    print(
        "TinManX1 layup editor contract passed: "
        f"{len(template_ids)} template(s), {len(band_fields)} band field(s), "
        f"{len(prime_fields)} prime-line field(s)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
