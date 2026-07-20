#!/bin/sh
''':'
unset PYTHONHOME
unset PYTHONPATH
unset PYTHONEXECUTABLE
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for PYTHON in \
  "${TINMAN_AUTO_PA_PYTHON:-}" \
  "${ORCASLICER_CODEX_PYTHON:-}" \
  "$(command -v python3 2>/dev/null)" \
  "$(command -v python3.12 2>/dev/null)" \
  "$(command -v python3.11 2>/dev/null)"
do
  if [ -n "${PYTHON}" ] && [ -x "${PYTHON}" ]; then
    exec "${PYTHON}" "$0" "$@"
  fi
done
echo "TinManX1 auto pressure advance postprocessor could not find a usable Python interpreter." >&2
exit 127
':'''
from __future__ import annotations

"""TinManX1 same-print PA/max-flow post-processing adapter.

Orca/TinManX1 post-process scripts receive a single G-code path and are expected
to mutate it in place. This adapter detects the target machine, looks for real
same-print calibration score files, and delegates the actual G-code preparation
to auto_pa.py. If fresh real scores are not present, it preserves the model G-code
and adds a visible audit stamp instead of silently applying synthetic data.
"""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
AUTO_PA = SCRIPT_DIR / "auto_pa.py"
DEFAULT_DATADIR = Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
STAMP_PREFIX = "; TINMAN_AUTO_PA_POSTPROCESS"


TARGETS: dict[str, dict[str, Any]] = {
    "qidi_plus4": {
        "label": "Qidi Plus 4",
        "flavor": "m900",
        "adaptive_reference_k": 0.038,
        "old_max_flow": 20.0,
    },
    "maxez": {
        "label": "Qidi Max EZ",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 20.0,
    },
    "ratrig_vcore4_t0": {
        "label": "RatRig V-Core 4 T0",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 24.0,
    },
    "ratrig_vcore4_t1": {
        "label": "RatRig V-Core 4 T1",
        "flavor": "klipper",
        "adaptive_reference_k": 0.036,
        "old_max_flow": 24.0,
    },
    "prusa_core_one": {
        "label": "Prusa Core One",
        "flavor": "prusa",
        "adaptive_reference_k": 0.040,
        "old_max_flow": 18.0,
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def datadir() -> Path:
    return Path(os.environ.get("ORCASLICER_CODEX_DATADIR") or DEFAULT_DATADIR).expanduser()


def cache_dir() -> Path:
    override = os.environ.get("TINMAN_AUTO_PA_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    return datadir() / "tinman_auto_pa"


def parse_config_value(text: str, key: str) -> str:
    pattern = re.compile(rf"^;\s*{re.escape(key)}\s*=\s*(.*?)\s*$", re.IGNORECASE | re.MULTILINE)
    matches = pattern.findall(text)
    return matches[-1].strip() if matches else ""


def parse_start_value(text: str, key: str) -> str:
    pattern = re.compile(rf"\b{re.escape(key)}=([^\s;]+)", re.IGNORECASE)
    match = pattern.search(text)
    return match.group(1) if match else ""


def parse_print_start_value(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(";"):
            continue
        if stripped.upper().startswith("PRINT_START"):
            value = parse_start_value(stripped, key)
            if value:
                return value
    return parse_start_value(text[:20000], key)


def detect_target(text: str) -> tuple[str, dict[str, str]]:
    printer_settings_id = parse_config_value(text, "printer_settings_id")
    printer_model = parse_config_value(text, "printer_model")
    print_start_tool = parse_print_start_value(text, "TOOL")
    haystack = " ".join([printer_settings_id, printer_model]).lower()
    details = {
        "printer_settings_id": printer_settings_id,
        "printer_model": printer_model,
        "print_start_tool": print_start_tool,
    }
    if "qidi" in haystack and ("plus 4" in haystack or "x-plus 4" in haystack or "xplus4" in haystack):
        return "qidi_plus4", details
    if "qidimaxez" in haystack or "max ez" in haystack:
        return "maxez", details
    if "ratrig" in haystack or "v-core 4" in haystack:
        return ("ratrig_vcore4_t1" if print_start_tool == "1" else "ratrig_vcore4_t0"), details
    if "prusa" in haystack and ("core one" in haystack or "core_one" in haystack):
        return "prusa_core_one", details
    return "", details


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def score_context(data: dict[str, Any]) -> dict[str, Any]:
    for key in ("calibration_context", "context", "model_context", "metadata"):
        value = data.get(key)
        if isinstance(value, dict):
            return value
    return {}


def score_allowed(path: Path) -> tuple[bool, str]:
    data = read_json(path)
    context = score_context(data)
    if env_flag("TINMAN_AUTO_PA_ALLOW_SYNTHETIC"):
        return True, "allowed_by_env"
    if data.get("synthetic") is True or context.get("synthetic") is True:
        return False, "synthetic"
    origin = str(context.get("score_origin") or data.get("score_origin") or "").lower()
    if origin == "real":
        return True, "real"
    if origin == "manual" and env_flag("TINMAN_AUTO_PA_ALLOW_MANUAL"):
        return True, "manual_allowed_by_env"
    if not origin:
        return False, "missing_score_origin"
    return False, f"unsupported_score_origin:{origin}"


def candidate_score_paths(target: str, kind: str) -> list[Path]:
    base = cache_dir()
    names = {
        "pa": ["latest_pa_score.json", "latest_beacon_pa_score.json", "pa_score.latest.json"],
        "maxflow": ["latest_maxflow_score.json", "latest_flow_score.json", "maxflow_score.latest.json"],
    }[kind]
    paths: list[Path] = []
    for name in names:
        paths.append(base / target / name)
        paths.append(base / name.replace("latest_", f"{target}_latest_"))
    override = os.environ.get(f"TINMAN_AUTO_PA_{kind.upper()}_SCORE")
    if override:
        paths.insert(0, Path(override).expanduser())
    return paths


def find_score(target: str, kind: str) -> tuple[str, str]:
    rejected: list[str] = []
    for path in candidate_score_paths(target, kind):
        if not path.exists():
            continue
        allowed, reason = score_allowed(path)
        if allowed:
            return str(path), reason
        rejected.append(f"{path}:{reason}")
    return "", ";".join(rejected)


def strip_previous_stamps(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.startswith(STAMP_PREFIX)
    ) + ("\n" if text.endswith("\n") else "")


def stamp_file(gcode: Path, fields: dict[str, Any]) -> None:
    text = strip_previous_stamps(gcode.read_text(errors="replace"))
    field_text = " ".join(f"{key}={value}" for key, value in fields.items() if value not in (None, ""))
    stamp = f"{STAMP_PREFIX} {field_text}".rstrip() + "\n"
    if text.startswith("; HEADER_BLOCK_START\n"):
        text = text.replace("; HEADER_BLOCK_START\n", "; HEADER_BLOCK_START\n" + stamp, 1)
    else:
        text = stamp + text
    gcode.write_text(text)


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def run_prepare(gcode: Path, target: str, target_config: dict[str, Any], pa_score: str, maxflow_score: str) -> tuple[int, str, str, Path, Path]:
    output = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.gcode")
    report = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa_prepare.json")
    for path in (output, report):
        try:
            path.unlink()
        except FileNotFoundError:
            pass
    cmd = [
        sys.executable,
        str(AUTO_PA),
        "same-print-prepare",
        "--model-input",
        str(gcode),
        "--output",
        str(output),
        "--report",
        str(report),
        "--flavor",
        str(target_config["flavor"]),
        "--adaptive-reference-k",
        str(target_config["adaptive_reference_k"]),
        "--old-max-flow",
        str(target_config["old_max_flow"]),
    ]
    if pa_score:
        cmd.extend(["--pa-score", pa_score])
    else:
        cmd.append("--no-fixed-pa")
    if maxflow_score:
        cmd.extend(["--maxflow-score", maxflow_score])
    else:
        cmd.append("--no-flow-governor")
    if env_flag("TINMAN_AUTO_PA_ALLOW_SYNTHETIC"):
        cmd.append("--allow-synthetic-scores")
    if env_flag("TINMAN_AUTO_PA_ALLOW_MISSING_METADATA"):
        cmd.append("--allow-missing-score-metadata")
    if env_flag("TINMAN_AUTO_PA_ALLOW_MISMATCHED_CONTEXT"):
        cmd.append("--allow-mismatched-score-context")
    if env_flag("TINMAN_AUTO_PA_ALLOW_STALE"):
        cmd.append("--allow-stale-scores")
    if env_flag("TINMAN_AUTO_PA_ANNOTATE"):
        cmd.append("--annotate")
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    return proc.returncode, proc.stdout, proc.stderr, output, report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="TinManX1 same-print PA/max-flow postprocessor")
    parser.add_argument("gcode", type=Path)
    args = parser.parse_args(argv)

    gcode = args.gcode.resolve()
    report_path = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.json")
    report: dict[str, Any] = {
        "kind": "tinman_auto_pa_postprocess_report",
        "version": 1,
        "gcode": str(gcode),
        "captured_at": utc_now(),
        "status": "unknown",
    }
    if not gcode.exists():
        report["status"] = "error_missing_gcode"
        write_report(report_path, report)
        return 2
    if env_flag("TINMAN_AUTO_PA_DISABLE"):
        report["status"] = "disabled"
        stamp_file(gcode, {"status": "disabled"})
        write_report(report_path, report)
        return 0
    if not AUTO_PA.exists():
        report["status"] = "deferred_missing_auto_pa"
        stamp_file(gcode, {"status": report["status"]})
        write_report(report_path, report)
        return 0

    text = gcode.read_text(errors="replace")
    target, detected = detect_target(text)
    report["detected"] = detected
    report["target"] = target
    if not target:
        report["status"] = "skipped_unknown_target"
        write_report(report_path, report)
        return 0

    pa_score, pa_reason = find_score(target, "pa")
    maxflow_score, maxflow_reason = find_score(target, "maxflow")
    report["pa_score"] = pa_score
    report["pa_score_reason"] = pa_reason
    report["maxflow_score"] = maxflow_score
    report["maxflow_score_reason"] = maxflow_reason
    if not pa_score and not maxflow_score:
        report["status"] = "deferred_no_real_scores"
        stamp_file(
            gcode,
            {
                "status": report["status"],
                "target": target,
                "pa_score": "missing",
                "maxflow_score": "missing",
            },
        )
        write_report(report_path, report)
        return 0

    original_backup = gcode.with_suffix(gcode.suffix + ".tinman_auto_pa.original")
    shutil.copy2(gcode, original_backup)
    rc, stdout, stderr, output, prepare_report = run_prepare(
        gcode,
        target,
        TARGETS[target],
        pa_score,
        maxflow_score,
    )
    report["prepare_returncode"] = rc
    report["prepare_stdout"] = stdout
    report["prepare_stderr"] = stderr
    report["prepare_report"] = str(prepare_report)
    if rc == 0 and output.exists():
        shutil.move(str(output), str(gcode))
        report["status"] = "prepared"
        stamp_file(
            gcode,
            {
                "status": report["status"],
                "target": target,
                "pa_score": "applied" if pa_score else "missing",
                "maxflow_score": "applied" if maxflow_score else "missing",
            },
        )
        write_report(report_path, report)
        return 0

    report["status"] = "deferred_prepare_failed"
    shutil.copy2(original_backup, gcode)
    stamp_file(
        gcode,
        {
            "status": report["status"],
            "target": target,
            "strict": int(env_flag("TINMAN_AUTO_PA_STRICT")),
        },
    )
    write_report(report_path, report)
    return 1 if env_flag("TINMAN_AUTO_PA_STRICT") else 0


if __name__ == "__main__":
    sys.exit(main())
