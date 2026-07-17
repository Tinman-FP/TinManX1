#!/usr/bin/env python3
"""Run public-release checks for TinManX1 FibreSeek support."""

from __future__ import annotations

import py_compile
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PYTHON_FILES = [
    "scripts/audit_fiberseek_gcode_contract.py",
    "scripts/check_tinmanx1_fiber_wiring.py",
    "scripts/compare_fiberseek_gcode.py",
    "scripts/generate_tinmanx1_fiberseek_profiles.py",
    "scripts/lint_tinmanx1_fiberseek_profiles.py",
    "scripts/orcaslicer_codex_native_fiber_planner.py",
    "scripts/smoke_orcaslicer_codex_native_fiber_planner.py",
    "resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py",
]

REQUIRED_PRESET_WHITELIST_KEYS = [
    "fiber_after_cut_plastic_extrusion_multiplier",
    "fiber_infill_angles",
    "fiber_infill_density",
    "fiber_machine_contract_payload",
    "fiber_max_arc_segment_length",
    "fiber_min_route_length",
    "fiber_reinforcement_payload",
    "fiber_seam_angle",
    "fiber_seam_position",
    "fiber_slow_length",
]

HYGIENE_PATHS = [
    ".gitignore",
    "checks",
    "docs",
    "resources/orcaslicer_codex/fiber_planner",
    "resources/profiles/TinManX1",
    "resources/profiles/TinManX1.json",
    "scripts/audit_fiberseek_gcode_contract.py",
    "scripts/check_tinmanx1_fiber_wiring.py",
    "scripts/compare_fiberseek_gcode.py",
    "scripts/generate_tinmanx1_fiberseek_profiles.py",
    "scripts/lint_tinmanx1_fiberseek_profiles.py",
    "scripts/orcaslicer_codex_native_fiber_planner.py",
    "scripts/smoke_orcaslicer_codex_native_fiber_planner.py",
    "src/libslic3r/Preset.cpp",
]

PRIVATE_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9_.-]+"),
    re.compile(r"~/Library/Application Support"),
    re.compile(r"Rocket Test Gcodes", re.IGNORECASE),
    re.compile(r"Monolith\.db", re.IGNORECASE),
    re.compile(r"app\.asar", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|auth[_-]?token|secret|password)\b\s*[:=]", re.IGNORECASE),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
]


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def run(command: list[str]) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=ROOT, check=True)


def compile_python() -> None:
    for name in PYTHON_FILES:
        path = ROOT / name
        if not path.exists():
            fail(f"missing Python file: {name}")
        py_compile.compile(str(path), doraise=True)
    print(f"Python syntax check passed for {len(PYTHON_FILES)} files.")


def check_preset_whitelist() -> None:
    path = ROOT / "src" / "libslic3r" / "Preset.cpp"
    text = path.read_text(encoding="utf-8", errors="ignore")
    missing = [key for key in REQUIRED_PRESET_WHITELIST_KEYS if key not in text]
    if missing:
        fail(f"Preset.cpp is missing FibreSeek whitelist keys: {', '.join(missing)}")
    print("Preset whitelist check passed.")


def iter_hygiene_files() -> list[Path]:
    files: list[Path] = []
    for name in HYGIENE_PATHS:
        path = ROOT / name
        if not path.exists():
            fail(f"missing release hygiene path: {name}")
        if path.is_file():
            files.append(path)
        else:
            files.extend(item for item in path.rglob("*") if item.is_file())
    return sorted(set(files))


def check_public_hygiene() -> None:
    offenders: list[str] = []
    self_path = Path(__file__).resolve()
    for path in iter_hygiene_files():
        if path.resolve() == self_path:
            continue
        if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".ico", ".icns"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for index, line in enumerate(text.splitlines(), start=1):
            for pattern in PRIVATE_PATTERNS:
                if pattern.search(line):
                    offenders.append(f"{rel(path)}:{index}: {line.strip()[:160]}")
                    break
    if offenders:
        fail("private/local release hygiene scan failed:\n" + "\n".join(offenders[:25]))

    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "outputs/fiberseek-local-validation.gcode"],
        cwd=ROOT,
        check=False,
    )
    if ignored.returncode != 0:
        fail("outputs/ is not ignored by git")
    tracked_outputs = subprocess.run(
        ["git", "ls-files", "outputs"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()
    if tracked_outputs:
        fail("outputs/ has tracked files:\n" + tracked_outputs)
    print("Public hygiene check passed.")


def main() -> int:
    compile_python()
    check_preset_whitelist()
    run([sys.executable, "scripts/check_tinmanx1_fiber_wiring.py"])
    run([sys.executable, "scripts/lint_tinmanx1_fiberseek_profiles.py"])
    run([sys.executable, "scripts/smoke_orcaslicer_codex_native_fiber_planner.py"])
    run([sys.executable, "scripts/compare_fiberseek_gcode.py", "--self-test"])
    check_public_hygiene()
    print("TinManX1 FibreSeek release verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
