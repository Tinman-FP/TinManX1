#!/usr/bin/env python3
"""Verify TinManX1 FibreSeek profile, UI, planner, and release wiring.

This is a structural regression guard. It does not prove a slice is printable;
the native planner smoke test and G-code contract audit do that. This check
keeps the option surface from drifting when profiles, UI tabs, compact setting
lists, or planner handoff code are edited later.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def find_repo_root(start: Path) -> Path:
    for candidate in (start.parent, *start.parents):
        if (candidate / "README.md").is_file() and (candidate / "scripts").is_dir():
            return candidate
    return start.parents[1]


ROOT = find_repo_root(Path(__file__).resolve())
PROFILE_ROOT = ROOT / "resources" / "profiles" / "TinManX1"

COMPACT_STRENGTH_OPTIONS = [
    "fiber_reinforcement_mode",
    "fiber_generate_perimeters",
    "fiber_generate_infill",
    "fiber_start_layer",
    "fiber_min_radius",
    "fiber_infill_pattern",
    "fiber_infill_density",
    "fiber_infill_angles",
    "fiber_infill_source_policy",
    "fiber_seam_position",
    "fiber_seam_angle",
    "fiber_line_width",
    "fiber_infill_spacing",
    "fiber_layer_step",
    "fiber_min_route_length",
    "fiber_print_speed",
    "fiber_start_speed",
]

CRITICAL_PLANNER_HANDOFFS = {
    "fiber_reinforcement_mode": {
        "print": ["--fiber-reinforcement-mode"],
        "planner": ['comments.get("fiber_reinforcement_mode")', "args.fiber_reinforcement_mode"],
    },
    "fiber_generate_perimeters": {
        "print": ["--fiber-generate-perimeters"],
        "planner": ['comments.get("fiber_generate_perimeters")', "args.fiber_generate_perimeters"],
    },
    "fiber_generate_infill": {
        "print": ["--fiber-generate-infill"],
        "planner": ['comments.get("fiber_generate_infill")', "args.fiber_generate_infill"],
    },
    "fiber_infill_pattern": {
        "print": ["--fiber-infill-pattern"],
        "planner": ["args.fiber_infill_pattern"],
    },
    "fiber_infill_source_policy": {
        "print": ["--fiber-infill-source"],
        "planner": ['comments.get("fiber_infill_source_policy")', "args.fiber_infill_source"],
    },
    "fiber_infill_density": {
        "print": ["--density"],
        "planner": ['comments.get("fiber_infill_density")', "args.density"],
    },
    "fiber_infill_angles": {
        "print": ["--angles"],
        "planner": ['comments.get("fiber_infill_angles")', "args.angles"],
    },
    "fiber_seam_position": {
        "print": ["--fiber-seam-position"],
        "planner": ['comments.get("fiber_seam_position")', "args.fiber_seam_position"],
    },
    "fiber_seam_angle": {
        "print": ["--fiber-seam-angle"],
        "planner": ['comments.get("fiber_seam_angle")', "args.fiber_seam_angle"],
    },
    "fiber_start_layer": {
        "print": ["--fiber-start-layer"],
        "planner": ['comments.get("fiber_start_layer")', "args.fiber_start_layer"],
    },
    "fiber_layer_step": {
        "print": ["--layer-step"],
        "planner": ['comments.get("fiber_layer_step")', "args.layer_step"],
    },
    "fiber_min_route_length": {
        "print": ["--min-route-length"],
        "planner": ['comments.get("fiber_min_route_length")', "args.min_route_length"],
    },
    "fiber_line_width": {
        "print": ["--line-width"],
        "planner": ['comments.get("fiber_line_width")', "args.line_width"],
    },
    "fiber_infill_spacing": {
        "print": ["--spacing"],
        "planner": ['comments.get("fiber_infill_spacing")', "args.spacing"],
    },
    "fiber_perimeter_inset": {
        "print": ["--perimeter-inset"],
        "planner": ['comments.get("fiber_perimeter_inset")', "args.perimeter_inset"],
    },
    "fiber_infill_inset": {
        "print": ["--infill-inset"],
        "planner": ['comments.get("fiber_infill_inset")', "args.infill_inset"],
    },
    "fiber_print_speed": {
        "print": ["--fiber-print-speed"],
        "planner": ['comments.get("fiber_print_speed")', "args.fiber_print_speed"],
    },
    "fiber_start_speed": {
        "print": ["--fiber-start-speed"],
        "planner": ['comments.get("fiber_start_speed")', "args.fiber_start_speed"],
    },
    "fiber_max_routes_per_layer": {
        "print": ["--max-routes-per-layer"],
        "planner": ['comments.get("fiber_max_routes_per_layer")', "args.max_routes_per_layer"],
    },
    "fiber_routes_per_cut": {
        "print": ["--fiber-routes-per-cut"],
        "planner": ['comments.get("fiber_routes_per_cut")', "args.fiber_routes_per_cut"],
    },
    "fiber_reinforcement_payload": {
        "print": ["fiber_reinforcement_payload"],
        "planner": ['comments.get("fiber_reinforcement_payload")'],
    },
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="ignore")


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def profile_fiber_keys() -> dict[str, set[str]]:
    by_kind: dict[str, set[str]] = {}
    for kind in ("process", "filament", "machine"):
        paths = sorted((PROFILE_ROOT / kind).glob("*.json"))
        if not paths:
            fail(f"missing TinManX1 {kind} profiles")
        keys: set[str] = set()
        for path in paths:
            data = json.loads(path.read_text(encoding="utf-8"))
            keys.update(key for key in data if key.startswith("fiber_"))
        by_kind[kind] = keys
    return by_kind


def profile_process_key_sets() -> dict[tuple[str, ...], list[str]]:
    grouped: dict[tuple[str, ...], list[str]] = {}
    for path in sorted((PROFILE_ROOT / "process").glob("*Continuous Fiber*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        key_tuple = tuple(sorted(key for key in data if key.startswith("fiber_")))
        grouped.setdefault(key_tuple, []).append(path.name)
    return grouped


def require_all(haystack: str, needles: list[str], label: str) -> None:
    missing = [needle for needle in needles if needle not in haystack]
    if missing:
        fail(f"{label} missing: {', '.join(missing)}")


def require_option_defs(keys: set[str]) -> None:
    print_config_cpp = read("src/libslic3r/PrintConfig.cpp")
    print_config_hpp = read("src/libslic3r/PrintConfig.hpp")
    missing_cpp = [key for key in sorted(keys) if f'this->add("{key}"' not in print_config_cpp]
    missing_hpp = [key for key in sorted(keys) if key not in print_config_hpp]
    if missing_cpp:
        fail("PrintConfig.cpp missing option definitions: " + ", ".join(missing_cpp))
    if missing_hpp:
        fail("PrintConfig.hpp missing option storage declarations: " + ", ".join(missing_hpp))


def require_profile_surface_consistency(by_kind: dict[str, set[str]]) -> None:
    process_grouped = profile_process_key_sets()
    if len(process_grouped) != 1:
        summary = "; ".join(f"{len(names)} profile(s): {', '.join(names[:3])}" for names in process_grouped.values())
        fail("continuous-fiber process profiles do not share the same fiber option set: " + summary)
    if len(process_grouped) == 0:
        fail("no continuous-fiber process profiles found")
    if not by_kind["filament"]:
        fail("CFC filament profiles expose no fiber_* keys")
    if not by_kind["machine"]:
        fail("FibreSeek machine profiles expose no fiber_* keys")


def require_ui_surface(keys: set[str]) -> None:
    tab_cpp = read("src/slic3r/GUI/Tab.cpp")
    missing = [key for key in sorted(keys) if key not in tab_cpp]
    if missing:
        fail("Tab.cpp missing fiber UI placement: " + ", ".join(missing))

    gui_factories = read("src/slic3r/GUI/GUI_Factories.cpp")
    missing_compact = [key for key in COMPACT_STRENGTH_OPTIONS if f'"{key}"' not in gui_factories]
    if missing_compact:
        fail("GUI_Factories.cpp missing compact Strength fiber settings: " + ", ".join(missing_compact))


def require_profile_generation_and_lint(process_keys: set[str]) -> None:
    generator = read("scripts/generate_tinmanx1_fiberseek_profiles.py")
    linter = read("scripts/lint_tinmanx1_fiberseek_profiles.py")
    missing_generator = [key for key in sorted(process_keys) if f'"{key}"' not in generator]
    if missing_generator:
        fail("profile generator missing process fiber keys: " + ", ".join(missing_generator))
    for key in ("fiber_seam_position", "fiber_infill_density", "fiber_infill_angles", "fiber_reinforcement_payload"):
        if key not in linter:
            fail(f"profile linter missing guard for {key}")


def require_preset_whitelist(process_keys: set[str]) -> None:
    preset_cpp = read("src/libslic3r/Preset.cpp")
    missing = [key for key in sorted(process_keys) if f'"{key}"' not in preset_cpp]
    if missing:
        fail("Preset.cpp missing process option whitelist entries: " + ", ".join(missing))


def require_planner_handoff() -> None:
    print_cpp = read("src/libslic3r/Print.cpp")
    planner = read("scripts/orcaslicer_codex_native_fiber_planner.py")
    bundled = read("resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py")
    if planner != bundled:
        fail("bundled native fiber planner copy differs from scripts/orcaslicer_codex_native_fiber_planner.py")

    for option, token_sets in CRITICAL_PLANNER_HANDOFFS.items():
        if option not in print_cpp:
            fail(f"Print.cpp missing planner handoff option: {option}")
        require_all(print_cpp, token_sets["print"], f"Print.cpp handoff for {option}")
        require_all(planner, token_sets["planner"], f"native planner consumption for {option}")


def main() -> int:
    by_kind = profile_fiber_keys()
    all_profile_keys = set().union(*by_kind.values())
    require_profile_surface_consistency(by_kind)
    require_option_defs(all_profile_keys)
    require_ui_surface(all_profile_keys)
    require_profile_generation_and_lint(by_kind["process"])
    require_preset_whitelist(by_kind["process"])
    require_planner_handoff()
    print(
        "TinManX1 FibreSeek wiring check passed: "
        f"{len(all_profile_keys)} profile fiber keys, "
        f"{len(by_kind['process'])} process keys, "
        f"{len(COMPACT_STRENGTH_OPTIONS)} compact UI keys."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
