#!/usr/bin/env python3
"""Rediscover and repair TinManX1 CORE One L PrusaLink bindings.

The helper runs before TinManX1 reads its configuration. It validates a host
with the saved API key and the same /api/version contract used by the slicer,
then updates every local CORE One L alias in one backed-up transaction. An
offline printer never causes a known-good binding to be erased.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import ipaddress
import json
import pathlib
import shutil
import socket
import subprocess
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Iterable


CORE_FAMILY = "Prusa CORE One L"
STABLE_HOSTNAME = "prusa-core-one-l.local"
SELF_TEST_STALE_HOST = "198.51.100.169"
CACHE_RELATIVE_PATH = pathlib.Path("_tinmanx1_state/prusalink_core_one_l.json")
Probe = Callable[[str, str], tuple[bool, str]]


def is_core_one_l(value: object) -> bool:
    normalized = " ".join(str(value or "").lower().replace("-", " ").replace("_", " ").split())
    return "prusa" in normalized and "core one l" in normalized


def load_json(path: pathlib.Path) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def unique(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value or "").strip().rstrip("/")
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def host_for_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parsed = urllib.parse.urlsplit(candidate if "://" in candidate else f"http://{candidate}")
    return parsed.netloc or parsed.path


def probe_prusalink(host: str, api_key: str, timeout: float = 0.65) -> tuple[bool, str]:
    netloc = host_for_url(host)
    if not netloc or not api_key:
        return False, ""
    request = urllib.request.Request(
        f"http://{netloc}/api/version",
        headers={"X-Api-Key": api_key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(65536)
    except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return False, ""
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        return False, ""
    if not isinstance(payload, dict) or not payload.get("api"):
        return False, ""
    identity = str(payload.get("text", ""))
    return identity.startswith("PrusaLink"), identity


def has_open_http(host: str, timeout: float = 0.16) -> bool:
    try:
        with socket.create_connection((host, 80), timeout=timeout):
            return True
    except OSError:
        return False


def local_ipv4() -> str | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.0.2.1", 9))
        address = str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        sock.close()
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return None
    return address if parsed.version == 4 and not parsed.is_loopback else None


def prefix_for(value: str) -> str | None:
    host = host_for_url(value).split(":", 1)[0]
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return None
    if address.version != 4 or address.is_loopback or not address.is_private:
        return None
    return ".".join(host.split(".")[:3])


def resolve_host(value: str, timeout: float = 0.9) -> str | None:
    """Resolve a configured hostname without allowing mDNS to stall startup."""
    netloc = host_for_url(value)
    parsed = urllib.parse.urlsplit(f"http://{netloc}")
    hostname = parsed.hostname or ""
    try:
        ipaddress.ip_address(hostname)
        return netloc
    except ValueError:
        pass
    if not hostname:
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/dscacheutil", "-q", "host", "-a", "name", hostname],
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        if not line.strip().startswith("ip_address:"):
            continue
        address = line.split(":", 1)[1].strip()
        try:
            parsed_address = ipaddress.ip_address(address)
        except ValueError:
            continue
        if parsed_address.version == 4:
            return f"{address}:{parsed.port}" if parsed.port else address
    return None


def scan_hosts(prefixes: Iterable[str]) -> list[str]:
    hosts = [f"{prefix}.{last}" for prefix in unique(prefixes)[:3] for last in range(1, 255)]
    found: list[str] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=64) as executor:
        futures = {executor.submit(has_open_http, host): host for host in hosts}
        for future in concurrent.futures.as_completed(futures):
            try:
                if future.result():
                    found.append(futures[future])
            except OSError:
                pass
    return sorted(found, key=lambda item: tuple(int(part) for part in item.split(".")))


def core_profiles(datadir: pathlib.Path) -> list[pathlib.Path]:
    result: list[pathlib.Path] = []
    for path in (datadir / "user").glob("*/machine/*.json"):
        profile = load_json(path)
        identity = " ".join(
            str(profile.get(key, "")) for key in ("name", "inherits", "printer_settings_id")
        )
        if is_core_one_l(path.stem) or is_core_one_l(identity):
            result.append(path)
    return sorted(result)


def collect_state(datadir: pathlib.Path) -> tuple[pathlib.Path, dict, list[pathlib.Path], list[str], list[str]]:
    conf_path = datadir / "OrcaSlicer.conf"
    conf = load_json(conf_path)
    profiles = core_profiles(datadir)
    hosts: list[str] = []
    keys: list[str] = []

    connections = conf.get("tinman_machine_connections", {})
    if isinstance(connections, dict):
        for suffix in ("print_host", "print_host_webui"):
            value = connections.get(f"{CORE_FAMILY}::{suffix}")
            if isinstance(value, str):
                hosts.append(value)
        value = connections.get(f"{CORE_FAMILY}::printhost_apikey")
        if isinstance(value, str):
            keys.append(value)

    machines = conf.get("local_machines", {})
    if isinstance(machines, dict):
        for alias, machine in machines.items():
            if not isinstance(machine, dict):
                continue
            if any(is_core_one_l(machine.get(field)) for field in ("dev_name", "printer_type")):
                hosts.extend((str(alias), str(machine.get("dev_ip", ""))))

    for path in profiles:
        profile = load_json(path)
        hosts.extend(str(profile.get(field, "")) for field in ("print_host", "print_host_webui"))
        value = profile.get("printhost_apikey")
        if isinstance(value, str):
            keys.append(value)

    cache = load_json(datadir / CACHE_RELATIVE_PATH)
    if is_core_one_l(cache.get("family")):
        hosts.append(str(cache.get("host", "")))
    hosts.append(STABLE_HOSTNAME)
    return conf_path, conf, profiles, unique(hosts), unique(keys)


def discover(
    hosts: Iterable[str],
    api_keys: Iterable[str],
    prefixes: Iterable[str],
    probe: Probe = probe_prusalink,
    allow_scan: bool = True,
) -> tuple[str, str, str] | None:
    host_list = unique(hosts)
    key_list = unique(api_keys)

    def probe_batch(batch: Iterable[str]) -> tuple[str, str, str] | None:
        pairs = [(host, api_key) for host in batch for api_key in key_list]
        if not pairs:
            return None
        results: dict[int, tuple[bool, str]] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(32, len(pairs))) as executor:
            futures = {
                executor.submit(probe, host, api_key): index
                for index, (host, api_key) in enumerate(pairs)
            }
            for future in concurrent.futures.as_completed(futures):
                try:
                    results[futures[future]] = future.result()
                except (OSError, ValueError):
                    results[futures[future]] = (False, "")
        for index, (host, api_key) in enumerate(pairs):
            valid, identity = results.get(index, (False, ""))
            if valid:
                return host_for_url(host), api_key, identity
        return None

    resolved_hosts = unique(resolved for host in host_list if (resolved := resolve_host(host)))
    match = probe_batch(resolved_hosts)
    if match:
        return match

    if not allow_scan:
        return None
    candidates = scan_hosts(prefixes)
    return probe_batch(host for host in candidates if host not in resolved_hosts)


def atomic_write_json(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        temp_path = pathlib.Path(handle.name)
        json.dump(payload, handle, indent=4, ensure_ascii=False)
        handle.write("\n")
    temp_path.chmod(mode)
    temp_path.replace(path)


def patch_conf(conf: dict, host: str, api_key: str) -> bool:
    changed = False
    access_codes = conf.setdefault("access_code", {})
    if isinstance(access_codes, dict) and access_codes.get(host) != api_key:
        access_codes[host] = api_key
        changed = True

    connections = conf.setdefault("tinman_machine_connections", {})
    if isinstance(connections, dict):
        desired = {
            f"{CORE_FAMILY}::bbl_use_printhost": "0",
            f"{CORE_FAMILY}::host_type": "prusalink",
            f"{CORE_FAMILY}::print_host": host,
            f"{CORE_FAMILY}::print_host_webui": host,
            f"{CORE_FAMILY}::printhost_apikey": api_key,
            f"{CORE_FAMILY}::printhost_authorization_type": "key",
        }
        for key, value in desired.items():
            if connections.get(key) != value:
                connections[key] = value
                changed = True

    machines = conf.setdefault("local_machines", {})
    if isinstance(machines, dict):
        core_aliases = [
            alias
            for alias, machine in machines.items()
            if isinstance(machine, dict)
            and any(is_core_one_l(machine.get(field)) for field in ("dev_name", "printer_type"))
        ]
        # TinManX1 owns the non-Bambu PrusaLink bridge entry. Recreate it after
        # an accidental Device-tab logout, but only after the printer has been
        # authenticated by discover(). Offline printers never reach this path.
        machine = dict(machines.get(host, machines[core_aliases[0]] if core_aliases else {}))
        desired = {"dev_ip": host, "dev_name": CORE_FAMILY, "printer_type": CORE_FAMILY}
        for key, value in desired.items():
            if machine.get(key) != value:
                machine[key] = value
                changed = True
        for alias in core_aliases:
            if alias != host:
                del machines[alias]
                changed = True
        if machines.get(host) != machine:
            machines[host] = machine
            changed = True
    return changed


def patch_profile(profile: dict, host: str, api_key: str) -> bool:
    desired = {
        "host_type": "prusalink",
        "print_host": host,
        "print_host_webui": host,
        "printhost_apikey": api_key,
        "printhost_authorization_type": "key",
    }
    changed = False
    for key, value in desired.items():
        if profile.get(key) != value:
            profile[key] = value
            changed = True
    return changed


def backup(paths: Iterable[pathlib.Path], datadir: pathlib.Path) -> None:
    backup_dir = datadir / "_codex_backups" / ("prusalink_recovery_" + dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    for path in paths:
        if not path.exists():
            continue
        try:
            relative = path.relative_to(datadir)
        except ValueError:
            relative = pathlib.Path(path.name)
        destination = backup_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)


def repair(
    datadir: pathlib.Path,
    dry_run: bool = False,
    allow_scan: bool = True,
    extra_hosts: Iterable[str] = (),
    extra_prefixes: Iterable[str] = (),
    probe: Probe = probe_prusalink,
) -> int:
    conf_path, conf, profiles, hosts, api_keys = collect_state(datadir)
    hosts = unique([*extra_hosts, *hosts])
    if not conf and not profiles:
        print("TinManX1 PrusaLink recovery: no CORE One L configuration found")
        return 0
    if not api_keys:
        print("TinManX1 PrusaLink recovery: saved CORE One L API key is unavailable")
        return 0

    local_address = local_ipv4()
    prefixes = unique(
        [
            *extra_prefixes,
            *(prefix_for(host) or "" for host in hosts),
            prefix_for(local_address or "") or "",
        ]
    )
    match = discover(hosts, api_keys, prefixes, probe=probe, allow_scan=allow_scan)
    if not match:
        print("TinManX1 PrusaLink recovery: CORE One L is offline or not exposed on the local LAN")
        return 0
    host, api_key, identity = match

    changed_paths: list[pathlib.Path] = []
    conf_changed = patch_conf(conf, host, api_key)
    if conf_changed:
        changed_paths.append(conf_path)

    profile_payloads: list[tuple[pathlib.Path, dict]] = []
    for path in profiles:
        profile = load_json(path)
        if patch_profile(profile, host, api_key):
            changed_paths.append(path)
            profile_payloads.append((path, profile))

    if dry_run:
        status = "would repair" if changed_paths else "is current"
        print(f"TinManX1 PrusaLink recovery: CORE One L {status} at {host}")
        return 0

    if changed_paths:
        backup(changed_paths, datadir)
        if conf_changed:
            atomic_write_json(conf_path, conf)
        for path, payload in profile_payloads:
            atomic_write_json(path, payload)

    atomic_write_json(
        datadir / CACHE_RELATIVE_PATH,
        {
            "family": CORE_FAMILY,
            "host": host,
            "identity": identity,
            "verified_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
    )
    status = "repaired" if changed_paths else "verified"
    print(f"TinManX1 PrusaLink recovery: CORE One L {status} at {host}")
    return 0


class _SelfTestHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path == "/api/version" and self.headers.get("X-Api-Key") == "self-test-key":
            body = json.dumps({"api": "2.0", "text": "PrusaLink self-test"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_error(403)

    def log_message(self, *_args: object) -> None:
        return


def self_test() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        datadir = pathlib.Path(temporary)
        machine_dir = datadir / "user/default/machine"
        machine_dir.mkdir(parents=True)
        profile_path = machine_dir / "Prusa CORE One L 0.4 nozzle - TinMan Codex.json"
        atomic_write_json(
            profile_path,
            {
                "name": "Prusa CORE One L 0.4 nozzle - TinMan Codex",
                "print_host": SELF_TEST_STALE_HOST,
                "printhost_apikey": "self-test-key",
            },
        )
        atomic_write_json(
            datadir / "OrcaSlicer.conf",
            {
                "local_machines": {
                    SELF_TEST_STALE_HOST: {
                        "dev_ip": SELF_TEST_STALE_HOST,
                        "dev_name": CORE_FAMILY,
                        "printer_type": CORE_FAMILY,
                    }
                },
                "tinman_machine_connections": {
                    f"{CORE_FAMILY}::print_host": SELF_TEST_STALE_HOST,
                    f"{CORE_FAMILY}::printhost_apikey": "self-test-key",
                },
            },
        )
        server = ThreadingHTTPServer(("127.0.0.1", 0), _SelfTestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host = f"127.0.0.1:{server.server_port}"
        try:
            repair(datadir, allow_scan=False, extra_hosts=[host])
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()

        conf = load_json(datadir / "OrcaSlicer.conf")
        profile = load_json(profile_path)
        assert conf["tinman_machine_connections"][f"{CORE_FAMILY}::print_host"] == host
        assert conf["access_code"][host] == "self-test-key"
        assert list(conf["local_machines"]) == [host]
        assert profile["print_host"] == host
        assert profile["host_type"] == "prusalink"
        assert load_json(datadir / CACHE_RELATIVE_PATH)["host"] == host

        # A verified printer must also be recreated after the Device tab drops
        # its cached entry.
        conf["local_machines"].clear()
        assert patch_conf(conf, host, "self-test-key")
        assert conf["access_code"][host] == "self-test-key"
        assert conf["local_machines"][host]["dev_name"] == CORE_FAMILY
    print("TinManX1 PrusaLink recovery self-test passed")
    return 0


def main() -> int:
    default_datadir = pathlib.Path.home() / "Library/Application Support/OrcaSlicer-Codex"
    parser = argparse.ArgumentParser()
    parser.add_argument("--datadir", type=pathlib.Path, default=default_datadir)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-scan", action="store_true")
    parser.add_argument("--candidate", action="append", default=[])
    parser.add_argument("--prefix", action="append", default=[])
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    try:
        if args.self_test:
            return self_test()
        return repair(
            args.datadir,
            dry_run=args.dry_run,
            allow_scan=not args.no_scan,
            extra_hosts=args.candidate,
            extra_prefixes=args.prefix,
        )
    except Exception as exc:
        print(f"TinManX1 PrusaLink recovery skipped: {exc}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
