#!/usr/bin/env python3
"""Install a locally available Bambu networking plugin for TinManX1.

This helper intentionally does not download or ship Bambu's native plugin.
It copies plugin binaries already present on the user's machine into the
TinManX1 data directory and updates OrcaSlicer.conf to load that version.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable


DEFAULT_DATA_DIR = Path.home() / "Library/Application Support/OrcaSlicer-Codex"
DEFAULT_SOURCE_DIRS = [
    Path.home() / "Library/Application Support/BambuStudio/plugins",
    Path.home() / "Library/Application Support/BambuStudioBeta/plugins",
    Path.home() / "Library/Application Support/OrcaSlicer/plugins",
]
VERSION_RE = re.compile(r"\b\d{2}\.\d{2}\.\d{2}\.\d{2}\b")
BAMBU_MODEL_RE = re.compile(r"^(BL-[A-Z0-9]+|O1[A-Z0-9]+|N[A-Z0-9]*|C1[123])$")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check)


def is_tinmanx1_running() -> bool:
    result = run(["pgrep", "-fl", r"TinManX1(\.app|\.real)?|OrcaSlicer-Codex"], check=False)
    return result.returncode == 0 and bool(result.stdout.strip())


def candidate_network_libs(source_dir: Path) -> list[Path]:
    names = ["libbambu_networking.dylib"]
    names.extend(sorted(p.name for p in source_dir.glob("libbambu_networking_*.dylib")))
    seen: set[Path] = set()
    result: list[Path] = []
    for name in names:
        path = source_dir / name
        if path.exists() and path not in seen:
            seen.add(path)
            result.append(path)
    return result


def find_source_dir(explicit: Path | None) -> Path:
    if explicit:
        if candidate_network_libs(explicit):
            return explicit
        raise SystemExit(f"No libbambu_networking dylib found in {explicit}")

    for path in DEFAULT_SOURCE_DIRS:
        if candidate_network_libs(path):
            return path
    searched = "\n  ".join(str(p) for p in DEFAULT_SOURCE_DIRS)
    raise SystemExit(f"No local Bambu networking plugin found. Searched:\n  {searched}")


def detect_version(network_lib: Path) -> str | None:
    if network_lib.name.startswith("libbambu_networking_"):
        stem = network_lib.stem
        version = stem.removeprefix("libbambu_networking_")
        if VERSION_RE.fullmatch(version):
            return version

    result = run(["strings", str(network_lib)], check=False)
    if result.returncode == 0:
        matches = sorted(set(VERSION_RE.findall(result.stdout)))
        if matches:
            return matches[-1]
    return None


def load_conf(conf_path: Path) -> dict:
    if not conf_path.exists():
        raise SystemExit(f"Missing TinManX1 config: {conf_path}")
    return json.loads(conf_path.read_text())


def backup_path(data_dir: Path) -> Path:
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return data_dir / f"_codex_bambu_network_plugin_backup_{stamp}"


def copy_file(src: Path, dst: Path, *, dry_run: bool) -> None:
    print(f"copy {src} -> {dst}")
    if dry_run:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    os.chmod(dst, 0o644)
    run(["xattr", "-cr", str(dst)], check=False)


def copy_tree_snapshot(src: Path, dst: Path, *, dry_run: bool) -> None:
    print(f"backup {src} -> {dst}")
    if dry_run:
        return
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True, symlinks=True, ignore_dangling_symlinks=True)


def plugin_arch(path: Path) -> str:
    result = run(["file", str(path)], check=False)
    return result.stdout.strip() or result.stderr.strip()


def ensure_bbl_provider(current: object) -> str:
    parts = []
    if isinstance(current, str):
        parts = [p for p in current.split(";") if p]
    if "orca" not in parts:
        parts.insert(0, "orca")
    if "bbl" not in parts:
        parts.append("bbl")
    return ";".join(parts)


def update_config(conf_path: Path, version: str, *, dry_run: bool) -> dict:
    conf = load_conf(conf_path)
    app = conf.setdefault("app", {})
    app["installed_networking"] = True
    app["network_plugin_version"] = version
    app["network_plugin_remind_later"] = True
    app["network_plugin_update_prompts_disabled"] = True
    app["update_network_plugin"] = "false"
    app["cloud_providers"] = ensure_bbl_provider(app.get("cloud_providers"))
    app["enable_ssl_for_ftp"] = True
    app["enable_ssl_for_mqtt"] = True

    skipped = app.get("network_plugin_skipped_versions")
    if isinstance(skipped, str):
        app["network_plugin_skipped_versions"] = ";".join(p for p in skipped.split(";") if p and p != version)
    elif isinstance(skipped, list):
        app["network_plugin_skipped_versions"] = [p for p in skipped if p != version]

    print(f"set app.network_plugin_version = {version}")
    if not dry_run:
        conf_path.write_text(json.dumps(conf, indent=2, ensure_ascii=False) + "\n")
    return conf


def summarize_machines(conf: dict) -> None:
    machines = conf.get("local_machines")
    access_codes = conf.get("access_code")
    if not isinstance(machines, dict):
        return
    print("saved Bambu machines:")
    for serial, item in machines.items():
        if not isinstance(item, dict):
            continue
        printer_type = str(item.get("printer_type", ""))
        if BAMBU_MODEL_RE.fullmatch(printer_type) or serial.startswith(("00M", "094")):
            has_code = isinstance(access_codes, dict) and bool(access_codes.get(serial))
            print(
                f"  {item.get('dev_name', serial)} serial={serial} "
                f"type={printer_type} ip={item.get('dev_ip', '')} access_code_saved={has_code}"
            )


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--source-dir", type=Path, default=None)
    parser.add_argument("--version", default=None, help="Plugin version to install, e.g. 02.06.00.50")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-running", action="store_true", help="Allow config edits while TinManX1 is running")
    args = parser.parse_args(list(argv) if argv is not None else None)

    data_dir = args.data_dir.expanduser()
    plugins_dir = data_dir / "plugins"
    conf_path = data_dir / "OrcaSlicer.conf"
    source_dir = find_source_dir(args.source_dir.expanduser() if args.source_dir else None)
    network_libs = candidate_network_libs(source_dir)
    network_lib = network_libs[0]
    version = args.version or detect_version(network_lib)
    if not version:
        raise SystemExit(f"Could not detect plugin version from {network_lib}; pass --version")

    if is_tinmanx1_running() and not args.allow_running:
        raise SystemExit("TinManX1 is running. Quit it first, then rerun this helper.")

    for required in ["libBambuSource.dylib", "liblive555.dylib"]:
        if not (source_dir / required).exists():
            raise SystemExit(f"Missing required companion library: {source_dir / required}")

    backup_dir = backup_path(data_dir)
    copy_tree_snapshot(plugins_dir, backup_dir / "plugins-before", dry_run=args.dry_run)
    if conf_path.exists():
        copy_file(conf_path, backup_dir / "OrcaSlicer.conf", dry_run=args.dry_run)

    versioned_network = plugins_dir / f"libbambu_networking_{version}.dylib"
    copy_file(network_lib, versioned_network, dry_run=args.dry_run)
    copy_file(source_dir / "libBambuSource.dylib", plugins_dir / "libBambuSource.dylib", dry_run=args.dry_run)
    copy_file(source_dir / "liblive555.dylib", plugins_dir / "liblive555.dylib", dry_run=args.dry_run)
    copy_file(network_lib, plugins_dir / "backup" / f"libbambu_networking_{version}.dylib", dry_run=args.dry_run)
    copy_file(source_dir / "libBambuSource.dylib", plugins_dir / "backup" / "libBambuSource.dylib", dry_run=args.dry_run)
    copy_file(source_dir / "liblive555.dylib", plugins_dir / "backup" / "liblive555.dylib", dry_run=args.dry_run)

    conf = update_config(conf_path, version, dry_run=args.dry_run)
    print(plugin_arch(versioned_network))
    summarize_machines(conf)
    print(f"backup_dir={backup_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
