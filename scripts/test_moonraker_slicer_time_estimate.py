#!/usr/bin/env python3
"""Regression checks for Moonraker slicer-time handling.

Moonraker's print_stats.total_duration is elapsed wall-clock duration, not the
slicer's planned duration. TinManX1 must use /server/files/metadata estimated_time
for the Device tab and Multi Device remaining-time displays.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def basename(filename: str) -> str:
    return filename.replace("\\", "/").rsplit("/", 1)[-1]


def filenames_match(status_filename: str, metadata_filename: str) -> bool:
    return bool(status_filename and metadata_filename) and (
        status_filename == metadata_filename or basename(status_filename) == basename(metadata_filename)
    )


def remaining_minutes_from_metadata(status: dict, metadata: dict) -> int | None:
    filename = status["print_stats"].get("filename", "")
    metadata_filename = metadata.get("filename", "")
    if not metadata_filename:
        metadata_filename = filename
    if not filenames_match(filename, metadata_filename):
        return None

    estimated = float(metadata.get("estimated_time", 0.0))
    elapsed = float(status["print_stats"].get("print_duration", 0.0))
    if estimated <= 0.0:
        return None
    return max(0, int(round((estimated - elapsed) / 60.0)))


def legacy_remaining_minutes_from_total_duration(status: dict) -> int:
    total = float(status["print_stats"].get("total_duration", 0.0))
    elapsed = float(status["print_stats"].get("print_duration", 0.0))
    return max(0, int((total - elapsed) / 60.0))


def remaining_seconds_for_multi_device(status: dict, metadata: dict) -> int | None:
    filename = status["print_stats"].get("filename", "")
    metadata_filename = metadata.get("filename", "")
    if not metadata_filename:
        metadata_filename = filename
    if not filenames_match(filename, metadata_filename):
        return None

    estimated = float(metadata.get("estimated_time", 0.0))
    elapsed = float(status["print_stats"].get("print_duration", 0.0))
    if estimated <= 0.0:
        return None
    return max(0, int(round(estimated - elapsed)))


def test_live_qidi_estimate_fixture() -> None:
    status = {
        "print_stats": {
            "filename": ".cache/Body2_PET-CF_22h53m.gcode",
            "print_duration": 512.733,
            "total_duration": 1136.0,
        },
        "virtual_sdcard": {"progress": 0.003695},
    }
    metadata = {
        "filename": "Body2_PET-CF_22h53m.gcode",
        "estimated_time": 82383.0,
        "layer_count": 865,
    }

    assert legacy_remaining_minutes_from_total_duration(status) == 10
    assert remaining_minutes_from_metadata(status, metadata) == 1365
    assert remaining_seconds_for_multi_device(status, metadata) == 81870


def test_previous_missing_slicer_time_fixture() -> None:
    status = {
        "print_stats": {
            "filename": ".cache/56fd3b_PET-CF_11h37m.gcode",
            "print_duration": 0.0,
            "total_duration": 275.0,
        },
        "virtual_sdcard": {"progress": 0.0001},
    }
    metadata = {
        "filename": ".cache/56fd3b_PET-CF_11h37m.gcode",
        "estimated_time": 41824.0,
    }

    assert legacy_remaining_minutes_from_total_duration(status) == 4
    assert remaining_minutes_from_metadata(status, metadata) == 697
    assert remaining_seconds_for_multi_device(status, metadata) == 41824


def test_agent_keeps_live_status_stream_enabled() -> None:
    source = (ROOT / "src/slic3r/Utils/MoonrakerPrinterAgent.cpp").read_text(encoding="utf-8")
    assert "/server/files/metadata?filename=" in source
    assert "sync_print_metadata(base_url, api_key);" in source
    assert "start_status_stream(dev_id, base_url, api_key);" in source
    assert "// Orca todo: disable websocket for now" not in source
    assert "#if 0\n        // Start WebSocket status stream" not in source


if __name__ == "__main__":
    test_live_qidi_estimate_fixture()
    test_previous_missing_slicer_time_fixture()
    test_agent_keeps_live_status_stream_enabled()
    print("Moonraker slicer-time regression checks passed")
