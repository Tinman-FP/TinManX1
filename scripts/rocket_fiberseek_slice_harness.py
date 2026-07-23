#!/usr/bin/env python3
"""Build Rocket Slicer `/api/slice/generate` payloads for clean-room testing.

This helper uses a locally installed Rocket Slicer as a behavioral oracle. It
does not copy Rocket code or presets into TinManX1; it reads the local Rocket
project/preset JSON selected by the user, constructs the public HTTP request
shape, and optionally posts it to Rocket's running local backend.
"""

from __future__ import annotations

import argparse
import base64
import copy
import gzip
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Optional


DEFAULT_ROCKET_RESOURCES = Path(
    "/Applications/Rocket Slicer.app/Contents/Resources/backend/resources"
)
DEFAULT_PROJECT_ID = "1207e5d0-9553-46c6-8e71-120472e8a115"

MODE_ALIASES = {
    "light": "Speedy",
    "speedy": "Speedy",
    "medium": "ReinForced",
    "reinforced": "ReinForced",
    "heavy": "Fortified",
    "fortified": "Fortified",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")


def camel_key(key: str) -> str:
    return key[:1].lower() + key[1:] if key else key


def camelize(value: Any) -> Any:
    if isinstance(value, dict):
        return {camel_key(str(key)): camelize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [camelize(item) for item in value]
    return value


def normalize_mode(mode: str) -> str:
    normalized = mode.strip().replace(" ", "").lower()
    try:
        return MODE_ALIASES[normalized]
    except KeyError as exc:
        raise SystemExit(f"Unsupported Rocket/TinMan fiber mode: {mode}") from exc


def gzip_base64_model(stl_path: Path) -> str:
    data = stl_path.read_bytes()
    compressed = gzip.compress(data, compresslevel=9, mtime=0)
    return base64.b64encode(compressed).decode("ascii")


def discover_rocket_port() -> Optional[int]:
    try:
        result = subprocess.run(
            ["ps", "aux"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    for line in result.stdout.splitlines():
        if "Aura.Monolith.API" not in line:
            continue
        match = re.search(r"--urls=http://127\.0\.0\.1:(\d+)", line)
        if match:
            return int(match.group(1))
    return None


def project_json_path(resources: Path, project_id: str) -> Path:
    return resources / "UserData" / "Default" / "Project" / f"{project_id}.json"


def profile_presets_path(resources: Path) -> Path:
    return resources / "UserData" / "Default" / "Presets" / "Profiles.json"


def relative_project_path(project_id: str) -> str:
    return f"UserData/Default/Project/{project_id}"


def profile_value(profile: dict[str, Any], key: str) -> Any:
    return profile.get(key) if key in profile else profile.get(key[:1].upper() + key[1:])


def select_profile(project_settings: dict[str, Any], mode: str) -> dict[str, Any]:
    profiles = project_settings.get("Profiles") or []
    for profile in profiles:
        if str(profile.get("PrintMode", "")).lower() == mode.lower():
            return profile
    available = sorted({str(profile.get("PrintMode")) for profile in profiles})
    raise SystemExit(f"No profile for mode {mode}; available modes: {available}")


def select_profile_from_presets(
    profiles_json: Path,
    mode: str,
    profile_group_id: Optional[str],
) -> dict[str, Any]:
    profiles = load_json(profiles_json)
    if not isinstance(profiles, list):
        raise SystemExit(f"Rocket profiles preset must contain an array: {profiles_json}")
    matches = []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        if str(profile_value(profile, "printMode") or "").lower() != mode.lower():
            continue
        if profile_group_id and str(profile_value(profile, "profileGroupId") or "") != profile_group_id:
            continue
        matches.append(profile)
    if len(matches) == 1:
        return matches[0]
    if matches:
        return sorted(matches, key=lambda item: str(profile_value(item, "id") or ""))[0]

    available = sorted(
        {
            str(profile_value(profile, "printMode"))
            for profile in profiles
            if isinstance(profile, dict)
        }
    )
    raise SystemExit(
        f"No preset profile for mode {mode}"
        f"{f' in profile group {profile_group_id}' if profile_group_id else ''}; "
        f"available modes: {available}"
    )


def make_part(stl_path: Path, name: Optional[str] = None) -> dict[str, Any]:
    return {
        "Id": str(uuid.uuid4()),
        "Name": name or stl_path.stem,
        "Type": "STL",
        "Model": gzip_base64_model(stl_path),
        "LayupRules": [],
        "MaskParts": [],
        "MarkerDatas": [],
        "IsEnabled": True,
        "IsLayupsEnabled": False,
        "IsMasksEnabled": False,
    }


def build_payload(
    project_json: Path,
    mode: str,
    stl_path: Optional[Path],
    project_path: Optional[str],
    part_name: Optional[str],
) -> dict[str, Any]:
    project = load_json(project_json)
    settings = project["ProjectSettings"]
    project_data = project["ProjectData"]
    project_id = str(project["ProjectId"])

    profile = select_profile(settings, mode)
    settings_set = dict(project_data["SettingsSet"])
    settings_set["ProfileId"] = profile.get("Id")
    if profile.get("ProfileGroupId") is not None:
        settings_set["ProfileGroupId"] = profile["ProfileGroupId"]

    parts = list(project_data.get("Parts") or [])
    if stl_path is not None:
        parts = [make_part(stl_path, part_name)]

    payload = {
        "CompanyId": project["CompanyId"],
        "UserId": project["UserId"],
        "ProjectId": project_id,
        "ProjectPath": project_path or relative_project_path(project_id),
        "PrintMode": mode,
        "Parts": parts,
        "SlotExtruderMaterials": project_data["SlotExtruderMaterials"],
        "SettingsSet": settings_set,
        "Plastics": settings["Plastics"],
        "Composites": settings["Composites"],
        "ExtruderPs": settings["ExtruderPs"],
        "ExtruderCs": settings["ExtruderCs"],
        "Slots": settings["Slots"],
        "Printer": settings["Printers"][0],
        "Profile": profile,
        "IsLargeModel": False,
    }
    return camelize(payload)


def update_payload_for_mode(payload: dict[str, Any], mode: str) -> None:
    payload["printMode"] = mode
    profile = payload.get("profile")
    if isinstance(profile, dict) and "printMode" in profile:
        profile["printMode"] = mode


def update_payload_part(payload: dict[str, Any], stl_path: Path, part_name: Optional[str]) -> None:
    payload["parts"] = [camelize(make_part(stl_path, part_name))]


def update_payload_profile(payload: dict[str, Any], profile_json: Path, mode: str) -> None:
    profile = load_json(profile_json)
    if not isinstance(profile, dict):
        raise SystemExit(f"Profile JSON must contain an object: {profile_json}")
    profile = camelize(profile)
    apply_payload_profile(payload, profile, mode)


def apply_payload_profile(payload: dict[str, Any], profile: dict[str, Any], mode: str) -> None:
    if not isinstance(profile, dict):
        raise SystemExit("Profile must contain an object.")

    payload["profile"] = profile
    update_payload_for_mode(payload, str(profile.get("printMode") or mode))

    settings_set = payload.get("settingsSet")
    if not isinstance(settings_set, dict):
        return
    if profile.get("id") is not None:
        settings_set["profileId"] = profile["id"]
    if profile.get("profileGroupId") is not None:
        settings_set["profileGroupId"] = profile["profileGroupId"]


def normalize_profile_to_template(
    profile: dict[str, Any],
    template: dict[str, Any],
    project_id: Optional[str],
) -> dict[str, Any]:
    """Match the profile shape Rocket's project layer posts to /api/slice/generate.

    Rocket's Presets/Profiles.json entries include a few nullable database fields
    that the slice API does not tolerate directly. A saved project payload gives
    us the accepted request shape, so keep preset values only for those accepted
    keys and copy any project-only keys from the template.
    """
    normalized = {key: profile[key] if key in profile else value for key, value in template.items()}
    if project_id is not None and "projectId" in normalized:
        normalized["projectId"] = project_id
    return normalized


def seed_payload_from_preset_profile(
    payload: dict[str, Any],
    profiles_json: Path,
    mode: str,
) -> None:
    template = payload.get("profile")
    profile_group_id = template.get("profileGroupId") if isinstance(template, dict) else None
    preset_profile = select_profile_from_presets(profiles_json, mode, profile_group_id)
    profile = camelize(preset_profile)
    if isinstance(template, dict):
        profile = normalize_profile_to_template(profile, template, payload.get("projectId"))
    apply_payload_profile(payload, profile, mode)


def summarize_payload(payload: dict[str, Any]) -> str:
    profile = payload["profile"]
    printer = payload["printer"]
    composites = payload["composites"]
    extruder_cs = payload["extruderCs"]
    lines = [
        f"projectId: {payload['projectId']}",
        f"projectPath: {payload['projectPath']}",
        f"printMode: {payload['printMode']}",
        f"parts: {len(payload['parts'])}",
        f"printer: {printer.get('name')} ({printer.get('areaSizeX')}x{printer.get('areaSizeY')}x{printer.get('areaSizeZ')})",
        f"profile: {profile.get('name')} / {profile.get('printMode')}",
        f"composites: {', '.join(str(item.get('name')) for item in composites)}",
    ]
    if extruder_cs:
        cfc = extruder_cs[0]
        lines.append(
            "cfc: "
            f"cut={cfc.get('cutDistance')} restart={cfc.get('fiberRestartLength')} "
            f"contact={cfc.get('nozzleContactRadius')}/"
            f"{cfc.get('nozzleContactRadiusExtended')}"
        )
    return "\n".join(lines)


def post_payload(port: int, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}/api/slice/generate"
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Rocket slice request failed: HTTP {exc.code}\n{error}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Rocket slice request failed: {exc}") from exc
    elapsed = time.time() - started
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Rocket returned non-JSON response after {elapsed:.1f}s:\n{text}") from exc
    parsed["_elapsedSeconds"] = elapsed
    return parsed


def local_result_path(resources: Path, slicing_result_path: str) -> Path:
    normalized = slicing_result_path.strip()
    if normalized.startswith("/files/"):
        normalized = normalized[len("/files/") :]
    return resources / normalized.lstrip("/")


def extract_result(resources: Path, response: dict[str, Any], output_dir: Path, stem: str) -> None:
    result_url = response.get("slicingResultPath")
    if not isinstance(result_url, str) or not result_url:
        raise SystemExit("Rocket response did not include slicingResultPath.")
    result_path = local_result_path(resources, result_url)
    if not result_path.exists():
        raise SystemExit(f"Rocket result file does not exist: {result_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    result_copy = output_dir / f"{stem}.result.json"
    gcode_path = output_dir / f"{stem}.gcode"
    profile_path = output_dir / f"{stem}.session_profile.json"
    response_path = output_dir / f"{stem}.response.json"

    data = load_result_json(result_path)
    write_json(response_path, response)
    write_json(result_copy, data)
    gcode_path.write_text(str(data.get("gCode") or ""), encoding="utf-8")
    session = data.get("sessionSet") if isinstance(data.get("sessionSet"), dict) else {}
    profile = session.get("profile") if isinstance(session.get("profile"), dict) else {}
    write_json(profile_path, profile)
    print(f"result: {result_path}")
    print(f"response: {response_path}")
    print(f"extracted gcode: {gcode_path}")
    print(f"session profile: {profile_path}")


def load_result_json(path: Path) -> Any:
    with gzip.open(path, "rt", encoding="utf-8-sig") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rocket-resources",
        type=Path,
        default=DEFAULT_ROCKET_RESOURCES,
        help="Rocket backend resources root.",
    )
    parser.add_argument(
        "--project-json",
        type=Path,
        help="Saved Rocket project JSON to use as settings/material source.",
    )
    parser.add_argument(
        "--payload-json",
        type=Path,
        help="Previously generated /api/slice/generate payload to use as a direct seed.",
    )
    parser.add_argument(
        "--profile-json",
        type=Path,
        help="Optional Rocket profile object to inject into a seeded payload.",
    )
    parser.add_argument(
        "--profiles-json",
        type=Path,
        help="Rocket Presets/Profiles.json file to select a same-group profile by --mode.",
    )
    parser.add_argument(
        "--project-id",
        default=DEFAULT_PROJECT_ID,
        help="Rocket project ID under UserData/Default/Project when --project-json is omitted.",
    )
    parser.add_argument(
        "--mode",
        default="heavy",
        help="TinMan/Rocket strength mode: light, medium, heavy, Speedy, ReinForced, or Fortified.",
    )
    parser.add_argument("--stl", type=Path, help="Optional STL to encode as the only enabled part.")
    parser.add_argument("--part-name", help="Optional display name for --stl.")
    parser.add_argument("--project-path", help="Override Rocket-relative output project path.")
    parser.add_argument("--write-payload", type=Path, help="Write generated JSON payload to this path.")
    parser.add_argument("--post", action="store_true", help="Post payload to Rocket's local backend.")
    parser.add_argument("--port", type=int, help="Rocket backend port; auto-detected when omitted.")
    parser.add_argument("--timeout", type=int, default=1800, help="HTTP timeout for --post, seconds.")
    parser.add_argument("--extract-dir", type=Path, help="After --post, extract Rocket result JSON, G-code, and profile here.")
    parser.add_argument("--extract-stem", help="Output filename stem for --extract-dir.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_json = args.project_json or project_json_path(args.rocket_resources, args.project_id)
    mode = normalize_mode(args.mode)

    if args.payload_json is not None and not args.payload_json.exists():
        raise SystemExit(f"Payload JSON does not exist: {args.payload_json}")
    if args.payload_json is None and not project_json.exists():
        raise SystemExit(f"Rocket project JSON does not exist: {project_json}")
    if args.profile_json is not None and not args.profile_json.exists():
        raise SystemExit(f"Profile JSON does not exist: {args.profile_json}")
    profiles_json = args.profiles_json or profile_presets_path(args.rocket_resources)
    if args.payload_json is not None and args.profile_json is None and not profiles_json.exists():
        raise SystemExit(f"Rocket profiles preset does not exist: {profiles_json}")
    if args.stl is not None and not args.stl.exists():
        raise SystemExit(f"STL does not exist: {args.stl}")

    if args.payload_json is not None:
        payload = copy.deepcopy(load_json(args.payload_json))
        if not isinstance(payload, dict):
            raise SystemExit(f"Payload JSON must contain an object: {args.payload_json}")
        update_payload_for_mode(payload, mode)
        if args.profile_json is not None:
            update_payload_profile(payload, args.profile_json, mode)
        else:
            seed_payload_from_preset_profile(payload, profiles_json, mode)
        if args.stl is not None:
            update_payload_part(payload, args.stl, args.part_name)
        if args.project_path is not None:
            payload["projectPath"] = args.project_path
    else:
        payload = build_payload(project_json, mode, args.stl, args.project_path, args.part_name)
    print(summarize_payload(payload))

    if args.write_payload:
        write_json(args.write_payload, payload)
        print(f"payload: {args.write_payload}")

    if args.post:
        port = args.port or discover_rocket_port()
        if port is None:
            raise SystemExit("Could not find Rocket backend port; pass --port.")
        result = post_payload(port, payload, args.timeout)
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.extract_dir:
            stem = args.extract_stem or f"rocket_{args.mode}_{args.stl.stem if args.stl else 'project'}"
            extract_result(args.rocket_resources, result, args.extract_dir, stem)

    return 0


if __name__ == "__main__":
    sys.exit(main())
