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

    print(
        "native fiber planner smoke passed: "
        f"{len(routes)} route(s), {len(infill_routes)} infill route(s), "
        f"stitched_short_pocket_length={stitched_route.length:.2f}, skipped={skipped}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
