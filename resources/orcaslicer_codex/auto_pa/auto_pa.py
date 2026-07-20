#!/usr/bin/env python3
"""
TinManX1 automatic pressure advance toolkit.

This is the first safe-development layer: it inventories printer support,
generates compact PA calibration coupons, probes Moonraker printers, and can
dry-run live PA commands. It does not move a printer unless --execute is used.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import ipaddress
import json
import math
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


TINMAN_ROOT = Path(
    os.environ.get("ORCASLICER_CODEX_DATADIR")
    or Path.home() / "Library" / "Application Support" / "OrcaSlicer-Codex"
)
ACTIVE_USER = os.environ.get("TINMAN_AUTO_PA_USER_STORE", "default")
DEFAULT_PRUSA_HOST = os.environ.get("TINMAN_AUTO_PA_PRUSA_HOST", "")
DEFAULT_QIDI_HOST = os.environ.get("TINMAN_AUTO_PA_QIDI_HOST", "")


@dataclass
class PrinterTarget:
    family: str
    profiles: int
    flavor: str
    hosts: list[str]
    native_status: str
    adapter: str
    measurement: list[str]
    priority: int
    notes: str


def read_json(path: Path) -> Any:
    return json.loads(path.read_text())


def first(value: Any, default: str = "") -> Any:
    if isinstance(value, list):
        return value[0] if value else default
    return default if value is None else value


def family_for_machine(machine: dict[str, Any], file_name: str) -> str:
    text = " ".join(
        str(machine.get(k, "")) for k in ("printer_model", "printer_settings_id", "inherits")
    ).lower()
    text += " " + file_name.lower()
    if "x1 carbon" in text or "bambu" in text:
        return "Bambu X1C/P1 family"
    if "k2 plus" in text:
        return "Creality K2 Plus"
    if "centauri" in text:
        return "Elegoo Centauri"
    if "prusa core" in text:
        return "Prusa Core One"
    if "qidi" in text:
        return "Qidi Plus/X-Plus"
    if "ratrig" in text or "v-core" in text:
        return "RatRig V-Core 4"
    if "snapmaker" in text:
        return "Snapmaker U1"
    if "sovol" in text:
        return "Sovol SV08 MAX"
    if "fibreseek" in text:
        return "FibreSeek Seeker 3"
    return "Other"


def inventory(root: Path = TINMAN_ROOT, user: str = ACTIVE_USER) -> list[PrinterTarget]:
    machine_dir = root / "user" / user / "machine"
    grouped: dict[str, list[dict[str, Any]]] = {}
    for path in sorted(machine_dir.glob("*.json")):
        machine = read_json(path)
        family = family_for_machine(machine, path.name)
        grouped.setdefault(family, []).append(machine)

    targets: list[PrinterTarget] = []
    for family, machines in sorted(grouped.items()):
        flavors = sorted({str(first(m.get("gcode_flavor")) or "") for m in machines if first(m.get("gcode_flavor"))})
        hosts = sorted({str(first(m.get("print_host")) or "") for m in machines if first(m.get("print_host"))})
        flavor = ",".join(flavors) if flavors else "inherit/unknown"

        if family == "Bambu X1C/P1 family":
            native = "omit: user/native automatic behavior"
            adapter = "none"
            measurement = ["native Bambu"]
            priority = 99
            notes = "Out of scope for this project."
        elif family == "Creality K2 Plus":
            native = "TinMan flow_cali on; true auto PA not proven"
            adapter = "creality_k2_or_generic_klipper"
            measurement = ["Creality flow dynamics", "possible camera", "possible pressure/apax hooks"]
            priority = 5
            notes = "Keep flow_cali on; do not force unsupported Auto mode."
        elif family == "Snapmaker U1":
            native = "native flow_calibrator exists"
            adapter = "snapmaker_u1_native_flow_k"
            measurement = ["native flow_calibrator", "webcam", "per-tool PA telemetry"]
            priority = 2
            notes = "Best native-data target after Prusa; per-material flow_k range is exposed."
        elif family == "Qidi Plus/X-Plus":
            native = "no native auto PA in TinMan metadata"
            adapter = "moonraker_cv_hall_width"
            measurement = ["webcam", "hall filament width", "motion_report", "M900"]
            priority = 3
            notes = "Clean Moonraker target with live PA and filament diameter telemetry."
        elif family == "RatRig V-Core 4":
            native = "no native auto PA found"
            adapter = "generic_klipper_cv"
            measurement = ["webcam/camera if reachable", "Beacon if configured", "SET_PRESSURE_ADVANCE"]
            priority = 4
            notes = "Needs M900 compatibility layer if slicer emits M900."
        elif family in {"Sovol SV08 MAX", "Elegoo Centauri"}:
            native = "not proven"
            adapter = "generic_klipper_cv"
            measurement = ["webcam if available", "Moonraker if reachable", "SET_PRESSURE_ADVANCE"]
            priority = 6
            notes = "Requires live config/API capture before profile rollout."
        elif family == "Prusa Core One":
            native = "no stock auto PA, but nozzle loadcell can be used"
            adapter = "prusa_loadcell_prusapatuner"
            measurement = ["nozzle loadcell over Buddy metrics", "PrusaLink", "M572"]
            priority = 1
            notes = "CNC Kitchen PrusaPATuner proves a force-based free-air sweep path."
        else:
            native = "unknown"
            adapter = "needs_discovery"
            measurement = []
            priority = 50
            notes = "Discovery required."

        targets.append(
            PrinterTarget(
                family=family,
                profiles=len(machines),
                flavor=flavor,
                hosts=hosts,
                native_status=native,
                adapter=adapter,
                measurement=measurement,
                priority=priority,
                notes=notes,
            )
        )
    return sorted(targets, key=lambda t: (t.priority, t.family))


def machine_dir(root: Path = TINMAN_ROOT, user: str = ACTIVE_USER) -> Path:
    return root / "user" / user / "machine"


def prusa_profiles(root: Path = TINMAN_ROOT, user: str = ACTIVE_USER, host: str = "") -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for path in sorted(machine_dir(root, user).glob("Prusa CORE One*.json")):
        data = read_json(path)
        profile_host = str(first(data.get("print_host")) or "")
        if host and profile_host != host:
            continue
        profiles.append(
            {
                "file": str(path),
                "profile": str(first(data.get("printer_settings_id")) or path.stem),
                "inherits": str(first(data.get("inherits")) or ""),
                "printer_model": str(first(data.get("printer_model")) or ""),
                "host": profile_host,
                "host_type": str(first(data.get("host_type")) or ""),
                "auth_type": str(first(data.get("printhost_authorization_type")) or ""),
                "api_key_present": bool(first(data.get("printhost_apikey"))),
                "user_present": bool(first(data.get("printhost_user"))),
                "password_present": bool(first(data.get("printhost_password"))),
                "nozzle_diameter": str(first(data.get("nozzle_diameter")) or ""),
                "default_filament_profile": str(first(data.get("default_filament_profile")) or ""),
            }
        )
    return profiles


def prusa_credentials(
    root: Path = TINMAN_ROOT,
    user: str = ACTIVE_USER,
    host: str = DEFAULT_PRUSA_HOST,
    api_key: str = "",
    password: str = "",
    prusa_user: str = "maker",
) -> dict[str, str]:
    if api_key or password:
        return {"api_key": api_key, "password": password, "user": prusa_user}
    for path in sorted(machine_dir(root, user).glob("Prusa CORE One*.json")):
        data = read_json(path)
        if str(first(data.get("print_host")) or "") != host:
            continue
        key = str(first(data.get("printhost_apikey")) or "")
        pw = str(first(data.get("printhost_password")) or "")
        usr = str(first(data.get("printhost_user")) or "") or prusa_user
        if key or pw:
            return {"api_key": key, "password": pw, "user": usr}
    return {"api_key": "", "password": "", "user": prusa_user}


def local_ip_toward(host: str, port: int = 80) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((host, port))
        return str(sock.getsockname()[0])
    finally:
        sock.close()


def udp_target_warning(printer_host: str, udp_host: str) -> str:
    try:
        printer_ip = ipaddress.ip_address(printer_host)
        target_ip = ipaddress.ip_address(udp_host)
    except ValueError:
        return ""
    if not printer_ip.is_private:
        return ""
    if str(target_ip).startswith("100.") and printer_ip.version == 4:
        return (
            "UDP target is a 100.x tunnel address. Prusa metrics are sent by the "
            "printer itself, so confirm the printer can route to this address or "
            "override --udp-host with a LAN-reachable host IP."
        )
    if printer_ip.version == 4 and target_ip.version == 4:
        printer_prefix = ".".join(str(printer_ip).split(".")[:3])
        target_prefix = ".".join(str(target_ip).split(".")[:3])
        if printer_prefix != target_prefix and target_ip.is_private:
            return (
                "Printer and UDP target appear to be on different /24 networks. "
                "This can work with routing, but metrics will be silent if the "
                "printer cannot route back to the host."
            )
    return ""


def prusa_opener(host: str, user: str, password: str) -> urllib.request.OpenerDirector:
    if not password:
        return urllib.request.build_opener()
    manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    manager.add_password(None, f"http://{host}", user, password)
    return urllib.request.build_opener(
        urllib.request.HTTPDigestAuthHandler(manager),
        urllib.request.HTTPBasicAuthHandler(manager),
    )


def prusa_request(
    host: str,
    path: str,
    *,
    method: str = "GET",
    payload: Optional[dict[str, Any]] = None,
    api_key: str = "",
    password: str = "",
    user: str = "maker",
    timeout: float = 5.0,
) -> dict[str, Any]:
    url = f"http://{host}{path}"
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if api_key:
        headers["X-Api-Key"] = api_key
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    opener = prusa_opener(host, user, password)
    try:
        with opener.open(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            try:
                data: Any = json.loads(text) if text else None
            except ValueError:
                data = text[:500]
            return {"ok": True, "status": resp.status, "data": data}
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        try:
            data = json.loads(text) if text else None
        except ValueError:
            data = text[:500]
        return {"ok": False, "status": exc.code, "data": data}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def prusa_probe(args: argparse.Namespace) -> dict[str, Any]:
    creds = prusa_credentials(
        Path(args.root),
        args.user_store,
        args.host,
        api_key=args.api_key or "",
        password=args.password or "",
        prusa_user=args.prusa_user,
    )
    result: dict[str, Any] = {
        "host": args.host,
        "profiles": prusa_profiles(Path(args.root), args.user_store, args.host),
        "auth": {
            "api_key_present": bool(creds["api_key"]),
            "password_present": bool(creds["password"]),
            "user": creds["user"] if creds["password"] else "",
        },
        "reachable": False,
        "endpoints": {},
    }
    for path in ("/api/v1/info", "/api/v1/status", "/api/v1/job"):
        response = prusa_request(
            args.host,
            path,
            api_key=creds["api_key"],
            password=creds["password"],
            user=creds["user"],
            timeout=args.timeout,
        )
        result["endpoints"][path] = response
        if response.get("ok"):
            result["reachable"] = True
    return result


def prusa_current_state(host: str, creds: dict[str, str], timeout: float = 5.0) -> dict[str, Any]:
    job = prusa_request(
        host,
        "/api/v1/job",
        api_key=creds["api_key"],
        password=creds["password"],
        user=creds["user"],
        timeout=timeout,
    )
    status = prusa_request(
        host,
        "/api/v1/status",
        api_key=creds["api_key"],
        password=creds["password"],
        user=creds["user"],
        timeout=timeout,
    )
    return {"job": job, "status": status}


def prusa_state_label(state: dict[str, Any]) -> str:
    labels: list[str] = []
    for key in ("job", "status"):
        data = state.get(key, {}).get("data")
        if isinstance(data, dict):
            for field in ("state", "printer_state", "status"):
                value = data.get(field)
                if isinstance(value, str):
                    labels.append(value.lower())
            printer = data.get("printer")
            if isinstance(printer, dict):
                value = printer.get("state")
                if isinstance(value, str):
                    labels.append(value.lower())
    return ",".join(labels)


def prusa_send_command(
    host: str,
    command: str,
    creds: dict[str, str],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for path in ("/api/v1/printer/command", "/api/printer/command"):
        response = prusa_request(
            host,
            path,
            method="POST",
            payload={"command": command},
            api_key=creds["api_key"],
            password=creds["password"],
            user=creds["user"],
            timeout=timeout,
        )
        last = {"path": path, **response}
        if response.get("ok") or response.get("status") not in {404, 405}:
            return last
    return last


def apply_prusa_pa(args: argparse.Namespace) -> dict[str, Any]:
    creds = prusa_credentials(
        Path(args.root),
        args.user_store,
        args.host,
        api_key=args.api_key or "",
        password=args.password or "",
        prusa_user=args.prusa_user,
    )
    command = f"M572 S{args.k:.4f}"
    result: dict[str, Any] = {
        "host": args.host,
        "execute": bool(args.execute),
        "command": command,
        "auth": {
            "api_key_present": bool(creds["api_key"]),
            "password_present": bool(creds["password"]),
            "user": creds["user"] if creds["password"] else "",
        },
    }
    if not args.execute:
        return result
    state = prusa_current_state(args.host, creds, timeout=args.timeout)
    label = prusa_state_label(state)
    result["state"] = label or "unknown"
    active_words = ("print", "busy", "paus", "running")
    if any(word in label for word in active_words) and not args.allow_printing:
        result.update(
            {
                "execute": False,
                "blocked": True,
                "reason": "Prusa appears to be active; pass --allow-printing to intentionally update M572 live.",
            }
        )
        return result
    result["response"] = prusa_send_command(args.host, command, creds, timeout=args.timeout)
    return result


def find_prusa_tuner_src() -> Optional[Path]:
    candidates: list[Path] = []
    env_src = os.environ.get("PRUSA_PA_TUNER_SRC")
    if env_src:
        candidates.append(Path(env_src))
    script = Path(__file__).resolve()
    for base in [Path.cwd(), *script.parents]:
        candidates.append(base / "work" / "PrusaPATuner" / "src")
        candidates.append(base.parent / "work" / "PrusaPATuner" / "src")
    for candidate in candidates:
        if (candidate / "prusa_pa_tuner" / "gcode_gen.py").exists():
            return candidate
    return None


def load_prusa_tuner_modules() -> tuple[Any, Any, Any]:
    try:
        from prusa_pa_tuner.config import AppConfig
        from prusa_pa_tuner.gcode_gen import build_sweep
        from prusa_pa_tuner.runner import params_from_config
        return AppConfig, build_sweep, params_from_config
    except ImportError:
        src = find_prusa_tuner_src()
        if src and str(src) not in sys.path:
            sys.path.insert(0, str(src))
        try:
            from prusa_pa_tuner.config import AppConfig
            from prusa_pa_tuner.gcode_gen import build_sweep
            from prusa_pa_tuner.runner import params_from_config
            return AppConfig, build_sweep, params_from_config
        except ImportError as exc:
            raise SystemExit(
                "PrusaPATuner is required for prusa-sweep. Install it with "
                "`work/prusa_pa_venv/bin/python -m pip install -e work/PrusaPATuner` "
                "or set PRUSA_PA_TUNER_SRC to its src directory."
            ) from exc


def load_prusa_flow_modules() -> tuple[Any, Any, Any, Any]:
    try:
        from prusa_pa_tuner.flow_analysis import analyse_flow, flow_analysis_to_dict
        from prusa_pa_tuner.flow_gen import FlowRampParams, build_flow_ramp
        return FlowRampParams, build_flow_ramp, analyse_flow, flow_analysis_to_dict
    except ImportError:
        src = find_prusa_tuner_src()
        if src and str(src) not in sys.path:
            sys.path.insert(0, str(src))
        try:
            from prusa_pa_tuner.flow_analysis import analyse_flow, flow_analysis_to_dict
            from prusa_pa_tuner.flow_gen import FlowRampParams, build_flow_ramp
            return FlowRampParams, build_flow_ramp, analyse_flow, flow_analysis_to_dict
        except ImportError as exc:
            raise SystemExit(
                "PrusaPATuner flow modules are required for Prusa max-flow. "
                "Install with `work/prusa_pa_venv/bin/python -m pip install -e "
                "work/PrusaPATuner` or set PRUSA_PA_TUNER_SRC to its src directory."
            ) from exc


def make_prusa_app_config(args: argparse.Namespace, udp_host: str) -> Any:
    AppConfig, _, _ = load_prusa_tuner_modules()
    return AppConfig(
        printer_host=args.host,
        printer_api_key="",
        printer_user=getattr(args, "prusa_user", "maker"),
        printer_password="",
        udp_port=args.udp_port,
        nozzle_temp=args.nozzle_temp,
        preheat_temp=args.preheat_temp,
        nozzle_diameter=args.nozzle_diameter,
        filament_diameter=args.filament_diameter,
        slow_flow_mm3_s=args.slow_flow,
        fast_flow_mm3_s=args.fast_flow,
        slow_volume_mm3=args.slow_volume,
        fast_volume_mm3=args.fast_volume,
        cycles_per_K=args.cycles,
        accel_mm_s2=args.accel,
        k_min=args.k_min,
        k_max=args.k_max,
        k_step=args.k_step,
        purge_x=args.purge_x,
        purge_y=args.purge_y,
        purge_z=args.purge_z,
        coupled_dx_mm=args.coupled_dx,
        coupled_dy_mm=args.coupled_dy,
        coupled_dz_mm=args.coupled_dz,
        first_slow_leg_factor=args.first_slow_leg_factor,
        filament_label=args.filament_label,
    )


def make_prusa_flow_params(args: argparse.Namespace, udp_host: str) -> Any:
    FlowRampParams, _, _, _ = load_prusa_flow_modules()
    return FlowRampParams(
        nozzle_temp=args.nozzle_temp,
        preheat_temp=args.preheat_temp,
        nozzle_diameter=args.nozzle_diameter,
        filament_diameter=args.filament_diameter,
        filament_label=args.filament_label,
        min_flow_mm3_s=args.flow_min,
        max_flow_mm3_s=args.flow_max,
        flow_step_mm3_s=args.flow_step,
        dwell_s=args.flow_dwell,
        settle_frac=args.flow_settle_frac,
        warmup_s=args.flow_warmup,
        tare_dwell_s=args.flow_tare_dwell,
        accel_mm_s2=args.accel,
        purge_x=args.purge_x,
        purge_y=args.purge_y,
        purge_z=args.purge_z,
        baseline_dwell_s=args.baseline_dwell,
        z_marker_lift_mm=args.z_marker_lift,
        udp_host=udp_host,
        udp_port=args.udp_port,
        label=f"Max flow test -- {args.filament_label}",
    )


def compact_prusa_flow_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    compact = dict(analysis)
    compact_levels: list[dict[str, Any]] = []
    for level in analysis.get("levels", []):
        if not isinstance(level, dict):
            continue
        row = {k: v for k, v in level.items() if k not in {"t", "force"}}
        row["raw_window_points"] = len(level.get("t", []))
        compact_levels.append(row)
    compact["levels"] = compact_levels
    compact["raw_window_note"] = "Per-sample level traces are stored in raw_npz, not duplicated in this score JSON."
    return compact


def prusa_maxflow_result(
    *,
    analysis: dict[str, Any],
    plan: Any,
    output: str = "",
    raw_npz: str = "",
    manifest: str = "",
) -> dict[str, Any]:
    levels = [float(seg.flow_mm3_s) for seg in plan.segments]
    markers = {
        "deviation_flow": analysis.get("deviation_flow"),
        "variance_onset_flow": analysis.get("variance_onset_flow"),
        "collapse_flow": analysis.get("collapse_flow"),
    }
    soft = [
        float(value)
        for value in (markers["deviation_flow"], markers["variance_onset_flow"])
        if value is not None
    ]
    if soft:
        selected_flow = min(soft)
        confidence = 0.82
    elif markers["collapse_flow"] is not None:
        selected_flow = float(markers["collapse_flow"])
        confidence = 0.62
    elif levels:
        selected_flow = max(levels)
        confidence = 0.35
    else:
        selected_flow = None
        confidence = 0.0

    safe_max = analysis.get("recommended_max_flow")
    warnings: list[str] = []
    if safe_max is None:
        warnings.append("No safe max flow was selected; inspect the raw loadcell trace.")
    if not soft and markers["collapse_flow"] is None:
        warnings.append("No breakdown detected across the tested range; real limit may be above flow_max.")
    if analysis.get("sample_rate_hz", 0.0) and float(analysis.get("sample_rate_hz", 0.0)) < 40.0:
        warnings.append("Loadcell sample rate is low; repeat with a clean UDP path before trusting result.")

    result = {
        "kind": "tinman_prusa_loadcell_maxflow_score",
        "version": 1,
        "machine_label": "PrusaCoreOne",
        "adapter": "prusa_loadcell_maxflow_v1",
        "output": output,
        "manifest": manifest,
        "raw_npz": raw_npz,
        "selected_flow_mm3_s": selected_flow,
        "safe_max_flow_mm3_s": safe_max,
        "safety_factor": None if analysis.get("derate_frac") is None else 1.0 - float(analysis["derate_frac"]),
        "derate_frac": analysis.get("derate_frac"),
        "confidence": round(confidence, 3),
        "markers": markers,
        "levels_tested": levels,
        "analysis": compact_prusa_flow_analysis(analysis),
        "warnings": warnings,
        "note": "Loadcell-backed Prusa max-flow result. Use safe_max_flow_mm3_s for the TinMan flow governor or slicer profile limits.",
    }
    return result


def prusa_sweep(args: argparse.Namespace) -> dict[str, Any]:
    _, build_sweep, params_from_config = load_prusa_tuner_modules()
    udp_host = args.udp_host or local_ip_toward(args.host)
    cfg = make_prusa_app_config(args, udp_host)
    plan = build_sweep(params_from_config(cfg, udp_host=udp_host))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(plan.gcode)
    result: dict[str, Any] = {
        "output": str(output),
        "host": args.host,
        "udp_host": udp_host,
        "udp_port": args.udp_port,
        "k_values": [seg.k for seg in plan.segments],
        "segments": len(plan.segments),
        "cycles_per_k": plan.params.cycles_per_K,
        "estimated_sweep_seconds": round(
            plan.segments[-1].start_offset_s + plan.segments[-1].duration_s
            if plan.segments else 0.0,
            2,
        ),
        "contains": {
            "M334": "M334 " in plan.gcode,
            "M331_loadcell_value": "M331 loadcell_value" in plan.gcode,
            "M572": "M572 S" in plan.gcode,
            "xy_coupling": args.coupled_dx != 0 or args.coupled_dy != 0,
        },
    }
    warning = udp_target_warning(args.host, udp_host)
    if warning:
        result["warning"] = warning
    if args.plan:
        plan_path = Path(args.plan)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(
                {
                    "params": dataclasses.asdict(plan.params),
                    "segments": [dataclasses.asdict(seg) for seg in plan.segments],
                },
                indent=2,
            )
            + "\n"
        )
        result["plan"] = str(plan_path)
    return result


def prusa_maxflow_sweep(args: argparse.Namespace) -> dict[str, Any]:
    _, build_flow_ramp, _, _ = load_prusa_flow_modules()
    udp_host = args.udp_host or local_ip_toward(args.host)
    params = make_prusa_flow_params(args, udp_host)
    plan = build_flow_ramp(params)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(plan.gcode)

    levels = [float(seg.flow_mm3_s) for seg in plan.segments]
    result: dict[str, Any] = {
        "kind": "tinman_prusa_loadcell_maxflow_sweep",
        "version": 1,
        "output": str(output),
        "host": args.host,
        "udp_host": udp_host,
        "udp_port": args.udp_port,
        "flow_levels_mm3_s": levels,
        "segments": len(plan.segments),
        "estimated_sweep_seconds": round(
            plan.segments[-1].start_offset_s + plan.segments[-1].duration_s
            if plan.segments else 0.0,
            2,
        ),
        "contains": {
            "M334": "M334 " in plan.gcode,
            "M331_loadcell_value": "M331 loadcell_value" in plan.gcode,
            "M331_pos_z": "M331 pos_z" in plan.gcode,
            "FLOW_TUNER_markers": ";FLOW_TUNER" in plan.gcode,
        },
        "notes": [
            "Free-air stepped flow sweep for Prusa Core One Nextruder loadcell.",
            "Scoring expects UDP loadcell_value and optionally pos_z from the same run.",
        ],
    }
    warning = udp_target_warning(args.host, udp_host)
    if warning:
        result["warning"] = warning
    if args.plan:
        plan_path = Path(args.plan)
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(
            json.dumps(
                {
                    "kind": "tinman_prusa_loadcell_maxflow_plan",
                    "version": 1,
                    "params": dataclasses.asdict(plan.params),
                    "segments": [dataclasses.asdict(seg) for seg in plan.segments],
                },
                indent=2,
            )
            + "\n"
        )
        result["plan"] = str(plan_path)
    return result


def prusa_simulate(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"numpy is required for prusa-simulate: {exc}") from exc

    _, build_sweep, params_from_config = load_prusa_tuner_modules()
    try:
        from prusa_pa_tuner.analysis import analyse_sweep
    except ImportError:
        src = find_prusa_tuner_src()
        if src and str(src) not in sys.path:
            sys.path.insert(0, str(src))
        from prusa_pa_tuner.analysis import analyse_sweep

    udp_host = args.udp_host or "127.0.0.1"
    cfg = make_prusa_app_config(args, udp_host)
    plan = build_sweep(params_from_config(cfg, udp_host=udp_host))
    if not plan.segments:
        raise SystemExit("generated sweep has no K segments")

    sample_rate = float(args.sample_rate)
    sweep_t0 = 1000.0
    total_s = plan.segments[-1].start_offset_s + plan.segments[-1].duration_s + 1.0
    n = int(total_s * sample_rate)
    t_rel = np.arange(n, dtype=float) / sample_rate
    force = np.full(n, float(args.baseline_force), dtype=float)
    p = plan.params
    cycle = p.slow_half_s + p.fast_half_s
    rng = np.random.default_rng(args.seed)

    for seg in plan.segments:
        delta = abs(float(seg.k) - float(args.planted_k))
        overshoot = args.overshoot_gain * delta
        undershoot = args.undershoot_gain * delta
        for cycle_idx in range(seg.cycles):
            t_rise = seg.start_offset_s + cycle_idx * cycle + p.slow_half_s
            t_fall = seg.start_offset_s + (cycle_idx + 1) * cycle
            mask_rise = (t_rel >= t_rise) & (t_rel < t_fall)
            if mask_rise.any():
                force[mask_rise] = args.high_force + overshoot * np.exp(
                    -(t_rel[mask_rise] - (t_rise + args.rise_delay_s)) / args.rise_tau_s
                )
            mask_fall = (t_rel >= t_fall) & (t_rel < t_fall + p.slow_half_s)
            if mask_fall.any():
                force[mask_fall] = args.baseline_force - undershoot * np.exp(
                    -(t_rel[mask_fall] - (t_fall + args.fall_delay_s)) / args.fall_tau_s
                )

    if args.noise > 0:
        force += rng.normal(0.0, float(args.noise), n)

    result = analyse_sweep(
        sweep_t0=sweep_t0,
        force_t=sweep_t0 + t_rel,
        force_y=force,
        plan=plan,
        auto_detect_t0=False,
    )

    if args.raw_npz:
        raw = Path(args.raw_npz)
        raw.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            raw,
            force_t=sweep_t0 + t_rel,
            force_y=force,
            sweep_t0=np.array([sweep_t0]),
            k_values=np.array([seg.k for seg in plan.segments], dtype=float),
            planted_k=np.array([args.planted_k], dtype=float),
        )

    bd_error = None
    if result.bd_k_opt is not None:
        bd_error = float(result.bd_k_opt) - float(args.planted_k)
    summary: dict[str, Any] = {
        "kind": "tinman_prusa_pa_simulation",
        "version": 1,
        "planted_k": args.planted_k,
        "bd_k_opt": None if result.bd_k_opt is None else round(float(result.bd_k_opt), 5),
        "bd_error": None if bd_error is None else round(bd_error, 5),
        "passed": bool(bd_error is not None and abs(bd_error) <= args.tolerance),
        "tolerance": args.tolerance,
        "phase_k_opt": (
            None if result.phase_fit is None else round(float(result.phase_fit.k_opt), 5)
        ),
        "integral_k_opt": (
            None if result.integral_fit is None else round(float(result.integral_fit.k_opt), 5)
        ),
        "bd_segments": len(result.bd_segments),
        "bd_per_k": [
            {
                "k": round(float(row.k), 5),
                "included": row.n_segments_included,
                "total": row.n_segments_total,
                "normalised": {
                    name: round(float(value), 5)
                    for name, value in row.normalised.items()
                    if value == value
                },
            }
            for row in result.bd_per_k
        ],
        "sample_rate_hz": result.sample_rate_hz,
        "force_samples": int(n),
        "k_values": [seg.k for seg in plan.segments],
        "notes_tail": result.notes[-5:],
    }
    if args.raw_npz:
        summary["raw_npz"] = args.raw_npz
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def prusa_maxflow_simulate(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"numpy is required for prusa-maxflow-simulate: {exc}") from exc

    _, build_flow_ramp, analyse_flow, flow_analysis_to_dict = load_prusa_flow_modules()
    params = make_prusa_flow_params(args, args.udp_host or "127.0.0.1")
    plan = build_flow_ramp(params)
    rng = np.random.default_rng(args.seed)
    fs = float(args.sample_rate)
    if fs <= 0:
        raise SystemExit("--sample-rate must be positive")

    total_s = args.heat_s + len(plan.segments) * params.dwell_s + args.tail_s
    t = np.arange(0.0, total_s, 1.0 / fs, dtype=float)
    force = np.full_like(t, float(args.static_force), dtype=float)
    force += rng.normal(0.0, float(args.idle_noise), len(t))

    # A narrow non-extrusion disturbance makes the detector prove it can
    # distinguish homing/probing spikes from the long flow staircase.
    if args.heat_s > 10.0:
        spike = np.abs(t - 8.0) < 0.05
        force[spike] += float(args.homing_spike)

    previous_level = float(args.static_force)
    for i, seg in enumerate(plan.segments):
        q = float(seg.flow_mm3_s)
        start = args.heat_s + i * params.dwell_s
        end = start + params.dwell_s
        mask = (t >= start) & (t < end)
        if not mask.any():
            continue
        base = args.static_force + args.force_a * (q ** args.force_b) + args.force_c
        if q >= args.soft_break_flow:
            base += args.deviation_gain * ((q - args.soft_break_flow) ** 2)
        noise = args.flow_noise + max(0.0, q - args.variance_flow) * args.variance_gain
        if q >= args.collapse_flow:
            base = args.static_force + (base - args.static_force) * args.collapse_ratio
        local_t = t[mask] - start
        rise = np.clip(local_t / max(args.rise_time_s, 1e-6), 0.0, 1.0)
        force[mask] = previous_level + (base - previous_level) * rise
        force[mask] += rng.normal(0.0, noise, int(mask.sum()))
        previous_level = float(base)

    tail = t >= args.heat_s + len(plan.segments) * params.dwell_s
    force[tail] = args.static_force + rng.normal(0.0, args.idle_noise, int(tail.sum()))

    pos_z_t = None
    pos_z = None
    if args.include_pos_z:
        marker_return = max(0.5, args.heat_s - plan.segments[0].start_offset_s)
        pos_z_t = np.arange(0.0, total_s, 0.02, dtype=float)
        pos_z = np.full_like(pos_z_t, params.purge_z, dtype=float)
        pulse = (pos_z_t >= marker_return - 0.5) & (pos_z_t < marker_return)
        pos_z[pulse] = params.purge_z + params.z_marker_lift_mm

    analysis_obj = analyse_flow(
        sweep_t0=0.0,
        force_t=t,
        force_y=force,
        plan=plan,
        pos_z_t=pos_z_t,
        pos_z=pos_z,
        z_marker_lift_mm=params.z_marker_lift_mm,
        derate_frac=args.derate_frac,
        n_sigma=args.n_sigma,
        var_factor=args.var_factor,
        collapse_frac=args.collapse_frac,
    )
    analysis = flow_analysis_to_dict(analysis_obj)

    raw_npz = ""
    if args.raw_npz:
        raw = Path(args.raw_npz)
        raw.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            raw,
            force_t=t,
            force_y=force,
            pos_z_t=pos_z_t if pos_z_t is not None else np.array([]),
            pos_z=pos_z if pos_z is not None else np.array([]),
            sweep_t0=np.array([float(analysis_obj.sweep_t0)]),
            flow_levels=np.array([seg.flow_mm3_s for seg in plan.segments], dtype=float),
            min_flow_mm3_s=np.array([params.min_flow_mm3_s]),
            max_flow_mm3_s=np.array([params.max_flow_mm3_s]),
            flow_step_mm3_s=np.array([params.flow_step_mm3_s]),
            dwell_s=np.array([params.dwell_s]),
            settle_frac=np.array([params.settle_frac]),
            warmup_s=np.array([params.warmup_s]),
            tare_dwell_s=np.array([params.tare_dwell_s]),
            accel_mm_s2=np.array([params.accel_mm_s2]),
            purge_x=np.array([params.purge_x]),
            purge_y=np.array([params.purge_y]),
            purge_z=np.array([params.purge_z]),
            z_marker_lift_mm=np.array([params.z_marker_lift_mm]),
            filament_diameter=np.array([params.filament_diameter]),
            nozzle_temp=np.array([params.nozzle_temp]),
            filament_label=np.array([params.filament_label], dtype="U128"),
        )
        raw_npz = str(raw)

    result = prusa_maxflow_result(
        analysis=analysis,
        plan=plan,
        output=args.output or "",
        raw_npz=raw_npz,
    )
    result["simulation"] = {
        "soft_break_flow": args.soft_break_flow,
        "variance_flow": args.variance_flow,
        "collapse_flow": args.collapse_flow,
        "sample_rate_hz": args.sample_rate,
        "force_samples": int(len(t)),
        "seed": args.seed,
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def npz_scalar(data: Any, name: str, default: Any) -> Any:
    if name not in data or len(data[name]) == 0:
        return default
    value = data[name][0]
    if isinstance(default, str):
        return str(value)
    try:
        return float(value)
    except Exception:
        return default


def prusa_maxflow_score_npz(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"numpy is required for prusa-maxflow-score-npz: {exc}") from exc

    FlowRampParams, build_flow_ramp, analyse_flow, flow_analysis_to_dict = load_prusa_flow_modules()
    path = Path(args.input_npz)
    if not path.exists():
        raise SystemExit(f"Input NPZ not found: {path}")
    data = np.load(path, allow_pickle=True)
    params = FlowRampParams(
        nozzle_temp=npz_scalar(data, "nozzle_temp", 215.0),
        filament_diameter=npz_scalar(data, "filament_diameter", 1.75),
        filament_label=npz_scalar(data, "filament_label", "PLA"),
        min_flow_mm3_s=npz_scalar(data, "min_flow_mm3_s", 5.0),
        max_flow_mm3_s=npz_scalar(data, "max_flow_mm3_s", 30.0),
        flow_step_mm3_s=npz_scalar(data, "flow_step_mm3_s", 1.0),
        dwell_s=npz_scalar(data, "dwell_s", 3.0),
        settle_frac=npz_scalar(data, "settle_frac", 0.5),
        warmup_s=npz_scalar(data, "warmup_s", 3.0),
        tare_dwell_s=npz_scalar(data, "tare_dwell_s", 1.5),
        accel_mm_s2=npz_scalar(data, "accel_mm_s2", 5000.0),
        purge_x=npz_scalar(data, "purge_x", 30.0),
        purge_y=npz_scalar(data, "purge_y", 30.0),
        purge_z=npz_scalar(data, "purge_z", 50.0),
        z_marker_lift_mm=npz_scalar(data, "z_marker_lift_mm", 2.0),
    )
    plan = build_flow_ramp(params)
    force_t = np.asarray(data["force_t"], dtype=float)
    force_y = np.asarray(data["force_y"], dtype=float)
    pos_z_t = np.asarray(data["pos_z_t"], dtype=float) if "pos_z_t" in data and len(data["pos_z_t"]) else None
    pos_z = np.asarray(data["pos_z"], dtype=float) if "pos_z" in data and len(data["pos_z"]) else None
    analysis_obj = analyse_flow(
        sweep_t0=npz_scalar(data, "sweep_t0", float(force_t[0]) if len(force_t) else 0.0),
        force_t=force_t,
        force_y=force_y,
        plan=plan,
        pos_z_t=pos_z_t,
        pos_z=pos_z,
        z_marker_lift_mm=params.z_marker_lift_mm,
        derate_frac=args.derate_frac,
        n_sigma=args.n_sigma,
        var_factor=args.var_factor,
        collapse_frac=args.collapse_frac,
    )
    result = prusa_maxflow_result(
        analysis=flow_analysis_to_dict(analysis_obj),
        plan=plan,
        output=args.output or "",
        raw_npz=str(path),
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def prusa_enable_metrics(args: argparse.Namespace) -> dict[str, Any]:
    creds = prusa_credentials(
        Path(args.root),
        args.user_store,
        args.host,
        api_key=args.api_key or "",
        password=args.password or "",
        prusa_user=args.prusa_user,
    )
    udp_host = args.udp_host or local_ip_toward(args.host)
    commands = [
        f"M334 {udp_host} {args.udp_port}",
        "M331 loadcell_value",
        "M331 pos_x",
        "M331 pos_y",
        "M331 pos_z",
    ]
    result: dict[str, Any] = {
        "host": args.host,
        "execute": bool(args.execute),
        "commands": commands,
        "auth": {
            "api_key_present": bool(creds["api_key"]),
            "password_present": bool(creds["password"]),
            "user": creds["user"] if creds["password"] else "",
        },
    }
    warning = udp_target_warning(args.host, udp_host)
    if warning:
        result["warning"] = warning
    if not args.execute:
        return result
    result["responses"] = [
        prusa_send_command(args.host, command, creds, timeout=args.timeout)
        for command in commands
    ]
    return result


def moonraker_get(host: str, endpoint: str, timeout: float = 3.0) -> Any:
    url = f"http://{host}:7125/{endpoint.lstrip('/')}"
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    return json.loads(data)


def moonraker_post(host: str, endpoint: str, payload: dict[str, Any], timeout: float = 5.0) -> Any:
    url = f"http://{host}:7125/{endpoint.lstrip('/')}"
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def moonraker_print_state(host: str) -> str:
    try:
        status = moonraker_get(host, "/printer/objects/query?print_stats")
        stats = status.get("result", {}).get("status", {}).get("print_stats", {})
        return str(stats.get("state") or "unknown")
    except Exception:
        return "unknown"


def probe(host: str) -> dict[str, Any]:
    result: dict[str, Any] = {"host": host, "moonraker": False, "webcams": [], "objects": []}
    try:
        info = moonraker_get(host, "/printer/info")
        result["moonraker"] = True
        result["info"] = info.get("result", info)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        result["error"] = str(exc)
        return result

    try:
        objects = moonraker_get(host, "/printer/objects/list").get("result", {}).get("objects", [])
        result["objects"] = sorted(objects)
    except Exception as exc:  # read-only best effort
        result["objects_error"] = str(exc)

    try:
        webcams = moonraker_get(host, "/server/webcams/list").get("result", {}).get("webcams", [])
        result["webcams"] = webcams
    except Exception as exc:
        result["webcams_error"] = str(exc)

    interesting = [
        "extruder",
        "hall_filament_width_sensor",
        "motion_report",
        "flow_calibrator",
        "filament_parameters",
        "print_stats",
    ]
    query = "&".join(urllib.parse.quote(item) for item in interesting)
    try:
        status = moonraker_get(host, f"/printer/objects/query?{query}").get("result", {}).get("status", {})
        result["status"] = status
    except Exception as exc:
        result["status_error"] = str(exc)

    return result


def qidi_query_status(host: str, timeout: float = 3.0) -> dict[str, Any]:
    objects = [
        "extruder",
        "hall_filament_width_sensor",
        "motion_report",
        "tmc2209 extruder",
        "beacon",
        "probe",
        "toolhead",
        "gcode_move",
        "temperature_sensor beacon_coil",
        "print_stats",
    ]
    query = "&".join(urllib.parse.quote(item) for item in objects)
    status = moonraker_get(host, f"/printer/objects/query?{query}", timeout=timeout)
    return status.get("result", {}).get("status", {})


QIDI_MONITOR_OBJECTS = [
    "print_stats",
    "virtual_sdcard",
    "toolhead",
    "gcode_move",
    "motion_report",
    "extruder",
    "heater_bed",
    "heater_generic chamber",
    "hall_filament_width_sensor",
    "beacon",
    "temperature_sensor beacon_coil",
    "temperature_sensor Chamber_Thermal_Protection_Sensor",
    "tmc2209 extruder",
    "system_stats",
]

QIDI_MONITOR_CSV_FIELDS = [
    "sample_index",
    "captured_at",
    "elapsed_s",
    "ok",
    "error",
    "state",
    "filename",
    "current_layer",
    "total_layer",
    "progress",
    "file_position",
    "file_size",
    "print_duration_s",
    "total_duration_s",
    "filament_used_mm",
    "active_extruder",
    "extruder_temp_c",
    "extruder_target_c",
    "extruder_power",
    "pressure_advance",
    "smooth_time",
    "can_extrude",
    "bed_temp_c",
    "bed_target_c",
    "bed_power",
    "chamber_temp_c",
    "chamber_target_c",
    "chamber_power",
    "chamber_protection_temp_c",
    "hall_diameter_mm",
    "hall_raw",
    "hall_active",
    "beacon_coil_temp_c",
    "beacon_sample_temp_c",
    "beacon_frequency_hz",
    "beacon_data",
    "beacon_data_smooth",
    "beacon_x",
    "beacon_y",
    "beacon_z",
    "beacon_velocity_mm_s",
    "live_velocity_mm_s",
    "live_extruder_velocity_mm_s",
    "estimated_flow_mm3_s",
    "flow_diameter_source",
    "motion_x",
    "motion_y",
    "motion_z",
    "motion_e",
    "toolhead_x",
    "toolhead_y",
    "toolhead_z",
    "toolhead_e",
    "gcode_x",
    "gcode_y",
    "gcode_z",
    "gcode_e",
    "speed_factor",
    "extrude_factor",
    "feedrate_mm_s",
    "toolhead_max_velocity",
    "toolhead_max_accel",
    "square_corner_velocity",
    "extruder_run_current_a",
    "extruder_hold_current_a",
    "extruder_cs_actual",
    "system_load",
    "system_memavail_kb",
]


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_list_get(values: Any, index: int) -> Any:
    if isinstance(values, list) and len(values) > index:
        return values[index]
    return None


def qidi_query_monitor_status(host: str, timeout: float = 3.0) -> dict[str, Any]:
    query = "&".join(urllib.parse.quote(item) for item in QIDI_MONITOR_OBJECTS)
    status = moonraker_get(host, f"/printer/objects/query?{query}", timeout=timeout)
    return status.get("result", {}).get("status", {})


def flatten_qidi_monitor_sample(
    status: dict[str, Any],
    captured_at: str,
    elapsed_s: float,
    sample_index: int,
) -> dict[str, Any]:
    print_stats = status.get("print_stats", {})
    print_info = print_stats.get("info", {}) if isinstance(print_stats.get("info"), dict) else {}
    virtual_sdcard = status.get("virtual_sdcard", {})
    toolhead = status.get("toolhead", {})
    gcode_move = status.get("gcode_move", {})
    motion = status.get("motion_report", {})
    extruder = status.get("extruder", {})
    bed = status.get("heater_bed", {})
    chamber = status.get("heater_generic chamber", {})
    chamber_protection = status.get("temperature_sensor Chamber_Thermal_Protection_Sensor", {})
    hall = status.get("hall_filament_width_sensor", {})
    beacon = status.get("beacon", {})
    beacon_sample = beacon.get("last_received_sample") or beacon.get("last_sample") or {}
    beacon_coil = status.get("temperature_sensor beacon_coil", {})
    tmc = status.get("tmc2209 extruder", {})
    tmc_status = tmc.get("drv_status", {}) if isinstance(tmc.get("drv_status"), dict) else {}
    system_stats = status.get("system_stats", {})

    hall_diameter = safe_float(hall.get("Diameter"))
    nominal_diameter = 1.75
    flow_diameter = hall_diameter if hall.get("is_active") and hall_diameter else nominal_diameter
    live_e_velocity = safe_float(motion.get("live_extruder_velocity"))
    estimated_flow = None
    if flow_diameter and live_e_velocity is not None:
        estimated_flow = math.pi * (flow_diameter / 2.0) ** 2 * max(0.0, live_e_velocity)

    motion_pos = motion.get("live_position", [])
    toolhead_pos = toolhead.get("position", [])
    gcode_pos = gcode_move.get("gcode_position", [])
    beacon_pos = beacon_sample.get("pos", []) if isinstance(beacon_sample, dict) else []

    return {
        "sample_index": sample_index,
        "captured_at": captured_at,
        "elapsed_s": round(elapsed_s, 3),
        "ok": True,
        "error": "",
        "state": print_stats.get("state", ""),
        "filename": print_stats.get("filename", ""),
        "current_layer": print_info.get("current_layer"),
        "total_layer": print_info.get("total_layer"),
        "progress": virtual_sdcard.get("progress"),
        "file_position": virtual_sdcard.get("file_position"),
        "file_size": virtual_sdcard.get("file_size"),
        "print_duration_s": print_stats.get("print_duration"),
        "total_duration_s": print_stats.get("total_duration"),
        "filament_used_mm": print_stats.get("filament_used"),
        "active_extruder": toolhead.get("extruder", ""),
        "extruder_temp_c": extruder.get("temperature"),
        "extruder_target_c": extruder.get("target"),
        "extruder_power": extruder.get("power"),
        "pressure_advance": extruder.get("pressure_advance"),
        "smooth_time": extruder.get("smooth_time"),
        "can_extrude": extruder.get("can_extrude"),
        "bed_temp_c": bed.get("temperature"),
        "bed_target_c": bed.get("target"),
        "bed_power": bed.get("power"),
        "chamber_temp_c": chamber.get("temperature"),
        "chamber_target_c": chamber.get("target"),
        "chamber_power": chamber.get("power"),
        "chamber_protection_temp_c": chamber_protection.get("temperature"),
        "hall_diameter_mm": hall.get("Diameter"),
        "hall_raw": hall.get("Raw"),
        "hall_active": hall.get("is_active"),
        "beacon_coil_temp_c": beacon_coil.get("temperature"),
        "beacon_sample_temp_c": beacon_sample.get("temp") if isinstance(beacon_sample, dict) else None,
        "beacon_frequency_hz": beacon_sample.get("freq") if isinstance(beacon_sample, dict) else None,
        "beacon_data": beacon_sample.get("data") if isinstance(beacon_sample, dict) else None,
        "beacon_data_smooth": beacon_sample.get("data_smooth") if isinstance(beacon_sample, dict) else None,
        "beacon_x": safe_list_get(beacon_pos, 0),
        "beacon_y": safe_list_get(beacon_pos, 1),
        "beacon_z": safe_list_get(beacon_pos, 2),
        "beacon_velocity_mm_s": beacon_sample.get("vel") if isinstance(beacon_sample, dict) else None,
        "live_velocity_mm_s": motion.get("live_velocity"),
        "live_extruder_velocity_mm_s": motion.get("live_extruder_velocity"),
        "estimated_flow_mm3_s": estimated_flow,
        "flow_diameter_source": "hall_diameter" if hall.get("is_active") and hall_diameter else "nominal_1.75",
        "motion_x": safe_list_get(motion_pos, 0),
        "motion_y": safe_list_get(motion_pos, 1),
        "motion_z": safe_list_get(motion_pos, 2),
        "motion_e": safe_list_get(motion_pos, 3),
        "toolhead_x": safe_list_get(toolhead_pos, 0),
        "toolhead_y": safe_list_get(toolhead_pos, 1),
        "toolhead_z": safe_list_get(toolhead_pos, 2),
        "toolhead_e": safe_list_get(toolhead_pos, 3),
        "gcode_x": safe_list_get(gcode_pos, 0),
        "gcode_y": safe_list_get(gcode_pos, 1),
        "gcode_z": safe_list_get(gcode_pos, 2),
        "gcode_e": safe_list_get(gcode_pos, 3),
        "speed_factor": gcode_move.get("speed_factor"),
        "extrude_factor": gcode_move.get("extrude_factor"),
        "feedrate_mm_s": safe_float(gcode_move.get("speed")) / 60.0 if safe_float(gcode_move.get("speed")) is not None else None,
        "toolhead_max_velocity": toolhead.get("max_velocity"),
        "toolhead_max_accel": toolhead.get("max_accel"),
        "square_corner_velocity": toolhead.get("square_corner_velocity"),
        "extruder_run_current_a": tmc.get("run_current"),
        "extruder_hold_current_a": tmc.get("hold_current"),
        "extruder_cs_actual": tmc_status.get("cs_actual"),
        "system_load": system_stats.get("sysload"),
        "system_memavail_kb": system_stats.get("memavail"),
    }


def summarize_qidi_monitor_samples(
    samples: list[dict[str, Any]],
    host: str,
    duration_s: float,
    interval_s: float,
) -> dict[str, Any]:
    ok_samples = [sample for sample in samples if sample.get("ok")]
    state_counts: dict[str, int] = {}
    for sample in ok_samples:
        state = str(sample.get("state") or "unknown")
        state_counts[state] = state_counts.get(state, 0) + 1

    numeric_stats: dict[str, dict[str, Any]] = {}
    for field in QIDI_MONITOR_CSV_FIELDS:
        values = [safe_float(sample.get(field)) for sample in ok_samples]
        numeric_values = [value for value in values if value is not None]
        if not numeric_values:
            continue
        last_value = next(
            (safe_float(sample.get(field)) for sample in reversed(ok_samples) if safe_float(sample.get(field)) is not None),
            None,
        )
        numeric_stats[field] = {
            "count": len(numeric_values),
            "min": min(numeric_values),
            "max": max(numeric_values),
            "avg": sum(numeric_values) / len(numeric_values),
            "last": last_value,
        }

    first_ok = ok_samples[0] if ok_samples else {}
    last_ok = ok_samples[-1] if ok_samples else {}
    return {
        "kind": "tinman_qidi_plus4_readonly_monitor_summary",
        "version": 1,
        "host": host,
        "captured_at": utc_timestamp(),
        "requested_duration_s": duration_s,
        "interval_s": interval_s,
        "sample_count": len(samples),
        "ok_sample_count": len(ok_samples),
        "error_sample_count": len(samples) - len(ok_samples),
        "state_counts": state_counts,
        "filename": last_ok.get("filename") or first_ok.get("filename", ""),
        "first_progress": first_ok.get("progress"),
        "last_progress": last_ok.get("progress"),
        "first_layer": first_ok.get("current_layer"),
        "last_layer": last_ok.get("current_layer"),
        "total_layer": last_ok.get("total_layer") or first_ok.get("total_layer"),
        "last_pressure_advance": last_ok.get("pressure_advance"),
        "last_hall_diameter_mm": last_ok.get("hall_diameter_mm"),
        "last_beacon_coil_temp_c": last_ok.get("beacon_coil_temp_c"),
        "numeric_stats": numeric_stats,
        "notes": [
            "Read-only Moonraker GET polling only; this command does not move axes, extrude filament, change PA, or start/stop prints.",
            "estimated_flow_mm3_s uses live extruder velocity and Hall filament diameter when the Hall sensor is active; otherwise it falls back to nominal 1.75 mm filament.",
        ],
    }


def qidi_monitor_readonly(args: argparse.Namespace) -> dict[str, Any]:
    if args.duration < 0:
        raise SystemExit("--duration must be zero or positive")
    if args.interval <= 0:
        raise SystemExit("--interval must be positive")

    jsonl_handle = None
    csv_handle = None
    writer: Optional[csv.DictWriter] = None
    samples: list[dict[str, Any]] = []
    start = time.monotonic()
    deadline = start + args.duration

    if args.jsonl:
        jsonl_path = Path(args.jsonl)
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        jsonl_handle = jsonl_path.open("w", encoding="utf-8")
    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        csv_handle = csv_path.open("w", newline="", encoding="utf-8")
        writer = csv.DictWriter(csv_handle, fieldnames=QIDI_MONITOR_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()

    try:
        sample_index = 0
        while True:
            captured_at = utc_timestamp()
            elapsed_s = time.monotonic() - start
            try:
                status = qidi_query_monitor_status(args.host, timeout=args.timeout)
                sample = flatten_qidi_monitor_sample(status, captured_at, elapsed_s, sample_index)
                if args.include_raw_status:
                    sample["raw_status"] = status
            except Exception as exc:
                sample = {
                    "sample_index": sample_index,
                    "captured_at": captured_at,
                    "elapsed_s": round(elapsed_s, 3),
                    "ok": False,
                    "error": str(exc),
                }
            samples.append(sample)
            if jsonl_handle:
                jsonl_handle.write(json.dumps(sample, sort_keys=True) + "\n")
                jsonl_handle.flush()
            if writer and csv_handle:
                writer.writerow({field: sample.get(field) for field in QIDI_MONITOR_CSV_FIELDS})
                csv_handle.flush()

            sample_index += 1
            if args.duration == 0:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(args.interval, remaining))
    finally:
        if jsonl_handle:
            jsonl_handle.close()
        if csv_handle:
            csv_handle.close()

    summary = summarize_qidi_monitor_samples(samples, args.host, args.duration, args.interval)
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def qidi_telemetry(args: argparse.Namespace) -> dict[str, Any]:
    result: dict[str, Any] = {
        "kind": "tinman_qidi_plus4_telemetry",
        "version": 1,
        "host": args.host,
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": qidi_query_status(args.host, timeout=args.timeout),
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def qidi_live_pressure_advance(host: str, timeout: float = 3.0) -> Optional[float]:
    try:
        extruder = qidi_query_status(host, timeout=timeout).get("extruder", {})
        value = extruder.get("pressure_advance")
        return None if value is None else float(value)
    except Exception:
        return None


def qidi_candidate_values(k_center: float, k_half_span: float, steps: int, k_min: float, k_max: float) -> list[float]:
    if steps < 3:
        raise SystemExit("--steps must be at least 3")
    if k_half_span <= 0:
        raise SystemExit("--k-half-span must be positive")
    if k_min < 0 or k_max <= k_min:
        raise SystemExit("--k-min/--k-max are invalid")
    raw = [
        k_center - k_half_span + (2.0 * k_half_span * i / (steps - 1))
        for i in range(steps)
    ]
    values = sorted({round(min(k_max, max(k_min, value)), 5) for value in raw})
    if len(values) < 3:
        raise SystemExit("candidate range collapsed to fewer than 3 unique K values")
    return values


def point_in_edge_band(x: float, y: float, bed_x: float, bed_y: float, band: float) -> bool:
    return x <= band or x >= bed_x - band or y <= band or y >= bed_y - band


def validate_point_on_bed(x: float, y: float, bed_x: float, bed_y: float, label: str) -> None:
    if x < 0 or x > bed_x or y < 0 or y > bed_y:
        raise SystemExit(f"{label} is outside the configured bed: X{x:.3f} Y{y:.3f}")


def validate_edge_band_point(x: float, y: float, bed_x: float, bed_y: float, band: float, label: str) -> None:
    validate_point_on_bed(x, y, bed_x, bed_y, label)
    if not point_in_edge_band(x, y, bed_x, bed_y, band):
        raise SystemExit(f"{label} is outside the {band:.1f} mm edge band: X{x:.3f} Y{y:.3f}")


def pa_candidate_geometry(args: argparse.Namespace, index: int) -> tuple[float, float, float, float, float, float]:
    layout = getattr(args, "layout", "stacked")
    if layout == "stacked":
        y = args.y + index * args.spacing
        x0 = args.x
        x1 = args.x + args.length
        return x0, y, x1, y, x1, y + args.corner_leg
    if layout == "front-edge":
        x0 = args.x + index * args.spacing
        x1 = x0 + args.length
        return x0, args.y, x1, args.y, x1, args.y + args.corner_leg
    if layout == "rear-edge":
        x0 = args.x + index * args.spacing
        x1 = x0 + args.length
        y = args.bed_y - args.y
        return x0, y, x1, y, x1, y - args.corner_leg
    raise SystemExit(f"unsupported PA coupon layout: {layout}")


def validate_pa_coupon_layout(args: argparse.Namespace, candidate_count: int) -> None:
    layout = getattr(args, "layout", "stacked")
    if layout == "stacked":
        if args.spacing <= args.corner_leg + args.line_width * 3.0:
            raise SystemExit(
                "--spacing must be larger than --corner-leg plus clearance so coupon candidates do not overlap"
            )
        return

    if layout in ("front-edge", "rear-edge"):
        if args.spacing <= args.length + args.line_width * 3.0:
            raise SystemExit(
                f"--spacing must be larger than --length plus clearance for the {layout} PA layout"
            )
        if args.edge_band_width <= 0:
            raise SystemExit("--edge-band-width must be positive")
        for i in range(candidate_count):
            x0, y0, x1, y1, x2, y2 = pa_candidate_geometry(args, i)
            validate_edge_band_point(x0, y0, args.bed_x, args.bed_y, args.edge_band_width, f"PA candidate {i} line_start")
            validate_edge_band_point(x1, y1, args.bed_x, args.bed_y, args.edge_band_width, f"PA candidate {i} line_end")
            validate_edge_band_point(x2, y2, args.bed_x, args.bed_y, args.edge_band_width, f"PA candidate {i} corner_end")
        return

    raise SystemExit(f"unsupported PA coupon layout: {layout}")


def qidi_beacon_probe_points(manifest: dict[str, Any], sample_offset: float = 3.0) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for candidate in manifest["candidates"]:
        idx = int(candidate["index"])
        k = float(candidate["k"])
        x0, y0 = candidate["line_start"]
        x1, y1 = candidate["line_end"]
        x2, y2 = candidate["corner_end"]
        line_mid = [(x0 + x1) / 2.0, y0]
        line_dx = float(x1) - float(x0)
        line_dy = float(y1) - float(y0)
        line_length = max(0.001, math.hypot(line_dx, line_dy))
        line_ux = line_dx / line_length
        line_uy = line_dy / line_length
        corner_dx = float(x2) - float(x1)
        corner_dy = float(y2) - float(y1)
        corner_length = max(0.001, math.hypot(corner_dx, corner_dy))
        corner_ux = corner_dx / corner_length
        corner_uy = corner_dy / corner_length
        corner_sample = min(sample_offset, corner_length)
        points.extend(
            [
                {
                    "candidate_index": idx,
                    "k": k,
                    "role": "line_mid_height",
                    "xy": [round(line_mid[0], 3), round(line_mid[1], 3)],
                    "why": "Bead height consistency along the straight line.",
                },
                {
                    "candidate_index": idx,
                    "k": k,
                    "role": "pre_corner_blob",
                    "xy": [
                        round(float(x1) - line_ux * sample_offset, 3),
                        round(float(y1) - line_uy * sample_offset, 3),
                    ],
                    "why": "Low PA tends to overfill immediately before deceleration into the corner.",
                },
                {
                    "candidate_index": idx,
                    "k": k,
                    "role": "corner_apex",
                    "xy": [round(x1, 3), round(y1, 3)],
                    "why": "Corner mass and rounding are the main PA signal in Klipper-style tests.",
                },
                {
                    "candidate_index": idx,
                    "k": k,
                    "role": "post_corner_gap",
                    "xy": [
                        round(float(x1) + corner_ux * corner_sample, 3),
                        round(float(y1) + corner_uy * corner_sample, 3),
                    ],
                    "why": "High PA tends to underfill after re-acceleration out of the corner.",
                },
                {
                    "candidate_index": idx,
                    "k": k,
                    "role": "local_plate_reference",
                    "xy": [round(x1 + sample_offset, 3), round(y1 + sample_offset, 3)],
                    "why": "Nearby bare-plate reference for local Z/plate slope correction.",
                },
            ]
        )
    return points


def qidi_beacon_plan_from_manifest(
    manifest: dict[str, Any],
    safe_z: float,
    travel_speed: float,
    sample_offset: float,
) -> dict[str, Any]:
    points = qidi_beacon_probe_points(manifest, sample_offset=sample_offset)
    commands = [
        "; TINMAN_QIDI_BEACON_PROBE_PLAN_DRY_RUN",
        "; Verify Beacon contact probe behavior on an idle printer before executing any probing.",
        "; Install/review outputs/auto_pa_v0/tinman_beacon_pa_macros_review.cfg before converting these calls to live G-code.",
        "G90",
        f"G1 Z{safe_z:.3f} F900",
    ]
    macro_calls: list[str] = []
    for point in points:
        x, y = point["xy"]
        commands.append(
            f"; candidate={point['candidate_index']} k={point['k']:.5f} role={point['role']}"
        )
        commands.append(f"G1 X{x:.3f} Y{y:.3f} F{int(travel_speed * 60)}")
        call = (
            "TINMAN_BEACON_PA_SAMPLE "
            f"CANDIDATE={point['candidate_index']} "
            f"K={point['k']:.5f} "
            f"ROLE={point['role']} "
            f"X{x:.3f} Y{y:.3f}"
        )
        macro_calls.append(call)
        commands.append(f"; {call}")
        commands.append("; dry-run only: reviewed machine macro decides PROBE vs BEACON_POKE")
    return {
        "kind": "tinman_qidi_beacon_probe_plan",
        "version": 1,
        "source_manifest_kind": manifest.get("kind", ""),
        "safe_z": safe_z,
        "sample_offset": sample_offset,
        "points": points,
        "macro_calls": macro_calls,
        "measurement_schema": {
            "required_fields": ["candidate_index", "role"],
            "z_fields": ["measured_z", "contact_z", "trigger_z", "z"],
            "accepted_formats": ["json", "csv"],
            "parser": "auto_pa.py beacon-score-coupon --measurements <file>",
        },
        "dry_run_commands": commands,
        "notes": [
            "This is a planning artifact, not an execution file.",
            "Beacon contact probing can deform a hot plastic bead; validate with a cold coupon and supervised probing first.",
            "Use these points to add bead-height evidence after the stock-camera scorer is working.",
        ],
    }


def qidi_generate_coupon(args: argparse.Namespace) -> dict[str, Any]:
    k_center = args.k_center
    if args.use_live_k:
        live_k = qidi_live_pressure_advance(args.host, timeout=args.timeout)
        if live_k is not None:
            k_center = live_k
    candidates = qidi_candidate_values(
        k_center=k_center,
        k_half_span=args.k_half_span,
        steps=args.steps,
        k_min=args.k_min,
        k_max=args.k_max,
    )
    validate_pa_coupon_layout(args, len(candidates))
    e_per_mm = extrusion_per_mm(
        args.line_width,
        args.layer_height,
        args.filament_diameter,
        args.flow_ratio,
    )
    manifest: dict[str, Any] = {
        "kind": "tinman_qidi_plus4_auto_pa_coupon",
        "version": 1,
        "adapter": "qidi_plus4_cv_hall_beacon_v1",
        "host": args.host,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": [args.x, args.y],
        "layout": args.layout,
        "bed_size": [args.bed_x, args.bed_y],
        "edge_band_width": args.edge_band_width if args.layout != "stacked" else None,
        "line_width": args.line_width,
        "layer_height": args.layer_height,
        "filament_diameter": args.filament_diameter,
        "flow_ratio": args.flow_ratio,
        "speed_mm_s": args.speed,
        "travel_speed_mm_s": args.travel_speed,
        "accel": args.accel,
        "fallback_k": round(k_center, 5),
        "candidate_strategy": {
            "center": round(k_center, 5),
            "half_span": args.k_half_span,
            "steps_requested": args.steps,
            "k_min": args.k_min,
            "k_max": args.k_max,
        },
        "sensor_inputs": {
            "primary": "stock camera coupon scoring",
            "normalization": "hall_filament_width_sensor Diameter",
            "optional_probe": "Beacon contact bead-height sampling plan",
            "safety_filters": ["print_stats.state", "extruder.temperature", "tmc2209 extruder drv_status"],
        },
        "candidates": [],
    }

    g: list[str] = []
    g.append("; TINMAN_QIDI_AUTO_PA_COUPON_START")
    g.append("; adapter=qidi_plus4_cv_hall_beacon_v1")
    g.append(f"; candidates={','.join(f'{k:.5f}' for k in candidates)}")
    g.append("SAVE_GCODE_STATE NAME=TINMAN_QIDI_AUTO_PA")
    g.append("G90")
    g.append("M83")
    if args.enable_hall:
        g.append("M8029 D1 ; enable Qidi hall filament width sensor")
    g.append(f"M204 S{int(args.accel)}")
    g.append(f"G1 Z{args.z:.3f} F900")
    first_x, first_y, _, _, _, _ = pa_candidate_geometry(args, 0)
    g.append(f"G1 X{first_x:.3f} Y{first_y:.3f} F{int(args.travel_speed * 60)}")
    g.append(f"G1 F{int(args.speed * 60)}")

    for i, k in enumerate(candidates):
        x0, y, x1, _, x2, y2 = pa_candidate_geometry(args, i)
        e1 = args.length * e_per_mm
        e2 = args.corner_leg * e_per_mm
        g.append(f"; TINMAN_QIDI_PA_CANDIDATE index={i} k={k:.5f}")
        g.append(pa_command("m900", k))
        g.append(f"G1 X{x0:.3f} Y{y:.3f} F{int(args.travel_speed * 60)}")
        g.append(f"G1 X{x1:.3f} Y{y:.3f} E{e1:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 X{x2:.3f} Y{y2:.3f} E{e2:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 E-{args.retract:.5f} F1800")
        g.append(f"G1 Z{args.z + args.z_hop:.3f} F900")
        g.append(f"G1 Z{args.z:.3f} F900")
        g.append(f"G1 E{args.retract:.5f} F1800")
        manifest["candidates"].append(
            {
                "index": i,
                "k": round(k, 5),
                "line_start": [round(x0, 3), round(y, 3)],
                "line_end": [round(x1, 3), round(y, 3)],
                "corner_end": [round(x2, 3), round(y2, 3)],
            }
        )

    g.append(pa_command("m900", k_center))
    g.append("M400")
    g.append("RESTORE_GCODE_STATE NAME=TINMAN_QIDI_AUTO_PA MOVE=0")
    g.append("; TINMAN_QIDI_AUTO_PA_COUPON_END")
    g.append("")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(g))

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    result: dict[str, Any] = {
        "kind": "tinman_qidi_plus4_auto_pa_coupon_result",
        "version": 1,
        "host": args.host,
        "output": str(output),
        "manifest": str(manifest_path),
        "k_values": candidates,
        "fallback_k": round(k_center, 5),
        "estimated_print_seconds": round(
            len(candidates) * ((args.length + args.corner_leg) / max(args.speed, 1.0) + 1.3),
            1,
        ),
    }

    if args.homography_template:
        template_path = Path(args.homography_template)
        template = homography_template(manifest_path, args.homography_margin)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(json.dumps(template, indent=2) + "\n")
        result["homography_template"] = str(template_path)
    if args.beacon_plan:
        plan_path = Path(args.beacon_plan)
        plan = qidi_beacon_plan_from_manifest(
            manifest,
            safe_z=args.beacon_safe_z,
            travel_speed=args.travel_speed,
            sample_offset=args.beacon_sample_offset,
        )
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        result["beacon_plan"] = str(plan_path)

    return result


def qidi_score_coupon(args: argparse.Namespace) -> dict[str, Any]:
    result = score_coupon(args)
    manifest = read_json(Path(args.manifest))
    telemetry: dict[str, Any] = {}
    if args.telemetry:
        telemetry = read_json(Path(args.telemetry))
    elif args.host:
        try:
            telemetry = {
                "kind": "tinman_qidi_plus4_telemetry_inline",
                "status": qidi_query_status(args.host, timeout=args.timeout),
            }
        except Exception as exc:
            telemetry = {"error": f"{type(exc).__name__}: {exc}"}

    hall_diameter = None
    status = telemetry.get("status") if isinstance(telemetry, dict) else None
    if isinstance(status, dict):
        hall = status.get("hall_filament_width_sensor")
        if isinstance(hall, dict) and hall.get("Diameter") is not None:
            hall_diameter = float(hall["Diameter"])

    selected = result.get("best")
    trusted = False
    warnings: list[str] = []
    if selected:
        trusted = True
        if float(selected.get("confidence", 0.0)) < args.min_confidence:
            trusted = False
            warnings.append("Best candidate confidence is below --min-confidence.")
        if float(selected.get("width_cv", 1.0)) > args.max_width_cv:
            trusted = False
            warnings.append("Best candidate width variation is above --max-width-cv.")
        if float(selected.get("score", 999.0)) > args.max_score:
            trusted = False
            warnings.append("Best candidate score is above --max-score.")
    else:
        warnings.append("No best candidate was selected by the image scorer.")

    if hall_diameter is not None:
        nominal = float(manifest.get("filament_diameter", 1.75))
        area_ratio = (hall_diameter / nominal) ** 2
        if abs(area_ratio - 1.0) > args.max_hall_area_delta:
            trusted = False
            warnings.append(
                "Hall filament diameter differs enough to affect volume; verify flow before trusting PA."
            )
    else:
        area_ratio = None
        trusted = False
        warnings.append("No Hall filament diameter was available for this score.")

    result["qidi"] = {
        "adapter": "qidi_plus4_cv_hall_beacon_v1",
        "selected_k": None if not selected else selected.get("k"),
        "apply_command": None if not selected else pa_command("m900", float(selected["k"])),
        "trusted_for_supervised_apply": trusted,
        "hall_filament_diameter": hall_diameter,
        "hall_area_ratio_vs_manifest": None if area_ratio is None else round(float(area_ratio), 5),
        "warnings": warnings,
        "note": "Use supervised application until several coupons agree with human inspection.",
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def qidi_apply_pa(args: argparse.Namespace) -> dict[str, Any]:
    return apply_pa(
        args.host,
        args.k,
        flavor="m900",
        execute=args.execute,
        allow_printing=args.allow_printing,
    )


def klipper_cv_generate_coupon(args: argparse.Namespace) -> dict[str, Any]:
    candidates = qidi_candidate_values(
        k_center=args.k_center,
        k_half_span=args.k_half_span,
        steps=args.steps,
        k_min=args.k_min,
        k_max=args.k_max,
    )
    validate_pa_coupon_layout(args, len(candidates))
    e_per_mm = extrusion_per_mm(
        args.line_width,
        args.layer_height,
        args.filament_diameter,
        args.flow_ratio,
    )
    manifest: dict[str, Any] = {
        "kind": "tinman_klipper_cv_auto_pa_coupon",
        "version": 1,
        "adapter": args.adapter,
        "machine_label": args.machine_label,
        "host": args.host,
        "tool": args.tool,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": [args.x, args.y],
        "layout": args.layout,
        "bed_size": [args.bed_x, args.bed_y],
        "edge_band_width": args.edge_band_width if args.layout != "stacked" else None,
        "line_width": args.line_width,
        "layer_height": args.layer_height,
        "filament_diameter": args.filament_diameter,
        "flow_ratio": args.flow_ratio,
        "speed_mm_s": args.speed,
        "travel_speed_mm_s": args.travel_speed,
        "accel": args.accel,
        "fallback_k": round(args.k_center, 5),
        "pa_command_flavor": args.flavor,
        "candidate_strategy": {
            "center": round(args.k_center, 5),
            "half_span": args.k_half_span,
            "steps_requested": args.steps,
            "k_min": args.k_min,
            "k_max": args.k_max,
        },
        "sensor_inputs": {
            "primary": "stock or external camera coupon scoring",
            "optional_probe": "Beacon contact bead-height sampling plan" if args.beacon_plan else "",
            "normalization": args.normalization_note,
            "safety_filters": ["print_stats.state", "extruder.temperature", "tmc driver status"],
        },
        "candidates": [],
    }

    g: list[str] = []
    g.append("; TINMAN_KLIPPER_CV_AUTO_PA_COUPON_START")
    g.append(f"; machine={args.machine_label}")
    g.append(f"; adapter={args.adapter}")
    g.append(f"; candidates={','.join(f'{k:.5f}' for k in candidates)}")
    g.append("SAVE_GCODE_STATE NAME=TINMAN_KLIPPER_CV_AUTO_PA")
    g.append("G90")
    g.append("M83")
    if args.tool:
        g.append(args.tool)
    if args.pre_gcode:
        for command in args.pre_gcode:
            g.append(command)
    g.append(f"M204 S{int(args.accel)}")
    g.append(f"G1 Z{args.z:.3f} F900")
    first_x, first_y, _, _, _, _ = pa_candidate_geometry(args, 0)
    g.append(f"G1 X{first_x:.3f} Y{first_y:.3f} F{int(args.travel_speed * 60)}")
    g.append(f"G1 F{int(args.speed * 60)}")

    for i, k in enumerate(candidates):
        x0, y, x1, _, x2, y2 = pa_candidate_geometry(args, i)
        e1 = args.length * e_per_mm
        e2 = args.corner_leg * e_per_mm
        g.append(f"; TINMAN_KLIPPER_CV_PA_CANDIDATE index={i} k={k:.5f}")
        g.append(pa_command(args.flavor, k))
        g.append(f"G1 X{x0:.3f} Y{y:.3f} F{int(args.travel_speed * 60)}")
        g.append(f"G1 X{x1:.3f} Y{y:.3f} E{e1:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 X{x2:.3f} Y{y2:.3f} E{e2:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 E-{args.retract:.5f} F1800")
        g.append(f"G1 Z{args.z + args.z_hop:.3f} F900")
        g.append(f"G1 Z{args.z:.3f} F900")
        g.append(f"G1 E{args.retract:.5f} F1800")
        manifest["candidates"].append(
            {
                "index": i,
                "k": round(k, 5),
                "line_start": [round(x0, 3), round(y, 3)],
                "line_end": [round(x1, 3), round(y, 3)],
                "corner_end": [round(x2, 3), round(y2, 3)],
            }
        )

    g.append(pa_command(args.flavor, args.k_center))
    g.append("M400")
    g.append("RESTORE_GCODE_STATE NAME=TINMAN_KLIPPER_CV_AUTO_PA MOVE=0")
    g.append("; TINMAN_KLIPPER_CV_AUTO_PA_COUPON_END")
    g.append("")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(g))

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    result: dict[str, Any] = {
        "kind": "tinman_klipper_cv_auto_pa_coupon_result",
        "version": 1,
        "machine_label": args.machine_label,
        "host": args.host,
        "tool": args.tool,
        "output": str(output),
        "manifest": str(manifest_path),
        "k_values": candidates,
        "fallback_k": round(args.k_center, 5),
        "estimated_print_seconds": round(
            len(candidates) * ((args.length + args.corner_leg) / max(args.speed, 1.0) + 1.3),
            1,
        ),
    }

    if args.homography_template:
        template_path = Path(args.homography_template)
        template = homography_template(manifest_path, args.homography_margin)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(json.dumps(template, indent=2) + "\n")
        result["homography_template"] = str(template_path)
    if args.beacon_plan:
        plan_path = Path(args.beacon_plan)
        plan = qidi_beacon_plan_from_manifest(
            manifest,
            safe_z=args.beacon_safe_z,
            travel_speed=args.travel_speed,
            sample_offset=args.beacon_sample_offset,
        )
        plan["machine_label"] = args.machine_label
        plan["adapter"] = args.adapter
        plan["tool"] = args.tool
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        result["beacon_plan"] = str(plan_path)

    return result


def klipper_cv_apply_pa(args: argparse.Namespace) -> dict[str, Any]:
    return apply_pa(
        args.host,
        args.k,
        flavor=args.flavor,
        execute=args.execute,
        allow_printing=args.allow_printing,
    )


def snapshot_url_candidates(host: str, snapshot_url: str) -> list[str]:
    if snapshot_url.startswith(("http://", "https://")):
        return [snapshot_url]
    if not snapshot_url.startswith("/"):
        snapshot_url = "/" + snapshot_url
    return [
        f"http://{host}:7125{snapshot_url}",
        f"http://{host}{snapshot_url}",
    ]


def capture_snapshot(host: str, output: Path) -> dict[str, Any]:
    webcams = moonraker_get(host, "/server/webcams/list").get("result", {}).get("webcams", [])
    enabled = [cam for cam in webcams if cam.get("enabled", True) and cam.get("snapshot_url")]
    if not enabled:
        raise SystemExit(f"No enabled snapshot webcam found for {host}")

    errors: list[str] = []
    for cam in enabled:
        for url in snapshot_url_candidates(host, str(cam["snapshot_url"])):
            try:
                with urllib.request.urlopen(url, timeout=5.0) as resp:
                    data = resp.read()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(data)
                return {
                    "host": host,
                    "output": str(output),
                    "webcam": cam.get("name", ""),
                    "url": url,
                    "bytes": len(data),
                }
            except Exception as exc:
                errors.append(f"{url}: {exc}")
    raise SystemExit("Unable to fetch webcam snapshot:\n" + "\n".join(errors))


def pa_command(flavor: str, k: float) -> str:
    if flavor == "prusa":
        return f"M572 S{k:.5f}"
    if flavor in {"klipper", "set_pressure_advance"}:
        return f"SET_PRESSURE_ADVANCE ADVANCE={k:.5f}"
    if flavor in {"rrf", "reprap"}:
        return f"M572 D0 S{k:.5f}"
    if flavor == "repetier":
        return f"M233 X{k:.5f} Y{k:.5f}"
    return f"M900 K{k:.5f}"


def extrusion_per_mm(line_width: float, layer_height: float, filament_diameter: float, flow_ratio: float) -> float:
    filament_area = math.pi * (filament_diameter / 2.0) ** 2
    return (line_width * layer_height * flow_ratio) / filament_area


def generate_coupon(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.steps < 2:
        raise SystemExit("--steps must be at least 2")
    if args.length <= 0 or args.spacing <= 0:
        raise SystemExit("--length and --spacing must be positive")
    e_per_mm = extrusion_per_mm(args.line_width, args.layer_height, args.filament_diameter, args.flow_ratio)
    candidates = [
        args.k_min + i * (args.k_max - args.k_min) / (args.steps - 1)
        for i in range(args.steps)
    ]
    manifest: dict[str, Any] = {
        "kind": "tinman_auto_pa_coupon",
        "version": 1,
        "origin": [args.x, args.y],
        "line_width": args.line_width,
        "layer_height": args.layer_height,
        "filament_diameter": args.filament_diameter,
        "flow_ratio": args.flow_ratio,
        "speed_mm_s": args.speed,
        "accel": args.accel,
        "candidates": [],
    }

    g: list[str] = []
    g.append("; TINMAN_AUTO_PA_COUPON_START")
    g.append(f"; candidates={','.join(f'{k:.5f}' for k in candidates)}")
    g.append("G90")
    g.append("M83")
    g.append(f"M204 S{int(args.accel)}")
    g.append(f"G1 Z{args.z:.3f} F900")
    g.append(f"G1 X{args.x:.3f} Y{args.y:.3f} F{int(args.travel_speed * 60)}")
    g.append(f"G1 F{int(args.speed * 60)}")

    for i, k in enumerate(candidates):
        y = args.y + i * args.spacing
        x0 = args.x
        x1 = args.x + args.length
        x2 = args.x + args.length
        y2 = y + args.corner_leg
        e1 = args.length * e_per_mm
        e2 = args.corner_leg * e_per_mm
        g.append(f"; TINMAN_PA_CANDIDATE index={i} k={k:.5f}")
        g.append(pa_command(args.flavor, k))
        g.append(f"G1 X{x0:.3f} Y{y:.3f} F{int(args.travel_speed * 60)}")
        g.append(f"G1 X{x1:.3f} Y{y:.3f} E{e1:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 X{x2:.3f} Y{y2:.3f} E{e2:.5f} F{int(args.speed * 60)}")
        g.append(f"G1 E-{args.retract:.5f} F1800")
        g.append(f"G1 Z{args.z + 0.35:.3f} F900")
        g.append(f"G1 Z{args.z:.3f} F900")
        g.append(f"G1 E{args.retract:.5f} F1800")
        manifest["candidates"].append(
            {
                "index": i,
                "k": round(k, 5),
                "line_start": [round(x0, 3), round(y, 3)],
                "line_end": [round(x1, 3), round(y, 3)],
                "corner_end": [round(x2, 3), round(y2, 3)],
            }
        )

    g.append(pa_command(args.flavor, args.fallback_k))
    g.append("; TINMAN_AUTO_PA_COUPON_END")
    g.append("")
    return "\n".join(g), manifest


def apply_pa(host: str, k: float, flavor: str, execute: bool, allow_printing: bool) -> dict[str, Any]:
    command = pa_command(flavor, k)
    if not execute:
        return {"host": host, "execute": False, "command": command}
    state = moonraker_print_state(host)
    if state in {"printing", "paused"} and not allow_printing:
        return {
            "host": host,
            "execute": False,
            "blocked": True,
            "state": state,
            "command": command,
            "reason": "Printer is mid-job; pass --allow-printing to intentionally update live PA.",
        }
    return moonraker_post(host, "/printer/gcode/script", {"script": command})


def coupon_bounds(manifest: dict[str, Any], margin: float) -> tuple[float, float, float, float]:
    points: list[list[float]] = []
    for candidate in manifest["candidates"]:
        points.extend([candidate["line_start"], candidate["line_end"], candidate["corner_end"]])
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def homography_template(manifest_path: Path, margin: float) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    min_x, min_y, max_x, max_y = coupon_bounds(manifest, margin)
    return {
        "kind": "tinman_auto_pa_homography",
        "version": 1,
        "instructions": "Fill image_points with matching pixel coordinates from the snapshot: top-left, top-right, bottom-right, bottom-left of the bed_points box.",
        "bed_points": [
            [round(min_x, 3), round(min_y, 3)],
            [round(max_x, 3), round(min_y, 3)],
            [round(max_x, 3), round(max_y, 3)],
            [round(min_x, 3), round(max_y, 3)],
        ],
        "image_points": [
            None,
            None,
            None,
            None,
        ],
    }


def load_homography(path: Path) -> Any:
    data = read_json(path)
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"OpenCV/numpy are required for scoring: {exc}") from exc

    if "matrix" in data:
        matrix = np.array(data["matrix"], dtype=np.float64)
        if matrix.shape != (3, 3):
            raise SystemExit("homography matrix must be 3x3")
        return matrix

    bed_points = data.get("bed_points")
    image_points = data.get("image_points")
    if not bed_points or not image_points or any(point is None for point in image_points):
        raise SystemExit("homography file needs either matrix or filled bed_points and image_points")

    source = np.array(bed_points, dtype=np.float64)
    dest = np.array(image_points, dtype=np.float64)
    if source.shape[0] < 4 or dest.shape[0] < 4:
        raise SystemExit("homography requires at least four bed_points and image_points")
    matrix, _ = cv2.findHomography(source, dest, method=0)
    if matrix is None:
        raise SystemExit("unable to compute homography")
    return matrix


def foreground_profile_score(profile: Any, center_index: int, expected_width_px: float) -> dict[str, float]:
    import numpy as np

    edge = max(2, int(len(profile) * 0.18))
    background = float(np.median(np.concatenate([profile[:edge], profile[-edge:]])))
    center_value = float(np.median(profile[max(0, center_index - 1): center_index + 2]))
    polarity = -1.0 if center_value < background else 1.0
    contrast = polarity * (profile - background)
    peak = float(np.max(contrast))
    if peak <= 3.0:
        return {"width_px": 0.0, "confidence": 0.0}

    threshold = peak * 0.42
    mask = contrast > threshold
    left = center_index
    while left > 0 and mask[left - 1]:
        left -= 1
    right = center_index
    while right < len(mask) - 1 and mask[right + 1]:
        right += 1
    width_px = float(max(0, right - left + 1))
    confidence = min(1.0, peak / 45.0) * min(1.0, width_px / max(1.0, expected_width_px * 0.45))
    return {"width_px": width_px, "confidence": float(confidence)}


def score_coupon(args: argparse.Namespace) -> dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except Exception as exc:
        raise SystemExit(f"OpenCV/numpy are required for scoring: {exc}") from exc

    manifest = read_json(Path(args.manifest))
    h_bed_to_img = load_homography(Path(args.homography))
    image = cv2.imread(str(args.image), cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Unable to read image: {args.image}")

    min_x, min_y, max_x, max_y = coupon_bounds(manifest, args.margin)
    width_px = max(1, int(math.ceil((max_x - min_x) * args.scale)))
    height_px = max(1, int(math.ceil((max_y - min_y) * args.scale)))
    rect_to_bed = np.array(
        [
            [1.0 / args.scale, 0.0, min_x],
            [0.0, 1.0 / args.scale, min_y],
            [0.0, 0.0, 1.0],
        ],
        dtype=np.float64,
    )
    rect_to_img = h_bed_to_img @ rect_to_bed
    img_to_rect = np.linalg.inv(rect_to_img)
    rectified = cv2.warpPerspective(image, img_to_rect, (width_px, height_px))
    gray = cv2.cvtColor(rectified, cv2.COLOR_BGR2GRAY).astype(np.float32)

    expected_width_px = max(1.0, float(manifest["line_width"]) * args.scale)
    scores: list[dict[str, Any]] = []
    for candidate in manifest["candidates"]:
        k = float(candidate["k"])
        x0, y0 = candidate["line_start"]
        x1, y1 = candidate["line_end"]
        _, y2 = candidate["corner_end"]
        y_px = int(round((y0 - min_y) * args.scale))
        x_start = int(round((x0 - min_x + args.sample_inset) * args.scale))
        x_end = int(round((x1 - min_x - args.sample_inset) * args.scale))
        half_band = max(4, int(round(args.band_mm * args.scale)))
        y_lo = max(0, y_px - half_band)
        y_hi = min(gray.shape[0], y_px + half_band + 1)
        widths_mm: list[float] = []
        confidences: list[float] = []

        for x_px in range(max(0, x_start), min(gray.shape[1], x_end), max(1, int(args.sample_step_mm * args.scale))):
            profile = gray[y_lo:y_hi, x_px]
            if profile.size < 5:
                continue
            measured = foreground_profile_score(profile, y_px - y_lo, expected_width_px)
            if measured["confidence"] > 0:
                widths_mm.append(measured["width_px"] / args.scale)
                confidences.append(measured["confidence"])

        mean_width = float(np.mean(widths_mm)) if widths_mm else 0.0
        width_cv = float(np.std(widths_mm) / mean_width) if mean_width > 0 else 1.0
        confidence = float(np.mean(confidences)) if confidences else 0.0
        width_error = abs(mean_width - float(manifest["line_width"])) / max(0.01, float(manifest["line_width"]))

        corner_x_px = int(round((x1 - min_x) * args.scale))
        corner_y_px = int(round((y1 - min_y) * args.scale))
        corner_leg_px = max(4, int(round(min(args.corner_score_mm, y2 - y1) * args.scale)))
        corner_pad = max(3, int(round(args.band_mm * args.scale)))
        x_lo = max(0, corner_x_px - corner_leg_px - corner_pad)
        x_hi = min(gray.shape[1], corner_x_px + corner_pad + 1)
        y_corner_lo = max(0, corner_y_px - corner_pad)
        y_corner_hi = min(gray.shape[0], corner_y_px + corner_leg_px + corner_pad + 1)
        corner = gray[y_corner_lo:y_corner_hi, x_lo:x_hi]
        corner_score = 0.5
        if corner.size:
            background = float(np.median(corner))
            polarity = -1.0 if np.mean(corner) < background else 1.0
            foreground = polarity * (corner - background)
            peak = float(np.max(foreground)) if foreground.size else 0.0
            if peak > 3:
                mask = foreground > peak * 0.42
                measured_area = float(np.count_nonzero(mask))
                expected_area = max(1.0, (corner_leg_px * expected_width_px * 2.0) - expected_width_px**2)
                area_ratio = measured_area / expected_area
                corner_score = abs(math.log(max(0.05, min(20.0, area_ratio))))

        total = (1.8 * width_cv) + (1.2 * width_error) + (0.8 * corner_score) + (1.0 - confidence)
        scores.append(
            {
                "index": candidate["index"],
                "k": k,
                "score": round(float(total), 5),
                "mean_width_mm": round(mean_width, 4),
                "width_cv": round(width_cv, 4),
                "corner_score": round(float(corner_score), 4),
                "confidence": round(confidence, 4),
            }
        )

    best = min(scores, key=lambda item: item["score"]) if scores else None
    result = {
        "kind": "tinman_auto_pa_score",
        "version": 1,
        "image": str(args.image),
        "manifest": str(args.manifest),
        "homography": str(args.homography),
        "best": best,
        "scores": scores,
        "note": "Experimental CV scorer; validate against known-good coupons before enabling unattended live updates.",
    }

    if args.debug_image:
        debug = rectified.copy()
        for item, candidate in zip(scores, manifest["candidates"]):
            x0, y0 = candidate["line_start"]
            x1, y1 = candidate["line_end"]
            x2, y2 = candidate["corner_end"]
            p0 = (int(round((x0 - min_x) * args.scale)), int(round((y0 - min_y) * args.scale)))
            p1 = (int(round((x1 - min_x) * args.scale)), int(round((y1 - min_y) * args.scale)))
            p2 = (int(round((x2 - min_x) * args.scale)), int(round((y2 - min_y) * args.scale)))
            color = (0, 220, 0) if best and item["index"] == best["index"] else (0, 160, 255)
            cv2.line(debug, p0, p1, color, 2)
            cv2.line(debug, p1, p2, color, 2)
            cv2.putText(debug, f"K{item['k']:.3f} S{item['score']:.2f}", (p0[0], max(12, p0[1] - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.38, color, 1, cv2.LINE_AA)
        out = Path(args.debug_image)
        out.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out), debug)
        result["debug_image"] = str(out)

    return result


def numeric_field(row: dict[str, Any], keys: tuple[str, ...]) -> Optional[float]:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def load_beacon_measurements(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".csv":
        with path.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
    else:
        data = read_json(path)
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("measurements") or data.get("points") or data.get("samples") or []
        else:
            rows = []
    records: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        z = numeric_field(
            row,
            (
                "measured_z",
                "contact_z",
                "trigger_z",
                "z",
                "height_z",
                "sample_z",
            ),
        )
        role = row.get("role")
        index = row.get("candidate_index", row.get("index"))
        if z is None or role is None or index is None:
            continue
        try:
            candidate_index = int(index)
        except (TypeError, ValueError):
            continue
        records.append(
            {
                "candidate_index": candidate_index,
                "k": numeric_field(row, ("k", "pa", "pressure_advance")),
                "flow_mm3_s": numeric_field(row, ("flow_mm3_s", "flow", "volumetric_flow", "mm3_s")),
                "role": str(role),
                "z": float(z),
                "quality": numeric_field(row, ("quality", "confidence", "weight")) or 1.0,
            }
        )
    return records


def average(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def beacon_measurements_by_candidate(records: list[dict[str, Any]]) -> dict[int, dict[str, list[float]]]:
    grouped: dict[int, dict[str, list[float]]] = {}
    for record in records:
        idx = int(record["candidate_index"])
        role = str(record["role"])
        grouped.setdefault(idx, {}).setdefault(role, []).append(float(record["z"]))
    return grouped


def maybe_auto_sign(scores: list[dict[str, Any]], requested_sign: float, auto_sign: bool) -> float:
    if not auto_sign:
        return requested_sign
    line_heights = [
        float(item["raw_heights"].get("line_mid_height", 0.0))
        for item in scores
        if item.get("raw_heights") and item["raw_heights"].get("line_mid_height") is not None
    ]
    if not line_heights:
        return requested_sign
    line_heights = sorted(line_heights)
    median = line_heights[len(line_heights) // 2]
    return -requested_sign if median < 0 else requested_sign


def beacon_score_from_records(
    manifest: dict[str, Any],
    records: list[dict[str, Any]],
    *,
    height_scale: float,
    target_height: float,
    invert_z: bool,
    auto_sign: bool,
    min_complete_roles: int,
) -> dict[str, Any]:
    grouped = beacon_measurements_by_candidate(records)
    sign = -1.0 if invert_z else 1.0
    required_roles = [
        "line_mid_height",
        "pre_corner_blob",
        "corner_apex",
        "post_corner_gap",
        "local_plate_reference",
    ]
    pre_scores: list[dict[str, Any]] = []
    for candidate in manifest.get("candidates", []):
        idx = int(candidate["index"])
        role_values = {
            role: average(grouped.get(idx, {}).get(role, []))
            for role in required_roles
        }
        ref = role_values.get("local_plate_reference")
        raw_heights: dict[str, Optional[float]] = {}
        if ref is not None:
            for role in required_roles:
                value = role_values.get(role)
                raw_heights[role] = None if value is None else (value - ref)
        pre_scores.append(
            {
                "index": idx,
                "k": float(candidate["k"]),
                "role_z": role_values,
                "raw_heights": raw_heights,
            }
        )
    sign = maybe_auto_sign(pre_scores, sign, auto_sign)

    scores: list[dict[str, Any]] = []
    for item in pre_scores:
        heights = {
            role: None if value is None else float(value) * sign
            for role, value in item["raw_heights"].items()
        }
        complete_roles = sum(1 for value in heights.values() if value is not None)
        missing = [role for role, value in heights.items() if value is None]
        line = heights.get("line_mid_height")
        pre = heights.get("pre_corner_blob")
        corner = heights.get("corner_apex")
        post = heights.get("post_corner_gap")
        if complete_roles < min_complete_roles or line is None:
            scores.append(
                {
                    "index": item["index"],
                    "k": round(float(item["k"]), 5),
                    "score": 999.0,
                    "trusted": False,
                    "missing_roles": missing,
                    "heights_mm": {k: None if v is None else round(float(v), 5) for k, v in heights.items()},
                }
            )
            continue

        pre_excess = max(0.0, (pre if pre is not None else line) - line)
        corner_excess = max(0.0, (corner if corner is not None else line) - line)
        post_deficit = max(0.0, line - (post if post is not None else line))
        post_excess = max(0.0, (post if post is not None else line) - line)
        height_error = abs(line - target_height)
        available_penalty = (len(missing) / len(required_roles)) * 0.75
        score = (
            (1.20 * pre_excess / height_scale)
            + (1.80 * corner_excess / height_scale)
            + (1.65 * post_deficit / height_scale)
            + (0.35 * post_excess / height_scale)
            + (0.25 * height_error / height_scale)
            + available_penalty
        )
        scores.append(
            {
                "index": item["index"],
                "k": round(float(item["k"]), 5),
                "score": round(float(score), 5),
                "trusted": complete_roles >= len(required_roles),
                "missing_roles": missing,
                "heights_mm": {
                    key: None if value is None else round(float(value), 5)
                    for key, value in heights.items()
                },
                "features_mm": {
                    "pre_corner_excess": round(float(pre_excess), 5),
                    "corner_excess": round(float(corner_excess), 5),
                    "post_corner_deficit": round(float(post_deficit), 5),
                    "post_corner_excess": round(float(post_excess), 5),
                    "line_height_error": round(float(height_error), 5),
                },
            }
        )

    ordered = sorted(scores, key=lambda row: float(row["score"]))
    best = ordered[0] if ordered else None
    second = ordered[1] if len(ordered) > 1 else None
    confidence = 0.0
    if best and second and float(best["score"]) < 999.0:
        separation = max(0.0, float(second["score"]) - float(best["score"]))
        confidence = min(1.0, separation / max(0.15, float(second["score"])))
        if not best.get("trusted", False):
            confidence *= 0.5
    return {
        "height_scale_mm": round(float(height_scale), 5),
        "target_height_mm": round(float(target_height), 5),
        "sign": sign,
        "best": best,
        "scores": scores,
        "confidence": round(float(confidence), 4),
    }


def normalised_score_map(rows: list[dict[str, Any]]) -> dict[int, float]:
    valid = [float(row["score"]) for row in rows if float(row.get("score", 999.0)) < 999.0]
    if not valid:
        return {}
    lo = min(valid)
    hi = max(valid)
    span = max(1e-9, hi - lo)
    result: dict[int, float] = {}
    for row in rows:
        score = float(row.get("score", 999.0))
        if score >= 999.0:
            result[int(row["index"])] = 1.0
        else:
            result[int(row["index"])] = max(0.0, min(1.0, (score - lo) / span))
    return result


def load_camera_score(path: Optional[str]) -> dict[str, Any]:
    if not path:
        return {}
    data = read_json(Path(path))
    return data if isinstance(data, dict) else {}


def fuse_camera_beacon_scores(
    manifest: dict[str, Any],
    beacon: dict[str, Any],
    camera_score: dict[str, Any],
    *,
    camera_weight: float,
    beacon_weight: float,
) -> dict[str, Any]:
    beacon_norm = normalised_score_map(beacon.get("scores", []))
    camera_rows = camera_score.get("scores") if isinstance(camera_score, dict) else None
    camera_norm = normalised_score_map(camera_rows or [])
    fused_rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    if not camera_norm:
        warnings.append("No camera score was supplied; fused result is Beacon-only.")
        camera_weight = 0.0
    if not beacon_norm:
        warnings.append("No Beacon score was available.")
        beacon_weight = 0.0
    total_weight = camera_weight + beacon_weight
    if total_weight <= 0:
        total_weight = 1.0

    beacon_by_index = {int(row["index"]): row for row in beacon.get("scores", [])}
    camera_by_index = {
        int(row["index"]): row for row in (camera_rows or [])
        if isinstance(row, dict) and "index" in row
    }
    for candidate in manifest.get("candidates", []):
        idx = int(candidate["index"])
        b = beacon_norm.get(idx, 1.0)
        c = camera_norm.get(idx, 1.0)
        score = ((beacon_weight * b) + (camera_weight * c)) / total_weight
        fused_rows.append(
            {
                "index": idx,
                "k": round(float(candidate["k"]), 5),
                "score": round(float(score), 5),
                "beacon_norm": round(float(b), 5),
                "camera_norm": round(float(c), 5),
                "beacon_score": beacon_by_index.get(idx, {}).get("score"),
                "camera_score": camera_by_index.get(idx, {}).get("score"),
            }
        )

    ordered = sorted(fused_rows, key=lambda row: float(row["score"]))
    selected = ordered[0] if ordered else None
    confidence = 0.0
    if selected and len(ordered) > 1:
        gap = max(0.0, float(ordered[1]["score"]) - float(selected["score"]))
        confidence = min(1.0, gap / 0.25)
    if beacon.get("confidence") is not None:
        confidence = max(confidence, min(1.0, float(beacon["confidence"]) * 0.8))
    return {
        "selected": selected,
        "scores": fused_rows,
        "confidence": round(float(confidence), 4),
        "weights": {
            "camera": round(float(camera_weight), 3),
            "beacon": round(float(beacon_weight), 3),
        },
        "warnings": warnings,
    }


def beacon_score_coupon(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(Path(args.manifest))
    records = load_beacon_measurements(Path(args.measurements))
    if not records:
        raise SystemExit("No Beacon measurements found. Expected JSON/CSV rows with candidate_index, role, and measured_z/contact_z/z.")
    layer_height = float(manifest.get("layer_height", 0.24))
    height_scale = args.height_scale if args.height_scale > 0 else max(0.03, layer_height * 0.20)
    target_height = args.target_height if args.target_height > 0 else layer_height
    beacon = beacon_score_from_records(
        manifest,
        records,
        height_scale=height_scale,
        target_height=target_height,
        invert_z=args.invert_z,
        auto_sign=not args.no_auto_sign,
        min_complete_roles=args.min_complete_roles,
    )
    camera_score = load_camera_score(args.camera_score)
    fusion = fuse_camera_beacon_scores(
        manifest,
        beacon,
        camera_score,
        camera_weight=args.camera_weight,
        beacon_weight=args.beacon_weight,
    )
    selected = fusion.get("selected") or beacon.get("best")
    warnings = list(fusion.get("warnings", []))
    if beacon.get("confidence", 0.0) < args.min_confidence:
        warnings.append("Beacon confidence is below --min-confidence.")
    trusted = bool(selected) and not warnings and float(beacon.get("confidence", 0.0)) >= args.min_confidence
    result: dict[str, Any] = {
        "kind": "tinman_beacon_auto_pa_score",
        "version": 1,
        "machine_label": args.machine_label,
        "adapter": args.adapter,
        "manifest": args.manifest,
        "measurements": args.measurements,
        "camera_score": args.camera_score or "",
        "beacon": beacon,
        "fusion": fusion,
        "selected_k": None if not selected else selected.get("k"),
        "apply_command": None if not selected else pa_command(args.flavor, float(selected["k"])),
        "trusted_for_supervised_apply": trusted,
        "warnings": warnings,
        "note": "Experimental Beacon/CV fusion; validate with supervised coupons before live PA updates.",
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def beacon_simulate_coupon(args: argparse.Namespace) -> dict[str, Any]:
    import random

    manifest = read_json(Path(args.manifest))
    rng = random.Random(args.seed)
    layer_height = float(manifest.get("layer_height", 0.24))
    line_height = args.line_height if args.line_height > 0 else layer_height
    measurements: list[dict[str, Any]] = []
    for point in qidi_beacon_probe_points(manifest, sample_offset=args.sample_offset):
        k = float(point["k"])
        low_delta = max(0.0, args.true_k - k)
        high_delta = max(0.0, k - args.true_k)
        role = point["role"]
        height = 0.0
        if role == "line_mid_height":
            height = line_height + 0.18 * args.low_pa_gain * low_delta + 0.12 * args.high_pa_gain * high_delta
        elif role == "pre_corner_blob":
            height = line_height + args.low_pa_gain * low_delta + 0.12 * args.high_pa_gain * high_delta
        elif role == "corner_apex":
            height = line_height + args.corner_gain * low_delta + 0.18 * args.high_pa_gain * high_delta
        elif role == "post_corner_gap":
            height = line_height - args.high_pa_gain * high_delta + 0.12 * args.low_pa_gain * low_delta
        elif role == "local_plate_reference":
            height = 0.0
        z = args.plate_z + height + rng.gauss(0.0, args.noise_mm)
        measurements.append(
            {
                "candidate_index": point["candidate_index"],
                "k": point["k"],
                "role": role,
                "xy": point["xy"],
                "measured_z": round(float(z), 6),
                "simulated_height_mm": round(float(height), 6),
            }
        )
    result = {
        "kind": "tinman_beacon_synthetic_measurements",
        "version": 1,
        "manifest": args.manifest,
        "true_k": args.true_k,
        "noise_mm": args.noise_mm,
        "measurements": measurements,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return {"output": str(output), "measurements": len(measurements), "true_k": args.true_k}


def linear_float_candidates(start: float, end: float, steps: int, digits: int = 4) -> list[float]:
    if steps < 2:
        raise SystemExit("--steps must be at least 2")
    if end <= start:
        raise SystemExit("candidate end must be greater than start")
    return [round(start + (end - start) * i / (steps - 1), digits) for i in range(steps)]


def maxflow_bounds(manifest: dict[str, Any], margin: float) -> tuple[float, float, float, float]:
    points: list[list[float]] = []
    for candidate in manifest["candidates"]:
        points.extend([candidate["line_start"], candidate["line_end"]])
        if "reference_point" in candidate:
            points.append(candidate["reference_point"])
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs) - margin, min(ys) - margin, max(xs) + margin, max(ys) + margin


def maxflow_homography_template(manifest_path: Path, margin: float) -> dict[str, Any]:
    manifest = read_json(manifest_path)
    min_x, min_y, max_x, max_y = maxflow_bounds(manifest, margin)
    return {
        "kind": "tinman_maxflow_homography",
        "version": 1,
        "instructions": "Fill image_points with matching pixel coordinates from the snapshot: top-left, top-right, bottom-right, bottom-left of the bed_points box.",
        "bed_points": [
            [round(min_x, 3), round(min_y, 3)],
            [round(max_x, 3), round(min_y, 3)],
            [round(max_x, 3), round(max_y, 3)],
            [round(min_x, 3), round(max_y, 3)],
        ],
        "image_points": [None, None, None, None],
    }


def maxflow_candidate_geometry(args: argparse.Namespace, index: int, candidate_count: int) -> dict[str, Any]:
    layout = getattr(args, "layout", "row")
    if layout == "row":
        y = args.y + index * args.spacing
        x0 = args.x
        x1 = args.x + args.length
        return {
            "line_start": [x0, y],
            "line_end": [x1, y],
            "reference_point": [x1 + args.reference_offset, y],
        }

    if layout in ("front-edge", "rear-edge"):
        if candidate_count < 1:
            raise SystemExit(f"{layout} max-flow layout needs at least one candidate")
        if args.edge_band_width <= 0:
            raise SystemExit("--edge-band-width must be positive")
        if args.reference_offset <= 0:
            raise SystemExit(f"--reference-offset must be positive for the {layout} max-flow layout")
        if args.y + args.reference_offset > args.edge_band_width:
            raise SystemExit("--y + --reference-offset must remain inside --edge-band-width")

        total_gap = args.spacing * max(0, candidate_count - 1)
        available = args.bed_x - (2.0 * args.x) - total_gap
        length = args.length if args.length > 0 else available / candidate_count
        if length <= 0:
            raise SystemExit("front-edge max-flow layout has no usable X length")
        used = candidate_count * length + total_gap
        if args.x + used > args.bed_x:
            raise SystemExit(
                "front-edge max-flow layout exceeds bed X; reduce --steps/--length/--spacing or --x"
            )
        x0 = args.x + index * (length + args.spacing)
        x1 = x0 + length
        y = args.y if layout == "front-edge" else args.bed_y - args.y
        reference_y = y + args.reference_offset if layout == "front-edge" else y - args.reference_offset
        return {
            "line_start": [x0, y],
            "line_end": [x1, y],
            "reference_point": [(x0 + x1) / 2.0, reference_y],
            "auto_length": length,
        }

    raise SystemExit(f"unsupported max-flow coupon layout: {layout}")


def validate_maxflow_coupon_layout(args: argparse.Namespace, candidate_count: int) -> None:
    layout = getattr(args, "layout", "row")
    if layout == "row":
        if args.spacing <= args.line_width * 5.0:
            raise SystemExit("--spacing is too small for Beacon/camera separation")
        return

    if layout in ("front-edge", "rear-edge"):
        for i in range(candidate_count):
            geometry = maxflow_candidate_geometry(args, i, candidate_count)
            for key in ("line_start", "line_end", "reference_point"):
                x, y = geometry[key]
                validate_edge_band_point(
                    float(x),
                    float(y),
                    args.bed_x,
                    args.bed_y,
                    args.edge_band_width,
                    f"max-flow candidate {i} {key}",
                )
        return

    raise SystemExit(f"unsupported max-flow coupon layout: {layout}")


def maxflow_beacon_probe_points(manifest: dict[str, Any], sample_inset: float = 5.0) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for candidate in manifest["candidates"]:
        idx = int(candidate["index"])
        flow = float(candidate["flow_mm3_s"])
        x0, y0 = candidate["line_start"]
        x1, y1 = candidate["line_end"]
        dx = float(x1) - float(x0)
        dy = float(y1) - float(y0)
        line_length = math.hypot(dx, dy)
        if line_length <= 0:
            continue
        ux = dx / line_length
        uy = dy / line_length
        inset = min(sample_inset, line_length * 0.30)
        x_start = float(x0) + ux * inset
        y_start = float(y0) + uy * inset
        x_mid = (float(x0) + float(x1)) / 2.0
        y_mid = (float(y0) + float(y1)) / 2.0
        x_end = float(x1) - ux * inset
        y_end = float(y1) - uy * inset
        ref = candidate.get("reference_point", [x_mid, y_mid + sample_inset])
        points.extend(
            [
                {
                    "candidate_index": idx,
                    "flow_mm3_s": flow,
                    "role": "line_start_height",
                    "xy": [round(x_start, 3), round(y_start, 3)],
                    "why": "Early bead height at this volumetric flow.",
                },
                {
                    "candidate_index": idx,
                    "flow_mm3_s": flow,
                    "role": "line_mid_height",
                    "xy": [round(x_mid, 3), round(y_mid, 3)],
                    "why": "Steady-state bead height at this volumetric flow.",
                },
                {
                    "candidate_index": idx,
                    "flow_mm3_s": flow,
                    "role": "line_end_height",
                    "xy": [round(x_end, 3), round(y_end, 3)],
                    "why": "End-of-line bead height after sustained flow demand.",
                },
                {
                    "candidate_index": idx,
                    "flow_mm3_s": flow,
                    "role": "local_plate_reference",
                    "xy": [round(float(ref[0]), 3), round(float(ref[1]), 3)],
                    "why": "Nearby bare-plate reference for local Z/plate slope correction.",
                },
            ]
        )
    return points


def maxflow_beacon_plan_from_manifest(
    manifest: dict[str, Any],
    safe_z: float,
    travel_speed: float,
    sample_inset: float,
) -> dict[str, Any]:
    points = maxflow_beacon_probe_points(manifest, sample_inset=sample_inset)
    commands = [
        "; TINMAN_MAXFLOW_BEACON_PROBE_PLAN_DRY_RUN",
        "; Verify Beacon contact probe behavior on an idle printer before executing any probing.",
        "; Install/review outputs/auto_pa_v0/tinman_beacon_pa_macros_review.cfg before converting these calls to live G-code.",
        "G90",
        f"G1 Z{safe_z:.3f} F900",
    ]
    macro_calls: list[str] = []
    for point in points:
        x, y = point["xy"]
        commands.append(
            f"; candidate={point['candidate_index']} flow={point['flow_mm3_s']:.3f} role={point['role']}"
        )
        commands.append(f"G1 X{x:.3f} Y{y:.3f} F{int(travel_speed * 60)}")
        call = (
            "TINMAN_BEACON_PA_SAMPLE "
            f"CANDIDATE={point['candidate_index']} "
            f"FLOW={point['flow_mm3_s']:.3f} "
            f"ROLE={point['role']} "
            f"X{x:.3f} Y{y:.3f}"
        )
        macro_calls.append(call)
        commands.append(f"; {call}")
        commands.append("; dry-run only: reviewed machine macro decides PROBE vs BEACON_POKE")
    return {
        "kind": "tinman_maxflow_beacon_probe_plan",
        "version": 1,
        "source_manifest_kind": manifest.get("kind", ""),
        "safe_z": safe_z,
        "sample_inset": sample_inset,
        "points": points,
        "macro_calls": macro_calls,
        "measurement_schema": {
            "required_fields": ["candidate_index", "role"],
            "z_fields": ["measured_z", "contact_z", "trigger_z", "z"],
            "accepted_formats": ["json", "csv"],
            "parser": "auto_pa.py maxflow-score-beacon --measurements <file>",
        },
        "dry_run_commands": commands,
        "notes": [
            "This is a planning artifact, not an execution file.",
            "The printed flow ladder should be cool enough not to deform under Beacon contact.",
            "Use a safety factor before applying a max volumetric speed to slicer/profile limits.",
        ],
    }


def maxflow_generate_coupon(args: argparse.Namespace) -> dict[str, Any]:
    flows = linear_float_candidates(args.flow_start, args.flow_end, args.steps, digits=3)
    validate_maxflow_coupon_layout(args, len(flows))
    e_per_mm = extrusion_per_mm(args.line_width, args.layer_height, args.filament_diameter, args.flow_ratio)
    cross_section = args.line_width * args.layer_height * args.flow_ratio
    if cross_section <= 0:
        raise SystemExit("line_width, layer_height, and flow_ratio must define a positive cross-section")

    manifest: dict[str, Any] = {
        "kind": "tinman_maxflow_ladder_coupon",
        "version": 1,
        "machine_label": args.machine_label,
        "adapter": args.adapter,
        "host": args.host,
        "tool": args.tool,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "origin": [args.x, args.y],
        "layout": args.layout,
        "bed_size": [args.bed_x, args.bed_y],
        "edge_band_width": args.edge_band_width if args.layout != "row" else None,
        "line_width": args.line_width,
        "layer_height": args.layer_height,
        "filament_diameter": args.filament_diameter,
        "flow_ratio": args.flow_ratio,
        "cross_section_mm2": round(cross_section, 5),
        "travel_speed_mm_s": args.travel_speed,
        "accel": args.accel,
        "pressure_advance_k": None if args.k < 0 else round(args.k, 5),
        "pa_command_flavor": args.flavor,
        "candidate_strategy": {
            "flow_start": args.flow_start,
            "flow_end": args.flow_end,
            "steps": args.steps,
            "safety_factor": args.safety_factor,
        },
        "source_reference": {
            "method": "CNC Kitchen-inspired increasing-flow extrusion benchmark, adapted for printed-line Beacon/camera scoring instead of weighing blobs.",
            "cnc_kitchen_blog": "https://www.cnckitchen.com/blog/extrusion-system-benchmark-tool-for-fast-prints",
            "cnc_kitchen_repo": "https://github.com/CNCKitchen/ExtrusionSystemBenchmark",
        },
        "candidates": [],
    }

    g: list[str] = []
    g.append("; TINMAN_MAXFLOW_LADDER_START")
    g.append("; CNC Kitchen-inspired flow ladder adapted for Beacon/camera scoring")
    g.append(f"; flows_mm3_s={','.join(f'{flow:.3f}' for flow in flows)}")
    g.append("SAVE_GCODE_STATE NAME=TINMAN_MAXFLOW_LADDER")
    g.append("G90")
    g.append("M83")
    if args.tool:
        g.append(args.tool)
    if args.pre_gcode:
        for command in args.pre_gcode:
            g.append(command)
    if args.k >= 0:
        g.append(pa_command(args.flavor, args.k))
    g.append(f"M204 S{int(args.accel)}")
    g.append(f"G1 Z{args.z:.3f} F900")

    for i, flow in enumerate(flows):
        geometry = maxflow_candidate_geometry(args, i, len(flows))
        x0, y0 = geometry["line_start"]
        x1, y1 = geometry["line_end"]
        line_length = math.hypot(float(x1) - float(x0), float(y1) - float(y0))
        speed = flow / cross_section
        if speed > args.max_speed:
            speed = args.max_speed
        e = line_length * e_per_mm
        g.append(f"; TINMAN_MAXFLOW_CANDIDATE index={i} flow={flow:.3f} speed={speed:.3f}")
        g.append(f"G1 X{x0:.3f} Y{y0:.3f} F{int(args.travel_speed * 60)}")
        g.append(f"G1 X{x1:.3f} Y{y1:.3f} E{e:.5f} F{int(speed * 60)}")
        g.append(f"G1 E-{args.retract:.5f} F1800")
        g.append(f"G1 Z{args.z + args.z_hop:.3f} F900")
        g.append(f"G1 Z{args.z:.3f} F900")
        g.append(f"G1 E{args.retract:.5f} F1800")
        manifest["candidates"].append(
            {
                "index": i,
                "flow_mm3_s": round(flow, 3),
                "speed_mm_s": round(speed, 3),
                "line_length_mm": round(line_length, 3),
                "line_start": [round(float(x0), 3), round(float(y0), 3)],
                "line_end": [round(float(x1), 3), round(float(y1), 3)],
                "reference_point": [
                    round(float(geometry["reference_point"][0]), 3),
                    round(float(geometry["reference_point"][1]), 3),
                ],
            }
        )

    g.append("M400")
    g.append("RESTORE_GCODE_STATE NAME=TINMAN_MAXFLOW_LADDER MOVE=0")
    g.append("; TINMAN_MAXFLOW_LADDER_END")
    g.append("")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(g))
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")

    result: dict[str, Any] = {
        "kind": "tinman_maxflow_ladder_result",
        "version": 1,
        "machine_label": args.machine_label,
        "host": args.host,
        "tool": args.tool,
        "output": str(output),
        "manifest": str(manifest_path),
        "flows_mm3_s": flows,
        "estimated_print_seconds": round(
            sum(float(c.get("line_length_mm", args.length)) / max(1.0, c["speed_mm_s"]) + 1.0 for c in manifest["candidates"]),
            1,
        ),
    }

    if args.homography_template:
        template_path = Path(args.homography_template)
        template = maxflow_homography_template(manifest_path, args.homography_margin)
        template_path.parent.mkdir(parents=True, exist_ok=True)
        template_path.write_text(json.dumps(template, indent=2) + "\n")
        result["homography_template"] = str(template_path)
    if args.beacon_plan:
        plan_path = Path(args.beacon_plan)
        plan = maxflow_beacon_plan_from_manifest(
            manifest,
            safe_z=args.beacon_safe_z,
            travel_speed=args.travel_speed,
            sample_inset=args.beacon_sample_inset,
        )
        plan["machine_label"] = args.machine_label
        plan["adapter"] = args.adapter
        plan["tool"] = args.tool
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        result["beacon_plan"] = str(plan_path)
    return result


def maxflow_simulate_beacon(args: argparse.Namespace) -> dict[str, Any]:
    import random

    manifest = read_json(Path(args.manifest))
    rng = random.Random(args.seed)
    layer_height = float(manifest.get("layer_height", 0.24))
    measurements: list[dict[str, Any]] = []
    for point in maxflow_beacon_probe_points(manifest, sample_inset=args.sample_inset):
        flow = float(point["flow_mm3_s"])
        role = point["role"]
        overload = max(0.0, flow - args.true_max_flow) / max(0.001, args.true_max_flow)
        ratio = max(args.min_height_ratio, 1.0 - args.drop_gain * overload)
        if role == "line_end_height":
            ratio = max(args.min_height_ratio, ratio - 0.16 * overload)
        elif role == "line_start_height":
            ratio = min(1.03, ratio + 0.05)
        elif role == "local_plate_reference":
            ratio = 0.0
        height = layer_height * ratio
        z = args.plate_z + height + rng.gauss(0.0, args.noise_mm)
        measurements.append(
            {
                "candidate_index": point["candidate_index"],
                "flow_mm3_s": flow,
                "role": role,
                "xy": point["xy"],
                "measured_z": round(float(z), 6),
                "simulated_height_mm": round(float(height), 6),
            }
        )
    result = {
        "kind": "tinman_maxflow_synthetic_beacon_measurements",
        "version": 1,
        "manifest": args.manifest,
        "true_max_flow_mm3_s": args.true_max_flow,
        "noise_mm": args.noise_mm,
        "measurements": measurements,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    return {"output": str(output), "measurements": len(measurements), "true_max_flow": args.true_max_flow}


def maxflow_score_beacon(args: argparse.Namespace) -> dict[str, Any]:
    manifest = read_json(Path(args.manifest))
    records = load_beacon_measurements(Path(args.measurements))
    if not records:
        raise SystemExit("No Beacon measurements found. Expected JSON/CSV rows with candidate_index, role, and measured_z/contact_z/z.")
    grouped = beacon_measurements_by_candidate(records)
    layer_height = float(manifest.get("layer_height", 0.24))
    rows: list[dict[str, Any]] = []
    for candidate in manifest.get("candidates", []):
        idx = int(candidate["index"])
        values = {
            role: average(grouped.get(idx, {}).get(role, []))
            for role in ("line_start_height", "line_mid_height", "line_end_height", "local_plate_reference")
        }
        ref = values.get("local_plate_reference")
        heights: dict[str, Optional[float]] = {}
        if ref is not None:
            for role in ("line_start_height", "line_mid_height", "line_end_height"):
                value = values.get(role)
                heights[role] = None if value is None else float(value) - float(ref)
        present = [float(v) for v in heights.values() if v is not None]
        if not present:
            rows.append(
                {
                    "index": idx,
                    "flow_mm3_s": float(candidate["flow_mm3_s"]),
                    "status": "missing",
                    "pass": False,
                    "height_ratio": 0.0,
                    "height_cv": 1.0,
                    "heights_mm": heights,
                }
            )
            continue
        avg_height = sum(present) / len(present)
        min_height = min(present)
        variance = sum((value - avg_height) ** 2 for value in present) / len(present)
        cv = math.sqrt(variance) / max(0.001, avg_height)
        height_ratio = avg_height / max(0.001, layer_height)
        min_ratio = min_height / max(0.001, layer_height)
        passed = (
            len(present) >= args.min_points
            and height_ratio >= args.min_height_ratio
            and min_ratio >= args.min_point_ratio
            and cv <= args.max_height_cv
        )
        rows.append(
            {
                "index": idx,
                "flow_mm3_s": round(float(candidate["flow_mm3_s"]), 3),
                "speed_mm_s": candidate.get("speed_mm_s"),
                "status": "pass" if passed else "fail",
                "pass": bool(passed),
                "height_ratio": round(float(height_ratio), 4),
                "min_point_ratio": round(float(min_ratio), 4),
                "height_cv": round(float(cv), 4),
                "heights_mm": {
                    key: None if value is None else round(float(value), 5)
                    for key, value in heights.items()
                },
            }
        )

    passing = [row for row in rows if row["pass"]]
    selected = max(passing, key=lambda row: float(row["flow_mm3_s"])) if passing else None
    first_fail = next((row for row in rows if not row["pass"]), None)
    safe_max = None if not selected else round(float(selected["flow_mm3_s"]) * args.safety_factor, 3)
    confidence = 0.0
    warnings: list[str] = []
    if not selected:
        warnings.append("No passing max-flow candidate was found; fall back to cached slicer limit.")
    else:
        if selected == rows[-1]:
            warnings.append("Highest candidate still passed; true max flow is above this test range.")
            confidence = 0.55
        elif first_fail:
            gap = float(first_fail["flow_mm3_s"]) - float(selected["flow_mm3_s"])
            confidence = max(0.35, min(1.0, gap / max(0.5, float(selected["flow_mm3_s"]) * 0.20)))
    result = {
        "kind": "tinman_maxflow_beacon_score",
        "version": 1,
        "machine_label": args.machine_label,
        "adapter": args.adapter,
        "manifest": args.manifest,
        "measurements": args.measurements,
        "selected_flow_mm3_s": None if not selected else selected["flow_mm3_s"],
        "safe_max_flow_mm3_s": safe_max,
        "safety_factor": args.safety_factor,
        "confidence": round(float(confidence), 4),
        "rows": rows,
        "warnings": warnings,
        "note": "Experimental max-flow Beacon scorer. Use the safety-factor result for slicer/profile limits, not the raw failure edge.",
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def split_gcode_comment(line: str) -> tuple[str, str]:
    if ";" not in line:
        return line.rstrip("\n"), ""
    code, comment = line.rstrip("\n").split(";", 1)
    return code.rstrip(), ";" + comment


def parse_gcode_tokens(code: str) -> tuple[str, dict[str, float], list[str]]:
    tokens = code.strip().split()
    if not tokens:
        return "", {}, []
    command = tokens[0].upper()
    params: dict[str, float] = {}
    for token in tokens[1:]:
        if len(token) < 2:
            continue
        key = token[0].upper()
        if key not in {"X", "Y", "Z", "E", "F", "S", "P"}:
            continue
        try:
            params[key] = float(token[1:])
        except ValueError:
            continue
    return command, params, tokens


def format_feedrate(value: float) -> str:
    if abs(value - round(value)) < 0.01:
        return f"F{int(round(value))}"
    return f"F{value:.2f}"


def rewrite_feedrate(code: str, new_feed: float) -> str:
    tokens = code.strip().split()
    if not tokens:
        return code
    replacement = format_feedrate(new_feed)
    replaced = False
    for i, token in enumerate(tokens):
        if len(token) >= 2 and token[0].upper() == "F":
            tokens[i] = replacement
            replaced = True
            break
    if not replaced:
        tokens.append(replacement)
    leading = code[: len(code) - len(code.lstrip())]
    return leading + " ".join(tokens)


def normalise_feature_name(raw: str) -> str:
    text = raw.strip().lower()
    text = text.replace("_", " ").replace("-", " ")
    text = re.sub(r"\s+", " ", text)
    aliases = {
        "inner wall": "inner_wall",
        "inner walls": "inner_wall",
        "inner perimeter": "inner_wall",
        "inner perimeters": "inner_wall",
        "internal perimeter": "inner_wall",
        "internal perimeters": "inner_wall",
        "outer wall": "outer_wall",
        "outer walls": "outer_wall",
        "external perimeter": "outer_wall",
        "external perimeters": "outer_wall",
        "overhang wall": "overhang",
        "overhang perimeter": "overhang",
        "bridge": "bridge",
        "bridges": "bridge",
        "sparse infill": "sparse_infill",
        "infill": "sparse_infill",
        "internal infill": "sparse_infill",
        "solid infill": "solid_infill",
        "internal solid infill": "solid_infill",
        "top solid infill": "top_surface",
        "top surface": "top_surface",
        "bottom surface": "bottom_surface",
        "gap fill": "gap_fill",
        "support": "support",
        "support material": "support",
        "skirt": "skirt_brim",
        "brim": "skirt_brim",
        "skirt/brim": "skirt_brim",
        "prime tower": "prime_tower",
        "wipe tower": "prime_tower",
        "ironing": "ironing",
    }
    return aliases.get(text, text.replace(" ", "_"))


DEFAULT_FLOW_GOV_INCLUDE = {"sparse_infill", "solid_infill"}
DEFAULT_FLOW_GOV_EXCLUDE = {
    "outer_wall",
    "overhang",
    "bridge",
    "top_surface",
    "bottom_surface",
    "gap_fill",
    "support",
    "skirt_brim",
    "prime_tower",
    "ironing",
}


def parse_feature_set(value: str, default: set[str]) -> set[str]:
    if not value:
        return set(default)
    if value.lower() in {"none", "off", "-"}:
        return set()
    return {normalise_feature_name(item) for item in value.split(",") if item.strip()}


@dataclass
class FlowGovernorState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0
    feed: float = 0.0
    xyz_absolute: bool = True
    e_absolute: bool = True
    layer: int = -1
    feature: str = "unknown"


def update_layer_feature_from_comment(state: FlowGovernorState, comment: str) -> None:
    if not comment:
        return
    text = comment[1:].strip()
    upper = text.upper()
    if upper.startswith("TYPE:"):
        state.feature = normalise_feature_name(text.split(":", 1)[1])
    elif upper.startswith("FEATURE:"):
        state.feature = normalise_feature_name(text.split(":", 1)[1])
    elif upper.startswith("LAYER:"):
        value = text.split(":", 1)[1].strip()
        try:
            state.layer = int(float(value))
        except ValueError:
            pass
    elif upper.startswith("LAYER_CHANGE"):
        if state.layer < 0:
            state.layer = 0
        else:
            state.layer += 1


def flow_governor_allowed_feature(
    feature: str,
    include_features: set[str],
    exclude_features: set[str],
    allow_unknown: bool,
) -> bool:
    if feature in exclude_features:
        return False
    if feature == "unknown":
        return allow_unknown
    return feature in include_features


def flow_governor(args: argparse.Namespace) -> dict[str, Any]:
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        raise SystemExit(f"Input G-code not found: {input_path}")
    if args.maxflow_score:
        score = read_json(Path(args.maxflow_score))
        if args.safe_max_flow <= 0:
            value = score.get("safe_max_flow_mm3_s") if isinstance(score, dict) else None
            if value is not None:
                args.safe_max_flow = float(value)
    if args.safe_max_flow <= 0:
        raise SystemExit("--safe-max-flow must be positive, or pass --maxflow-score with safe_max_flow_mm3_s")
    if args.max_factor < 1.0:
        raise SystemExit("--max-factor must be >= 1.0")
    if args.max_speed <= 0:
        raise SystemExit("--max-speed must be positive")
    cap_over_safe = bool(getattr(args, "cap_over_safe", True))

    include_features = parse_feature_set(args.include_features, DEFAULT_FLOW_GOV_INCLUDE)
    exclude_features = parse_feature_set(args.exclude_features, DEFAULT_FLOW_GOV_EXCLUDE)
    filament_area = math.pi * (args.filament_diameter / 2.0) ** 2
    old_to_new_ratio = None
    if args.old_max_flow > 0:
        old_to_new_ratio = args.safe_max_flow / args.old_max_flow

    state = FlowGovernorState(e_absolute=not bool(args.default_relative_e))
    lines = input_path.read_text(errors="replace").splitlines(keepends=True)
    out_lines: list[str] = []
    changed = 0
    sped_up = 0
    slowed_down = 0
    eligible = 0
    extrusion_moves = 0
    skipped_reasons: dict[str, int] = {}
    feature_stats: dict[str, dict[str, float]] = {}
    old_time_s = 0.0
    new_time_s = 0.0
    old_extrusion_time_s = 0.0
    new_extrusion_time_s = 0.0
    max_seen_flow = 0.0
    max_new_flow = 0.0
    max_seen_allowed_flow = 0.0
    max_new_allowed_flow = 0.0

    def skip(reason: str) -> None:
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    def stat_feature(feature: str, key: str, amount: float = 1.0) -> None:
        stats = feature_stats.setdefault(
            feature,
            {
                "moves": 0,
                "changed": 0,
                "sped_up": 0,
                "slowed_down": 0,
                "old_time_s": 0.0,
                "new_time_s": 0.0,
            },
        )
        stats[key] = stats.get(key, 0.0) + amount

    for raw_line in lines:
        newline = "\n" if raw_line.endswith("\n") else ""
        code, comment = split_gcode_comment(raw_line)
        command, params, _ = parse_gcode_tokens(code)
        update_layer_feature_from_comment(state, comment)

        if command in {"G90"}:
            state.xyz_absolute = True
            out_lines.append(raw_line)
            continue
        if command in {"G91"}:
            state.xyz_absolute = False
            out_lines.append(raw_line)
            continue
        if command in {"M82"}:
            state.e_absolute = True
            out_lines.append(raw_line)
            continue
        if command in {"M83"}:
            state.e_absolute = False
            out_lines.append(raw_line)
            continue
        if command == "G92":
            if "X" in params:
                state.x = params["X"]
            if "Y" in params:
                state.y = params["Y"]
            if "Z" in params:
                state.z = params["Z"]
            if "E" in params:
                state.e = params["E"]
            out_lines.append(raw_line)
            continue

        if command not in {"G0", "G1"}:
            out_lines.append(raw_line)
            continue

        old_x, old_y, old_z, old_e = state.x, state.y, state.z, state.e
        target_x = old_x
        target_y = old_y
        target_z = old_z
        if "X" in params:
            target_x = params["X"] if state.xyz_absolute else old_x + params["X"]
        if "Y" in params:
            target_y = params["Y"] if state.xyz_absolute else old_y + params["Y"]
        if "Z" in params:
            target_z = params["Z"] if state.xyz_absolute else old_z + params["Z"]

        e_delta = 0.0
        if "E" in params:
            if state.e_absolute:
                e_delta = params["E"] - old_e
                state.e = params["E"]
            else:
                e_delta = params["E"]
                state.e = old_e + params["E"]

        if "F" in params:
            state.feed = params["F"]
        feed = state.feed
        distance = math.sqrt(
            (target_x - old_x) ** 2 + (target_y - old_y) ** 2 + (target_z - old_z) ** 2
        )
        state.x, state.y, state.z = target_x, target_y, target_z

        if feed > 0 and distance > 0:
            move_time = distance / (feed / 60.0)
            old_time_s += move_time
            new_time_for_total = move_time
        else:
            move_time = 0.0
            new_time_for_total = 0.0

        if command != "G1" or e_delta <= 0 or distance < args.min_move or feed <= 0:
            if e_delta > 0:
                skip("non_xy_or_too_short")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            continue

        extrusion_moves += 1
        stat_feature(state.feature, "moves", 1.0)
        old_extrusion_time_s += move_time
        stat_feature(state.feature, "old_time_s", move_time)
        flow = (e_delta * filament_area) / max(1e-9, move_time)
        max_seen_flow = max(max_seen_flow, flow)

        allowed = flow_governor_allowed_feature(
            state.feature,
            include_features,
            exclude_features,
            bool(args.allow_unknown_features),
        )
        if not allowed:
            skip(f"feature:{state.feature}")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            continue
        if state.layer >= 0 and state.layer < args.first_layer_count:
            skip("first_layer")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            continue

        max_seen_allowed_flow = max(max_seen_allowed_flow, flow)
        over_safe = flow > args.safe_max_flow * args.max_flow_fraction
        if over_safe and not cap_over_safe:
            skip("already_near_safe_max")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            max_new_allowed_flow = max(max_new_allowed_flow, flow)
            continue
        if (
            not over_safe
            and args.old_max_flow > 0
            and flow < args.old_max_flow * args.min_old_flow_ratio
        ):
            skip("below_old_limit_ratio")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            max_new_allowed_flow = max(max_new_allowed_flow, flow)
            continue

        eligible += 1
        mode = "cap" if over_safe else "boost"
        if mode == "cap":
            target_flow = args.safe_max_flow
        else:
            target_flow = args.safe_max_flow
            if old_to_new_ratio is not None:
                target_flow = min(args.safe_max_flow, flow * old_to_new_ratio)
            target_flow = min(target_flow, flow * args.max_factor)
        target_feed = feed * target_flow / max(1e-9, flow)
        if mode == "boost":
            target_feed = min(target_feed, args.max_speed * 60.0)
        if mode == "boost" and target_feed <= feed * (1.0 + args.min_gain):
            skip("gain_too_small")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            max_new_allowed_flow = max(max_new_allowed_flow, flow)
            continue
        if mode == "cap" and target_feed >= feed:
            skip("cap_not_needed")
            out_lines.append(raw_line)
            new_time_s += new_time_for_total
            new_extrusion_time_s += move_time
            stat_feature(state.feature, "new_time_s", move_time)
            max_new_flow = max(max_new_flow, flow)
            max_new_allowed_flow = max(max_new_allowed_flow, flow)
            continue

        new_flow = flow * (target_feed / feed)
        max_new_flow = max(max_new_flow, new_flow)
        max_new_allowed_flow = max(max_new_allowed_flow, new_flow)
        new_move_time = move_time * (feed / target_feed)
        new_code = rewrite_feedrate(code, target_feed)
        annotation = ""
        if args.annotate:
            annotation = (
                f" ; TINMAN_FLOW_GOV oldF={feed:.1f} newF={target_feed:.1f}"
                f" flow={flow:.3f}->{new_flow:.3f} feature={state.feature} mode={mode}"
            )
            if comment:
                new_line = f"{new_code} {comment}{annotation}{newline}"
            else:
                new_line = f"{new_code}{annotation}{newline}"
        else:
            new_line = f"{new_code}"
            if comment:
                new_line += f" {comment}"
            new_line += newline
        out_lines.append(new_line)
        if args.restore_feed_after_change:
            restore_line = f"G1 {format_feedrate(feed)} ; TINMAN_FLOW_GOV restore modal feedrate{newline}"
            out_lines.append(restore_line)
            state.feed = feed
        else:
            state.feed = target_feed
        changed += 1
        if mode == "boost":
            sped_up += 1
            stat_feature(state.feature, "sped_up", 1.0)
        else:
            slowed_down += 1
            stat_feature(state.feature, "slowed_down", 1.0)
        new_time_s += new_move_time
        new_extrusion_time_s += new_move_time
        stat_feature(state.feature, "changed", 1.0)
        stat_feature(state.feature, "new_time_s", new_move_time)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    header = ""
    if args.add_header:
        header = (
            f"; TINMAN_FLOW_GOVERNOR safe_max_flow={args.safe_max_flow:.3f} "
            f"old_max_flow={args.old_max_flow:.3f} max_factor={args.max_factor:.3f}\n"
        )
    output_path.write_text(header + "".join(out_lines))
    report = {
        "kind": "tinman_flow_aware_governor_report",
        "version": 1,
        "input": str(input_path),
        "output": str(output_path),
        "safe_max_flow_mm3_s": args.safe_max_flow,
        "old_max_flow_mm3_s": args.old_max_flow,
        "filament_diameter": args.filament_diameter,
        "cap_over_safe": cap_over_safe,
        "include_features": sorted(include_features),
        "exclude_features": sorted(exclude_features),
        "allow_unknown_features": bool(args.allow_unknown_features),
        "extrusion_moves": extrusion_moves,
        "eligible_moves": eligible,
        "changed_moves": changed,
        "sped_up_moves": sped_up,
        "slowed_down_moves": slowed_down,
        "max_seen_flow_mm3_s": round(float(max_seen_flow), 4),
        "max_new_flow_mm3_s": round(float(max_new_flow), 4),
        "max_seen_allowed_flow_mm3_s": round(float(max_seen_allowed_flow), 4),
        "max_new_allowed_flow_mm3_s": round(float(max_new_allowed_flow), 4),
        "estimated_motion_time_s": round(float(old_time_s), 3),
        "estimated_motion_time_after_s": round(float(new_time_s), 3),
        "estimated_extrusion_time_s": round(float(old_extrusion_time_s), 3),
        "estimated_extrusion_time_after_s": round(float(new_extrusion_time_s), 3),
        "estimated_saved_s": round(float(max(0.0, old_time_s - new_time_s)), 3),
        "estimated_added_s": round(float(max(0.0, new_time_s - old_time_s)), 3),
        "estimated_time_delta_s": round(float(new_time_s - old_time_s), 3),
        "estimated_extrusion_saved_s": round(float(max(0.0, old_extrusion_time_s - new_extrusion_time_s)), 3),
        "estimated_extrusion_added_s": round(float(max(0.0, new_extrusion_time_s - old_extrusion_time_s)), 3),
        "estimated_extrusion_time_delta_s": round(float(new_extrusion_time_s - old_extrusion_time_s), 3),
        "skipped_reasons": skipped_reasons,
        "feature_stats": feature_stats,
        "notes": [
            "Time estimates ignore acceleration, junction deviation, input shaping, and firmware velocity caps.",
            "Default policy speeds sparse/solid infill only; outer walls, bridges, top surfaces, first layer, supports, and unknown features are protected.",
            "Use old_max_flow for the most surgical same-print speedup after a max-flow calibration.",
        ],
    }
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        report["report"] = str(report_path)
    return report


def make_synthetic_flow_governor_gcode(args: argparse.Namespace) -> dict[str, Any]:
    filament_area = math.pi * (args.filament_diameter / 2.0) ** 2

    def e_for_flow(flow: float, length: float, speed: float) -> float:
        move_time = length / speed
        return flow * move_time / filament_area

    lines = [
        "; generated synthetic TinMan flow-governor fixture",
        "G90",
        "M83",
        ";LAYER:0",
        ";TYPE:Outer wall",
        "G1 X0 Y0 Z0.24 F12000",
        f"G1 X40 Y0 E{e_for_flow(9.0, 40.0, 80.0):.5f} F4800",
        ";TYPE:Sparse infill",
        f"G1 X80 Y0 E{e_for_flow(args.old_max_flow, 40.0, 120.0):.5f} F7200",
        ";LAYER:1",
        ";TYPE:Sparse infill",
        "G1 X80 Y10 F12000",
        f"G1 X0 Y10 E{e_for_flow(args.old_max_flow, 80.0, 120.0):.5f} F7200",
        ";TYPE:Internal solid infill",
        "G1 X0 Y20 F12000",
        f"G1 X80 Y20 E{e_for_flow(args.old_max_flow * 0.92, 80.0, 110.0):.5f} F6600",
        ";TYPE:Top surface",
        "G1 X80 Y30 F12000",
        f"G1 X0 Y30 E{e_for_flow(10.0, 80.0, 80.0):.5f} F4800",
        ";TYPE:Bridge",
        "G1 X0 Y40 F12000",
        f"G1 X80 Y40 E{e_for_flow(8.0, 80.0, 70.0):.5f} F4200",
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return {"output": str(output), "lines": len(lines), "old_max_flow": args.old_max_flow}


SAME_PRINT_TARGET_PRESETS: dict[str, dict[str, Any]] = {
    "prusa_core_one": {
        "label": "Prusa Core One",
        "flavor": "prusa",
        "pa_score": "outputs/auto_pa_v0/prusa_sim_summary.json",
        "pa_reference_k": 0.040,
        "maxflow_score": "outputs/auto_pa_v0/prusa_core_one_maxflow_sim_score.json",
        "old_max_flow": 18.0,
        "calibration_assets": [
            "outputs/auto_pa_v0/prusa_core_one_pa_sweep.gcode",
            "outputs/auto_pa_v0/prusa_core_one_maxflow_sweep.gcode",
        ],
        "status": "offline; ready for simulator/replay, live run after tool board repair",
    },
    "qidi_plus4": {
        "label": "Qidi Plus 4",
        "flavor": "m900",
        "pa_score": "outputs/auto_pa_v0/qidi_plus4_synthetic_beacon_fused_score.json",
        "pa_reference_k": 0.038,
        "maxflow_score": "outputs/auto_pa_v0/qidi_plus4_maxflow_synthetic_score.json",
        "old_max_flow": 20.0,
        "calibration_assets": [
            "outputs/auto_pa_v0/qidi_plus4_auto_pa_coupon.gcode",
            "outputs/auto_pa_v0/qidi_plus4_maxflow_ladder.gcode",
        ],
        "status": "generated; Beacon live probing remains gated pending supervised validation",
    },
    "maxez": {
        "label": "Qidi Max EZ",
        "flavor": "klipper",
        "pa_score": "outputs/auto_pa_v0/maxez_synthetic_beacon_fused_score.json",
        "pa_reference_k": 0.036,
        "maxflow_score": "outputs/auto_pa_v0/maxez_maxflow_synthetic_score.json",
        "old_max_flow": 20.0,
        "calibration_assets": [
            "outputs/auto_pa_v0/maxez_auto_pa_coupon.gcode",
            "outputs/auto_pa_v0/maxez_maxflow_ladder.gcode",
        ],
        "status": "online but toolhead apart; do not run motion yet",
    },
    "ratrig_vcore4_t0": {
        "label": "RatRig V-Core 4 T0",
        "flavor": "klipper",
        "pa_score": "outputs/auto_pa_v0/ratrig_vcore4_t0_synthetic_beacon_fused_score.json",
        "pa_reference_k": 0.036,
        "maxflow_score": "outputs/auto_pa_v0/ratrig_vcore4_t0_maxflow_synthetic_score.json",
        "old_max_flow": 24.0,
        "calibration_assets": [
            "outputs/auto_pa_v0/ratrig_vcore4_t0_auto_pa_coupon.gcode",
            "outputs/auto_pa_v0/ratrig_vcore4_t0_maxflow_ladder.gcode",
        ],
        "status": "offline; IDEX tool must be validated independently",
    },
    "ratrig_vcore4_t1": {
        "label": "RatRig V-Core 4 T1",
        "flavor": "klipper",
        "pa_score": "outputs/auto_pa_v0/ratrig_vcore4_t1_synthetic_beacon_fused_score.json",
        "pa_reference_k": 0.036,
        "maxflow_score": "outputs/auto_pa_v0/ratrig_vcore4_t1_maxflow_synthetic_score.json",
        "old_max_flow": 24.0,
        "calibration_assets": [
            "outputs/auto_pa_v0/ratrig_vcore4_t1_auto_pa_coupon.gcode",
            "outputs/auto_pa_v0/ratrig_vcore4_t1_maxflow_ladder.gcode",
        ],
        "status": "offline; IDEX tool must be validated independently",
    },
}


def nested_get(data: Any, path: str) -> Any:
    cur = data
    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def parse_pa_value_from_command(command: str) -> Optional[float]:
    patterns = [
        r"\bADVANCE\s*=\s*(-?\d+(?:\.\d+)?)",
        r"\bK\s*(-?\d+(?:\.\d+)?)",
        r"\bS\s*(-?\d+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, command, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def pa_command_flavor_from_code(code: str) -> str:
    stripped = code.lstrip().upper()
    if stripped.startswith("M900"):
        return "m900"
    if stripped.startswith("M572"):
        return "prusa"
    if stripped.startswith("SET_PRESSURE_ADVANCE"):
        return "klipper"
    return ""


def pa_values_from_text(text: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        code, _ = split_gcode_comment(raw_line)
        flavor = pa_command_flavor_from_code(code)
        if not flavor:
            continue
        value = parse_pa_value_from_command(code)
        if value is not None:
            values.append({"line": line_no, "value": value, "flavor": flavor, "code": code.strip()})
    return values


def first_gcode_config_value(text: str, key: str) -> str:
    prefix = f"; {key} = "
    value = ""
    for line in text.splitlines():
        if line.startswith(prefix):
            value = line[len(prefix) :].strip()
    return value


def first_float_from_setting(value: str) -> Optional[float]:
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    if not match:
        return None
    return float(match.group(0))


def split_setting_values(value: str) -> list[str]:
    if not value:
        return []
    if ";" in value:
        try:
            row = next(csv.reader([value], delimiter=";", quotechar='"'))
            return [item.strip().strip('"') for item in row]
        except csv.Error:
            return [item.strip().strip('"') for item in value.split(";")]
    if "," in value:
        return [item.strip().strip('"') for item in value.split(",")]
    return [value.strip().strip('"')]


def setting_for_index(value: str, index: int) -> str:
    values = split_setting_values(value)
    if not values:
        return ""
    if 0 <= index < len(values):
        return values[index]
    return values[0]


def detect_active_extruder(text: str) -> int:
    match = re.search(r"\bPRINT_START\w*\b[^\n;]*\bEXTRUDER\s*=\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    match = re.search(r"(?m)^\s*T(\d+)\s*(?:;.*)?$", text)
    if match:
        return int(match.group(1))
    return 0


def detect_start_temperature(text: str, key: str) -> Optional[float]:
    start_match = re.search(
        rf"\bPRINT_START\w*\b[^\n;]*\b{re.escape(key)}\s*=\s*(-?\d+(?:\.\d+)?)",
        text,
        re.IGNORECASE,
    )
    if start_match:
        return float(start_match.group(1))
    command = {"BED": "M140", "HOTEND": "M104", "CHAMBER": "M141"}.get(key.upper())
    if command:
        match = re.search(rf"(?m)^\s*{command}\s+S(-?\d+(?:\.\d+)?)\b", text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def detect_generation_line(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("; generated by TinManX1"):
            return line[2:].strip()
    return ""


def count_gcode_features(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in text.splitlines():
        if line.startswith(";TYPE:"):
            feature = normalise_feature_name(line.split(":", 1)[1])
            counts[feature] = counts.get(feature, 0) + 1
        elif line.startswith("; FEATURE:"):
            feature = normalise_feature_name(line.split(":", 1)[1])
            counts[feature] = counts.get(feature, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def model_context_from_info(model_info: dict[str, Any]) -> dict[str, Any]:
    config = model_info.get("config", {}) if isinstance(model_info, dict) else {}
    active = model_info.get("active_config", {}) if isinstance(model_info, dict) else {}
    context = {
        "printer_model": config.get("printer_model", ""),
        "printer_settings_id": config.get("printer_settings_id", ""),
        "print_settings_id": config.get("print_settings_id", ""),
        "filament_settings_id": active.get("filament_settings_id") or config.get("filament_settings_id", ""),
        "filament_type": active.get("filament_type") or config.get("filament_type", ""),
        "filament_vendor": active.get("filament_vendor") or config.get("filament_vendor", ""),
        "nozzle_diameter": first_float_from_setting(active.get("nozzle_diameter") or config.get("nozzle_diameter", "")),
        "filament_diameter": model_info.get("detected_filament_diameter"),
        "nozzle_temp": model_info.get("detected_nozzle_temp_c"),
        "bed_temp": model_info.get("detected_bed_temp_c"),
        "chamber_temp": model_info.get("detected_chamber_temp_c"),
        "gcode_flavor": config.get("gcode_flavor", ""),
        "active_extruder": model_info.get("active_extruder", 0),
    }
    return context


def infer_same_print_model_info(text: str) -> dict[str, Any]:
    pa_values = pa_values_from_text(text)
    pa_flavor = pa_values[0]["flavor"] if pa_values else ""
    pa_reference = pa_values[0]["value"] if pa_values else None
    active_extruder = detect_active_extruder(text)
    config_keys = [
        "printer_model",
        "printer_settings_id",
        "print_settings_id",
        "filament_settings_id",
        "filament_type",
        "filament_vendor",
        "filament_max_volumetric_speed",
        "filament_flow_ratio",
        "nozzle_diameter",
        "gcode_flavor",
        "use_relative_e_distances",
        "pressure_advance",
        "adaptive_pressure_advance",
        "first_layer_bed_temperature",
        "first_layer_temperature",
    ]
    config = {key: first_gcode_config_value(text, key) for key in config_keys}
    active_config = {
        key: setting_for_index(config.get(key, ""), active_extruder)
        for key in (
            "filament_settings_id",
            "filament_type",
            "filament_vendor",
            "filament_max_volumetric_speed",
            "filament_flow_ratio",
            "pressure_advance",
            "adaptive_pressure_advance",
        )
    }
    active_config["nozzle_diameter"] = config.get("nozzle_diameter", "")
    old_max_flow = first_float_from_setting(active_config.get("filament_max_volumetric_speed", ""))
    filament_diameter = first_float_from_setting(first_gcode_config_value(text, "filament_diameter"))
    nozzle_temp = detect_start_temperature(text, "HOTEND")
    bed_temp = detect_start_temperature(text, "BED")
    chamber_temp = detect_start_temperature(text, "CHAMBER")
    return {
        "generated_by": detect_generation_line(text),
        "active_extruder": active_extruder,
        "pa_command_count": len(pa_values),
        "pa_commands": pa_values[:20],
        "pa_commands_truncated": max(0, len(pa_values) - 20),
        "detected_pa_reference_k": pa_reference,
        "detected_pa_flavor": pa_flavor,
        "detected_old_max_flow_mm3_s": old_max_flow,
        "detected_filament_diameter": filament_diameter,
        "detected_nozzle_temp_c": nozzle_temp,
        "detected_bed_temp_c": bed_temp,
        "detected_chamber_temp_c": chamber_temp,
        "feature_counts": count_gcode_features(text),
        "config": config,
        "active_config": active_config,
        "context": {},
    }


def normalised_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def parse_score_time(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def score_context_from_data(data: dict[str, Any]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for key in ("compatibility", "calibration_context", "context", "model_context", "metadata"):
        value = data.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    merged: dict[str, Any] = {}
    for candidate in candidates:
        for key, value in candidate.items():
            if value not in ("", None, [], {}):
                merged[key] = value
    for key in (
        "printer_model",
        "printer_settings_id",
        "print_settings_id",
        "filament_settings_id",
        "filament_type",
        "filament_vendor",
        "nozzle_diameter",
        "filament_diameter",
        "nozzle_temp",
        "nozzle_temp_c",
        "bed_temp",
        "bed_temp_c",
        "chamber_temp",
        "chamber_temp_c",
        "gcode_flavor",
        "created_at",
        "calibrated_at",
        "measured_at",
        "synthetic",
    ):
        if key in data and data[key] not in ("", None, [], {}):
            merged.setdefault(key, data[key])
    if "machine_label" in data:
        merged.setdefault("machine_label", data["machine_label"])
    if "adapter" in data:
        merged.setdefault("adapter", data["adapter"])
    return merged


def score_is_synthetic(path: str, data: dict[str, Any], context: dict[str, Any]) -> bool:
    if context.get("synthetic") is True or data.get("synthetic") is True:
        return True
    haystack = " ".join(
        str(value)
        for value in (
            path,
            data.get("kind", ""),
            data.get("note", ""),
            data.get("manifest", ""),
            data.get("measurements", ""),
            data.get("raw_npz", ""),
        )
    ).lower()
    return any(token in haystack for token in ("synthetic", "simulation", "simulate", "_sim_"))


def score_created_at(context: dict[str, Any]) -> Optional[datetime]:
    for key in ("created_at", "calibrated_at", "measured_at"):
        parsed = parse_score_time(context.get(key))
        if parsed is not None:
            return parsed
    return None


def describe_score(path: str, score_type: str, value: Optional[float], source: str) -> dict[str, Any]:
    if not path:
        return {
            "path": "",
            "score_type": score_type,
            "value": value,
            "value_source": source,
            "present": False,
            "synthetic": False,
            "context": {},
            "metadata_present": False,
            "warnings": ["No score path was used."],
        }
    data = read_json(Path(path))
    if not isinstance(data, dict):
        data = {}
    context = score_context_from_data(data)
    synthetic = score_is_synthetic(path, data, context)
    created_at = score_created_at(context)
    metadata_keys = {
        "printer_model",
        "printer_settings_id",
        "filament_settings_id",
        "filament_type",
        "nozzle_diameter",
        "nozzle_temp",
        "nozzle_temp_c",
        "bed_temp",
        "bed_temp_c",
        "created_at",
        "calibrated_at",
        "measured_at",
    }
    metadata_present = any(key in context for key in metadata_keys)
    return {
        "path": path,
        "score_type": score_type,
        "value": value,
        "value_source": source,
        "present": True,
        "kind": data.get("kind", ""),
        "machine_label": data.get("machine_label", ""),
        "adapter": data.get("adapter", ""),
        "synthetic": synthetic,
        "metadata_present": metadata_present,
        "created_at": None if created_at is None else created_at.isoformat(),
        "context": context,
        "trusted_for_supervised_apply": bool(
            data.get("trusted_for_supervised_apply")
            or nested_get(data, "qidi.trusted_for_supervised_apply")
        ),
        "confidence": data.get("confidence"),
        "warnings": data.get("warnings", []),
    }


def score_context_value(context: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = context.get(key)
        if value not in ("", None, [], {}):
            return value
    return None


def compare_float_context(
    issues: list[dict[str, Any]],
    *,
    score_type: str,
    field: str,
    score_value: Any,
    model_value: Any,
    tolerance: float,
) -> None:
    if score_value in ("", None) or model_value in ("", None):
        return
    try:
        score_float = float(score_value)
        model_float = float(model_value)
    except (TypeError, ValueError):
        return
    if abs(score_float - model_float) > tolerance:
        issues.append(
            {
                "gate": "mismatch",
                "score_type": score_type,
                "field": field,
                "score_value": score_float,
                "model_value": model_float,
                "message": f"{score_type} score {field} {score_float} does not match model {model_float}.",
            }
        )


def compare_text_context(
    issues: list[dict[str, Any]],
    *,
    score_type: str,
    field: str,
    score_value: Any,
    model_value: Any,
) -> None:
    if score_value in ("", None) or model_value in ("", None):
        return
    if normalised_text(score_value) != normalised_text(model_value):
        issues.append(
            {
                "gate": "mismatch",
                "score_type": score_type,
                "field": field,
                "score_value": score_value,
                "model_value": model_value,
                "message": f"{score_type} score {field} does not match the model.",
            }
        )


def score_compatibility_issues(
    score_info: dict[str, Any],
    model_context: dict[str, Any],
    *,
    max_age_hours: float,
) -> list[dict[str, Any]]:
    if not score_info.get("present"):
        return []
    score_type = str(score_info.get("score_type") or "score")
    issues: list[dict[str, Any]] = []
    if score_info.get("synthetic"):
        issues.append(
            {
                "gate": "synthetic",
                "score_type": score_type,
                "path": score_info.get("path", ""),
                "message": f"{score_type} score is synthetic/simulated.",
            }
        )
    if not score_info.get("metadata_present"):
        issues.append(
            {
                "gate": "missing_metadata",
                "score_type": score_type,
                "path": score_info.get("path", ""),
                "message": f"{score_type} score lacks compatibility metadata for printer/nozzle/material/temperature.",
            }
        )
        return issues

    context = score_info.get("context", {}) if isinstance(score_info.get("context"), dict) else {}
    compare_text_context(
        issues,
        score_type=score_type,
        field="printer_model",
        score_value=score_context_value(context, "printer_model"),
        model_value=model_context.get("printer_model"),
    )
    compare_text_context(
        issues,
        score_type=score_type,
        field="printer_settings_id",
        score_value=score_context_value(context, "printer_settings_id"),
        model_value=model_context.get("printer_settings_id"),
    )
    compare_text_context(
        issues,
        score_type=score_type,
        field="filament_settings_id",
        score_value=score_context_value(context, "filament_settings_id"),
        model_value=model_context.get("filament_settings_id"),
    )
    compare_text_context(
        issues,
        score_type=score_type,
        field="filament_type",
        score_value=score_context_value(context, "filament_type"),
        model_value=model_context.get("filament_type"),
    )
    compare_float_context(
        issues,
        score_type=score_type,
        field="nozzle_diameter",
        score_value=score_context_value(context, "nozzle_diameter"),
        model_value=model_context.get("nozzle_diameter"),
        tolerance=0.011,
    )
    compare_float_context(
        issues,
        score_type=score_type,
        field="nozzle_temp_c",
        score_value=score_context_value(context, "nozzle_temp_c", "nozzle_temp"),
        model_value=model_context.get("nozzle_temp"),
        tolerance=3.0,
    )
    compare_float_context(
        issues,
        score_type=score_type,
        field="bed_temp_c",
        score_value=score_context_value(context, "bed_temp_c", "bed_temp"),
        model_value=model_context.get("bed_temp"),
        tolerance=5.0,
    )
    created = score_created_at(context)
    if created is not None and max_age_hours > 0:
        age_hours = (datetime.now(timezone.utc) - created).total_seconds() / 3600.0
        if age_hours > max_age_hours:
            issues.append(
                {
                    "gate": "stale",
                    "score_type": score_type,
                    "age_hours": round(age_hours, 3),
                    "max_age_hours": max_age_hours,
                    "message": f"{score_type} score is stale: {age_hours:.1f} h old.",
                }
            )
    return issues


def filter_blocked_issues(issues: list[dict[str, Any]], args: argparse.Namespace) -> list[dict[str, Any]]:
    blocked: list[dict[str, Any]] = []
    for issue in issues:
        gate = issue.get("gate")
        if gate == "synthetic" and getattr(args, "allow_synthetic_scores", False):
            continue
        if gate == "missing_metadata" and getattr(args, "allow_missing_score_metadata", False):
            continue
        if gate == "mismatch" and getattr(args, "allow_mismatched_score_context", False):
            continue
        if gate == "stale" and getattr(args, "allow_stale_scores", False):
            continue
        blocked.append(issue)
    return blocked


def same_print_compatibility(
    *,
    model_info: dict[str, Any],
    pa_score_info: Optional[dict[str, Any]],
    maxflow_score_info: Optional[dict[str, Any]],
    args: argparse.Namespace,
) -> dict[str, Any]:
    model_context = model_context_from_info(model_info)
    issues: list[dict[str, Any]] = []
    if pa_score_info is not None:
        issues.extend(
            score_compatibility_issues(
                pa_score_info,
                model_context,
                max_age_hours=float(getattr(args, "score_max_age_hours", 168.0)),
            )
        )
    if maxflow_score_info is not None:
        issues.extend(
            score_compatibility_issues(
                maxflow_score_info,
                model_context,
                max_age_hours=float(getattr(args, "score_max_age_hours", 168.0)),
            )
        )
    blocked = filter_blocked_issues(issues, args)
    return {
        "model_context": model_context,
        "pa_score": pa_score_info,
        "maxflow_score": maxflow_score_info,
        "issues": issues,
        "blocked_issues": blocked,
        "safe_to_prepare": not blocked,
        "override_flags": {
            "allow_synthetic_scores": bool(getattr(args, "allow_synthetic_scores", False)),
            "allow_missing_score_metadata": bool(getattr(args, "allow_missing_score_metadata", False)),
            "allow_mismatched_score_context": bool(getattr(args, "allow_mismatched_score_context", False)),
            "allow_stale_scores": bool(getattr(args, "allow_stale_scores", False)),
            "score_max_age_hours": float(getattr(args, "score_max_age_hours", 168.0)),
        },
    }


def selected_pa_from_score(path: str) -> tuple[Optional[float], str, dict[str, Any]]:
    if not path:
        return None, "", {}
    data = read_json(Path(path))
    keys = [
        "selected_k",
        "bd_k_opt",
        "qidi.selected_k",
        "fusion.selected.k",
        "beacon.best.k",
        "selected.k",
        "best.k",
    ]
    for key in keys:
        value = nested_get(data, key)
        if value is not None:
            try:
                return float(value), key, data
            except (TypeError, ValueError):
                pass
    command = data.get("apply_command") if isinstance(data, dict) else None
    if isinstance(command, str):
        value = parse_pa_value_from_command(command)
        if value is not None:
            return value, "apply_command", data
    qidi = data.get("qidi") if isinstance(data, dict) else None
    if isinstance(qidi, dict) and isinstance(qidi.get("apply_command"), str):
        value = parse_pa_value_from_command(qidi["apply_command"])
        if value is not None:
            return value, "qidi.apply_command", data
    return None, "", data if isinstance(data, dict) else {}


def selected_maxflow_from_score(path: str) -> tuple[Optional[float], str, dict[str, Any]]:
    if not path:
        return None, "", {}
    data = read_json(Path(path))
    if not isinstance(data, dict):
        return None, "", {}
    for key in ("safe_max_flow_mm3_s", "safe_max_flow", "selected_safe_flow_mm3_s"):
        value = nested_get(data, key)
        if value is not None:
            try:
                return float(value), key, data
            except (TypeError, ValueError):
                pass
    return None, "", data


def same_print_inspect(args: argparse.Namespace) -> dict[str, Any]:
    model_input = Path(args.model_input)
    if not model_input.exists():
        raise SystemExit(f"model input not found: {model_input}")
    text = model_input.read_text(errors="replace")
    model_info = infer_same_print_model_info(text)
    model_info["byte_size"] = model_input.stat().st_size
    model_info["line_count"] = text.count("\n") + (0 if text.endswith("\n") else 1)

    preset = SAME_PRINT_TARGET_PRESETS.get(args.target, {}) if args.target else {}
    pa_score = args.pa_score or str(preset.get("pa_score") or "")
    maxflow_score = args.maxflow_score or str(preset.get("maxflow_score") or "")
    selected_k, selected_source, _ = selected_pa_from_score(pa_score) if pa_score else (None, "", {})
    safe_flow, safe_flow_source, _ = (
        selected_maxflow_from_score(maxflow_score) if maxflow_score else (None, "", {})
    )
    if args.fixed_pa is not None:
        selected_k = args.fixed_pa
        selected_source = "fixed_pa_arg"
        pa_score_info = None
    else:
        pa_score_info = describe_score(pa_score, "pa", selected_k, selected_source) if pa_score else None
    if args.safe_max_flow > 0:
        safe_flow = args.safe_max_flow
        safe_flow_source = "safe_max_flow_arg"
        maxflow_score_info = None
    else:
        maxflow_score_info = (
            describe_score(maxflow_score, "maxflow", safe_flow, safe_flow_source)
            if maxflow_score
            else None
        )
    compatibility = same_print_compatibility(
        model_info=model_info,
        pa_score_info=pa_score_info,
        maxflow_score_info=maxflow_score_info,
        args=args,
    )
    old_max_flow = (
        args.old_max_flow
        if args.old_max_flow > 0
        else model_info.get("detected_old_max_flow_mm3_s")
        or float(preset.get("old_max_flow") or 0.0)
    )
    result = {
        "kind": "tinman_same_print_inspect",
        "version": 1,
        "model_input": str(model_input),
        "target": args.target or "custom",
        "selected_pa_k": selected_k,
        "selected_pa_source": selected_source,
        "safe_max_flow_mm3_s": safe_flow,
        "safe_max_flow_source": safe_flow_source,
        "old_max_flow_mm3_s": old_max_flow,
        "model_info": model_info,
        "compatibility": compatibility,
        "recommendation": (
            "safe-to-prepare"
            if compatibility["safe_to_prepare"]
            else "blocked-until-score-context-is-real-or-explicitly-overridden"
        ),
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def same_print_stamp_score_context(args: argparse.Namespace) -> dict[str, Any]:
    score_input = Path(args.score_input)
    model_input = Path(args.model_input)
    if not score_input.exists():
        raise SystemExit(f"score input not found: {score_input}")
    if not model_input.exists():
        raise SystemExit(f"model input not found: {model_input}")
    data = read_json(score_input)
    if not isinstance(data, dict):
        raise SystemExit("score input must be a JSON object")
    text = model_input.read_text(errors="replace")
    model_info = infer_same_print_model_info(text)
    context = model_context_from_info(model_info)
    context.update(
        {
            "context_version": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_model": str(model_input),
            "score_origin": args.score_origin,
            "synthetic": args.score_origin == "synthetic",
            "measurement_channel": args.measurement_channel,
            "active_extruder": model_info.get("active_extruder", 0),
            "detected_pa_reference_k": model_info.get("detected_pa_reference_k"),
            "detected_old_max_flow_mm3_s": model_info.get("detected_old_max_flow_mm3_s"),
        }
    )
    if args.calibration_id:
        context["calibration_id"] = args.calibration_id
    data["calibration_context"] = context
    data["synthetic"] = args.score_origin == "synthetic"
    data["context_attached_by"] = "auto_pa.py same-print-stamp-score-context"
    data["context_attached_at"] = context["created_at"]

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n")
    return {
        "kind": "tinman_same_print_stamp_score_context",
        "version": 1,
        "score_input": str(score_input),
        "model_input": str(model_input),
        "output": str(output),
        "score_origin": args.score_origin,
        "measurement_channel": args.measurement_channel,
        "calibration_context": context,
        "note": "Use score_origin=real only after the score came from an actual same-printer measurement.",
    }


def raise_for_compatibility(compatibility: dict[str, Any]) -> None:
    blocked = compatibility.get("blocked_issues", [])
    if not blocked:
        return
    lines = ["same-print-prepare blocked by score compatibility gates:"]
    for issue in blocked:
        lines.append(f"- [{issue.get('gate')}] {issue.get('message')}")
    lines.append(
        "Use same-print-inspect for a read-only report, or pass the explicit allow-* flags only for offline dry-runs."
    )
    raise SystemExit("\n".join(lines))


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def shift_pa_code(code: str, delta_k: float, pa_min: float, pa_max: float) -> tuple[str, int, list[dict[str, float]]]:
    replacements: list[dict[str, float]] = []
    changed = 0
    stripped = code.lstrip()
    upper = stripped.upper()
    if upper.startswith("M900"):
        pattern = re.compile(r"(\bK\s*)(-?\d+(?:\.\d+)?)", re.IGNORECASE)
    elif upper.startswith("M572"):
        pattern = re.compile(r"(\bS\s*)(-?\d+(?:\.\d+)?)", re.IGNORECASE)
    elif upper.startswith("SET_PRESSURE_ADVANCE"):
        pattern = re.compile(r"(\bADVANCE\s*=\s*)(-?\d+(?:\.\d+)?)", re.IGNORECASE)
    else:
        return code, 0, replacements

    def repl(match: re.Match[str]) -> str:
        nonlocal changed
        old = float(match.group(2))
        new = clamp(old + delta_k, pa_min, pa_max)
        changed += 1
        replacements.append({"old": old, "new": new})
        return f"{match.group(1)}{new:.5f}"

    new_code = pattern.sub(repl, code, count=1)
    return new_code, changed, replacements


def shift_pa_commands_in_text(
    text: str,
    *,
    delta_k: float,
    pa_min: float,
    pa_max: float,
    annotate: bool = False,
) -> tuple[str, dict[str, Any]]:
    out: list[str] = []
    shifted = 0
    values: list[dict[str, float]] = []
    for raw_line in text.splitlines(keepends=True):
        newline = "\n" if raw_line.endswith("\n") else ""
        code, comment = split_gcode_comment(raw_line)
        new_code, count, rows = shift_pa_code(code, delta_k, pa_min, pa_max)
        if count:
            shifted += count
            values.extend(rows)
            suffix = ""
            if annotate:
                suffix = f" ; TINMAN_ADAPTIVE_PA_SHIFT delta={delta_k:+.5f}"
            if comment:
                out.append(f"{new_code} {comment}{suffix}{newline}")
            else:
                out.append(f"{new_code}{suffix}{newline}")
        else:
            out.append(raw_line)
    return "".join(out), {
        "shifted_commands": shifted,
        "delta_k": round(float(delta_k), 6),
        "pa_min": pa_min,
        "pa_max": pa_max,
        "values": values[:50],
        "values_truncated": max(0, len(values) - 50),
    }


def same_print_fixture(args: argparse.Namespace) -> dict[str, Any]:
    filament_area = math.pi * (args.filament_diameter / 2.0) ** 2

    def e_for_flow(flow: float, length: float, speed: float) -> float:
        return flow * (length / speed) / filament_area

    lines = [
        "; generated synthetic TinMan same-print model fixture",
        "G90",
        "M83",
        ";LAYER:0",
        ";TYPE:Outer wall",
        pa_command(args.flavor, args.reference_k),
        "G1 X0 Y0 Z0.24 F12000",
        f"G1 X40 Y0 E{e_for_flow(9.0, 40.0, 80.0):.5f} F4800",
        ";TYPE:Sparse infill",
        f"G1 X80 Y0 E{e_for_flow(args.old_max_flow, 40.0, 120.0):.5f} F7200",
        ";LAYER:1",
        ";TYPE:Sparse infill",
        pa_command(args.flavor, args.reference_k + args.adaptive_step),
        "G1 X80 Y10 F12000",
        f"G1 X0 Y10 E{e_for_flow(args.old_max_flow, 80.0, 120.0):.5f} F7200",
        ";TYPE:Internal solid infill",
        "G1 X0 Y20 F12000",
        f"G1 X80 Y20 E{e_for_flow(args.old_max_flow * 0.92, 80.0, 110.0):.5f} F6600",
        ";TYPE:Top surface",
        "G1 X80 Y30 F12000",
        f"G1 X0 Y30 E{e_for_flow(10.0, 80.0, 80.0):.5f} F4800",
        ";TYPE:Bridge",
        "G1 X0 Y40 F12000",
        f"G1 X80 Y40 E{e_for_flow(8.0, 80.0, 70.0):.5f} F4200",
    ]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    return {
        "kind": "tinman_same_print_fixture",
        "output": str(output),
        "flavor": args.flavor,
        "reference_k": args.reference_k,
        "old_max_flow": args.old_max_flow,
    }


def same_print_plan(args: argparse.Namespace) -> dict[str, Any]:
    targets = list(SAME_PRINT_TARGET_PRESETS)
    if args.target != "all":
        if args.target not in SAME_PRINT_TARGET_PRESETS:
            raise SystemExit(f"unknown target {args.target}; choose one of {', '.join(targets)}")
        targets = [args.target]
    plans: list[dict[str, Any]] = []
    for target in targets:
        preset = SAME_PRINT_TARGET_PRESETS[target]
        plans.append(
            {
                "target": target,
                "label": preset["label"],
                "status": preset["status"],
                "flavor": preset["flavor"],
                "pa_score": preset["pa_score"],
                "pa_reference_k": preset["pa_reference_k"],
                "maxflow_score": preset["maxflow_score"],
                "old_max_flow": preset["old_max_flow"],
                "calibration_assets": preset["calibration_assets"],
                "upcoming_print_sequence": [
                    "Run calibration prefix while heat soak is active.",
                    "Score fixed PA from loadcell/camera/Beacon/Hall measurements.",
                    "Score max volumetric flow from loadcell or Beacon/camera ladder.",
                    "Run same-print-prepare on the held model body.",
                    "Print the prepared body; it starts with fixed PA, shifted adaptive PA commands, and governed infill feed rates.",
                ],
                "prepare_example": (
                    "python3 outputs/auto_pa_v0/auto_pa.py same-print-prepare "
                    f"--target {target} --model-input <model_body.gcode> "
                    f"--output outputs/auto_pa_v0/{target}_same_print_prepared.gcode "
                    f"--report outputs/auto_pa_v0/{target}_same_print_report.json"
                ),
            }
        )
    result = {
        "kind": "tinman_same_print_plan",
        "version": 1,
        "targets": plans,
        "safety": [
            "This companion prepares files only; it does not upload, heat, move, or send live commands.",
            "Do not rewrite a G-code file while Moonraker/PrusaLink is already reading it.",
            "Use a split calibration-prefix/model-body print path or a future streaming host governor.",
        ],
    }
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")
    return result


def same_print_prepare(args: argparse.Namespace) -> dict[str, Any]:
    model_input = Path(args.model_input)
    if not model_input.exists():
        raise SystemExit(f"model input not found: {model_input}")
    text = model_input.read_text(errors="replace")
    model_info = infer_same_print_model_info(text)

    preset = SAME_PRINT_TARGET_PRESETS.get(args.target, {}) if args.target else {}
    flavor_source = "arg"
    if args.flavor != "auto":
        flavor = args.flavor
    elif model_info.get("detected_pa_flavor"):
        flavor = str(model_info["detected_pa_flavor"])
        flavor_source = "model_pa_command"
    else:
        flavor = str(preset.get("flavor") or "klipper")
        flavor_source = "target_preset" if preset else "default"
    pa_score = args.pa_score or str(preset.get("pa_score") or "")
    maxflow_score = args.maxflow_score or str(preset.get("maxflow_score") or "")

    old_max_flow_source = "arg"
    if args.old_max_flow > 0:
        old_max_flow = args.old_max_flow
    elif model_info.get("detected_old_max_flow_mm3_s"):
        old_max_flow = float(model_info["detected_old_max_flow_mm3_s"])
        old_max_flow_source = "model_filament_max_volumetric_speed"
    else:
        old_max_flow = float(preset.get("old_max_flow") or 0.0)
        old_max_flow_source = "target_preset" if preset else "default"

    filament_diameter_source = "arg"
    filament_diameter = args.filament_diameter
    if (
        args.filament_diameter == 1.75
        and model_info.get("detected_filament_diameter")
        and float(model_info["detected_filament_diameter"]) > 0
    ):
        filament_diameter = float(model_info["detected_filament_diameter"])
        filament_diameter_source = "model_header"

    adaptive_reference_source = "arg"
    adaptive_reference_k = args.adaptive_reference_k
    if adaptive_reference_k is None and model_info.get("detected_pa_reference_k") is not None:
        adaptive_reference_k = float(model_info["detected_pa_reference_k"])
        adaptive_reference_source = "model_pa_command"
    elif adaptive_reference_k is None and preset.get("pa_reference_k") is not None:
        adaptive_reference_k = float(preset["pa_reference_k"])
        adaptive_reference_source = "target_preset"

    selected_k = args.fixed_pa
    selected_source = "fixed_pa_arg" if selected_k is not None else ""
    if selected_k is None and pa_score:
        selected_k, selected_source, _ = selected_pa_from_score(pa_score)
    fixed_command = None
    if selected_k is not None and not args.no_fixed_pa:
        fixed_command = pa_command(flavor, selected_k)

    pa_score_info: Optional[dict[str, Any]] = None
    if (
        pa_score
        and selected_source != "fixed_pa_arg"
        and not (args.no_fixed_pa and args.adaptive_mode == "off")
    ):
        pa_score_info = describe_score(pa_score, "pa", selected_k, selected_source)

    maxflow_score_info: Optional[dict[str, Any]] = None
    maxflow_score_value = args.safe_max_flow if args.safe_max_flow > 0 else None
    maxflow_score_source = "safe_max_flow_arg" if args.safe_max_flow > 0 else ""
    if not args.no_flow_governor and maxflow_score and args.safe_max_flow <= 0:
        maxflow_score_value, maxflow_score_source, _ = selected_maxflow_from_score(maxflow_score)
        maxflow_score_info = describe_score(
            maxflow_score,
            "maxflow",
            maxflow_score_value,
            maxflow_score_source,
        )

    compatibility = same_print_compatibility(
        model_info=model_info,
        pa_score_info=pa_score_info,
        maxflow_score_info=maxflow_score_info,
        args=args,
    )
    raise_for_compatibility(compatibility)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    adaptive_report: dict[str, Any] = {
        "mode": args.adaptive_mode,
        "reference_k": adaptive_reference_k,
        "reference_source": adaptive_reference_source,
        "selected_k": selected_k,
        "shifted_commands": 0,
    }
    if (
        args.adaptive_mode == "shift-existing"
        and selected_k is not None
        and adaptive_reference_k is not None
    ):
        delta_k = float(selected_k) - float(adaptive_reference_k)
        text, adaptive_report = shift_pa_commands_in_text(
            text,
            delta_k=delta_k,
            pa_min=args.pa_min,
            pa_max=args.pa_max,
            annotate=args.annotate,
        )
        adaptive_report["mode"] = args.adaptive_mode
        adaptive_report["reference_k"] = adaptive_reference_k
        adaptive_report["reference_source"] = adaptive_reference_source
        adaptive_report["selected_k"] = selected_k
    elif args.adaptive_mode == "shift-existing":
        adaptive_report["note"] = "No adaptive shift applied because selected_k or reference_k is missing."

    temp_adapted = output.with_suffix(output.suffix + ".adaptive.tmp")
    temp_governed = output.with_suffix(output.suffix + ".flow.tmp")
    temp_flow_report = output.with_suffix(output.suffix + ".flow_report.json")
    temp_adapted.write_text(text)

    flow_report: dict[str, Any] | None = None
    body_path = temp_adapted
    if not args.no_flow_governor and (maxflow_score or args.safe_max_flow > 0):
        flow_args = argparse.Namespace(
            input=str(temp_adapted),
            output=str(temp_governed),
            report=str(temp_flow_report),
            safe_max_flow=args.safe_max_flow,
            maxflow_score=maxflow_score,
            old_max_flow=old_max_flow,
            filament_diameter=filament_diameter,
            max_factor=args.flow_max_factor,
            max_speed=args.flow_max_speed,
            min_move=args.flow_min_move,
            min_gain=args.flow_min_gain,
            max_flow_fraction=args.flow_max_flow_fraction,
            min_old_flow_ratio=args.flow_min_old_flow_ratio,
            first_layer_count=args.first_layer_count,
            include_features=args.flow_include_features,
            exclude_features=args.flow_exclude_features,
            allow_unknown_features=args.flow_allow_unknown_features,
            default_relative_e=args.default_relative_e,
            annotate=args.annotate,
            add_header=True,
            restore_feed_after_change=args.flow_restore_feed,
            cap_over_safe=args.flow_cap_over_safe,
        )
        flow_report = flow_governor(flow_args)
        body_path = temp_governed

    body = body_path.read_text(errors="replace")
    header = [
        "; TINMAN_SAME_PRINT_PREP_START",
        f"; target={args.target or 'custom'}",
        f"; flavor={flavor}",
        f"; pa_score={pa_score}",
        f"; maxflow_score={maxflow_score}",
        f"; selected_pa_k={'' if selected_k is None else f'{selected_k:.5f}'}",
        f"; adaptive_reference_k={'' if adaptive_reference_k is None else f'{adaptive_reference_k:.5f}'}",
        f"; adaptive_shifted_commands={adaptive_report.get('shifted_commands', 0)}",
        "; TINMAN_SAME_PRINT_MODEL_BODY",
    ]
    if fixed_command:
        header.append(fixed_command + " ; TINMAN fixed PA for upcoming print")
    header.append("; TINMAN_SAME_PRINT_PREP_END")
    output.write_text("\n".join(header) + "\n" + body)

    for temp in (temp_adapted, temp_governed):
        try:
            temp.unlink()
        except FileNotFoundError:
            pass

    result = {
        "kind": "tinman_same_print_prepare_report",
        "version": 1,
        "target": args.target or "custom",
        "output": str(output),
        "model_input": str(model_input),
        "flavor": flavor,
        "flavor_source": flavor_source,
        "pa_score": pa_score,
        "selected_pa_k": selected_k,
        "selected_pa_source": selected_source,
        "fixed_pa_command": fixed_command,
        "adaptive": adaptive_report,
        "maxflow_score": maxflow_score,
        "old_max_flow_mm3_s": old_max_flow,
        "old_max_flow_source": old_max_flow_source,
        "filament_diameter": filament_diameter,
        "filament_diameter_source": filament_diameter_source,
        "model_info": model_info,
        "compatibility": compatibility,
        "flow_governor": flow_report,
        "notes": [
            "Prepared body is safe to print only after the calibration prefix has finished and the score files are trusted.",
            "This command does not upload, heat, move, or send live printer commands.",
            "Adaptive PA v1 shifts PA commands already present in the model body; if none exist, fixed PA still applies.",
        ],
    }
    if args.report:
        report = Path(args.report)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result, indent=2) + "\n")
        result["report"] = str(report)
    return result


def moonraker_gcode_file_url(host: str, filename: str) -> str:
    safe_name = urllib.parse.quote(filename.lstrip("/"), safe="/")
    return f"http://{host}:7125/server/files/gcodes/{safe_name}"


def moonraker_gcode_metadata(host: str, filename: str, timeout: float = 10.0) -> dict[str, Any]:
    endpoint = "/server/files/metadata?filename=" + urllib.parse.quote(filename, safe="")
    data = moonraker_get(host, endpoint, timeout=timeout)
    result = data.get("result", data) if isinstance(data, dict) else {}
    return result if isinstance(result, dict) else {}


def qidi_download_active_gcode(args: argparse.Namespace) -> dict[str, Any]:
    status = qidi_query_monitor_status(args.host, timeout=args.timeout)
    print_stats = status.get("print_stats", {})
    virtual_sdcard = status.get("virtual_sdcard", {})
    filename = args.filename or str(print_stats.get("filename") or "")
    if not filename:
        raise SystemExit("No active filename found; pass --filename explicitly.")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, Any] = {}
    try:
        metadata = moonraker_gcode_metadata(args.host, filename, timeout=args.timeout)
    except Exception as exc:
        metadata = {"metadata_error": str(exc)}

    url = moonraker_gcode_file_url(args.host, filename)
    byte_count = 0
    with urllib.request.urlopen(url, timeout=args.timeout) as resp, output.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            byte_count += len(chunk)

    result = {
        "kind": "tinman_qidi_active_gcode_download",
        "version": 1,
        "host": args.host,
        "captured_at": utc_timestamp(),
        "filename": filename,
        "output": str(output),
        "bytes_written": byte_count,
        "metadata": metadata,
        "print_state": print_stats.get("state", ""),
        "virtual_sdcard": {
            "file_path": virtual_sdcard.get("file_path"),
            "file_position": virtual_sdcard.get("file_position"),
            "file_size": virtual_sdcard.get("file_size"),
            "progress": virtual_sdcard.get("progress"),
            "is_active": virtual_sdcard.get("is_active"),
        },
        "notes": [
            "Read-only Moonraker file GET only; this command does not pause, move, extrude, or change printer settings.",
            "Downloading an active G-code file is for analysis only. Do not rewrite the active file while Moonraker is reading it.",
        ],
    }
    if args.metadata_output:
        metadata_path = Path(args.metadata_output)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(result, indent=2) + "\n")
    return result


@dataclass
class GcodeTelemetryMapState:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0
    feed: float = 0.0
    xyz_absolute: bool = True
    e_absolute: bool = True
    layer: int = -1
    reported_layer: Optional[int] = None
    feature: str = "unknown"
    pa_k: Optional[float] = None
    accel: Optional[float] = None
    line_number: int = 0
    byte_start: int = 0
    byte_end: int = 0
    last_line: str = ""
    last_command: str = ""
    last_motion_line_number: int = 0
    last_motion_byte_start: int = 0
    last_motion_byte_end: int = 0
    last_motion_line: str = ""
    last_motion_kind: str = ""
    last_motion_distance_mm: Optional[float] = None
    last_motion_e_delta_mm: Optional[float] = None
    last_motion_time_s: Optional[float] = None
    last_motion_expected_flow_mm3_s: Optional[float] = None
    last_motion_expected_e_velocity_mm_s: Optional[float] = None
    last_motion_speed_mm_s: Optional[float] = None
    last_motion_start: Optional[list[float]] = None
    last_motion_end: Optional[list[float]] = None


GCODE_TELEMETRY_CSV_FIELDS = [
    "sample_index",
    "captured_at",
    "telemetry_state",
    "filename",
    "file_position",
    "file_size",
    "mapped_line_number",
    "mapped_byte_end",
    "mapped_feature",
    "mapped_layer_comment",
    "mapped_reported_layer",
    "telemetry_layer",
    "telemetry_total_layer",
    "progress",
    "gcode_pa_k",
    "telemetry_pa_k",
    "pa_delta",
    "gcode_accel",
    "last_command",
    "last_motion_line_number",
    "last_motion_kind",
    "last_motion_feature",
    "gcode_speed_mm_s",
    "telemetry_live_velocity_mm_s",
    "speed_ratio_live_to_gcode",
    "gcode_e_velocity_mm_s",
    "telemetry_live_e_velocity_mm_s",
    "e_velocity_ratio_live_to_gcode",
    "gcode_expected_flow_mm3_s",
    "gcode_expected_flow_hall_mm3_s",
    "telemetry_estimated_flow_mm3_s",
    "flow_delta_mm3_s",
    "flow_ratio_telemetry_to_gcode",
    "flow_delta_hall_mm3_s",
    "flow_ratio_telemetry_to_gcode_hall",
    "hall_diameter_mm",
    "extruder_temp_c",
    "extruder_target_c",
    "bed_temp_c",
    "bed_target_c",
    "chamber_temp_c",
    "chamber_target_c",
    "beacon_coil_temp_c",
    "beacon_frequency_hz",
    "beacon_data_smooth",
    "gcode_x",
    "gcode_y",
    "gcode_z",
    "gcode_e",
    "motion_x",
    "motion_y",
    "motion_z",
    "motion_e",
    "last_motion_line",
]


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            data = json.loads(text)
            if not isinstance(data, dict):
                raise SystemExit(f"JSONL row {line_number} is not an object")
            rows.append(data)
    return rows


def update_reported_layer_from_code(state: GcodeTelemetryMapState, code: str) -> None:
    match = re.search(r"\bCURRENT_LAYER\s*=\s*(-?\d+)", code, re.IGNORECASE)
    if match:
        state.reported_layer = int(match.group(1))


def classify_motion(command: str, distance: float, e_delta: float) -> str:
    if command == "G0":
        return "travel"
    if e_delta > 0 and distance > 0:
        return "extrude_xy"
    if e_delta > 0:
        return "extrude_e_only"
    if e_delta < 0:
        return "retract"
    if distance > 0:
        return "travel"
    return "dwell_or_noop"


def update_gcode_map_state(
    state: GcodeTelemetryMapState,
    raw_line: bytes,
    *,
    line_number: int,
    byte_start: int,
    byte_end: int,
    filament_area: float,
) -> None:
    text = raw_line.decode("utf-8", errors="replace").rstrip("\n\r")
    code, comment = split_gcode_comment(text)
    command, params, _ = parse_gcode_tokens(code)
    update_layer_feature_from_comment(state, comment)
    update_reported_layer_from_code(state, code)

    state.line_number = line_number
    state.byte_start = byte_start
    state.byte_end = byte_end
    state.last_line = text[:500]
    state.last_command = command

    if command == "G90":
        state.xyz_absolute = True
        return
    if command == "G91":
        state.xyz_absolute = False
        return
    if command == "M82":
        state.e_absolute = True
        return
    if command == "M83":
        state.e_absolute = False
        return
    if command == "G92":
        if "X" in params:
            state.x = params["X"]
        if "Y" in params:
            state.y = params["Y"]
        if "Z" in params:
            state.z = params["Z"]
        if "E" in params:
            state.e = params["E"]
        return
    if command == "M204":
        if "S" in params:
            state.accel = params["S"]
        elif "P" in params:
            state.accel = params["P"]

    pa_value = parse_pa_value_from_command(code) if pa_command_flavor_from_code(code) else None
    if pa_value is not None:
        state.pa_k = pa_value
        return

    if command not in {"G0", "G1"}:
        return

    old_x, old_y, old_z, old_e = state.x, state.y, state.z, state.e
    target_x = old_x
    target_y = old_y
    target_z = old_z
    if "X" in params:
        target_x = params["X"] if state.xyz_absolute else old_x + params["X"]
    if "Y" in params:
        target_y = params["Y"] if state.xyz_absolute else old_y + params["Y"]
    if "Z" in params:
        target_z = params["Z"] if state.xyz_absolute else old_z + params["Z"]

    e_delta = 0.0
    if "E" in params:
        if state.e_absolute:
            e_delta = params["E"] - old_e
            state.e = params["E"]
        else:
            e_delta = params["E"]
            state.e = old_e + params["E"]

    if "F" in params:
        state.feed = params["F"]
    feed = state.feed
    distance = math.sqrt(
        (target_x - old_x) ** 2 + (target_y - old_y) ** 2 + (target_z - old_z) ** 2
    )
    speed = feed / 60.0 if feed > 0 else None
    move_time = distance / speed if speed and distance > 0 else None
    expected_flow = None
    expected_e_velocity = None
    if move_time and move_time > 0:
        expected_e_velocity = e_delta / move_time
        if e_delta > 0:
            expected_flow = e_delta * filament_area / move_time

    state.x, state.y, state.z = target_x, target_y, target_z
    state.last_motion_line_number = line_number
    state.last_motion_byte_start = byte_start
    state.last_motion_byte_end = byte_end
    state.last_motion_line = text[:500]
    state.last_motion_kind = classify_motion(command, distance, e_delta)
    state.last_motion_distance_mm = distance
    state.last_motion_e_delta_mm = e_delta
    state.last_motion_time_s = move_time
    state.last_motion_expected_flow_mm3_s = expected_flow
    state.last_motion_expected_e_velocity_mm_s = expected_e_velocity
    state.last_motion_speed_mm_s = speed
    state.last_motion_start = [old_x, old_y, old_z, old_e]
    state.last_motion_end = [target_x, target_y, target_z, state.e]


def ratio_or_none(numerator: Any, denominator: Any) -> Optional[float]:
    num = safe_float(numerator)
    den = safe_float(denominator)
    if num is None or den is None or abs(den) < 1e-12:
        return None
    return num / den


def gcode_state_sample_row(
    sample: dict[str, Any],
    state: GcodeTelemetryMapState,
    *,
    gcode_input: Path,
) -> dict[str, Any]:
    telemetry_flow = safe_float(sample.get("estimated_flow_mm3_s"))
    gcode_flow = state.last_motion_expected_flow_mm3_s
    telemetry_speed = safe_float(sample.get("live_velocity_mm_s"))
    gcode_speed = state.last_motion_speed_mm_s
    telemetry_e_velocity = safe_float(sample.get("live_extruder_velocity_mm_s"))
    gcode_e_velocity = state.last_motion_expected_e_velocity_mm_s
    telemetry_pa = safe_float(sample.get("pressure_advance"))
    hall_diameter = safe_float(sample.get("hall_diameter_mm"))
    pa_delta = None
    if telemetry_pa is not None and state.pa_k is not None:
        pa_delta = telemetry_pa - state.pa_k
    flow_delta = None
    if telemetry_flow is not None and gcode_flow is not None:
        flow_delta = telemetry_flow - gcode_flow
    gcode_flow_hall = None
    if gcode_e_velocity is not None and gcode_e_velocity > 0 and hall_diameter is not None:
        gcode_flow_hall = gcode_e_velocity * math.pi * (hall_diameter / 2.0) ** 2
    flow_delta_hall = None
    if telemetry_flow is not None and gcode_flow_hall is not None:
        flow_delta_hall = telemetry_flow - gcode_flow_hall

    return {
        "sample_index": sample.get("sample_index"),
        "captured_at": sample.get("captured_at", ""),
        "telemetry_state": sample.get("state", ""),
        "filename": sample.get("filename", ""),
        "gcode_input": str(gcode_input),
        "file_position": sample.get("file_position"),
        "file_size": sample.get("file_size"),
        "mapped_line_number": state.line_number,
        "mapped_byte_start": state.byte_start,
        "mapped_byte_end": state.byte_end,
        "mapped_feature": state.feature,
        "mapped_layer_comment": state.layer,
        "mapped_reported_layer": state.reported_layer,
        "telemetry_layer": sample.get("current_layer"),
        "telemetry_total_layer": sample.get("total_layer"),
        "progress": sample.get("progress"),
        "gcode_pa_k": state.pa_k,
        "telemetry_pa_k": telemetry_pa,
        "pa_delta": pa_delta,
        "gcode_accel": state.accel,
        "last_command": state.last_command,
        "last_line": state.last_line,
        "last_motion_line_number": state.last_motion_line_number,
        "last_motion_byte_start": state.last_motion_byte_start,
        "last_motion_byte_end": state.last_motion_byte_end,
        "last_motion_kind": state.last_motion_kind,
        "last_motion_feature": state.feature,
        "last_motion_distance_mm": state.last_motion_distance_mm,
        "last_motion_e_delta_mm": state.last_motion_e_delta_mm,
        "last_motion_time_s": state.last_motion_time_s,
        "gcode_speed_mm_s": gcode_speed,
        "telemetry_live_velocity_mm_s": telemetry_speed,
        "speed_ratio_live_to_gcode": ratio_or_none(telemetry_speed, gcode_speed),
        "gcode_e_velocity_mm_s": gcode_e_velocity,
        "telemetry_live_e_velocity_mm_s": telemetry_e_velocity,
        "e_velocity_ratio_live_to_gcode": ratio_or_none(telemetry_e_velocity, gcode_e_velocity),
        "gcode_expected_flow_mm3_s": gcode_flow,
        "gcode_expected_flow_hall_mm3_s": gcode_flow_hall,
        "telemetry_estimated_flow_mm3_s": telemetry_flow,
        "flow_delta_mm3_s": flow_delta,
        "flow_ratio_telemetry_to_gcode": ratio_or_none(telemetry_flow, gcode_flow),
        "flow_delta_hall_mm3_s": flow_delta_hall,
        "flow_ratio_telemetry_to_gcode_hall": ratio_or_none(telemetry_flow, gcode_flow_hall),
        "hall_diameter_mm": hall_diameter,
        "extruder_temp_c": sample.get("extruder_temp_c"),
        "extruder_target_c": sample.get("extruder_target_c"),
        "bed_temp_c": sample.get("bed_temp_c"),
        "bed_target_c": sample.get("bed_target_c"),
        "chamber_temp_c": sample.get("chamber_temp_c"),
        "chamber_target_c": sample.get("chamber_target_c"),
        "beacon_coil_temp_c": sample.get("beacon_coil_temp_c"),
        "beacon_frequency_hz": sample.get("beacon_frequency_hz"),
        "beacon_data_smooth": sample.get("beacon_data_smooth"),
        "gcode_x": safe_list_get(state.last_motion_end, 0),
        "gcode_y": safe_list_get(state.last_motion_end, 1),
        "gcode_z": safe_list_get(state.last_motion_end, 2),
        "gcode_e": safe_list_get(state.last_motion_end, 3),
        "motion_x": sample.get("motion_x"),
        "motion_y": sample.get("motion_y"),
        "motion_z": sample.get("motion_z"),
        "motion_e": sample.get("motion_e"),
        "last_motion_line": state.last_motion_line,
    }


def numeric_summary(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for field in fields:
        values = [safe_float(row.get(field)) for row in rows]
        nums = [value for value in values if value is not None]
        if not nums:
            continue
        last_value = next(
            (safe_float(row.get(field)) for row in reversed(rows) if safe_float(row.get(field)) is not None),
            None,
        )
        result[field] = {
            "count": len(nums),
            "min": min(nums),
            "max": max(nums),
            "avg": sum(nums) / len(nums),
            "last": last_value,
        }
    return result


def summarize_gcode_telemetry_map(
    rows: list[dict[str, Any]],
    *,
    telemetry_jsonl: Path,
    gcode_input: Path,
    gcode_size: int,
) -> dict[str, Any]:
    feature_counts: dict[str, int] = {}
    motion_kind_counts: dict[str, int] = {}
    for row in rows:
        feature = str(row.get("last_motion_feature") or row.get("mapped_feature") or "unknown")
        feature_counts[feature] = feature_counts.get(feature, 0) + 1
        kind = str(row.get("last_motion_kind") or "unknown")
        motion_kind_counts[kind] = motion_kind_counts.get(kind, 0) + 1

    numeric_fields = [
        "file_position",
        "mapped_line_number",
        "progress",
        "gcode_pa_k",
        "telemetry_pa_k",
        "pa_delta",
        "gcode_accel",
        "gcode_speed_mm_s",
        "telemetry_live_velocity_mm_s",
        "speed_ratio_live_to_gcode",
        "gcode_e_velocity_mm_s",
        "telemetry_live_e_velocity_mm_s",
        "e_velocity_ratio_live_to_gcode",
        "gcode_expected_flow_mm3_s",
        "gcode_expected_flow_hall_mm3_s",
        "telemetry_estimated_flow_mm3_s",
        "flow_delta_mm3_s",
        "flow_ratio_telemetry_to_gcode",
        "flow_delta_hall_mm3_s",
        "flow_ratio_telemetry_to_gcode_hall",
        "hall_diameter_mm",
        "extruder_temp_c",
        "bed_temp_c",
        "chamber_temp_c",
        "beacon_coil_temp_c",
        "beacon_frequency_hz",
    ]
    flow_rows = [
        row
        for row in rows
        if safe_float(row.get("gcode_expected_flow_mm3_s")) is not None
    ]
    high_flow = sorted(
        flow_rows,
        key=lambda row: safe_float(row.get("gcode_expected_flow_mm3_s")) or -1.0,
        reverse=True,
    )[:10]
    mismatch_warnings: list[str] = []
    file_sizes = {
        int(value)
        for value in (
            safe_float(row.get("file_size"))
            for row in rows
            if safe_float(row.get("file_size")) is not None
        )
    }
    if file_sizes and gcode_size not in file_sizes:
        mismatch_warnings.append(
            f"Telemetry file_size values {sorted(file_sizes)} do not match local G-code size {gcode_size}."
        )

    return {
        "kind": "tinman_gcode_telemetry_map_summary",
        "version": 1,
        "captured_at": utc_timestamp(),
        "telemetry_jsonl": str(telemetry_jsonl),
        "gcode_input": str(gcode_input),
        "gcode_size": gcode_size,
        "sample_count": len(rows),
        "mapped_count": sum(1 for row in rows if row.get("mapped_line_number")),
        "feature_counts": dict(sorted(feature_counts.items(), key=lambda item: (-item[1], item[0]))),
        "motion_kind_counts": dict(sorted(motion_kind_counts.items(), key=lambda item: (-item[1], item[0]))),
        "numeric_stats": numeric_summary(rows, numeric_fields),
        "high_flow_samples": [
            {
                "sample_index": row.get("sample_index"),
                "captured_at": row.get("captured_at"),
                "file_position": row.get("file_position"),
                "line": row.get("last_motion_line_number"),
                "feature": row.get("last_motion_feature"),
                "kind": row.get("last_motion_kind"),
                "gcode_flow": row.get("gcode_expected_flow_mm3_s"),
                "gcode_flow_hall": row.get("gcode_expected_flow_hall_mm3_s"),
                "telemetry_flow": row.get("telemetry_estimated_flow_mm3_s"),
                "gcode_speed": row.get("gcode_speed_mm_s"),
                "live_speed": row.get("telemetry_live_velocity_mm_s"),
                "line_text": row.get("last_motion_line"),
            }
            for row in high_flow
        ],
        "warnings": mismatch_warnings,
        "notes": [
            "Moonraker file_position is a byte offset into the file being read, not a guaranteed nozzle-contact timestamp. Planner buffering can make exact line-to-sensor alignment lag or lead the real bead.",
            "Use this mapper for aggregate context, feature/flow distribution, and sensor-baseline work before using it for adaptive pressure advance decisions.",
            "This command is offline/read-only. It does not contact the printer unless the input files were separately downloaded by a read-only command.",
        ],
    }


def map_gcode_telemetry(args: argparse.Namespace) -> dict[str, Any]:
    gcode_input = Path(args.gcode_input)
    telemetry_jsonl = Path(args.telemetry_jsonl)
    if not gcode_input.exists():
        raise SystemExit(f"G-code input not found: {gcode_input}")
    if not telemetry_jsonl.exists():
        raise SystemExit(f"Telemetry JSONL not found: {telemetry_jsonl}")
    samples = load_jsonl(telemetry_jsonl)
    filament_area = math.pi * (args.filament_diameter / 2.0) ** 2
    state = GcodeTelemetryMapState(e_absolute=not bool(args.default_relative_e))
    rows_by_index: list[Optional[dict[str, Any]]] = [None] * len(samples)
    indexed_samples = sorted(
        enumerate(samples),
        key=lambda item: (
            int(safe_float(item[1].get("file_position")) or -1),
            int(safe_float(item[1].get("sample_index")) or item[0]),
        ),
    )
    current_offset = 0
    line_number = 0
    with gcode_input.open("rb") as handle:
        for original_index, sample in indexed_samples:
            sample_offset = int(safe_float(sample.get("file_position")) or -1)
            if sample_offset < 0:
                rows_by_index[original_index] = gcode_state_sample_row(
                    sample,
                    state,
                    gcode_input=gcode_input,
                )
                continue
            while current_offset < sample_offset:
                byte_start = current_offset
                raw_line = handle.readline()
                if not raw_line:
                    break
                current_offset = handle.tell()
                line_number += 1
                update_gcode_map_state(
                    state,
                    raw_line,
                    line_number=line_number,
                    byte_start=byte_start,
                    byte_end=current_offset,
                    filament_area=filament_area,
                )
            rows_by_index[original_index] = gcode_state_sample_row(
                sample,
                state,
                gcode_input=gcode_input,
            )

    rows = [row for row in rows_by_index if row is not None]
    if args.output_jsonl:
        out = Path(args.output_jsonl)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, sort_keys=True) + "\n")
    if args.csv:
        out_csv = Path(args.csv)
        out_csv.parent.mkdir(parents=True, exist_ok=True)
        with out_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=GCODE_TELEMETRY_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({field: row.get(field) for field in GCODE_TELEMETRY_CSV_FIELDS})

    summary = summarize_gcode_telemetry_map(
        rows,
        telemetry_jsonl=telemetry_jsonl,
        gcode_input=gcode_input,
        gcode_size=gcode_input.stat().st_size,
    )
    if args.summary:
        summary_path = Path(args.summary)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


AGGREGATE_NUMERIC_FIELDS = [
    "file_position",
    "mapped_line_number",
    "mapped_layer_comment",
    "mapped_reported_layer",
    "telemetry_layer",
    "progress",
    "gcode_pa_k",
    "telemetry_pa_k",
    "pa_delta",
    "gcode_accel",
    "gcode_speed_mm_s",
    "telemetry_live_velocity_mm_s",
    "speed_ratio_live_to_gcode",
    "gcode_e_velocity_mm_s",
    "telemetry_live_e_velocity_mm_s",
    "e_velocity_ratio_live_to_gcode",
    "gcode_expected_flow_mm3_s",
    "gcode_expected_flow_hall_mm3_s",
    "telemetry_estimated_flow_mm3_s",
    "flow_delta_mm3_s",
    "flow_ratio_telemetry_to_gcode",
    "flow_delta_hall_mm3_s",
    "flow_ratio_telemetry_to_gcode_hall",
    "hall_diameter_mm",
    "extruder_temp_c",
    "extruder_target_c",
    "bed_temp_c",
    "bed_target_c",
    "chamber_temp_c",
    "chamber_target_c",
    "beacon_coil_temp_c",
    "beacon_frequency_hz",
    "beacon_data_smooth",
]

AGGREGATE_BAND_CSV_FIELDS = [
    "group_type",
    "group_key",
    "sample_count",
    "feature",
    "motion_kind",
    "flow_band",
    "speed_band",
    "pa_band",
    "temp_band",
    "chamber_band",
    "beacon_coil_band",
    "flow_avg",
    "flow_min",
    "flow_max",
    "flow_std",
    "speed_avg",
    "speed_ratio_avg",
    "e_velocity_ratio_avg",
    "hall_diameter_avg",
    "pa_avg",
    "extruder_temp_avg",
    "chamber_temp_avg",
    "beacon_coil_avg",
    "beacon_frequency_avg",
    "alignment_score",
    "eligible_for_adaptive_modeling",
]


def load_mapped_rows(paths: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path_text in paths:
        path = Path(path_text)
        if not path.exists():
            raise SystemExit(f"mapped JSONL not found: {path}")
        for row in load_jsonl(path):
            row = dict(row)
            row.setdefault("mapped_source", str(path))
            rows.append(row)
    return rows


def finite_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values = [safe_float(row.get(field)) for row in rows]
    return [float(value) for value in values if value is not None and math.isfinite(value)]


def stats_from_values(values: list[float]) -> Optional[dict[str, Any]]:
    if not values:
        return None
    avg = sum(values) / len(values)
    variance = sum((value - avg) ** 2 for value in values) / len(values)
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": avg,
        "std": math.sqrt(variance),
        "last": values[-1],
    }


def numeric_stats_with_std(rows: list[dict[str, Any]], fields: list[str]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    for field in fields:
        result = stats_from_values(finite_values(rows, field))
        if result is not None:
            stats[field] = result
    return stats


def selected_flow_for_aggregate(row: dict[str, Any], metric: str) -> Optional[float]:
    candidates: list[str]
    if metric == "hall":
        candidates = [
            "gcode_expected_flow_hall_mm3_s",
            "telemetry_estimated_flow_mm3_s",
            "gcode_expected_flow_mm3_s",
        ]
    elif metric == "telemetry":
        candidates = [
            "telemetry_estimated_flow_mm3_s",
            "gcode_expected_flow_hall_mm3_s",
            "gcode_expected_flow_mm3_s",
        ]
    else:
        candidates = [
            "gcode_expected_flow_mm3_s",
            "gcode_expected_flow_hall_mm3_s",
            "telemetry_estimated_flow_mm3_s",
        ]
    for field in candidates:
        value = safe_float(row.get(field))
        if value is not None and math.isfinite(value):
            return value
    return None


def band_label(value: Any, size: float, suffix: str = "") -> str:
    number = safe_float(value)
    if number is None or not math.isfinite(number) or size <= 0:
        return "unknown"
    low = math.floor(number / size) * size
    high = low + size
    if size >= 1.0:
        label = f"{low:.0f}-{high:.0f}"
    elif size >= 0.1:
        label = f"{low:.1f}-{high:.1f}"
    else:
        label = f"{low:.3f}-{high:.3f}"
    return label + suffix


def add_aggregate_band_fields(row: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    enriched = dict(row)
    flow = selected_flow_for_aggregate(row, args.flow_metric)
    enriched["aggregate_flow_mm3_s"] = flow
    enriched["aggregate_feature"] = str(row.get("last_motion_feature") or row.get("mapped_feature") or "unknown")
    enriched["aggregate_motion_kind"] = str(row.get("last_motion_kind") or "unknown")
    enriched["aggregate_flow_band"] = band_label(flow, args.flow_bin_size, " mm3/s")
    enriched["aggregate_speed_band"] = band_label(row.get("gcode_speed_mm_s"), args.speed_bin_size, " mm/s")
    enriched["aggregate_pa_band"] = band_label(row.get("gcode_pa_k"), args.pa_bin_size, " K")
    enriched["aggregate_temp_band"] = band_label(row.get("extruder_temp_c"), args.temp_bin_size, " C")
    enriched["aggregate_chamber_band"] = band_label(row.get("chamber_temp_c"), args.temp_bin_size, " C")
    enriched["aggregate_beacon_coil_band"] = band_label(row.get("beacon_coil_temp_c"), args.beacon_bin_size, " C")
    enriched["aggregate_layer_band"] = band_label(
        row.get("mapped_reported_layer") if row.get("mapped_reported_layer") is not None else row.get("telemetry_layer"),
        args.layer_bin_size,
        " layer",
    )
    return enriched


def filter_aggregate_rows(rows: list[dict[str, Any]], args: argparse.Namespace) -> tuple[list[dict[str, Any]], dict[str, int]]:
    included: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    include_features = parse_feature_set(args.include_features, set())
    exclude_features = parse_feature_set(args.exclude_features, set())
    for row in rows:
        enriched = add_aggregate_band_fields(row, args)
        feature = enriched["aggregate_feature"]
        motion = enriched["aggregate_motion_kind"]
        if args.motion_filter != "all" and motion != args.motion_filter:
            excluded[f"motion:{motion}"] = excluded.get(f"motion:{motion}", 0) + 1
            continue
        if include_features and feature not in include_features:
            excluded[f"feature_not_included:{feature}"] = excluded.get(f"feature_not_included:{feature}", 0) + 1
            continue
        if exclude_features and feature in exclude_features:
            excluded[f"feature_excluded:{feature}"] = excluded.get(f"feature_excluded:{feature}", 0) + 1
            continue
        if args.require_flow and enriched.get("aggregate_flow_mm3_s") is None:
            excluded["missing_flow"] = excluded.get("missing_flow", 0) + 1
            continue
        if args.require_telemetry_alignment:
            flow_ratio = safe_float(enriched.get("flow_ratio_telemetry_to_gcode_hall"))
            e_ratio = safe_float(enriched.get("e_velocity_ratio_live_to_gcode"))
            if flow_ratio is None:
                excluded["missing_hall_flow_ratio"] = excluded.get("missing_hall_flow_ratio", 0) + 1
                continue
            if flow_ratio < args.min_flow_ratio_hall:
                excluded["low_hall_flow_ratio"] = excluded.get("low_hall_flow_ratio", 0) + 1
                continue
            if flow_ratio > args.max_flow_ratio_hall:
                excluded["high_hall_flow_ratio"] = excluded.get("high_hall_flow_ratio", 0) + 1
                continue
            if e_ratio is None:
                excluded["missing_e_velocity_ratio"] = excluded.get("missing_e_velocity_ratio", 0) + 1
                continue
            if e_ratio < args.min_e_velocity_ratio:
                excluded["low_e_velocity_ratio"] = excluded.get("low_e_velocity_ratio", 0) + 1
                continue
            if e_ratio > args.max_e_velocity_ratio:
                excluded["high_e_velocity_ratio"] = excluded.get("high_e_velocity_ratio", 0) + 1
                continue
        included.append(enriched)
    return included, excluded


def group_rows(rows: list[dict[str, Any]], fields: list[str]) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = tuple(row.get(field, "unknown") for field in fields)
        grouped.setdefault(key, []).append(row)
    return grouped


def aggregate_alignment_score(stats: dict[str, dict[str, Any]]) -> Optional[float]:
    parts: list[float] = []
    for field in ("speed_ratio_live_to_gcode", "e_velocity_ratio_live_to_gcode", "flow_ratio_telemetry_to_gcode_hall"):
        avg = nested_get(stats, f"{field}.avg")
        std = nested_get(stats, f"{field}.std")
        avg_f = safe_float(avg)
        std_f = safe_float(std) or 0.0
        if avg_f is None:
            continue
        parts.append(max(0.0, 1.0 - abs(avg_f - 1.0) - std_f))
    if not parts:
        return None
    return sum(parts) / len(parts)


def summarize_aggregate_group(
    group_type: str,
    key_fields: list[str],
    key: tuple[Any, ...],
    rows: list[dict[str, Any]],
    *,
    min_samples: int,
) -> dict[str, Any]:
    stats = numeric_stats_with_std(rows, AGGREGATE_NUMERIC_FIELDS + ["aggregate_flow_mm3_s"])
    alignment = aggregate_alignment_score(stats)
    row = {
        "group_type": group_type,
        "group_key": " | ".join(str(part) for part in key),
        "sample_count": len(rows),
        "key": dict(zip(key_fields, key)),
        "first_captured_at": rows[0].get("captured_at", ""),
        "last_captured_at": rows[-1].get("captured_at", ""),
        "numeric_stats": stats,
        "alignment_score": alignment,
        "eligible_for_adaptive_modeling": bool(
            len(rows) >= min_samples
            and (alignment is None or alignment >= 0.94)
            and nested_get(stats, "aggregate_flow_mm3_s.count")
        ),
    }
    examples = sorted(
        rows,
        key=lambda item: safe_float(item.get("aggregate_flow_mm3_s")) or -1.0,
        reverse=True,
    )[:3]
    row["example_samples"] = [
        {
            "sample_index": item.get("sample_index"),
            "captured_at": item.get("captured_at"),
            "line": item.get("last_motion_line_number"),
            "feature": item.get("aggregate_feature"),
            "flow": item.get("aggregate_flow_mm3_s"),
            "speed": item.get("gcode_speed_mm_s"),
            "pa": item.get("gcode_pa_k"),
            "line_text": item.get("last_motion_line"),
        }
        for item in examples
    ]
    return row


def flatten_aggregate_group_for_csv(group: dict[str, Any]) -> dict[str, Any]:
    stats = group.get("numeric_stats", {})
    key = group.get("key", {}) if isinstance(group.get("key"), dict) else {}

    def avg(field: str) -> Any:
        return nested_get(stats, f"{field}.avg")

    def minv(field: str) -> Any:
        return nested_get(stats, f"{field}.min")

    def maxv(field: str) -> Any:
        return nested_get(stats, f"{field}.max")

    def std(field: str) -> Any:
        return nested_get(stats, f"{field}.std")

    return {
        "group_type": group.get("group_type"),
        "group_key": group.get("group_key"),
        "sample_count": group.get("sample_count"),
        "feature": key.get("aggregate_feature", ""),
        "motion_kind": key.get("aggregate_motion_kind", ""),
        "flow_band": key.get("aggregate_flow_band", ""),
        "speed_band": key.get("aggregate_speed_band", ""),
        "pa_band": key.get("aggregate_pa_band", ""),
        "temp_band": key.get("aggregate_temp_band", ""),
        "chamber_band": key.get("aggregate_chamber_band", ""),
        "beacon_coil_band": key.get("aggregate_beacon_coil_band", ""),
        "flow_avg": avg("aggregate_flow_mm3_s"),
        "flow_min": minv("aggregate_flow_mm3_s"),
        "flow_max": maxv("aggregate_flow_mm3_s"),
        "flow_std": std("aggregate_flow_mm3_s"),
        "speed_avg": avg("gcode_speed_mm_s"),
        "speed_ratio_avg": avg("speed_ratio_live_to_gcode"),
        "e_velocity_ratio_avg": avg("e_velocity_ratio_live_to_gcode"),
        "hall_diameter_avg": avg("hall_diameter_mm"),
        "pa_avg": avg("gcode_pa_k"),
        "extruder_temp_avg": avg("extruder_temp_c"),
        "chamber_temp_avg": avg("chamber_temp_c"),
        "beacon_coil_avg": avg("beacon_coil_temp_c"),
        "beacon_frequency_avg": avg("beacon_frequency_hz"),
        "alignment_score": group.get("alignment_score"),
        "eligible_for_adaptive_modeling": group.get("eligible_for_adaptive_modeling"),
    }


def top_groups(groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    return sorted(
        groups,
        key=lambda group: (
            int(group.get("sample_count") or 0),
            safe_float(nested_get(group, "numeric_stats.aggregate_flow_mm3_s.avg")) or -1.0,
        ),
        reverse=True,
    )[:limit]


def adaptive_pa_input_summary(rows: list[dict[str, Any]], groups: dict[str, list[dict[str, Any]]], args: argparse.Namespace) -> dict[str, Any]:
    stats = numeric_stats_with_std(rows, AGGREGATE_NUMERIC_FIELDS + ["aggregate_flow_mm3_s"])
    pa_values = sorted({round(value, 6) for value in finite_values(rows, "gcode_pa_k")})
    eligible_bands = [
        group
        for group in groups.get("feature_flow_speed", [])
        if group.get("eligible_for_adaptive_modeling")
    ]
    schedule_candidates: list[dict[str, Any]] = []
    for group in top_groups(eligible_bands, args.top_groups):
        key = group.get("key", {}) if isinstance(group.get("key"), dict) else {}
        group_stats = group.get("numeric_stats", {})
        schedule_candidates.append(
            {
                "feature": key.get("aggregate_feature"),
                "flow_band": key.get("aggregate_flow_band"),
                "speed_band": key.get("aggregate_speed_band"),
                "sample_count": group.get("sample_count"),
                "current_pa_k": nested_get(group_stats, "gcode_pa_k.avg"),
                "flow_mm3_s": nested_get(group_stats, "aggregate_flow_mm3_s.avg"),
                "speed_mm_s": nested_get(group_stats, "gcode_speed_mm_s.avg"),
                "extruder_temp_c": nested_get(group_stats, "extruder_temp_c.avg"),
                "hall_diameter_mm": nested_get(group_stats, "hall_diameter_mm.avg"),
                "alignment_score": group.get("alignment_score"),
                "pa_update_status": "hold_current_pa_until_controlled_coupon_scores_this_band",
            }
        )
    return {
        "flow_metric": args.flow_metric,
        "pa_values_seen": pa_values,
        "fixed_pa_observed": len(pa_values) <= 1,
        "overall_numeric_stats": stats,
        "candidate_schedule_inputs": schedule_candidates,
        "ready_to_change_pa": False,
        "why_not_ready": [
            "Passive model-print telemetry confirms slicer/sensor alignment but does not measure corner bulge or post-corner underfill.",
            "Adaptive PA changes require controlled PA coupons or a scored in-print calibration feature for each useful flow/speed/material/temperature band.",
        ],
        "next_measurements_needed": [
            "Controlled PA coupon at low, medium, and high Hall-normalized flow bands.",
            "Beacon or camera evidence around acceleration/deceleration features, not just steady wall/infill extrusion.",
            "Longer passive capture across infill, wall, bridge, top-surface, and speed transitions to populate more bands.",
        ],
    }


def aggregate_gcode_telemetry(args: argparse.Namespace) -> dict[str, Any]:
    raw_rows = load_mapped_rows(args.mapped_jsonl)
    rows, excluded = filter_aggregate_rows(raw_rows, args)
    group_specs = {
        "feature": ["aggregate_feature"],
        "motion_kind": ["aggregate_motion_kind"],
        "flow_band": ["aggregate_flow_band"],
        "speed_band": ["aggregate_speed_band"],
        "pa_band": ["aggregate_pa_band"],
        "feature_flow": ["aggregate_feature", "aggregate_flow_band"],
        "feature_speed": ["aggregate_feature", "aggregate_speed_band"],
        "feature_flow_speed": ["aggregate_feature", "aggregate_flow_band", "aggregate_speed_band"],
        "feature_flow_temp": ["aggregate_feature", "aggregate_flow_band", "aggregate_temp_band"],
        "feature_flow_beacon": ["aggregate_feature", "aggregate_flow_band", "aggregate_beacon_coil_band"],
        "layer_feature_flow": ["aggregate_layer_band", "aggregate_feature", "aggregate_flow_band"],
    }
    grouped: dict[str, list[dict[str, Any]]] = {}
    for name, fields in group_specs.items():
        summaries = [
            summarize_aggregate_group(
                name,
                fields,
                key,
                group_rows_list,
                min_samples=args.min_samples_per_band,
            )
            for key, group_rows_list in group_rows(rows, fields).items()
        ]
        grouped[name] = top_groups(summaries, args.max_groups_per_table)

    result = {
        "kind": "tinman_gcode_telemetry_aggregate",
        "version": 1,
        "captured_at": utc_timestamp(),
        "mapped_jsonl": args.mapped_jsonl,
        "raw_sample_count": len(raw_rows),
        "included_sample_count": len(rows),
        "excluded_sample_count": len(raw_rows) - len(rows),
        "excluded_reasons": dict(sorted(excluded.items())),
        "settings": {
            "flow_metric": args.flow_metric,
            "motion_filter": args.motion_filter,
            "flow_bin_size": args.flow_bin_size,
            "speed_bin_size": args.speed_bin_size,
            "pa_bin_size": args.pa_bin_size,
            "temp_bin_size": args.temp_bin_size,
            "beacon_bin_size": args.beacon_bin_size,
            "layer_bin_size": args.layer_bin_size,
            "min_samples_per_band": args.min_samples_per_band,
            "require_telemetry_alignment": args.require_telemetry_alignment,
            "min_flow_ratio_hall": args.min_flow_ratio_hall,
            "max_flow_ratio_hall": args.max_flow_ratio_hall,
            "min_e_velocity_ratio": args.min_e_velocity_ratio,
            "max_e_velocity_ratio": args.max_e_velocity_ratio,
        },
        "overall": {
            "numeric_stats": numeric_stats_with_std(rows, AGGREGATE_NUMERIC_FIELDS + ["aggregate_flow_mm3_s"]),
            "feature_counts": dict(sorted(
                {
                    feature: sum(1 for row in rows if row.get("aggregate_feature") == feature)
                    for feature in {row.get("aggregate_feature") for row in rows}
                }.items(),
                key=lambda item: (-item[1], str(item[0])),
            )),
        },
        "groups": grouped,
        "adaptive_pa_inputs": adaptive_pa_input_summary(rows, grouped, args),
        "notes": [
            "Default aggregation includes only XY extrusion rows so travel/planner context does not drive PA bands.",
            "Hall flow uses gcode E velocity multiplied by the live Hall diameter cross-section. This is the preferred Qidi flow metric when the Hall sensor is active.",
            "This report proposes adaptive-PA input bands only; it does not compute new PA values from passive model-print telemetry.",
        ],
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2) + "\n")
    if args.bands_csv:
        csv_path = Path(args.bands_csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=AGGREGATE_BAND_CSV_FIELDS, extrasaction="ignore")
            writer.writeheader()
            for table_name in ("feature", "flow_band", "feature_flow", "feature_flow_speed", "feature_flow_temp", "layer_feature_flow"):
                for group in grouped.get(table_name, []):
                    writer.writerow(flatten_aggregate_group_for_csv(group))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="TinManX1 auto pressure advance toolkit")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_inv = sub.add_parser("inventory", help="Inventory TinManX1 machine families")
    p_inv.add_argument("--root", default=str(TINMAN_ROOT))
    p_inv.add_argument("--user", default=ACTIVE_USER)

    p_prusa_profiles = sub.add_parser("prusa-profiles", help="List Prusa Core One TinManX1 profiles with credentials redacted")
    p_prusa_profiles.add_argument("--root", default=str(TINMAN_ROOT))
    p_prusa_profiles.add_argument("--user-store", default=ACTIVE_USER)
    p_prusa_profiles.add_argument("--host", default="")

    p_prusa_probe = sub.add_parser("prusa-probe", help="Read-only PrusaLink probe using TinManX1 credentials when available")
    p_prusa_probe.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_probe.add_argument("--root", default=str(TINMAN_ROOT))
    p_prusa_probe.add_argument("--user-store", default=ACTIVE_USER)
    p_prusa_probe.add_argument("--api-key", default="")
    p_prusa_probe.add_argument("--password", default="")
    p_prusa_probe.add_argument("--prusa-user", default="maker")
    p_prusa_probe.add_argument("--timeout", type=float, default=5.0)

    p_prusa_sweep = sub.add_parser("prusa-sweep", help="Generate CNC Kitchen/PrusaPATuner-style free-air PA sweep G-code")
    p_prusa_sweep.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_sweep.add_argument("--output", required=True)
    p_prusa_sweep.add_argument("--plan", help="write sweep timing plan JSON")
    p_prusa_sweep.add_argument("--udp-host", default="", help="host IP the printer should stream UDP metrics to; auto-detected by default")
    p_prusa_sweep.add_argument("--udp-port", type=int, default=8514)
    p_prusa_sweep.add_argument("--prusa-user", default="maker")
    p_prusa_sweep.add_argument("--nozzle-temp", type=float, default=215.0)
    p_prusa_sweep.add_argument("--preheat-temp", type=float, default=225.0)
    p_prusa_sweep.add_argument("--nozzle-diameter", type=float, default=0.4)
    p_prusa_sweep.add_argument("--filament-diameter", type=float, default=1.75)
    p_prusa_sweep.add_argument("--filament-label", default="PLA")
    p_prusa_sweep.add_argument("--slow-flow", type=float, default=3.0, help="slow leg volumetric flow in mm^3/s")
    p_prusa_sweep.add_argument("--fast-flow", type=float, default=14.0, help="fast leg volumetric flow in mm^3/s")
    p_prusa_sweep.add_argument("--slow-volume", type=float, default=6.0, help="slow leg volume in mm^3")
    p_prusa_sweep.add_argument("--fast-volume", type=float, default=10.0, help="fast leg volume in mm^3")
    p_prusa_sweep.add_argument("--cycles", type=int, default=4)
    p_prusa_sweep.add_argument("--accel", type=float, default=500.0)
    p_prusa_sweep.add_argument("--k-min", type=float, default=0.0)
    p_prusa_sweep.add_argument("--k-max", type=float, default=0.05)
    p_prusa_sweep.add_argument("--k-step", type=float, default=0.005)
    p_prusa_sweep.add_argument("--purge-x", type=float, default=30.0)
    p_prusa_sweep.add_argument("--purge-y", type=float, default=30.0)
    p_prusa_sweep.add_argument("--purge-z", type=float, default=80.0)
    p_prusa_sweep.add_argument("--coupled-dx", type=float, default=1.0)
    p_prusa_sweep.add_argument("--coupled-dy", type=float, default=0.0)
    p_prusa_sweep.add_argument("--coupled-dz", type=float, default=0.0)
    p_prusa_sweep.add_argument("--first-slow-leg-factor", type=float, default=5.0)

    p_prusa_sim = sub.add_parser("prusa-simulate", help="Run offline synthetic loadcell validation against the Prusa analyzer")
    p_prusa_sim.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_sim.add_argument("--output", help="write simulation summary JSON")
    p_prusa_sim.add_argument("--raw-npz", help="write synthetic raw force data")
    p_prusa_sim.add_argument("--udp-host", default="127.0.0.1")
    p_prusa_sim.add_argument("--udp-port", type=int, default=8514)
    p_prusa_sim.add_argument("--prusa-user", default="maker")
    p_prusa_sim.add_argument("--nozzle-temp", type=float, default=215.0)
    p_prusa_sim.add_argument("--preheat-temp", type=float, default=225.0)
    p_prusa_sim.add_argument("--nozzle-diameter", type=float, default=0.4)
    p_prusa_sim.add_argument("--filament-diameter", type=float, default=1.75)
    p_prusa_sim.add_argument("--filament-label", default="PLA")
    p_prusa_sim.add_argument("--slow-flow", type=float, default=3.0)
    p_prusa_sim.add_argument("--fast-flow", type=float, default=14.0)
    p_prusa_sim.add_argument("--slow-volume", type=float, default=6.0)
    p_prusa_sim.add_argument("--fast-volume", type=float, default=10.0)
    p_prusa_sim.add_argument("--cycles", type=int, default=6)
    p_prusa_sim.add_argument("--accel", type=float, default=5000.0)
    p_prusa_sim.add_argument("--k-min", type=float, default=0.0)
    p_prusa_sim.add_argument("--k-max", type=float, default=0.06)
    p_prusa_sim.add_argument("--k-step", type=float, default=0.005)
    p_prusa_sim.add_argument("--purge-x", type=float, default=30.0)
    p_prusa_sim.add_argument("--purge-y", type=float, default=30.0)
    p_prusa_sim.add_argument("--purge-z", type=float, default=80.0)
    p_prusa_sim.add_argument("--coupled-dx", type=float, default=1.0)
    p_prusa_sim.add_argument("--coupled-dy", type=float, default=0.0)
    p_prusa_sim.add_argument("--coupled-dz", type=float, default=0.0)
    p_prusa_sim.add_argument("--first-slow-leg-factor", type=float, default=5.0)
    p_prusa_sim.add_argument("--planted-k", type=float, default=0.040)
    p_prusa_sim.add_argument("--tolerance", type=float, default=0.010)
    p_prusa_sim.add_argument("--sample-rate", type=float, default=200.0)
    p_prusa_sim.add_argument("--noise", type=float, default=3.0)
    p_prusa_sim.add_argument("--seed", type=int, default=42)
    p_prusa_sim.add_argument("--baseline-force", type=float, default=100.0)
    p_prusa_sim.add_argument("--high-force", type=float, default=1100.0)
    p_prusa_sim.add_argument("--overshoot-gain", type=float, default=8000.0)
    p_prusa_sim.add_argument("--undershoot-gain", type=float, default=9000.0)
    p_prusa_sim.add_argument("--rise-delay-s", type=float, default=0.030)
    p_prusa_sim.add_argument("--fall-delay-s", type=float, default=0.040)
    p_prusa_sim.add_argument("--rise-tau-s", type=float, default=0.040)
    p_prusa_sim.add_argument("--fall-tau-s", type=float, default=0.100)

    p_prusa_maxflow = sub.add_parser("prusa-maxflow-sweep", help="Generate a Prusa Core One loadcell max-flow sweep G-code")
    p_prusa_maxflow.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_maxflow.add_argument("--output", required=True)
    p_prusa_maxflow.add_argument("--plan", help="write flow timing plan JSON")
    p_prusa_maxflow.add_argument("--udp-host", default="", help="host IP the printer should stream UDP metrics to; auto-detected by default")
    p_prusa_maxflow.add_argument("--udp-port", type=int, default=8514)
    p_prusa_maxflow.add_argument("--prusa-user", default="maker")
    p_prusa_maxflow.add_argument("--nozzle-temp", type=float, default=215.0)
    p_prusa_maxflow.add_argument("--preheat-temp", type=float, default=225.0)
    p_prusa_maxflow.add_argument("--nozzle-diameter", type=float, default=0.4)
    p_prusa_maxflow.add_argument("--filament-diameter", type=float, default=1.75)
    p_prusa_maxflow.add_argument("--filament-label", default="PLA")
    p_prusa_maxflow.add_argument("--flow-min", type=float, default=5.0)
    p_prusa_maxflow.add_argument("--flow-max", type=float, default=30.0)
    p_prusa_maxflow.add_argument("--flow-step", type=float, default=1.0)
    p_prusa_maxflow.add_argument("--flow-dwell", type=float, default=3.0)
    p_prusa_maxflow.add_argument("--flow-settle-frac", type=float, default=0.5)
    p_prusa_maxflow.add_argument("--flow-warmup", type=float, default=3.0)
    p_prusa_maxflow.add_argument("--flow-tare-dwell", type=float, default=1.5)
    p_prusa_maxflow.add_argument("--accel", type=float, default=5000.0)
    p_prusa_maxflow.add_argument("--purge-x", type=float, default=30.0)
    p_prusa_maxflow.add_argument("--purge-y", type=float, default=30.0)
    p_prusa_maxflow.add_argument("--purge-z", type=float, default=80.0)
    p_prusa_maxflow.add_argument("--baseline-dwell", type=float, default=2.0)
    p_prusa_maxflow.add_argument("--z-marker-lift", type=float, default=2.0)

    p_prusa_maxflow_sim = sub.add_parser("prusa-maxflow-simulate", help="Run offline synthetic Prusa loadcell max-flow validation")
    p_prusa_maxflow_sim.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_maxflow_sim.add_argument("--output", help="write max-flow score JSON")
    p_prusa_maxflow_sim.add_argument("--raw-npz", help="write synthetic raw force data")
    p_prusa_maxflow_sim.add_argument("--udp-host", default="127.0.0.1")
    p_prusa_maxflow_sim.add_argument("--udp-port", type=int, default=8514)
    p_prusa_maxflow_sim.add_argument("--prusa-user", default="maker")
    p_prusa_maxflow_sim.add_argument("--nozzle-temp", type=float, default=215.0)
    p_prusa_maxflow_sim.add_argument("--preheat-temp", type=float, default=225.0)
    p_prusa_maxflow_sim.add_argument("--nozzle-diameter", type=float, default=0.4)
    p_prusa_maxflow_sim.add_argument("--filament-diameter", type=float, default=1.75)
    p_prusa_maxflow_sim.add_argument("--filament-label", default="PLA")
    p_prusa_maxflow_sim.add_argument("--flow-min", type=float, default=5.0)
    p_prusa_maxflow_sim.add_argument("--flow-max", type=float, default=30.0)
    p_prusa_maxflow_sim.add_argument("--flow-step", type=float, default=1.0)
    p_prusa_maxflow_sim.add_argument("--flow-dwell", type=float, default=3.0)
    p_prusa_maxflow_sim.add_argument("--flow-settle-frac", type=float, default=0.5)
    p_prusa_maxflow_sim.add_argument("--flow-warmup", type=float, default=3.0)
    p_prusa_maxflow_sim.add_argument("--flow-tare-dwell", type=float, default=1.5)
    p_prusa_maxflow_sim.add_argument("--accel", type=float, default=5000.0)
    p_prusa_maxflow_sim.add_argument("--purge-x", type=float, default=30.0)
    p_prusa_maxflow_sim.add_argument("--purge-y", type=float, default=30.0)
    p_prusa_maxflow_sim.add_argument("--purge-z", type=float, default=80.0)
    p_prusa_maxflow_sim.add_argument("--baseline-dwell", type=float, default=2.0)
    p_prusa_maxflow_sim.add_argument("--z-marker-lift", type=float, default=2.0)
    p_prusa_maxflow_sim.add_argument("--soft-break-flow", type=float, default=24.0)
    p_prusa_maxflow_sim.add_argument("--variance-flow", type=float, default=23.0)
    p_prusa_maxflow_sim.add_argument("--collapse-flow", type=float, default=28.0)
    p_prusa_maxflow_sim.add_argument("--derate-frac", type=float, default=0.15)
    p_prusa_maxflow_sim.add_argument("--n-sigma", type=float, default=4.0)
    p_prusa_maxflow_sim.add_argument("--var-factor", type=float, default=3.0)
    p_prusa_maxflow_sim.add_argument("--collapse-frac", type=float, default=0.15)
    p_prusa_maxflow_sim.add_argument("--sample-rate", type=float, default=180.0)
    p_prusa_maxflow_sim.add_argument("--seed", type=int, default=7)
    p_prusa_maxflow_sim.add_argument("--heat-s", type=float, default=35.0)
    p_prusa_maxflow_sim.add_argument("--tail-s", type=float, default=15.0)
    p_prusa_maxflow_sim.add_argument("--static-force", type=float, default=1500.0)
    p_prusa_maxflow_sim.add_argument("--force-a", type=float, default=3.0)
    p_prusa_maxflow_sim.add_argument("--force-b", type=float, default=0.55)
    p_prusa_maxflow_sim.add_argument("--force-c", type=float, default=4.0)
    p_prusa_maxflow_sim.add_argument("--deviation-gain", type=float, default=0.8)
    p_prusa_maxflow_sim.add_argument("--variance-gain", type=float, default=1.5)
    p_prusa_maxflow_sim.add_argument("--collapse-ratio", type=float, default=0.55)
    p_prusa_maxflow_sim.add_argument("--idle-noise", type=float, default=2.0)
    p_prusa_maxflow_sim.add_argument("--flow-noise", type=float, default=0.3)
    p_prusa_maxflow_sim.add_argument("--rise-time-s", type=float, default=0.15)
    p_prusa_maxflow_sim.add_argument("--homing-spike", type=float, default=8000.0)
    p_prusa_maxflow_sim.add_argument("--include-pos-z", action=argparse.BooleanOptionalAction, default=True)

    p_prusa_maxflow_score = sub.add_parser("prusa-maxflow-score", help="Score a saved Prusa loadcell max-flow NPZ capture")
    p_prusa_maxflow_score.add_argument("--input-npz", required=True)
    p_prusa_maxflow_score.add_argument("--output", help="write max-flow score JSON")
    p_prusa_maxflow_score.add_argument("--derate-frac", type=float, default=0.15)
    p_prusa_maxflow_score.add_argument("--n-sigma", type=float, default=4.0)
    p_prusa_maxflow_score.add_argument("--var-factor", type=float, default=3.0)
    p_prusa_maxflow_score.add_argument("--collapse-frac", type=float, default=0.15)

    p_prusa_apply = sub.add_parser("prusa-apply-pa", help="Dry-run or execute a Prusa M572 pressure advance update")
    p_prusa_apply.add_argument("k", type=float)
    p_prusa_apply.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_apply.add_argument("--root", default=str(TINMAN_ROOT))
    p_prusa_apply.add_argument("--user-store", default=ACTIVE_USER)
    p_prusa_apply.add_argument("--api-key", default="")
    p_prusa_apply.add_argument("--password", default="")
    p_prusa_apply.add_argument("--prusa-user", default="maker")
    p_prusa_apply.add_argument("--execute", action="store_true")
    p_prusa_apply.add_argument("--allow-printing", action="store_true")
    p_prusa_apply.add_argument("--timeout", type=float, default=5.0)

    p_prusa_metrics = sub.add_parser("prusa-enable-metrics", help="Dry-run or enable Prusa UDP metrics needed by the loadcell adapter")
    p_prusa_metrics.add_argument("--host", default=DEFAULT_PRUSA_HOST)
    p_prusa_metrics.add_argument("--root", default=str(TINMAN_ROOT))
    p_prusa_metrics.add_argument("--user-store", default=ACTIVE_USER)
    p_prusa_metrics.add_argument("--api-key", default="")
    p_prusa_metrics.add_argument("--password", default="")
    p_prusa_metrics.add_argument("--prusa-user", default="maker")
    p_prusa_metrics.add_argument("--udp-host", default="")
    p_prusa_metrics.add_argument("--udp-port", type=int, default=8514)
    p_prusa_metrics.add_argument("--execute", action="store_true")
    p_prusa_metrics.add_argument("--timeout", type=float, default=5.0)

    p_qidi_telemetry = sub.add_parser("qidi-telemetry", help="Capture read-only Qidi Plus 4 telemetry for auto PA")
    p_qidi_telemetry.add_argument("--host", default=DEFAULT_QIDI_HOST)
    p_qidi_telemetry.add_argument("--output", help="write telemetry JSON")
    p_qidi_telemetry.add_argument("--timeout", type=float, default=5.0)

    p_qidi_monitor = sub.add_parser("qidi-monitor-readonly", help="Poll read-only Qidi Plus 4 telemetry during a print")
    p_qidi_monitor.add_argument("--host", default=DEFAULT_QIDI_HOST)
    p_qidi_monitor.add_argument("--duration", type=float, default=60.0, help="capture duration in seconds; 0 captures one sample")
    p_qidi_monitor.add_argument("--interval", type=float, default=2.0, help="poll interval in seconds")
    p_qidi_monitor.add_argument("--jsonl", help="write flattened samples as JSON Lines")
    p_qidi_monitor.add_argument("--csv", help="write flattened samples as CSV")
    p_qidi_monitor.add_argument("--summary", help="write summary JSON")
    p_qidi_monitor.add_argument("--include-raw-status", action="store_true", help="include full raw Moonraker object status in JSONL")
    p_qidi_monitor.add_argument("--timeout", type=float, default=5.0)

    p_qidi_download = sub.add_parser("qidi-download-active-gcode", help="Download the active Qidi G-code file with read-only Moonraker GET")
    p_qidi_download.add_argument("--host", default=DEFAULT_QIDI_HOST)
    p_qidi_download.add_argument("--filename", default="", help="override active filename; default reads print_stats.filename")
    p_qidi_download.add_argument("--output", required=True)
    p_qidi_download.add_argument("--metadata-output", help="write download metadata JSON")
    p_qidi_download.add_argument("--timeout", type=float, default=30.0)

    p_qidi_coupon = sub.add_parser("qidi-coupon", help="Generate a Qidi Plus 4 stock-camera/Hall-width PA coupon")
    p_qidi_coupon.add_argument("--host", default=DEFAULT_QIDI_HOST)
    p_qidi_coupon.add_argument("--output", required=True)
    p_qidi_coupon.add_argument("--manifest", required=True)
    p_qidi_coupon.add_argument("--homography-template", help="write camera homography template JSON")
    p_qidi_coupon.add_argument("--beacon-plan", help="write dry-run Beacon contact probe plan JSON")
    p_qidi_coupon.add_argument("--use-live-k", action="store_true", help="read current Qidi pressure_advance and center the sweep on it")
    p_qidi_coupon.add_argument("--timeout", type=float, default=5.0)
    p_qidi_coupon.add_argument("--k-center", type=float, default=0.032)
    p_qidi_coupon.add_argument("--k-half-span", type=float, default=0.018)
    p_qidi_coupon.add_argument("--k-min", type=float, default=0.0)
    p_qidi_coupon.add_argument("--k-max", type=float, default=0.12)
    p_qidi_coupon.add_argument("--steps", type=int, default=7)
    p_qidi_coupon.add_argument("--layout", default="stacked", choices=["stacked", "front-edge", "rear-edge"])
    p_qidi_coupon.add_argument("--bed-x", type=float, default=300.0)
    p_qidi_coupon.add_argument("--bed-y", type=float, default=300.0)
    p_qidi_coupon.add_argument("--edge-band-width", type=float, default=20.0)
    p_qidi_coupon.add_argument("--x", type=float, default=18.0)
    p_qidi_coupon.add_argument("--y", type=float, default=18.0)
    p_qidi_coupon.add_argument("--z", type=float, default=0.24)
    p_qidi_coupon.add_argument("--length", type=float, default=64.0)
    p_qidi_coupon.add_argument("--corner-leg", type=float, default=14.0)
    p_qidi_coupon.add_argument("--spacing", type=float, default=18.0)
    p_qidi_coupon.add_argument("--speed", type=float, default=140.0)
    p_qidi_coupon.add_argument("--travel-speed", type=float, default=250.0)
    p_qidi_coupon.add_argument("--accel", type=float, default=5000.0)
    p_qidi_coupon.add_argument("--line-width", type=float, default=0.48)
    p_qidi_coupon.add_argument("--layer-height", type=float, default=0.24)
    p_qidi_coupon.add_argument("--filament-diameter", type=float, default=1.75)
    p_qidi_coupon.add_argument("--flow-ratio", type=float, default=1.0)
    p_qidi_coupon.add_argument("--retract", type=float, default=0.4)
    p_qidi_coupon.add_argument("--z-hop", type=float, default=0.35)
    p_qidi_coupon.add_argument("--enable-hall", action=argparse.BooleanOptionalAction, default=True)
    p_qidi_coupon.add_argument("--homography-margin", type=float, default=5.0)
    p_qidi_coupon.add_argument("--beacon-safe-z", type=float, default=2.0)
    p_qidi_coupon.add_argument("--beacon-sample-offset", type=float, default=3.0)

    p_qidi_score = sub.add_parser("qidi-score-coupon", help="Score a Qidi coupon and attach Hall-width selection context")
    p_qidi_score.add_argument("--image", required=True)
    p_qidi_score.add_argument("--manifest", required=True)
    p_qidi_score.add_argument("--homography", required=True)
    p_qidi_score.add_argument("--debug-image")
    p_qidi_score.add_argument("--output", help="write score JSON")
    p_qidi_score.add_argument("--host", default="", help="optional Qidi host for live Hall-width context")
    p_qidi_score.add_argument("--telemetry", help="optional saved qidi-telemetry JSON")
    p_qidi_score.add_argument("--timeout", type=float, default=5.0)
    p_qidi_score.add_argument("--scale", type=float, default=8.0)
    p_qidi_score.add_argument("--margin", type=float, default=5.0)
    p_qidi_score.add_argument("--band-mm", type=float, default=3.0)
    p_qidi_score.add_argument("--sample-inset", type=float, default=5.0)
    p_qidi_score.add_argument("--sample-step-mm", type=float, default=2.0)
    p_qidi_score.add_argument("--corner-score-mm", type=float, default=7.0)
    p_qidi_score.add_argument("--min-confidence", type=float, default=0.35)
    p_qidi_score.add_argument("--max-width-cv", type=float, default=0.30)
    p_qidi_score.add_argument("--max-score", type=float, default=2.2)
    p_qidi_score.add_argument("--max-hall-area-delta", type=float, default=0.12)

    p_qidi_apply = sub.add_parser("qidi-apply-pa", help="Dry-run or execute Qidi M900 K pressure advance update")
    p_qidi_apply.add_argument("k", type=float)
    p_qidi_apply.add_argument("--host", default=DEFAULT_QIDI_HOST)
    p_qidi_apply.add_argument("--execute", action="store_true")
    p_qidi_apply.add_argument("--allow-printing", action="store_true")

    p_cv_coupon = sub.add_parser("klipper-cv-coupon", help="Generate a generic Klipper camera/Beacon PA coupon")
    p_cv_coupon.add_argument("--machine-label", required=True)
    p_cv_coupon.add_argument("--adapter", default="generic_klipper_cv_beacon")
    p_cv_coupon.add_argument("--host", default="")
    p_cv_coupon.add_argument("--tool", default="", help="optional tool select command, e.g. T0 or T1")
    p_cv_coupon.add_argument("--output", required=True)
    p_cv_coupon.add_argument("--manifest", required=True)
    p_cv_coupon.add_argument("--homography-template", help="write camera homography template JSON")
    p_cv_coupon.add_argument("--beacon-plan", help="write dry-run Beacon contact probe plan JSON")
    p_cv_coupon.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_cv_coupon.add_argument("--pre-gcode", action="append", default=[], help="extra setup G-code line; repeatable")
    p_cv_coupon.add_argument("--normalization-note", default="No live filament-width normalization configured.")
    p_cv_coupon.add_argument("--k-center", type=float, default=0.030)
    p_cv_coupon.add_argument("--k-half-span", type=float, default=0.018)
    p_cv_coupon.add_argument("--k-min", type=float, default=0.0)
    p_cv_coupon.add_argument("--k-max", type=float, default=0.12)
    p_cv_coupon.add_argument("--steps", type=int, default=7)
    p_cv_coupon.add_argument("--layout", default="stacked", choices=["stacked", "front-edge", "rear-edge"])
    p_cv_coupon.add_argument("--bed-x", type=float, default=300.0)
    p_cv_coupon.add_argument("--bed-y", type=float, default=300.0)
    p_cv_coupon.add_argument("--edge-band-width", type=float, default=20.0)
    p_cv_coupon.add_argument("--x", type=float, default=18.0)
    p_cv_coupon.add_argument("--y", type=float, default=18.0)
    p_cv_coupon.add_argument("--z", type=float, default=0.24)
    p_cv_coupon.add_argument("--length", type=float, default=64.0)
    p_cv_coupon.add_argument("--corner-leg", type=float, default=14.0)
    p_cv_coupon.add_argument("--spacing", type=float, default=18.0)
    p_cv_coupon.add_argument("--speed", type=float, default=140.0)
    p_cv_coupon.add_argument("--travel-speed", type=float, default=250.0)
    p_cv_coupon.add_argument("--accel", type=float, default=5000.0)
    p_cv_coupon.add_argument("--line-width", type=float, default=0.48)
    p_cv_coupon.add_argument("--layer-height", type=float, default=0.24)
    p_cv_coupon.add_argument("--filament-diameter", type=float, default=1.75)
    p_cv_coupon.add_argument("--flow-ratio", type=float, default=1.0)
    p_cv_coupon.add_argument("--retract", type=float, default=0.4)
    p_cv_coupon.add_argument("--z-hop", type=float, default=0.35)
    p_cv_coupon.add_argument("--homography-margin", type=float, default=5.0)
    p_cv_coupon.add_argument("--beacon-safe-z", type=float, default=2.0)
    p_cv_coupon.add_argument("--beacon-sample-offset", type=float, default=3.0)

    p_cv_apply = sub.add_parser("klipper-cv-apply-pa", help="Dry-run or execute generic Klipper PA update")
    p_cv_apply.add_argument("k", type=float)
    p_cv_apply.add_argument("--host", required=True)
    p_cv_apply.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_cv_apply.add_argument("--execute", action="store_true")
    p_cv_apply.add_argument("--allow-printing", action="store_true")

    p_beacon_sim = sub.add_parser("beacon-simulate-coupon", help="Generate synthetic Beacon coupon measurements for offline validation")
    p_beacon_sim.add_argument("--manifest", required=True)
    p_beacon_sim.add_argument("--output", required=True)
    p_beacon_sim.add_argument("--true-k", type=float, required=True)
    p_beacon_sim.add_argument("--noise-mm", type=float, default=0.003)
    p_beacon_sim.add_argument("--seed", type=int, default=42)
    p_beacon_sim.add_argument("--plate-z", type=float, default=0.0)
    p_beacon_sim.add_argument("--line-height", type=float, default=0.0, help="0 means use manifest layer_height")
    p_beacon_sim.add_argument("--sample-offset", type=float, default=3.0)
    p_beacon_sim.add_argument("--low-pa-gain", type=float, default=2.2, help="mm of measured overfill per 1.0 K under target")
    p_beacon_sim.add_argument("--corner-gain", type=float, default=2.8, help="mm of corner overfill per 1.0 K under target")
    p_beacon_sim.add_argument("--high-pa-gain", type=float, default=2.4, help="mm of post-corner underfill per 1.0 K over target")

    p_beacon_score = sub.add_parser("beacon-score-coupon", help="Score Beacon bead-height measurements and optionally fuse them with camera scoring")
    p_beacon_score.add_argument("--manifest", required=True)
    p_beacon_score.add_argument("--measurements", required=True)
    p_beacon_score.add_argument("--camera-score", default="", help="optional score-coupon/qidi-score-coupon JSON to fuse with Beacon")
    p_beacon_score.add_argument("--output", help="write Beacon/fusion score JSON")
    p_beacon_score.add_argument("--machine-label", default="")
    p_beacon_score.add_argument("--adapter", default="beacon_cv_fusion_v1")
    p_beacon_score.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_beacon_score.add_argument("--camera-weight", type=float, default=0.45)
    p_beacon_score.add_argument("--beacon-weight", type=float, default=0.55)
    p_beacon_score.add_argument("--height-scale", type=float, default=0.0, help="0 means max(0.03, layer_height*0.20)")
    p_beacon_score.add_argument("--target-height", type=float, default=0.0, help="0 means use manifest layer_height")
    p_beacon_score.add_argument("--invert-z", action="store_true", help="invert measurement sign if contact results use the opposite Z convention")
    p_beacon_score.add_argument("--no-auto-sign", action="store_true", help="do not auto-flip negative bead heights")
    p_beacon_score.add_argument("--min-complete-roles", type=int, default=5)
    p_beacon_score.add_argument("--min-confidence", type=float, default=0.25)

    p_maxflow = sub.add_parser("maxflow-coupon", help="Generate a CNC-Kitchen-inspired max volumetric flow ladder coupon")
    p_maxflow.add_argument("--machine-label", required=True)
    p_maxflow.add_argument("--adapter", default="maxflow_beacon_v1")
    p_maxflow.add_argument("--host", default="")
    p_maxflow.add_argument("--tool", default="", help="optional tool select command, e.g. T0 or T1")
    p_maxflow.add_argument("--output", required=True)
    p_maxflow.add_argument("--manifest", required=True)
    p_maxflow.add_argument("--homography-template", help="write camera homography template JSON")
    p_maxflow.add_argument("--beacon-plan", help="write dry-run Beacon contact probe plan JSON")
    p_maxflow.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_maxflow.add_argument("--pre-gcode", action="append", default=[], help="extra setup G-code line; repeatable")
    p_maxflow.add_argument("--k", type=float, default=-1.0, help="pressure advance K to apply before the ladder; negative means leave current PA")
    p_maxflow.add_argument("--flow-start", type=float, default=10.0)
    p_maxflow.add_argument("--flow-end", type=float, default=38.0)
    p_maxflow.add_argument("--steps", type=int, default=8)
    p_maxflow.add_argument("--safety-factor", type=float, default=0.85)
    p_maxflow.add_argument("--layout", default="row", choices=["row", "front-edge", "rear-edge"])
    p_maxflow.add_argument("--bed-x", type=float, default=300.0)
    p_maxflow.add_argument("--bed-y", type=float, default=300.0)
    p_maxflow.add_argument("--edge-band-width", type=float, default=20.0)
    p_maxflow.add_argument("--x", type=float, default=18.0)
    p_maxflow.add_argument("--y", type=float, default=150.0)
    p_maxflow.add_argument("--z", type=float, default=0.24)
    p_maxflow.add_argument("--length", type=float, default=80.0)
    p_maxflow.add_argument("--spacing", type=float, default=8.0)
    p_maxflow.add_argument("--travel-speed", type=float, default=250.0)
    p_maxflow.add_argument("--max-speed", type=float, default=350.0)
    p_maxflow.add_argument("--accel", type=float, default=10000.0)
    p_maxflow.add_argument("--line-width", type=float, default=0.48)
    p_maxflow.add_argument("--layer-height", type=float, default=0.24)
    p_maxflow.add_argument("--filament-diameter", type=float, default=1.75)
    p_maxflow.add_argument("--flow-ratio", type=float, default=1.0)
    p_maxflow.add_argument("--retract", type=float, default=0.4)
    p_maxflow.add_argument("--z-hop", type=float, default=0.35)
    p_maxflow.add_argument("--reference-offset", type=float, default=4.0)
    p_maxflow.add_argument("--homography-margin", type=float, default=5.0)
    p_maxflow.add_argument("--beacon-safe-z", type=float, default=2.0)
    p_maxflow.add_argument("--beacon-sample-inset", type=float, default=5.0)

    p_maxflow_sim = sub.add_parser("maxflow-simulate-beacon", help="Generate synthetic Beacon measurements for a max-flow ladder")
    p_maxflow_sim.add_argument("--manifest", required=True)
    p_maxflow_sim.add_argument("--output", required=True)
    p_maxflow_sim.add_argument("--true-max-flow", type=float, required=True)
    p_maxflow_sim.add_argument("--noise-mm", type=float, default=0.003)
    p_maxflow_sim.add_argument("--seed", type=int, default=42)
    p_maxflow_sim.add_argument("--plate-z", type=float, default=0.0)
    p_maxflow_sim.add_argument("--sample-inset", type=float, default=5.0)
    p_maxflow_sim.add_argument("--drop-gain", type=float, default=1.6)
    p_maxflow_sim.add_argument("--min-height-ratio", type=float, default=0.45)

    p_maxflow_score = sub.add_parser("maxflow-score-beacon", help="Score Beacon bead-height measurements from a max-flow ladder")
    p_maxflow_score.add_argument("--manifest", required=True)
    p_maxflow_score.add_argument("--measurements", required=True)
    p_maxflow_score.add_argument("--output", help="write max-flow score JSON")
    p_maxflow_score.add_argument("--machine-label", default="")
    p_maxflow_score.add_argument("--adapter", default="maxflow_beacon_v1")
    p_maxflow_score.add_argument("--safety-factor", type=float, default=0.85)
    p_maxflow_score.add_argument("--min-height-ratio", type=float, default=0.88)
    p_maxflow_score.add_argument("--min-point-ratio", type=float, default=0.82)
    p_maxflow_score.add_argument("--max-height-cv", type=float, default=0.12)
    p_maxflow_score.add_argument("--min-points", type=int, default=3)

    p_flow_gov = sub.add_parser("flow-governor", help="Postprocess G-code with a flow-aware same-print speed governor")
    p_flow_gov.add_argument("--input", required=True, help="input G-code file")
    p_flow_gov.add_argument("--output", required=True, help="rewritten G-code file")
    p_flow_gov.add_argument("--report", help="write JSON report")
    p_flow_gov.add_argument("--safe-max-flow", type=float, default=0.0, help="safe calibrated max flow in mm^3/s")
    p_flow_gov.add_argument("--maxflow-score", default="", help="optional maxflow-score-beacon JSON; uses safe_max_flow_mm3_s")
    p_flow_gov.add_argument("--old-max-flow", type=float, default=0.0, help="old slicer max flow in mm^3/s; enables surgical flow-capped detection")
    p_flow_gov.add_argument("--filament-diameter", type=float, default=1.75)
    p_flow_gov.add_argument("--max-factor", type=float, default=1.35, help="maximum feedrate multiplier for one move")
    p_flow_gov.add_argument("--max-speed", type=float, default=350.0, help="absolute move speed cap in mm/s")
    p_flow_gov.add_argument("--min-move", type=float, default=1.0, help="minimum move length to govern")
    p_flow_gov.add_argument("--min-gain", type=float, default=0.015, help="minimum fractional feedrate gain before rewriting")
    p_flow_gov.add_argument("--max-flow-fraction", type=float, default=0.985, help="do not alter moves already above this fraction of safe max")
    p_flow_gov.add_argument("--min-old-flow-ratio", type=float, default=0.70, help="with --old-max-flow, only alter moves at least this fraction of the old limit")
    p_flow_gov.add_argument("--cap-over-safe", action=argparse.BooleanOptionalAction, default=True, help="slow eligible moves that exceed the calibrated safe max flow")
    p_flow_gov.add_argument("--first-layer-count", type=int, default=1)
    p_flow_gov.add_argument("--include-features", default="", help="comma list; default is sparse infill and solid infill")
    p_flow_gov.add_argument("--exclude-features", default="", help="comma list; default protects walls, bridges, top/bottom, support, etc.")
    p_flow_gov.add_argument("--allow-unknown-features", action="store_true")
    p_flow_gov.add_argument("--default-relative-e", action="store_true", help="assume relative E until M82/M83 appears")
    p_flow_gov.add_argument("--annotate", action="store_true", help="append debug comments to changed moves")
    p_flow_gov.add_argument("--add-header", action=argparse.BooleanOptionalAction, default=True)
    p_flow_gov.add_argument("--restore-feed-after-change", action=argparse.BooleanOptionalAction, default=True)

    p_flow_fixture = sub.add_parser("flow-governor-synthetic", help="Generate a small synthetic G-code fixture for the flow governor")
    p_flow_fixture.add_argument("--output", required=True)
    p_flow_fixture.add_argument("--old-max-flow", type=float, default=20.0)
    p_flow_fixture.add_argument("--filament-diameter", type=float, default=1.75)

    p_gcode_map = sub.add_parser("gcode-telemetry-map", help="Map passive telemetry samples to G-code byte offsets and slicer intent")
    p_gcode_map.add_argument("--gcode-input", required=True)
    p_gcode_map.add_argument("--telemetry-jsonl", required=True)
    p_gcode_map.add_argument("--output-jsonl", help="write mapped samples as JSON Lines")
    p_gcode_map.add_argument("--csv", help="write mapped samples as CSV")
    p_gcode_map.add_argument("--summary", help="write summary JSON")
    p_gcode_map.add_argument("--filament-diameter", type=float, default=1.75)
    p_gcode_map.add_argument("--default-relative-e", action="store_true", help="assume relative E until M82/M83 appears")

    p_gcode_agg = sub.add_parser("gcode-telemetry-aggregate", help="Aggregate mapped G-code telemetry into feature/flow/speed bands")
    p_gcode_agg.add_argument("--mapped-jsonl", action="append", required=True, help="mapped JSONL from gcode-telemetry-map; repeatable")
    p_gcode_agg.add_argument("--output", help="write aggregate summary JSON")
    p_gcode_agg.add_argument("--bands-csv", help="write flattened band table CSV")
    p_gcode_agg.add_argument("--flow-metric", default="hall", choices=["hall", "telemetry", "nominal"])
    p_gcode_agg.add_argument("--motion-filter", default="extrude_xy", choices=["extrude_xy", "all"])
    p_gcode_agg.add_argument("--include-features", default="", help="optional comma-list of features to include")
    p_gcode_agg.add_argument("--exclude-features", default="", help="optional comma-list of features to exclude")
    p_gcode_agg.add_argument("--require-flow", action=argparse.BooleanOptionalAction, default=True)
    p_gcode_agg.add_argument("--flow-bin-size", type=float, default=1.0)
    p_gcode_agg.add_argument("--speed-bin-size", type=float, default=25.0)
    p_gcode_agg.add_argument("--pa-bin-size", type=float, default=0.005)
    p_gcode_agg.add_argument("--temp-bin-size", type=float, default=2.0)
    p_gcode_agg.add_argument("--beacon-bin-size", type=float, default=1.0)
    p_gcode_agg.add_argument("--layer-bin-size", type=float, default=25.0)
    p_gcode_agg.add_argument("--min-samples-per-band", type=int, default=3)
    p_gcode_agg.add_argument("--max-groups-per-table", type=int, default=40)
    p_gcode_agg.add_argument("--top-groups", type=int, default=12)
    p_gcode_agg.add_argument("--require-telemetry-alignment", action=argparse.BooleanOptionalAction, default=True)
    p_gcode_agg.add_argument("--min-flow-ratio-hall", type=float, default=0.85)
    p_gcode_agg.add_argument("--max-flow-ratio-hall", type=float, default=1.15)
    p_gcode_agg.add_argument("--min-e-velocity-ratio", type=float, default=0.85)
    p_gcode_agg.add_argument("--max-e-velocity-ratio", type=float, default=1.15)

    p_same_plan = sub.add_parser("same-print-plan", help="Write a same-upcoming-print calibration/prep plan")
    p_same_plan.add_argument("--target", default="all", choices=["all", *sorted(SAME_PRINT_TARGET_PRESETS)])
    p_same_plan.add_argument("--output", help="write plan JSON")

    p_same_fixture = sub.add_parser("same-print-fixture", help="Generate a synthetic model body with adaptive PA commands")
    p_same_fixture.add_argument("--output", required=True)
    p_same_fixture.add_argument("--flavor", default="m900", choices=["m900", "klipper", "set_pressure_advance", "prusa", "rrf", "reprap"])
    p_same_fixture.add_argument("--reference-k", type=float, default=0.040)
    p_same_fixture.add_argument("--adaptive-step", type=float, default=0.010)
    p_same_fixture.add_argument("--old-max-flow", type=float, default=20.0)
    p_same_fixture.add_argument("--filament-diameter", type=float, default=1.75)

    p_same_inspect = sub.add_parser("same-print-inspect", help="Inspect a held model body and score compatibility without writing G-code")
    p_same_inspect.add_argument("--target", default="", choices=sorted(SAME_PRINT_TARGET_PRESETS))
    p_same_inspect.add_argument("--model-input", required=True)
    p_same_inspect.add_argument("--output", help="write inspect JSON")
    p_same_inspect.add_argument("--pa-score", default="", help="score JSON containing selected PA/K")
    p_same_inspect.add_argument("--maxflow-score", default="", help="max-flow score JSON containing safe_max_flow_mm3_s")
    p_same_inspect.add_argument("--fixed-pa", type=float, default=None, help="manual PA/K override for inspection")
    p_same_inspect.add_argument("--safe-max-flow", type=float, default=0.0, help="manual safe max-flow override for inspection")
    p_same_inspect.add_argument("--old-max-flow", type=float, default=0.0)
    p_same_inspect.add_argument("--allow-synthetic-scores", action="store_true")
    p_same_inspect.add_argument("--allow-missing-score-metadata", action="store_true")
    p_same_inspect.add_argument("--allow-mismatched-score-context", action="store_true")
    p_same_inspect.add_argument("--allow-stale-scores", action="store_true")
    p_same_inspect.add_argument("--score-max-age-hours", type=float, default=168.0)

    p_same_stamp = sub.add_parser("same-print-stamp-score-context", help="Attach model compatibility context to a PA or max-flow score JSON")
    p_same_stamp.add_argument("--score-input", required=True)
    p_same_stamp.add_argument("--model-input", required=True)
    p_same_stamp.add_argument("--output", required=True)
    p_same_stamp.add_argument("--score-origin", required=True, choices=["real", "synthetic", "manual"])
    p_same_stamp.add_argument("--measurement-channel", default="")
    p_same_stamp.add_argument("--calibration-id", default="")

    p_same_prepare = sub.add_parser("same-print-prepare", help="Prepare a held model body using fixed PA, adaptive PA shift, and max-flow governor")
    p_same_prepare.add_argument("--target", default="", choices=sorted(SAME_PRINT_TARGET_PRESETS))
    p_same_prepare.add_argument("--model-input", required=True)
    p_same_prepare.add_argument("--output", required=True)
    p_same_prepare.add_argument("--report", help="write prepare report JSON")
    p_same_prepare.add_argument("--flavor", default="auto", choices=["auto", "m900", "klipper", "set_pressure_advance", "prusa", "rrf", "reprap"])
    p_same_prepare.add_argument("--pa-score", default="", help="score JSON containing selected PA/K")
    p_same_prepare.add_argument("--fixed-pa", type=float, default=None, help="override selected fixed PA/K")
    p_same_prepare.add_argument("--no-fixed-pa", action="store_true")
    p_same_prepare.add_argument("--adaptive-mode", default="shift-existing", choices=["shift-existing", "off"])
    p_same_prepare.add_argument("--adaptive-reference-k", type=float, default=None, help="PA/K value used when the model body was sliced")
    p_same_prepare.add_argument("--pa-min", type=float, default=0.0)
    p_same_prepare.add_argument("--pa-max", type=float, default=0.20)
    p_same_prepare.add_argument("--maxflow-score", default="", help="max-flow score JSON containing safe_max_flow_mm3_s")
    p_same_prepare.add_argument("--safe-max-flow", type=float, default=0.0)
    p_same_prepare.add_argument("--old-max-flow", type=float, default=0.0)
    p_same_prepare.add_argument("--no-flow-governor", action="store_true")
    p_same_prepare.add_argument("--filament-diameter", type=float, default=1.75)
    p_same_prepare.add_argument("--flow-max-factor", type=float, default=1.35)
    p_same_prepare.add_argument("--flow-max-speed", type=float, default=350.0)
    p_same_prepare.add_argument("--flow-min-move", type=float, default=1.0)
    p_same_prepare.add_argument("--flow-min-gain", type=float, default=0.015)
    p_same_prepare.add_argument("--flow-max-flow-fraction", type=float, default=0.985)
    p_same_prepare.add_argument("--flow-min-old-flow-ratio", type=float, default=0.70)
    p_same_prepare.add_argument("--flow-cap-over-safe", action=argparse.BooleanOptionalAction, default=True)
    p_same_prepare.add_argument("--first-layer-count", type=int, default=1)
    p_same_prepare.add_argument("--flow-include-features", default="")
    p_same_prepare.add_argument("--flow-exclude-features", default="")
    p_same_prepare.add_argument("--flow-allow-unknown-features", action="store_true")
    p_same_prepare.add_argument("--default-relative-e", action="store_true")
    p_same_prepare.add_argument("--flow-restore-feed", action=argparse.BooleanOptionalAction, default=True)
    p_same_prepare.add_argument("--allow-synthetic-scores", action="store_true")
    p_same_prepare.add_argument("--allow-missing-score-metadata", action="store_true")
    p_same_prepare.add_argument("--allow-mismatched-score-context", action="store_true")
    p_same_prepare.add_argument("--allow-stale-scores", action="store_true")
    p_same_prepare.add_argument("--score-max-age-hours", type=float, default=168.0)
    p_same_prepare.add_argument("--annotate", action="store_true")

    p_probe = sub.add_parser("probe", help="Read-only Moonraker probe")
    p_probe.add_argument("host")

    p_snapshot = sub.add_parser("snapshot", help="Capture the first enabled Moonraker webcam snapshot")
    p_snapshot.add_argument("host")
    p_snapshot.add_argument("--output", required=True)

    p_coupon = sub.add_parser("coupon", help="Generate a compact PA calibration coupon")
    p_coupon.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_coupon.add_argument("--k-min", type=float, default=0.005)
    p_coupon.add_argument("--k-max", type=float, default=0.080)
    p_coupon.add_argument("--fallback-k", type=float, default=0.030)
    p_coupon.add_argument("--steps", type=int, default=10)
    p_coupon.add_argument("--x", type=float, default=15.0)
    p_coupon.add_argument("--y", type=float, default=15.0)
    p_coupon.add_argument("--z", type=float, default=0.22)
    p_coupon.add_argument("--length", type=float, default=70.0)
    p_coupon.add_argument("--corner-leg", type=float, default=12.0)
    p_coupon.add_argument("--spacing", type=float, default=6.0)
    p_coupon.add_argument("--speed", type=float, default=120.0, help="print speed in mm/s")
    p_coupon.add_argument("--travel-speed", type=float, default=250.0, help="travel speed in mm/s")
    p_coupon.add_argument("--accel", type=float, default=8000.0)
    p_coupon.add_argument("--line-width", type=float, default=0.45)
    p_coupon.add_argument("--layer-height", type=float, default=0.22)
    p_coupon.add_argument("--filament-diameter", type=float, default=1.75)
    p_coupon.add_argument("--flow-ratio", type=float, default=1.0)
    p_coupon.add_argument("--retract", type=float, default=0.4)
    p_coupon.add_argument("--manifest", help="write coupon manifest JSON to this path")

    p_homography = sub.add_parser("homography-template", help="Create a camera homography template for a coupon")
    p_homography.add_argument("--manifest", required=True)
    p_homography.add_argument("--output", required=True)
    p_homography.add_argument("--margin", type=float, default=5.0)

    p_score = sub.add_parser("score-coupon", help="Score a printed coupon from a camera image")
    p_score.add_argument("--image", required=True)
    p_score.add_argument("--manifest", required=True)
    p_score.add_argument("--homography", required=True)
    p_score.add_argument("--debug-image")
    p_score.add_argument("--scale", type=float, default=8.0, help="rectified pixels per bed mm")
    p_score.add_argument("--margin", type=float, default=5.0)
    p_score.add_argument("--band-mm", type=float, default=3.0)
    p_score.add_argument("--sample-inset", type=float, default=5.0)
    p_score.add_argument("--sample-step-mm", type=float, default=2.0)
    p_score.add_argument("--corner-score-mm", type=float, default=7.0)

    p_apply = sub.add_parser("apply-pa", help="Dry-run or execute a live PA update through Moonraker")
    p_apply.add_argument("host")
    p_apply.add_argument("k", type=float)
    p_apply.add_argument("--flavor", default="klipper", choices=["klipper", "m900", "rrf", "reprap", "repetier", "set_pressure_advance"])
    p_apply.add_argument("--execute", action="store_true", help="actually send the PA command")
    p_apply.add_argument("--allow-printing", action="store_true", help="allow live PA update while print_stats.state is printing or paused")

    args = parser.parse_args()
    if args.cmd == "inventory":
        print(json.dumps([asdict(t) for t in inventory(Path(args.root), args.user)], indent=2))
    elif args.cmd == "prusa-profiles":
        print(json.dumps(prusa_profiles(Path(args.root), args.user_store, args.host), indent=2))
    elif args.cmd == "prusa-probe":
        print(json.dumps(prusa_probe(args), indent=2))
    elif args.cmd == "prusa-sweep":
        print(json.dumps(prusa_sweep(args), indent=2))
    elif args.cmd == "prusa-simulate":
        print(json.dumps(prusa_simulate(args), indent=2))
    elif args.cmd == "prusa-maxflow-sweep":
        print(json.dumps(prusa_maxflow_sweep(args), indent=2))
    elif args.cmd == "prusa-maxflow-simulate":
        print(json.dumps(prusa_maxflow_simulate(args), indent=2))
    elif args.cmd == "prusa-maxflow-score":
        print(json.dumps(prusa_maxflow_score_npz(args), indent=2))
    elif args.cmd == "prusa-apply-pa":
        print(json.dumps(apply_prusa_pa(args), indent=2))
    elif args.cmd == "prusa-enable-metrics":
        print(json.dumps(prusa_enable_metrics(args), indent=2))
    elif args.cmd == "qidi-telemetry":
        print(json.dumps(qidi_telemetry(args), indent=2))
    elif args.cmd == "qidi-monitor-readonly":
        print(json.dumps(qidi_monitor_readonly(args), indent=2))
    elif args.cmd == "qidi-download-active-gcode":
        print(json.dumps(qidi_download_active_gcode(args), indent=2))
    elif args.cmd == "qidi-coupon":
        print(json.dumps(qidi_generate_coupon(args), indent=2))
    elif args.cmd == "qidi-score-coupon":
        print(json.dumps(qidi_score_coupon(args), indent=2))
    elif args.cmd == "qidi-apply-pa":
        print(json.dumps(qidi_apply_pa(args), indent=2))
    elif args.cmd == "klipper-cv-coupon":
        print(json.dumps(klipper_cv_generate_coupon(args), indent=2))
    elif args.cmd == "klipper-cv-apply-pa":
        print(json.dumps(klipper_cv_apply_pa(args), indent=2))
    elif args.cmd == "beacon-simulate-coupon":
        print(json.dumps(beacon_simulate_coupon(args), indent=2))
    elif args.cmd == "beacon-score-coupon":
        print(json.dumps(beacon_score_coupon(args), indent=2))
    elif args.cmd == "maxflow-coupon":
        print(json.dumps(maxflow_generate_coupon(args), indent=2))
    elif args.cmd == "maxflow-simulate-beacon":
        print(json.dumps(maxflow_simulate_beacon(args), indent=2))
    elif args.cmd == "maxflow-score-beacon":
        print(json.dumps(maxflow_score_beacon(args), indent=2))
    elif args.cmd == "flow-governor":
        print(json.dumps(flow_governor(args), indent=2))
    elif args.cmd == "flow-governor-synthetic":
        print(json.dumps(make_synthetic_flow_governor_gcode(args), indent=2))
    elif args.cmd == "gcode-telemetry-map":
        print(json.dumps(map_gcode_telemetry(args), indent=2))
    elif args.cmd == "gcode-telemetry-aggregate":
        print(json.dumps(aggregate_gcode_telemetry(args), indent=2))
    elif args.cmd == "same-print-plan":
        print(json.dumps(same_print_plan(args), indent=2))
    elif args.cmd == "same-print-fixture":
        print(json.dumps(same_print_fixture(args), indent=2))
    elif args.cmd == "same-print-inspect":
        print(json.dumps(same_print_inspect(args), indent=2))
    elif args.cmd == "same-print-stamp-score-context":
        print(json.dumps(same_print_stamp_score_context(args), indent=2))
    elif args.cmd == "same-print-prepare":
        print(json.dumps(same_print_prepare(args), indent=2))
    elif args.cmd == "probe":
        print(json.dumps(probe(args.host), indent=2))
    elif args.cmd == "snapshot":
        print(json.dumps(capture_snapshot(args.host, Path(args.output)), indent=2))
    elif args.cmd == "coupon":
        gcode, manifest = generate_coupon(args)
        if args.manifest:
            Path(args.manifest).write_text(json.dumps(manifest, indent=2) + "\n")
        print(gcode)
    elif args.cmd == "homography-template":
        template = homography_template(Path(args.manifest), args.margin)
        Path(args.output).write_text(json.dumps(template, indent=2) + "\n")
        print(json.dumps({"output": args.output, "bed_points": template["bed_points"]}, indent=2))
    elif args.cmd == "score-coupon":
        print(json.dumps(score_coupon(args), indent=2))
    elif args.cmd == "apply-pa":
        print(json.dumps(apply_pa(args.host, args.k, args.flavor, args.execute, args.allow_printing), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
