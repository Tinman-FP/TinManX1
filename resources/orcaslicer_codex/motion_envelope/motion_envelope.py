#!/usr/bin/env python3
"""Validate and apply TinManX1 machine motion capability envelopes.

This module deliberately treats a no-skip motion test as one input, not as a
print-speed recommendation. An envelope becomes active only after a coupled
velocity/acceleration point survives repeated validation and an independent
quality limit has been recorded. Applying an envelope only lowers existing
profile values; it never raises them.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = 1
MIN_VALIDATION_ITERATIONS = 50
SUPPORTED_FIRMWARE = {"klipper"}
SUPPORTED_KINEMATICS = {"corexy"}
ACTIVE_STATUS = "active"
KNOWN_STATUSES = {"draft", "motion-validated", ACTIVE_STATUS}

MODE_FACTORS = {
    "Tank": {"speed": 0.55, "acceleration": 0.50},
    "Quality": {"speed": 0.65, "acceleration": 0.60},
    "Fast": {"speed": 0.80, "acceleration": 0.78},
    "Draft": {"speed": 0.90, "acceleration": 0.88},
}

QUALITY_SPEED_KEYS = {
    "outer_wall_speed",
    "small_perimeter_speed",
    "top_surface_speed",
    "bridge_speed",
    "initial_layer_speed",
}
GENERAL_SPEED_KEYS = {
    "inner_wall_speed",
    "sparse_infill_speed",
    "internal_solid_infill_speed",
    "gap_infill_speed",
    "support_speed",
    "support_interface_speed",
    "travel_speed",
}
QUALITY_ACCELERATION_KEYS = {
    "outer_wall_acceleration",
    "top_surface_acceleration",
    "bridge_acceleration",
    "initial_layer_acceleration",
    "initial_layer_travel_acceleration",
}
GENERAL_ACCELERATION_KEYS = {
    "default_acceleration",
    "inner_wall_acceleration",
    "internal_solid_infill_acceleration",
    "sparse_infill_acceleration",
    "travel_acceleration",
}
MACHINE_SPEED_KEYS = {
    "machine_max_speed_x",
    "machine_max_speed_y",
}
MACHINE_ACCELERATION_KEYS = {
    "machine_max_acceleration_x",
    "machine_max_acceleration_y",
    "machine_max_acceleration_extruding",
    "machine_max_acceleration_retracting",
    "machine_max_acceleration_travel",
}


class EnvelopeError(ValueError):
    """Raised when an envelope could produce an unsafe or ambiguous result."""


@dataclass(frozen=True)
class MotionCaps:
    envelope_id: str
    hard_velocity_mm_s: float
    hard_acceleration_mm_s2: float
    quality_velocity_mm_s: float
    quality_acceleration_mm_s2: float
    process_velocity_mm_s: float
    process_acceleration_mm_s2: float

    def as_dict(self) -> dict[str, float | str]:
        return {
            "envelope_id": self.envelope_id,
            "hard_velocity_mm_s": self.hard_velocity_mm_s,
            "hard_acceleration_mm_s2": self.hard_acceleration_mm_s2,
            "quality_velocity_mm_s": self.quality_velocity_mm_s,
            "quality_acceleration_mm_s2": self.quality_acceleration_mm_s2,
            "process_velocity_mm_s": self.process_velocity_mm_s,
            "process_acceleration_mm_s2": self.process_acceleration_mm_s2,
        }


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EnvelopeError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EnvelopeError(f"{label} must be a non-empty string")
    return value.strip()


def _number(value: Any, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EnvelopeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result) or result <= minimum:
        raise EnvelopeError(f"{label} must be greater than {minimum:g}")
    return result


def _factor(value: Any, label: str, *, minimum: float, maximum: float) -> float:
    result = _number(value, label)
    if result < minimum or result > maximum:
        raise EnvelopeError(f"{label} must be between {minimum:g} and {maximum:g}")
    return result


def _normalized_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def _timestamp(value: Any, label: str) -> datetime:
    text = _text(value, label)
    normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise EnvelopeError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise EnvelopeError(f"{label} must include a timezone")
    if parsed.astimezone(timezone.utc) > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise EnvelopeError(f"{label} cannot be in the future")
    return parsed


def _point_signature(point: dict[str, Any]) -> tuple[float, float]:
    return (
        _number(point.get("velocity_mm_s"), "coupled point velocity_mm_s"),
        _number(point.get("acceleration_mm_s2"), "coupled point acceleration_mm_s2"),
    )


def validate_envelope(envelope: dict[str, Any], *, require_active: bool = False) -> None:
    if envelope.get("schema_version") != SCHEMA_VERSION:
        raise EnvelopeError(f"schema_version must be {SCHEMA_VERSION}")

    _text(envelope.get("id"), "id")
    _text(envelope.get("printer_model"), "printer_model")
    status = _normalized_token(envelope.get("status"))
    if status not in KNOWN_STATUSES:
        raise EnvelopeError(f"status must be one of {sorted(KNOWN_STATUSES)}")
    if require_active and status != ACTIVE_STATUS:
        raise EnvelopeError("envelope is not active")

    firmware = _normalized_token(envelope.get("firmware"))
    kinematics = _normalized_token(envelope.get("kinematics"))
    if firmware not in SUPPORTED_FIRMWARE:
        raise EnvelopeError("only Klipper envelopes are currently supported")
    if kinematics not in SUPPORTED_KINEMATICS:
        raise EnvelopeError("only CoreXY envelopes are currently supported")

    hardware = _object(envelope.get("hardware"), "hardware")
    _text(hardware.get("toolhead"), "hardware.toolhead")
    _text(hardware.get("hotend"), "hardware.hotend")
    _text(hardware.get("nozzle_type"), "hardware.nozzle_type")
    _text(hardware.get("belt_state"), "hardware.belt_state")
    _text(hardware.get("run_current"), "hardware.run_current")
    _number(hardware.get("nozzle_diameter_mm"), "hardware.nozzle_diameter_mm")

    if status == "draft":
        return

    conditions = _object(envelope.get("test_conditions"), "test_conditions")
    cruise_ratio = conditions.get("minimum_cruise_ratio")
    if isinstance(cruise_ratio, bool) or not isinstance(cruise_ratio, (int, float)):
        raise EnvelopeError("test_conditions.minimum_cruise_ratio must be numeric")
    if not math.isclose(float(cruise_ratio), 0.0, abs_tol=1e-9):
        raise EnvelopeError("minimum_cruise_ratio must be 0 during motion validation")
    if conditions.get("heat_soaked") is not True:
        raise EnvelopeError("motion validation must be performed after heat soak")

    points = envelope.get("coupled_points")
    if not isinstance(points, list) or not points:
        raise EnvelopeError("coupled_points must contain validation results")
    passed_signatures: set[tuple[float, float]] = set()
    for index, raw_point in enumerate(points):
        point = _object(raw_point, f"coupled_points[{index}]")
        signature = _point_signature(point)
        iterations = point.get("iterations")
        if isinstance(iterations, bool) or not isinstance(iterations, int):
            raise EnvelopeError(f"coupled_points[{index}].iterations must be an integer")
        if point.get("passed") is True and iterations >= MIN_VALIDATION_ITERATIONS:
            passed_signatures.add(signature)

    selected = _object(envelope.get("selected_coupled_point"), "selected_coupled_point")
    selected_signature = _point_signature(selected)
    if selected_signature not in passed_signatures:
        raise EnvelopeError(
            "selected_coupled_point must exactly match a passing coupled point "
            f"validated for at least {MIN_VALIDATION_ITERATIONS} iterations"
        )

    safety = _object(envelope.get("safety"), "safety")
    _factor(safety.get("motion_factor"), "safety.motion_factor", minimum=0.50, maximum=0.90)
    _factor(safety.get("quality_factor"), "safety.quality_factor", minimum=0.50, maximum=1.00)

    if status != ACTIVE_STATUS:
        return

    quality = _object(envelope.get("quality_limit"), "quality_limit")
    _number(quality.get("velocity_mm_s"), "quality_limit.velocity_mm_s")
    _number(quality.get("acceleration_mm_s2"), "quality_limit.acceleration_mm_s2")
    _text(quality.get("source"), "quality_limit.source")
    _timestamp(envelope.get("calibrated_at"), "calibrated_at")


def envelope_matches(envelope: dict[str, Any], printer_model: str, nozzle: str | float) -> bool:
    if _normalized_token(envelope.get("status")) != ACTIVE_STATUS:
        return False
    if str(envelope.get("printer_model", "")).strip() != printer_model.strip():
        return False
    hardware = envelope.get("hardware")
    if not isinstance(hardware, dict):
        return False
    try:
        return math.isclose(float(hardware.get("nozzle_diameter_mm")), float(nozzle), abs_tol=1e-6)
    except (TypeError, ValueError):
        return False


def derive_caps(envelope: dict[str, Any], mode: str) -> MotionCaps:
    validate_envelope(envelope, require_active=True)
    if mode not in MODE_FACTORS:
        raise EnvelopeError(f"unknown process mode: {mode}")

    selected = envelope["selected_coupled_point"]
    quality = envelope["quality_limit"]
    safety = envelope["safety"]
    hard_velocity = float(selected["velocity_mm_s"]) * float(safety["motion_factor"])
    hard_acceleration = float(selected["acceleration_mm_s2"]) * float(safety["motion_factor"])
    quality_velocity = min(
        hard_velocity,
        float(quality["velocity_mm_s"]) * float(safety["quality_factor"]),
    )
    quality_acceleration = min(
        hard_acceleration,
        float(quality["acceleration_mm_s2"]) * float(safety["quality_factor"]),
    )
    factors = MODE_FACTORS[mode]
    return MotionCaps(
        envelope_id=str(envelope["id"]),
        hard_velocity_mm_s=hard_velocity,
        hard_acceleration_mm_s2=hard_acceleration,
        quality_velocity_mm_s=quality_velocity,
        quality_acceleration_mm_s2=quality_acceleration,
        process_velocity_mm_s=hard_velocity * factors["speed"],
        process_acceleration_mm_s2=hard_acceleration * factors["acceleration"],
    )


def _cap_scalar(value: Any, limit: float) -> Any:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return min(value, round(limit))
    if not isinstance(value, str) or value.endswith("%"):
        return value
    try:
        numeric = float(value)
    except ValueError:
        return value
    capped = min(numeric, limit)
    return str(int(round(capped))) if numeric.is_integer() else f"{capped:g}"


def _cap_vector(value: Any, limit: float) -> Any:
    if not isinstance(value, list):
        return value
    return [_cap_scalar(item, limit) for item in value]


def apply_process_caps(profile: dict[str, Any], caps: MotionCaps) -> dict[str, Any]:
    result = dict(profile)
    for key in QUALITY_SPEED_KEYS:
        if key in result:
            result[key] = _cap_scalar(result[key], caps.quality_velocity_mm_s)
    for key in GENERAL_SPEED_KEYS:
        if key in result:
            result[key] = _cap_scalar(result[key], caps.process_velocity_mm_s)
    for key in QUALITY_ACCELERATION_KEYS:
        if key in result:
            result[key] = _cap_scalar(result[key], caps.quality_acceleration_mm_s2)
    for key in GENERAL_ACCELERATION_KEYS:
        if key in result:
            result[key] = _cap_scalar(result[key], caps.process_acceleration_mm_s2)
    return result


def apply_machine_caps(profile: dict[str, Any], caps: MotionCaps) -> dict[str, Any]:
    result = dict(profile)
    for key in MACHINE_SPEED_KEYS:
        if key in result:
            result[key] = _cap_vector(result[key], caps.hard_velocity_mm_s)
    for key in MACHINE_ACCELERATION_KEYS:
        if key in result:
            result[key] = _cap_vector(result[key], caps.hard_acceleration_mm_s2)
    return result


def load_registry(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA_VERSION:
        raise EnvelopeError(f"registry schema_version must be {SCHEMA_VERSION}")
    envelopes = data.get("envelopes")
    if not isinstance(envelopes, list):
        raise EnvelopeError("registry envelopes must be a list")
    seen: set[str] = set()
    for index, envelope in enumerate(envelopes):
        if not isinstance(envelope, dict):
            raise EnvelopeError(f"envelopes[{index}] must be an object")
        validate_envelope(envelope)
        envelope_id = str(envelope["id"])
        if envelope_id in seen:
            raise EnvelopeError(f"duplicate envelope id: {envelope_id}")
        seen.add(envelope_id)
    return envelopes


def find_active_envelope(
    envelopes: Iterable[dict[str, Any]], printer_model: str, nozzle: str | float
) -> dict[str, Any] | None:
    matches = [item for item in envelopes if envelope_matches(item, printer_model, nozzle)]
    if len(matches) > 1:
        raise EnvelopeError(
            f"multiple active envelopes match {printer_model} {float(nozzle):g} mm"
        )
    return matches[0] if matches else None


def draft_envelope(printer_model: str, nozzle: float) -> dict[str, Any]:
    slug = "-".join(printer_model.lower().replace("_", " ").split())
    return {
        "schema_version": SCHEMA_VERSION,
        "id": f"{slug}-{nozzle:g}mm-draft",
        "printer_model": printer_model,
        "firmware": "klipper",
        "kinematics": "corexy",
        "status": "draft",
        "calibrated_at": "",
        "hardware": {
            "toolhead": "RECORD BEFORE TESTING",
            "hotend": "RECORD BEFORE TESTING",
            "nozzle_diameter_mm": nozzle,
            "nozzle_type": "RECORD BEFORE TESTING",
            "belt_state": "RECORD TENSION AND SERVICE STATE",
            "run_current": "RECORD X/Y DRIVER CURRENT",
        },
        "test_conditions": {
            "minimum_cruise_ratio": 0.0,
            "heat_soaked": False,
        },
        "coupled_points": [],
        "selected_coupled_point": {},
        "quality_limit": {},
        "safety": {"motion_factor": 0.80, "quality_factor": 0.85},
    }


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate an envelope registry")
    validate_parser.add_argument("registry", type=Path)

    new_parser = subparsers.add_parser("new", help="Create a fail-closed draft envelope")
    new_parser.add_argument("--printer-model", required=True)
    new_parser.add_argument("--nozzle", required=True, type=float)
    new_parser.add_argument("--output", required=True, type=Path)

    report_parser = subparsers.add_parser("report", help="Report active caps for a machine mode")
    report_parser.add_argument("registry", type=Path)
    report_parser.add_argument("--printer-model", required=True)
    report_parser.add_argument("--nozzle", required=True, type=float)
    report_parser.add_argument("--mode", choices=tuple(MODE_FACTORS), required=True)

    args = parser.parse_args()
    if args.command == "validate":
        envelopes = load_registry(args.registry)
        active = sum(_normalized_token(item.get("status")) == ACTIVE_STATUS for item in envelopes)
        print(f"valid motion-envelope registry: {len(envelopes)} envelopes, {active} active")
        return 0
    if args.command == "new":
        write_json(args.output, draft_envelope(args.printer_model, args.nozzle))
        print(f"wrote fail-closed draft envelope: {args.output}")
        return 0

    envelopes = load_registry(args.registry)
    envelope = find_active_envelope(envelopes, args.printer_model, args.nozzle)
    if envelope is None:
        raise EnvelopeError("no matching active envelope")
    print(json.dumps(derive_caps(envelope, args.mode).as_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (EnvelopeError, OSError, json.JSONDecodeError) as exc:
        print(f"motion-envelope error: {exc}", file=sys.stderr)
        raise SystemExit(2)
