#!/usr/bin/env python3
"""Collect a sanitized manifest for the local TinManX1 install."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_CODEX_APP = Path("/Applications/TinManX1.app")
DEFAULT_STOCK_APP = Path("/Applications/OrcaSlicer.app")
DEFAULT_TINMANX_APP = Path("/Applications/TinManX TinManX1.app")
DEFAULT_APP_SUPPORT = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
BAMBU_PLUGINS = (
    "libBambuSource.dylib",
    "libbambu_networking_02.06.00.50.dylib",
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_plist(path: Path) -> dict[str, Any]:
    with path.open("rb") as fh:
        return plistlib.load(fh)


def maybe_plist_info(app: Path) -> dict[str, Any]:
    info = app / "Contents" / "Info.plist"
    if not info.exists():
        return {"exists": False}
    data = read_plist(info)
    keys = [
        "CFBundleDisplayName",
        "CFBundleName",
        "CFBundleIdentifier",
        "CFBundleShortVersionString",
        "CFBundleExecutable",
        "CFBundleIconFile",
    ]
    return {key: data.get(key) for key in keys}


def run_text(args: list[str]) -> str:
    proc = subprocess.run(args, text=True, capture_output=True, check=False)
    return proc.stdout if proc.returncode == 0 else ""


def file_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False}
    return {
        "exists": True,
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


def executable_summary(path: Path) -> dict[str, Any]:
    summary = file_summary(path)
    if not path.exists():
        return summary
    strings = run_text(["strings", str(path)])
    versions = sorted(set(re.findall(r"\b2\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9_.-]+)?\b", strings)))
    labels = sorted(set(re.findall(r"OrcaSlicer(?: G-code Viewer)? [0-9][^\n\x00]+", strings)))
    summary.update(
        {
            "reported_versions": versions,
            "reported_orcaslicer_labels": labels[:20],
            "contains_240_dev": "OrcaSlicer 2.4.0-dev" in strings,
            "contains_232": "OrcaSlicer 2.3.2" in strings or "OrcaSlicer/2.3.2" in strings,
        }
    )
    return summary


def resource_files(root: Path) -> dict[str, Path]:
    resources = root / "Contents" / "Resources"
    if not resources.exists():
        return {}
    return {
        str(path.relative_to(resources)): path
        for path in resources.rglob("*")
        if path.is_file() and path.name != ".DS_Store"
    }


def resource_compare(codex_app: Path, stock_app: Path) -> dict[str, Any]:
    codex = resource_files(codex_app)
    stock = resource_files(stock_app)
    if not codex or not stock:
        return {"available": False}

    missing = sorted(set(stock) - set(codex))
    extra = sorted(set(codex) - set(stock))
    changed: list[str] = []
    for rel in sorted(set(codex) & set(stock)):
        cp = codex[rel]
        sp = stock[rel]
        if cp.stat().st_size != sp.stat().st_size or sha256(cp) != sha256(sp):
            changed.append(rel)

    return {
        "available": True,
        "stock_resource_files": len(stock),
        "codex_resource_files": len(codex),
        "stock_files_missing_from_codex_count": len(missing),
        "codex_extra_files_count": len(extra),
        "same_path_different_content_count": len(changed),
        "stock_files_missing_from_codex": missing[:200],
        "codex_extra_files": extra[:200],
        "same_path_different_content": changed[:200],
    }


def config_summary(app_support: Path) -> dict[str, Any]:
    config = app_support / "OrcaSlicer.conf"
    if not config.exists():
        return {"exists": False}
    text = config.read_text(errors="replace")
    header = None
    match = re.search(r'"header"\s*:\s*"([^"]+)"', text)
    if match:
        header = match.group(1)
    network_version = None
    match = re.search(r'"network_plugin_version"\s*:\s*"([^"]+)"', text)
    if match:
        network_version = match.group(1)
    prompts_disabled = '"network_plugin_update_prompts_disabled": true' in text
    stable_update_only = '"check_stable_update_only": true' in text
    return {
        "exists": True,
        "header": header,
        "network_plugin_version": network_version,
        "network_plugin_update_prompts_disabled": prompts_disabled,
        "check_stable_update_only": stable_update_only,
    }


def plugin_summary(app_support: Path) -> dict[str, Any]:
    plugin_dir = app_support / "plugins"
    result: dict[str, Any] = {"plugin_dir_exists": plugin_dir.exists(), "plugins": {}}
    for name in BAMBU_PLUGINS:
        result["plugins"][name] = file_summary(plugin_dir / name)
    return result


def tinmanx_summary(tinmanx_app: Path, codex_app: Path) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(tinmanx_app),
        "exists": tinmanx_app.exists(),
        "is_symlink": tinmanx_app.is_symlink(),
    }
    if tinmanx_app.exists():
        result["plist"] = maybe_plist_info(tinmanx_app)
        try:
            result["resolves_to_codex"] = tinmanx_app.resolve() == codex_app.resolve()
        except FileNotFoundError:
            result["resolves_to_codex"] = None
        launcher = tinmanx_app / "Contents" / "MacOS" / "OrcaSlicer"
        if launcher.exists() and launcher.stat().st_size < 50_000:
            text = launcher.read_text(errors="replace")
            result["launcher_mentions_tinmanx_data_dir"] = "TinManX-Orca-Codex" in text
            result["launcher_mentions_codex_data_dir"] = "OrcaSlicer-Codex" in text
    return result


def build_manifest(args: argparse.Namespace) -> dict[str, Any]:
    codex_real = args.codex_app / "Contents" / "MacOS" / "OrcaSlicer.real"
    codex_launcher = args.codex_app / "Contents" / "MacOS" / "OrcaSlicer"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "codex_app": {
            "path": str(args.codex_app),
            "exists": args.codex_app.exists(),
            "is_symlink": args.codex_app.is_symlink(),
            "plist": maybe_plist_info(args.codex_app),
            "launcher": file_summary(codex_launcher),
            "real_executable": executable_summary(codex_real),
        },
        "stock_app": {
            "path": str(args.stock_app),
            "exists": args.stock_app.exists(),
            "plist": maybe_plist_info(args.stock_app),
        },
        "app_support": {
            "path": str(args.app_support),
            "exists": args.app_support.exists(),
            "config": config_summary(args.app_support),
            "bambu_plugins": plugin_summary(args.app_support),
        },
        "tinmanx_app": tinmanx_summary(args.tinmanx_app, args.codex_app),
        "resource_compare_against_stock": resource_compare(args.codex_app, args.stock_app),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-app", type=Path, default=DEFAULT_CODEX_APP)
    parser.add_argument("--stock-app", type=Path, default=DEFAULT_STOCK_APP)
    parser.add_argument("--tinmanx-app", type=Path, default=DEFAULT_TINMANX_APP)
    parser.add_argument("--app-support", type=Path, default=DEFAULT_APP_SUPPORT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    manifest = build_manifest(args)
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
