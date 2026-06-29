#!/usr/bin/env python3
"""Install a locally built OrcaSlicer bundle as TinManX1.

The installer preserves the TinManX1 app identity and data directory while swapping
in a freshly built OrcaSlicer executable/resources bundle.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import plistlib
import shutil
import stat
import subprocess
import sys
from pathlib import Path


EXPECTED_TARGET_NAME = "TinManX1"
EXPECTED_BUNDLE_ID = "com.orcaslicer.OrcaSlicerCodex"
DEFAULT_TARGET_APP = Path("/Applications/TinManX1.app")
DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"


def repo_defaults() -> tuple[Path, Path]:
    control_root = Path(__file__).resolve().parents[1]
    work_root = control_root.parent
    source_root = work_root / "TinManX1-source-v2.4.0"
    built_apps = [
        source_root / "build" / "arm64" / "src" / "Release" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "src" / "RelWithDebInfo" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "src" / "Debug" / "OrcaSlicer.app",
        source_root / "build" / "arm64" / "OrcaSlicer" / "OrcaSlicer.app",
    ]
    built_app = next(
        (app for app in built_apps if (app / "Contents" / "MacOS" / "OrcaSlicer").exists()),
        built_apps[-1],
    )
    return source_root, built_app


def run(args: list[str]) -> None:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        if proc.stdout:
            print(proc.stdout)
        if proc.stderr:
            print(proc.stderr, file=sys.stderr)
        raise SystemExit(proc.returncode)


def copy_optional_file(src: Path, dst: Path) -> None:
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def copy_optional_tree(src: Path, dst: Path) -> None:
    if src.exists():
        if dst.exists():
            shutil.rmtree(dst)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, symlinks=True)


def install_feature_resources(source_root: Path, app: Path) -> None:
    resources = app / "Contents" / "Resources" / "orcaslicer_codex"
    arc_support = resources / "arc_support"
    sidecars = resources / "sidecars"

    copy_optional_file(
        source_root / "scripts" / "orcaslicer_codex_arc_support_inplace_adapter.py",
        arc_support / "orcaslicer_codex_arc_support_inplace_adapter.py",
    )
    copy_optional_file(
        source_root / "scripts" / "orcaslicer_codex_arc_support_transform.py",
        arc_support / "orcaslicer_codex_arc_support_transform.py",
    )
    copy_optional_tree(
        source_root / "third_party" / "gpl" / "arc-overhang",
        resources / "third_party" / "gpl" / "arc-overhang",
    )
    copy_optional_file(
        source_root / "scripts" / "orcaslicer_codex_strength_lens_sidecar.py",
        sidecars / "orcaslicer_codex_strength_lens_sidecar.py",
    )
    copy_optional_file(
        source_root / "scripts" / "orcaslicer_codex_fiber_metadata_sidecar.py",
        sidecars / "orcaslicer_codex_fiber_metadata_sidecar.py",
    )
    copy_optional_file(
        source_root / "SoftFever_doc" / "orcaslicer_codex_feature_attribution.md",
        resources / "attribution" / "orcaslicer_codex_feature_attribution.md",
    )


def update_info_plist(app: Path) -> str:
    info_path = app / "Contents" / "Info.plist"
    with info_path.open("rb") as fh:
        info = plistlib.load(fh)

    version = str(info.get("CFBundleShortVersionString") or "2.4.0-alpha")
    info["CFBundleName"] = EXPECTED_TARGET_NAME
    info["CFBundleDisplayName"] = EXPECTED_TARGET_NAME
    info["CFBundleIdentifier"] = EXPECTED_BUNDLE_ID
    info["CFBundleExecutable"] = "OrcaSlicer"
    info["CFBundleShortVersionString"] = version

    with info_path.open("wb") as fh:
        plistlib.dump(info, fh, sort_keys=False)
    return version


def write_launcher(app: Path, app_support: Path) -> None:
    macos_dir = app / "Contents" / "MacOS"
    launcher = macos_dir / "OrcaSlicer"
    real = macos_dir / "OrcaSlicer.real"

    if real.exists():
        real.unlink()
    launcher.rename(real)

    script = f"""#!/bin/sh
DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
DATADIR="${{ORCASLICER_CODEX_DATADIR:-{app_support}}}"
PREFLIGHT="$DATADIR/tools/orca_codex_launch_preflight.py"
PYTHON_BIN="${{ORCASLICER_CODEX_PYTHON:-/usr/bin/python3}}"
LIVE_GUARD_SECONDS="${{ORCASLICER_CODEX_LIVE_GUARD_SECONDS:-300}}"
LIVE_GUARD_TICK_SECONDS="${{ORCASLICER_CODEX_LIVE_GUARD_TICK_SECONDS:-5}}"
: "${{ORCASLICER_CODEX_BAMBU_PLUGIN_POLICY:=allow}}"
export ORCASLICER_CODEX_BAMBU_PLUGIN_POLICY

# CAD tools such as Autodesk Fusion can leave Python runtime variables in the
# launch environment. TinManX1 helper planners must use a clean interpreter.
unset PYTHONHOME
unset PYTHONPATH

run_preflight() {{
  PYTHONHOME= PYTHONPATH= "$PYTHON_BIN" "$PREFLIGHT" "$@"
}}

if [ -x "$PREFLIGHT" ]; then
  mkdir -p "$DATADIR" 2>/dev/null || true
  run_preflight \\
    --app-support "$DATADIR" \\
    --summary "$DATADIR/_orcaslicer_codex_launch_preflight_last.json" \\
    > "$DATADIR/_orcaslicer_codex_launch_preflight_last.out" \\
    2> "$DATADIR/_orcaslicer_codex_launch_preflight_last.err" || true
fi

ORCA_STARTED_EPOCH="$(date +%s)"
"$DIR/OrcaSlicer.real" --datadir "$DATADIR" "$@" &
ORCA_PID=$!
LAST_GUARD_EPOCH="$ORCA_STARTED_EPOCH"

while kill -0 "$ORCA_PID" 2>/dev/null; do
  sleep "$LIVE_GUARD_TICK_SECONDS"
  NOW_EPOCH="$(date +%s)"
  if kill -0 "$ORCA_PID" 2>/dev/null && \\
     [ -x "$PREFLIGHT" ] && \\
     [ $((NOW_EPOCH - LAST_GUARD_EPOCH)) -ge "$LIVE_GUARD_SECONDS" ]; then
    run_preflight \\
      --app-support "$DATADIR" \\
      --summary "$DATADIR/_orcaslicer_codex_launch_live_guard_last.json" \\
      --skip-validator \\
      > "$DATADIR/_orcaslicer_codex_launch_live_guard_last.out" \\
      2> "$DATADIR/_orcaslicer_codex_launch_live_guard_last.err" || true
    LAST_GUARD_EPOCH="$NOW_EPOCH"
  fi
done

wait "$ORCA_PID"
STATUS=$?
if [ -x "$PREFLIGHT" ]; then
  ORCASLICER_CODEX_SESSION_START_EPOCH="$ORCA_STARTED_EPOCH" run_preflight \\
    --app-support "$DATADIR" \\
    --summary "$DATADIR/_orcaslicer_codex_launch_postflight_last.json" \\
    > "$DATADIR/_orcaslicer_codex_launch_postflight_last.out" \\
    2> "$DATADIR/_orcaslicer_codex_launch_postflight_last.err" || true
fi
exit "$STATUS"
"""
    launcher.write_text(script)
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def preserve_existing_identity_assets(existing_app: Path, staged_app: Path) -> None:
    copy_optional_file(
        existing_app / "Contents" / "Resources" / "Icon.icns",
        staged_app / "Contents" / "Resources" / "Icon.icns",
    )


def main() -> int:
    source_root, built_app = repo_defaults()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=source_root)
    parser.add_argument("--source-app", type=Path, default=built_app)
    parser.add_argument("--target-app", type=Path, default=DEFAULT_TARGET_APP)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--stage-dir", type=Path, default=Path("/tmp/TinManX1-install-stage"))
    parser.add_argument("--skip-codesign", action="store_true")
    args = parser.parse_args()

    if not args.source_app.exists():
        raise SystemExit(f"source app not found: {args.source_app}")
    if args.target_app.name != f"{EXPECTED_TARGET_NAME}.app":
        raise SystemExit(f"refusing unexpected target app path: {args.target_app}")

    staged_app = args.stage_dir / args.target_app.name
    if staged_app.exists():
        shutil.rmtree(staged_app)
    args.stage_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(args.source_app, staged_app, symlinks=False)

    if args.target_app.exists():
        preserve_existing_identity_assets(args.target_app, staged_app)

    version = update_info_plist(staged_app)
    write_launcher(staged_app, args.app_support)
    install_feature_resources(args.source_root, staged_app)

    if not args.skip_codesign:
        run(["codesign", "--force", "--deep", "--sign", "-", str(staged_app)])

    backup_path = None
    if args.target_app.exists():
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = args.target_app.with_name(f"{args.target_app.name}.backup-{timestamp}")
        args.target_app.rename(backup_path)

    try:
        shutil.move(str(staged_app), str(args.target_app))
        run(["xattr", "-dr", "com.apple.quarantine", str(args.target_app)])
    except Exception:
        if args.target_app.exists():
            shutil.rmtree(args.target_app)
        if backup_path and backup_path.exists():
            backup_path.rename(args.target_app)
        raise

    print(f"Installed {args.target_app}")
    print(f"Source {args.source_app}")
    print(f"Version {version}")
    if backup_path:
        print(f"Backup {backup_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
