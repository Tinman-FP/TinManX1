#!/bin/sh
''':'
unset PYTHONHOME
unset PYTHONPATH
unset PYTHONEXECUTABLE
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for PYTHON in \
  "${ORCASLICER_CODEX_ARC_PYTHON:-}" \
  "${TINMANX_ARC_PYTHON:-}" \
  "${SCRIPT_DIR}/../arc-support-venv/bin/python" \
  "${SCRIPT_DIR}/../../../arc-support-venv/bin/python" \
  "$(command -v python3 2>/dev/null)" \
  "$(command -v python3.12 2>/dev/null)" \
  "$(command -v python3.11 2>/dev/null)" \
  "$(command -v python3.10 2>/dev/null)"
do
  if [ -n "${PYTHON}" ] && [ -x "${PYTHON}" ]; then
    exec "${PYTHON}" "$0" "$@"
  fi
done
echo "TinManX1 Arc Overhang transform could not find a usable Python interpreter." >&2
exit 127
':'''
from __future__ import annotations

"""Safe TinManX1 wrapper for the vendored Arc Overhang transform.

The upstream Kelsch script overwrites its input file and pauses for interactive
prompts. This wrapper keeps the experimental feature available while preserving
the original G-code and emitting a machine-readable audit summary.
"""

import argparse
import builtins
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import types
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_REVISION = "0693ef29a0eb3e96fdc336841cd714e071f3ed9a"
LOCAL_ARC_PYTHON = REPO_ROOT.parent / "arc-support-venv" / "bin" / "python"
SUPPORT_STRATEGY = "arc"
BASE_SUPPORT_PATH = "bridge_overhang_generation"
POSTPROCESS_STAGE = "replace_bridge_infill_with_arc_overhangs"
ADAPTER_CONTRACT = "separate_output_then_replace_on_success"
LOW_ARC_COVERAGE_ERROR = "Arc Overhang transform covered too little bridge source geometry"
MIN_ARC_SUPPORT_COVERAGE_RATIO = float(os.environ.get(
    "ORCASLICER_CODEX_ARC_SUPPORT_MIN_COVERAGE_RATIO",
    os.environ.get("TINMANX_ARC_SUPPORT_MIN_COVERAGE_RATIO", "0.25"),
))
ARC_SOURCE_FEATURES = ("Bridge", "Overhang wall")


def _python_candidates() -> list[str | None]:
    return [
        os.environ.get("ORCASLICER_CODEX_ARC_PYTHON"),
        os.environ.get("TINMANX_ARC_PYTHON"),
        str(LOCAL_ARC_PYTHON),
        shutil.which("python3"),
        shutil.which("python3.12"),
        shutil.which("python3.11"),
        shutil.which("python3.10"),
    ]


def _reexec_if_needed(reason: str) -> None:
    current = Path(sys.executable).resolve()
    for executable in _python_candidates():
        if not executable:
            continue
        path = Path(executable).expanduser()
        if not path.exists() or path.resolve() == current:
            continue
        os.environ["ORCASLICER_CODEX_ARC_REEXEC_REASON"] = reason
        os.execv(str(path), [str(path), *sys.argv])


if sys.version_info < (3, 9):
    _reexec_if_needed("python_version")
    raise RuntimeError("Arc Overhangs require Python 3.9+ for the vendored upstream engine.")

missing_dependencies = [
    module_name
    for module_name in ("shapely", "numpy")
    if importlib.util.find_spec(module_name) is None
]
if missing_dependencies and not os.environ.get("ORCASLICER_CODEX_ARC_REEXEC_REASON") and not os.environ.get("TINMANX_ARC_REEXEC_REASON"):
    _reexec_if_needed("missing_dependencies")
if missing_dependencies:
    candidates = [
        candidate for candidate in _python_candidates() if candidate
    ]
    raise RuntimeError(
        "Arc Overhang dependencies are missing "
        f"({', '.join(missing_dependencies)}). Set ORCASLICER_CODEX_ARC_PYTHON to a Python with "
        f"the vendored requirements installed. Checked: {', '.join(candidates)}"
    )


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _file_size(path: Path) -> int:
    return path.stat().st_size


def _default_engine_path() -> Path:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        os.environ.get("ORCASLICER_CODEX_ARC_SUPPORT_ENGINE"),
        os.environ.get("TINMANX_ARC_SUPPORT_ENGINE"),
        str(REPO_ROOT / "third_party" / "gpl" / "arc-overhang" / "softfever_slicer_post_processing_script.py"),
        str(script_dir / "third_party" / "gpl" / "arc-overhang" / "softfever_slicer_post_processing_script.py"),
        str(script_dir.parent / "third_party" / "gpl" / "arc-overhang" / "softfever_slicer_post_processing_script.py"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path.resolve()
    return REPO_ROOT / "third_party" / "gpl" / "arc-overhang" / "softfever_slicer_post_processing_script.py"


def _count_markers(lines: list[str]) -> dict[str, int]:
    return {
        "arc_infill_type_markers": sum(1 for line in lines if line.startswith(";TYPE:Arc infill")),
        "arc_infill_extrusion_moves": _count_arc_infill_extrusion_moves(lines),
        "arc_support_type_markers": sum(1 for line in lines if line.startswith(";TYPE:Arc support")),
        "arc_support_feature_markers": sum(1 for line in lines if line.startswith("; FEATURE: Arc support")),
        "arc_support_extrusion_moves": _count_arc_support_extrusion_moves(lines),
        "normal_support_type_markers": sum(1 for line in lines if line.startswith(";TYPE:Support")),
        "normal_support_extrusion_moves": _count_normal_support_extrusion_moves(lines),
        "bridge_type_markers": sum(1 for line in lines if "Bridge" in line and line.startswith(";TYPE:")),
        "layer_change_markers": sum(1 for line in lines if line.startswith(";LAYER_CHANGE")),
        "toolchange_markers": sum(1 for line in lines if line.startswith("T") and line[1:2].isdigit()),
    }


def _is_extrusion_move(line: str) -> bool:
    return re.match(r"^G[0123]\b", line) is not None and re.search(r"\bE[-+0-9.]", line) is not None


def _count_arc_support_extrusion_moves(lines: list[str]) -> int:
    moves = 0
    in_arc_section = False
    for line in lines:
        if line.startswith(";TYPE:Arc support"):
            in_arc_section = True
            continue
        if in_arc_section and (
            line.startswith(";TYPE:")
            or line.startswith("; FEATURE:")
            or line.startswith(";LAYER_CHANGE")
        ):
            in_arc_section = False
        if in_arc_section and _is_extrusion_move(line):
            moves += 1
    return moves


def _count_arc_infill_extrusion_moves(lines: list[str]) -> int:
    moves = 0
    in_arc_section = False
    for line in lines:
        if line.startswith(";TYPE:Arc infill"):
            in_arc_section = True
            continue
        if in_arc_section and (
            line.startswith(";TYPE:")
            or line.startswith("; FEATURE:")
            or line.startswith(";LAYER_CHANGE")
        ):
            in_arc_section = False
        if in_arc_section and _is_extrusion_move(line):
            moves += 1
    return moves


def _count_normal_support_extrusion_moves(lines: list[str]) -> int:
    moves = 0
    in_support_section = False
    for line in lines:
        if line.startswith(";TYPE:Support") and not line.startswith(";TYPE:Arc support"):
            in_support_section = True
            continue
        if in_support_section and (
            line.startswith(";TYPE:")
            or line.startswith("; FEATURE:")
            or line.startswith(";LAYER_CHANGE")
        ):
            in_support_section = False
        if in_support_section and _is_extrusion_move(line):
            moves += 1
    return moves


def _clean_arc_infill_sections(lines: list[str]) -> tuple[list[str], int, int]:
    cleaned: list[str] = []
    removed_empty = 0
    kept_sections = 0
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith(";TYPE:Arc infill"):
            cleaned.append(line)
            index += 1
            continue

        section_start = index + 1
        section_end = section_start
        while section_end < len(lines) and not (
            lines[section_end].startswith(";TYPE:")
            or lines[section_end].startswith("; FEATURE:")
            or lines[section_end].startswith(";LAYER_CHANGE")
        ):
            section_end += 1

        section = lines[section_start:section_end]
        extrusion_moves = sum(1 for item in section if item.startswith("G1") and " E" in item)
        if extrusion_moves == 0:
            removed_empty += 1
        else:
            kept_sections += 1
            cleaned.extend(
                [
                    "; FEATURE: Arc overhang\n",
                    ";TYPE:Arc infill\n",
                    "; orcaslicer_codex_arc_support_geometry=arc_overhang_infill\n",
                ]
            )
            cleaned.extend(section)
        index = section_end
    return cleaned, kept_sections, removed_empty


def _command_part(line: str) -> str:
    return line.split(";", 1)[0].strip()


def _is_guarded_command(command: str) -> bool:
    if not command:
        return False
    first = command.split(None, 1)[0].upper()
    if first.startswith("T") and first[1:].isdigit():
        return True
    return first in {
        "G28",
        "G29",
        "M82",
        "M83",
        "M104",
        "M106",
        "M107",
        "M109",
        "M140",
        "M190",
        "M600",
        "M701",
        "M702",
        "M900",
    }


def _first_layer_change_line(lines: list[str]) -> int:
    for index, line in enumerate(lines, start=1):
        if line.startswith(";LAYER_CHANGE"):
            return index
    return len(lines) + 1


def _toolchange_region_ended(command: str, line: str) -> bool:
    if line.startswith(";LAYER_CHANGE") or line.startswith(";TYPE:"):
        return True
    first = command.split(None, 1)[0].upper() if command else ""
    return first in {"G0", "G1", "G2", "G3"}


def _guarded_commands(lines: list[str]) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    first_layer_change = _first_layer_change_line(lines)
    in_toolchange_region = False
    for index, line in enumerate(lines, start=1):
        command = _command_part(line)
        command_word = command.split(None, 1)[0].upper() if command else ""
        in_startup_region = index < first_layer_change
        starts_toolchange = command_word.startswith("T") and command_word[1:].isdigit()
        if not in_startup_region and _toolchange_region_ended(command, line):
            in_toolchange_region = False
        if starts_toolchange:
            in_toolchange_region = True
        if (in_startup_region or in_toolchange_region) and _is_guarded_command(command):
            commands.append(
                {
                    "line": index,
                    "scope": "startup" if in_startup_region else "toolchange",
                    "command": command,
                }
            )
    return commands


def _machine_start_toolchange_guard(before_lines: list[str], after_lines: list[str]) -> dict[str, Any]:
    before = _guarded_commands(before_lines)
    after = _guarded_commands(after_lines)
    before_commands = [item["command"] for item in before]
    after_commands = [item["command"] for item in after]
    changed = before_commands != after_commands
    return {
        "status": "changed" if changed else "passed",
        "guarded_command_count_before": len(before_commands),
        "guarded_command_count_after": len(after_commands),
        "changed": changed,
        "before_commands": before_commands,
        "after_commands": after_commands,
        "note": "Guards heater, fan, extrusion-distance mode, homing, bed leveling, filament-change, pressure-advance, and toolchange commands in startup and toolchange setup regions only.",
    }


def _prepend_preview_metadata(
    output_path: Path,
    *,
    status: str,
    guarded_transform_required: bool,
    removed_bridge_moves: int,
) -> None:
    lines = _read_lines(output_path)
    existing_prefixes = ("; orcaslicer_codex_arc_support_", "; tinmanx_arc_support_")
    lines = [line for line in lines if not line.startswith(existing_prefixes)]
    metadata = [
        "; orcaslicer_codex_arc_support_status=guarded_preview\n",
        f"; orcaslicer_codex_arc_support_transform_status={status}\n",
        "; orcaslicer_codex_arc_support_strategy=arc\n",
        "; orcaslicer_codex_arc_support_base_path=bridge_overhang_generation\n",
        "; orcaslicer_codex_arc_support_postprocess_stage=replace_bridge_infill_with_arc_overhangs\n",
        f"; orcaslicer_codex_arc_support_removed_bridge_extrusions={removed_bridge_moves}\n",
        "; orcaslicer_codex_arc_support_removed_orca_support_extrusions=0\n",
        f"; orcaslicer_codex_arc_support_guarded_transform_required={str(guarded_transform_required).lower()}\n",
        "; orcaslicer_codex_arc_support_preview_note=arc_overhang_model_toolpath_no_support_material\n",
    ]
    output_path.write_text("".join(metadata + lines), encoding="utf-8")


def _load_engine(engine_path: Path) -> Any:
    spec = importlib.util.spec_from_file_location("orcaslicer_codex_arc_overhang_engine", engine_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Arc Overhang engine from {engine_path}")
    module = importlib.util.module_from_spec(spec)
    old_dont_write_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = old_dont_write_bytecode
    if not hasattr(module, "main"):
        raise RuntimeError(f"Arc Overhang engine has no main() entry point: {engine_path}")
    return module


def _install_plot_stub() -> None:
    if os.environ.get("ORCASLICER_CODEX_ARC_ENABLE_PLOTS") or os.environ.get("TINMANX_ARC_ENABLE_PLOTS"):
        return
    pyplot = types.ModuleType("matplotlib.pyplot")

    def noop(*args: Any, **kwargs: Any) -> None:
        return None

    pyplot.__getattr__ = lambda _name: noop  # type: ignore[attr-defined]
    matplotlib = types.ModuleType("matplotlib")
    matplotlib.__path__ = []  # type: ignore[attr-defined]
    matplotlib.pyplot = pyplot  # type: ignore[attr-defined]
    sys.modules.setdefault("matplotlib", matplotlib)
    sys.modules.setdefault("matplotlib.pyplot", pyplot)


def _patch_engine_defaults(engine: Any) -> None:
    reader = getattr(engine, "readSettingsFromGCode2dict", None)
    if reader is None:
        return
    defaults = {
        "outer_wall_line_width": 0.4,
        "nozzle_diameter": 0.4,
        "overhang_fan_speed": 100,
        "travel_speed": 150,
    }
    numeric_settings = {
        "outer_wall_line_width",
        "nozzle_diameter",
        "overhang_fan_speed",
        "travel_speed",
        "filament_diameter",
        "retract_length",
        "retract_speed",
        "deretract_speed",
        "ArcExtrusionMultiplier",
    }

    def first_numeric(value: Any) -> float | None:
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        if isinstance(value, (list, tuple)):
            for item in value:
                coerced = first_numeric(item)
                if coerced is not None:
                    return coerced
        return None

    def patched_reader(lines: list[str]) -> dict[str, Any]:
        settings = reader(lines)
        for key, value in defaults.items():
            if settings.get(key) is None:
                settings[key] = value
        for key in numeric_settings:
            coerced = first_numeric(settings.get(key))
            if coerced is not None:
                settings[key] = coerced
        return settings

    engine.readSettingsFromGCode2dict = patched_reader


def _patch_engine_support_sources(engine: Any) -> None:
    """Keep the vendored bridge-based engine on bridge/overhang source geometry.

    Arc Overhangs are not ordinary supports. The upstream script detects bridge
    infill, validates it against overhang walls, and injects `Arc infill`.
    TinManX1 keeps that behavior; an opt-in debug environment variable
    may still expose old support-source experiments, but production defaults do
    not consume or relabel support-material toolpaths.
    """
    layer_type = getattr(engine, "Layer", None)
    bridge_infill_type = getattr(engine, "BridgeInfill", None)
    get_point = getattr(engine, "getPtfromCmd", None)
    line_string_type = getattr(engine, "LineString", None)
    if layer_type is None or bridge_infill_type is None or get_point is None:
        return

    original_make_external_perimeters = getattr(layer_type, "makeExternalPerimeter2Polys", None)
    original_verify_infill_polys = getattr(layer_type, "verifyinfillpolys", None)

    extended_support = os.environ.get(
        "ORCASLICER_CODEX_ARC_SUPPORT_ENGINE_EXTENDED_SUPPORT",
        os.environ.get("TINMANX_ARC_SUPPORT_ENGINE_EXTENDED_SUPPORT", "0"),
    )
    allow_support_source = extended_support in {"1", "true", "True", "yes"}

    def feature_is_support_source(feature_type: str) -> bool:
        return "Bridge" in feature_type or (allow_support_source and feature_type.startswith(";TYPE:Support"))

    def support_source_line_strings(layer: Any) -> list[Any]:
        if line_string_type is None:
            return []
        parts: list[list[Any]] = []
        travel_speed = layer.parameters.get("travel_speed")
        travelstr = f"F{travel_speed * 60}" if travel_speed is not None else None
        for feature in layer.features:
            ftype = feature[0]
            lines = feature[1]
            if not feature_is_support_source(ftype):
                continue
            pts = []
            is_wipe_move = False
            for line in lines:
                if "G1" in line and not is_wipe_move:
                    if "E" not in line and travelstr is not None and travelstr in line:
                        if len(pts) >= 2:
                            parts.append(pts)
                            pts = []
                    elif "E" in line:
                        point = get_point(line)
                        if point:
                            pts.append(point)
                if "WIPE_START" in line:
                    is_wipe_move = True
                if "WIPE_END" in line:
                    is_wipe_move = False
            if len(pts) >= 2:
                parts.append(pts)
        line_strings = []
        for pts in parts:
            try:
                line_strings.append(line_string_type(pts))
            except Exception:
                continue
        return line_strings

    def patched_spot_bridge_infill(self: Any) -> None:
        parts: list[list[Any]] = []
        travel_speed = self.parameters.get("travel_speed")
        travelstr = f"F{travel_speed * 60}" if travel_speed is not None else None
        for feature in self.features:
            ftype = feature[0]
            lines = feature[1]
            if "Bridge" not in ftype and not (allow_support_source and ftype.startswith(";TYPE:Support")):
                continue
            pts = []
            is_wipe_move = False
            for line in lines:
                if "G1" in line and not is_wipe_move:
                    if "E" not in line and travelstr is not None and travelstr in line:
                        if len(pts) >= 2:
                            parts.append(pts)
                            pts = []
                    elif "E" in line:
                        point = get_point(line)
                        if point:
                            pts.append(point)
                if "WIPE_START" in line:
                    is_wipe_move = True
                if "WIPE_END" in line:
                    is_wipe_move = False
            if len(pts) > 1:
                parts.append(pts)
        for infillpts in parts:
            self.binfills.append(bridge_infill_type(infillpts))

    layer_type.spotBridgeInfill = patched_spot_bridge_infill

    if not allow_support_source:
        return

    if original_make_external_perimeters is not None:
        def patched_make_external_perimeter_polys(self: Any) -> None:
            original_make_external_perimeters(self)
            if self.extPerimeterPolys:
                return
            for line_string in support_source_line_strings(self):
                try:
                    poly = line_string.buffer(max(float(self.parameters.get("ArcWidth") or 0.4), 0.4))
                except Exception:
                    continue
                if poly and not poly.is_empty:
                    self.extPerimeterPolys.append(poly)

        layer_type.makeExternalPerimeter2Polys = patched_make_external_perimeter_polys

    if original_verify_infill_polys is not None:
        def patched_verify_infill_polys(self: Any, minDistForValidation: float = 0.5) -> None:
            original_verify_infill_polys(self, minDistForValidation)
            if self.validpolys:
                return
            allowed_space = self.parameters.get("AllowedSpaceForArcs")
            for idp, poly in enumerate(self.polys):
                if not getattr(poly, "is_valid", False):
                    continue
                if allowed_space and not allowed_space.contains(poly):
                    continue
                if poly.area < self.parameters.get("MinArea"):
                    continue
                self.validpolys.append(poly)
                self.deleteTheseInfills.append(idp)

        layer_type.verifyinfillpolys = patched_verify_infill_polys


def transform_gcode(input_path: Path, output_path: Path, audit_path: Path, engine_path: Path) -> int:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    audit_path = audit_path.resolve()
    engine_path = engine_path.resolve()

    if input_path == output_path:
        raise ValueError("Input and output must be different paths; wrapper never mutates the source G-code.")

    before_lines = _read_lines(input_path)
    before = _count_markers(before_lines)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(input_path, output_path)

    status = "ok"
    error = None
    engine_invoked = False
    native_stats: dict[str, int | bool | str] = {
        "enabled": False,
        "source": "disabled_support_material_is_not_arc_overhang_source",
        "note": "Arc Overhangs are generated from bridge/overhang infill, not Orca support material.",
    }

    old_input = builtins.input
    old_backend = os.environ.get("MPLBACKEND")
    try:
        engine_invoked = True
        os.environ["MPLBACKEND"] = "Agg"
        builtins.input = lambda prompt="": ""
        _install_plot_stub()
        engine = _load_engine(engine_path)
        _patch_engine_defaults(engine)
        _patch_engine_support_sources(engine)
        with output_path.open("r", encoding="utf-8", errors="replace") as stream:
            engine.main(stream, str(output_path))
    except Exception as exc:  # noqa: BLE001 - audit must capture engine failures.
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"
    finally:
        builtins.input = old_input
        if old_backend is None:
            os.environ.pop("MPLBACKEND", None)
        else:
            os.environ["MPLBACKEND"] = old_backend

    after_lines = _read_lines(output_path)
    after_lines, kept_arc_infill_sections, removed_empty_arc_sections = _clean_arc_infill_sections(after_lines)
    removed_normal_support_moves = 0
    removed_normal_support_markers = 0
    removed_normal_support_unretracts = 0
    output_path.write_text("".join(after_lines), encoding="utf-8")
    after = _count_markers(after_lines)
    command_guard = _machine_start_toolchange_guard(before_lines, after_lines)
    input_sha256 = _file_sha256(input_path)
    output_sha256 = _file_sha256(output_path)
    engine_exists = engine_path.exists()
    if status == "ok" and command_guard["changed"]:
        status = "failed"
        error = "Guarded machine-start/toolchange command mutation detected; refusing Arc Overhang output."
    if status == "ok" and after["arc_infill_extrusion_moves"] == 0 and before["bridge_type_markers"] > 0:
        status = "failed"
        error = "Arc Overhang transform produced no Arc infill extrusion moves; refusing to report a successful export."
    coverage_ratio = 1.0
    if status == "ok" and after["normal_support_extrusion_moves"] != 0:
        status = "failed"
        error = "Arc Overhang export still contains normal support extrusion moves; refusing support-material output."
    if status == "ok" and after["arc_support_extrusion_moves"] != 0:
        status = "failed"
        error = "Arc Overhang export produced Arc support extrusion moves instead of Arc infill."
    if status == "ok":
        _prepend_preview_metadata(
            output_path,
            status=status,
            guarded_transform_required=True,
            removed_bridge_moves=max(0, before.get("bridge_type_markers", 0) - after.get("bridge_type_markers", 0)),
        )
        after_lines = _read_lines(output_path)
        after = _count_markers(after_lines)
        command_guard = _machine_start_toolchange_guard(before_lines, after_lines)
        output_sha256 = _file_sha256(output_path)
    audit = {
        "status": status,
        "error": error,
        "input": str(input_path),
        "output": str(output_path),
        "engine": str(engine_path),
        "engine_exists": engine_exists,
        "engine_sha256": _file_sha256(engine_path) if engine_exists else "",
        "engine_size_bytes": _file_size(engine_path) if engine_exists else 0,
        "source_revision": SOURCE_REVISION,
        "license": "GPL-3.0",
        "support_strategy": SUPPORT_STRATEGY,
        "arc_support_source_features": list(ARC_SOURCE_FEATURES),
        "native_arc_support": native_stats,
        "native_arc_support_enabled": native_stats.get("enabled") is True,
        "engine_invoked": engine_invoked,
        "base_support_path": BASE_SUPPORT_PATH,
        "postprocess_stage": POSTPROCESS_STAGE,
        "adapter_contract": ADAPTER_CONTRACT,
        "normal_support_generation_preserved": False,
        "kept_arc_infill_sections": kept_arc_infill_sections,
        "promoted_arc_support_sections": 0,
        "removed_empty_arc_sections": removed_empty_arc_sections,
        "removed_normal_support_extrusion_moves": removed_normal_support_moves,
        "removed_normal_support_type_markers": removed_normal_support_markers,
        "removed_normal_support_unretracts": removed_normal_support_unretracts,
        "arc_support_coverage_ratio": coverage_ratio,
        "minimum_arc_support_coverage_ratio": MIN_ARC_SUPPORT_COVERAGE_RATIO,
        "input_sha256": input_sha256,
        "output_sha256": output_sha256,
        "input_size_bytes": _file_size(input_path),
        "output_size_bytes": _file_size(output_path),
        "credits": [
            "Steven McCulloch / layershift3d arc-overhang concept",
            "Nicolai Wachenschwan PrusaSlicer integration",
            "Kelsch OrcaSlicer integration",
        ],
        "before": before,
        "after": after,
        "delta": {key: after[key] - before[key] for key in before},
        "input_preserved": before_lines == _read_lines(input_path),
        "output_changed": before_lines != after_lines,
        "output_differs_by_hash": input_sha256 != output_sha256,
        "machine_start_toolchange_guard": command_guard,
    }
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if status == "ok" else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the experimental TinManX1 Arc Overhang transform safely.")
    parser.add_argument("input_gcode", type=Path)
    parser.add_argument("output_gcode", type=Path)
    parser.add_argument("--audit", type=Path, required=True, help="Path for JSON audit output.")
    parser.add_argument("--engine", type=Path, default=_default_engine_path(), help="Vendored Arc Overhang engine path.")
    args = parser.parse_args(argv)
    return transform_gcode(args.input_gcode, args.output_gcode, args.audit, args.engine)


if __name__ == "__main__":
    sys.exit(main())
