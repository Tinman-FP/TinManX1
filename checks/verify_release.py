#!/usr/bin/env python3
"""Verify the public TinManX1 release package."""

from __future__ import annotations

import json
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
    "docs/features/fiber-layup-editor.md",
    "docs/features/strength-lens.md",
    "docs/features/wave-overhangs.md",
    "docs/features/arc-supports.md",
    "docs/features/backend-improvements.md",
    "docs/audit/tinmanx1-houseclean-2026-06-26.md",
    "docs/audit/tinmanx1-hole-cluster-fiber-2026-06-27.md",
    "docs/audit/tinmanx1-hole-loop-guard-2026-06-27.md",
    "docs/audit/tinmanx1-architecture-hardening-2026-08-04.md",
    "checks/contracts/fiber_layup_editor_contract.json",
    "checks/golden/native_fiber_planner_golden.json",
    "checks/verify_tinman_machine_profile_catalog.py",
    "manifests/tinmanx1-profile-resources.sha256",
    ".github/workflows/validate_public_helpers.yml",
    ".github/workflows/winget_updater.yml",
    "patches/tinmanx1-v2.4.2-houseclean-native-fiber.patch",
    "resources/profiles/TinManX1.json",
    "resources/profiles/TinManX1/machine/FibreSeek Seeker 3 0.4+0.7 composite nozzle.json",
    "resources/profiles/TinManX1/process/0.20mm Plastic + Continuous Fiber Heavy @FibreSeek Seeker 3 0.4+0.7 nozzle.json",
    "resources/profiles/TinManX1/filament/TinManX1 PETG @FibreSeek Seeker 3.json",
    "resources/profiles/TinManX1/filament/CFC PETG + X-CCF @FibreSeek Seeker 3.json",
    "scripts/source-helpers/audit_fiberseek_gcode_contract.py",
    "scripts/source-helpers/orcaslicer_codex_arc_support_inplace_adapter.py",
    "scripts/source-helpers/orcaslicer_codex_arc_support_transform.py",
    "scripts/source-helpers/orcaslicer_codex_fiber_metadata_sidecar.py",
    "scripts/source-helpers/orcaslicer_codex_strength_lens_sidecar.py",
    "scripts/source-helpers/build_tinmanx1_fiber_layup_payload.py",
    "scripts/source-helpers/check_tinmanx1_fiber_wiring.py",
    "scripts/source-helpers/compare_fiberseek_gcode.py",
    "scripts/source-helpers/golden_orcaslicer_codex_native_fiber_planner.py",
    "scripts/source-helpers/generate_tinmanx1_fiberseek_profiles.py",
    "scripts/source-helpers/lint_tinmanx1_fiberseek_profiles.py",
    "scripts/source-helpers/normalize_tinman_machine_catalog.py",
    "scripts/source-helpers/tinman_profile_manifest.py",
    "src/libslic3r/TinManMachineProfileContract.cpp",
    "src/libslic3r/TinManMachineProfileContract.hpp",
    "tests/libslic3r/test_tinman_machine_profile_contract.cpp",
    "scripts/source-helpers/orcaslicer_codex_native_fiber_planner.py",
    "scripts/source-helpers/smoke_orcaslicer_codex_native_fiber_planner.py",
    "scripts/source-helpers/validate_tinmanx1_fiber_layup_editor_contract.py",
]

MIRRORED_RUNTIME_HELPERS = [
    (
        "scripts/source-helpers/orcaslicer_codex_arc_support_inplace_adapter.py",
        "resources/orcaslicer_codex/arc_support/orcaslicer_codex_arc_support_inplace_adapter.py",
    ),
    (
        "scripts/source-helpers/orcaslicer_codex_arc_support_transform.py",
        "resources/orcaslicer_codex/arc_support/orcaslicer_codex_arc_support_transform.py",
    ),
    (
        "scripts/source-helpers/orcaslicer_codex_fiber_metadata_sidecar.py",
        "resources/orcaslicer_codex/sidecars/orcaslicer_codex_fiber_metadata_sidecar.py",
    ),
    (
        "scripts/source-helpers/orcaslicer_codex_native_fiber_planner.py",
        "resources/orcaslicer_codex/fiber_planner/orcaslicer_codex_native_fiber_planner.py",
    ),
    (
        "scripts/source-helpers/orcaslicer_codex_strength_lens_sidecar.py",
        "resources/orcaslicer_codex/sidecars/orcaslicer_codex_strength_lens_sidecar.py",
    ),
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
    ".venv",
    "venv",
    "arc-support-venv",
}

PUBLIC_SCAN_PATHS = [
    ".github/workflows/validate_public_helpers.yml",
    "README.md",
    "ATTRIBUTION.md",
    "NOTICE.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "checks",
    "docs",
    "manifests",
    "patches",
    "resources/orcaslicer_codex",
    "resources/profiles/Codex",
    "resources/profiles/Qidi/machine",
    "resources/profiles/TinManX1",
    "resources/profiles/TinManX1.json",
    "resources/profiles/polymaker",
    "scripts",
    "version.inc",
]

PUBLIC_LINE_ALLOWLIST = {
    "patches/tinmanx1-v2.4.2-houseclean-native-fiber.patch": [
        re.compile(r'^-DEFAULT_HOST = "192\.168\.88\.9"$'),
    ],
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for rel in PUBLIC_SCAN_PATHS:
        root = ROOT / rel
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else root.rglob("*")
        for path in candidates:
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

    k2_profile_dir = ROOT / "resources/profiles/Creality/machine/TinMan Codex"
    forbidden_k2_startup = (
        "BOX_ENABLE_CFS_PRINT",
        "CFS_SLOT",
        "CODEX_CFS_SELECT",
        "CODEX_REQUIRE_FILAMENT",
    )
    for nozzle in ("0.4", "0.6", "0.8", "1.0"):
        k2_profile = k2_profile_dir / f"Creality K2 Plus {nozzle} nozzle - TinMan Codex.json"
        if not k2_profile.is_file():
            errors.append(f"missing TinMan K2 profile: {k2_profile.relative_to(ROOT)}")
            continue
        k2_data = json.loads(k2_profile.read_text())
        if "machine_start_gcode" in k2_data:
            errors.append(f"{k2_profile.name} must inherit Creality's native startup sequence")
        profile_text = k2_profile.read_text()
        for token in forbidden_k2_startup:
            if token in profile_text:
                errors.append(f"{k2_profile.name} contains obsolete K2 startup token {token}")

    k2_gcode_source = (ROOT / "src/libslic3r/GCode.cpp").read_text()
    for marker in (
        "is_creality_k2_printer",
        "sanitize_legacy_k2_cfs_start_gcode",
        "is_bbl_printers || is_creality_k2_printer",
    ):
        if marker not in k2_gcode_source:
            errors.append(f"K2 G-code export contract is missing {marker}")

    k2_transport_source = (ROOT / "src/slic3r/Utils/CrealityPrint.cpp").read_text()
    start_print_pos = k2_transport_source.find("bool CrealityPrint::start_print")
    k2_handoff_source = k2_transport_source[start_print_pos:] if start_print_pos >= 0 else ""
    transport_markers = ("colorMatch", "retGcodeFileInfo2", "multiColorPrint")
    positions = [k2_handoff_source.find(marker) for marker in transport_markers]
    if any(position < 0 for position in positions) or positions != sorted(positions):
        errors.append("K2 native CFS handoff must validate colorMatch metadata before multiColorPrint")

    prusa_filament = ROOT / (
        "resources/profiles/Codex/filament/"
        "PC-PBT-CF Codex-Push Plastic - Prusa CORE One L @Codex.json"
    )
    prusa_machine = ROOT / (
        "resources/profiles/Prusa/machine/Prusa CORE One L HF 0.4 nozzle.json"
    )
    if prusa_filament.is_file():
        filament_data = json.loads(prusa_filament.read_text())
        if filament_data.get("filament_type") != ["PCPBTCF"]:
            errors.append("CORE One L PC-PBT-CF must emit the native PCPBTCF token")
    if prusa_machine.is_file():
        machine_data = json.loads(prusa_machine.read_text())
        start_gcode = machine_data.get("machine_start_gcode", "")
        if isinstance(start_gcode, list):
            start_gcode = start_gcode[0] if start_gcode else ""
        pc_class_check = (
            'filament_type[0] == "PC" or filament_type[0] == "PCPBTCF" '
            'or filament_type[0] == "PA"'
        )
        if start_gcode.count(pc_class_check) != 3:
            errors.append(
                "CORE One L startup must classify PCPBTCF as PC for all three MBL temperature checks"
            )

    qidi_common = ROOT / "resources/profiles/Qidi/machine/fdm_qidi_x3_common.json"
    if qidi_common.is_file():
        qidi_data = json.loads(qidi_common.read_text())
        if qidi_data.get("host_type") != "moonraker":
            errors.append("Qidi Klipper profiles must use Moonraker instead of OctoPrint")

    connection_contract = (ROOT / "src/libslic3r/TinManMachineProfileContract.cpp").read_text(
        errors="replace"
    )
    for marker in (
        'model == "Qidi X-Plus 4" || model == "QidiMaxEz"',
        'value = "moonraker";',
    ):
        if marker not in connection_contract:
            errors.append(f"Qidi connection contract is missing marker: {marker}")

    gui_app = (ROOT / "src/slic3r/GUI/GUI_App.cpp").read_text(errors="replace")
    shutdown_body = gui_app[gui_app.find("void GUI_App::shutdown()") : gui_app.find("GUI_App::~GUI_App()")]
    for marker in (
        "NetworkAgentFactory::clear_printer_agent_cache();",
        "BBLNetworkPlugin::shutdown();",
    ):
        if marker not in shutdown_body:
            errors.append(f"early network shutdown is missing marker: {marker}")

    gui_app_header = (ROOT / "src/slic3r/GUI/GUI_App.hpp").read_text(errors="replace")
    if "m_shutdown_started" not in gui_app_header:
        errors.append("GUI shutdown must use state separate from the close-request flag")
    if "m_shutdown_started.compare_exchange_strong" not in shutdown_body:
        errors.append("GUI shutdown is missing its one-time execution guard")
    if "m_is_closing.compare_exchange_strong" in shutdown_body:
        errors.append("GUI shutdown must not use the pre-set close-request flag as its execution guard")

    for rel in REQUIRED_FILES:
        path = ROOT / rel
        if not path.is_file():
            errors.append(f"missing required file: {rel}")
        elif path.stat().st_size == 0:
            errors.append(f"required file is empty: {rel}")

    for source_rel, runtime_rel in MIRRORED_RUNTIME_HELPERS:
        source = ROOT / source_rel
        runtime = ROOT / runtime_rel
        if source.is_file() and runtime.is_file() and source.read_bytes() != runtime.read_bytes():
            errors.append(f"packaged helper drift: {runtime_rel} differs from {source_rel}")

    license_text = (ROOT / "LICENSE").read_text(errors="replace")
    if "GNU AFFERO GENERAL PUBLIC LICENSE" not in license_text:
        errors.append("LICENSE does not look like AGPL")

    attribution_text = (ROOT / "ATTRIBUTION.md").read_text(errors="replace")
    for marker in ATTRIBUTION_MARKERS:
        if marker not in attribution_text:
            errors.append(f"missing attribution marker: {marker}")

    version_text = (ROOT / "version.inc").read_text(errors="replace")
    revision_match = re.search(r'set\(TINMANX1_REVISION\s+"([^"]+)"\)', version_text)
    if revision_match is None:
        errors.append("version.inc does not define TINMANX1_REVISION")
    else:
        revision = revision_match.group(1)
        for rel in (
            "resources/images/splash_logo.svg",
            "resources/images/splash_logo_dark.svg",
            "resources/images/TinManX1_about.svg",
            "resources/images/TinManX1_about_dark.svg",
        ):
            artwork = ROOT / rel
            if not artwork.is_file():
                errors.append(f"missing versioned artwork: {rel}")
            elif f"TinManX1 Revision {revision}" not in artwork.read_text(errors="replace"):
                errors.append(f"{rel} does not match TINMANX1_REVISION {revision}")

    package_match = re.search(
        r'set\(TINMANX1_PACKAGE_VERSION\s+"(\d+)\.(\d+)\.(\d+)\.(\d+)"\)',
        version_text,
    )
    if package_match is None:
        errors.append("version.inc does not define a four-part TINMANX1_PACKAGE_VERSION")
    else:
        package_version = ".".join(package_match.groups())
        if any(int(component) > 65535 for component in package_match.groups()):
            errors.append(f"TINMANX1_PACKAGE_VERSION exceeds Windows limits: {package_version}")

        release_contracts = {
            "CMakeLists.txt": [
                'CPACK_PACKAGE_VERSION "${TINMANX1_PACKAGE_VERSION}"',
                'TinManX1_Windows_Installer_V${TINMANX1_PACKAGE_VERSION}',
            ],
            "src/dev-utils/platform/msw/OrcaSlicer.rc.in": [
                'VALUE "CompanyName", "Tinman-FP"',
                'VALUE "ProductVersion", "@TINMANX1_PACKAGE_VERSION@"',
            ],
            "src/dev-utils/platform/msw/OrcaSlicer-gcodeviewer.rc.in": [
                'VALUE "CompanyName", "Tinman-FP"',
                'VALUE "ProductVersion", "@TINMANX1_PACKAGE_VERSION@"',
            ],
            "scripts/msix/build_msix.ps1": [
                'TINMANX1_PACKAGE_VERSION',
                '$msixVersion = "$($Matches[1]).$($Matches[2]).$($Matches[3]).0"',
            ],
            "src/dev-utils/platform/unix/build_appimage.sh.in": [
                '@SLIC3R_APP_NAME@_Linux_V@TINMANX1_PACKAGE_VERSION@.AppImage',
            ],
            "src/dev-utils/platform/unix/build_linux_image.sh.in": [
                '@SLIC3R_APP_NAME@_Linux_V@TINMANX1_PACKAGE_VERSION@.AppImage',
            ],
            ".github/workflows/winget_updater.yml": [
                "identifier: TinmanFP.TinManX1",
                "WINGET_AUTOMATION_ENABLED",
                "secrets.WINGET_TOKEN",
                "TINMANX1_PACKAGE_VERSION",
            ],
            ".github/workflows/build_orca.yml": [
                "grep '^set(TINMANX1_PACKAGE_VERSION \"' version.inc",
                'TinManX1_Linux_V${{ env.ver_pure }}.AppImage',
                "choco install nsis --yes --no-progress",
                "NSIS was not available after 3 install attempts",
            ],
            ".github/workflows/build_all.yml": [
                "grep '^set(TINMANX1_PACKAGE_VERSION \"' version.inc",
                "- tinmanx1-v2.4.2-rebase",
                "comment_mode: off",
            ],
            ".github/workflows/publish_release.yml": [
                "-p 'TinManX1_Linux_ubuntu_*'",
            ],
        }
        for rel, markers in release_contracts.items():
            contract_text = (ROOT / rel).read_text(errors="replace")
            for marker in markers:
                if marker not in contract_text:
                    errors.append(f"{rel} is missing package contract marker: {marker}")

        winget_text = (ROOT / ".github/workflows/winget_updater.yml").read_text(errors="replace")
        for forbidden in ("SoftFever.OrcaSlicer", "winget-releaser@main"):
            if forbidden in winget_text:
                errors.append(f"WinGet workflow contains inherited or mutable reference: {forbidden}")

    for patch in (ROOT / "patches").glob("*.patch"):
        if patch.stat().st_size < 1024:
            errors.append(f"patch file is unexpectedly small: {patch.name}")

    for path in iter_files():
        try:
            text = path.read_text(errors="replace")
        except UnicodeDecodeError:
            errors.append(f"binary-looking file included: {path.relative_to(ROOT)}")
            continue
        relative = path.relative_to(ROOT).as_posix()
        allowed_lines = PUBLIC_LINE_ALLOWLIST.get(relative, [])
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(allowed.fullmatch(line) for allowed in allowed_lines):
                continue
            for pattern in PRIVATE_PATTERNS:
                if pattern.search(line):
                    errors.append(
                        f"private/sensitive pattern in {relative}:{line_number}: {pattern.pattern}"
                    )
                    break

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("release verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
