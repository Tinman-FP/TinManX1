#!/usr/bin/env python3
"""Smoke-test the native FibreSeek planner against pocket-crossing regressions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

from shapely.geometry import LineString, Polygon


REPO_ROOT = Path(__file__).resolve().parents[1]
PLANNER_DIR = REPO_ROOT / "resources" / "orcaslicer_codex" / "fiber_planner"
sys.path.insert(0, str(PLANNER_DIR))

import orcaslicer_codex_native_fiber_planner as planner  # noqa: E402


SYNTHETIC_GCODE = """\
;LAYER_CHANGE
;Z:0.2
;HEIGHT:0.2
G90
M82
G0 X0 Y0 F9000
;TYPE:Outer wall
G1 X100 Y0 E1 F1800
G1 X100 Y100 E2
G1 X0 Y100 E3
G1 X0 Y0 E4
G0 X35 Y35 F9000
;TYPE:Outer wall
G1 X65 Y35 E5 F1800
G1 X65 Y65 E6
G1 X35 Y65 E7
G1 X35 Y35 E8
; fiber_generate_perimeters = 1
; fiber_generate_infill = 1
; fiber_reinforcement_mode = heavy
; fiber_infill_pattern = grid
; fiber_diameter = 0.25
; fiber_linear_density = 102
"""


SYNTHETIC_SHORT_POCKET_GCODE = """\
;LAYER_CHANGE
;Z:0.2
;HEIGHT:0.2
G90
M82
G0 X0 Y0 F9000
;TYPE:Outer wall
G1 X100 Y0 E1 F1800
G1 X100 Y100 E2
G1 X0 Y100 E3
G1 X0 Y0 E4
G0 X20 Y20 F9000
;TYPE:Inner wall
G1 X37 Y20 E5 F1800
G1 X37 Y37 E6
G1 X20 Y37 E7
G1 X20 Y20 E8
G0 X39 Y20 F9000
;TYPE:Inner wall
G1 X56 Y20 E9 F1800
G1 X56 Y37 E10
G1 X39 Y37 E11
G1 X39 Y20 E12
; fiber_generate_perimeters = 1
; fiber_generate_infill = 0
; fiber_reinforcement_mode = heavy
; fiber_minimum_perimeter_length = 55
; fiber_cut_distance = 58
; fiber_start_length = 15
; fiber_diameter = 0.25
; fiber_linear_density = 102
"""


SYNTHETIC_TOO_SHORT_CUT_WINDOW_GCODE = """\
;LAYER_CHANGE
;Z:0.2
;HEIGHT:0.2
G90
M82
G0 X0 Y0 F9000
;TYPE:Outer wall
G1 X100 Y0 E1 F1800
G1 X100 Y100 E2
G1 X0 Y100 E3
G1 X0 Y0 E4
G0 X20 Y20 F9000
;TYPE:Inner wall
G1 X34 Y20 E5 F1800
G1 X34 Y34 E6
G1 X20 Y34 E7
G1 X20 Y20 E8
; fiber_generate_perimeters = 1
; fiber_generate_infill = 0
; fiber_reinforcement_mode = heavy
; fiber_minimum_perimeter_length = 55
; fiber_cut_distance = 58
; fiber_start_length = 15
; fiber_diameter = 0.25
; fiber_linear_density = 102
"""


def circular_wall_gcode(
    cx: float,
    cy: float,
    radius: float,
    e_start: float,
    segments: int = 32,
    role: str = "Inner wall",
) -> tuple[str, float]:
    import math

    lines = [f"G0 X{cx + radius:.3f} Y{cy:.3f} F9000", f";TYPE:{role}"]
    e_value = e_start
    for index in range(1, segments + 1):
        angle = 2.0 * math.pi * index / segments
        e_value += 0.12
        lines.append(f"G1 X{cx + radius * math.cos(angle):.3f} Y{cy + radius * math.sin(angle):.3f} E{e_value:.4f} F1800")
    return "\n".join(lines), e_value


def circular_inner_wall_gcode(cx: float, cy: float, radius: float, e_start: float, segments: int = 32) -> tuple[str, float]:
    return circular_wall_gcode(cx, cy, radius, e_start, segments=segments, role="Inner wall")


def synthetic_close_hole_cluster_gcode() -> str:
    centers = [
        (44.7, 48.0),
        (44.7, 57.0),
        (52.5, 43.5),
        (52.5, 61.5),
        (60.3, 48.0),
        (60.3, 57.0),
    ]
    e_value = 4.0
    hole_blocks: list[str] = []
    for cx, cy in centers:
        block, e_value = circular_inner_wall_gcode(cx, cy, 3.0, e_value)
        hole_blocks.append(block)
    return "\n".join(
        [
            ";LAYER_CHANGE",
            ";Z:0.2",
            ";HEIGHT:0.2",
            "G90",
            "M82",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            *hole_blocks,
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 12",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


def synthetic_legal_small_hole_gcode() -> str:
    block, _ = circular_inner_wall_gcode(50.0, 50.0, 13.0, 4.0, segments=64)
    return "\n".join(
        [
            ";LAYER_CHANGE",
            ";Z:0.2",
            ";HEIGHT:0.2",
            "G90",
            "M82",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            block,
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 12",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


def synthetic_isolated_tiny_hole_gcode() -> str:
    block, _ = circular_inner_wall_gcode(50.0, 50.0, 3.0, 4.0, segments=32)
    return "\n".join(
        [
            ";LAYER_CHANGE",
            ";Z:0.2",
            ";HEIGHT:0.2",
            "G90",
            "M82",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            block,
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 12",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


def synthetic_local_hole_cluster_gcode() -> str:
    centers = [
        (52.5, 43.5),
        (60.3, 48.0),
        (44.7, 48.0),
        (53.0, 52.5),
        (60.3, 57.0),
        (44.7, 57.0),
        (52.5, 61.5),
    ]
    e_value = 4.0
    hole_blocks: list[str] = []
    for cx, cy in centers:
        outer_block, e_value = circular_wall_gcode(cx, cy, 2.7, e_value, segments=32, role="Outer wall")
        inner_radius = 4.6 if (cx, cy) == (53.0, 52.5) else 3.5
        inner_block, e_value = circular_wall_gcode(cx, cy, inner_radius, e_value, segments=32, role="Inner wall")
        hole_blocks.extend([outer_block, inner_block])
    return "\n".join(
        [
            ";LAYER_CHANGE",
            ";Z:0.2",
            ";HEIGHT:0.2",
            "G90",
            "M82",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            *hole_blocks,
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 12",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


def synthetic_internal_void_stitch_gear_gcode() -> str:
    centers = [
        (50.0, 50.0),
        (80.0, 50.0),
        (65.0, 75.981),
        (35.0, 75.981),
        (20.0, 50.0),
        (35.0, 24.019),
        (65.0, 24.019),
    ]
    e_value = 0.0
    lines: list[str] = []
    for layer_index, z in enumerate((0.2, 0.4, 0.6, 0.8, 1.0, 1.2)):
        e_value += 1.0
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z:.1f}",
                ";HEIGHT:0.2",
                "G90",
                "M82",
                "G0 X0 Y0 F9000",
                ";TYPE:Inner wall",
                f"G1 X100 Y0 E{e_value:.4f} F1800",
            ]
        )
        for point in ((100.0, 100.0), (0.0, 100.0), (0.0, 0.0)):
            e_value += 1.0
            lines.append(f"G1 X{point[0]:.3f} Y{point[1]:.3f} E{e_value:.4f}")
        for cx, cy in centers:
            outer_radius = 4.0 if (cx, cy) == (50.0, 50.0) else 2.7
            outer_block, e_value = circular_wall_gcode(cx, cy, outer_radius, e_value, segments=32, role="Outer wall")
            inner_radius = 4.6 if (cx, cy) == (50.0, 50.0) else 3.5
            inner_block, e_value = circular_wall_gcode(cx, cy, inner_radius, e_value, segments=32, role="Inner wall")
            lines.extend([outer_block, inner_block])
        if layer_index == 0:
            lines.extend(
                [
                    "; fiber_generate_perimeters = 1",
                    "; fiber_generate_infill = 0",
                    "; fiber_reinforcement_mode = heavy",
                    "; fiber_cut_distance = 58",
                    "; fiber_start_length = 15",
                    "; fiber_min_radius = 12",
                    "; fiber_diameter = 0.25",
                    "; fiber_linear_density = 102",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def synthetic_alternating_hole_family_gcode() -> str:
    centers = [
        (50.0, 50.0),
        (25.0, 80.0),
        (75.0, 80.0),
        (25.0, 20.0),
        (75.0, 20.0),
    ]
    e_value = 0.0
    lines: list[str] = []
    for layer_index, z in enumerate((0.2, 0.4, 0.6)):
        e_value += 1.0
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z:.1f}",
                ";HEIGHT:0.2",
                "G90",
                "M82",
                "G0 X0 Y0 F9000",
                ";TYPE:Outer wall",
                f"G1 X100 Y0 E{e_value:.4f} F1800",
            ]
        )
        for point in ((100.0, 100.0), (0.0, 100.0), (0.0, 0.0)):
            e_value += 1.0
            lines.append(f"G1 X{point[0]:.3f} Y{point[1]:.3f} E{e_value:.4f}")
        for cx, cy in centers:
            block, e_value = circular_inner_wall_gcode(cx, cy, 13.0, e_value, segments=48)
            lines.append(block)
        if layer_index == 0:
            lines.extend(
                [
                    "; fiber_generate_perimeters = 1",
                    "; fiber_generate_infill = 0",
                    "; fiber_reinforcement_mode = medium",
                    "; fiber_cut_distance = 58",
                    "; fiber_start_length = 15",
                    "; fiber_min_radius = 12",
                    "; fiber_diameter = 0.25",
                    "; fiber_linear_density = 102",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def synthetic_radial_small_gear_hole_gcode() -> str:
    centers = [
        (50.0, 50.0),
        (80.0, 50.0),
        (65.0, 75.981),
        (35.0, 75.981),
        (20.0, 50.0),
        (35.0, 24.019),
        (65.0, 24.019),
    ]
    e_value = 0.0
    lines: list[str] = []
    for layer_index, z in enumerate((0.2, 0.4, 0.6)):
        e_value += 1.0
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z:.1f}",
                ";HEIGHT:0.2",
                "G90",
                "M82",
                "G0 X0 Y0 F9000",
                ";TYPE:Outer wall",
                f"G1 X100 Y0 E{e_value:.4f} F1800",
            ]
        )
        for point in ((100.0, 100.0), (0.0, 100.0), (0.0, 0.0)):
            e_value += 1.0
            lines.append(f"G1 X{point[0]:.3f} Y{point[1]:.3f} E{e_value:.4f}")
        for cx, cy in centers:
            block, e_value = circular_inner_wall_gcode(cx, cy, 12.4, e_value, segments=48)
            lines.append(block)
        if layer_index == 0:
            lines.extend(
                [
                    "; fiber_generate_perimeters = 1",
                    "; fiber_generate_infill = 0",
                    "; fiber_reinforcement_mode = medium",
                    "; fiber_cut_distance = 58",
                    "; fiber_start_length = 15",
                    "; fiber_min_radius = 12",
                    "; fiber_diameter = 0.25",
                    "; fiber_linear_density = 102",
                ]
            )
    lines.append("")
    return "\n".join(lines)


def synthetic_fiberseek_contract_gcode() -> str:
    return "\n".join(
        [
            ";FLAVOR:Marlin",
            "; nozzle_temperature = 260,275",
            "; nozzle_temperature_initial_layer = 260,275",
            "; hot_plate_temp_initial_layer = 80",
            "; chamber_temperature = 35",
            "M104 S260",
            "M140 S80",
            "G21",
            "G90",
            "M83",
            "G92 E0",
            "M190 S80",
            "T0",
            ";LAYER_CHANGE",
            ";Z:0.2",
            ";HEIGHT:0.2",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            ";LAYER_CHANGE",
            ";Z:0.4",
            ";HEIGHT:0.2",
            "G0 X0 Y0 F9000",
            ";TYPE:Outer wall",
            "G1 X100 Y0 E1 F1800",
            "G1 X100 Y100 E2",
            "G1 X0 Y100 E3",
            "G1 X0 Y0 E4",
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 12",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "M106 S0",
            ";TYPE:Custom",
            "; filament end gcode",
            "M106 S0",
            "G0 X300 Y280 F9000",
            "; EXECUTABLE_BLOCK_END",
            "; CONFIG_BLOCK_START",
            "",
        ]
    )


def synthetic_layup_payload_gcode() -> str:
    payload = {
        "z_bands": [
            {"name": "off_layer", "from_layer": 1, "to_layer": 1, "enabled": False},
            {
                "name": "tetra_layer",
                "from_layer": 2,
                "to_layer": 2,
                "mode": "heavy",
                "perimeters": False,
                "infill": True,
                "pattern": "tetragrid",
                "spacing": 32,
                "infill_routes_per_layer": 80,
            },
        ]
    }
    lines = ["G90", "M82"]
    e_value = 0.0
    for z in (0.2, 0.4):
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z}",
                ";HEIGHT:0.2",
                "G0 X0 Y0 F9000",
                ";TYPE:Outer wall",
            ]
        )
        for x, y in ((120, 0), (120, 120), (0, 120), (0, 0)):
            e_value += 1.0
            lines.append(f"G1 X{x} Y{y} E{e_value:.4f} F1800")
    lines.extend(
        [
            "; fiber_generate_perimeters = 0",
            "; fiber_generate_infill = 1",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_infill_source_policy = generated_ribs",
            "; fiber_min_route_length = 55",
            "; fiber_mechanical_min_route_length = 55",
            f"; fiber_reinforcement_payload = {json.dumps(payload, separators=(',', ':'))}",
        ]
    )
    return "\n".join(lines) + "\n"


def synthetic_layup_ui_gcode() -> str:
    payload = {
        "layup_bands": [
            {
                "name": "UI Shell",
                "from_layer": 1,
                "to_layer": 1,
                "mode": "light",
                "pattern": "rhombic",
                "perimeters": True,
                "infill": False,
                "priority": 101,
            },
            {
                "name": "UI Core",
                "from_layer": 2,
                "to_layer": 2,
                "mode": "heavy",
                "pattern": "tetragrid",
                "perimeters": False,
                "infill": True,
                "spacing": 32,
                "max_routes_per_layer": 80,
                "priority": 102,
            },
        ]
    }
    lines = ["G90", "M82"]
    e_value = 0.0
    for z in (0.2, 0.4):
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z}",
                ";HEIGHT:0.2",
                "G0 X0 Y0 F9000",
                ";TYPE:Outer wall",
            ]
        )
        for x, y in ((120, 0), (120, 120), (0, 120), (0, 0)):
            e_value += 1.0
            lines.append(f"G1 X{x} Y{y} E{e_value:.4f} F1800")
    lines.extend(
        [
            "; fiber_generate_perimeters = 0",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = light",
            "; fiber_infill_source_policy = generated_ribs",
            "; fiber_min_route_length = 55",
            "; fiber_mechanical_min_route_length = 55",
            f"; fiber_reinforcement_payload = {json.dumps(payload, separators=(',', ':'))}",
        ]
    )
    return "\n".join(lines) + "\n"


def synthetic_fan_schedule_gcode() -> str:
    lines = ["G90", "M82"]
    e_value = 0.0
    for z in (0.2, 0.4, 0.6, 0.8, 1.0):
        lines.extend(
            [
                ";LAYER_CHANGE",
                f";Z:{z}",
                ";HEIGHT:0.2",
                "G0 X0 Y0 F9000",
                ";TYPE:Outer wall",
            ]
        )
        for x, y in ((100, 0), (100, 100), (0, 100), (0, 0)):
            e_value += 1.0
            lines.append(f"G1 X{x} Y{y} E{e_value:.4f} F1800")
    lines.extend(
        [
            "; fiber_generate_perimeters = 1",
            "; fiber_generate_infill = 0",
            "; fiber_reinforcement_mode = heavy",
            "; fiber_cut_distance = 58",
            "; fiber_start_length = 15",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
        ]
    )
    return "\n".join(lines) + "\n"


def route_center(route: planner.FiberRoute) -> tuple[float, float]:
    center = planner.route_spatial_center(route.points)
    if center is None:
        raise SystemExit(f"Route has no measurable center: {route}")
    return center


def default_planner_args(**overrides: object) -> SimpleNamespace:
    values = {
        "angles": None,
        "fiber_reinforcement_mode": None,
        "fiber_generate_perimeters": None,
        "fiber_generate_infill": None,
        "fiber_infill_pattern": None,
        "fiber_infill_source": None,
        "spacing": None,
        "density": None,
        "fiber_seam_position": None,
        "fiber_seam_angle": None,
        "layer_step": None,
        "fiber_start_layer": None,
        "min_route_length": None,
        "line_width": None,
        "perimeter_inset": None,
        "infill_inset": None,
        "fiber_print_speed": None,
        "fiber_start_speed": None,
        "max_routes_per_layer": 200,
        "fiber_routes_per_cut": None,
        "no_perimeters": False,
        "no_infill": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def require_in_order(text: str, needles: list[str]) -> None:
    cursor = -1
    for needle in needles:
        index = text.find(needle, cursor + 1)
        if index < 0:
            raise SystemExit(f"Missing expected G-code fragment: {needle}")
        cursor = index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keep-gcode", type=Path, help="Optional path to keep the generated fixture.")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmpdir:
        fixture = Path(tmpdir) / "pocket_fixture.gcode"
        fixture.write_text(SYNTHETIC_GCODE, encoding="utf-8")
        if args.keep_gcode:
            args.keep_gcode.parent.mkdir(parents=True, exist_ok=True)
            args.keep_gcode.write_text(SYNTHETIC_GCODE, encoding="utf-8")

        parsed = planner.parse_gcode(fixture)
        cfg = planner.planner_config(
            parsed,
            SimpleNamespace(
                angles="0,90",
                fiber_reinforcement_mode=None,
                fiber_generate_perimeters=None,
                fiber_generate_infill=None,
                fiber_infill_pattern=None,
                fiber_infill_source="generated-ribs",
                spacing=10.0,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=1.0,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        routes, skipped = planner.plan_routes(parsed, cfg)

        expected_pattern_angles = {
            "rhombic": {45, 135},
            "isogrid": {0, 60, 120},
            "anisogrid": {0, 45, 135},
            "tetragrid": {0, 45, 90, 135},
        }
        pattern_polygon = Polygon([(0, 0), (120, 0), (120, 120), (0, 120)])
        pattern_layer = planner.LayerGeometry(index=0, z=0.2, height=0.2)
        solid_layer_0_cfg = planner.PlannerConfig(
            pattern="solid",
            angles=planner.angles_for_pattern("solid", None),
            infill_spacing=40.0,
            min_route_length=1.0,
        )
        solid_layer_1_cfg = planner.PlannerConfig(
            pattern="solid",
            angles=planner.angles_for_pattern("solid", None),
            infill_spacing=40.0,
            min_route_length=1.0,
        )
        solid_layer_0_angles = {int(round(route.angle or 0.0)) for route in planner.clipped_infill_routes(pattern_layer, pattern_polygon, solid_layer_0_cfg)}
        solid_layer_1_angles = {
            int(round(route.angle or 0.0))
            for route in planner.clipped_infill_routes(
                planner.LayerGeometry(index=1, z=0.4, height=0.2),
                pattern_polygon,
                solid_layer_1_cfg,
            )
        }
        if solid_layer_0_angles != {0} or solid_layer_1_angles != {90}:
            raise SystemExit(f"Solid generated-rib pattern should alternate single-family layers: {solid_layer_0_angles}, {solid_layer_1_angles}")
        for pattern_name, expected_angles in expected_pattern_angles.items():
            pattern_cfg = planner.PlannerConfig(
                pattern=pattern_name,
                angles=planner.angles_for_pattern(pattern_name, None),
                infill_spacing=40.0,
                min_route_length=1.0,
            )
            pattern_routes = planner.clipped_infill_routes(pattern_layer, pattern_polygon, pattern_cfg)
            got_angles = {int(round(route.angle or 0.0)) for route in pattern_routes}
            if got_angles != expected_angles:
                raise SystemExit(f"{pattern_name} generated-rib angles collapsed: expected {expected_angles}, got {got_angles}")

        density_angle_cfg = planner.planner_config(
            parsed,
            default_planner_args(
                angles="30,120",
                density=25.0,
                line_width=1.0,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="0",
                fiber_generate_infill="1",
                fiber_infill_pattern="tetragrid",
                fiber_infill_source="generated-ribs",
                layer_step=1,
                min_route_length=1.0,
                max_routes_per_layer=200,
            ),
        )
        if abs(density_angle_cfg.infill_spacing - 4.0) > 0.001:
            raise SystemExit(f"Fiber density did not derive expected 4.0 mm spacing: {density_angle_cfg.infill_spacing}")
        if density_angle_cfg.angles != [30.0, 120.0]:
            raise SystemExit(f"Fiber angle override was not preserved: {density_angle_cfg.angles}")
        density_angle_routes, _ = planner.plan_routes(parsed, density_angle_cfg)
        density_angle_got = {
            int(round(route.angle or 0.0))
            for route in density_angle_routes
            if route.kind == "infill_chord"
        }
        if density_angle_got != {30, 120}:
            raise SystemExit(f"Generated ribs did not use explicit fiber angles: {density_angle_got}")

        seam_cfg = planner.planner_config(
            parsed,
            default_planner_args(
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_seam_position="aligned",
                fiber_seam_angle=90.0,
                min_route_length=1.0,
            ),
        )
        seam_routes, _ = planner.plan_routes(parsed, seam_cfg)
        seam_closed_routes = [route for route in seam_routes if planner.path_is_closed(route.points)]
        if not seam_closed_routes:
            raise SystemExit("No closed route available for fiber seam placement smoke.")
        seam_route = seam_closed_routes[0]
        seam_center = planner.route_spatial_center(seam_route.points)
        if seam_center is None or seam_route.points[0][1] < seam_center[1]:
            raise SystemExit(f"Aligned fiber seam did not rotate route toward 90 degrees: start={seam_route.points[0]}, center={seam_center}")
        if "fiber_seam_aligned" not in seam_route.warnings:
            raise SystemExit(f"Aligned fiber seam route missing warning marker: {seam_route.warnings}")

        short_pocket_fixture = Path(tmpdir) / "short_pocket_fixture.gcode"
        short_pocket_fixture.write_text(SYNTHETIC_SHORT_POCKET_GCODE, encoding="utf-8")
        short_pocket_parsed = planner.parse_gcode(short_pocket_fixture)
        short_pocket_cfg = planner.planner_config(
            short_pocket_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        short_pocket_routes, short_pocket_skipped = planner.plan_routes(short_pocket_parsed, short_pocket_cfg)

        too_short_cut_window_fixture = Path(tmpdir) / "too_short_cut_window_fixture.gcode"
        too_short_cut_window_fixture.write_text(SYNTHETIC_TOO_SHORT_CUT_WINDOW_GCODE, encoding="utf-8")
        too_short_cut_window_parsed = planner.parse_gcode(too_short_cut_window_fixture)
        too_short_cut_window_cfg = planner.planner_config(
            too_short_cut_window_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        too_short_cut_window_cfg.hole_reinforcement_routes_per_layer = 0
        too_short_cut_window_routes, too_short_cut_window_skipped = planner.plan_routes(
            too_short_cut_window_parsed,
            too_short_cut_window_cfg,
        )

        close_hole_fixture = Path(tmpdir) / "close_hole_cluster_fixture.gcode"
        close_hole_fixture.write_text(synthetic_close_hole_cluster_gcode(), encoding="utf-8")
        close_hole_parsed = planner.parse_gcode(close_hole_fixture)
        close_hole_cfg = planner.planner_config(
            close_hole_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        close_hole_routes, close_hole_skipped = planner.plan_routes(close_hole_parsed, close_hole_cfg)

        legal_hole_fixture = Path(tmpdir) / "legal_small_hole_fixture.gcode"
        legal_hole_fixture.write_text(synthetic_legal_small_hole_gcode(), encoding="utf-8")
        legal_hole_parsed = planner.parse_gcode(legal_hole_fixture)
        legal_hole_cfg = planner.planner_config(
            legal_hole_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        legal_hole_routes, legal_hole_skipped = planner.plan_routes(legal_hole_parsed, legal_hole_cfg)

        tiny_hole_fixture = Path(tmpdir) / "isolated_tiny_hole_fixture.gcode"
        tiny_hole_fixture.write_text(synthetic_isolated_tiny_hole_gcode(), encoding="utf-8")
        tiny_hole_parsed = planner.parse_gcode(tiny_hole_fixture)
        tiny_hole_cfg = planner.planner_config(
            tiny_hole_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        tiny_hole_routes, tiny_hole_skipped = planner.plan_routes(tiny_hole_parsed, tiny_hole_cfg)

        local_cluster_fixture = Path(tmpdir) / "local_hole_cluster_fixture.gcode"
        local_cluster_fixture.write_text(synthetic_local_hole_cluster_gcode(), encoding="utf-8")
        local_cluster_parsed = planner.parse_gcode(local_cluster_fixture)
        local_cluster_cfg = planner.planner_config(
            local_cluster_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        local_cluster_routes, local_cluster_skipped = planner.plan_routes(local_cluster_parsed, local_cluster_cfg)

        internal_void_fixture = Path(tmpdir) / "internal_void_stitch_gear_fixture.gcode"
        internal_void_fixture.write_text(synthetic_internal_void_stitch_gear_gcode(), encoding="utf-8")
        internal_void_parsed = planner.parse_gcode(internal_void_fixture)
        internal_void_cfg = planner.planner_config(
            internal_void_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        internal_void_cfg.perimeter_routes_per_layer = 0
        internal_void_routes, internal_void_skipped = planner.plan_routes(internal_void_parsed, internal_void_cfg)

        alternating_fixture = Path(tmpdir) / "alternating_hole_family_fixture.gcode"
        alternating_fixture.write_text(synthetic_alternating_hole_family_gcode(), encoding="utf-8")
        alternating_parsed = planner.parse_gcode(alternating_fixture)
        alternating_cfg = planner.planner_config(
            alternating_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="medium",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=2,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        alternating_cfg.perimeter_routes_per_layer = 0
        alternating_cfg.hole_reinforcement_routes_per_layer = 3
        alternating_routes, alternating_skipped = planner.plan_routes(alternating_parsed, alternating_cfg)

        alternating_perimeter_cfg = planner.planner_config(
            alternating_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="medium",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=2,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        alternating_perimeter_cfg.perimeter_routes_per_layer = 3
        alternating_perimeter_cfg.hole_reinforcement_routes_per_layer = 0
        alternating_perimeter_routes, alternating_perimeter_skipped = planner.plan_routes(
            alternating_parsed,
            alternating_perimeter_cfg,
        )

        radial_fixture = Path(tmpdir) / "radial_small_gear_hole_fixture.gcode"
        radial_fixture.write_text(synthetic_radial_small_gear_hole_gcode(), encoding="utf-8")
        radial_parsed = planner.parse_gcode(radial_fixture)
        radial_cfg = planner.planner_config(
            radial_parsed,
            SimpleNamespace(
                angles=None,
                fiber_reinforcement_mode="medium",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
                fiber_infill_pattern=None,
                fiber_infill_source=None,
                spacing=None,
                layer_step=1,
                fiber_start_layer=None,
                min_route_length=None,
                line_width=None,
                perimeter_inset=None,
                infill_inset=None,
                fiber_print_speed=None,
                fiber_start_speed=None,
                max_routes_per_layer=200,
                fiber_routes_per_cut=None,
                no_perimeters=False,
                no_infill=False,
            ),
        )
        radial_cfg.perimeter_routes_per_layer = 0
        radial_cfg.hole_reinforcement_routes_per_layer = 3
        radial_routes, radial_skipped = planner.plan_routes(radial_parsed, radial_cfg)

        contract_fixture = Path(tmpdir) / "fiberseek_contract_fixture.gcode"
        contract_fixture.write_text(synthetic_fiberseek_contract_gcode(), encoding="utf-8")
        contract_parsed = planner.parse_gcode(contract_fixture)
        contract_cfg = planner.planner_config(
            contract_parsed,
            default_planner_args(
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
            ),
        )
        contract_routes, contract_skipped = planner.plan_routes(contract_parsed, contract_cfg)
        contract_merged = planner.emit_append_after_layer(contract_parsed, contract_routes, contract_cfg)

        fan_schedule_fixture = Path(tmpdir) / "fiberseek_fan_schedule_fixture.gcode"
        fan_schedule_fixture.write_text(synthetic_fan_schedule_gcode(), encoding="utf-8")
        fan_schedule_parsed = planner.parse_gcode(fan_schedule_fixture)
        fan_schedule_cfg = planner.planner_config(
            fan_schedule_parsed,
            default_planner_args(
                fiber_reinforcement_mode="heavy",
                fiber_generate_perimeters="1",
                fiber_generate_infill="0",
            ),
        )
        fan_schedule_routes, fan_schedule_skipped = planner.plan_routes(fan_schedule_parsed, fan_schedule_cfg)
        fan_schedule_merged = planner.emit_append_after_layer(
            fan_schedule_parsed,
            fan_schedule_routes,
            fan_schedule_cfg,
        )

        layup_fixture = Path(tmpdir) / "layup_payload_fixture.gcode"
        layup_fixture.write_text(synthetic_layup_payload_gcode(), encoding="utf-8")
        layup_parsed = planner.parse_gcode(layup_fixture)
        layup_cfg = planner.planner_config(layup_parsed, default_planner_args())
        layup_routes, layup_skipped = planner.plan_routes(layup_parsed, layup_cfg)

        layup_ui_fixture = Path(tmpdir) / "layup_ui_fixture.gcode"
        layup_ui_fixture.write_text(synthetic_layup_ui_gcode(), encoding="utf-8")
        layup_ui_parsed = planner.parse_gcode(layup_ui_fixture)
        layup_ui_cfg = planner.planner_config(layup_ui_parsed, default_planner_args())
        layup_ui_routes, layup_ui_skipped = planner.plan_routes(layup_ui_parsed, layup_ui_cfg)

    pocket = Polygon([(35, 35), (65, 35), (65, 65), (35, 65)])
    infill_routes = [route for route in routes if route.kind == "infill_chord"]
    if not infill_routes:
        raise SystemExit("No infill routes were generated for the pocket fixture.")

    crossings = [
        route
        for route in infill_routes
        if LineString(route.points).intersection(pocket).length > 1e-6
    ]
    if crossings:
        raise SystemExit(f"{len(crossings)} fiber infill route(s) crossed the pocket void.")

    perimeter_sources = {
        route.source_role
        for route in routes
        if "perimeter" in route.kind or route.source_role in {"Outer wall", "Inner wall"}
    }
    if "Inner wall" not in perimeter_sources:
        raise SystemExit("No continuous-fiber perimeter route was generated around the pocket wall.")

    if len(layup_cfg.layup_bands) != 2 or layup_cfg.layup_payload_warnings:
        raise SystemExit(f"Layup payload was not parsed cleanly: bands={layup_cfg.layup_bands} warnings={layup_cfg.layup_payload_warnings}")
    layup_layers = {route.layer_index for route in layup_routes}
    if layup_layers != {1}:
        raise SystemExit(f"Layup payload should disable layer 0 and reinforce layer 1 only: {layup_layers} skipped={layup_skipped}")
    layup_angles = {int(round(route.angle or 0.0)) for route in layup_routes if route.kind == "infill_chord"}
    if layup_angles != {0, 45, 90, 135}:
        raise SystemExit(f"Layup Tetragrid band did not generate all four angle families: {layup_angles}")
    if layup_skipped.get("layers_skipped_by_layup_band") != 1:
        raise SystemExit(f"Layup disabled layer was not tracked: {layup_skipped}")
    if not all(any(warning == "layup_band_tetra_layer" for warning in route.warnings) for route in layup_routes):
        raise SystemExit("Layup routes did not carry the band warning tag.")

    if len(layup_ui_cfg.layup_bands) != 2:
        raise SystemExit(f"Serialized layup payload did not create two bands: {layup_ui_cfg.layup_bands}")
    layup_ui_by_layer: dict[int, list[planner.FiberRoute]] = {}
    for route in layup_ui_routes:
        layup_ui_by_layer.setdefault(route.layer_index, []).append(route)
    if sorted(layup_ui_by_layer) != [0, 1]:
        raise SystemExit(f"Serialized layup bands should route both fixture layers: {layup_ui_by_layer} skipped={layup_ui_skipped}")
    if not all(any(warning == "layup_band_ui_shell" for warning in route.warnings) for route in layup_ui_by_layer[0]):
        raise SystemExit("Serialized layup band 1 did not tag layer 0 routes.")
    if not all(any(warning == "layup_band_ui_core" for warning in route.warnings) for route in layup_ui_by_layer[1]):
        raise SystemExit("Serialized layup band 2 did not tag layer 1 routes.")
    if not any("perimeter" in route.kind for route in layup_ui_by_layer[0]):
        raise SystemExit("Serialized layup band 1 should have perimeter routes.")
    if any("perimeter" in route.kind for route in layup_ui_by_layer[1]):
        raise SystemExit("Serialized layup band 2 should disable perimeter routes.")
    ui_core_angles = {int(round(route.angle or 0.0)) for route in layup_ui_by_layer[1] if route.kind == "infill_chord"}
    if ui_core_angles != {0, 45, 90, 135}:
        raise SystemExit(f"Serialized layup band 2 did not select Tetragrid generated ribs: {ui_core_angles}")

    minimum_pocket_routes = [
        route
        for route in short_pocket_routes
        if route.kind == "perimeter_trace" and route.source_role == "Inner wall"
    ]
    if len(minimum_pocket_routes) != 2:
        raise SystemExit(f"Expected two minimum pocket perimeter routes, got {len(minimum_pocket_routes)}.")
    if any(route.length + 1e-6 < planner.hardware_min_route_length(short_pocket_cfg) for route in minimum_pocket_routes):
        raise SystemExit("A minimum pocket route did not satisfy the 55 mm route floor.")
    if any(route.length + 1e-6 < planner.standalone_cuttable_min_route_length(short_pocket_cfg) for route in minimum_pocket_routes):
        raise SystemExit("A minimum pocket route did not satisfy the standalone cut-window route floor.")
    if any(route.length >= 90.0 for route in minimum_pocket_routes):
        raise SystemExit("Minimum pocket fixture no longer proves the old 90 mm floor was removed.")
    if short_pocket_skipped.get("short_perimeter_stitched_routes") != 0:
        raise SystemExit(f"Minimum pocket routes should not require stitching at the 55 mm floor: {short_pocket_skipped}")
    if abs(short_pocket_cfg.cut_distance - 54.8) > 1e-6:
        raise SystemExit(f"Effective cut distance should follow the emitted cut macro: {short_pocket_cfg.cut_distance}")
    if abs(planner.standalone_cuttable_min_route_length(short_pocket_cfg) - 64.8) > 1e-6:
        raise SystemExit(
            f"Unexpected standalone cut-window route floor: "
            f"{planner.standalone_cuttable_min_route_length(short_pocket_cfg)}"
        )

    too_short_cut_window_floor = planner.standalone_cuttable_min_route_length(too_short_cut_window_cfg)
    leaked_cut_window_routes = [
        route
        for route in too_short_cut_window_routes
        if route.length + 1e-6 < too_short_cut_window_floor and route.length + 1e-6 >= planner.hardware_min_route_length(too_short_cut_window_cfg)
    ]
    if leaked_cut_window_routes:
        raise SystemExit(f"Route below the cut-window floor should have been rejected: {leaked_cut_window_routes}")
    extended_cut_window_routes = [
        route
        for route in too_short_cut_window_routes
        if any("cut_window_extended_closed_route" in warning for warning in route.warnings)
    ]
    if not extended_cut_window_routes:
        raise SystemExit(
            "Expected a closed route below the cut-window floor to be extended instead of dropped: "
            f"routes={too_short_cut_window_routes} skipped={too_short_cut_window_skipped}"
        )

    cluster_routes = [route for route in close_hole_routes if route.kind == "hole_cluster_reinforcement_loop"]
    if len(cluster_routes) > 1:
        raise SystemExit(f"Tiny close-hole cluster generated too many connecting halo routes: {len(cluster_routes)}.")
    if cluster_routes:
        cluster_route = cluster_routes[0]
        if "local_hole_cluster_halo" not in cluster_route.warnings:
            raise SystemExit(f"Tiny close-hole cluster used an unsafe halo path: {cluster_route.warnings}")
        xs = [point[0] for point in cluster_route.points]
        ys = [point[1] for point in cluster_route.points]
        if max(max(xs) - min(xs), max(ys) - min(ys)) > 42.0:
            raise SystemExit("Tiny close-hole cluster route grew too large and risks connecting unrelated features.")
    impossible_hole_routes = [route for route in close_hole_routes if route.kind == "hole_reinforcement_loop"]
    if impossible_hole_routes:
        raise SystemExit(f"Tiny holes below bend radius incorrectly generated fiber routes: {len(impossible_hole_routes)}.")

    legal_hole_routes = [route for route in legal_hole_routes if route.kind == "hole_reinforcement_loop"]
    if len(legal_hole_routes) != 1:
        raise SystemExit(f"Expected one legal small-hole reinforcement route, got {len(legal_hole_routes)}.")
    legal_hole_route = legal_hole_routes[0]
    if legal_hole_route.length + 1e-6 < planner.hardware_min_route_length(legal_hole_cfg):
        raise SystemExit("Legal small-hole route did not satisfy the 55 mm route minimum.")
    if any(warning.startswith("hole_reinforcement_") and warning.endswith("x_lap") for warning in legal_hole_route.warnings):
        raise SystemExit(f"Legal small-hole route should not require multi-lap routing at the 55 mm floor: {legal_hole_route.warnings}")
    if legal_hole_skipped.get("hole_reinforcement_routes") != 1:
        raise SystemExit(f"Legal small-hole route was not reported in skipped summary: {legal_hole_skipped}")

    tiny_hole_routes = [route for route in tiny_hole_routes if route.kind == "hole_reinforcement_loop"]
    if len(tiny_hole_routes) != 1:
        raise SystemExit(f"Expected one isolated tiny-hole expanded orbit, got {len(tiny_hole_routes)}.")
    tiny_hole_route = tiny_hole_routes[0]
    if "expanded_hole_orbit" not in tiny_hole_route.warnings:
        raise SystemExit(f"Tiny hole route did not use the expanded orbit path: {tiny_hole_route.warnings}")
    if tiny_hole_route.length + 1e-6 < planner.hardware_min_route_length(tiny_hole_cfg):
        raise SystemExit("Tiny hole expanded orbit did not satisfy the 55 mm route minimum.")

    local_cluster_routes = [route for route in local_cluster_routes if route.kind == "hole_cluster_reinforcement_loop"]
    unsafe_local_cluster_routes = [
        route
        for route in local_cluster_routes
        if "local_hole_cluster_halo" in route.warnings
    ]
    if unsafe_local_cluster_routes:
        raise SystemExit(f"Local cluster halo must stay disabled in production planning, got {len(unsafe_local_cluster_routes)}.")
    unexpected_local_cluster_routes = [
        route
        for route in local_cluster_routes
        if "internal_void_stitch" not in route.warnings
    ]
    if unexpected_local_cluster_routes:
        raise SystemExit(f"Local cluster routes must use internal void stitching: {unexpected_local_cluster_routes}")

    internal_void_stitch_routes = [
        route
        for route in internal_void_routes
        if route.kind == "hole_cluster_reinforcement_loop" and "internal_void_stitch" in route.warnings
    ]
    if not internal_void_stitch_routes:
        raise SystemExit(f"Internal void stitch fixture generated no stitch routes: {internal_void_skipped}")
    unsafe_internal_void_routes = [
        route
        for route in internal_void_routes
        if "local_hole_cluster_halo" in route.warnings
    ]
    if unsafe_internal_void_routes:
        raise SystemExit(f"Internal void fixture emitted unsafe halo routes: {unsafe_internal_void_routes}")
    internal_void_by_layer: dict[int, list[planner.FiberRoute]] = {}
    for route in internal_void_stitch_routes:
        internal_void_by_layer.setdefault(route.layer_index, []).append(route)
        if route.length + 1e-6 < planner.hardware_min_route_length(internal_void_cfg):
            raise SystemExit("Internal void stitch route did not satisfy the 55 mm route minimum.")
    if sorted(internal_void_by_layer) != [0, 1, 2, 3, 4, 5]:
        raise SystemExit(f"Internal void stitch fixture should route all six layers: {sorted(internal_void_by_layer)}")
    internal_void_sectors = {
        warning
        for route in internal_void_stitch_routes
        for warning in route.warnings
        if warning.startswith("internal_void_sector_")
    }
    if len(internal_void_sectors) < 6:
        raise SystemExit(
            f"Internal void stitching did not cover all satellite sectors: "
            f"{sorted(internal_void_sectors)} skipped={internal_void_skipped}"
        )
    if internal_void_skipped.get("internal_void_stitch_routes") != len(internal_void_stitch_routes):
        raise SystemExit(f"Internal void stitch route count was not tracked: {internal_void_skipped}")

    alternating_by_layer: dict[int, list[planner.FiberRoute]] = {}
    for route in alternating_routes:
        if route.kind == "hole_reinforcement_loop":
            alternating_by_layer.setdefault(route.layer_index, []).append(route)
    if sorted(alternating_by_layer) != [0, 2]:
        raise SystemExit(f"Medium alternating fixture should route only layers 0 and 2: {sorted(alternating_by_layer)}")
    layer0_centers = [route_center(route) for route in alternating_by_layer[0]]
    layer2_centers = [route_center(route) for route in alternating_by_layer[2]]
    if len(layer0_centers) != 3 or len(layer2_centers) != 3:
        raise SystemExit(f"Alternating fixture expected three routes per fiber layer: {alternating_by_layer}")

    def has_center(centers: list[tuple[float, float]]) -> bool:
        return any(abs(cx - 50.0) <= 1.0 and abs(cy - 50.0) <= 1.0 for cx, cy in centers)

    def matched_satellite_indexes(
        centers: list[tuple[float, float]],
        expected: list[tuple[float, float]],
    ) -> set[int]:
        matched: set[int] = set()
        for cx, cy in centers:
            if abs(cx - 50.0) <= 1.0 and abs(cy - 50.0) <= 1.0:
                continue
            nearest = min(
                range(len(expected)),
                key=lambda index: (cx - expected[index][0]) ** 2 + (cy - expected[index][1]) ** 2,
            )
            if (cx - expected[nearest][0]) ** 2 + (cy - expected[nearest][1]) ** 2 <= 4.0:
                matched.add(nearest)
        return matched

    if not has_center(layer0_centers) or not has_center(layer2_centers):
        raise SystemExit(f"Alternating fixture did not keep the center hole reinforced: {layer0_centers}, {layer2_centers}")
    alternating_satellite_centers = [(25.0, 80.0), (75.0, 80.0), (25.0, 20.0), (75.0, 20.0)]
    layer0_satellites = matched_satellite_indexes(layer0_centers, alternating_satellite_centers)
    layer2_satellites = matched_satellite_indexes(layer2_centers, alternating_satellite_centers)
    if len(layer0_satellites) != 2 or len(layer2_satellites) != 2 or layer0_satellites & layer2_satellites:
        raise SystemExit(f"Alternating fixture did not select complementary hole families: {layer0_centers}, {layer2_centers}")
    if len(layer0_satellites | layer2_satellites) != len(alternating_satellite_centers):
        raise SystemExit(f"Alternating fixture did not cover all satellite holes: {layer0_centers}, {layer2_centers}")
    if alternating_skipped.get("hole_reinforcement_routes") != 6:
        raise SystemExit(f"Alternating fixture route count was not tracked: {alternating_skipped}")

    alternating_perimeters_by_layer: dict[int, list[planner.FiberRoute]] = {}
    for route in alternating_perimeter_routes:
        if route.kind == "perimeter_trace":
            alternating_perimeters_by_layer.setdefault(route.layer_index, []).append(route)
    if sorted(alternating_perimeters_by_layer) != [0, 2]:
        raise SystemExit(
            f"Medium perimeter alternating fixture should route only layers 0 and 2: "
            f"{sorted(alternating_perimeters_by_layer)}"
        )
    perimeter_layer0_centers = [route_center(route) for route in alternating_perimeters_by_layer[0]]
    perimeter_layer2_centers = [route_center(route) for route in alternating_perimeters_by_layer[2]]
    if len(perimeter_layer0_centers) != 3 or len(perimeter_layer2_centers) != 3:
        raise SystemExit(
            f"Alternating perimeter fixture expected three perimeter traces per fiber layer: "
            f"{alternating_perimeters_by_layer}"
        )
    if not has_center(perimeter_layer0_centers) or not has_center(perimeter_layer2_centers):
        raise SystemExit(
            f"Alternating perimeter fixture did not keep the center trace reinforced: "
            f"{perimeter_layer0_centers}, {perimeter_layer2_centers}"
        )
    perimeter_layer0_satellites = matched_satellite_indexes(perimeter_layer0_centers, alternating_satellite_centers)
    perimeter_layer2_satellites = matched_satellite_indexes(perimeter_layer2_centers, alternating_satellite_centers)
    if (
        len(perimeter_layer0_satellites) != 2
        or len(perimeter_layer2_satellites) != 2
        or perimeter_layer0_satellites & perimeter_layer2_satellites
    ):
        raise SystemExit(
            f"Alternating perimeter fixture did not select complementary hole families: "
            f"{perimeter_layer0_centers}, {perimeter_layer2_centers}"
        )
    if len(perimeter_layer0_satellites | perimeter_layer2_satellites) != len(alternating_satellite_centers):
        raise SystemExit(
            f"Alternating perimeter fixture did not cover all satellite holes: "
            f"{perimeter_layer0_centers}, {perimeter_layer2_centers}"
        )
    if alternating_perimeter_skipped.get("hole_reinforcement_routes") != 0:
        raise SystemExit(f"Perimeter-only alternating fixture unexpectedly emitted hole routes: {alternating_perimeter_skipped}")

    radial_by_layer: dict[int, list[planner.FiberRoute]] = {}
    for route in radial_routes:
        if route.kind == "hole_reinforcement_loop":
            radial_by_layer.setdefault(route.layer_index, []).append(route)
    if sorted(radial_by_layer) != [0, 1, 2]:
        raise SystemExit(f"Radial small-gear fixture should route three fiber layers: {sorted(radial_by_layer)}")
    radial_satellite_centers = [
        (80.0, 50.0),
        (65.0, 75.981),
        (35.0, 75.981),
        (20.0, 50.0),
        (35.0, 24.019),
        (65.0, 24.019),
    ]
    covered_satellites: set[int] = set()
    for layer_index, layer_routes in radial_by_layer.items():
        centers = [route_center(route) for route in layer_routes]
        if len(centers) != 3:
            raise SystemExit(f"Radial layer {layer_index} expected center plus two satellites: {centers}")
        if not has_center(centers):
            raise SystemExit(f"Radial layer {layer_index} did not keep the center hole reinforced: {centers}")
        satellite_centers = [(cx, cy) for cx, cy in centers if abs(cx - 50.0) > 1.0 or abs(cy - 50.0) > 1.0]
        if len(satellite_centers) != 2:
            raise SystemExit(f"Radial layer {layer_index} did not select exactly two satellite holes: {centers}")
        covered_satellites.update(matched_satellite_indexes(centers, radial_satellite_centers))
    if len(covered_satellites) != len(radial_satellite_centers):
        raise SystemExit(
            f"Radial small-gear alternation did not cover all satellite holes: "
            f"covered={sorted(covered_satellites)} skipped={radial_skipped}"
        )

    if not contract_routes:
        raise SystemExit(f"FibreSeek contract fixture did not generate routes: {contract_skipped}")
    if not fan_schedule_routes:
        raise SystemExit(f"FibreSeek fan schedule fixture did not generate routes: {fan_schedule_skipped}")
    contract_lines = contract_merged.splitlines()
    exact_commands = {line.strip() for line in contract_lines if line.strip() and not line.strip().startswith(";")}
    if "T0" in exact_commands:
        raise SystemExit("FibreSeek contract left a bare initial T0 in the merged G-code.")
    if contract_merged.count("; ORCA_CODEX_FIBER_PRIME_START") != 1:
        raise SystemExit("FibreSeek contract should emit exactly one fiber prime start marker.")
    if contract_merged.count("; ORCA_CODEX_FIBER_PRIME_END") != 1:
        raise SystemExit("FibreSeek contract should emit exactly one fiber prime end marker.")
    for required in (
        "SET_PRINT_STATS_INFO TOTAL_LAYER=2",
        "SET_PRINT_STATS_INFO CURRENT_LAYER=1",
        "SET_PRINT_STATS_INFO CURRENT_LAYER=2",
        "SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY=1",
        "M106 P3 S0",
        "M106 P5 S0",
        "M104 S275 T0",
        "M140 S80",
        "M141 S35",
        "M191 S35",
        "T1 ; switch extruder type to:PLASTIC",
        "M109 S260 T1",
        "MOVE_TO_BRUSH_STATION",
        "CLEAN_NOZZLE",
        "MOVE_OUT_BRUSH_STATION",
        "T0 R ; switch extruder type to:FIBER",
        "M109 S275 T0",
        "M104 S0 T1",
        "M104 S0 T0",
        "M106 P2 S0",
        "M140 S0",
        "M141 S0",
    ):
        if required not in contract_merged:
            raise SystemExit(f"FibreSeek contract missing required command: {required}")

    require_in_order(
        contract_merged,
        [
            "; ORCA_CODEX_FIBERSEEK_MACHINE_CONTRACT_START",
            "SET_PRINT_STATS_INFO TOTAL_LAYER=2",
            "M141 S35",
            "M104 S260 T1 ; set plastic nozzle temperature",
            "M190 S80",
            "M191 S35",
            "; ORCA_CODEX_FIBERSEEK_INITIAL_PLASTIC_TOOL",
            "T1 ; switch extruder type to:PLASTIC",
            ";LAYER_CHANGE",
            "SET_PRINT_STATS_INFO CURRENT_LAYER=1",
            "; ORCA_CODEX_NATIVE_FIBER_PLANNER_START",
            "MOVE_TO_BRUSH_STATION",
            "T0 R ; switch extruder type to:FIBER",
            "; ORCA_CODEX_FIBER_PRIME_START",
            "M1001 L90",
            "M2800",
            ";CUT DISTANCE 54.8",
            "M1002",
            "; ORCA_CODEX_FIBER_PRIME_END",
            "; ORCA_CODEX_FIBER_LAYER",
            "T1 ; switch extruder type to:PLASTIC",
            "; ORCA_CODEX_NATIVE_FIBER_PLANNER_END",
            "; filament end gcode",
            "; ORCA_CODEX_FIBERSEEK_MACHINE_SHUTDOWN_START",
            "M104 S0 T1",
            "M141 S0",
            "; EXECUTABLE_BLOCK_END",
        ],
    )
    require_in_order(
        fan_schedule_merged,
        [
            "SET_PRINT_STATS_INFO CURRENT_LAYER=1",
            "M106 P3 S0",
            "M106 P5 S0",
            "SET_PRINT_STATS_INFO CURRENT_LAYER=5",
            "M106 P3 S255",
            "M106 P5 S255",
        ],
    )
    executable_end_index = contract_merged.find("; EXECUTABLE_BLOCK_END")
    if executable_end_index < 0:
        raise SystemExit("FibreSeek contract fixture lost EXECUTABLE_BLOCK_END.")
    if contract_merged.find("; ORCA_CODEX_FIBER_LAYER", executable_end_index) >= 0:
        raise SystemExit("FibreSeek fiber layer was emitted after EXECUTABLE_BLOCK_END.")
    if contract_merged.find("M104 S0 T1") > executable_end_index:
        raise SystemExit("FibreSeek shutdown was emitted after EXECUTABLE_BLOCK_END.")

    print(
        "native fiber planner smoke passed: "
        f"{len(routes)} route(s), {len(infill_routes)} infill route(s), "
        f"minimum_pocket_lengths={[round(route.length, 2) for route in minimum_pocket_routes]}, "
        f"cut_window_floor={planner.standalone_cuttable_min_route_length(short_pocket_cfg):.2f}, "
        f"cut_window_extended_lengths={[round(route.length, 2) for route in extended_cut_window_routes]}, "
        f"legal_small_hole_length={legal_hole_route.length:.2f}, "
        f"tiny_orbit_length={tiny_hole_route.length:.2f}, "
        f"safe_local_cluster_stitches={len(local_cluster_routes)}, "
        f"internal_void_stitches={len(internal_void_stitch_routes)}, "
        f"internal_void_sectors={len(internal_void_sectors)}, "
        f"alternating_layers={sorted(alternating_by_layer)}, "
        f"alternating_perimeter_layers={sorted(alternating_perimeters_by_layer)}, "
        f"radial_satellites={len(covered_satellites)}, "
        f"contract_routes={len(contract_routes)}, skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
