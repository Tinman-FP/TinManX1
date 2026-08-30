#!/usr/bin/env python3
"""Guard the TinManX1 Wave Overhang v0.4 source port and extensions."""

from __future__ import annotations

from pathlib import Path
import re
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
WAVE_TAG = "v0.4.0"
WAVE_REVISION = "f6a901d57cd128c922c81591ceae4fd0b7cc5524"
WAVE_SOURCE_URL = "https://github.com/dennisklappe/OrcaSlicer-WaveOverhangs"

WAVE_FILES = [
    "src/libslic3r/WaveOverhangs/WaveOverhangs.cpp",
    "src/libslic3r/WaveOverhangs/WaveOverhangs.hpp",
    "src/libslic3r/WaveOverhangs/IGenerator.hpp",
    "src/libslic3r/WaveOverhangs/AndersonsGenerator.cpp",
    "src/libslic3r/WaveOverhangs/AndersonsGenerator.hpp",
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
    "wave_overhang_aux_fan_speed",
    "wave_overhang_floor_layers",
    "wave_overhang_floor_use_hilbert",
    "wave_overhang_floor_hilbert_layers",
    "wave_overhang_floor_hilbert_density",
    "wave_overhang_floor_print_speed",
    "wave_overhang_floor_perimeter_speed",
    "wave_overhang_floor_speed_ramp",
    "wave_overhang_floor_fan_speed",
    "wave_overhang_floor_aux_fan_speed",
    "wave_overhang_nozzle_temp",
    "wave_overhang_min_wave_time",
    "wave_overhang_min_layer_time",
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
    "WaveOverhangSpacingMode",
    "WaveOverhangSeamMode",
    "WaveOverhangPattern",
]

RETIRED_TOKENS = [
    "WaveOverhangAlgorithm",
    "wave_overhang_algorithm",
    "wave_overhang_ring_overlap",
    "KaiserGenerator",
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


def require_tokens(text: str, tokens: list[str], context: str) -> None:
    for token in tokens:
        require(token in text, f"{context} missing: {token}")


def main() -> int:
    cmake = read("src/libslic3r/CMakeLists.txt")
    hpp = read("src/libslic3r/PrintConfig.hpp")
    cpp = read("src/libslic3r/PrintConfig.cpp")
    tab = read("src/slic3r/GUI/Tab.cpp")
    manip = read("src/slic3r/GUI/ConfigManipulation.cpp")
    credits = read("SoftFever_doc/orcaslicer_codex_feature_attribution.md")
    packaged_credits = read("resources/orcaslicer_codex/attribution/orcaslicer_codex_feature_attribution.md")
    extrusion = read("src/libslic3r/ExtrusionEntity.hpp")
    wave_cpp = read("src/libslic3r/WaveOverhangs/WaveOverhangs.cpp")
    perim_hpp = read("src/libslic3r/PerimeterGenerator.hpp")
    perim_cpp = read("src/libslic3r/PerimeterGenerator.cpp")
    layer_hpp = read("src/libslic3r/Layer.hpp")
    layer_region_cpp = read("src/libslic3r/LayerRegion.cpp")
    print_object_cpp = read("src/libslic3r/PrintObject.cpp")
    fill_cpp = read("src/libslic3r/Fill/Fill.cpp")
    support_cpp = read("src/libslic3r/Support/SupportMaterial.cpp")
    gcode_cpp = read("src/libslic3r/GCode.cpp")
    gcode_hpp = read("src/libslic3r/GCode.hpp")
    writer_cpp = read("src/libslic3r/GCodeWriter.cpp")
    writer_hpp = read("src/libslic3r/GCodeWriter.hpp")
    cooling_cpp = read("src/libslic3r/GCode/CoolingBuffer.cpp")

    for rel in WAVE_FILES:
        require((REPO_ROOT / rel).exists(), f"missing copied source file: {rel}")
        require(rel.removeprefix("src/libslic3r/") in cmake, f"CMake missing {rel}")

    for token in RETIRED_TOKENS:
        require(token not in cmake + hpp + cpp + tab + manip + perim_cpp,
                f"retired Wave Overhang token remains active: {token}")
    require(not (REPO_ROOT / "src/libslic3r/WaveOverhangs/KaiserGenerator.cpp").exists(),
            "retired Kaiser source remains")
    require(not (REPO_ROOT / "src/libslic3r/WaveOverhangs/KaiserGenerator.hpp").exists(),
            "retired Kaiser header remains")

    for enum in ENUMS:
        require(f"enum {enum}" in hpp or f"enum class {enum}" in hpp, f"PrintConfig.hpp missing {enum}")
        require(f"CONFIG_OPTION_ENUM_DECLARE_STATIC_MAPS({enum})" in hpp,
                f"PrintConfig.hpp missing enum declaration for {enum}")
        require(f"s_keys_map_{enum}" in cpp, f"PrintConfig.cpp missing enum map for {enum}")
        require(f"CONFIG_OPTION_ENUM_DEFINE_STATIC_MAPS({enum})" in cpp,
                f"PrintConfig.cpp missing enum map definition for {enum}")

    for option in WAVE_OPTIONS:
        hpp_pattern = re.compile(rf"\(\(\s*ConfigOption[^,]*,\s*{re.escape(option)}\s*\)\)")
        direct_hpp_pattern = re.compile(rf"\bConfigOption[A-Za-z0-9_]*(?:<[^>]+>)?\s+{re.escape(option)}\s*;")
        require(hpp_pattern.search(hpp) is not None or direct_hpp_pattern.search(hpp) is not None,
                f"PrintConfig.hpp missing storage for {option}")
        require(f'this->add("{option}",' in cpp, f"PrintConfig.cpp missing definition for {option}")
        require(option in tab, f"Tab.cpp missing UI row for {option}")

    require("new ConfigOptionBool(false)" in option_block(cpp, "wave_overhangs"),
            "wave_overhangs must stay off by default")
    require("Compatibility metadata" in option_block(cpp, "wave_overhang_min_angle"),
            "legacy minimum-angle field must disclose that Orca detection owns activation")
    require("WAVE_OVERHANG_START" in option_block(cpp, "wave_overhang_debug_gcode"),
            "debug marker contract missing")
    require("support_remaining_areas_after_wave_overhangs" in manip,
            "hybrid support-remainder toggle missing")
    require("wo_enabled" in manip and "wo_floor_hilbert" in manip, "Wave Overhang visibility gates missing")
    require('new_optgroup(L("Wave overhangs")' in tab, "settings group missing")

    require_tokens(extrusion, [
        "bool wave_overhang = false",
        "bool wave_overhang_floor = false",
        "bool wave_overhang_perimeter = false",
        "bool wave_overhang_floor_perimeter = false",
        "int8_t wave_overhang_floor_distance = 0",
        "this->wave_overhang_floor_distance = rhs.wave_overhang_floor_distance",
    ], "ExtrusionPath wave role contract")
    require("path.wave_overhang = true" in wave_cpp, "wave generator must mark generated paths")

    require_tokens(perim_hpp, ["out_wave_overhang_floor_polygons", "out_wave_overhang_covered_polygons"],
                   "PerimeterGenerator output contract")
    require_tokens(perim_cpp, [
        "WaveOverhangs/AndersonsGenerator.hpp",
        "generate_wave_overhang_paths",
        "clip_inner_perimeters_in_zone",
        "out_wave_overhang_floor_polygons",
        "out_wave_overhang_covered_polygons",
        "algorithm=wavefront",
    ], "PerimeterGenerator runtime")
    require(perim_cpp.count("apply_extra_perimeters(infill_exp, surface.expolygon)") >= 2,
            "classic and Arachne perimeter flows must pass island geometry")

    require_tokens(layer_hpp, ["wave_overhang_floor_polygons", "wave_overhang_shadow_polygons",
                               "wave_overhang_covered_polygons"], "Layer wave geometry")
    require_tokens(layer_region_cpp, ["out_wave_overhang_floor_polygons", "wave_overhang_floor_polygons",
                                      "out_wave_overhang_covered_polygons", "wave_overhang_covered_polygons"],
                   "LayerRegion forwarding")
    require_tokens(print_object_cpp, [
        "apply_wave_overhang_floor_layer_authority",
        "apply_wave_overhang_bridge_suppression",
        "tag_wave_overhang_perimeters",
        "Classify each point by its distance from a wave strip below",
        "wave_overhang_shadow_polygons",
        "wave_overhang_floor_perimeter = true",
    ], "angled backing-floor authority")
    require_tokens(fill_cpp, [
        "ipHilbertCurve",
        "wave_overhang_floor_hilbert_density",
        "tag_wave_overhang_floor_recursive",
        "wave_overhang_floor_distance",
    ], "backing-floor fill generation")
    require("support_remaining_areas_after_wave_overhangs.value" in support_cpp, "hybrid support gate missing")
    require("diff_ex(overhangs_per_layers[layer_id], layer.wave_overhang_covered_polygons)" in support_cpp,
            "hybrid support must subtract covered areas")

    require_tokens(gcode_cpp, [
        "HEADER_BLOCK_END",
        "WAVE_OVERHANG_BUILD",
        WAVE_TAG,
        WAVE_REVISION,
        "WAVE_OVERHANG_CONFIG",
        ";_WAVE_OVERHANG_FAN_START %d %d",
        "wave_overhang_nozzle_temp",
        "wave_overhang_end_retract_length",
        "wave-overhang min_wave_time dwell",
        "wave-overhang min_layer_time dwell",
        "wave_overhang_floor_speed_ramp",
        "wave_overhang_travel_speed",
    ], "G-code Wave Overhang runtime")
    require(gcode_cpp.index("HEADER_BLOCK_END") < gcode_cpp.index("WAVE_OVERHANG_BUILD"),
            "Wave Overhang diagnostics must stay outside firmware-parsed HEADER_BLOCK")
    require_tokens(gcode_hpp, ["m_inside_wave_overhang", "m_wave_layer_accumulated_time"],
                   "G-code wave state")
    require("travel_to_xy(const Vec2d &point, double speed_override" in writer_hpp and
            "travel_to_xyz(const Vec3d &point, double speed_override" in writer_hpp,
            "GCodeWriter explicit wave travel-speed overload missing")
    require_tokens(writer_cpp, [
        "return this->travel_to_xy(to_2d(point), speed_override);",
        "w.emit_f(travel_speed * 60.0);",
    ], "GCodeWriter wave travel-speed propagation")
    require_tokens(cooling_cpp, [
        "_WAVE_OVERHANG_FAN_START",
        "wave_overhang_fan_speed",
        "wave_overhang_aux_fan_percent",
        "set_additional_fan",
    ], "CoolingBuffer wave fan handling")

    for credit_text in (credits, packaged_credits):
        require_tokens(credit_text, [WAVE_SOURCE_URL, WAVE_TAG, WAVE_REVISION, "Janis A. Andersons",
                                     "Dennis Klappe", "Additive Manufacturing Letters"],
                       "Wave source attribution")

    print("TinManX1 Wave Overhang v0.4 smoke passed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print(f"TinManX1 Wave Overhang smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
