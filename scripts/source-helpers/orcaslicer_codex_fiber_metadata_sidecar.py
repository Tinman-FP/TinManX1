#!/usr/bin/env python3
"""Build a FibreSeek metadata sidecar for TinManX1 integration.

This sidecar keeps continuous-fiber work visible to Preview/Summary without
making hardware-ready claims or emitting machine commands. If the full Codex
fiber preview builder is available and a plan is supplied, this script delegates
to it. Otherwise it emits a compact metadata contract from Orca config JSON.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any


DEFAULT_ROUTE = {"polymer_tool": 0, "composite_tool": 1, "fiber_drive": 2}

FIBER_METADATA_CONTRACT = {
    "id": "orcaslicer_codex_fiber_metadata_sidecar",
    "schema_version": "1.0.0",
    "contract_version": "1.0.0",
    "output_kind": "metadata_only_preview",
    "hardware_ready": False,
    "command_emission_allowed": False,
    "live_machine_side_effects": False,
    "upload_or_start_print_allowed": False,
}

COMMAND_PAYLOAD_KEYS = {
    "commands",
    "command_queue",
    "execution_commands",
    "generated_commands",
    "gcode",
    "gcode_commands",
    "machine_commands",
    "printer_commands",
    "raw_gcode",
    "start_gcode",
    "end_gcode",
    "toolchange_gcode",
    "upload_payload",
    "start_print_payload",
}

NESTED_GUARDRAIL_FALSE_KEYS = {
    "hardware_ready",
    "command_emission_allowed",
    "live_machine_side_effects",
    "upload_or_start_print_allowed",
    "upload_allowed",
    "start_print_allowed",
}

FILAMENT_TYPE_KEYS = ("filament_type", "filament_types", "filament_material", "filament_materials")
FILAMENT_SETTINGS_KEYS = (
    "filament_settings_id",
    "filament_settings_ids",
    "filament_preset_id",
    "filament_preset_ids",
    "filament_preset",
    "filament_presets",
)
FILAMENT_VENDOR_KEYS = ("filament_vendor", "filament_vendors")
FILAMENT_COLOR_KEYS = (
    "filament_colour",
    "filament_color",
    "filament_colours",
    "filament_colors",
    "default_filament_colour",
    "default_filament_color",
    "extruder_colour",
    "extruder_color",
)
NOZZLE_DIAMETER_KEYS = ("nozzle_diameter", "nozzle_diameters", "nozzle_size", "nozzle_sizes")
LANE_REVIEW_CHIP_CATEGORIES = (
    ("missing_material", "Missing material", "missing_material_lane_count"),
    ("missing_color", "Missing color", "missing_color_lane_count"),
    ("missing_nozzle", "Missing nozzle", "missing_nozzle_lane_count"),
    ("blocked_validation_gates", "Blocked validation gates", "validation_blocked_gate_count"),
)
LANE_REVIEW_CHIP_COLOR = "#FFB300"
LANE_READY_COLOR = "#1E88E5"
MATERIAL_FAMILY_ALIASES = {
    "pla": ("PLA", "pla", "none", ["pla", "pla_basic", "pla+", "pla plus"]),
    "pla_cf": ("PLA-CF", "pla", "carbon_fiber", ["pla-cf", "pla_cf", "pla cf", "carbon fiber pla", "pla carbon fiber"]),
    "petg": ("PETG", "petg", "none", ["petg"]),
    "petg_cf": ("PETG-CF", "petg", "carbon_fiber", ["petg-cf", "petg_cf", "petg cf", "carbon fiber petg", "petg carbon fiber"]),
    "abs": ("ABS", "abs", "none", ["abs"]),
    "abs_cf": ("ABS-CF", "abs", "carbon_fiber", ["abs-cf", "abs_cf", "abs cf", "carbon fiber abs", "abs carbon fiber"]),
    "asa": ("ASA", "asa", "none", ["asa"]),
    "asa_cf": ("ASA-CF", "asa", "carbon_fiber", ["asa-cf", "asa_cf", "asa cf", "carbon fiber asa", "asa carbon fiber"]),
    "pa": ("PA/Nylon", "pa", "none", ["pa", "nylon", "pa6", "pa12"]),
    "pa_cf": ("PA-CF", "pa", "carbon_fiber", ["pa-cf", "pa_cf", "pa cf", "nylon-cf", "nylon cf", "carbon fiber nylon", "nylon carbon fiber"]),
    "pa_gf": ("PA-GF", "pa", "glass_fiber", ["pa-gf", "pa_gf", "pa gf", "nylon-gf", "nylon gf", "glass fiber nylon", "nylon glass fiber"]),
    "pc": ("PC", "pc", "none", ["pc", "polycarbonate"]),
    "pc_cf": ("PC-CF", "pc", "carbon_fiber", ["pc-cf", "pc_cf", "pc cf", "polycarbonate-cf", "polycarbonate cf", "carbon fiber pc"]),
    "tpu": ("TPU", "tpu", "none", ["tpu", "flex", "flexible"]),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-json", type=Path, help="Optional Orca/TinManX1 dynamic config JSON.")
    parser.add_argument("--plan", type=Path, help="Optional TinManX1 fiber reinforcement plan JSON.")
    parser.add_argument("--audit", type=Path, help="Optional G-code audit JSON.")
    parser.add_argument("--bundle", type=Path, help="Optional compiled fiber toolpath bundle JSON.")
    parser.add_argument("--integrity", type=Path, help="Optional composite-candidate integrity report JSON.")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--external-builder", type=Path, help="Optional build_fiber_preview_overlay.py path.")
    parser.add_argument("--force-fallback", action="store_true")
    return parser.parse_args()


def read_json(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def file_artifact(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "path": "",
            "exists": False,
        }
    artifact = {
        "path": str(path),
        "exists": path.exists(),
    }
    if path.exists():
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        artifact["sha256"] = digest.hexdigest()
        artifact["size_bytes"] = path.stat().st_size
    return artifact


def input_artifacts(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "config_json": file_artifact(args.config_json),
        "plan": file_artifact(args.plan),
        "audit": file_artifact(args.audit),
        "bundle": file_artifact(args.bundle),
        "integrity": file_artifact(args.integrity),
    }


def parse_jsonish(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on", "enabled"}
    return False


def as_float(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return default
    return default


def split_vector_text(value: str) -> list[str]:
    separators = [",", ";", "\n"]
    has_separator = any(separator in value for separator in separators)
    if not has_separator:
        stripped = value.strip()
        return [stripped] if stripped else []
    values = [value]
    for separator in separators:
        values = [piece for item in values for piece in item.split(separator)]
    return [item.strip() for item in values]


def string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return ["" if item is None else str(item).strip() for item in value]
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return ["" if item is None else str(item).strip() for item in data]
        return split_vector_text(value)
    return []


def value_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            data = None
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and isinstance(data.get("values"), list):
            return data["values"]
        return split_vector_text(value)
    if value is None:
        return []
    return [value]


def config_value(config: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in config and config[key] is not None:
            return config[key]
    return None


def any_bool(value: Any) -> bool:
    return any(as_bool(item) for item in value_list(value))


def count_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def blocked_validation_gates(gates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [gate for gate in gates if isinstance(gate, dict) and gate.get("status") == "blocked"]


def blocked_validation_gate_ids(gates: list[dict[str, Any]]) -> list[str]:
    return [str(gate.get("id") or "") for gate in blocked_validation_gates(gates) if gate.get("id")]


def blocked_validation_gate_messages(gates: list[dict[str, Any]]) -> list[str]:
    return [
        str(gate.get("message") or "")
        for gate in blocked_validation_gates(gates)
        if gate.get("message")
    ]


def lane_readiness_review_chips(summary: dict[str, Any]) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []
    for chip_id, label, count_key in LANE_REVIEW_CHIP_CATEGORIES:
        count = count_value(summary.get(count_key))
        if count <= 0:
            continue
        chips.append(
            {
                "id": chip_id,
                "label": label,
                "count": count,
                "severity": "warning",
                "color": LANE_REVIEW_CHIP_COLOR,
                "source_count": count_key,
            }
        )
    return chips


def lane_readiness_review_reasons(summary: dict[str, Any]) -> list[dict[str, Any]]:
    reasons: list[dict[str, Any]] = []
    lane_index_fields = {
        "missing_material": "unknown_material_lane_indices",
        "missing_color": "missing_color_lane_indices",
        "missing_nozzle": "missing_nozzle_lane_indices",
    }
    for chip_id, label, count_key in LANE_REVIEW_CHIP_CATEGORIES:
        count = count_value(summary.get(count_key))
        if count <= 0:
            continue
        reason = {
            "id": chip_id,
            "label": label,
            "count": count,
            "severity": "warning",
            "color": LANE_REVIEW_CHIP_COLOR,
            "source_count": count_key,
            "lane_indices": [],
            "gate_ids": [],
            "messages": [],
        }
        lane_indices = summary.get(lane_index_fields.get(chip_id, ""))
        if isinstance(lane_indices, list):
            reason["lane_indices"] = lane_indices
        if chip_id == "blocked_validation_gates":
            gate_ids = summary.get("validation_blocked_gate_ids")
            messages = summary.get("validation_blocked_gate_messages")
            reason["gate_ids"] = gate_ids if isinstance(gate_ids, list) else []
            reason["messages"] = messages if isinstance(messages, list) else []
        reasons.append(reason)
    return reasons


def lane_readiness_review_chip_categories() -> list[dict[str, Any]]:
    return [
        {
            "id": chip_id,
            "label": label,
            "severity": "warning",
            "color": LANE_REVIEW_CHIP_COLOR,
            "source_count": count_key,
        }
        for chip_id, label, count_key in LANE_REVIEW_CHIP_CATEGORIES
    ]


def lane_readiness_needs_review(readiness: dict[str, Any]) -> bool:
    return (
        str(readiness.get("status") or "") == "needs_lane_review"
        or str(readiness.get("readiness_level") or "") == "needs_lane_review"
        or count_value(readiness.get("lane_readiness_review_issue_count")) > 0
        or count_value(readiness.get("validation_blocked_gate_count")) > 0
    )


def lane_readiness_review_message(summary: dict[str, Any]) -> str:
    if not lane_readiness_needs_review(summary):
        lane_count = count_value(summary.get("lane_count"))
        return f"Lane readiness is metadata-ready for {lane_count} lane(s)."

    issue_count = count_value(summary.get("lane_readiness_review_issue_count"))
    blocked_count = count_value(summary.get("validation_blocked_gate_count"))
    parts: list[str] = []
    if issue_count > 0:
        parts.append(f"{issue_count} lane metadata issue(s)")
    if blocked_count > 0:
        parts.append(f"{blocked_count} blocked validation gate(s)")
    if not parts:
        parts.append("lane readiness review required")
    return f"Lane readiness needs review: {' and '.join(parts)}."


def lane_readiness_review_severity(readiness: dict[str, Any]) -> str:
    return "warning" if lane_readiness_needs_review(readiness) else "info"


def lane_readiness_review_color(readiness: dict[str, Any]) -> str:
    return LANE_REVIEW_CHIP_COLOR if lane_readiness_needs_review(readiness) else LANE_READY_COLOR


def decorate_lane_readiness_review_fields(readiness: dict[str, Any]) -> dict[str, Any]:
    readiness["lane_readiness_review_issue_count"] = count_value(readiness.get("review_issue_count"))
    readiness["lane_readiness_review_needed"] = lane_readiness_needs_review(readiness)
    readiness["missing_material_lane_count"] = len(readiness.get("unknown_material_lane_indices", []))
    readiness["missing_color_lane_count"] = len(readiness.get("missing_color_lane_indices", []))
    readiness["missing_nozzle_lane_count"] = len(readiness.get("missing_nozzle_lane_indices", []))
    readiness["lane_readiness_review_chip_categories"] = lane_readiness_review_chip_categories()
    readiness["lane_readiness_review_chip_category_count"] = len(
        readiness["lane_readiness_review_chip_categories"]
    )
    readiness["lane_readiness_review_chips"] = lane_readiness_review_chips(readiness)
    readiness["lane_readiness_review_chip_count"] = len(readiness["lane_readiness_review_chips"])
    readiness["lane_readiness_review_reasons"] = lane_readiness_review_reasons(readiness)
    readiness["lane_readiness_review_reason_count"] = len(readiness["lane_readiness_review_reasons"])
    readiness["lane_readiness_review_message"] = lane_readiness_review_message(readiness)
    readiness["lane_readiness_review_severity"] = lane_readiness_review_severity(readiness)
    readiness["lane_readiness_review_color"] = lane_readiness_review_color(readiness)
    return readiness


def metadata_contract(existing: Any = None) -> dict[str, Any]:
    contract = dict(existing) if isinstance(existing, dict) else {}
    contract.update(FIBER_METADATA_CONTRACT)
    return contract


def normalize_lane_readiness_contract(
    value: Any,
    source: str,
    normalizations: list[str],
) -> dict[str, Any]:
    readiness = dict(value) if isinstance(value, dict) else {}
    if not readiness:
        normalizations.append("lane_readiness_summary_defaulted_needs_lane_review")

    defaults: dict[str, Any] = {
        "schema_version": "1.0.0",
        "status": "needs_lane_review",
        "readiness_level": "needs_lane_review",
        "source": source,
        "lane_count": 0,
        "independent_lane_count": 0,
        "per_toolhead_lanes": False,
        "shared_nozzle": False,
        "role_counts": {},
        "lane_kind_counts": {},
        "polymer_lane_count": 0,
        "composite_lane_count": 0,
        "continuous_fiber_lane_count": 0,
        "support_lane_count": 0,
        "unknown_material_lane_indices": [],
        "missing_color_lane_indices": [],
        "missing_nozzle_lane_indices": [],
        "validation_blocked_gate_ids": [],
        "validation_blocked_gate_messages": [],
        "review_issue_count": 0,
        "validation_blocked_gate_count": 0,
        "selected_material_count": 0,
        "color_count": 0,
        "selected_nozzle_count": 0,
    }
    for key, default in defaults.items():
        if key not in readiness or readiness.get(key) is None:
            readiness[key] = default

    for key in ("role_counts", "lane_kind_counts"):
        if not isinstance(readiness.get(key), dict):
            readiness[key] = {}
            normalizations.append(f"lane_readiness_summary.{key}_defaulted_empty")
    for key in (
        "unknown_material_lane_indices",
        "missing_color_lane_indices",
        "missing_nozzle_lane_indices",
        "validation_blocked_gate_ids",
        "validation_blocked_gate_messages",
    ):
        if not isinstance(readiness.get(key), list):
            readiness[key] = []
            normalizations.append(f"lane_readiness_summary.{key}_defaulted_empty")
    for key in (
        "lane_count",
        "independent_lane_count",
        "polymer_lane_count",
        "composite_lane_count",
        "continuous_fiber_lane_count",
        "support_lane_count",
        "review_issue_count",
        "validation_blocked_gate_count",
        "selected_material_count",
        "color_count",
        "selected_nozzle_count",
    ):
        readiness[key] = int(as_float(readiness.get(key), 0.0))

    for key, expected in (("hardware_ready", False), ("command_emission_allowed", False)):
        if readiness.get(key) != expected:
            normalizations.append(f"lane_readiness_summary.{key}_forced_false")
        readiness[key] = expected
    if readiness.get("advisory_only") is not True:
        normalizations.append("lane_readiness_summary.advisory_only_forced_true")
    readiness["advisory_only"] = True
    readiness = decorate_lane_readiness_review_fields(readiness)
    return readiness


def normalize_lane_identity_contract(value: Any, normalizations: list[str]) -> Any:
    if not isinstance(value, dict):
        return value
    normalized = dict(value)
    lane_items = normalized.get("lanes")
    if not isinstance(lane_items, list):
        return normalized
    normalized_lanes = []
    for fallback_index, item in enumerate(lane_items):
        original_item: Any = item
        if not isinstance(item, dict):
            item = {"details": {"original_lane_value": original_item}}
            normalizations.append(f"lane_contract.lane_{fallback_index}.normalized_from_non_object")
        lane = dict(item)
        lane_index = int(as_float(lane.get("lane_index"), float(fallback_index)))
        tool_index = int(as_float(lane.get("tool_index"), float(lane_index)))
        if "lane_index" not in lane or lane.get("lane_index") in (None, ""):
            lane["lane_index"] = lane_index
            normalizations.append(f"lane_contract.lane_{lane_index}.lane_index_defaulted")
        if "lane_id" not in lane or not lane.get("lane_id"):
            lane["lane_id"] = f"L{lane_index}"
            normalizations.append(f"lane_contract.lane_{lane_index}.lane_id_defaulted")
        if "role" not in lane or not lane.get("role"):
            lane["role"] = "unknown"
            normalizations.append(f"lane_contract.lane_{lane_index}.role_defaulted")
        if "lane_kind" not in lane or not lane.get("lane_kind"):
            role_text = str(lane.get("role") or "unknown")
            lane["lane_kind"] = "unknown" if role_text == "unknown" else lane_kind(role_text)
            normalizations.append(f"lane_contract.lane_{lane_index}.lane_kind_defaulted")
        if "tool_index" not in lane or lane.get("tool_index") is None or lane.get("tool_index") == "":
            lane["tool_index"] = tool_index
            normalizations.append(f"lane_contract.lane_{lane_index}.tool_index_defaulted")
        toolhead_value = lane.get("toolhead_index")
        if "toolhead_index" not in lane or toolhead_value is None or toolhead_value == "":
            lane["toolhead_index"] = tool_index
            normalizations.append(f"lane_contract.lane_{lane_index}.toolhead_index_defaulted")
        if "extruder_id" not in lane or not lane.get("extruder_id"):
            lane["extruder_id"] = f"T{int(as_float(lane.get('toolhead_index'), float(tool_index)))}"
            normalizations.append(f"lane_contract.lane_{lane_index}.extruder_id_defaulted")
        if "independent_lane" not in lane:
            lane["independent_lane"] = True
            normalizations.append(f"lane_contract.lane_{lane_index}.independent_lane_defaulted")
        for field in ("material_type", "filament_settings_id", "filament_vendor", "display_color"):
            if field not in lane or lane.get(field) is None:
                lane[field] = ""
                normalizations.append(f"lane_contract.lane_{lane_index}.{field}_defaulted")
        expected_family = infer_material_family_metadata(lane.get("material_type"), lane.get("filament_settings_id"))
        for field, expected_value in expected_family.items():
            if field not in lane or lane.get(field) is None:
                lane[field] = expected_value
                normalizations.append(f"lane_contract.lane_{lane_index}.{field}_defaulted")
            elif field == "material_family_is_filled":
                lane[field] = bool(lane.get(field, False))
        if "nozzle_diameter" not in lane or lane.get("nozzle_diameter") is None or lane.get("nozzle_diameter") == "":
            lane["nozzle_diameter"] = 0.0
            normalizations.append(f"lane_contract.lane_{lane_index}.nozzle_diameter_defaulted")
        else:
            lane["nozzle_diameter"] = as_float(lane.get("nozzle_diameter"), 0.0)
        if "display_label" not in lane or not lane.get("display_label"):
            lane["display_label"] = lane_display_label(lane)
            normalizations.append(f"lane_contract.lane_{lane_index}.display_label_defaulted")
        normalized_lanes.append(lane)
    normalized["lanes"] = normalized_lanes
    if normalized.get("lane_count") != len(normalized_lanes):
        normalized["lane_count"] = len(normalized_lanes)
        normalizations.append("lane_contract.lane_count_defaulted_from_lanes")
    return normalized


def scrub_external_command_payloads(value: Any, normalizations: list[str], path: str = "$") -> Any:
    if isinstance(value, list):
        return [
            scrub_external_command_payloads(item, normalizations, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if not isinstance(value, dict):
        return value

    scrubbed: dict[str, Any] = {}
    for key, item in value.items():
        key_text = str(key)
        normalized_key = key_text.strip().lower()
        child_path = f"{path}.{key_text}"
        if normalized_key in COMMAND_PAYLOAD_KEYS:
            normalizations.append(f"external_command_payload_removed:{child_path}")
            continue
        if path != "$" and normalized_key in NESTED_GUARDRAIL_FALSE_KEYS:
            if item is not False:
                normalizations.append(f"nested_guardrail_forced_false:{child_path}")
            scrubbed[key] = False
            continue
        scrubbed[key] = scrub_external_command_payloads(item, normalizations, child_path)
    return scrubbed


def value_at(value: Any, index: int, default: str = "") -> str:
    values = value_list(value)
    if not values:
        return default
    item = values[index] if index < len(values) else values[0] if len(values) == 1 else default
    text = str(item).strip()
    return text if text else default


def float_at(value: Any, index: int, default: float = 0.0) -> float:
    values = value_list(value)
    if not values:
        return default
    item = values[index] if index < len(values) else values[0] if len(values) == 1 else default
    return as_float(item, default)


def find_external_builder(explicit: Path | None) -> Path | None:
    env_path = os.environ.get("ORCASLICER_CODEX_FIBER_PREVIEW_BUILDER") or os.environ.get("TINMANX_FIBER_PREVIEW_BUILDER")
    candidates = [
        explicit,
        Path(env_path) if env_path else None,
        Path(__file__).resolve().parents[1] / "tools" / "build_fiber_preview_overlay.py",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        path = candidate.expanduser()
        if path.exists():
            return path.resolve()
    return None


def run_external_builder(args: argparse.Namespace, builder: Path) -> str | None:
    if args.plan is None:
        return "external builder requires --plan"
    command = [
        sys.executable,
        str(builder),
        "--plan",
        str(args.plan),
        "--out",
        str(args.out),
    ]
    for flag, path in [
        ("--audit", args.audit),
        ("--bundle", args.bundle),
        ("--integrity", args.integrity),
    ]:
        if path:
            command.extend([flag, str(path)])
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode == 0 and args.out.exists():
        return None
    return completed.stderr.strip() or completed.stdout.strip() or f"external builder exited {completed.returncode}"


def enforce_metadata_guardrails(sidecar: dict[str, Any], source: str) -> dict[str, Any]:
    normalized = dict(sidecar)
    normalizations: list[str] = list(normalized.get("orcaslicer_codex_guardrail_normalizations", [])) \
        if isinstance(normalized.get("orcaslicer_codex_guardrail_normalizations"), list) else []

    for key, value in [
        ("hardware_ready", False),
        ("command_emission_allowed", False),
        ("live_machine_side_effects", False),
        ("upload_or_start_print_allowed", False),
    ]:
        if normalized.get(key) != value:
            normalizations.append(f"{key}_forced_false")
        normalized[key] = value

    if source == "external_builder":
        normalized = scrub_external_command_payloads(normalized, normalizations)

    if normalized.get("safety_level") not in {"hardware_candidate", "polymer_only"}:
        normalizations.append("safety_level_forced_hardware_candidate")
        normalized["safety_level"] = "hardware_candidate"
    normalized["schema_version"] = str(normalized.get("schema_version") or "1.0.0")
    normalized["contract"] = metadata_contract(normalized.get("contract"))

    guardrails = normalized.get("guardrails")
    if not isinstance(guardrails, list):
        guardrails = []
    for guardrail in [
        "metadata_only_until_hardware_validated",
        "no_live_machine_commands",
        "no_upload_or_start_print",
        "preserve_normal_orca_printer_behavior",
    ]:
        if guardrail not in guardrails:
            guardrails.append(guardrail)
            normalizations.append(f"guardrail_added:{guardrail}")
    normalized["guardrails"] = guardrails

    normalized["lane_contract"] = normalize_lane_identity_contract(
        normalized.get("lane_contract"),
        normalizations,
    )
    lane_readiness = normalize_lane_readiness_contract(
        normalized.get("lane_readiness_summary"),
        source,
        normalizations,
    )
    normalized["lane_readiness_summary"] = lane_readiness
    summary = dict(normalized.get("summary")) if isinstance(normalized.get("summary"), dict) else {}
    summary["lane_readiness_status"] = lane_readiness.get("status", "needs_lane_review")
    summary["lane_readiness_level"] = lane_readiness.get("readiness_level", "needs_lane_review")
    summary["lane_readiness_review_issue_count"] = lane_readiness.get("lane_readiness_review_issue_count", 0)
    summary["lane_readiness_review_needed"] = bool(lane_readiness.get("lane_readiness_review_needed", True))
    summary["lane_readiness_review_message"] = lane_readiness.get("lane_readiness_review_message", "")
    summary["lane_readiness_review_severity"] = lane_readiness.get("lane_readiness_review_severity", "warning")
    summary["lane_readiness_review_color"] = lane_readiness.get("lane_readiness_review_color", LANE_REVIEW_CHIP_COLOR)
    summary["continuous_fiber_lane_count"] = lane_readiness.get("continuous_fiber_lane_count", 0)
    summary["polymer_lane_count"] = lane_readiness.get("polymer_lane_count", 0)
    summary["missing_material_lane_count"] = len(lane_readiness.get("unknown_material_lane_indices", []))
    summary["missing_color_lane_count"] = len(lane_readiness.get("missing_color_lane_indices", []))
    summary["missing_nozzle_lane_count"] = len(lane_readiness.get("missing_nozzle_lane_indices", []))
    summary["validation_blocked_gate_count"] = lane_readiness.get("validation_blocked_gate_count", 0)
    summary["validation_blocked_gate_ids"] = lane_readiness.get("validation_blocked_gate_ids", [])
    summary["validation_blocked_gate_messages"] = lane_readiness.get("validation_blocked_gate_messages", [])
    summary["lane_readiness_review_chip_categories"] = lane_readiness_review_chip_categories()
    summary["lane_readiness_review_chip_category_count"] = len(summary["lane_readiness_review_chip_categories"])
    summary["lane_readiness_review_chips"] = lane_readiness_review_chips(summary)
    summary["lane_readiness_review_chip_count"] = len(summary["lane_readiness_review_chips"])
    summary["lane_readiness_review_reasons"] = lane_readiness_review_reasons(summary)
    summary["lane_readiness_review_reason_count"] = len(summary["lane_readiness_review_reasons"])
    normalized["summary"] = summary

    normalized["preview_summary"] = fiber_preview_summary(normalized)
    normalized["orcaslicer_codex_guardrail_source"] = source
    normalized["orcaslicer_codex_guardrail_normalizations"] = normalizations
    return normalized


def normalize_external_sidecar(output_path: Path, source: str, artifacts: dict[str, Any]) -> str | None:
    sidecar = read_json(output_path)
    if not sidecar:
        return "external builder output was not valid JSON"
    normalized = enforce_metadata_guardrails(sidecar, source)
    normalized["input_artifacts"] = artifacts
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return None


def fiber_preview_summary(sidecar: dict[str, Any]) -> dict[str, Any]:
    """Small stable payload for Orca Preview/Summary labels."""
    summary = sidecar.get("summary") if isinstance(sidecar.get("summary"), dict) else {}
    readiness = sidecar.get("lane_readiness_summary") if isinstance(sidecar.get("lane_readiness_summary"), dict) else {}
    lane_count = count_value(summary.get("mixed_filament_lane_count", readiness.get("lane_count", 0)))
    review_needed = bool(summary.get("lane_readiness_review_needed", readiness.get("lane_readiness_review_needed", True)))
    status_message = str(
        summary.get("lane_readiness_review_message")
        or readiness.get("lane_readiness_review_message")
        or (
            f"{lane_count} independent lane metadata row(s) ready for review."
            if lane_count
            else "No FibreSeek lane metadata is active for this slice."
        )
    )
    cards = fiber_preview_status_cards(summary, readiness, lane_count, review_needed, status_message)
    return {
        "schema_version": "1.0.0",
        "component": "fiberseek_metadata",
        "label": "FibreSeek lanes",
        "status": str(sidecar.get("status") or "metadata_only"),
        "safety_level": str(sidecar.get("safety_level") or "hardware_candidate"),
        "status_message": status_message,
        "lane_count": lane_count,
        "continuous_fiber_lane_count": count_value(summary.get("continuous_fiber_lane_count", 0)),
        "filled_material_lane_count": count_value(summary.get("filled_material_lane_count", 0)),
        "lane_readiness_level": str(summary.get("lane_readiness_level") or readiness.get("readiness_level") or ""),
        "lane_readiness_review_needed": review_needed,
        "lane_readiness_review_issue_count": count_value(summary.get("lane_readiness_review_issue_count", 0)),
        "preview_status_cards": cards,
        "preview_status_card_count": len(cards),
        "hardware_ready": False,
        "command_emission_allowed": False,
        "upload_or_start_print_allowed": False,
        "advisory_only": True,
        "safety_note": "Metadata-only preview; does not emit commands, start prints, upload files, or claim hardware readiness.",
    }


def fiber_preview_status_cards(
    summary: dict[str, Any],
    readiness: dict[str, Any],
    lane_count: int,
    review_needed: bool,
    status_message: str,
) -> list[dict[str, Any]]:
    """Ready-to-render Preview/Summary rows for lane setup and metadata guardrails."""
    continuous_count = count_value(summary.get("continuous_fiber_lane_count", 0))
    blocked_count = count_value(summary.get("validation_blocked_gate_count", readiness.get("validation_blocked_gate_count", 0)))
    return [
        {
            "id": "lanes",
            "label": "Per-toolhead lanes",
            "status": str(summary.get("lane_readiness_level") or readiness.get("readiness_level") or "unavailable"),
            "severity": "warning" if review_needed else "info",
            "message": status_message,
            "count": lane_count,
            "source": "lane_readiness_summary",
        },
        {
            "id": "continuous_fiber",
            "label": "Continuous fiber lanes",
            "status": "present" if continuous_count else "not_present",
            "severity": "info",
            "message": f"{continuous_count} continuous-fiber lane(s) represented in metadata.",
            "count": continuous_count,
            "source": "lane_contract",
        },
        {
            "id": "validation",
            "label": "Validation gates",
            "status": "blocked" if blocked_count else "metadata_only",
            "severity": "warning" if blocked_count else "info",
            "message": (
                f"{blocked_count} validation gate(s) still need review."
                if blocked_count
                else "No hardware-validation gate is approved by metadata alone."
            ),
            "count": blocked_count,
            "source": "lane_readiness_summary.validation_blocked_gate_count",
        },
        {
            "id": "safety",
            "label": "Safety boundary",
            "status": "metadata_only",
            "severity": "info",
            "message": "Metadata-only preview; no commands, upload/start-print, or hardware-ready approval.",
            "count": 0,
            "source": "orcaslicer_codex_guardrails",
        },
    ]


def route_from_inputs(config: dict[str, Any], plan: dict[str, Any], machine_payload: dict[str, Any]) -> dict[str, Any]:
    route = parse_jsonish(config.get("fiber_reinforcement_payload")).get("route")
    if not isinstance(route, dict):
        route = plan.get("route") if isinstance(plan.get("route"), dict) else {}
    if not route:
        route = machine_payload.get("route") if isinstance(machine_payload.get("route"), dict) else {}
    result = dict(DEFAULT_ROUTE)
    for key in DEFAULT_ROUTE:
        if key in route:
            try:
                result[key] = int(route[key])
            except (TypeError, ValueError):
                pass
    result["plastic_nozzle_diameter"] = as_float(config.get("plastic_nozzle_diameter"), 0.0)
    result["composite_nozzle_diameter"] = as_float(config.get("composite_nozzle_diameter"), 0.0)
    return result


def lane_kind(role: str) -> str:
    normalized = role.strip().lower()
    if normalized == "fiber_drive":
        return "continuous_fiber"
    if "support" in normalized:
        return "support_material"
    if "composite" in normalized:
        return "composite_polymer"
    return "polymer"


def lane_tool_index(role: str, index: int, route: dict[str, Any]) -> int:
    normalized = role.strip().lower()
    if normalized == "fiber_drive":
        return int(route.get("fiber_drive", DEFAULT_ROUTE["fiber_drive"]))
    if "composite" in normalized:
        return int(route.get("composite_tool", index))
    if normalized == "polymer":
        return int(route.get("polymer_tool", index))
    return index


def lane_color(config: dict[str, Any], index: int) -> str:
    return value_at(config_value(config, FILAMENT_COLOR_KEYS), index)


def selected_count(values: list[str]) -> int:
    return len({value for value in values if value})


def normalize_material_family_text(value: Any) -> str:
    return str(value or "").lower().replace("_", " ").replace("-", " ").strip()


def material_family_alias_candidates() -> list[tuple[str, str, str, str, str]]:
    candidates: list[tuple[str, str, str, str, str]] = []
    for family_key, (label, base_polymer, reinforcement_type, aliases) in MATERIAL_FAMILY_ALIASES.items():
        for alias in aliases:
            normalized = normalize_material_family_text(alias)
            if normalized:
                candidates.append((normalized, family_key, label, base_polymer, reinforcement_type))
    return sorted(candidates, key=lambda item: len(item[0]), reverse=True)


def unknown_material_family_metadata(source_text: str = "") -> dict[str, Any]:
    return {
        "material_family_key": "",
        "material_family_label": "",
        "material_family_source_material_text": source_text,
        "material_family_matched_alias": "",
        "material_family_base_polymer": "",
        "material_family_reinforcement_type": "none",
        "material_family_is_filled": False,
    }


def infer_material_family_metadata(*source_texts: Any) -> dict[str, Any]:
    flattened_sources = [str(item).strip() for item in source_texts if str(item or "").strip()]
    for source_text in flattened_sources:
        normalized_source = normalize_material_family_text(source_text)
        for alias, family_key, label, base_polymer, reinforcement_type in material_family_alias_candidates():
            if alias in normalized_source:
                return {
                    "material_family_key": family_key,
                    "material_family_label": label,
                    "material_family_source_material_text": source_text,
                    "material_family_matched_alias": alias,
                    "material_family_base_polymer": base_polymer,
                    "material_family_reinforcement_type": reinforcement_type,
                    "material_family_is_filled": reinforcement_type != "none",
                }
    return unknown_material_family_metadata(flattened_sources[0] if flattened_sources else "")


def decorate_lane_material_family(lane: dict[str, Any]) -> dict[str, Any]:
    fiber_material = lane.get("fiber_material") if isinstance(lane.get("fiber_material"), dict) else {}
    lane.update(
        infer_material_family_metadata(
            lane.get("material_type"),
            lane.get("filament_settings_id"),
            fiber_material.get("name"),
        )
    )
    return lane


def lane_material_label(lane: dict[str, Any]) -> str:
    fiber_material = lane.get("fiber_material") if isinstance(lane.get("fiber_material"), dict) else {}
    for value in (
        lane.get("filament_settings_id"),
        lane.get("material_type"),
        fiber_material.get("name"),
        lane.get("role"),
    ):
        if value:
            return str(value)
    return "Unknown material"


def lane_display_label(lane: dict[str, Any]) -> str:
    lane_index = int(as_float(lane.get("lane_index"), 0.0))
    toolhead_index = int(as_float(lane.get("toolhead_index"), as_float(lane.get("tool_index"), float(lane_index))))
    extruder_id = str(lane.get("extruder_id") or f"T{toolhead_index}")
    lane_id = str(lane.get("lane_id") or f"L{lane_index}")
    return f"{extruder_id} / {lane_id} - {lane_material_label(lane)}"


def material_palette(lane_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    palette: list[dict[str, Any]] = []
    for lane in lane_items:
        palette.append(
            {
                "label": lane_material_label(lane),
                "color": str(lane.get("display_color") or ""),
                "lane_id": str(lane.get("lane_id") or f"L{int(as_float(lane.get('lane_index'), 0.0))}"),
                "tool_index": int(as_float(lane.get("tool_index"), as_float(lane.get("lane_index"), 0.0))),
                "toolhead_index": int(as_float(lane.get("toolhead_index"), as_float(lane.get("tool_index"), 0.0))),
                "extruder_id": str(lane.get("extruder_id") or f"T{int(as_float(lane.get('toolhead_index'), as_float(lane.get('tool_index'), 0.0)))}"),
                "display_label": str(lane.get("display_label") or lane_display_label(lane)),
                "nozzle_diameter": as_float(lane.get("nozzle_diameter"), 0.0),
                "material_type": str(lane.get("material_type") or ""),
                "filament_settings_id": str(lane.get("filament_settings_id") or ""),
                "material_family_key": str(lane.get("material_family_key") or ""),
                "material_family_label": str(lane.get("material_family_label") or ""),
                "material_family_base_polymer": str(lane.get("material_family_base_polymer") or ""),
                "material_family_reinforcement_type": str(lane.get("material_family_reinforcement_type") or "none"),
                "material_family_is_filled": bool(lane.get("material_family_is_filled", False)),
            }
        )
    return palette


def lane_badges(lane_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    badges: list[dict[str, Any]] = []
    for lane in lane_items:
        lane_index = int(as_float(lane.get("lane_index"), 0.0))
        tool_index = int(as_float(lane.get("tool_index"), float(lane_index)))
        toolhead_index = int(as_float(lane.get("toolhead_index"), float(tool_index)))
        badges.append(
            {
                "lane_index": lane_index,
                "lane_id": str(lane.get("lane_id") or f"L{lane_index}"),
                "toolhead_index": toolhead_index,
                "extruder_id": str(lane.get("extruder_id") or f"T{toolhead_index}"),
                "label": str(lane.get("display_label") or lane_display_label(lane)),
                "material_label": lane_material_label(lane),
                "color": str(lane.get("display_color") or ""),
                "nozzle_diameter": as_float(lane.get("nozzle_diameter"), 0.0),
                "lane_kind": str(lane.get("lane_kind") or lane_kind(str(lane.get("role") or "unknown"))),
                "role": str(lane.get("role") or "unknown"),
                "material_family_key": str(lane.get("material_family_key") or ""),
                "material_family_label": str(lane.get("material_family_label") or ""),
                "material_family_base_polymer": str(lane.get("material_family_base_polymer") or ""),
                "material_family_reinforcement_type": str(lane.get("material_family_reinforcement_type") or "none"),
                "material_family_is_filled": bool(lane.get("material_family_is_filled", False)),
                "enabled": True,
            }
        )
    return badges


def filled_material_lane_badges(badges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        badge
        for badge in badges
        if isinstance(badge, dict) and bool(badge.get("material_family_is_filled", False))
    ]


def role_at(roles: list[str], index: int) -> str:
    if index >= len(roles):
        return "polymer"
    return roles[index] or "polymer"


def lane_contract(config: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    roles = string_list(config.get("fiber_slot_roles"))
    filament_type_value = config_value(config, FILAMENT_TYPE_KEYS)
    filament_settings_value = config_value(config, FILAMENT_SETTINGS_KEYS)
    filament_vendor_value = config_value(config, FILAMENT_VENDOR_KEYS)
    filament_colour_value = config_value(config, FILAMENT_COLOR_KEYS)
    nozzle_diameter_value = config_value(config, NOZZLE_DIAMETER_KEYS)
    filament_types = value_list(filament_type_value)
    filament_settings = value_list(filament_settings_value)
    filament_colours = value_list(filament_colour_value)
    nozzle_diameters = value_list(nozzle_diameter_value)
    if not roles and not any([filament_types, filament_settings, filament_colours, nozzle_diameters]):
        roles = ["polymer", "composite", "fiber_drive"]
    lane_count = max(
        len(roles),
        len(filament_types),
        len(filament_settings),
        len(filament_colours),
        len(nozzle_diameters),
        1,
    )
    lanes = []
    for index in range(lane_count):
        role = role_at(roles, index)
        tool_index = lane_tool_index(role, index, route)
        lanes.append(
            {
                "lane_index": index,
                "lane_id": f"L{index}",
                "role": role,
                "lane_kind": lane_kind(role),
                "tool_index": tool_index,
                "toolhead_index": tool_index,
                "extruder_id": f"T{tool_index}",
                "independent_lane": True,
                "material_type": value_at(filament_type_value, index),
                "filament_settings_id": value_at(filament_settings_value, index),
                "filament_vendor": value_at(filament_vendor_value, index),
                "display_color": lane_color(config, index),
                "nozzle_diameter": float_at(nozzle_diameter_value, index, 0.0),
            }
        )
        lanes[-1]["display_label"] = lane_display_label(lanes[-1])
    for lane in lanes:
        if lane["role"] == "fiber_drive":
            lane["fiber_material"] = {
                "name": value_at(config.get("fiber_name"), lane["lane_index"]),
                "type": value_at(config.get("fiber_type"), lane["lane_index"]),
                "material_kind": value_at(config.get("fiber_material_kind"), lane["lane_index"]),
                "source_material_id": value_at(config.get("fiber_source_material_id"), lane["lane_index"]),
                "diameter": float_at(config.get("fiber_diameter"), lane["lane_index"], 0.0),
            }
        decorate_lane_material_family(lane)
    material_labels = [
        lane.get("filament_settings_id") or lane.get("material_type") or lane.get("fiber_material", {}).get("name", "")
        for lane in lanes
    ]
    colors = [str(lane.get("display_color") or "") for lane in lanes]
    nozzles = [lane.get("nozzle_diameter") for lane in lanes if lane.get("nozzle_diameter")]
    return {
        "lane_count": len(lanes),
        "lanes": lanes,
        "per_toolhead_lanes": not as_bool(config.get("fiber_shared_nozzle")),
        "shared_nozzle": as_bool(config.get("fiber_shared_nozzle")),
        "mixed_filament_enabled": True,
        "selected_material_count": selected_count([str(item) for item in material_labels]),
        "color_count": selected_count(colors),
        "selected_nozzle_count": len({float(item) for item in nozzles}),
    }


def mixed_filament_contract(lanes: dict[str, Any]) -> dict[str, Any]:
    lane_items = lanes.get("lanes") if isinstance(lanes.get("lanes"), list) else []
    lane_dicts = [lane for lane in lane_items if isinstance(lane, dict)]
    badges = lane_badges(lane_dicts)
    materials = [
        str(lane.get("filament_settings_id") or lane.get("material_type") or lane.get("fiber_material", {}).get("name", ""))
        for lane in lane_dicts
    ]
    colors = [str(lane.get("display_color") or "") for lane in lane_dicts]
    filled_material_lane_count = sum(1 for lane in lane_dicts if lane.get("material_family_is_filled"))
    filled_badges = filled_material_lane_badges(badges)
    return {
        "source": "orca_config",
        "enabled": lanes.get("mixed_filament_enabled", False),
        "lane_count": lanes.get("lane_count", 0),
        "per_toolhead_lanes": lanes.get("per_toolhead_lanes", False),
        "shared_nozzle": lanes.get("shared_nozzle", False),
        "selected_material_count": lanes.get("selected_material_count", selected_count(materials)),
        "color_count": lanes.get("color_count", selected_count(colors)),
        "selected_nozzle_count": lanes.get("selected_nozzle_count", 0),
        "filled_material_lane_count": filled_material_lane_count,
        "filled_material_lane_badge_count": len(filled_badges),
        "filled_material_lane_badges": filled_badges,
        "lane_badge_count": len(badges),
        "lane_roles": [lane.get("role") for lane in lane_dicts],
        "material_palette": material_palette(lane_dicts),
        "lane_badges": badges,
    }


def lane_readiness_summary(lanes: dict[str, Any], mixed_filament: dict[str, Any], gates: list[dict[str, Any]]) -> dict[str, Any]:
    lane_items = [lane for lane in lanes.get("lanes", []) if isinstance(lane, dict)]
    role_counts: dict[str, int] = {}
    lane_kind_counts: dict[str, int] = {}
    unknown_material_lane_indices: list[int] = []
    missing_color_lane_indices: list[int] = []
    missing_nozzle_lane_indices: list[int] = []

    for lane in lane_items:
        lane_index = int(as_float(lane.get("lane_index"), 0.0))
        role = str(lane.get("role") or "unknown")
        kind = str(lane.get("lane_kind") or "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
        lane_kind_counts[kind] = lane_kind_counts.get(kind, 0) + 1
        fiber_material = lane.get("fiber_material") if isinstance(lane.get("fiber_material"), dict) else {}
        material_name = lane.get("filament_settings_id") or lane.get("material_type") or fiber_material.get("name")
        if not material_name:
            unknown_material_lane_indices.append(lane_index)
        if not lane.get("display_color"):
            missing_color_lane_indices.append(lane_index)
        if kind != "continuous_fiber" and not lane.get("nozzle_diameter"):
            missing_nozzle_lane_indices.append(lane_index)

    review_issue_count = (
        len(unknown_material_lane_indices)
        + len(missing_color_lane_indices)
        + len(missing_nozzle_lane_indices)
    )
    readiness = {
        "schema_version": "1.0.0",
        "status": "ready" if review_issue_count == 0 else "needs_lane_review",
        "readiness_level": "metadata_ready" if review_issue_count == 0 else "needs_lane_review",
        "source": "orca_config",
        "lane_count": len(lane_items),
        "independent_lane_count": sum(1 for lane in lane_items if lane.get("independent_lane")),
        "per_toolhead_lanes": lanes.get("per_toolhead_lanes", False),
        "shared_nozzle": lanes.get("shared_nozzle", False),
        "role_counts": role_counts,
        "lane_kind_counts": lane_kind_counts,
        "polymer_lane_count": lane_kind_counts.get("polymer", 0),
        "composite_lane_count": lane_kind_counts.get("composite_polymer", 0),
        "continuous_fiber_lane_count": lane_kind_counts.get("continuous_fiber", 0),
        "support_lane_count": lane_kind_counts.get("support_material", 0),
        "unknown_material_lane_indices": unknown_material_lane_indices,
        "missing_color_lane_indices": missing_color_lane_indices,
        "missing_nozzle_lane_indices": missing_nozzle_lane_indices,
        "review_issue_count": review_issue_count,
        "validation_blocked_gate_count": len(blocked_validation_gates(gates)),
        "validation_blocked_gate_ids": blocked_validation_gate_ids(gates),
        "validation_blocked_gate_messages": blocked_validation_gate_messages(gates),
        "selected_material_count": mixed_filament.get("selected_material_count", 0),
        "color_count": mixed_filament.get("color_count", 0),
        "selected_nozzle_count": mixed_filament.get("selected_nozzle_count", 0),
        "hardware_ready": False,
        "command_emission_allowed": False,
        "advisory_only": True,
    }
    return decorate_lane_readiness_review_fields(readiness)


def validation_gates(config: dict[str, Any], machine_payload: dict[str, Any]) -> list[dict[str, Any]]:
    cut_gcode = str(config.get("fiber_cut_gcode", "") or "").strip()
    return [
        {
            "id": "machine_specific_cut_restart",
            "status": "blocked" if not cut_gcode else "review",
            "message": "Machine-specific cut and restart commands must be validated before hardware-ready output.",
        },
        {
            "id": "toolhead_keepout",
            "status": "blocked",
            "message": "Measured toolhead keepout and fiber contact geometry are required before hardware-ready output.",
        },
        {
            "id": "fiber_feed_tension",
            "status": "blocked",
            "message": "Fiber feed distance, release behavior, and tension limits need hardware validation.",
        },
        {
            "id": "operator_hardware_validation",
            "status": "blocked" if not as_bool(machine_payload.get("hardware_ready")) else "review",
            "message": "Operator validation is required; this sidecar never starts printers or sends live commands.",
        },
    ]


def fallback_sidecar(args: argparse.Namespace, external_error: str | None) -> dict[str, Any]:
    config = read_json(args.config_json)
    plan = read_json(args.plan)
    audit = read_json(args.audit)
    bundle = read_json(args.bundle)
    integrity = read_json(args.integrity)
    machine_payload = parse_jsonish(config.get("fiber_machine_contract_payload"))
    fiber_enabled = any_bool(config.get("fiber_enabled")) or bool(plan) or bool(bundle)
    composite_enabled = any_bool(config.get("composite_enabled"))
    gates = validation_gates(config, machine_payload)
    blocked_gate_count = sum(1 for gate in gates if gate.get("status") == "blocked")
    route = route_from_inputs(config, plan, machine_payload)
    lanes = lane_contract(config, route)
    lane_items = [lane for lane in lanes.get("lanes", []) if isinstance(lane, dict)]
    fiber_enabled = fiber_enabled or any(lane.get("lane_kind") == "continuous_fiber" for lane in lane_items)
    composite_enabled = composite_enabled or fiber_enabled or any(
        lane.get("lane_kind") == "composite_polymer" for lane in lane_items
    )
    mixed_filament = mixed_filament_contract(lanes)
    lane_readiness = lane_readiness_summary(lanes, mixed_filament, gates)
    generated_path_count = len(bundle.get("paths", [])) if isinstance(bundle.get("paths"), list) else 0
    observed_marker_count = int(audit.get("fiber_marker_count", 0)) if audit else 0
    integrity_passed = bool(integrity.get("passed")) if integrity else False
    status = "hardware_candidate" if fiber_enabled or composite_enabled else "polymer_only"

    sidecar = {
        "schema_version": "1.0.0",
        "contract": metadata_contract(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_artifacts": input_artifacts(args),
        "status": status,
        "safety_level": "hardware_candidate" if status != "polymer_only" else "polymer_only",
        "hardware_ready": False,
        "command_emission_allowed": False,
        "live_machine_side_effects": False,
        "mode": str(config.get("fiber_reinforcement_mode") or plan.get("mode") or "metadata_only"),
        "route": route,
        "lane_contract": lanes,
        "mixed_filament_contract": mixed_filament,
        "lane_readiness_summary": lane_readiness,
        "summary": {
            "fiber_enabled": fiber_enabled,
            "composite_enabled": composite_enabled,
            "generated_path_count": generated_path_count,
            "observed_fiber_marker_count": observed_marker_count,
            "composite_candidate_integrity_available": bool(integrity),
            "composite_candidate_integrity_passed": integrity_passed,
            "validation_gate_count": len(gates),
            "blocked_gate_count": blocked_gate_count,
            "mixed_filament_lane_count": mixed_filament["lane_count"],
            "selected_material_count": mixed_filament["selected_material_count"],
            "color_count": mixed_filament["color_count"],
            "selected_nozzle_count": mixed_filament["selected_nozzle_count"],
            "filled_material_lane_count": mixed_filament["filled_material_lane_count"],
            "filled_material_lane_badge_count": mixed_filament["filled_material_lane_badge_count"],
            "filled_material_lane_badges": mixed_filament["filled_material_lane_badges"],
            "lane_badge_count": mixed_filament["lane_badge_count"],
            "lane_readiness_status": lane_readiness["status"],
            "lane_readiness_level": lane_readiness["readiness_level"],
            "lane_readiness_review_issue_count": lane_readiness["lane_readiness_review_issue_count"],
            "lane_readiness_review_needed": lane_readiness["lane_readiness_review_needed"],
            "lane_readiness_review_message": lane_readiness["lane_readiness_review_message"],
            "lane_readiness_review_severity": lane_readiness["lane_readiness_review_severity"],
            "lane_readiness_review_color": lane_readiness["lane_readiness_review_color"],
            "continuous_fiber_lane_count": lane_readiness["continuous_fiber_lane_count"],
            "polymer_lane_count": lane_readiness["polymer_lane_count"],
            "missing_material_lane_count": len(lane_readiness["unknown_material_lane_indices"]),
            "missing_color_lane_count": len(lane_readiness["missing_color_lane_indices"]),
            "missing_nozzle_lane_count": len(lane_readiness["missing_nozzle_lane_indices"]),
            "validation_blocked_gate_count": lane_readiness["validation_blocked_gate_count"],
            "validation_blocked_gate_ids": lane_readiness["validation_blocked_gate_ids"],
            "validation_blocked_gate_messages": lane_readiness["validation_blocked_gate_messages"],
        },
        "validation_gates": gates,
        "artifacts": {
            "plan": str(args.plan or ""),
            "audit": str(args.audit or ""),
            "bundle": str(args.bundle or ""),
            "integrity": str(args.integrity or ""),
        },
        "guardrails": [
            "metadata_only_until_hardware_validated",
            "no_live_machine_commands",
            "no_upload_or_start_print",
            "preserve_normal_orca_printer_behavior",
        ],
        "external_builder_error": external_error,
    }
    summary = sidecar["summary"]
    summary["lane_readiness_review_chip_categories"] = lane_readiness_review_chip_categories()
    summary["lane_readiness_review_chip_category_count"] = len(summary["lane_readiness_review_chip_categories"])
    summary["lane_readiness_review_chips"] = lane_readiness_review_chips(summary)
    summary["lane_readiness_review_chip_count"] = len(summary["lane_readiness_review_chips"])
    summary["lane_readiness_review_reasons"] = lane_readiness_review_reasons(summary)
    summary["lane_readiness_review_reason_count"] = len(summary["lane_readiness_review_reasons"])
    return enforce_metadata_guardrails(sidecar, "fallback")


def main() -> int:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    external_error = None
    if not args.force_fallback:
        builder = find_external_builder(args.external_builder)
        if builder is not None:
            external_error = run_external_builder(args, builder)
            if external_error is None:
                normalization_error = normalize_external_sidecar(args.out, "external_builder", input_artifacts(args))
                if normalization_error is not None:
                    external_error = normalization_error
                else:
                    return 0
    sidecar = fallback_sidecar(args, external_error)
    args.out.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
