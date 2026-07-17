#!/usr/bin/env python3
"""Guard the TinManX1 Wave Overhang source-port scaffold."""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
WAVE_REVISION = "379c18470f251b3839db12726a2c3a4e4135bfb8"
WAVE_SOURCE_URL = "https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs"

WAVE_FILES = [
    "src/libslic3r/WaveOverhangs/WaveOverhangs.cpp",
    "src/libslic3r/WaveOverhangs/WaveOverhangs.hpp",
    "src/libslic3r/WaveOverhangs/IGenerator.hpp",
    "src/libslic3r/WaveOverhangs/AndersonsGenerator.cpp",
    "src/libslic3r/WaveOverhangs/AndersonsGenerator.hpp",
    "src/libslic3r/WaveOverhangs/KaiserGenerator.cpp",
    "src/libslic3r/WaveOverhangs/KaiserGenerator.hpp",
]

WAVE_OPTIONS = [
    "wave_overhangs",
    "wave_overhangs_instead_of_bridges",
    "wave_overhang_outer_perimeters",
    "wave_overhang_perimeter_overlap",
    "wave_overhang_minimum_width",
    "wave_overhang_pattern",
    "wave_overhang_line_spacing",
    "wave_overhang_flow_mm3_per_mm",
    "wave_overhang_print_speed",
    "wave_overhang_perimeter_speed",
    "wave_overhang_travel_speed",
    "wave_overhang_fan_speed",
    "wave_overhang_floor_layers",
    "wave_overhang_floor_use_hilbert",
    "wave_overhang_floor_hilbert_layers",
    "wave_overhang_floor_hilbert_density",
    "wave_overhang_floor_print_speed",
    "wave_overhang_floor_perimeter_speed",
    "wave_overhang_floor_fan_speed",
    "wave_overhang_nozzle_temp",
    "wave_overhang_min_wave_time",
    "wave_overhang_min_layer_time",
    "wave_overhang_algorithm",
    "wave_overhang_ring_overlap",
    "wave_overhang_min_angle",
    "wave_overhang_spacing_mode",
    "wave_overhang_seam_mode",
    "wave_overhang_debug_gcode",
    "wave_overhang_min_length",
    "wave_overhang_max_iterations",
    "wave_overhang_min_new_area",
    "wave_overhang_fringe_reinforcement_max_cover_to_real",
    "wave_overhang_fringe_reinforcement_max_cover_area",
    "wave_overhang_fringe_contact_compensation_max_over_cap",
    "wave_overhang_corner_taper_enable",
    "wave_overhang_line_spacing_corner",
    "wave_overhang_corner_taper_distance",
    "wave_overhang_corner_angle_threshold",
    "wave_overhang_end_retract_length",
    "support_remaining_areas_after_wave_overhangs",
]

ENUMS = [
    "WaveOverhangAlgorithm",
    "WaveOverhangSpacingMode",
    "WaveOverhangSeamMode",
    "WaveOverhangPattern",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace")


def option_block(cpp: str, option: str) -> str:
    marker = f'this->add("{option}",'
    start = cpp.find(marker)
    require(start >= 0, f"PrintConfig.cpp missing add block for {option}")
    next_start = cpp.find('this->add("', start + len(marker))
    return cpp[start: next_start if next_start >= 0 else len(cpp)]


def main() -> int:
    cmake = read("src/libslic3r/CMakeLists.txt")
    hpp = read("src/libslic3r/PrintConfig.hpp")
    cpp = read("src/libslic3r/PrintConfig.cpp")
    tab = read("src/slic3r/GUI/Tab.cpp")
    manip = read("src/slic3r/GUI/ConfigManipulation.cpp")
    credits = read("SoftFever_doc/orcaslicer_codex_feature_attribution.md")
    extrusion = read("src/libslic3r/ExtrusionEntity.hpp")
    wave_cpp = read("src/libslic3r/WaveOverhangs/WaveOverhangs.cpp")
    kaiser_cpp = read("src/libslic3r/WaveOverhangs/KaiserGenerator.cpp")
    perim_hpp = read("src/libslic3r/PerimeterGenerator.hpp")
    perim_cpp = read("src/libslic3r/PerimeterGenerator.cpp")
    layer_hpp = read("src/libslic3r/Layer.hpp")
    layer_region_cpp = read("src/libslic3r/LayerRegion.cpp")
    support_cpp = read("src/libslic3r/Support/SupportMaterial.cpp")
    gcode_cpp = read("src/libslic3r/GCode.cpp")

    for rel in WAVE_FILES:
        require((REPO_ROOT / rel).exists(), f"missing copied source file: {rel}")
        require(rel.removeprefix("src/libslic3r/") in cmake, f"CMake missing {rel}")

    for enum in ENUMS:
        require(f"enum {enum}" in hpp or f"enum class {enum}" in hpp, f"PrintConfig.hpp missing {enum}")
        require(f"CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS({enum})" in hpp, f"PrintConfig.hpp missing enum declaration for {enum}")
        require(f"s_keys_map_{enum}" in cpp, f"PrintConfig.cpp missing enum map for {enum}")
        require(f"CONFIG_OPTION_ENUM_DEFINE_STATIC_MAPS({enum})" in cpp, f"PrintConfig.cpp missing enum map definition for {enum}")

    for option in WAVE_OPTIONS:
        hpp_pattern = re.compile(rf"\(\(\s*ConfigOption[^,]*,\s*{re.escape(option)}\s*\)\)")
        require(hpp_pattern.search(hpp) is not None, f"PrintConfig.hpp missing storage for {option}")
        require(f'this->add("{option}",' in cpp, f"PrintConfig.cpp missing definition for {option}")
        require(option in tab, f"Tab.cpp missing UI row for {option}")

    wave_block = option_block(cpp, "wave_overhangs")
    require("new ConfigOptionBool(false)" in wave_block, "wave_overhangs must stay off by default")
    require("WAVE_OVERHANG_START" in option_block(cpp, "wave_overhang_debug_gcode"), "debug marker contract missing")
    require("support_remaining_areas_after_wave_overhangs" in manip, "ConfigManipulation missing hybrid support-remainder toggle")
    require("wo_enabled" in manip and "woaAndersons" in manip and "woaKaiser" in manip, "ConfigManipulation missing wave visibility gates")
    require('add_options_page(L("Wave overhangs")' in tab, "settings page missing")

    require("bool wave_overhang = false" in extrusion, "ExtrusionPath missing Wave Overhang tag")
    require("wave_overhang(rhs.wave_overhang)" in extrusion, "ExtrusionPath constructors must copy Wave Overhang tag")
    require("this->wave_overhang = rhs.wave_overhang" in extrusion, "ExtrusionPath assignments must copy Wave Overhang tag")
    require("path.wave_overhang = true" in wave_cpp, "WaveOverhangs tag helper must mark generated paths")
    require("path.wave_overhang = true" in kaiser_cpp, "Kaiser generator must mark generated paths")

    require("out_wave_overhang_covered_polygons" in perim_hpp, "PerimeterGenerator missing Wave Overhang coverage output")
    require("apply_extra_perimeters(ExPolygons& infill_area, const ExPolygon& island_region)" in perim_hpp, "PerimeterGenerator signature must receive island geometry")
    for token in [
        "WaveOverhangs/AndersonsGenerator.hpp",
        "WaveOverhangs/KaiserGenerator.hpp",
        "generate_wave_overhang_paths",
        "clip_inner_perimeters_in_zone",
        "generate_wave_overhang_paths(wave_infill",
        "generate_extra_perimeters_over_overhangs(infill_area",
        "out_wave_overhang_covered_polygons",
    ]:
        require(token in perim_cpp, f"PerimeterGenerator.cpp missing runtime hook: {token}")
    require(perim_cpp.count("apply_extra_perimeters(infill_exp, surface.expolygon)") >= 2, "classic and Arachne perimeter flows must pass island geometry")

    require("wave_overhang_covered_polygons" in layer_hpp, "Layer missing Wave Overhang covered footprint storage")
    require("out_wave_overhang_covered_polygons" in layer_region_cpp and "wave_overhang_covered_polygons" in layer_region_cpp, "LayerRegion must forward Wave Overhang coverage to Layer")
    require("support_remaining_areas_after_wave_overhangs.value" in support_cpp, "SupportMaterial missing hybrid support gate")
    require("diff_ex(overhangs_per_layers[layer_id], layer.wave_overhang_covered_polygons)" in support_cpp, "SupportMaterial must subtract Wave Overhang covered areas")

    for token in [
        "WAVE_OVERHANG_BUILD",
        WAVE_REVISION,
        "WAVE_OVERHANG_CONFIG",
        "WAVE_OVERHANG_START",
        "WAVE_OVERHANG_END",
        "path.wave_overhang && m_config.wave_overhang_debug_gcode.value",
        "path.wave_overhang && m_config.wave_overhang_print_speed.value > 0",
    ]:
        require(token in gcode_cpp, f"GCode.cpp missing Wave Overhang debug/speed hook: {token}")

    for token in [WAVE_SOURCE_URL, WAVE_REVISION, "Janis A. Andersons", "Rieks Kaiser"]:
        require(token in credits, f"Wave source attribution missing {token}")

    print("TinManX1 Wave Overhang scaffold smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"TinManX1 Wave Overhang scaffold smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
