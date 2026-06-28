#!/usr/bin/env python3
"""Verify the public TinManX1 release package."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "README.md",
    "ATTRIBUTION.md",
    "NOTICE.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "LICENSE",
    "docs/release-scope.md",
    "docs/features/native-fiber-planner.md",
    "docs/features/strength-lens.md",
    "docs/features/wave-overhangs.md",
    "docs/features/arc-supports.md",
    "docs/features/backend-improvements.md",
    "docs/audit/tinmanx1-houseclean-2026-06-26.md",
    "docs/audit/tinmanx1-hole-cluster-fiber-2026-06-27.md",
    "docs/audit/tinmanx1-hole-loop-guard-2026-06-27.md",
    "checks/golden/native_fiber_planner_golden.json",
    ".github/workflows/validate_public_helpers.yml",
    "patches/tinmanx1-v2.4.0-houseclean-native-fiber.patch",
    "scripts/source-helpers/audit_fiberseek_gcode_contract.py",
    "scripts/source-helpers/build_tinmanx1_fiber_layup_payload.py",
    "scripts/source-helpers/check_tinmanx1_fiber_wiring.py",
    "scripts/source-helpers/compare_fiberseek_gcode.py",
    "scripts/source-helpers/golden_orcaslicer_codex_native_fiber_planner.py",
    "scripts/source-helpers/generate_tinmanx1_fiberseek_profiles.py",
    "scripts/source-helpers/lint_tinmanx1_fiberseek_profiles.py",
    "scripts/source-helpers/orcaslicer_codex_native_fiber_planner.py",
    "scripts/source-helpers/smoke_orcaslicer_codex_native_fiber_planner.py",
]

ATTRIBUTION_MARKERS = [
    "William Tinney",
    "OpenAI Codex",
    "SoftFever",
    "OrcaSlicer",
    "Bambu Studio",
    "Bambu Lab",
    "PrusaSlicer",
    "Prusa Research",
    "Slic3r",
    "Dennis Klappe",
    "Steven McCulloch",
    "Nicolai Wachenschwan",
    "Kelsch",
    "Klipper",
    "Moonraker",
    "CNC Kitchen",
    "ModBot",
    "MechaniCalc",
    "FibreSeek",
]

PRIVATE_PATTERNS = [
    re.compile(r"/Users/[A-Za-z0-9._-]+"),
    re.compile(r"\bwilliamtinney\b", re.IGNORECASE),
    re.compile(r"\b192\.168\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b10\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b172\.(?:1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"\b100\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
    re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
    re.compile(
        r"(?i)\b(?:password|passwd|token|secret|api[_-]?key|access[_-]?code)\b\s*[:=]\s*['\"][^'\"]+['\"]"
    ),
]

SKIP_SCAN = {
    ".git",
    "__pycache__",
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_SCAN for part in path.relative_to(ROOT).parts):
            continue
        if path.relative_to(ROOT).as_posix() == "checks/verify_release.py":
            continue
        files.append(path)
    return files


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing required file: {rel}")
        elif path.stat().st_size == 0:
            errors.append(f"required file is empty: {rel}")

    license_text = (ROOT / "LICENSE").read_text(errors="replace")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in license_text:
        errors.append("LICENSE does not look like AGPL")

    attribution_text = (ROOT / "ATTRIBUTION.md").read_text(errors="replace")
    for marker in ATTRIBUTION_MARKERS:
        if marker not in attribution_text:
            errors.append(f"missing attribution marker: {marker}")

    for patch in (ROOT / "patches").glob("*.patch"):
        if patch.stat().st_size < 1024:
            errors.append(f"patch file is unexpectedly small: {patch.name}")

    for path in iter_files():
        try:
            text = path.read_text(errors="replace")
        except UnicodeDecodeError:
            errors.append(f"binary-looking file included: {path.relative_to(ROOT)}")
            continue
        for pattern in PRIVATE_PATTERNS:
            if pattern.search(text):
                errors.append(f"private/sensitive pattern in {path.relative_to(ROOT)}: {pattern.pattern}")
                break

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("release verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
