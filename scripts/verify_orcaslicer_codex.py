#!/usr/bin/env python3
"""Verify the local TinManX1 installation.

This script intentionally checks installed local paths. It does not read or print
printer credentials, access codes, or full config files.
"""

from __future__ import annotations

import argparse
import json
import plistlib
import subprocess
import sys
from pathlib import Path


DEFAULT_APP = Path("/Applications/TinManX1.app")
DEFAULT_LEGACY_APP = Path("/Applications/TinManX TinManX1.app")
DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
EXPECTED_BUNDLE_ID = "com.tinmanfp.TinManX1"
EXPECTED_DISPLAY_NAME = "TinManX1"
LAUNCHER_NAMES = (
    "TinManX1",
    "OrcaSlicer",
)
BAMBU_PLUGINS = (
    "libBambuSource.dylib",
    "libbambu_networking_02.06.00.50.dylib",
)
FEATURE_RESOURCES = (
    "auto_pa/auto_pa.py",
    "auto_pa/tinman_auto_pa_postprocess.py",
    "auto_pa/visible_lanes/README.md",
    "auto_pa/visible_lanes/manifest.json",
    "auto_pa/visible_lanes/TINMAN_AUTO_PA_LANE_300_FRONT.3mf",
    "auto_pa/visible_lanes/TINMAN_AUTO_PA_LANE_300_REAR.3mf",
    "auto_pa/visible_lanes/TINMAN_AUTO_PA_LANE_500_FRONT.3mf",
    "auto_pa/visible_lanes/TINMAN_AUTO_PA_LANE_500_REAR.3mf",
    "arc_support/orcaslicer_codex_arc_support_inplace_adapter.py",
    "arc_support/orcaslicer_codex_arc_support_transform.py",
    "attribution/orcaslicer_codex_feature_attribution.md",
    "sidecars/orcaslicer_codex_fiber_metadata_sidecar.py",
    "sidecars/orcaslicer_codex_strength_lens_sidecar.py",
    "tools/repair_bambu_lan_bindings.py",
    "tools/repair_prusalink_bindings.py",
    "tools/sync_bambu_network_plugin.py",
    "tools/tinman-rtsp-bridge",
    "tools/FFmpeg-LGPL-2.1.txt",
    "motion_envelope/motion_envelope.py",
    "motion_envelope/registry.json",
    "motion_envelope/README.md",
    "third_party/gpl/arc-overhang/LICENSE",
    "third_party/gpl/arc-overhang/NOTICE.md",
    "third_party/gpl/arc-overhang/requirements.txt",
    "third_party/gpl/arc-overhang/softfever_slicer_post_processing_script.py",
)
FEATURE_ATTRIBUTION_MARKERS = (
    "SOLIDWORKS FEM",
    "Oak Ridge National Laboratory",
    "Strength Lens load axis",
    "stronger in X/Y than through the Z layer stack",
    "Auto Pressure Advance / Max Flow Preflight",
    "real same-print calibration score files",
)
FEATURE_BINARY_MARKERS = (
    "Strength Lens load axis",
    "Load axis:",
    "Testing the part through the layer stack",
    "Continuous fiber",
)
CRLF_SENSITIVE_RESOURCES = (
    "third_party/gpl/arc-overhang/softfever_slicer_post_processing_script.py",
)


class CheckState:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, message: str) -> None:
        print(f"OK: {message}")

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"WARN: {message}")

    def fail(self, message: str) -> None:
        self.failures.append(message)
        print(f"FAIL: {message}")


def run_text(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def read_plist(path: Path) -> dict:
    with path.open("rb") as fh:
        return plistlib.load(fh)


def binary_strings(path: Path) -> str:
    proc = run_text(["strings", str(path)])
    return proc.stdout if proc.returncode == 0 else ""


def file_description(path: Path) -> str:
    proc = run_text(["file", str(path)])
    return proc.stdout if proc.returncode == 0 else ""


def launcher_strings(path: Path) -> str:
    description = file_description(path)
    if "Mach-O" in description:
        return binary_strings(path)
    return path.read_text(errors="replace")


def find_launcher_pair(app: Path):
    macos_dir = app / "Contents" / "MacOS"
    for name in LAUNCHER_NAMES:
        launcher = macos_dir / name
        real = macos_dir / f"{name}.real"
        if launcher.exists() or real.exists():
            return launcher, real
    return None, None


def check_info(state: CheckState, app: Path, expected_version: str) -> None:
    info_path = app / "Contents" / "Info.plist"
    if not info_path.exists():
        state.fail(f"missing Info.plist: {info_path}")
        return

    info = read_plist(info_path)
    checks = {
        "CFBundleDisplayName": EXPECTED_DISPLAY_NAME,
        "CFBundleName": EXPECTED_DISPLAY_NAME,
        "CFBundleIdentifier": EXPECTED_BUNDLE_ID,
        "CFBundleShortVersionString": expected_version,
    }
    for key, expected in checks.items():
        actual = info.get(key)
        if actual == expected:
            state.ok(f"{key} is {expected}")
        else:
            state.fail(f"{key} expected {expected!r}, got {actual!r}")


def check_launcher(state: CheckState, app: Path, app_support: Path) -> None:
    launcher, real = find_launcher_pair(app)

    if launcher is None or not launcher.exists():
        state.fail(f"missing launcher in {app / 'Contents' / 'MacOS'}")
        return
    if real is None or not real.exists():
        state.fail(f"missing real executable next to launcher: {launcher}")
        return

    launcher_description = file_description(launcher)
    if "Mach-O" in launcher_description:
        state.ok("launcher is native Mach-O for Finder/Dock launch")
    else:
        state.fail(f"launcher is not a native Mach-O executable: {launcher_description.strip()}")

    text = launcher_strings(launcher)
    if str(app_support) in text or "OrcaSlicer-Codex" in text:
        state.ok("launcher points at OrcaSlicer-Codex data directory")
    else:
        state.fail("launcher does not appear to target OrcaSlicer-Codex")

    if "BAMBU_PLUGIN_POLICY" in text and "allow" in text:
        state.ok("launcher keeps Bambu plugin policy available")
    else:
        state.warn("launcher did not expose an allow-style Bambu plugin policy")

    if "repair_bambu_lan_bindings.py" in text:
        state.ok("launcher runs Bambu LAN binding repair helper")
    else:
        state.fail("launcher does not run Bambu LAN binding repair helper")

    if "repair_prusalink_bindings.py" in text:
        state.ok("launcher runs authenticated PrusaLink rediscovery and binding repair")
    else:
        state.fail("launcher does not run PrusaLink binding repair helper")

    if "sync_bambu_network_plugin.py" in text:
        state.ok("launcher can adopt a newer locally installed official Bambu network plug-in")
    else:
        state.fail("launcher does not run the local Bambu plug-in sync helper")

    if "orca_codex_launch_preflight.py" in text:
        state.fail("launcher still executes the mutable legacy launch preflight")
    else:
        state.ok("launcher does not execute the mutable legacy launch preflight")

    if real.stat().st_size > 1_000_000:
        state.ok("real executable is present and non-trivial")
    else:
        state.fail("real executable is unexpectedly small")


def check_executable_version(state: CheckState, app: Path, expected_version: str) -> None:
    _, real = find_launcher_pair(app)
    if real is None or not real.exists():
        state.fail("real executable missing; cannot check executable version")
        return
    text = binary_strings(real)
    expected_labels = (
        f"TinManX1 {expected_version}",
        f"TinManX1/{expected_version}",
        f"OrcaSlicer {expected_version}",
        f"OrcaSlicer/{expected_version}",
    )
    if any(label in text for label in expected_labels):
        state.ok(f"executable reports {expected_version}")
    else:
        state.fail(f"executable does not report {expected_version}")

    if expected_version == "2.3.2" and "OrcaSlicer 2.4.0-dev" in text:
        state.fail("executable still reports OrcaSlicer 2.4.0-dev")

    for marker in FEATURE_BINARY_MARKERS:
        if marker in text:
            state.ok(f"feature marker present in executable: {marker}")
        else:
            state.fail(f"missing feature marker in executable: {marker}")


def check_config(state: CheckState, app_support: Path, expected_version: str) -> None:
    config = app_support / "OrcaSlicer.conf"
    if not config.exists():
        state.warn(f"missing config: {config}")
        return

    try:
        data = json.loads(config.read_text(errors="replace"))
    except json.JSONDecodeError:
        state.fail("config is not parseable JSON")
        return

    expected_headers = {f"TinManX1 {expected_version}", f"OrcaSlicer {expected_version}"}
    if data.get("header") in expected_headers:
        state.ok(f"config header reports {data.get('header')}")
    else:
        state.warn(f"config header does not report TinManX1 {expected_version}")

    app = data.get("app", {})
    if isinstance(app, dict) and app.get("check_stable_update_only") is True:
        state.ok("config keeps stable-update-only guard enabled")
    else:
        state.fail("config stable-update-only guard is not enabled")


def check_bambu_plugins(state: CheckState, app_support: Path) -> None:
    plugin_dir = app_support / "plugins"
    if not plugin_dir.exists():
        state.fail(f"missing plugin directory: {plugin_dir}")
        return

    for name in BAMBU_PLUGINS:
        path = plugin_dir / name
        if path.exists():
            state.ok(f"Bambu plugin present: {name}")
        else:
            state.fail(f"Bambu plugin missing: {name}")


def check_feature_resources(state: CheckState, app: Path) -> None:
    resources = app / "Contents" / "Resources" / "orcaslicer_codex"
    if not resources.exists():
        state.fail(f"missing feature resources directory: {resources}")
        return

    for rel in FEATURE_RESOURCES:
        path = resources / rel
        if path.exists() and path.stat().st_size > 0:
            state.ok(f"feature resource present: {rel}")
            if rel == "tools/tinman-rtsp-bridge" and path.stat().st_mode & 0o111 == 0:
                state.fail("Prusa RTSP decoder is not executable")
        else:
            state.fail(f"missing feature resource: {rel}")

    attribution = resources / "attribution" / "orcaslicer_codex_feature_attribution.md"
    if attribution.exists():
        text = attribution.read_text(errors="replace")
        for marker in FEATURE_ATTRIBUTION_MARKERS:
            if marker in text:
                state.ok(f"feature attribution marker present: {marker}")
            else:
                state.fail(f"missing feature attribution marker: {marker}")

    for rel in CRLF_SENSITIVE_RESOURCES:
        path = resources / rel
        if path.exists() and b"\r\n" in path.read_bytes():
            state.fail(f"feature resource still has CRLF line endings: {rel}")
        elif path.exists():
            state.ok(f"feature resource uses LF line endings: {rel}")


def check_legacy_app_separation(state: CheckState, app: Path, legacy_app: Path) -> None:
    if not legacy_app.exists():
        state.ok(f"legacy TinManX app is absent: {legacy_app}")
        return
    if legacy_app.is_symlink():
        state.fail(f"legacy TinManX app is a symlink to {legacy_app.resolve()}")
    else:
        state.ok("legacy TinManX app is not a symlink")

    try:
        if legacy_app.resolve() == app.resolve():
            state.fail("legacy TinManX app resolves to the current TinManX1 app")
        else:
            state.ok("legacy TinManX and current TinManX1 are separate app bundles")
    except FileNotFoundError:
        state.warn("could not resolve legacy TinManX app path")


def check_codesign(state: CheckState, app: Path) -> None:
    proc = run_text(["codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
    if proc.returncode == 0:
        state.ok("codesign verification passes")
    else:
        state.fail("codesign verification failed")
        if proc.stderr.strip():
            print(proc.stderr.strip())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, default=DEFAULT_APP)
    parser.add_argument(
        "--legacy-app",
        "--tinmanx-app",
        dest="legacy_app",
        type=Path,
        default=DEFAULT_LEGACY_APP,
        help="obsolete app bundle that must not alias the current TinManX1 installation",
    )
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--expected-version", default="2.4.2")
    parser.add_argument("--codesign", action="store_true")
    args = parser.parse_args()

    state = CheckState()
    if not args.app.exists():
        state.fail(f"TinManX1 app missing: {args.app}")
    elif args.app.is_symlink():
        state.fail(f"TinManX1 app is a symlink: {args.app}")
    else:
        state.ok(f"TinManX1 app exists: {args.app}")

    check_info(state, args.app, args.expected_version)
    check_launcher(state, args.app, args.app_support)
    check_executable_version(state, args.app, args.expected_version)
    check_config(state, args.app_support, args.expected_version)
    check_bambu_plugins(state, args.app_support)
    check_feature_resources(state, args.app)
    check_legacy_app_separation(state, args.app, args.legacy_app)
    if args.codesign:
        check_codesign(state, args.app)

    if state.warnings:
        print(f"\nWarnings: {len(state.warnings)}")
    if state.failures:
        print(f"\nFailures: {len(state.failures)}")
        return 1
    print("\nVerification passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
