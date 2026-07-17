#!/usr/bin/env python3
"""Build an TinManX1 Strength Lens sidecar from an Orca slice-result payload.

This is an TinManX1 bridge for the Strength Lens contract. It prefers
the richer Codex builder when available, then falls back to a compact
predictive overlay so Orca can keep emitting stable metadata during integration.
The output is advisory display data only; it does not modify slicing or G-code.
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


COLORS = {
    "critical": "#E53935",
    "review": "#FFB300",
    "strong": "#43A047",
    "fiber": "#00E5FF",
    "orientation": "#1E88E5",
    "load_path": "#D81B60",
    "experimental": "#8E24AA",
}
LANE_REVIEW_CHIP_CATEGORIES = (
    ("missing_material", "Missing material", "missing_material_lane_count"),
    ("missing_color", "Missing color", "missing_color_lane_count"),
    ("missing_nozzle", "Missing nozzle", "missing_nozzle_lane_count"),
    ("blocked_validation_gates", "Blocked validation gates", "validation_blocked_gate_count"),
)
ARC_SUPPORT_PREVIEW_CUE_CHIPS = {
    "normal_support_rejected": ("Normal support extrusion rejected", "info", COLORS["orientation"]),
    "guarded_arc_transform_expected": ("Guarded Arc transform expected", "info", COLORS["experimental"]),
    "same_path_mutation_forbidden": ("Same-path mutation blocked", "info", COLORS["review"]),
    "adapter_replaces_input_only_on_success": ("Replace only after success", "info", COLORS["strong"]),
}

MECHANICS_REFERENCE = {
    "source_id": "mechanicalc_strength_of_materials",
    "source_label": "MechaniCalc Strength of Materials",
    "source_url": "https://mechanicalc.com/reference/strength-of-materials",
    "calculator_index_url": "https://mechanicalc.com/calculators/",
    "used_for": [
        "load_case_language",
        "stress_concentration_risk_cues",
        "combined_stress_and_principal_direction_vocabulary",
        "stiffness_and_load_path_explanation",
    ],
    "not_used_for": [
        "certified_safety_factor",
        "automatic metal-to-polymer material substitution",
        "machine-ready structural approval",
    ],
}

SIMULATION_REFERENCE = {
    "source_id": "autodesk_fusion_simulation_intro",
    "source_label": "Autodesk Fusion 360 Simulation learning path",
    "source_url": "https://www.autodesk.com/learn/ondemand/curated/getting-started-with-simulation/KW9u4cqugIm75g2EoAc9q",
    "used_for": [
        "simulation_workflow_vocabulary",
        "load_constraint_result_review_flow",
        "strength_lens_future_solver_requirements",
    ],
    "not_used_for": [
        "certified_fea",
        "automatic solver result substitution",
        "machine-ready structural approval",
    ],
}

LOAD_CASE_VECTORS = {
    "tension": [
        {"id": "tension_axis", "label": "Tension pull direction", "x": 1.0, "y": 0.0, "z": 0.0},
        {"id": "tension_reaction", "label": "Opposing fixture reaction", "x": -1.0, "y": 0.0, "z": 0.0},
    ],
    "bending": [
        {"id": "bending_span", "label": "Span direction", "x": 1.0, "y": 0.0, "z": 0.0},
        {"id": "bending_load", "label": "Applied bending load", "x": 0.0, "y": 0.0, "z": -1.0},
    ],
    "compression_clamp": [
        {"id": "compression_axis", "label": "Clamp compression direction", "x": 0.0, "y": 0.0, "z": -1.0},
        {"id": "compression_reaction", "label": "Fixture reaction", "x": 0.0, "y": 0.0, "z": 1.0},
    ],
    "torsion": [
        {"id": "torsion_axis", "label": "Torque axis", "x": 0.0, "y": 0.0, "z": 1.0},
        {"id": "torsion_shear", "label": "Dominant shear-loop cue", "x": 1.0, "y": 1.0, "z": 0.0},
    ],
    "custom_vector": [
        {"id": "custom_vector", "label": "User-defined load vector placeholder", "x": 1.0, "y": 0.0, "z": 0.0},
    ],
}

LOAD_CASE_MESSAGES = {
    "unknown": "No load case selected yet; show orientation and design-risk cues without force-vector assumptions.",
    "tension": "Tension cue staged: compare pull direction against the weakest print axis and layer-line split risk.",
    "bending": "Bending cue staged: review tensile-side layer orientation, wall count, and section-change stress crowding.",
    "compression_clamp": "Compression/clamp cue staged: review bearing faces, creep risk, and load spreading.",
    "torsion": "Torsion cue staged: review shear-loop continuity, seam placement, and perimeter-dominated strength.",
    "custom_vector": "Custom load vector cue staged; define force and fixture faces for stronger orientation guidance.",
}

LOAD_CASE_NORMALIZATION_TOKENS = {
    "kind": "load_case.kind_defaulted_from_cli",
    "label": "load_case.label_defaulted_from_cli",
    "message": "load_case.message_defaulted_from_cli",
    "vectors": "load_case.vectors_defaulted_from_cli",
    "vector_chips": "load_case.vector_chips_defaulted_from_vectors",
    "vector_chip_count": "load_case.vector_chip_count_defaulted_from_vectors",
}

VIEWPORT_GUARDRAIL_FALSE_FIELDS = (
    "slicing_or_gcode_modified",
    "certified_fea",
    "certified_safety_factor",
    "print_approval",
    "machine_ready_structural_approval",
)
VIEWPORT_GUARDRAIL_NORMALIZATION_TOKENS = {
    "advisory_only": "viewport_render_plan.advisory_only_forced_true",
    "slicing_or_gcode_modified": "viewport_render_plan.slicing_or_gcode_modified_forced_false",
    "certified_fea": "viewport_render_plan.certified_fea_forced_false",
    "certified_safety_factor": "viewport_render_plan.certified_safety_factor_forced_false",
    "print_approval": "viewport_render_plan.print_approval_forced_false",
    "machine_ready_structural_approval": "viewport_render_plan.machine_ready_structural_approval_forced_false",
}
MATERIAL_FAMILY_VIEWPORT_FIELDS = (
    ("status", "material_family_estimate_status", "unavailable"),
    ("family_key", "material_family_key", ""),
    ("display_name", "material_family_label", ""),
    ("source_material_text", "material_family_source_material_text", ""),
    ("matched_alias", "material_family_matched_alias", ""),
    ("base_polymer", "material_family_base_polymer", ""),
    ("reinforcement_type", "material_family_reinforcement_type", "none"),
    ("basis", "material_family_basis", ""),
    ("source", "material_family_source", ""),
    ("warning", "material_family_warning", ""),
)
MATERIAL_FAMILY_VIEWPORT_NORMALIZATION_TOKENS = {
    "material_family_estimate_status": (
        "viewport_render_plan.material_family_estimate_status_defaulted_from_material_family_estimate"
    ),
    "material_family_key": "viewport_render_plan.material_family_key_defaulted_from_material_family_estimate",
    "material_family_label": "viewport_render_plan.material_family_label_defaulted_from_material_family_estimate",
    "material_family_source_material_text": (
        "viewport_render_plan.material_family_source_material_text_defaulted_from_material_family_estimate"
    ),
    "material_family_matched_alias": (
        "viewport_render_plan.material_family_matched_alias_defaulted_from_material_family_estimate"
    ),
    "material_family_base_polymer": (
        "viewport_render_plan.material_family_base_polymer_defaulted_from_material_family_estimate"
    ),
    "material_family_reinforcement_type": (
        "viewport_render_plan.material_family_reinforcement_type_defaulted_from_material_family_estimate"
    ),
    "material_family_is_filled": (
        "viewport_render_plan.material_family_is_filled_defaulted_from_material_family_estimate"
    ),
    "material_family_basis": "viewport_render_plan.material_family_basis_defaulted_from_material_family_estimate",
    "material_family_source": "viewport_render_plan.material_family_source_defaulted_from_material_family_estimate",
    "material_family_warning": "viewport_render_plan.material_family_warning_defaulted_from_material_family_estimate",
    "material_family_axis_strengths_mpa": (
        "viewport_render_plan.material_family_axis_strengths_mpa_defaulted_from_material_family_estimate"
    ),
}
STRENGTH_MAP_VIEWPORT_FIELDS = (
    ("metric", "strength_map_metric", ""),
    ("render_policy", "strength_render_policy", ""),
    ("color_mode", "strength_color_mode", ""),
    ("reference_strength_mpa", "reference_strength_mpa", 0.0),
)
STRENGTH_MAP_VIEWPORT_NORMALIZATION_TOKENS = {
    "strength_map_metric": "viewport_render_plan.strength_map_metric_defaulted_from_strength_map",
    "strength_render_policy": "viewport_render_plan.strength_render_policy_defaulted_from_strength_map",
    "strength_color_mode": "viewport_render_plan.strength_color_mode_defaulted_from_strength_map",
    "reference_strength_mpa": "viewport_render_plan.reference_strength_mpa_defaulted_from_strength_map",
    "print_axis_bands": "viewport_render_plan.print_axis_bands_defaulted_from_strength_map",
    "print_axis_band_count": "viewport_render_plan.print_axis_band_count_defaulted_from_strength_map",
}
VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS = {
    "overlay_count": "viewport_render_plan.overlay_count_defaulted_from_overlays",
    "warning_overlay_count": "viewport_render_plan.warning_overlay_count_defaulted_from_overlays",
    "top_cue_count": "viewport_render_plan.top_cue_count_defaulted_from_top_cues",
    "lens_overlay_counts": "viewport_render_plan.lens_overlay_counts_defaulted_from_overlays",
    "lens_warning_counts": "viewport_render_plan.lens_warning_counts_defaulted_from_overlays",
}
MIXED_FILAMENT_VIEWPORT_TEXT_FIELDS = (
    ("status", "mixed_filament_status", "unavailable"),
    ("source", "mixed_filament_source", ""),
    ("lane_readiness_review_message", "lane_readiness_review_message", ""),
    ("lane_readiness_review_severity", "lane_readiness_review_severity", "info"),
    ("lane_readiness_review_color", "lane_readiness_review_color", COLORS["orientation"]),
)
MIXED_FILAMENT_VIEWPORT_COUNT_FIELDS = (
    ("lane_count", "mixed_filament_lane_count", 0),
    ("selected_material_count", "mixed_filament_material_count", 0),
    ("color_count", "mixed_filament_color_count", 0),
    ("selected_nozzle_count", "mixed_filament_nozzle_count", 0),
    ("lane_readiness_review_issue_count", "lane_readiness_review_issue_count", 0),
    ("continuous_fiber_lane_count", "continuous_fiber_lane_count", 0),
    ("filled_material_lane_count", "filled_material_lane_count", 0),
    ("filled_material_lane_badge_count", "filled_material_lane_badge_count", 0),
    ("polymer_lane_count", "polymer_lane_count", 0),
    ("missing_material_lane_count", "missing_material_lane_count", 0),
    ("missing_color_lane_count", "missing_color_lane_count", 0),
    ("missing_nozzle_lane_count", "missing_nozzle_lane_count", 0),
    ("validation_blocked_gate_count", "validation_blocked_gate_count", 0),
)
MIXED_FILAMENT_VIEWPORT_BOOL_FIELDS = (
    ("lane_readiness_review_needed", "lane_readiness_review_needed", False),
)
MIXED_FILAMENT_VIEWPORT_LIST_FIELDS = (
    ("validation_blocked_gate_ids", "validation_blocked_gate_ids"),
    ("validation_blocked_gate_messages", "validation_blocked_gate_messages"),
    ("filled_material_lane_badges", "filled_material_lane_badges"),
)
MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS = {
    "mixed_filament_status": "viewport_render_plan.mixed_filament_status_defaulted_from_mixed_context",
    "mixed_filament_source": "viewport_render_plan.mixed_filament_source_defaulted_from_mixed_context",
    "mixed_filament_lane_count": "viewport_render_plan.mixed_filament_lane_count_defaulted_from_mixed_context",
    "mixed_filament_material_count": "viewport_render_plan.mixed_filament_material_count_defaulted_from_mixed_context",
    "mixed_filament_color_count": "viewport_render_plan.mixed_filament_color_count_defaulted_from_mixed_context",
    "mixed_filament_nozzle_count": "viewport_render_plan.mixed_filament_nozzle_count_defaulted_from_mixed_context",
    "lane_readiness_review_issue_count": (
        "viewport_render_plan.lane_readiness_review_issue_count_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_needed": (
        "viewport_render_plan.lane_readiness_review_needed_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_message": (
        "viewport_render_plan.lane_readiness_review_message_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_severity": (
        "viewport_render_plan.lane_readiness_review_severity_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_color": (
        "viewport_render_plan.lane_readiness_review_color_defaulted_from_mixed_context"
    ),
    "continuous_fiber_lane_count": "viewport_render_plan.continuous_fiber_lane_count_defaulted_from_mixed_context",
    "filled_material_lane_count": "viewport_render_plan.filled_material_lane_count_defaulted_from_mixed_context",
    "filled_material_lane_badge_count": (
        "viewport_render_plan.filled_material_lane_badge_count_defaulted_from_mixed_context"
    ),
    "polymer_lane_count": "viewport_render_plan.polymer_lane_count_defaulted_from_mixed_context",
    "missing_material_lane_count": (
        "viewport_render_plan.missing_material_lane_count_defaulted_from_mixed_context"
    ),
    "missing_color_lane_count": "viewport_render_plan.missing_color_lane_count_defaulted_from_mixed_context",
    "missing_nozzle_lane_count": "viewport_render_plan.missing_nozzle_lane_count_defaulted_from_mixed_context",
    "validation_blocked_gate_count": (
        "viewport_render_plan.validation_blocked_gate_count_defaulted_from_mixed_context"
    ),
    "validation_blocked_gate_ids": (
        "viewport_render_plan.validation_blocked_gate_ids_defaulted_from_mixed_context"
    ),
    "validation_blocked_gate_messages": (
        "viewport_render_plan.validation_blocked_gate_messages_defaulted_from_mixed_context"
    ),
    "filled_material_lane_badges": "viewport_render_plan.filled_material_lane_badges_defaulted_from_mixed_context",
    "lane_readiness_review_chip_categories": (
        "viewport_render_plan.lane_readiness_review_chip_categories_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_chip_category_count": (
        "viewport_render_plan.lane_readiness_review_chip_category_count_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_chips": "viewport_render_plan.lane_readiness_review_chips_defaulted_from_mixed_context",
    "lane_readiness_review_chip_count": (
        "viewport_render_plan.lane_readiness_review_chip_count_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_reasons": (
        "viewport_render_plan.lane_readiness_review_reasons_defaulted_from_mixed_context"
    ),
    "lane_readiness_review_reason_count": (
        "viewport_render_plan.lane_readiness_review_reason_count_defaulted_from_mixed_context"
    ),
}
ORIENTATION_CONFIDENCE_VIEWPORT_FIELDS = (
    ("status", "orientation_confidence_status", "needs_material_axis_data"),
    ("basis", "orientation_confidence_basis", ""),
    ("estimated", "orientation_confidence_estimated", False),
    ("strongest_strength_mpa", "strongest_strength_mpa", 0.0),
    ("weakest_strength_mpa", "weakest_strength_mpa", 0.0),
    ("weakest_to_strongest_ratio", "weakest_to_strongest_ratio", 0.0),
    ("weakest_axis_drop_percent", "weakest_axis_drop_percent", 0.0),
)
ORIENTATION_CONFIDENCE_VIEWPORT_NORMALIZATION_TOKENS = {
    "orientation_confidence_status": (
        "viewport_render_plan.orientation_confidence_status_defaulted_from_orientation_confidence"
    ),
    "orientation_confidence_basis": (
        "viewport_render_plan.orientation_confidence_basis_defaulted_from_orientation_confidence"
    ),
    "orientation_confidence_estimated": (
        "viewport_render_plan.orientation_confidence_estimated_defaulted_from_orientation_confidence"
    ),
    "strongest_strength_mpa": "viewport_render_plan.strongest_strength_mpa_defaulted_from_orientation_confidence",
    "weakest_strength_mpa": "viewport_render_plan.weakest_strength_mpa_defaulted_from_orientation_confidence",
    "weakest_to_strongest_ratio": (
        "viewport_render_plan.weakest_to_strongest_ratio_defaulted_from_orientation_confidence"
    ),
    "weakest_axis_drop_percent": (
        "viewport_render_plan.weakest_axis_drop_percent_defaulted_from_orientation_confidence"
    ),
    "orientation_warning_axes": "viewport_render_plan.orientation_warning_axes_defaulted_from_orientation_confidence",
}

STRENGTH_LENS_CONTRACT = {
    "id": "orcaslicer_codex_strength_lens_sidecar",
    "schema_version": "1.0.0",
    "contract_version": "1.0.0",
    "output_kind": "viewport_overlay_metadata",
    "advisory_only": True,
    "slicing_or_gcode_modified": False,
    "certified_fea": False,
    "print_approval": False,
}

COMMAND_PAYLOAD_KEYS = {
    "commands",
    "command_queue",
    "execution_commands",
    "generated_commands",
    "gcode",
    "gcode_commands",
    "machine_commands",
    "modified_gcode",
    "postprocess_commands",
    "printer_commands",
    "raw_gcode",
    "slice_patch",
    "slicer_patch",
    "start_gcode",
    "end_gcode",
    "toolchange_gcode",
    "upload_payload",
    "start_print_payload",
}

NESTED_ADVISORY_FALSE_KEYS = {
    "certified_fea",
    "certified_safety_factor",
    "command_emission_allowed",
    "hardware_ready",
    "live_machine_side_effects",
    "machine_ready_structural_approval",
    "print_approval",
    "slicing_or_gcode_modified",
    "start_print_allowed",
    "upload_allowed",
    "upload_or_start_print_allowed",
}

NESTED_ADVISORY_TRUE_KEYS = {
    "advisory_only",
}

LENSES = [
    ("orientation_risk", "Orientation Risk"),
    ("design_risk", "Design Risk"),
    ("process_confidence", "Process Confidence"),
    ("fiber_route", "Fiber Route"),
]
KNOWN_OVERLAY_KINDS = {
    "strength_color_map",
    "material_data_gap",
    "load_case_direction",
    "stress_concentration_reference",
    "arc_support_experimental",
    "fiber_route_preview",
    "mixed_filament_lane_context",
    "integration_fallback",
    "advisory_only",
}
KNOWN_OVERLAY_SEVERITIES = {"info", "warning"}

LANE_READY_STATUSES = {"ready", "metadata_ready"}
LANE_REVIEW_STATUSES = {"needs_lane_review"}

MATERIAL_FAMILY_AXIS_ESTIMATES = {
    "pla": {
        "display_name": "PLA",
        "print_axis_tensile_strength_mpa": {"x": 58.0, "y": 52.0, "z": 28.0},
        "aliases": ["pla", "pla_basic", "pla+", "pla plus"],
    },
    "pla_cf": {
        "display_name": "PLA-CF",
        "print_axis_tensile_strength_mpa": {"x": 72.0, "y": 58.0, "z": 24.0},
        "aliases": ["pla-cf", "pla_cf", "pla cf", "carbon fiber pla", "pla carbon fiber"],
    },
    "petg": {
        "display_name": "PETG",
        "print_axis_tensile_strength_mpa": {"x": 50.0, "y": 44.0, "z": 24.0},
        "aliases": ["petg"],
    },
    "petg_cf": {
        "display_name": "PETG-CF",
        "print_axis_tensile_strength_mpa": {"x": 68.0, "y": 54.0, "z": 22.0},
        "aliases": ["petg-cf", "petg_cf", "petg cf", "carbon fiber petg", "petg carbon fiber"],
    },
    "abs": {
        "display_name": "ABS",
        "print_axis_tensile_strength_mpa": {"x": 40.0, "y": 35.0, "z": 20.0},
        "aliases": ["abs"],
    },
    "asa": {
        "display_name": "ASA",
        "print_axis_tensile_strength_mpa": {"x": 42.0, "y": 36.0, "z": 20.0},
        "aliases": ["asa"],
    },
    "asa_cf": {
        "display_name": "ASA-CF",
        "print_axis_tensile_strength_mpa": {"x": 66.0, "y": 52.0, "z": 21.0},
        "aliases": ["asa-cf", "asa_cf", "asa cf", "carbon fiber asa", "asa carbon fiber"],
    },
    "abs_cf": {
        "display_name": "ABS-CF",
        "print_axis_tensile_strength_mpa": {"x": 70.0, "y": 55.0, "z": 22.0},
        "aliases": ["abs-cf", "abs_cf", "abs cf", "carbon fiber abs", "abs carbon fiber"],
    },
    "pa": {
        "display_name": "PA/Nylon",
        "print_axis_tensile_strength_mpa": {"x": 65.0, "y": 55.0, "z": 30.0},
        "aliases": ["pa", "nylon", "pa6", "pa12"],
    },
    "pa_cf": {
        "display_name": "PA-CF",
        "print_axis_tensile_strength_mpa": {"x": 95.0, "y": 72.0, "z": 30.0},
        "aliases": ["pa-cf", "pa_cf", "pa cf", "nylon-cf", "nylon cf", "carbon fiber nylon", "nylon carbon fiber"],
    },
    "pa_gf": {
        "display_name": "PA-GF",
        "print_axis_tensile_strength_mpa": {"x": 82.0, "y": 66.0, "z": 29.0},
        "aliases": ["pa-gf", "pa_gf", "pa gf", "nylon-gf", "nylon gf", "glass fiber nylon", "nylon glass fiber"],
    },
    "pc": {
        "display_name": "PC",
        "print_axis_tensile_strength_mpa": {"x": 60.0, "y": 52.0, "z": 28.0},
        "aliases": ["pc", "polycarbonate"],
    },
    "pc_cf": {
        "display_name": "PC-CF",
        "print_axis_tensile_strength_mpa": {"x": 90.0, "y": 70.0, "z": 27.0},
        "aliases": ["pc-cf", "pc_cf", "pc cf", "polycarbonate-cf", "polycarbonate cf", "carbon fiber pc"],
    },
    "tpu": {
        "display_name": "TPU",
        "print_axis_tensile_strength_mpa": {"x": 30.0, "y": 28.0, "z": 15.0},
        "aliases": ["tpu", "flex", "flexible"],
    },
}

MATERIAL_FAMILY_PROFILE_KEYS = (
    "filament_type",
    "filament_types",
    "filament_material",
    "filament_materials",
    "filament_settings_id",
    "filament_settings_ids",
    "filament_preset_id",
    "filament_preset_ids",
    "filament_preset",
    "filament_presets",
    "filament",
    "filaments",
    "material",
    "materials",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--slice-result", required=True, type=Path)
    parser.add_argument("--fiber-preview-overlay", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--active-lens",
        default="orientation_risk",
        choices=[lens_id for lens_id, _ in LENSES],
    )
    parser.add_argument(
        "--load-case",
        default="unknown",
        choices=["unknown", "tension", "bending", "compression_clamp", "torsion", "custom_vector"],
    )
    parser.add_argument(
        "--external-builder",
        type=Path,
        help="Optional path to the full TinManX1 build_strength_visualization.py tool.",
    )
    parser.add_argument(
        "--force-fallback",
        action="store_true",
        help="Use the compact Orca fallback even if the full TinManX1 builder is available.",
    )
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
        "slice_result": file_artifact(args.slice_result),
        "fiber_preview_overlay": file_artifact(args.fiber_preview_overlay),
    }


def text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    result = str(value)
    return result if result else default


def number(value: Any, default: float = 0.0) -> float:
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


def lane_readiness_review_chips(summary: dict[str, Any]) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []
    for chip_id, label, count_key in LANE_REVIEW_CHIP_CATEGORIES:
        count = int(number(summary.get(count_key), 0.0))
        if count <= 0:
            continue
        chips.append(
            {
                "id": chip_id,
                "label": label,
                "count": count,
                "severity": "warning",
                "color": COLORS["review"],
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
        count = int(number(summary.get(count_key), 0.0))
        if count <= 0:
            continue
        reason = {
            "id": chip_id,
            "label": label,
            "count": count,
            "severity": "warning",
            "color": COLORS["review"],
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
            "color": COLORS["review"],
            "source_count": count_key,
        }
        for chip_id, label, count_key in LANE_REVIEW_CHIP_CATEGORIES
    ]


def arc_support_preview_cue_chips(cues: Any) -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []
    for cue in list_value(cues):
        cue_id = text(cue)
        if not cue_id:
            continue
        label, severity, color = ARC_SUPPORT_PREVIEW_CUE_CHIPS.get(
            cue_id,
            (cue_id.replace("_", " ").title(), "info", COLORS["experimental"]),
        )
        chips.append({
            "id": cue_id,
            "label": label,
            "severity": severity,
            "color": color,
            "source": "arc_support_context.preview_cues",
        })
    return chips


def load_case_direction_label(x: float, y: float, z: float) -> str:
    labels = []
    for axis, value in (("X", x), ("Y", y), ("Z", z)):
        if abs(value) <= 1.0e-9:
            continue
        labels.append(f"{'+' if value > 0 else '-'}{axis}")
    return " ".join(labels) if labels else "0"


def load_case_vector_chips(vectors: Any, load_case_kind: str = "unknown") -> list[dict[str, Any]]:
    chips: list[dict[str, Any]] = []
    color = COLORS["review"] if load_case_kind == "custom_vector" else COLORS["load_path"]
    severity = "warning" if load_case_kind == "custom_vector" else "info"
    for fallback_index, item in enumerate(list_value(vectors)):
        vector = nested(item)
        if not vector:
            continue
        vector_id = text(vector.get("id"), f"load_vector_{fallback_index}")
        x = number(vector.get("x"), 0.0)
        y = number(vector.get("y"), 0.0)
        z = number(vector.get("z"), 0.0)
        magnitude = (x * x + y * y + z * z) ** 0.5
        normalized_vector = (
            {"x": round(x / magnitude, 6), "y": round(y / magnitude, 6), "z": round(z / magnitude, 6)}
            if magnitude > 1.0e-9
            else {"x": 0.0, "y": 0.0, "z": 0.0}
        )
        chips.append({
            "id": vector_id,
            "label": text(vector.get("label"), vector_id.replace("_", " ").title()),
            "severity": severity,
            "color": color,
            "source": "load_case.vectors",
            "direction_label": load_case_direction_label(x, y, z),
            "magnitude": round(magnitude, 6),
            "vector": {"x": x, "y": y, "z": z},
            "normalized_vector": normalized_vector,
        })
    return chips


def lane_readiness_needs_review(readiness: dict[str, Any]) -> bool:
    return (
        text(readiness.get("status")) == "needs_lane_review"
        or text(readiness.get("readiness_level")) == "needs_lane_review"
        or int(number(readiness.get("lane_readiness_review_issue_count"), 0.0)) > 0
        or int(number(readiness.get("validation_blocked_gate_count"), 0.0)) > 0
    )


def lane_readiness_review_message(summary: dict[str, Any]) -> str:
    if not lane_readiness_needs_review(summary):
        lane_count = int(number(summary.get("lane_count"), 0.0))
        return f"Lane readiness is metadata-ready for {lane_count} lane(s)."

    issue_count = int(number(summary.get("lane_readiness_review_issue_count"), 0.0))
    blocked_count = int(number(summary.get("validation_blocked_gate_count"), 0.0))
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
    return COLORS["review"] if lane_readiness_needs_review(readiness) else COLORS["orientation"]


def decorate_lane_readiness_review_fields(readiness: dict[str, Any]) -> dict[str, Any]:
    readiness["lane_readiness_review_issue_count"] = int(number(readiness.get("review_issue_count"), 0.0))
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


def nested(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def flatten_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float)):
        return [str(value)]
    if isinstance(value, list):
        result: list[str] = []
        for item in value:
            result.extend(flatten_strings(item))
        return result
    if isinstance(value, dict):
        result = []
        for item in value.values():
            result.extend(flatten_strings(item))
        return result
    return []


def split_material_family_source_values(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        result: list[str] = []
        for item in parsed:
            result.extend(split_material_family_source_values(text(item)))
        return result
    values = [value]
    for separator in (";", ",", "\n"):
        values = [piece for item in values for piece in item.split(separator)]
    return [item.strip() for item in values if item.strip()]


def strength_contract(existing: Any = None) -> dict[str, Any]:
    contract = dict(existing) if isinstance(existing, dict) else {}
    contract.update(STRENGTH_LENS_CONTRACT)
    return contract


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
        if normalized_key in NESTED_ADVISORY_FALSE_KEYS:
            if item is not False:
                normalizations.append(f"nested_advisory_guardrail_forced_false:{child_path}")
            scrubbed[key] = False
            continue
        if normalized_key in NESTED_ADVISORY_TRUE_KEYS:
            if item is not True:
                normalizations.append(f"nested_advisory_guardrail_forced_true:{child_path}")
            scrubbed[key] = True
            continue
        scrubbed[key] = scrub_external_command_payloads(item, normalizations, child_path)
    return scrubbed


def find_external_builder(explicit: Path | None) -> Path | None:
    candidates: list[Path] = []
    env_path = (
        os.environ.get("ORCASLICER_CODEX_STRENGTH_LENS_BUILDER", "").strip()
        or os.environ.get("TINMANX_STRENGTH_LENS_BUILDER", "").strip()
    )
    if explicit:
        candidates.append(explicit)
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(Path(__file__).resolve().parents[1] / "tools" / "build_strength_visualization.py")

    this_script = Path(__file__).resolve()
    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved == this_script:
            continue
        if resolved.exists():
            return resolved
    return None


def run_external_builder(args: argparse.Namespace, builder: Path) -> str | None:
    command = [
        sys.executable,
        str(builder),
        "--slice-result",
        str(args.slice_result),
        "--out",
        str(args.out),
        "--active-lens",
        args.active_lens,
        "--load-case",
        args.load_case,
    ]
    if args.fiber_preview_overlay:
        command.extend(["--fiber-preview-overlay", str(args.fiber_preview_overlay)])

    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode == 0 and args.out.exists():
        return None
    stderr = completed.stderr.strip() or completed.stdout.strip()
    return stderr or f"external builder exited {completed.returncode}"


def normalize_overlay_rows(
    value: Any,
    active_lens: str,
    normalizations: list[str],
    source: str,
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        if value is not None:
            normalizations.append("overlays_defaulted_empty")
        return []

    overlays: list[dict[str, Any]] = []
    lens_ids = {lens_id for lens_id, _ in LENSES}
    default_source = "external_builder" if source == "external_builder" else "orca_codex.strength_lens.contract"
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            normalizations.append(f"overlays.{index}_dropped_non_object")
            continue
        row = dict(item)
        details = dict(row.get("details")) if isinstance(row.get("details"), dict) else {}
        if not row.get("id"):
            row["id"] = f"{source}_overlay_{index}"
            normalizations.append(f"overlays.{index}.id_defaulted")
        if row.get("lens") not in lens_ids:
            details["original_lens"] = row.get("lens", "")
            row["lens"] = active_lens
            normalizations.append(f"overlays.{index}.lens_defaulted")
        if row.get("kind") not in KNOWN_OVERLAY_KINDS:
            details["original_kind"] = row.get("kind", "")
            row["kind"] = "advisory_only"
            normalizations.append(f"overlays.{index}.kind_defaulted")
        if row.get("severity") not in KNOWN_OVERLAY_SEVERITIES:
            details["original_severity"] = row.get("severity", "")
            row["severity"] = "info"
            normalizations.append(f"overlays.{index}.severity_defaulted")
        if not row.get("color"):
            row["color"] = COLORS["review"] if row.get("severity") == "warning" else COLORS["strong"]
            normalizations.append(f"overlays.{index}.color_defaulted")
        if not row.get("message"):
            row["message"] = "External Strength Lens overlay normalized for safe preview display."
            normalizations.append(f"overlays.{index}.message_defaulted")
        if not row.get("source"):
            row["source"] = default_source
            normalizations.append(f"overlays.{index}.source_defaulted")
        row["details"] = details
        overlays.append(row)
    return overlays


def enforce_advisory_contract(
    visualization: dict[str, Any],
    source: str,
    slice_result: dict[str, Any] | None = None,
    fiber_overlay: dict[str, Any] | None = None,
    active_lens: str | None = None,
    selected_load_case: str = "unknown",
) -> dict[str, Any]:
    normalized = dict(visualization)
    normalizations: list[str] = list(normalized.get("orcaslicer_codex_advisory_normalizations", [])) \
        if isinstance(normalized.get("orcaslicer_codex_advisory_normalizations"), list) else []

    status = text(normalized.get("status"), "external_predictive")
    if any(token in status.lower() for token in ("certified", "approved", "hardware_ready")):
        normalized["status"] = "external_predictive"
        normalizations.append("status_forced_external_predictive")
    elif not normalized.get("status"):
        normalized["status"] = "external_predictive"
        normalizations.append("status_defaulted_external_predictive")

    scope = dict(normalized.get("scope")) if isinstance(normalized.get("scope"), dict) else {}
    for key, value in [
        ("applies_to_all_printers", True),
        ("applies_to_non_continuous_fiber", True),
        ("continuous_fiber_required", False),
        ("slicing_or_gcode_modified", False),
    ]:
        if scope.get(key) != value:
            normalizations.append(f"scope.{key}_forced_{str(value).lower()}")
        scope[key] = value
    normalized["scope"] = scope

    display = dict(normalized.get("display")) if isinstance(normalized.get("display"), dict) else {}
    guardrail = text(display.get("guardrail"))
    if "not certified FEA" not in guardrail or "not a print approval" not in guardrail:
        display["guardrail"] = "predictive planning display only; not certified FEA, not a safety factor, and not a print approval"
        normalizations.append("display.guardrail_forced_advisory")
    normalized["display"] = display

    summary = dict(normalized.get("summary")) if isinstance(normalized.get("summary"), dict) else {}
    if summary.get("advisory_only") is not True:
        normalizations.append("summary.advisory_only_forced_true")
    summary["advisory_only"] = True

    requested_load_case = selected_load_case if selected_load_case in LOAD_CASE_MESSAGES else "unknown"
    load_case = dict(normalized.get("load_case")) if isinstance(normalized.get("load_case"), dict) else {}
    load_vectors = LOAD_CASE_VECTORS.get(requested_load_case, [])
    load_vector_chips = load_case_vector_chips(load_vectors, requested_load_case)
    expected_load_case = {
        "kind": requested_load_case,
        "label": requested_load_case.replace("_", " ").title(),
        "message": LOAD_CASE_MESSAGES[requested_load_case],
        "vectors": load_vectors,
        "vector_chips": load_vector_chips,
        "vector_chip_count": len(load_vector_chips),
    }
    for key, expected_value in expected_load_case.items():
        if load_case.get(key) != expected_value:
            normalizations.append(LOAD_CASE_NORMALIZATION_TOKENS[key])
        load_case[key] = expected_value
    normalized["load_case"] = load_case
    summary["load_case_kind"] = requested_load_case
    summary["load_case_label"] = expected_load_case["label"]
    summary["load_case_message"] = expected_load_case["message"]
    summary["load_case_vector_count"] = len(load_vectors)
    summary["load_case_vectors"] = load_vectors
    summary["load_case_vector_chips"] = load_vector_chips
    summary["load_case_vector_chip_count"] = len(load_vector_chips)

    expected_strength = strength_map(slice_result or {}, fiber_overlay or {})
    expected_strength_ready = expected_strength.get("status") == "ready"
    strength = dict(normalized.get("strength_map")) if isinstance(normalized.get("strength_map"), dict) else {}
    if expected_strength_ready and (not strength or strength.get("status") in {None, "", "unavailable"}):
        strength = dict(expected_strength)
        normalizations.append(
            "external_builder_did_not_emit_strength_map_backfilled_from_slice_result"
            if source == "external_builder" else "strength_map_backfilled_from_slice_result"
        )
    elif not strength:
        normalizations.append("strength_map_defaulted_unavailable")
    strength["schema_version"] = text(strength.get("schema_version"), "1.0.0")
    strength["status"] = text(strength.get("status"), "unavailable")
    strength["basis"] = text(strength.get("basis"))
    strength["estimated"] = bool(strength.get("estimated", False))
    if strength.get("advisory_only") is not True:
        normalizations.append("strength_map.advisory_only_forced_true")
    strength["advisory_only"] = True
    family = dict(strength.get("material_family_estimate")) if isinstance(strength.get("material_family_estimate"), dict) else {}
    if not family:
        normalizations.append("strength_map.material_family_estimate_defaulted_unavailable")
    family["schema_version"] = text(family.get("schema_version"), "1.0.0")
    family["status"] = text(family.get("status"), "unavailable")
    family["reason"] = text(
        family.get("reason"),
        "external_builder_did_not_emit_material_family_estimate"
        if source == "external_builder" else "missing_material_family_estimate",
    )
    family_key = text(family.get("family_key"))
    if family_key:
        fill_metadata = material_family_fill_metadata(family_key)
        for key, expected_value in fill_metadata.items():
            if family.get(key) != expected_value:
                normalizations.append(f"strength_map.material_family_estimate.{key}_defaulted_from_family_key")
            family[key] = expected_value
    if family.get("advisory_only") is not True:
        normalizations.append("strength_map.material_family_estimate.advisory_only_forced_true")
    family["advisory_only"] = True
    strength["material_family_estimate"] = family
    normalized["strength_map"] = strength
    summary["strength_map_basis"] = strength.get("basis", "")
    summary["strength_map_estimated"] = strength.get("estimated", False)
    summary["material_family_estimate_status"] = family.get("status", "unavailable")
    summary["material_family"] = family.get("family_key", "")
    summary["material_family_base_polymer"] = family.get("base_polymer", "")
    summary["material_family_reinforcement_type"] = family.get("reinforcement_type", "none")
    summary["material_family_is_filled"] = bool(family.get("is_filled_family", False))

    expected_orientation = orientation_confidence(strength)
    expected_orientation_ready = expected_orientation.get("status") == "ready"
    orientation = dict(normalized.get("orientation_confidence")) \
        if isinstance(normalized.get("orientation_confidence"), dict) else {}
    if expected_orientation_ready and (not orientation or orientation.get("status") in {None, "", "needs_material_axis_data"}):
        orientation = dict(expected_orientation)
        normalizations.append(
            "external_builder_did_not_emit_orientation_confidence_backfilled_from_strength_map"
            if source == "external_builder" else "orientation_confidence_backfilled_from_strength_map"
        )
    elif not orientation:
        normalizations.append("orientation_confidence_defaulted_setup_required")
    orientation["schema_version"] = text(orientation.get("schema_version"), "1.0.0")
    orientation["status"] = text(orientation.get("status"), "needs_material_axis_data")
    orientation["confidence_level"] = text(orientation.get("confidence_level"), "setup_required")
    orientation["reason"] = text(
        orientation.get("reason"),
        "external_builder_did_not_emit_orientation_confidence"
        if source == "external_builder" else "missing_strength_map",
    )
    if orientation.get("advisory_only") is not True:
        normalizations.append("orientation_confidence.advisory_only_forced_true")
    orientation["advisory_only"] = True
    normalized["orientation_confidence"] = orientation
    summary["orientation_confidence_level"] = orientation.get("confidence_level", "setup_required")
    summary["weakest_print_axis"] = orientation.get("weakest_print_axis", "")
    summary["strongest_print_axis"] = orientation.get("strongest_print_axis", "")

    expected_mixed_context = mixed_filament_context(fiber_overlay or {}, slice_result or {})
    expected_mixed_ready = expected_mixed_context.get("status") == "ready"
    mixed_context = dict(normalized.get("mixed_filament_context")) \
        if isinstance(normalized.get("mixed_filament_context"), dict) else {}
    had_mixed_context = bool(mixed_context)
    mixed_lanes = mixed_context.get("lanes") if isinstance(mixed_context.get("lanes"), list) else []
    if expected_mixed_ready and (not had_mixed_context or not mixed_lanes):
        mixed_context = dict(expected_mixed_context)
        normalizations.append(
            "external_builder_did_not_emit_mixed_filament_context_backfilled_from_fiber_overlay"
            if source == "external_builder" and not had_mixed_context
            else "mixed_filament_context.lanes_backfilled_from_fiber_overlay"
        )
    elif not mixed_context:
        normalizations.append("mixed_filament_context_defaulted_unavailable")
    mixed_context["schema_version"] = text(mixed_context.get("schema_version"), "1.0.0")
    mixed_context["status"] = text(mixed_context.get("status"), "unavailable")
    mixed_context["reason"] = text(
        mixed_context.get("reason"),
        "external_builder_did_not_emit_mixed_filament_context"
        if source == "external_builder" else "missing_lane_contract",
    )
    mixed_context["source"] = text(mixed_context.get("source"), "orcaslicer_codex.fiber_metadata_sidecar")
    if not isinstance(mixed_context.get("lanes"), list):
        mixed_context["lanes"] = []
    if not isinstance(mixed_context.get("material_palette"), list):
        mixed_context["material_palette"] = []
    mixed_context = normalize_mixed_context_lane_identity(mixed_context, normalizations)
    readiness = dict(mixed_context.get("lane_readiness_summary")) \
        if isinstance(mixed_context.get("lane_readiness_summary"), dict) else {}
    if not readiness:
        normalizations.append("mixed_filament_context.lane_readiness_summary_defaulted_unavailable")
    readiness["schema_version"] = text(readiness.get("schema_version"), "1.0.0")
    readiness["status"] = text(readiness.get("status"), "unavailable")
    readiness["readiness_level"] = text(readiness.get("readiness_level"))
    readiness["source"] = text(readiness.get("source"), "orcaslicer_codex.fiber_metadata_sidecar")
    for key in (
        "unknown_material_lane_indices",
        "missing_color_lane_indices",
        "missing_nozzle_lane_indices",
        "validation_blocked_gate_ids",
        "validation_blocked_gate_messages",
    ):
        if not isinstance(readiness.get(key), list):
            readiness[key] = []
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
        readiness[key] = int(number(readiness.get(key), 0.0))
    readiness["hardware_ready"] = False
    readiness["command_emission_allowed"] = False
    readiness["advisory_only"] = True
    readiness = decorate_lane_readiness_review_fields(readiness)
    mixed_context["lane_readiness_summary"] = readiness
    mixed_context["lane_readiness_status"] = readiness.get("status", "unavailable")
    mixed_context["lane_readiness_level"] = readiness.get("readiness_level", "")
    mixed_context["review_issue_count"] = readiness.get("review_issue_count", 0)
    mixed_context["lane_readiness_review_issue_count"] = readiness.get("lane_readiness_review_issue_count", 0)
    mixed_context["lane_readiness_review_needed"] = bool(readiness.get("lane_readiness_review_needed", False))
    mixed_context["lane_readiness_review_message"] = text(readiness.get("lane_readiness_review_message"))
    mixed_context["lane_readiness_review_severity"] = text(readiness.get("lane_readiness_review_severity"), "info")
    mixed_context["lane_readiness_review_color"] = text(readiness.get("lane_readiness_review_color"), COLORS["orientation"])
    mixed_context["continuous_fiber_lane_count"] = readiness.get("continuous_fiber_lane_count", 0)
    mixed_context["filled_material_lane_count"] = int(number(
        mixed_context.get("filled_material_lane_count"),
        float(material_family_filled_lane_count(mixed_context.get("lanes", []))),
    ))
    filled_badges = filled_material_lane_badges(mixed_context.get("lane_badges", []))
    mixed_context["filled_material_lane_badges"] = filled_badges
    mixed_context["filled_material_lane_badge_count"] = len(filled_badges)
    mixed_context["polymer_lane_count"] = readiness.get("polymer_lane_count", 0)
    mixed_context["missing_material_lane_count"] = readiness.get("missing_material_lane_count", 0)
    mixed_context["missing_color_lane_count"] = readiness.get("missing_color_lane_count", 0)
    mixed_context["missing_nozzle_lane_count"] = readiness.get("missing_nozzle_lane_count", 0)
    mixed_context["validation_blocked_gate_count"] = readiness.get("validation_blocked_gate_count", 0)
    mixed_context["validation_blocked_gate_ids"] = readiness.get("validation_blocked_gate_ids", [])
    mixed_context["validation_blocked_gate_messages"] = readiness.get("validation_blocked_gate_messages", [])
    mixed_context["lane_readiness_review_chip_categories"] = lane_readiness_review_chip_categories()
    mixed_context["lane_readiness_review_chip_category_count"] = len(mixed_context["lane_readiness_review_chip_categories"])
    mixed_context["lane_readiness_review_chips"] = lane_readiness_review_chips(mixed_context)
    mixed_context["lane_readiness_review_chip_count"] = len(mixed_context["lane_readiness_review_chips"])
    mixed_context["lane_readiness_review_reasons"] = lane_readiness_review_reasons(mixed_context)
    mixed_context["lane_readiness_review_reason_count"] = len(mixed_context["lane_readiness_review_reasons"])
    mixed_context["advisory_only"] = True
    normalized["mixed_filament_context"] = mixed_context
    summary["mixed_filament_lane_count"] = mixed_context.get("lane_count", 0) if mixed_context.get("status") == "ready" else 0
    summary["mixed_filament_material_count"] = (
        mixed_context.get("selected_material_count", 0) if mixed_context.get("status") == "ready" else 0
    )
    summary["mixed_filament_lane_badge_count"] = (
        mixed_context.get("lane_badge_count", 0) if mixed_context.get("status") == "ready" else 0
    )
    summary["lane_readiness_status"] = mixed_context["lane_readiness_status"]
    summary["lane_readiness_level"] = mixed_context["lane_readiness_level"]
    summary["lane_readiness_review_issue_count"] = mixed_context["lane_readiness_review_issue_count"]
    summary["lane_readiness_review_needed"] = mixed_context["lane_readiness_review_needed"]
    summary["lane_readiness_review_message"] = mixed_context["lane_readiness_review_message"]
    summary["lane_readiness_review_severity"] = mixed_context["lane_readiness_review_severity"]
    summary["lane_readiness_review_color"] = mixed_context["lane_readiness_review_color"]
    summary["continuous_fiber_lane_count"] = mixed_context["continuous_fiber_lane_count"]
    summary["filled_material_lane_count"] = mixed_context["filled_material_lane_count"]
    summary["filled_material_lane_badge_count"] = mixed_context["filled_material_lane_badge_count"]
    summary["filled_material_lane_badges"] = mixed_context["filled_material_lane_badges"]
    summary["missing_material_lane_count"] = mixed_context["missing_material_lane_count"]
    summary["missing_color_lane_count"] = mixed_context["missing_color_lane_count"]
    summary["missing_nozzle_lane_count"] = mixed_context["missing_nozzle_lane_count"]
    summary["validation_blocked_gate_count"] = mixed_context["validation_blocked_gate_count"]
    summary["validation_blocked_gate_ids"] = mixed_context["validation_blocked_gate_ids"]
    summary["validation_blocked_gate_messages"] = mixed_context["validation_blocked_gate_messages"]
    summary["lane_readiness_review_chip_categories"] = mixed_context["lane_readiness_review_chip_categories"]
    summary["lane_readiness_review_chip_category_count"] = mixed_context["lane_readiness_review_chip_category_count"]
    summary["lane_readiness_review_chips"] = mixed_context["lane_readiness_review_chips"]
    summary["lane_readiness_review_chip_count"] = mixed_context["lane_readiness_review_chip_count"]
    summary["lane_readiness_review_reasons"] = mixed_context["lane_readiness_review_reasons"]
    summary["lane_readiness_review_reason_count"] = mixed_context["lane_readiness_review_reason_count"]

    expected_arc_context = arc_support_context(slice_result or {})
    arc_context = dict(normalized.get("arc_support_context")) \
        if isinstance(normalized.get("arc_support_context"), dict) else {}
    had_arc_context = bool(arc_context)
    if not had_arc_context:
        normalizations.append(
            "external_builder_did_not_emit_arc_support_context"
            if source == "external_builder" else "arc_support_context_defaulted_from_slice_result"
        )
    for key, expected_value in expected_arc_context.items():
        if had_arc_context and arc_context.get(key) != expected_value:
            normalizations.append(f"arc_support_context.{key}_forced_from_slice_result")
        arc_context[key] = expected_value
    normalized["arc_support_context"] = arc_context
    summary["arc_support_selected"] = arc_context.get("arc_support_selected", False)
    summary["arc_support_preview_status"] = arc_context.get("status", "unavailable")
    summary["arc_support_preview_label"] = arc_context.get("preview_label", "")
    summary["arc_support_postprocess_stage"] = arc_context.get("postprocess_stage", "")
    summary["arc_support_guarded_transform_required"] = arc_context.get("guarded_transform_required", False)
    summary["arc_support_preview_cue_count"] = arc_context.get("preview_cue_count", 0)
    summary["arc_support_preview_cue_chips"] = arc_context.get("preview_cue_chips", [])
    summary["arc_support_preview_cue_chip_count"] = arc_context.get("preview_cue_chip_count", 0)
    normalized["summary"] = summary

    legend = normalized.get("legend") if isinstance(normalized.get("legend"), list) else []
    if not legend:
        normalizations.append("legend.defaulted_from_mixed_context")
        legend = viewport_legend(mixed_context)
    normalized["legend"] = legend
    if summary.get("legend_count") != len(legend):
        normalizations.append("summary.legend_count_defaulted_from_legend")
    summary["legend_count"] = len(legend)
    normalized["summary"] = summary

    viewport = dict(normalized.get("viewport_render_plan")) if isinstance(normalized.get("viewport_render_plan"), dict) else {}
    lens_ids = {lens_id for lens_id, _ in LENSES}
    selected_lens = text(viewport.get("active_lens"), text(normalized.get("active_lens"), active_lens or "orientation_risk"))
    if selected_lens not in lens_ids:
        normalizations.append("viewport_render_plan.active_lens_defaulted_orientation_risk")
        selected_lens = "orientation_risk"
    overlays = normalize_overlay_rows(normalized.get("overlays"), selected_lens, normalizations, source)
    normalized["overlays"] = overlays
    if not viewport.get("schema_version"):
        normalizations.append("viewport_render_plan.schema_version_defaulted")
    viewport["schema_version"] = text(viewport.get("schema_version"), "1.0.0")
    if not viewport.get("status"):
        normalizations.append("viewport_render_plan.status_defaulted")
    viewport["status"] = text(viewport.get("status"), "ready" if overlays else "empty")
    if viewport.get("active_lens") != selected_lens:
        normalizations.append("viewport_render_plan.active_lens_defaulted")
    viewport["active_lens"] = selected_lens
    if viewport.get("render_mode") != "non_destructive_preview_overlay":
        normalizations.append("viewport_render_plan.render_mode_forced_non_destructive")
    viewport["render_mode"] = "non_destructive_preview_overlay"
    raw_layers = viewport.get("layers") if isinstance(viewport.get("layers"), list) else []
    rendered_lenses = {item.get("lens") for item in raw_layers if isinstance(item, dict)}
    if not lens_ids.issubset(rendered_lenses):
        normalizations.append("viewport_render_plan.layers_defaulted")
        raw_layers = [
            {
                "lens": lens_id,
                "label": label,
                "visible_by_default": lens_id == selected_lens,
                "render_style": "surface_tint_and_badge_cues",
                "model_target": "selected_model_surface",
                "overlay_count": sum(1 for item in overlays if isinstance(item, dict) and item.get("lens") == lens_id),
                "warning_count": sum(
                    1
                    for item in overlays
                    if isinstance(item, dict) and item.get("lens") == lens_id and item.get("severity") == "warning"
                ),
            }
            for lens_id, label in LENSES
        ]
    viewport["layers"] = raw_layers
    if not isinstance(viewport.get("top_cues"), list):
        normalizations.append("viewport_render_plan.top_cues_defaulted")
        viewport["top_cues"] = overlays[:6]
    expected_overlay_count = len(overlays)
    expected_warning_overlay_count = sum(1 for item in overlays if item.get("severity") == "warning")
    expected_top_cue_count = len(viewport["top_cues"]) if isinstance(viewport.get("top_cues"), list) else 0
    expected_lens_overlay_counts = {
        lens_id: sum(1 for item in overlays if item.get("lens") == lens_id)
        for lens_id, _ in LENSES
    }
    expected_lens_warning_counts = {
        lens_id: sum(1 for item in overlays if item.get("lens") == lens_id and item.get("severity") == "warning")
        for lens_id, _ in LENSES
    }
    if viewport.get("overlay_count") != expected_overlay_count:
        normalizations.append(VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS["overlay_count"])
    viewport["overlay_count"] = expected_overlay_count
    if viewport.get("warning_overlay_count") != expected_warning_overlay_count:
        normalizations.append(VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS["warning_overlay_count"])
    viewport["warning_overlay_count"] = expected_warning_overlay_count
    if viewport.get("top_cue_count") != expected_top_cue_count:
        normalizations.append(VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS["top_cue_count"])
    viewport["top_cue_count"] = expected_top_cue_count
    if viewport.get("lens_overlay_counts") != expected_lens_overlay_counts:
        normalizations.append(VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS["lens_overlay_counts"])
    viewport["lens_overlay_counts"] = expected_lens_overlay_counts
    if viewport.get("lens_warning_counts") != expected_lens_warning_counts:
        normalizations.append(VIEWPORT_OVERLAY_SUMMARY_NORMALIZATION_TOKENS["lens_warning_counts"])
    viewport["lens_warning_counts"] = expected_lens_warning_counts
    expected_lane_badges = (
        mixed_context.get("lane_badges")
        if isinstance(mixed_context.get("lane_badges"), list)
        else []
    )
    current_lane_badges = viewport.get("lane_badges") if isinstance(viewport.get("lane_badges"), list) else []
    if expected_lane_badges:
        if current_lane_badges != expected_lane_badges:
            normalizations.append("viewport_render_plan.lane_badges_defaulted_from_mixed_context")
        viewport["lane_badges"] = expected_lane_badges
    else:
        if not isinstance(viewport.get("lane_badges"), list):
            normalizations.append("viewport_render_plan.lane_badges_defaulted")
        viewport["lane_badges"] = current_lane_badges
    if viewport.get("lane_badge_count") != len(viewport["lane_badges"]):
        normalizations.append("viewport_render_plan.lane_badge_count_defaulted")
    viewport["lane_badge_count"] = len(viewport["lane_badges"])
    expected_lane_readiness_status = text(mixed_context.get("lane_readiness_status"), "unavailable")
    expected_lane_readiness_level = text(mixed_context.get("lane_readiness_level"))
    if viewport.get("lane_readiness_status") != expected_lane_readiness_status:
        normalizations.append("viewport_render_plan.lane_readiness_status_defaulted_from_mixed_context")
    viewport["lane_readiness_status"] = expected_lane_readiness_status
    if viewport.get("lane_readiness_level") != expected_lane_readiness_level:
        normalizations.append("viewport_render_plan.lane_readiness_level_defaulted_from_mixed_context")
    viewport["lane_readiness_level"] = expected_lane_readiness_level
    for key, output_key, default in MIXED_FILAMENT_VIEWPORT_TEXT_FIELDS:
        expected_value = text(mixed_context.get(key), default)
        if viewport.get(output_key) != expected_value:
            normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    for key, output_key, default in MIXED_FILAMENT_VIEWPORT_COUNT_FIELDS:
        expected_value = int(number(mixed_context.get(key), float(default)))
        if viewport.get(output_key) != expected_value:
            normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    for key, output_key, default in MIXED_FILAMENT_VIEWPORT_BOOL_FIELDS:
        expected_value = bool(mixed_context.get(key, default))
        if viewport.get(output_key) is not expected_value:
            normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    for key, output_key in MIXED_FILAMENT_VIEWPORT_LIST_FIELDS:
        expected_value = mixed_context.get(key) if isinstance(mixed_context.get(key), list) else []
        if viewport.get(output_key) != expected_value:
            normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    expected_lane_review_chips = lane_readiness_review_chips(mixed_context)
    expected_lane_review_categories = lane_readiness_review_chip_categories()
    if viewport.get("lane_readiness_review_chip_categories") != expected_lane_review_categories:
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_chip_categories"])
    viewport["lane_readiness_review_chip_categories"] = expected_lane_review_categories
    if viewport.get("lane_readiness_review_chip_category_count") != len(expected_lane_review_categories):
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_chip_category_count"])
    viewport["lane_readiness_review_chip_category_count"] = len(expected_lane_review_categories)
    if viewport.get("lane_readiness_review_chips") != expected_lane_review_chips:
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_chips"])
    viewport["lane_readiness_review_chips"] = expected_lane_review_chips
    if viewport.get("lane_readiness_review_chip_count") != len(expected_lane_review_chips):
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_chip_count"])
    viewport["lane_readiness_review_chip_count"] = len(expected_lane_review_chips)
    expected_lane_review_reasons = lane_readiness_review_reasons(mixed_context)
    if viewport.get("lane_readiness_review_reasons") != expected_lane_review_reasons:
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_reasons"])
    viewport["lane_readiness_review_reasons"] = expected_lane_review_reasons
    if viewport.get("lane_readiness_review_reason_count") != len(expected_lane_review_reasons):
        normalizations.append(MIXED_FILAMENT_VIEWPORT_NORMALIZATION_TOKENS["lane_readiness_review_reason_count"])
    viewport["lane_readiness_review_reason_count"] = len(expected_lane_review_reasons)
    expected_arc_selected = bool(arc_context.get("arc_support_selected", False))
    expected_arc_status = text(arc_context.get("status"), "unavailable")
    expected_arc_label = text(arc_context.get("preview_label"))
    expected_arc_status_message = text(arc_context.get("preview_status_message"))
    expected_arc_stage = text(arc_context.get("postprocess_stage"))
    expected_arc_guardrail = text(arc_context.get("guardrail_summary"))
    expected_arc_guarded = bool(arc_context.get("guarded_transform_required", False))
    expected_arc_cues = arc_context.get("preview_cues") if isinstance(arc_context.get("preview_cues"), list) else []
    expected_arc_cue_count = int(number(arc_context.get("preview_cue_count"), float(len(expected_arc_cues))))
    expected_arc_cue_chips = arc_context.get("preview_cue_chips") \
        if isinstance(arc_context.get("preview_cue_chips"), list) else arc_support_preview_cue_chips(expected_arc_cues)
    expected_arc_cue_chip_count = int(
        number(arc_context.get("preview_cue_chip_count"), float(len(expected_arc_cue_chips)))
    )
    if viewport.get("arc_support_selected") != expected_arc_selected:
        normalizations.append("viewport_render_plan.arc_support_selected_defaulted_from_arc_context")
    viewport["arc_support_selected"] = expected_arc_selected
    if viewport.get("arc_support_preview_status") != expected_arc_status:
        normalizations.append("viewport_render_plan.arc_support_preview_status_defaulted_from_arc_context")
    viewport["arc_support_preview_status"] = expected_arc_status
    if viewport.get("arc_support_preview_label") != expected_arc_label:
        normalizations.append("viewport_render_plan.arc_support_preview_label_defaulted_from_arc_context")
    viewport["arc_support_preview_label"] = expected_arc_label
    if viewport.get("arc_support_preview_status_message") != expected_arc_status_message:
        normalizations.append("viewport_render_plan.arc_support_preview_status_message_defaulted_from_arc_context")
    viewport["arc_support_preview_status_message"] = expected_arc_status_message
    if viewport.get("arc_support_postprocess_stage") != expected_arc_stage:
        normalizations.append("viewport_render_plan.arc_support_postprocess_stage_defaulted_from_arc_context")
    viewport["arc_support_postprocess_stage"] = expected_arc_stage
    if viewport.get("arc_support_guardrail_summary") != expected_arc_guardrail:
        normalizations.append("viewport_render_plan.arc_support_guardrail_summary_defaulted_from_arc_context")
    viewport["arc_support_guardrail_summary"] = expected_arc_guardrail
    if viewport.get("arc_support_guarded_transform_required") != expected_arc_guarded:
        normalizations.append("viewport_render_plan.arc_support_guarded_transform_required_defaulted_from_arc_context")
    viewport["arc_support_guarded_transform_required"] = expected_arc_guarded
    if viewport.get("arc_support_preview_cues") != expected_arc_cues:
        normalizations.append("viewport_render_plan.arc_support_preview_cues_defaulted_from_arc_context")
    viewport["arc_support_preview_cues"] = expected_arc_cues
    if viewport.get("arc_support_preview_cue_count") != expected_arc_cue_count:
        normalizations.append("viewport_render_plan.arc_support_preview_cue_count_defaulted_from_arc_context")
    viewport["arc_support_preview_cue_count"] = expected_arc_cue_count
    if viewport.get("arc_support_preview_cue_chips") != expected_arc_cue_chips:
        normalizations.append("viewport_render_plan.arc_support_preview_cue_chips_defaulted_from_arc_context")
    viewport["arc_support_preview_cue_chips"] = expected_arc_cue_chips
    if viewport.get("arc_support_preview_cue_chip_count") != expected_arc_cue_chip_count:
        normalizations.append("viewport_render_plan.arc_support_preview_cue_chip_count_defaulted_from_arc_context")
    viewport["arc_support_preview_cue_chip_count"] = expected_arc_cue_chip_count
    expected_strength_status = text(strength.get("status"), "unavailable")
    expected_strength_basis = text(strength.get("basis"))
    expected_strength_estimated = bool(strength.get("estimated", False))
    expected_family = nested(strength.get("material_family_estimate"))
    expected_family_axis_strengths = nested(expected_family.get("print_axis_tensile_strength_mpa"))
    if viewport.get("strength_map_status") != expected_strength_status:
        normalizations.append("viewport_render_plan.strength_map_status_defaulted_from_strength_map")
    viewport["strength_map_status"] = expected_strength_status
    if viewport.get("strength_map_basis") != expected_strength_basis:
        normalizations.append("viewport_render_plan.strength_map_basis_defaulted_from_strength_map")
    viewport["strength_map_basis"] = expected_strength_basis
    if viewport.get("strength_map_estimated") != expected_strength_estimated:
        normalizations.append("viewport_render_plan.strength_map_estimated_defaulted_from_strength_map")
    viewport["strength_map_estimated"] = expected_strength_estimated
    for key, output_key, default in STRENGTH_MAP_VIEWPORT_FIELDS:
        expected_value = strength.get(key, default)
        if isinstance(default, str):
            expected_value = text(expected_value, default)
        else:
            expected_value = number(expected_value, float(default))
        if viewport.get(output_key) != expected_value:
            normalizations.append(STRENGTH_MAP_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    expected_axis_bands = strength.get("print_axis_bands") if isinstance(strength.get("print_axis_bands"), list) else []
    if viewport.get("print_axis_bands") != expected_axis_bands:
        normalizations.append(STRENGTH_MAP_VIEWPORT_NORMALIZATION_TOKENS["print_axis_bands"])
    viewport["print_axis_bands"] = expected_axis_bands
    if viewport.get("print_axis_band_count") != len(expected_axis_bands):
        normalizations.append(STRENGTH_MAP_VIEWPORT_NORMALIZATION_TOKENS["print_axis_band_count"])
    viewport["print_axis_band_count"] = len(expected_axis_bands)
    for key, output_key, default in MATERIAL_FAMILY_VIEWPORT_FIELDS:
        expected_value = text(expected_family.get(key), default)
        if viewport.get(output_key) != expected_value:
            normalizations.append(MATERIAL_FAMILY_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    expected_family_is_filled = bool(expected_family.get("is_filled_family", False))
    if viewport.get("material_family_is_filled") != expected_family_is_filled:
        normalizations.append(MATERIAL_FAMILY_VIEWPORT_NORMALIZATION_TOKENS["material_family_is_filled"])
    viewport["material_family_is_filled"] = expected_family_is_filled
    if viewport.get("material_family_axis_strengths_mpa") != expected_family_axis_strengths:
        normalizations.append(MATERIAL_FAMILY_VIEWPORT_NORMALIZATION_TOKENS["material_family_axis_strengths_mpa"])
    viewport["material_family_axis_strengths_mpa"] = expected_family_axis_strengths
    expected_orientation_level = text(orientation.get("confidence_level"), "setup_required")
    expected_strongest_axis = text(orientation.get("strongest_print_axis"))
    expected_weakest_axis = text(orientation.get("weakest_print_axis"))
    for key, output_key, default in ORIENTATION_CONFIDENCE_VIEWPORT_FIELDS:
        expected_value = orientation.get(key, default)
        if isinstance(default, str):
            expected_value = text(expected_value, default)
        elif isinstance(default, bool):
            expected_value = bool(expected_value)
        else:
            expected_value = number(expected_value, float(default))
        if viewport.get(output_key) != expected_value:
            normalizations.append(ORIENTATION_CONFIDENCE_VIEWPORT_NORMALIZATION_TOKENS[output_key])
        viewport[output_key] = expected_value
    expected_warning_axes = orientation.get("warning_axes") if isinstance(orientation.get("warning_axes"), list) else []
    if viewport.get("orientation_warning_axes") != expected_warning_axes:
        normalizations.append(ORIENTATION_CONFIDENCE_VIEWPORT_NORMALIZATION_TOKENS["orientation_warning_axes"])
    viewport["orientation_warning_axes"] = expected_warning_axes
    if viewport.get("orientation_confidence_level") != expected_orientation_level:
        normalizations.append("viewport_render_plan.orientation_confidence_level_defaulted_from_orientation_confidence")
    viewport["orientation_confidence_level"] = expected_orientation_level
    if viewport.get("strongest_print_axis") != expected_strongest_axis:
        normalizations.append("viewport_render_plan.strongest_print_axis_defaulted_from_orientation_confidence")
    viewport["strongest_print_axis"] = expected_strongest_axis
    if viewport.get("weakest_print_axis") != expected_weakest_axis:
        normalizations.append("viewport_render_plan.weakest_print_axis_defaulted_from_orientation_confidence")
    viewport["weakest_print_axis"] = expected_weakest_axis
    expected_load_kind = text(load_case.get("kind"), "unknown")
    expected_load_label = text(load_case.get("label"))
    expected_load_message = text(load_case.get("message"))
    expected_load_vectors = load_case.get("vectors") if isinstance(load_case.get("vectors"), list) else []
    expected_load_vector_chips = (
        load_case.get("vector_chips")
        if isinstance(load_case.get("vector_chips"), list)
        else load_case_vector_chips(expected_load_vectors, expected_load_kind)
    )
    if viewport.get("load_case_kind") != expected_load_kind:
        normalizations.append("viewport_render_plan.load_case_kind_defaulted_from_load_case")
    viewport["load_case_kind"] = expected_load_kind
    if viewport.get("load_case_label") != expected_load_label:
        normalizations.append("viewport_render_plan.load_case_label_defaulted_from_load_case")
    viewport["load_case_label"] = expected_load_label
    if viewport.get("load_case_message") != expected_load_message:
        normalizations.append("viewport_render_plan.load_case_message_defaulted_from_load_case")
    viewport["load_case_message"] = expected_load_message
    if viewport.get("load_case_vector_count") != len(expected_load_vectors):
        normalizations.append("viewport_render_plan.load_case_vector_count_defaulted_from_load_case")
    viewport["load_case_vector_count"] = len(expected_load_vectors)
    if viewport.get("load_case_vectors") != expected_load_vectors:
        normalizations.append("viewport_render_plan.load_case_vectors_defaulted_from_load_case")
    viewport["load_case_vectors"] = expected_load_vectors
    if viewport.get("load_case_vector_chips") != expected_load_vector_chips:
        normalizations.append("viewport_render_plan.load_case_vector_chips_defaulted_from_load_case")
    viewport["load_case_vector_chips"] = expected_load_vector_chips
    if viewport.get("load_case_vector_chip_count") != len(expected_load_vector_chips):
        normalizations.append("viewport_render_plan.load_case_vector_chip_count_defaulted_from_load_case")
    viewport["load_case_vector_chip_count"] = len(expected_load_vector_chips)
    expected_legend = normalized.get("legend") if isinstance(normalized.get("legend"), list) else []
    if viewport.get("legend") != expected_legend:
        normalizations.append("viewport_render_plan.legend_defaulted_from_legend")
    viewport["legend"] = expected_legend
    if viewport.get("legend_count") != len(expected_legend):
        normalizations.append("viewport_render_plan.legend_count_defaulted_from_legend")
    viewport["legend_count"] = len(expected_legend)
    if viewport.get("advisory_only") is not True:
        normalizations.append(VIEWPORT_GUARDRAIL_NORMALIZATION_TOKENS["advisory_only"])
    viewport["advisory_only"] = True
    for key in VIEWPORT_GUARDRAIL_FALSE_FIELDS:
        if viewport.get(key) is not False:
            normalizations.append(VIEWPORT_GUARDRAIL_NORMALIZATION_TOKENS[key])
        viewport[key] = False
    viewport["safety_note"] = "Viewport cues are predictive display metadata only; they do not alter slicing, G-code, or printer behavior."
    normalized["viewport_render_plan"] = viewport

    for key in ("certified_fea", "certified_safety_factor", "print_approval", "machine_ready_structural_approval"):
        if normalized.get(key) not in {None, False}:
            normalizations.append(f"{key}_forced_false")
        normalized[key] = False

    normalized["advisory_only"] = True
    normalized["schema_version"] = text(normalized.get("schema_version"), "1.0.0")
    normalized["contract"] = strength_contract(normalized.get("contract"))
    normalized["mechanics_reference"] = normalized.get("mechanics_reference") if isinstance(normalized.get("mechanics_reference"), dict) else MECHANICS_REFERENCE
    normalized["simulation_reference"] = normalized.get("simulation_reference") if isinstance(normalized.get("simulation_reference"), dict) else SIMULATION_REFERENCE
    if source == "external_builder":
        normalized = scrub_external_command_payloads(normalized, normalizations)
    normalized["preview_summary"] = strength_preview_summary(
        normalized.get("summary") if isinstance(normalized.get("summary"), dict) else {},
        normalized.get("viewport_render_plan") if isinstance(normalized.get("viewport_render_plan"), dict) else {},
    )
    normalized["integration_readiness_summary"] = integration_readiness_summary(
        normalized.get("summary") if isinstance(normalized.get("summary"), dict) else {},
        normalized.get("viewport_render_plan") if isinstance(normalized.get("viewport_render_plan"), dict) else {},
    )
    normalized["orcaslicer_codex_advisory_source"] = source
    normalized["orcaslicer_codex_advisory_normalizations"] = normalizations
    return normalized


def normalize_mixed_context_lane_identity(mixed_context: dict[str, Any], normalizations: list[str]) -> dict[str, Any]:
    normalized = dict(mixed_context)
    raw_lanes = normalized.get("lanes") if isinstance(normalized.get("lanes"), list) else []
    lanes: list[dict[str, Any]] = []
    lanes_by_index: dict[int, dict[str, Any]] = {}
    for fallback_index, item in enumerate(raw_lanes):
        original_item: Any = item
        if not isinstance(item, dict):
            item = {"details": {"original_lane_value": original_item}}
            normalizations.append(f"mixed_filament_context.lane_{fallback_index}.normalized_from_non_object")
        lane = dict(item)
        if "lane_index" not in lane or lane.get("lane_index") in {None, ""}:
            lane["lane_index"] = fallback_index
            normalizations.append(f"mixed_filament_context.lane_{fallback_index}.lane_index_defaulted")
        lane_index = int(number(lane.get("lane_index"), float(fallback_index)))
        if "tool_index" not in lane or lane.get("tool_index") in {None, ""}:
            lane["tool_index"] = int(number(lane.get("toolhead_index"), float(lane_index)))
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.tool_index_defaulted")
        tool_index = int(number(lane.get("tool_index"), float(lane_index)))
        if "lane_id" not in lane or not lane.get("lane_id"):
            lane["lane_id"] = f"L{lane_index}"
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.lane_id_defaulted")
        if "toolhead_index" not in lane or lane.get("toolhead_index") in {None, ""}:
            lane["toolhead_index"] = tool_index
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.toolhead_index_defaulted")
        toolhead_index = int(number(lane.get("toolhead_index"), float(tool_index)))
        if "extruder_id" not in lane or not lane.get("extruder_id"):
            lane["extruder_id"] = f"T{toolhead_index}"
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.extruder_id_defaulted")
        if "role" not in lane or not lane.get("role"):
            lane["role"] = "unknown"
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.role_defaulted")
        if "lane_kind" not in lane or not lane.get("lane_kind"):
            lane["lane_kind"] = "unknown"
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.lane_kind_defaulted")
        for field in ("material_type", "filament_settings_id", "filament_vendor", "display_color"):
            if field not in lane or lane.get(field) is None:
                lane[field] = ""
                normalizations.append(f"mixed_filament_context.lane_{lane_index}.{field}_defaulted")
        nozzle_value = lane.get("nozzle_diameter")
        if "nozzle_diameter" not in lane or nozzle_value is None or nozzle_value == "":
            lane["nozzle_diameter"] = 0.0
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.nozzle_diameter_defaulted")
        else:
            lane["nozzle_diameter"] = number(lane.get("nozzle_diameter"), 0.0)
        if "display_label" not in lane or not lane.get("display_label"):
            lane["display_label"] = mixed_lane_display_label(lane)
            normalizations.append(f"mixed_filament_context.lane_{lane_index}.display_label_defaulted")
        lane_family = material_family_lane_metadata(
            lane,
            lane.get("material_family_source_material_text"),
            lane.get("filament_settings_id"),
            lane.get("material_type"),
            lane.get("display_label"),
            lane.get("role"),
            lane.get("lane_kind"),
        )
        for field, value in lane_family.items():
            if field not in lane or lane.get(field) is None or lane.get(field) == "":
                lane[field] = value
                normalizations.append(f"mixed_filament_context.lane_{lane_index}.{field}_defaulted")
            elif field == "material_family_is_filled":
                lane[field] = boolish(lane.get(field))
        lanes_by_index[lane_index] = lane
        lanes.append(lane)
    normalized["lanes"] = lanes

    raw_palette = normalized.get("material_palette") if isinstance(normalized.get("material_palette"), list) else []
    palette: list[dict[str, Any]] = []
    for fallback_index, item in enumerate(raw_palette):
        original_item: Any = item
        if not isinstance(item, dict):
            item = {"details": {"original_palette_value": original_item}}
            normalizations.append(f"mixed_filament_context.palette_{fallback_index}.normalized_from_non_object")
        entry = dict(item)
        if "lane_index" not in entry or entry.get("lane_index") is None or entry.get("lane_index") == "":
            entry["lane_index"] = fallback_index
            normalizations.append(f"mixed_filament_context.palette_{fallback_index}.lane_index_defaulted")
        lane_index = int(number(entry.get("lane_index"), float(fallback_index)))
        source_lane = lanes_by_index.get(lane_index, {})
        if "id" not in entry or not entry.get("id"):
            entry["id"] = f"lane_{lane_index}"
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.id_defaulted")
        if "label" not in entry or not entry.get("label"):
            entry["label"] = text(source_lane.get("filament_settings_id") or source_lane.get("material_type"), "Unknown material")
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.label_defaulted")
        if "color" not in entry or not entry.get("color"):
            entry["color"] = text(source_lane.get("display_color"), COLORS["orientation"])
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.color_defaulted")
        if "lane_id" not in entry or not entry.get("lane_id"):
            entry["lane_id"] = text(source_lane.get("lane_id"), f"L{lane_index}")
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.lane_id_defaulted")
        if "tool_index" not in entry or entry.get("tool_index") in {None, ""}:
            entry["tool_index"] = int(number(source_lane.get("tool_index"), float(lane_index)))
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.tool_index_defaulted")
        if "toolhead_index" not in entry or entry.get("toolhead_index") in {None, ""}:
            entry["toolhead_index"] = int(number(source_lane.get("toolhead_index"), number(entry.get("tool_index"), float(lane_index))))
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.toolhead_index_defaulted")
        if "extruder_id" not in entry or not entry.get("extruder_id"):
            entry["extruder_id"] = text(source_lane.get("extruder_id"), f"T{int(number(entry.get('toolhead_index'), float(lane_index)))}")
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.extruder_id_defaulted")
        if "material_type" not in entry or entry.get("material_type") is None:
            entry["material_type"] = text(source_lane.get("material_type"))
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.material_type_defaulted")
        if "filament_settings_id" not in entry or entry.get("filament_settings_id") is None:
            entry["filament_settings_id"] = text(source_lane.get("filament_settings_id"))
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.filament_settings_id_defaulted")
        if "display_label" not in entry or not entry.get("display_label"):
            entry["display_label"] = text(source_lane.get("display_label"), mixed_palette_display_label(entry, source_lane))
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.display_label_defaulted")
        palette_nozzle_value = entry.get("nozzle_diameter")
        if "nozzle_diameter" not in entry or palette_nozzle_value is None or palette_nozzle_value == "":
            entry["nozzle_diameter"] = number(source_lane.get("nozzle_diameter"), 0.0)
            normalizations.append(f"mixed_filament_context.palette_{lane_index}.nozzle_diameter_defaulted")
        else:
            entry["nozzle_diameter"] = number(entry.get("nozzle_diameter"), 0.0)
        palette_family = material_family_lane_metadata(
            entry,
            source_lane,
            entry.get("label"),
            entry.get("filament_settings_id"),
            entry.get("material_type"),
            source_lane.get("display_label"),
        )
        for field in (
            "material_family_key",
            "material_family_label",
            "material_family_base_polymer",
            "material_family_reinforcement_type",
            "material_family_is_filled",
        ):
            if field not in entry or entry.get(field) is None or entry.get(field) == "":
                entry[field] = palette_family[field]
                normalizations.append(f"mixed_filament_context.palette_{lane_index}.{field}_defaulted")
            elif field == "material_family_is_filled":
                entry[field] = boolish(entry.get(field))
        palette.append(entry)
    normalized["material_palette"] = palette
    lane_badges = mixed_lane_badges(lanes, palette)
    if normalized.get("lane_badges") != lane_badges:
        normalized["lane_badges"] = lane_badges
        normalizations.append("mixed_filament_context.lane_badges_defaulted_from_lanes")
    if normalized.get("lane_badge_count") != len(lane_badges):
        normalized["lane_badge_count"] = len(lane_badges)
        normalizations.append("mixed_filament_context.lane_badge_count_defaulted_from_lane_badges")
    filled_badges = filled_material_lane_badges(lane_badges)
    if normalized.get("filled_material_lane_badges") != filled_badges:
        normalized["filled_material_lane_badges"] = filled_badges
        normalizations.append("mixed_filament_context.filled_material_lane_badges_defaulted_from_lane_badges")
    if normalized.get("filled_material_lane_badge_count") != len(filled_badges):
        normalized["filled_material_lane_badge_count"] = len(filled_badges)
        normalizations.append("mixed_filament_context.filled_material_lane_badge_count_defaulted_from_lane_badges")
    if normalized.get("lane_count") != len(lanes):
        normalized["lane_count"] = len(lanes)
        normalizations.append("mixed_filament_context.lane_count_defaulted_from_lanes")
    if "selected_material_count" not in normalized or normalized.get("selected_material_count") is None or normalized.get("selected_material_count") == "":
        normalized["selected_material_count"] = len({entry.get("label") for entry in palette if entry.get("label")})
        normalizations.append("mixed_filament_context.selected_material_count_defaulted_from_palette")
    if "color_count" not in normalized or normalized.get("color_count") is None or normalized.get("color_count") == "":
        normalized["color_count"] = len({entry.get("color") for entry in palette if entry.get("color")})
        normalizations.append("mixed_filament_context.color_count_defaulted_from_palette")
    if "selected_nozzle_count" not in normalized or normalized.get("selected_nozzle_count") is None or normalized.get("selected_nozzle_count") == "":
        normalized["selected_nozzle_count"] = len({lane.get("nozzle_diameter") for lane in lanes if lane.get("nozzle_diameter")})
        normalizations.append("mixed_filament_context.selected_nozzle_count_defaulted_from_lanes")
    if "filled_material_lane_count" not in normalized or normalized.get("filled_material_lane_count") is None or normalized.get("filled_material_lane_count") == "":
        normalized["filled_material_lane_count"] = material_family_filled_lane_count(lanes)
        normalizations.append("mixed_filament_context.filled_material_lane_count_defaulted_from_lanes")
    else:
        normalized["filled_material_lane_count"] = int(number(normalized.get("filled_material_lane_count"), 0.0))
    return normalized


def mixed_lane_material_label(lane: dict[str, Any]) -> str:
    fiber_material = nested(lane.get("fiber_material"))
    for value in (
        lane.get("filament_settings_id"),
        lane.get("material_type"),
        fiber_material.get("name"),
        lane.get("role"),
    ):
        if value:
            return str(value)
    return "Unknown material"


def mixed_lane_display_label(lane: dict[str, Any]) -> str:
    lane_index = int(number(lane.get("lane_index"), 0.0))
    toolhead_index = int(number(lane.get("toolhead_index"), number(lane.get("tool_index"), float(lane_index))))
    extruder_id = text(lane.get("extruder_id"), f"T{toolhead_index}")
    lane_id = text(lane.get("lane_id"), f"L{lane_index}")
    return f"{extruder_id} / {lane_id} - {mixed_lane_material_label(lane)}"


def mixed_palette_display_label(entry: dict[str, Any], source_lane: dict[str, Any]) -> str:
    if source_lane.get("display_label"):
        return text(source_lane.get("display_label"))
    lane_index = int(number(entry.get("lane_index"), number(source_lane.get("lane_index"), 0.0)))
    toolhead_index = int(number(entry.get("toolhead_index"), number(source_lane.get("toolhead_index"), number(entry.get("tool_index"), float(lane_index)))))
    extruder_id = text(entry.get("extruder_id"), text(source_lane.get("extruder_id"), f"T{toolhead_index}"))
    lane_id = text(entry.get("lane_id"), text(source_lane.get("lane_id"), f"L{lane_index}"))
    label = text(entry.get("label"), mixed_lane_material_label(source_lane))
    return f"{extruder_id} / {lane_id} - {label}"


def mixed_lane_badges(lanes: list[dict[str, Any]], material_palette: list[dict[str, Any]]) -> list[dict[str, Any]]:
    palette_by_lane_id = {
        text(item.get("lane_id")): item
        for item in material_palette
        if isinstance(item, dict) and text(item.get("lane_id"))
    }
    badges: list[dict[str, Any]] = []
    for lane in lanes:
        lane_index = int(number(lane.get("lane_index"), 0.0))
        palette_entry = palette_by_lane_id.get(text(lane.get("lane_id"))) or {}
        family = material_family_lane_metadata(
            palette_entry,
            lane,
            palette_entry.get("label"),
            lane.get("display_label"),
            lane.get("filament_settings_id"),
            lane.get("material_type"),
        )
        badges.append(
            {
                "lane_index": lane_index,
                "lane_id": text(lane.get("lane_id"), f"L{lane_index}"),
                "toolhead_index": int(number(lane.get("toolhead_index"), number(lane.get("tool_index"), float(lane_index)))),
                "extruder_id": text(lane.get("extruder_id"), f"T{lane_index}"),
                "label": text(lane.get("display_label"), mixed_lane_display_label(lane)),
                "material_label": text(palette_entry.get("label"), mixed_lane_material_label(lane)),
                "color": text(palette_entry.get("color"), lane.get("display_color") or COLORS["orientation"]),
                "nozzle_diameter": number(palette_entry.get("nozzle_diameter"), lane.get("nozzle_diameter", 0.0)),
                "lane_kind": text(lane.get("lane_kind"), "unknown"),
                "role": text(lane.get("role"), "unknown"),
                "material_family_key": family["material_family_key"],
                "material_family_label": family["material_family_label"],
                "material_family_base_polymer": family["material_family_base_polymer"],
                "material_family_reinforcement_type": family["material_family_reinforcement_type"],
                "material_family_is_filled": family["material_family_is_filled"],
                "enabled": True,
            }
        )
    return badges


def filled_material_lane_badges(badges: Any) -> list[dict[str, Any]]:
    return [
        badge
        for badge in list_value(badges)
        if isinstance(badge, dict) and boolish(badge.get("material_family_is_filled", False))
    ]


def normalize_external_visualization(
    output_path: Path,
    source: str,
    artifacts: dict[str, Any],
    slice_result: dict[str, Any],
    fiber_overlay: dict[str, Any],
    active_lens: str,
    selected_load_case: str,
) -> str | None:
    visualization = read_json(output_path)
    if not visualization:
        return "external builder output was not valid JSON"
    normalized = enforce_advisory_contract(visualization, source, slice_result, fiber_overlay, active_lens, selected_load_case)
    normalized["input_artifacts"] = artifacts
    output_path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return None


def strength_preview_summary(summary: dict[str, Any], viewport: dict[str, Any]) -> dict[str, Any]:
    """Small stable payload for Orca Preview/Summary labels."""
    lane_message = text(summary.get("lane_readiness_review_message"))
    status_message = text(viewport.get("load_case_message"), text(summary.get("load_case_message")))
    if lane_message and boolish(summary.get("lane_readiness_review_needed", False)):
        status_message = lane_message
    cards = strength_preview_status_cards(summary, viewport, status_message)
    return {
        "schema_version": "1.0.0",
        "component": "strength_lens",
        "label": "Strength Lens",
        "status": text(viewport.get("status"), "ready"),
        "active_lens": text(viewport.get("active_lens"), "orientation_risk"),
        "status_message": status_message,
        "overlay_count": int(number(summary.get("overlay_count"), number(viewport.get("overlay_count"), 0.0))),
        "warning_count": int(number(summary.get("warning_count"), number(viewport.get("warning_overlay_count"), 0.0))),
        "material_family": text(summary.get("material_family")),
        "orientation_confidence_level": text(summary.get("orientation_confidence_level"), "setup_required"),
        "lane_readiness_level": text(summary.get("lane_readiness_level")),
        "arc_support_preview_status": text(summary.get("arc_support_preview_status"), "unavailable"),
        "preview_status_cards": cards,
        "preview_status_card_count": len(cards),
        "advisory_only": True,
        "slicing_or_gcode_modified": False,
        "machine_ready_structural_approval": False,
        "safety_note": "Advisory preview metadata only; does not alter slicing, G-code, printer state, or print approval.",
    }


def strength_preview_status_cards(
    summary: dict[str, Any],
    viewport: dict[str, Any],
    status_message: str,
) -> list[dict[str, Any]]:
    """Ready-to-render Preview/Summary rows for Support, Strength, FibreSeek, and safety."""
    lane_review_needed = boolish(summary.get("lane_readiness_review_needed", viewport.get("lane_readiness_review_needed", False)))
    lane_message = text(summary.get("lane_readiness_review_message"), text(viewport.get("lane_readiness_review_message")))
    arc_selected = boolish(summary.get("arc_support_selected", viewport.get("arc_support_selected", False)))
    arc_status = text(summary.get("arc_support_preview_status"), text(viewport.get("arc_support_preview_status"), "unavailable"))
    arc_label = text(summary.get("arc_support_preview_label"), text(viewport.get("arc_support_preview_label"), "Arc Overhang"))
    return [
        {
            "id": "support",
            "label": arc_label,
            "status": arc_status,
            "severity": "info" if arc_selected else "neutral",
            "message": text(viewport.get("arc_support_preview_status_message"), "Arc Overhang is not selected for this slice."),
            "source": "arc_support_context",
        },
        {
            "id": "strength",
            "label": "Strength Lens",
            "status": text(summary.get("strength_map_status"), text(viewport.get("strength_map_status"), "ready")),
            "severity": "warning" if int(number(summary.get("warning_count"), 0.0)) > 0 else "info",
            "message": status_message,
            "source": "strength_lens.summary",
        },
        {
            "id": "fibreseeker_lanes",
            "label": "FibreSeek lanes",
            "status": text(summary.get("lane_readiness_level"), text(viewport.get("lane_readiness_level"), "unavailable")),
            "severity": "warning" if lane_review_needed else "info",
            "message": lane_message or "Lane metadata is available for Preview/Summary.",
            "source": "mixed_filament_context.lane_readiness_summary",
        },
        {
            "id": "safety",
            "label": "Safety boundary",
            "status": "advisory_only",
            "severity": "info",
            "message": "Preview metadata only; no G-code mutation, upload/start-print, or hardware-ready approval.",
            "source": "orcaslicer_codex_guardrails",
        },
    ]


def integration_readiness_summary(summary: dict[str, Any], viewport: dict[str, Any]) -> dict[str, Any]:
    """One shallow UI handoff for Support, Strength Lens, and FibreSeeker status."""
    arc_selected = bool(summary.get("arc_support_selected", viewport.get("arc_support_selected", False)))
    arc_status = text(summary.get("arc_support_preview_status"), text(viewport.get("arc_support_preview_status"), "unavailable"))
    strength_status = text(summary.get("strength_map_status"), text(viewport.get("strength_map_status"), "unavailable"))
    lane_level = text(summary.get("lane_readiness_level"), text(viewport.get("lane_readiness_level")))
    lane_review_needed = bool(summary.get("lane_readiness_review_needed", viewport.get("lane_readiness_review_needed", False)))
    lane_review_issues = int(number(summary.get("lane_readiness_review_issue_count"), number(viewport.get("lane_readiness_review_issue_count"), 0.0)))
    blocked_gates = int(number(summary.get("validation_blocked_gate_count"), number(viewport.get("validation_blocked_gate_count"), 0.0)))
    return {
        "schema_version": "1.0.0",
        "component": "support_strength_fibreseeker_readiness",
        "label": "Support + Strength + FibreSeeker",
        "support_status": "arc_ready" if arc_selected and arc_status == "ready" else "standard_or_unavailable",
        "arc_support_selected": arc_selected,
        "arc_support_preview_status": arc_status,
        "arc_support_guarded_transform_required": bool(summary.get("arc_support_guarded_transform_required", viewport.get("arc_support_guarded_transform_required", False))),
        "strength_status": strength_status,
        "orientation_confidence_level": text(summary.get("orientation_confidence_level"), text(viewport.get("orientation_confidence_level"), "setup_required")),
        "material_family": text(summary.get("material_family"), text(viewport.get("material_family_key"))),
        "fibreseeker_status": "needs_lane_review" if lane_review_needed else text(summary.get("lane_readiness_status"), text(viewport.get("lane_readiness_status"), "unavailable")),
        "lane_readiness_level": lane_level,
        "lane_readiness_review_needed": lane_review_needed,
        "lane_readiness_review_issue_count": lane_review_issues,
        "validation_blocked_gate_count": blocked_gates,
        "mixed_filament_lane_count": int(number(summary.get("mixed_filament_lane_count"), number(viewport.get("mixed_filament_lane_count"), 0.0))),
        "continuous_fiber_lane_count": int(number(summary.get("continuous_fiber_lane_count"), number(viewport.get("continuous_fiber_lane_count"), 0.0))),
        "advisory_only": True,
        "slicing_or_gcode_modified": False,
        "command_emission_allowed": False,
        "upload_or_start_print_allowed": False,
        "hardware_ready": False,
        "machine_ready_structural_approval": False,
        "safety_note": "Readiness metadata only; it does not alter supports, strength analysis, G-code, printer state, or hardware validation.",
    }


def material_id(slice_result: dict[str, Any]) -> str:
    material_strength = nested(slice_result.get("material_strength"))
    estimate = nested(nested(material_strength.get("primary_estimate")).get("material"))
    for candidate in [
        material_strength.get("primary_material_id"),
        estimate.get("material_id"),
        slice_result.get("filament_type"),
        slice_result.get("filament"),
        slice_result.get("material"),
    ]:
        flattened = flatten_strings(candidate)
        if flattened:
            return flattened[0].lower().replace(" ", "_")
    return "unknown"


def material_label(slice_result: dict[str, Any]) -> str:
    material_strength = nested(slice_result.get("material_strength"))
    estimate = nested(nested(material_strength.get("primary_estimate")).get("material"))
    for candidate in [
        estimate.get("display_name"),
        material_strength.get("primary_material_label"),
        slice_result.get("filament_type"),
        slice_result.get("material"),
    ]:
        flattened = flatten_strings(candidate)
        if flattened:
            return flattened[0]
    return "Unknown material"


def append_profile_key_values(result: list[str], source: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        for item in flatten_strings(source.get(key)):
            result.extend(split_material_family_source_values(item))


def material_family_source_texts(slice_result: dict[str, Any], fiber_overlay: dict[str, Any] | None = None) -> list[str]:
    material_strength = nested(slice_result.get("material_strength"))
    estimate = nested(nested(material_strength.get("primary_estimate")).get("material"))
    settings = nested(slice_result.get("settings")) or nested(slice_result.get("config"))
    lane_contract = nested((fiber_overlay or {}).get("lane_contract"))
    candidates = [
        material_strength.get("primary_material_id"),
        material_strength.get("primary_material_label"),
        estimate.get("material_id"),
        estimate.get("display_name"),
        slice_result.get("filament_type"),
        slice_result.get("filament_settings_id"),
        slice_result.get("filament"),
        slice_result.get("material"),
        settings.get("filament_type"),
        settings.get("filament_settings_id"),
        settings.get("filament"),
        settings.get("material"),
    ]
    result: list[str] = []
    for candidate in candidates:
        for item in flatten_strings(candidate):
            result.extend(split_material_family_source_values(item))
    append_profile_key_values(result, slice_result, MATERIAL_FAMILY_PROFILE_KEYS)
    append_profile_key_values(result, settings, MATERIAL_FAMILY_PROFILE_KEYS)
    lanes = list_value(lane_contract.get("lanes"))
    for lane in lanes:
        if not isinstance(lane, dict):
            continue
        lane_kind = text(lane.get("lane_kind"), text(lane.get("role"))).lower()
        if "fiber" in lane_kind and "composite" not in lane_kind:
            continue
        for field in ("filament_settings_id", "material_type", "filament_vendor"):
            value = text(lane.get(field))
            if value:
                result.append(value)
    return result


def normalize_material_family_text(value: str) -> str:
    return value.lower().replace("_", " ").replace("-", " ").strip()


def material_family_alias_candidates() -> list[tuple[str, str, dict[str, Any]]]:
    candidates: list[tuple[str, str, dict[str, Any]]] = []
    for family_key, estimate in MATERIAL_FAMILY_AXIS_ESTIMATES.items():
        for alias in estimate.get("aliases", []):
            normalized = normalize_material_family_text(text(alias))
            if normalized:
                candidates.append((normalized, family_key, estimate))
    return sorted(candidates, key=lambda item: len(item[0]), reverse=True)


def material_family_base_polymer(family_key: str) -> str:
    return text(family_key).split("_", 1)[0]


def material_family_reinforcement_type(family_key: str) -> str:
    normalized = text(family_key)
    if normalized.endswith("_cf"):
        return "carbon_fiber"
    if normalized.endswith("_gf"):
        return "glass_fiber"
    return "none"


def material_family_fill_metadata(family_key: str) -> dict[str, Any]:
    reinforcement = material_family_reinforcement_type(family_key)
    return {
        "base_polymer": material_family_base_polymer(family_key),
        "reinforcement_type": reinforcement,
        "is_filled_family": reinforcement != "none",
    }


def boolish(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in {None, ""}:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "filled", "filled_family"}
    return bool(value)


def material_family_source_candidates(*source_values: Any) -> list[str]:
    result: list[str] = []
    for source_value in source_values:
        for item in flatten_strings(source_value):
            result.extend(split_material_family_source_values(item))
    return [item for item in result if item]


def material_family_filled_lane_count(lanes: Any) -> int:
    return sum(
        1
        for lane in list_value(lanes)
        if isinstance(lane, dict) and boolish(lane.get("material_family_is_filled", False))
    )


def material_family_lane_metadata(existing: Any = None, *source_values: Any) -> dict[str, Any]:
    source = nested(existing)
    existing_key = text(source.get("material_family_key") or source.get("family_key"))
    existing_label = text(source.get("material_family_label") or source.get("display_name"))
    existing_source_text = text(source.get("material_family_source_material_text") or source.get("source_material_text"))
    existing_alias = text(source.get("material_family_matched_alias") or source.get("matched_alias"))
    candidates = material_family_source_candidates(existing_source_text, *source_values)

    if existing_key in MATERIAL_FAMILY_AXIS_ESTIMATES:
        estimate = MATERIAL_FAMILY_AXIS_ESTIMATES[existing_key]
        fill = material_family_fill_metadata(existing_key)
        return {
            "material_family_key": existing_key,
            "material_family_label": text(existing_label, estimate["display_name"]),
            "material_family_source_material_text": text(existing_source_text, candidates[0] if candidates else ""),
            "material_family_matched_alias": text(existing_alias, existing_key.replace("_", " ")),
            "material_family_base_polymer": text(source.get("material_family_base_polymer") or source.get("base_polymer"), fill["base_polymer"]),
            "material_family_reinforcement_type": text(
                source.get("material_family_reinforcement_type") or source.get("reinforcement_type"),
                fill["reinforcement_type"],
            ),
            "material_family_is_filled": boolish(
                source.get("material_family_is_filled", source.get("is_filled_family", fill["is_filled_family"])),
                fill["is_filled_family"],
            ),
        }

    family_aliases = material_family_alias_candidates()
    for source_text in candidates:
        normalized_source = normalize_material_family_text(source_text)
        for alias, family_key, estimate in family_aliases:
            if alias in normalized_source:
                fill = material_family_fill_metadata(family_key)
                return {
                    "material_family_key": family_key,
                    "material_family_label": text(existing_label, estimate["display_name"]),
                    "material_family_source_material_text": text(existing_source_text, source_text),
                    "material_family_matched_alias": text(existing_alias, alias),
                    "material_family_base_polymer": fill["base_polymer"],
                    "material_family_reinforcement_type": fill["reinforcement_type"],
                    "material_family_is_filled": fill["is_filled_family"],
                }

    return {
        "material_family_key": existing_key,
        "material_family_label": existing_label,
        "material_family_source_material_text": existing_source_text,
        "material_family_matched_alias": existing_alias,
        "material_family_base_polymer": text(source.get("material_family_base_polymer") or source.get("base_polymer")),
        "material_family_reinforcement_type": text(
            source.get("material_family_reinforcement_type") or source.get("reinforcement_type"),
            "none",
        ),
        "material_family_is_filled": boolish(source.get("material_family_is_filled", source.get("is_filled_family", False))),
    }


def infer_material_family_axis_estimate(
    slice_result: dict[str, Any],
    fiber_overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source_texts = material_family_source_texts(slice_result, fiber_overlay)
    family_aliases = material_family_alias_candidates()
    for source_text in source_texts:
        source = normalize_material_family_text(source_text)
        for alias, family_key, estimate in family_aliases:
            if alias in source:
                return {
                    "schema_version": "1.0.0",
                    "status": "ready",
                    "family_key": family_key,
                    "display_name": estimate["display_name"],
                    "source_material_text": source_text,
                    "matched_alias": alias,
                    **material_family_fill_metadata(family_key),
                    "print_axis_tensile_strength_mpa": estimate["print_axis_tensile_strength_mpa"],
                    "basis": "material_family_proxy_estimate",
                    "source": "orcaslicer_codex.material_family_axis_estimate",
                    "warning": (
                        "Filament-family values are planning estimates for vibrant orientation preview only; "
                        "they are not measured spool data, certified FEA, or print approval."
                    ),
                    "advisory_only": True,
                }
    return {
        "schema_version": "1.0.0",
        "status": "unavailable",
        "reason": "unknown_filament_family",
        "source_material_text": source_texts[0] if source_texts else "",
        "known_families": sorted(MATERIAL_FAMILY_AXIS_ESTIMATES),
        "advisory_only": True,
    }


def band_for_ratio(ratio: float) -> dict[str, Any]:
    clamped = max(0.0, min(ratio, 1.0))
    if clamped < 0.5:
        return {"id": "critical", "label": "critical weak axis", "color": COLORS["critical"], "severity": "warning"}
    if clamped < 0.7:
        return {"id": "review", "label": "review weak axis", "color": COLORS["review"], "severity": "warning"}
    if clamped < 0.9:
        return {"id": "usable", "label": "usable orientation", "color": COLORS["orientation"], "severity": "info"}
    return {"id": "strong", "label": "strong orientation", "color": COLORS["strong"], "severity": "info"}


def strength_map(slice_result: dict[str, Any], fiber_overlay: dict[str, Any] | None = None) -> dict[str, Any]:
    orientation = nested(nested(slice_result.get("material_strength")).get("orientation_comparison"))
    print_axis = nested(orientation.get("print_axis_tensile_strength_mpa"))
    axis_values = {axis: number(print_axis.get(axis)) for axis in ("x", "y", "z") if axis in print_axis}
    material_family_estimate: dict[str, Any] = {}
    source = "material_strength.orientation_comparison.print_axis_tensile_strength_mpa"
    basis = "measured_or_profile_axis_strength"
    estimated = False
    if not axis_values:
        material_family_estimate = infer_material_family_axis_estimate(slice_result, fiber_overlay)
        axis_values = {
            axis: number(value)
            for axis, value in nested(material_family_estimate.get("print_axis_tensile_strength_mpa")).items()
            if axis in {"x", "y", "z"}
        }
        source = text(material_family_estimate.get("source"), "orcaslicer_codex.material_family_axis_estimate")
        basis = text(material_family_estimate.get("basis"), "material_family_proxy_estimate")
        estimated = True
        if not axis_values:
            return {
                "schema_version": "1.0.0",
                "status": "unavailable",
                "reason": "missing_print_axis_tensile_strength_mpa",
                "render_policy": "predictive_non_destructive_overlay",
                "material_family_estimate": material_family_estimate,
                "advisory_only": True,
            }

    reference = max(axis_values.values())
    axis_bands: list[dict[str, Any]] = []
    for axis in ("x", "y", "z"):
        strength = axis_values.get(axis, 0.0)
        ratio = strength / reference if reference > 0 else 0.0
        band = band_for_ratio(ratio)
        axis_bands.append(
            {
                **band,
                "axis": axis,
                "label": f"Print {axis.upper()} axis",
                "strength_mpa": round(strength, 4),
                "relative_strength_ratio": round(ratio, 4),
                "relative_strength_percent": round(ratio * 100.0, 1),
            }
        )

    return {
        "schema_version": "1.0.0",
        "status": "ready",
        "metric": "relative_tensile_strength_by_print_axis",
        "basis": basis,
        "source": source,
        "estimated": estimated,
        "render_policy": "predictive_non_destructive_overlay",
        "color_mode": "vibrant_strength_band",
        "reference_strength_mpa": round(reference, 4),
        "print_axis_bands": axis_bands,
        "material_family_estimate": material_family_estimate,
        "advisory_only": True,
    }


def orientation_confidence(strength_payload: dict[str, Any]) -> dict[str, Any]:
    if strength_payload.get("status") != "ready":
        return {
            "schema_version": "1.0.0",
            "status": "needs_material_axis_data",
            "confidence_level": "setup_required",
            "reason": strength_payload.get("reason", "missing_strength_map"),
            "advisory_only": True,
        }

    bands = [
        item
        for item in strength_payload.get("print_axis_bands", [])
        if isinstance(item, dict) and isinstance(item.get("strength_mpa"), (int, float))
    ]
    if not bands:
        return {
            "schema_version": "1.0.0",
            "status": "needs_material_axis_data",
            "confidence_level": "setup_required",
            "reason": "missing_axis_bands",
            "advisory_only": True,
        }

    strongest = max(bands, key=lambda item: float(item.get("strength_mpa", 0.0)))
    weakest = min(bands, key=lambda item: float(item.get("strength_mpa", 0.0)))
    reference = float(strength_payload.get("reference_strength_mpa", strongest.get("strength_mpa", 0.0)) or 0.0)
    weakest_strength = float(weakest.get("strength_mpa", 0.0) or 0.0)
    anisotropy_ratio = weakest_strength / reference if reference > 0 else 0.0
    warning_axes = [
        {
            "axis": item.get("axis", ""),
            "band": item.get("id", ""),
            "relative_strength_percent": item.get("relative_strength_percent", 0.0),
        }
        for item in bands
        if item.get("severity") == "warning"
    ]
    return {
        "schema_version": "1.0.0",
        "status": "ready",
        "confidence_level": "material_family_estimate" if strength_payload.get("estimated") else "material_axis_data",
        "basis": strength_payload.get("basis", "relative_tensile_strength_by_print_axis"),
        "strongest_print_axis": strongest.get("axis", ""),
        "weakest_print_axis": weakest.get("axis", ""),
        "strongest_strength_mpa": strongest.get("strength_mpa", 0.0),
        "weakest_strength_mpa": weakest.get("strength_mpa", 0.0),
        "weakest_to_strongest_ratio": round(anisotropy_ratio, 4),
        "weakest_axis_drop_percent": round((1.0 - anisotropy_ratio) * 100.0, 1),
        "warning_axes": warning_axes,
        "estimated": bool(strength_payload.get("estimated")),
        "material_family_estimate": strength_payload.get("material_family_estimate", {}),
        "advisory_only": True,
    }


def overlay(
    overlay_id: str,
    lens: str,
    kind: str,
    severity: str,
    color: str,
    message: str,
    source: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": overlay_id,
        "lens": lens,
        "kind": kind,
        "severity": severity,
        "color": color,
        "confidence": "heuristic",
        "source": source,
        "message": message,
        "details": details or {},
    }


def detect_support(slice_result: dict[str, Any]) -> str:
    for key in ("support_type", "support", "tinman_support_strategy"):
        flattened = flatten_strings(slice_result.get(key))
        if flattened:
            return " ".join(flattened)
    settings = nested(slice_result.get("settings")) or nested(slice_result.get("config"))
    for key in ("support_type", "support", "tinman_support_strategy"):
        flattened = flatten_strings(settings.get(key))
        if flattened:
            return " ".join(flattened)
    return ""


def arc_support_context(slice_result: dict[str, Any]) -> dict[str, Any]:
    support_type = detect_support(slice_result).lower()
    arc_selected = "arc" in support_type
    preview_label = "Arc Overhang (guarded preview)" if arc_selected else "Arc Overhang not selected"
    preview_status_message = (
        "Arc Overhang selected: bridge/overhang infill feeds the guarded adapter and ordinary support extrusion is rejected from the final export."
        if arc_selected
        else "Arc Overhang is not selected for this slice."
    )
    postprocess_stage = "replace_bridge_infill_with_arc_overhangs" if arc_selected else ""
    guardrail_summary = (
        "Adapter must write a separate output, prove Arc infill extrusion exists, reject ordinary support extrusion, and replace Orca G-code only after a successful guarded transform."
        if arc_selected
        else "No Arc Overhang transform is scheduled."
    )
    preview_cues = [
        "normal_support_rejected",
        "guarded_arc_transform_expected",
        "same_path_mutation_forbidden",
        "adapter_replaces_input_only_on_success",
    ] if arc_selected else []
    preview_cue_chips = arc_support_preview_cue_chips(preview_cues)
    return {
        "schema_version": "1.0.0",
        "status": "ready" if arc_selected else "unavailable",
        "arc_support_selected": arc_selected,
        "support_type": support_type,
        "preview_label": preview_label,
        "preview_status_message": preview_status_message,
        "postprocess_stage": postprocess_stage,
        "guardrail_summary": guardrail_summary,
        "experimental": arc_selected,
        "base_support_path": "bridge_overhang_generation" if arc_selected else "",
        "postprocess_adapter": "orcaslicer_codex_arc_support_inplace_adapter.py" if arc_selected else "",
        "guarded_transform_required": arc_selected,
        "same_path_mutation_forbidden": arc_selected,
        "adapter_replaces_input_only_on_success": arc_selected,
        "strength_lens_mutates_gcode": False,
        "slicing_or_gcode_modified": arc_selected,
        "preview_cues": preview_cues,
        "preview_cue_count": len(preview_cues),
        "preview_cue_chips": preview_cue_chips,
        "preview_cue_chip_count": len(preview_cue_chips),
        "advisory_only": True,
    }


def detect_fiber(slice_result: dict[str, Any], fiber_overlay: dict[str, Any]) -> bool:
    if fiber_overlay:
        return True
    haystack = " ".join(flatten_strings(slice_result)).lower()
    return any(token in haystack for token in ("fiber_enabled", "fiber_route", "fiberseek", "fibreseek", "continuous_fiber"))


def mixed_filament_context(fiber_overlay: dict[str, Any], slice_result: dict[str, Any]) -> dict[str, Any]:
    lane_contract = nested(fiber_overlay.get("lane_contract")) or nested(slice_result.get("lane_contract"))
    mixed_contract = nested(fiber_overlay.get("mixed_filament_contract")) or nested(slice_result.get("mixed_filament_contract"))
    readiness = nested(fiber_overlay.get("lane_readiness_summary")) or nested(slice_result.get("lane_readiness_summary"))
    lanes = list_value(lane_contract.get("lanes"))
    if not lanes:
        return {
            "status": "unavailable",
            "reason": "missing_lane_contract",
            "source": "orcaslicer_codex.fiber_metadata_sidecar",
            "lanes": [],
            "material_palette": [],
            "lane_badges": [],
            "filled_material_lane_badges": [],
            "filled_material_lane_badge_count": 0,
            "filled_material_lane_count": 0,
        }

    normalized_lanes: list[dict[str, Any]] = []
    material_palette: list[dict[str, Any]] = []
    raw_palette = [
        item for item in list_value(mixed_contract.get("material_palette"))
        if isinstance(item, dict)
    ]
    palette_by_lane_id = {
        text(item.get("lane_id")): item
        for item in raw_palette
        if text(item.get("lane_id"))
    }
    palette_by_lane_index = {
        int(number(item.get("lane_index"), float(index))): item
        for index, item in enumerate(raw_palette)
    }
    for raw_lane in lanes:
        if not isinstance(raw_lane, dict):
            continue
        lane_index = int(number(raw_lane.get("lane_index"), 0.0))
        tool_index = int(number(raw_lane.get("tool_index"), float(lane_index)))
        toolhead_index = int(number(raw_lane.get("toolhead_index"), float(tool_index)))
        lane = {
            "lane_index": lane_index,
            "lane_id": text(raw_lane.get("lane_id"), f"L{lane_index}"),
            "role": text(raw_lane.get("role"), "polymer"),
            "lane_kind": text(raw_lane.get("lane_kind"), "polymer"),
            "tool_index": tool_index,
            "toolhead_index": toolhead_index,
            "extruder_id": text(raw_lane.get("extruder_id"), f"T{toolhead_index}"),
            "material_type": text(raw_lane.get("material_type")),
            "filament_settings_id": text(raw_lane.get("filament_settings_id")),
            "filament_vendor": text(raw_lane.get("filament_vendor")),
            "display_color": text(raw_lane.get("display_color")),
            "nozzle_diameter": number(raw_lane.get("nozzle_diameter")),
            "display_label": text(raw_lane.get("display_label")),
        }
        lane.update(
            material_family_lane_metadata(
                raw_lane,
                raw_lane.get("material_family_source_material_text"),
                raw_lane.get("filament_settings_id"),
                raw_lane.get("material_type"),
                raw_lane.get("display_label"),
                raw_lane.get("role"),
                raw_lane.get("lane_kind"),
            )
        )
        fiber_material = nested(raw_lane.get("fiber_material"))
        if fiber_material:
            lane["fiber_material"] = {
                "name": text(fiber_material.get("name")),
                "type": text(fiber_material.get("type")),
                "material_kind": text(fiber_material.get("material_kind")),
                "source_material_id": text(fiber_material.get("source_material_id")),
                "diameter": number(fiber_material.get("diameter")),
            }
        if not lane["display_label"]:
            lane["display_label"] = mixed_lane_display_label(lane)
        normalized_lanes.append(lane)

        source_palette = palette_by_lane_id.get(lane["lane_id"]) or palette_by_lane_index.get(lane_index) or {}
        material_label = text(
            source_palette.get("label"),
            lane.get("filament_settings_id") or lane.get("material_type") or nested(lane.get("fiber_material")).get("name", ""),
        )
        color = text(source_palette.get("color"), lane.get("display_color") or COLORS["orientation"])
        palette_family = material_family_lane_metadata(
            source_palette,
            lane,
            material_label,
            source_palette.get("filament_settings_id"),
            source_palette.get("material_type"),
        )
        material_palette.append(
            {
                "id": text(source_palette.get("id"), f"lane_{lane['lane_index']}"),
                "label": material_label,
                "color": color,
                "lane_index": lane["lane_index"],
                "lane_id": lane["lane_id"],
                "tool_index": lane["tool_index"],
                "toolhead_index": lane["toolhead_index"],
                "extruder_id": lane["extruder_id"],
                "material_type": text(source_palette.get("material_type"), lane.get("material_type", "")),
                "filament_settings_id": text(source_palette.get("filament_settings_id"), lane.get("filament_settings_id", "")),
                "display_label": text(source_palette.get("display_label"), lane["display_label"]),
                "nozzle_diameter": number(source_palette.get("nozzle_diameter"), lane.get("nozzle_diameter", 0.0)),
                "material_family_key": palette_family["material_family_key"],
                "material_family_label": palette_family["material_family_label"],
                "material_family_base_polymer": palette_family["material_family_base_polymer"],
                "material_family_reinforcement_type": palette_family["material_family_reinforcement_type"],
                "material_family_is_filled": palette_family["material_family_is_filled"],
            }
        )

    lane_badges = mixed_lane_badges(normalized_lanes, material_palette)
    filled_badges = filled_material_lane_badges(lane_badges)
    readiness = dict(readiness)
    for key in (
        "unknown_material_lane_indices",
        "missing_color_lane_indices",
        "missing_nozzle_lane_indices",
        "validation_blocked_gate_ids",
        "validation_blocked_gate_messages",
    ):
        if not isinstance(readiness.get(key), list):
            readiness[key] = []
    readiness = decorate_lane_readiness_review_fields(readiness)

    mixed_context = {
        "schema_version": "1.0.0",
        "status": "ready" if normalized_lanes else "unavailable",
        "source": "orcaslicer_codex.fiber_metadata_sidecar",
        "lane_count": mixed_contract.get("lane_count", lane_contract.get("lane_count", len(normalized_lanes))),
        "selected_material_count": mixed_contract.get("selected_material_count", len(material_palette)),
        "color_count": mixed_contract.get("color_count", len({item.get("color") for item in material_palette})),
        "selected_nozzle_count": mixed_contract.get(
            "selected_nozzle_count",
            len({lane.get("nozzle_diameter") for lane in normalized_lanes if lane.get("nozzle_diameter")}),
        ),
        "filled_material_lane_count": mixed_contract.get(
            "filled_material_lane_count",
            material_family_filled_lane_count(normalized_lanes),
        ),
        "filled_material_lane_badge_count": mixed_contract.get(
            "filled_material_lane_badge_count",
            len(filled_badges),
        ),
        "filled_material_lane_badges": mixed_contract.get(
            "filled_material_lane_badges",
            filled_badges,
        ),
        "lane_badge_count": mixed_contract.get("lane_badge_count", len(lane_badges)),
        "per_toolhead_lanes": mixed_contract.get("per_toolhead_lanes", lane_contract.get("per_toolhead_lanes", False)),
        "shared_nozzle": mixed_contract.get("shared_nozzle", lane_contract.get("shared_nozzle", False)),
        "lanes": normalized_lanes,
        "material_palette": material_palette,
        "lane_badges": lane_badges,
        "lane_readiness_summary": readiness,
        "lane_readiness_status": readiness.get("status", "unavailable"),
        "lane_readiness_level": readiness.get("readiness_level", ""),
        "review_issue_count": readiness.get("review_issue_count", 0),
        "lane_readiness_review_issue_count": readiness.get("lane_readiness_review_issue_count", 0),
        "lane_readiness_review_needed": bool(readiness.get("lane_readiness_review_needed", False)),
        "lane_readiness_review_message": text(readiness.get("lane_readiness_review_message")),
        "lane_readiness_review_severity": text(readiness.get("lane_readiness_review_severity"), "info"),
        "lane_readiness_review_color": text(readiness.get("lane_readiness_review_color"), COLORS["orientation"]),
        "continuous_fiber_lane_count": readiness.get("continuous_fiber_lane_count", 0),
        "polymer_lane_count": readiness.get("polymer_lane_count", 0),
        "missing_material_lane_count": readiness.get("missing_material_lane_count", 0),
        "missing_color_lane_count": readiness.get("missing_color_lane_count", 0),
        "missing_nozzle_lane_count": readiness.get("missing_nozzle_lane_count", 0),
        "validation_blocked_gate_count": readiness.get("validation_blocked_gate_count", 0),
        "validation_blocked_gate_ids": readiness.get("validation_blocked_gate_ids", []),
        "validation_blocked_gate_messages": readiness.get("validation_blocked_gate_messages", []),
        "advisory_only": True,
    }
    mixed_context["lane_readiness_review_chip_categories"] = lane_readiness_review_chip_categories()
    mixed_context["lane_readiness_review_chip_category_count"] = len(mixed_context["lane_readiness_review_chip_categories"])
    mixed_context["lane_readiness_review_chips"] = lane_readiness_review_chips(mixed_context)
    mixed_context["lane_readiness_review_chip_count"] = len(mixed_context["lane_readiness_review_chips"])
    mixed_context["lane_readiness_review_reasons"] = lane_readiness_review_reasons(mixed_context)
    mixed_context["lane_readiness_review_reason_count"] = len(mixed_context["lane_readiness_review_reasons"])
    return mixed_context


def build_overlays(
    slice_result: dict[str, Any],
    fiber_overlay: dict[str, Any],
    selected_load_case: str,
    external_error: str | None,
) -> list[dict[str, Any]]:
    overlays: list[dict[str, Any]] = []
    current_strength_map = strength_map(slice_result, fiber_overlay)
    current_orientation_confidence = orientation_confidence(current_strength_map)
    mixed_context = mixed_filament_context(fiber_overlay, slice_result)
    current_arc_support_context = arc_support_context(slice_result)

    if current_strength_map.get("status") == "ready":
        axis_summary = ", ".join(
            f"{item['axis'].upper()} {item['relative_strength_percent']:g}%"
            for item in current_strength_map.get("print_axis_bands", [])
            if isinstance(item, dict)
        )
        estimated = bool(current_strength_map.get("estimated"))
        source = text(
            current_strength_map.get("source"),
            "orcaslicer_codex.material_family_axis_estimate" if estimated else "material_strength.orientation_comparison.print_axis_tensile_strength_mpa",
        )
        family = nested(current_strength_map.get("material_family_estimate"))
        overlays.append(
            overlay(
                "orientation_strength_color_map",
                "orientation_risk",
                "strength_color_map",
                "info",
                COLORS["orientation"],
                (
                    "Estimated filament-family strength color map is available "
                    f"for {family.get('display_name', 'the selected material')} ({axis_summary})."
                    if estimated
                    else f"Vibrant print-axis strength color map is available ({axis_summary})."
                ),
                source,
                {
                    "strength_map": current_strength_map,
                    "orientation_confidence": current_orientation_confidence,
                    "material_family_estimate": family,
                },
            )
        )
    else:
        overlays.append(
            overlay(
                "orientation_material_data_needed",
                "orientation_risk",
                "material_data_gap",
                "info",
                COLORS["orientation"],
                "Material axis-strength data is not present yet; show setup guidance instead of silent failure.",
                "orca_codex.strength_lens.fallback",
            )
        )

    if selected_load_case != "unknown":
        overlays.append(
            overlay(
                f"design_load_case_{selected_load_case}",
                "design_risk",
                "load_case_direction",
                "info" if selected_load_case != "custom_vector" else "warning",
                COLORS["load_path"] if selected_load_case != "custom_vector" else COLORS["review"],
                LOAD_CASE_MESSAGES[selected_load_case],
                "mechanicalc.strength_of_materials.load_case_vocabulary",
                {"vectors": LOAD_CASE_VECTORS.get(selected_load_case, [])},
            )
        )

    overlays.append(
        overlay(
            "design_stress_concentration_watch",
            "design_risk",
            "stress_concentration_reference",
            "warning",
            COLORS["load_path"],
            "Watch holes, notches, sharp corners, thin necks, and abrupt section changes; stress-flow crowding can dominate printed polymer parts.",
            "mechanicalc.strength_of_materials.stress_concentrations",
            {"reference": MECHANICS_REFERENCE, "simulation_reference": SIMULATION_REFERENCE},
        )
    )

    if current_arc_support_context.get("arc_support_selected"):
        overlays.append(
            overlay(
                "process_arc_support_selected",
                "process_confidence",
                "arc_support_experimental",
                "info",
                COLORS["experimental"],
                current_arc_support_context.get(
                    "preview_status_message",
                    "Arc Overhang is selected; preview it as an experimental guarded post-transform without ordinary support generation.",
                ),
                "orca_codex.support_type.arc",
                {
                    "arc_support_context": current_arc_support_context,
                    "preview_cues": current_arc_support_context.get("preview_cues", []),
                },
            )
        )

    if detect_fiber(slice_result, fiber_overlay):
        overlays.append(
            overlay(
                "fiber_route_metadata_present",
                "fiber_route",
                "fiber_route_preview",
                "info",
                COLORS["fiber"],
                "Fiber metadata is present; Strength Lens can reserve a fiber-route lens without claiming hardware readiness.",
                "orcaslicer_codex.fiber_preview_overlay",
                {"fiber_overlay_keys": sorted(fiber_overlay.keys()) if fiber_overlay else []},
            )
        )

    if mixed_context.get("status") == "ready":
        lane_readiness_status = text(mixed_context.get("lane_readiness_status"), "unavailable")
        review_issue_count = int(number(
            mixed_context.get("lane_readiness_review_issue_count", mixed_context.get("review_issue_count")),
            0.0,
        ))
        lane_review_needed = (
            bool(mixed_context.get("lane_readiness_review_needed", False))
            or lane_readiness_status in LANE_REVIEW_STATUSES
            or lane_readiness_status not in LANE_READY_STATUSES
            or review_issue_count > 0
        )
        overlays.append(
            overlay(
                "process_mixed_filament_lane_context",
                "process_confidence",
                "mixed_filament_lane_context",
                "warning" if lane_review_needed else "info",
                COLORS["review"] if lane_review_needed else COLORS["orientation"],
                (
                    mixed_context.get(
                        "lane_readiness_review_message",
                        f"Lane readiness needs review: {review_issue_count} lane metadata issue(s).",
                    )
                    if lane_review_needed
                    else (
                        "Mixed-filament lane context is available for material-aware preview and strength cues "
                        f"({mixed_context.get('lane_count', 0)} lanes, "
                        f"{mixed_context.get('selected_material_count', 0)} materials)."
                    )
                ),
                "orcaslicer_codex.fiber_metadata_sidecar.mixed_filament_contract",
                {
                    "lane_count": mixed_context.get("lane_count", 0),
                    "selected_material_count": mixed_context.get("selected_material_count", 0),
                    "color_count": mixed_context.get("color_count", 0),
                    "selected_nozzle_count": mixed_context.get("selected_nozzle_count", 0),
                    "lane_badge_count": mixed_context.get("lane_badge_count", 0),
                    "lane_readiness_status": lane_readiness_status,
                    "lane_readiness_level": mixed_context.get("lane_readiness_level", ""),
                    "review_issue_count": review_issue_count,
                    "lane_readiness_review_issue_count": review_issue_count,
                    "lane_readiness_review_needed": lane_review_needed,
                    "lane_review_needed": lane_review_needed,
                    "lane_readiness_review_message": mixed_context.get("lane_readiness_review_message", ""),
                    "lane_readiness_review_severity": mixed_context.get("lane_readiness_review_severity", "info"),
                    "lane_readiness_review_color": mixed_context.get("lane_readiness_review_color", COLORS["orientation"]),
                    "continuous_fiber_lane_count": mixed_context.get("continuous_fiber_lane_count", 0),
                    "filled_material_lane_count": mixed_context.get("filled_material_lane_count", 0),
                    "filled_material_lane_badge_count": mixed_context.get("filled_material_lane_badge_count", 0),
                    "filled_material_lane_badges": mixed_context.get("filled_material_lane_badges", []),
                    "missing_material_lane_count": mixed_context.get("missing_material_lane_count", 0),
                    "missing_color_lane_count": mixed_context.get("missing_color_lane_count", 0),
                    "missing_nozzle_lane_count": mixed_context.get("missing_nozzle_lane_count", 0),
                    "validation_blocked_gate_count": mixed_context.get("validation_blocked_gate_count", 0),
                    "validation_blocked_gate_ids": mixed_context.get("validation_blocked_gate_ids", []),
                    "validation_blocked_gate_messages": mixed_context.get("validation_blocked_gate_messages", []),
                    "lane_readiness_review_chip_categories": mixed_context.get(
                        "lane_readiness_review_chip_categories",
                        lane_readiness_review_chip_categories(),
                    ),
                    "lane_readiness_review_chip_category_count": mixed_context.get(
                        "lane_readiness_review_chip_category_count",
                        len(lane_readiness_review_chip_categories()),
                    ),
                    "lane_readiness_review_chips": mixed_context.get("lane_readiness_review_chips", []),
                    "lane_readiness_review_chip_count": mixed_context.get("lane_readiness_review_chip_count", 0),
                    "lane_readiness_review_reasons": mixed_context.get("lane_readiness_review_reasons", []),
                    "lane_readiness_review_reason_count": mixed_context.get("lane_readiness_review_reason_count", 0),
                    "lanes": mixed_context.get("lanes", []),
                    "material_palette": mixed_context.get("material_palette", []),
                    "lane_badges": mixed_context.get("lane_badges", []),
                },
            )
        )

    if external_error:
        overlays.append(
            overlay(
                "process_full_builder_fallback",
                "process_confidence",
                "integration_fallback",
                "warning",
                COLORS["review"],
                "Full TinManX1 Strength Lens builder was unavailable or failed; compact Orca fallback generated advisory overlays.",
                "orca_codex.strength_lens.fallback",
                {"external_builder_error": external_error[-1200:]},
            )
        )

    overlays.append(
        overlay(
            "process_advisory_guardrail",
            "process_confidence",
            "advisory_only",
            "info",
            COLORS["strong"],
            "Strength Lens is a predictive planning display only, not certified FEA, not a safety factor, and not a print approval.",
            "orca_codex.strength_lens.contract",
        )
    )
    return overlays


def viewport_legend(mixed_context: dict[str, Any]) -> list[dict[str, Any]]:
    material_palette = mixed_context.get("material_palette") if isinstance(mixed_context.get("material_palette"), list) else []
    return [
        {"id": "critical", "label": "Critical weak axis", "color": COLORS["critical"]},
        {"id": "review", "label": "Review weak axis", "color": COLORS["review"]},
        {"id": "usable", "label": "Usable orientation", "color": COLORS["orientation"]},
        {"id": "strong", "label": "Strong orientation", "color": COLORS["strong"]},
        {"id": "load_path", "label": "Load path cue", "color": COLORS["load_path"]},
        {"id": "fiber", "label": "Fiber route cue", "color": COLORS["fiber"]},
        *[
            {
                "id": text(item.get("id"), "material_lane"),
                "label": f"Material: {text(item.get('label'), 'Lane')}",
                "color": text(item.get("color"), COLORS["orientation"]),
            }
            for item in material_palette[:8]
            if isinstance(item, dict)
        ],
    ]


def viewport_plan(
    overlays: list[dict[str, Any]],
    active_lens: str,
    lane_badges: list[dict[str, Any]] | None = None,
    lane_readiness_status: str = "unavailable",
    lane_readiness_level: str = "",
    current_arc_context: dict[str, Any] | None = None,
    current_strength_map: dict[str, Any] | None = None,
    current_orientation_confidence: dict[str, Any] | None = None,
    current_load_case: dict[str, Any] | None = None,
    current_legend: list[dict[str, Any]] | None = None,
    current_mixed_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    badges = [item for item in lane_badges or [] if isinstance(item, dict)]
    legend = [item for item in current_legend or [] if isinstance(item, dict)]
    mixed_context = current_mixed_context if isinstance(current_mixed_context, dict) else {}
    arc_context = current_arc_context if isinstance(current_arc_context, dict) else {}
    strength = current_strength_map if isinstance(current_strength_map, dict) else {}
    family = nested(strength.get("material_family_estimate"))
    print_axis_bands = strength.get("print_axis_bands") if isinstance(strength.get("print_axis_bands"), list) else []
    orientation = current_orientation_confidence if isinstance(current_orientation_confidence, dict) else {}
    load_case = current_load_case if isinstance(current_load_case, dict) else {}
    load_vectors = load_case.get("vectors") if isinstance(load_case.get("vectors"), list) else []
    load_vector_chips = load_case_vector_chips(load_vectors, text(load_case.get("kind"), "unknown"))
    arc_preview_cues = arc_context.get("preview_cues") if isinstance(arc_context.get("preview_cues"), list) else []
    review_categories = lane_readiness_review_chip_categories()
    review_chips = lane_readiness_review_chips(mixed_context)
    review_reasons = lane_readiness_review_reasons(mixed_context)
    lens_overlay_counts: dict[str, int] = {}
    lens_warning_counts: dict[str, int] = {}
    layers = []
    for lens_id, label in LENSES:
        lens_overlays = [item for item in overlays if item.get("lens") == lens_id]
        lens_overlay_counts[lens_id] = len(lens_overlays)
        lens_warning_counts[lens_id] = sum(1 for item in lens_overlays if item.get("severity") == "warning")
        layers.append(
            {
                "lens": lens_id,
                "label": label,
                "visible_by_default": lens_id == active_lens,
                "render_style": "surface_tint_and_badge_cues",
                "model_target": "selected_model_surface",
                "overlay_count": lens_overlay_counts[lens_id],
                "warning_count": lens_warning_counts[lens_id],
            }
        )
    top_cues = overlays[:6]
    return {
        "schema_version": "1.0.0",
        "status": "ready" if overlays else "empty",
        "active_lens": active_lens,
        "render_mode": "non_destructive_preview_overlay",
        "layers": layers,
        "top_cues": top_cues,
        "overlay_count": len(overlays),
        "warning_overlay_count": sum(1 for item in overlays if item.get("severity") == "warning"),
        "top_cue_count": len(top_cues),
        "lens_overlay_counts": lens_overlay_counts,
        "lens_warning_counts": lens_warning_counts,
        "lane_badge_count": len(badges),
        "lane_badges": badges,
        "lane_readiness_status": lane_readiness_status,
        "lane_readiness_level": lane_readiness_level,
        "mixed_filament_status": text(mixed_context.get("status"), "unavailable"),
        "mixed_filament_source": text(mixed_context.get("source")),
        "mixed_filament_lane_count": int(number(mixed_context.get("lane_count"), 0.0)),
        "mixed_filament_material_count": int(number(mixed_context.get("selected_material_count"), 0.0)),
        "mixed_filament_color_count": int(number(mixed_context.get("color_count"), 0.0)),
        "mixed_filament_nozzle_count": int(number(mixed_context.get("selected_nozzle_count"), 0.0)),
        "lane_readiness_review_issue_count": int(number(
            mixed_context.get("lane_readiness_review_issue_count", mixed_context.get("review_issue_count")),
            0.0,
        )),
        "lane_readiness_review_needed": bool(mixed_context.get("lane_readiness_review_needed", False)),
        "lane_readiness_review_message": text(mixed_context.get("lane_readiness_review_message")),
        "lane_readiness_review_severity": text(mixed_context.get("lane_readiness_review_severity"), "info"),
        "lane_readiness_review_color": text(mixed_context.get("lane_readiness_review_color"), COLORS["orientation"]),
        "continuous_fiber_lane_count": int(number(mixed_context.get("continuous_fiber_lane_count"), 0.0)),
        "filled_material_lane_count": int(number(mixed_context.get("filled_material_lane_count"), 0.0)),
        "filled_material_lane_badge_count": int(number(mixed_context.get("filled_material_lane_badge_count"), 0.0)),
        "filled_material_lane_badges": mixed_context.get("filled_material_lane_badges")
        if isinstance(mixed_context.get("filled_material_lane_badges"), list)
        else [],
        "polymer_lane_count": int(number(mixed_context.get("polymer_lane_count"), 0.0)),
        "missing_material_lane_count": int(number(mixed_context.get("missing_material_lane_count"), 0.0)),
        "missing_color_lane_count": int(number(mixed_context.get("missing_color_lane_count"), 0.0)),
        "missing_nozzle_lane_count": int(number(mixed_context.get("missing_nozzle_lane_count"), 0.0)),
        "validation_blocked_gate_count": int(number(mixed_context.get("validation_blocked_gate_count"), 0.0)),
        "validation_blocked_gate_ids": mixed_context.get("validation_blocked_gate_ids")
        if isinstance(mixed_context.get("validation_blocked_gate_ids"), list)
        else [],
        "validation_blocked_gate_messages": mixed_context.get("validation_blocked_gate_messages")
        if isinstance(mixed_context.get("validation_blocked_gate_messages"), list)
        else [],
        "lane_readiness_review_chip_categories": review_categories,
        "lane_readiness_review_chip_category_count": len(review_categories),
        "lane_readiness_review_chips": review_chips,
        "lane_readiness_review_chip_count": len(review_chips),
        "lane_readiness_review_reasons": review_reasons,
        "lane_readiness_review_reason_count": len(review_reasons),
        "arc_support_selected": bool(arc_context.get("arc_support_selected", False)),
        "arc_support_preview_status": text(arc_context.get("status"), "unavailable"),
        "arc_support_preview_label": text(arc_context.get("preview_label")),
        "arc_support_preview_status_message": text(arc_context.get("preview_status_message")),
        "arc_support_postprocess_stage": text(arc_context.get("postprocess_stage")),
        "arc_support_guardrail_summary": text(arc_context.get("guardrail_summary")),
        "arc_support_guarded_transform_required": bool(arc_context.get("guarded_transform_required", False)),
        "arc_support_preview_cues": arc_preview_cues,
        "arc_support_preview_cue_count": len(arc_preview_cues),
        "arc_support_preview_cue_chips": arc_support_preview_cue_chips(arc_preview_cues),
        "arc_support_preview_cue_chip_count": len(arc_support_preview_cue_chips(arc_preview_cues)),
        "strength_map_status": text(strength.get("status"), "unavailable"),
        "strength_map_basis": text(strength.get("basis")),
        "strength_map_estimated": bool(strength.get("estimated", False)),
        "strength_map_metric": text(strength.get("metric")),
        "strength_render_policy": text(strength.get("render_policy")),
        "strength_color_mode": text(strength.get("color_mode")),
        "reference_strength_mpa": number(strength.get("reference_strength_mpa"), 0.0),
        "print_axis_bands": print_axis_bands,
        "print_axis_band_count": len(print_axis_bands),
        "material_family_estimate_status": text(family.get("status"), "unavailable"),
        "material_family_key": text(family.get("family_key")),
        "material_family_label": text(family.get("display_name")),
        "material_family_source_material_text": text(family.get("source_material_text")),
        "material_family_matched_alias": text(family.get("matched_alias")),
        "material_family_base_polymer": text(family.get("base_polymer")),
        "material_family_reinforcement_type": text(family.get("reinforcement_type"), "none"),
        "material_family_is_filled": bool(family.get("is_filled_family", False)),
        "material_family_basis": text(family.get("basis")),
        "material_family_source": text(family.get("source")),
        "material_family_warning": text(family.get("warning")),
        "material_family_axis_strengths_mpa": nested(family.get("print_axis_tensile_strength_mpa")),
        "orientation_confidence_status": text(orientation.get("status"), "needs_material_axis_data"),
        "orientation_confidence_level": text(orientation.get("confidence_level"), "setup_required"),
        "orientation_confidence_basis": text(orientation.get("basis")),
        "orientation_confidence_estimated": bool(orientation.get("estimated", False)),
        "strongest_print_axis": text(orientation.get("strongest_print_axis")),
        "weakest_print_axis": text(orientation.get("weakest_print_axis")),
        "strongest_strength_mpa": number(orientation.get("strongest_strength_mpa"), 0.0),
        "weakest_strength_mpa": number(orientation.get("weakest_strength_mpa"), 0.0),
        "weakest_to_strongest_ratio": number(orientation.get("weakest_to_strongest_ratio"), 0.0),
        "weakest_axis_drop_percent": number(orientation.get("weakest_axis_drop_percent"), 0.0),
        "orientation_warning_axes": orientation.get("warning_axes") if isinstance(orientation.get("warning_axes"), list) else [],
        "load_case_kind": text(load_case.get("kind"), "unknown"),
        "load_case_label": text(load_case.get("label")),
        "load_case_message": text(load_case.get("message")),
        "load_case_vector_count": len(load_vectors),
        "load_case_vectors": load_vectors,
        "load_case_vector_chips": load_vector_chips,
        "load_case_vector_chip_count": len(load_vector_chips),
        "legend": legend,
        "legend_count": len(legend),
        "advisory_only": True,
        "slicing_or_gcode_modified": False,
        "certified_fea": False,
        "certified_safety_factor": False,
        "print_approval": False,
        "machine_ready_structural_approval": False,
        "safety_note": "Viewport cues are predictive display metadata only; they do not alter slicing, G-code, or printer behavior.",
    }


def fallback_visualization(
    args: argparse.Namespace,
    slice_result: dict[str, Any],
    fiber_overlay: dict[str, Any],
    external_error: str | None,
) -> dict[str, Any]:
    overlays = build_overlays(slice_result, fiber_overlay, args.load_case, external_error)
    current_strength_map = strength_map(slice_result, fiber_overlay)
    current_orientation_confidence = orientation_confidence(current_strength_map)
    mixed_context = mixed_filament_context(fiber_overlay, slice_result)
    current_arc_support_context = arc_support_context(slice_result)
    warning_count = sum(1 for item in overlays if item.get("severity") == "warning")
    current_load_case = {
        "kind": args.load_case,
        "label": args.load_case.replace("_", " ").title(),
        "message": LOAD_CASE_MESSAGES[args.load_case],
        "vectors": LOAD_CASE_VECTORS.get(args.load_case, []),
    }
    current_load_case["vector_chips"] = load_case_vector_chips(current_load_case["vectors"], args.load_case)
    current_load_case["vector_chip_count"] = len(current_load_case["vector_chips"])
    current_legend = viewport_legend(mixed_context)
    visualization = {
        "schema_version": "1.0.0",
        "contract": strength_contract(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_artifacts": input_artifacts(args),
        "visualization_id": f"orca-codex-strength-lens-{args.load_case}",
        "status": "fallback_predictive",
        "active_lens": args.active_lens,
        "scope": {
            "applies_to_all_printers": True,
            "applies_to_non_continuous_fiber": True,
            "continuous_fiber_required": False,
            "slicing_or_gcode_modified": False,
        },
        "mechanics_reference": MECHANICS_REFERENCE,
        "simulation_reference": SIMULATION_REFERENCE,
        "material": {
            "material_id": material_id(slice_result),
            "display_name": material_label(slice_result),
        },
        "load_case": current_load_case,
        "display": {
            "style": "vibrant_surface_overlay",
            "palette": COLORS,
            "guardrail": "predictive planning display only; not certified FEA, not a safety factor, and not a print approval",
        },
        "strength_map": current_strength_map,
        "orientation_confidence": current_orientation_confidence,
        "mixed_filament_context": mixed_context,
        "arc_support_context": current_arc_support_context,
        "summary": {
            "overlay_count": len(overlays),
            "warning_count": warning_count,
            "strength_map_status": current_strength_map.get("status", "unavailable"),
            "strength_map_basis": current_strength_map.get("basis", ""),
            "strength_map_estimated": bool(current_strength_map.get("estimated")),
            "material_family_estimate_status": nested(current_strength_map.get("material_family_estimate")).get("status", ""),
            "material_family": nested(current_strength_map.get("material_family_estimate")).get("family_key", ""),
            "material_family_base_polymer": nested(current_strength_map.get("material_family_estimate")).get("base_polymer", ""),
            "material_family_reinforcement_type": nested(current_strength_map.get("material_family_estimate")).get(
                "reinforcement_type",
                "none",
            ),
            "material_family_is_filled": bool(
                nested(current_strength_map.get("material_family_estimate")).get("is_filled_family", False)
            ),
            "orientation_confidence_level": current_orientation_confidence.get("confidence_level", "setup_required"),
            "weakest_print_axis": current_orientation_confidence.get("weakest_print_axis", ""),
            "strongest_print_axis": current_orientation_confidence.get("strongest_print_axis", ""),
            "load_case_kind": current_load_case.get("kind", args.load_case),
            "load_case_label": current_load_case.get("label", args.load_case.replace("_", " ").title()),
            "load_case_message": current_load_case.get("message", ""),
            "load_case_vector_count": len(current_load_case.get("vectors", [])),
            "load_case_vectors": current_load_case.get("vectors", []),
            "load_case_vector_chips": current_load_case.get("vector_chips", []),
            "load_case_vector_chip_count": current_load_case.get("vector_chip_count", 0),
            "legend_count": len(current_legend),
            "mixed_filament_lane_count": mixed_context.get("lane_count", 0) if mixed_context.get("status") == "ready" else 0,
            "mixed_filament_material_count": mixed_context.get("selected_material_count", 0)
            if mixed_context.get("status") == "ready"
            else 0,
            "mixed_filament_lane_badge_count": mixed_context.get("lane_badge_count", 0)
            if mixed_context.get("status") == "ready"
            else 0,
            "filled_material_lane_count": mixed_context.get("filled_material_lane_count", 0)
            if mixed_context.get("status") == "ready"
            else 0,
            "filled_material_lane_badge_count": mixed_context.get("filled_material_lane_badge_count", 0)
            if mixed_context.get("status") == "ready"
            else 0,
            "filled_material_lane_badges": mixed_context.get("filled_material_lane_badges", [])
            if mixed_context.get("status") == "ready"
            else [],
            "lane_readiness_status": mixed_context.get("lane_readiness_status", "unavailable"),
            "lane_readiness_level": mixed_context.get("lane_readiness_level", ""),
            "lane_readiness_review_issue_count": mixed_context.get(
                "lane_readiness_review_issue_count",
                mixed_context.get("review_issue_count", 0),
            ),
            "lane_readiness_review_needed": bool(mixed_context.get("lane_readiness_review_needed", False)),
            "lane_readiness_review_message": mixed_context.get("lane_readiness_review_message", ""),
            "lane_readiness_review_severity": mixed_context.get("lane_readiness_review_severity", "info"),
            "lane_readiness_review_color": mixed_context.get("lane_readiness_review_color", COLORS["orientation"]),
            "continuous_fiber_lane_count": mixed_context.get("continuous_fiber_lane_count", 0),
            "missing_material_lane_count": mixed_context.get("missing_material_lane_count", 0),
            "missing_color_lane_count": mixed_context.get("missing_color_lane_count", 0),
            "missing_nozzle_lane_count": mixed_context.get("missing_nozzle_lane_count", 0),
            "validation_blocked_gate_count": mixed_context.get("validation_blocked_gate_count", 0),
            "validation_blocked_gate_ids": mixed_context.get("validation_blocked_gate_ids", []),
            "validation_blocked_gate_messages": mixed_context.get("validation_blocked_gate_messages", []),
            "lane_readiness_review_chip_categories": mixed_context.get(
                "lane_readiness_review_chip_categories",
                lane_readiness_review_chip_categories(),
            ),
            "lane_readiness_review_chip_category_count": mixed_context.get(
                "lane_readiness_review_chip_category_count",
                len(lane_readiness_review_chip_categories()),
            ),
            "lane_readiness_review_chips": mixed_context.get("lane_readiness_review_chips", []),
            "lane_readiness_review_chip_count": mixed_context.get("lane_readiness_review_chip_count", 0),
            "lane_readiness_review_reasons": mixed_context.get("lane_readiness_review_reasons", []),
            "lane_readiness_review_reason_count": mixed_context.get("lane_readiness_review_reason_count", 0),
            "arc_support_selected": current_arc_support_context.get("arc_support_selected", False),
            "arc_support_preview_status": current_arc_support_context.get("status", "unavailable"),
            "arc_support_preview_label": current_arc_support_context.get("preview_label", ""),
            "arc_support_postprocess_stage": current_arc_support_context.get("postprocess_stage", ""),
            "arc_support_guarded_transform_required": current_arc_support_context.get("guarded_transform_required", False),
            "arc_support_preview_cue_count": current_arc_support_context.get("preview_cue_count", 0),
            "arc_support_preview_cue_chips": current_arc_support_context.get("preview_cue_chips", []),
            "arc_support_preview_cue_chip_count": current_arc_support_context.get("preview_cue_chip_count", 0),
            "advisory_only": True,
        },
        "legend": current_legend,
        "viewport_render_plan": viewport_plan(
            overlays,
            args.active_lens,
            mixed_context.get("lane_badges", []),
            mixed_context.get("lane_readiness_status", "unavailable"),
            mixed_context.get("lane_readiness_level", ""),
            current_arc_support_context,
            current_strength_map,
            current_orientation_confidence,
            current_load_case,
            current_legend,
            mixed_context,
        ),
        "overlays": overlays,
        "external_builder_error": external_error,
    }
    return enforce_advisory_contract(visualization, "fallback", slice_result, fiber_overlay, args.active_lens, args.load_case)


def main() -> int:
    args = parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)

    slice_result = read_json(args.slice_result)
    fiber_overlay = read_json(args.fiber_preview_overlay)

    external_error = None
    if not args.force_fallback:
        builder = find_external_builder(args.external_builder)
        if builder:
            external_error = run_external_builder(args, builder)
            if external_error is None:
                normalization_error = normalize_external_visualization(
                    args.out,
                    "external_builder",
                    input_artifacts(args),
                    slice_result,
                    fiber_overlay,
                    args.active_lens,
                    args.load_case,
                )
                if normalization_error is None:
                    return 0
                external_error = normalization_error

    visualization = fallback_visualization(args, slice_result, fiber_overlay, external_error)
    args.out.write_text(json.dumps(visualization, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
