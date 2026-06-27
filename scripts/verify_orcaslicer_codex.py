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
DEFAULT_TINMANX_APP = Path("/Applications/TinManX TinManX1.app")
DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
EXPECTED_BUNDLE_ID = "com.orcaslicer.OrcaSlicerCodex"
EXPECTED_DISPLAY_NAME = "TinManX1"
BAMBU_PLUGINS = (
    "libBambuSource.dylib",
    "libbambu_networking_02.06.00.50.dylib",
)
FEATURE_RESOURCES = (
    "arc_support/orcaslicer_codex_arc_support_inplace_adapter.py",
    "arc_support/orcaslicer_codex_arc_support_transform.py",
    "attribution/orcaslicer_codex_feature_attribution.md",
    "sidecars/orcaslicer_codex_fiber_metadata_sidecar.py",
    "sidecars/orcaslicer_codex_strength_lens_sidecar.py",
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
    launcher = app / "Contents" / "MacOS" / "OrcaSlicer"
    real = app / "Contents" / "MacOS" / "OrcaSlicer.real"

    if not launcher.exists():
        state.fail(f"missing launcher: {launcher}")
        return
    if not real.exists():
        state.fail(f"missing real executable: {real}")
        return

    text = launcher.read_text(errors="replace")
    if str(app_support) in text or "OrcaSlicer-Codex" in text:
        state.ok("launcher points at OrcaSlicer-Codex data directory")
    else:
        state.fail("launcher does not appear to target OrcaSlicer-Codex")

    if "BAMBU_PLUGIN_POLICY" in text and "allow" in text:
        state.ok("launcher keeps Bambu plugin policy available")
    else:
        state.warn("launcher did not expose an allow-style Bambu plugin policy")

    if real.stat().st_size > 1_000_000:
        state.ok("real executable is present and non-trivial")
    else:
        state.fail("real executable is unexpectedly small")


def check_executable_version(state: CheckState, app: Path, expected_version: str) -> None:
    real = app / "Contents" / "MacOS" / "OrcaSlicer.real"
    text = binary_strings(real)
    expected_label = f"OrcaSlicer {expected_version}"
    if expected_label in text or f"OrcaSlicer/{expected_version}" in text:
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

    expected_header = f"OrcaSlicer {expected_version}"
    if data.get("header") == expected_header:
        state.ok(f"config header reports OrcaSlicer {expected_version}")
    else:
        state.warn(f"config header does not report OrcaSlicer {expected_version}")

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


def check_tinmanx_separation(state: CheckState, app: Path, tinmanx_app: Path) -> None:
    if not tinmanx_app.exists():
        state.warn(f"TinManX app not found: {tinmanx_app}")
        return
    if tinmanx_app.is_symlink():
        state.fail(f"TinManX app is a symlink to {tinmanx_app.resolve()}")
    else:
        state.ok("TinManX app is not a symlink")

    try:
        if tinmanx_app.resolve() == app.resolve():
            state.fail("TinManX app resolves to the Codex app")
        else:
            state.ok("TinManX and Codex resolve to different app bundles")
    except FileNotFoundError:
        state.warn("could not resolve TinManX app path")


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
    parser.add_argument("--tinmanx-app", type=Path, default=DEFAULT_TINMANX_APP)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--expected-version", default="2.4.0-alpha")
    parser.add_argument("--codesign", action="store_true")
    args = parser.parse_args()

    state = CheckState()
    if not args.app.exists():
        state.fail(f"Codex app missing: {args.app}")
    elif args.app.is_symlink():
        state.fail(f"Codex app is a symlink: {args.app}")
    else:
        state.ok(f"Codex app exists: {args.app}")

    check_info(state, args.app, args.expected_version)
    check_launcher(state, args.app, args.app_support)
    check_executable_version(state, args.app, args.expected_version)
    check_config(state, args.app_support, args.expected_version)
    check_bambu_plugins(state, args.app_support)
    check_feature_resources(state, args.app)
    check_tinmanx_separation(state, args.app, args.tinmanx_app)
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
