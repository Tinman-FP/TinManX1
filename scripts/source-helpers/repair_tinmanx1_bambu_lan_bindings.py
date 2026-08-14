#!/usr/bin/env python3
"""Repair TinManX1 Bambu LAN bindings and canonical device identities.

This helper intentionally avoids access codes. It reads local_machines,
canonicalizes known Bambu model names, tests Bambu MQTT TLS endpoints, and
updates dev_ip when a configured serial number is found at a different LAN
address.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as _dt
import ipaddress
import json
import pathlib
import re
import shutil
import socket
import subprocess
import sys
from typing import Iterable


BAMBU_TYPES = {
    "BL-P001",
    "BL-P002",
    "C11",
    "C12",
    "C13",
    "N1",
    "N2S",
    "N6",
    "N7",
    "O1D",
    "O1E",
    "O1S",
}

BAMBU_TYPE_ALIASES = {
    "3DPrinter-X1": "BL-P002",
    "3DPrinter-X1-Carbon": "BL-P001",
    "Bambu Lab X1 Carbon": "BL-P001",
    "Bambu Lab X1": "BL-P002",
    "Bambu Lab P1P": "C11",
    "Bambu Lab P1S": "C12",
    "Bambu Lab X1E": "C13",
    "Bambu Lab A1 mini": "N1",
    "Bambu Lab A1": "N2S",
    "Bambu Lab X2D": "N6",
    "Bambu Lab P2S": "N7",
    "Bambu Lab H2D": "O1D",
    "Bambu Lab H2D Pro": "O1E",
    "Bambu Lab H2S": "O1S",
}


def is_probably_bambu(serial: str, machine: dict) -> bool:
    printer_type = str(machine.get("printer_type", ""))
    if printer_type in BAMBU_TYPES or printer_type in BAMBU_TYPE_ALIASES:
        return True
    return bool(re.fullmatch(r"[0-9A-Z]{10,24}", serial)) and bool(machine.get("dev_ip"))


def has_open_port(host: str, port: int = 8883, timeout: float = 0.18) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def cert_cn(host: str, timeout: float = 3.0) -> str | None:
    try:
        s_client = subprocess.Popen(
            [
                "openssl",
                "s_client",
                "-connect",
                f"{host}:8883",
                "-servername",
                "bblp",
                "-showcerts",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        x509 = subprocess.run(
            ["openssl", "x509", "-noout", "-subject"],
            stdin=s_client.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        if s_client.stdout:
            s_client.stdout.close()
        try:
            s_client.wait(timeout=1)
        except subprocess.TimeoutExpired:
            s_client.kill()
        subject = x509.stdout.decode("utf-8", "ignore").strip()
    except (OSError, subprocess.SubprocessError):
        return None

    match = re.search(r"(?:^|[ /,])CN\s*=\s*([^,/]+)", subject)
    return match.group(1).strip() if match else None


def candidate_prefixes(machines: dict) -> list[str]:
    prefixes: set[str] = set()
    for machine in machines.values():
        ip = str(machine.get("dev_ip", ""))
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if addr.version == 4 and not addr.is_loopback:
            parts = ip.split(".")
            prefixes.add(".".join(parts[:3]))
    return sorted(prefixes)


def open_hosts(prefixes: Iterable[str]) -> list[str]:
    hosts = [f"{prefix}.{i}" for prefix in prefixes for i in range(1, 255)]
    found: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=96) as executor:
        future_map = {executor.submit(has_open_port, host): host for host in hosts}
        for future in concurrent.futures.as_completed(future_map):
            host = future_map[future]
            try:
                if future.result():
                    found.append(host)
            except OSError:
                pass
    return sorted(found, key=lambda h: tuple(int(p) for p in h.split(".")))


def discover_serial_hosts(prefixes: Iterable[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    hosts = open_hosts(prefixes)
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
        future_map = {executor.submit(cert_cn, host): host for host in hosts}
        for future in concurrent.futures.as_completed(future_map):
            host = future_map[future]
            cn = future.result()
            if cn:
                result[cn] = host
    return result


def repair(datadir: pathlib.Path, dry_run: bool = False) -> int:
    conf = datadir / "OrcaSlicer.conf"
    if not conf.exists():
        return 0
    data = json.loads(conf.read_text())
    machines = data.get("local_machines")
    if not isinstance(machines, dict):
        return 0

    bambu = {serial: m for serial, m in machines.items() if is_probably_bambu(serial, m)}
    if not bambu:
        return 0

    serial_hosts: dict[str, str] = {}
    for serial, machine in bambu.items():
        current_ip = str(machine.get("dev_ip", ""))
        if current_ip and has_open_port(current_ip):
            cn = cert_cn(current_ip)
            if cn:
                serial_hosts[cn] = current_ip

    missing = [serial for serial in bambu if serial_hosts.get(serial) != str(bambu[serial].get("dev_ip", ""))]
    if missing:
        serial_hosts.update(discover_serial_hosts(candidate_prefixes(machines)))

    changes: list[tuple[str, str, str, str]] = []
    for serial, machine in bambu.items():
        old_type = str(machine.get("printer_type", ""))
        new_type = BAMBU_TYPE_ALIASES.get(old_type, old_type)
        if new_type != old_type:
            machine["printer_type"] = new_type

        new_ip = serial_hosts.get(serial)
        old_ip = str(machine.get("dev_ip", ""))
        if new_ip and old_ip != new_ip:
            machine["dev_ip"] = new_ip
        else:
            new_ip = old_ip

        if old_type != new_type or old_ip != new_ip:
            changes.append((serial, old_ip, new_ip, f"{old_type} -> {new_type}"))

    if not changes:
        return 0

    for serial, old_ip, new_ip, type_change in changes:
        print(
            f"TinManX1 Bambu LAN repair: {serial} ip {old_ip} -> {new_ip}; model {type_change}",
            file=sys.stderr,
        )

    if dry_run:
        return 0

    backup_dir = datadir / "_codex_backups" / ("bambu_lan_preflight_" + _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(conf, backup_dir / conf.name)
    tmp = conf.with_suffix(conf.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
    tmp.replace(conf)
    return 0


def main() -> int:
    default_datadir = pathlib.Path.home() / "Library/Application Support/OrcaSlicer-Codex"
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", type=pathlib.Path, default=default_datadir)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        return repair(args.datadir, args.dry_run)
    except Exception as exc:
        print(f"TinManX1 Bambu LAN repair skipped: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
