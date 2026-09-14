#!/usr/bin/env python3
"""Adopt a newer official Bambu networking plug-in already installed locally.

TinManX1 does not redistribute Bambu's proprietary networking binaries. On
macOS, this launch helper may copy a newer compatible plug-in set from the
user's installed Bambu Studio into TinManX1's private data directory.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import mmap
import os
import pathlib
import re
import shutil
import sys


PLUGIN_NAMES = ("libBambuSource.dylib", "liblive555.dylib")
FRAMEWORK_NAMES = (
    "AgoraCore.framework",
    "AgoraRtcKit.framework",
    "AgoraSoundTouch.framework",
    "Agoraffmpeg.framework",
)
VERSION_PATTERN = re.compile(rb"(?<![0-9])(?:01|02)\.[0-9]{2}\.[0-9]{2}\.[0-9]{2}(?![0-9])")


def version_tuple(value: str) -> tuple[int, ...]:
    try:
        return tuple(int(part) for part in value.split("."))
    except ValueError:
        return ()


def embedded_version(path: pathlib.Path) -> str:
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as data:
        versions = {match.decode("ascii") for match in VERSION_PATTERN.findall(data)}
    return max(versions, key=version_tuple, default="")


def copy_tree(source: pathlib.Path, destination: pathlib.Path) -> None:
    temporary = destination.with_name(destination.name + ".tinmanx-new")
    if temporary.exists():
        shutil.rmtree(temporary)
    shutil.copytree(source, temporary, symlinks=True)
    if destination.exists():
        shutil.rmtree(destination)
    temporary.replace(destination)


def synchronize(datadir: pathlib.Path, source_dir: pathlib.Path, dry_run: bool = False) -> int:
    source_network = source_dir / "libbambu_networking.dylib"
    config_path = datadir / "OrcaSlicer.conf"
    if not source_network.exists() or not config_path.exists():
        return 0

    source_version = embedded_version(source_network)
    if not source_version:
        print("TinManX1 Bambu plug-in sync skipped: source version was not identifiable", file=sys.stderr)
        return 0

    config = json.loads(config_path.read_text())
    app = config.setdefault("app", {})
    current_version = str(app.get("network_plugin_version", ""))
    destination_network = datadir / "plugins" / f"libbambu_networking_{source_version}.dylib"
    if version_tuple(source_version) <= version_tuple(current_version) and destination_network.exists():
        return 0

    print(f"TinManX1 Bambu plug-in sync: {current_version or 'none'} -> {source_version}", file=sys.stderr)
    if dry_run:
        return 0

    plugin_dir = datadir / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = datadir / "_codex_backups" / f"bambu_plugin_sync_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    shutil.copy2(config_path, backup / config_path.name)
    for source in plugin_dir.glob("libbambu_networking_*.dylib"):
        shutil.copy2(source, backup / source.name)
    for name in PLUGIN_NAMES:
        source = plugin_dir / name
        if source.exists():
            shutil.copy2(source, backup / name)

    shutil.copy2(source_network, destination_network)
    for name in PLUGIN_NAMES:
        source = source_dir / name
        if source.exists():
            shutil.copy2(source, plugin_dir / name)
    for name in FRAMEWORK_NAMES:
        source = source_dir / name
        if source.exists():
            copy_tree(source, plugin_dir / name)

    app["installed_networking"] = True
    app["network_plugin_version"] = source_version
    app["update_network_plugin"] = False
    temporary_config = config_path.with_suffix(config_path.suffix + ".tinmanx-new")
    temporary_config.write_text(json.dumps(config, indent=4, ensure_ascii=False) + "\n")
    os.replace(temporary_config, config_path)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--datadir",
        type=pathlib.Path,
        default=pathlib.Path.home() / "Library/Application Support/OrcaSlicer-Codex",
    )
    parser.add_argument(
        "--source-plugin-dir",
        type=pathlib.Path,
        default=pathlib.Path.home() / "Library/Application Support/BambuStudio/plugins",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return synchronize(args.datadir, args.source_plugin_dir, args.dry_run)
    except Exception as exc:
        print(f"TinManX1 Bambu plug-in sync skipped: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
