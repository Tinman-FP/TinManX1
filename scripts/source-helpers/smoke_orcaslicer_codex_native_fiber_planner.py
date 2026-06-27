#!/usr/bin/env python3
"""Smoke-test the native FibreSeek planner against pocket-crossing regressions."""

from __future__ import annotations

import argparse
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
G1 X34 Y20 E5 F1800
G1 X34 Y34 E6
G1 X20 Y34 E7
G1 X20 Y20 E8
G0 X36 Y20 F9000
;TYPE:Inner wall
G1 X50 Y20 E9 F1800
G1 X50 Y34 E10
G1 X36 Y34 E11
G1 X36 Y20 E12
; fiber_generate_perimeters = 1
; fiber_generate_infill = 0
; fiber_reinforcement_mode = heavy
; fiber_minimum_perimeter_length = 55
; fiber_cut_distance = 60
; fiber_start_length = 15
; fiber_diameter = 0.25
; fiber_linear_density = 102
"""


def circular_inner_wall_gcode(cx: float, cy: float, radius: float, e_start: float, segments: int = 32) -> tuple[str, float]:
    import math

    lines = [f"G0 X{cx + radius:.3f} Y{cy:.3f} F9000", ";TYPE:Inner wall"]
    e_value = e_start
    for index in range(1, segments + 1):
        angle = 2.0 * math.pi * index / segments
        e_value += 0.12
        lines.append(f"G1 X{cx + radius * math.cos(angle):.3f} Y{cy + radius * math.sin(angle):.3f} E{e_value:.4f} F1800")
    return "\n".join(lines), e_value


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
            "; fiber_cut_distance = 60",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 8",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


def synthetic_legal_small_hole_gcode() -> str:
    block, _ = circular_inner_wall_gcode(50.0, 50.0, 11.0, 4.0, segments=64)
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
            "; fiber_cut_distance = 60",
            "; fiber_start_length = 15",
            "; fiber_min_radius = 8",
            "; fiber_diameter = 0.25",
            "; fiber_linear_density = 102",
            "",
        ]
    )


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

    stitched_routes = [route for route in short_pocket_routes if route.kind == "stitched_perimeter_trace"]
    if len(stitched_routes) != 1:
        raise SystemExit(f"Expected one stitched short-pocket perimeter route, got {len(stitched_routes)}.")
    stitched_route = stitched_routes[0]
    if stitched_route.length + 1e-6 < planner.hardware_min_route_length(short_pocket_cfg):
        raise SystemExit("Stitched short-pocket route did not satisfy the hardware minimum length.")
    if short_pocket_skipped.get("short_perimeter_stitched_routes") != 1:
        raise SystemExit(f"Short-pocket stitching was not reported in skipped summary: {short_pocket_skipped}")
    if any(route.kind == "perimeter_trace" for route in short_pocket_routes):
        raise SystemExit("A raw short pocket route passed the hardware filter without stitching.")

    cluster_routes = [route for route in close_hole_routes if route.kind == "hole_cluster_reinforcement_loop"]
    if cluster_routes:
        raise SystemExit(f"Tiny close-hole cluster incorrectly generated a connecting halo route: {len(cluster_routes)}.")
    impossible_hole_routes = [route for route in close_hole_routes if route.kind == "hole_reinforcement_loop"]
    if impossible_hole_routes:
        raise SystemExit(f"Tiny holes below bend radius incorrectly generated fiber routes: {len(impossible_hole_routes)}.")

    legal_hole_routes = [route for route in legal_hole_routes if route.kind == "hole_reinforcement_loop"]
    if len(legal_hole_routes) != 1:
        raise SystemExit(f"Expected one legal small-hole reinforcement route, got {len(legal_hole_routes)}.")
    legal_hole_route = legal_hole_routes[0]
    if legal_hole_route.length + 1e-6 < planner.hardware_min_route_length(legal_hole_cfg):
        raise SystemExit("Legal small-hole route did not satisfy the 90 mm hardware minimum.")
    if "below_min_bend_radius" in legal_hole_route.warnings:
        raise SystemExit(f"Legal small-hole route violated bend radius: {legal_hole_route.warnings}")
    if "hole_reinforcement_2x_lap" not in legal_hole_route.warnings:
        raise SystemExit(f"Legal small-hole route did not use the expected multi-lap route: {legal_hole_route.warnings}")
    if legal_hole_skipped.get("hole_reinforcement_routes") != 1:
        raise SystemExit(f"Legal small-hole route was not reported in skipped summary: {legal_hole_skipped}")

    print(
        "native fiber planner smoke passed: "
        f"{len(routes)} route(s), {len(infill_routes)} infill route(s), "
        f"stitched_short_pocket_length={stitched_route.length:.2f}, "
        f"legal_small_hole_length={legal_hole_route.length:.2f}, skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
