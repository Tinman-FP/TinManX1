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
  "$(command -v python3.11 2>/dev/null)"
do
  if [ -n "${PYTHON}" ] && [ -x "${PYTHON}" ]; then
    exec "${PYTHON}" "$0" "$@"
  fi
done
echo "TinManX1 Arc Overhang adapter could not find a usable Python interpreter." >&2
exit 127
':'''
from __future__ import annotations

"""Post-processing adapter for Orca's one-argument script contract.

Orca post-processing scripts receive a single G-code path and are expected to
mutate it in place. The TinManX1 transform wrapper is safer than that: it writes
to a separate output and emits an audit file. This adapter bridges those two
contracts by replacing Orca's temporary post-process file only after a successful
Arc Overhang transform.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
NO_ARC_MOVES_ERROR = "Arc Overhang transform produced no arc extrusion moves"
LOW_ARC_COVERAGE_ERROR = "Arc Overhang transform covered too little bridge source geometry"


def wrapper_path() -> Path:
    candidates = [
        os.environ.get("ORCASLICER_CODEX_ARC_SUPPORT_TRANSFORM"),
        os.environ.get("TINMANX_ARC_SUPPORT_TRANSFORM"),
        str(SCRIPT_DIR / "orcaslicer_codex_arc_support_transform.py"),
        str(SCRIPT_DIR.parent.parent / "scripts" / "orcaslicer_codex_arc_support_transform.py"),
        str(Path.cwd() / "scripts" / "orcaslicer_codex_arc_support_transform.py"),
        str(Path.cwd().parent / "scripts" / "orcaslicer_codex_arc_support_transform.py"),
        str(SCRIPT_DIR / "tinmanx_arc_support_transform.py"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if path.exists():
            return path.resolve()
    raise FileNotFoundError(
        "TinManX1 Arc Overhang transform was not found. Set ORCASLICER_CODEX_ARC_SUPPORT_TRANSFORM."
    )


def failure_message(audit: Path) -> str:
    if not audit.exists():
        return "TinManX1 Arc Overhang transform failed before writing an audit; original G-code was preserved."
    try:
        details = json.loads(audit.read_text(encoding="utf-8"))
    except Exception:
        return f"TinManX1 Arc Overhang transform failed; audit could not be parsed: {audit}"
    error = details.get("error") or "Arc Overhang transform failed"
    status = details.get("status") or "unknown"
    preserved = details.get("input_preserved")
    preserved_note = "original G-code preserved" if preserved is True else "input preservation unknown"
    guard = details.get("machine_start_toolchange_guard")
    guard_status = guard.get("status") if isinstance(guard, dict) else "unknown"
    return (
        f"TinManX1 Arc Overhang transform {status}: {error}. "
        f"{preserved_note}; machine-command guard={guard_status}; audit={audit}"
    )


def read_audit(audit: Path) -> dict:
    if not audit.exists():
        return {}
    try:
        details = json.loads(audit.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return details if isinstance(details, dict) else {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply TinManX1 Arc Overhangs to an Orca post-process G-code file.")
    parser.add_argument("gcode", type=Path)
    args = parser.parse_args(argv)

    gcode = args.gcode.resolve()
    output = gcode.with_suffix(gcode.suffix + ".arc_support.gcode")
    audit = gcode.with_suffix(gcode.suffix + ".arc_support_audit.json")
    if output.exists():
        output.unlink()
    command = [str(wrapper_path()), str(gcode), str(output), "--audit", str(audit)]
    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        print(failure_message(audit), file=sys.stderr)
        return result.returncode
    shutil.move(str(output), str(gcode))
    return 0


if __name__ == "__main__":
    sys.exit(main())
