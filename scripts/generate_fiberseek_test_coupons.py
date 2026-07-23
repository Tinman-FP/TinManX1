#!/usr/bin/env python3
"""Generate neutral FibreSeek planner coupon models.

The coupons are intentionally simple and sanitized. They are not Rocket assets;
they are geometry probes for validating continuous-fiber route ownership,
minimum route length, hole coverage, bend behavior, and island separation.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Callable

import cadquery as cq


DEFAULT_OUTPUT = Path("work/rocket-algorithm-1.3.1.480-research/coupons")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT, help="Directory for STEP/STL coupon exports.")
    return parser.parse_args()


def export_model(name: str, model: cq.Workplane, output_dir: Path, purpose: str) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    step_path = output_dir / f"{name}.step"
    stl_path = output_dir / f"{name}.stl"
    cq.exporters.export(model, str(step_path))
    cq.exporters.export(model, str(stl_path), tolerance=0.05, angularTolerance=0.1)
    return {
        "name": name,
        "purpose": purpose,
        "step": str(step_path),
        "stl": str(stl_path),
    }


def rect_plate() -> cq.Workplane:
    return cq.Workplane("XY").box(100, 40, 6).translate((0, 0, 3))


def single_hole_plate() -> cq.Workplane:
    return cq.Workplane("XY").box(100, 60, 6).faces(">Z").workplane().hole(20).translate((0, 0, 3))


def multi_hole_plate() -> cq.Workplane:
    plate = cq.Workplane("XY").box(120, 80, 6)
    holes = [(-38, 22, 14), (0, 24, 18), (38, 22, 14), (-35, -20, 12), (0, -22, 16), (35, -20, 12)]
    wp = plate.faces(">Z").workplane()
    for x, y, diameter in holes:
        wp = wp.pushPoints([(x, y)]).hole(diameter)
    return wp.translate((0, 0, 3))


def min_length_bars() -> cq.Workplane:
    result: cq.Workplane | None = None
    lengths = [40, 55, 65, 90]
    for index, length in enumerate(lengths):
        bar = cq.Workplane("XY").box(length, 10, 5).translate((0, (index - 1.5) * 22, 0))
        result = bar if result is None else result.union(bar)
    assert result is not None
    return result.translate((0, 0, 2.5))


def bend_radius_plate() -> cq.Workplane:
    plate = cq.Workplane("XY").box(130, 90, 6)
    holes = [(-45, 0, 12), (-18, 0, 20), (16, 0, 28), (45, 0, 36)]
    wp = plate.faces(">Z").workplane()
    for x, y, diameter in holes:
        wp = wp.pushPoints([(x, y)]).hole(diameter)
    return wp.translate((0, 0, 3))


def gear_with_holes(teeth: int = 24, root_radius: float = 42, tip_radius: float = 48, height: float = 7) -> cq.Workplane:
    points: list[tuple[float, float]] = []
    for index in range(teeth * 2):
        radius = tip_radius if index % 2 == 0 else root_radius
        angle = math.tau * index / (teeth * 2)
        points.append((radius * math.cos(angle), radius * math.sin(angle)))
    gear = cq.Workplane("XY").polyline(points).close().extrude(height)
    wp = gear.faces(">Z").workplane()
    wp = wp.hole(18)
    for index in range(6):
        angle = math.tau * index / 6
        wp = wp.pushPoints([(25 * math.cos(angle), 25 * math.sin(angle))]).hole(10)
    return wp


def separate_islands() -> cq.Workplane:
    left = cq.Workplane("XY").box(45, 45, 5).translate((-35, 0, 0))
    right = cq.Workplane("XY").box(45, 45, 5).translate((35, 0, 0))
    return left.union(right).translate((0, 0, 2.5))


def main() -> int:
    args = parse_args()
    coupons: list[tuple[str, Callable[[], cq.Workplane], str]] = [
        ("coupon_01_rect_plate_100x40x6", rect_plate, "Long straight perimeter and generated rib baseline."),
        ("coupon_02_single_hole_plate_100x60x6_h20", single_hole_plate, "Single-hole perimeter ownership and hole loop coverage."),
        ("coupon_03_multi_hole_plate_120x80x6", multi_hole_plate, "Alternating-hole coverage and graph route selection."),
        ("coupon_04_min_length_bars_40_55_65_90", min_length_bars, "Cut threshold behavior across 40, 55, 65, and 90 mm islands."),
        ("coupon_05_bend_radius_hole_ladder", bend_radius_plate, "Bend-radius stress case across small to larger holes."),
        ("coupon_06_gear_with_six_holes", gear_with_holes, "Gear teeth, hole coverage, and no-crossing validation."),
        ("coupon_07_separate_islands", separate_islands, "Guard against stitching routes across separate model islands."),
    ]

    manifest = [export_model(name, builder(), args.output_dir, purpose) for name, builder, purpose in coupons]
    manifest_path = args.output_dir / "manifest.json"
    manifest_path.write_text(json.dumps({"coupons": manifest}, indent=2), encoding="utf-8")
    print(f"Wrote {len(manifest)} coupon models to {args.output_dir}")
    print(f"Manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
