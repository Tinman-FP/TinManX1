#!/usr/bin/env python3
"""Regression tests for TinManX1 machine capability envelopes."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "resources/orcaslicer_codex/motion_envelope/motion_envelope.py"
SPEC = importlib.util.spec_from_file_location("tinman_motion_envelope", MODULE_PATH)
assert SPEC and SPEC.loader
motion = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = motion
SPEC.loader.exec_module(motion)

NORMALIZER_PATH = ROOT / "scripts/source-helpers/normalize_tinman_machine_catalog.py"
NORMALIZER_SPEC = importlib.util.spec_from_file_location(
    "tinman_machine_catalog_for_motion_test", NORMALIZER_PATH
)
assert NORMALIZER_SPEC and NORMALIZER_SPEC.loader
normalizer = importlib.util.module_from_spec(NORMALIZER_SPEC)
sys.modules[NORMALIZER_SPEC.name] = normalizer
NORMALIZER_SPEC.loader.exec_module(normalizer)


def active_envelope() -> dict:
    return {
        "schema_version": 1,
        "id": "test-corexy-06-v1",
        "printer_model": "Test CoreXY",
        "firmware": "klipper",
        "kinematics": "corexy",
        "status": "active",
        "calibrated_at": "2026-08-29T12:00:00Z",
        "hardware": {
            "toolhead": "Test toolhead",
            "hotend": "Test hotend",
            "nozzle_diameter_mm": 0.6,
            "nozzle_type": "hardened high flow",
            "belt_state": "tensioned and inspected",
            "run_current": "x=0.9A y=0.9A",
        },
        "test_conditions": {
            "minimum_cruise_ratio": 0.0,
            "heat_soaked": True,
        },
        "coupled_points": [
            {
                "velocity_mm_s": 600,
                "acceleration_mm_s2": 10000,
                "iterations": 50,
                "passed": True,
            }
        ],
        "selected_coupled_point": {
            "velocity_mm_s": 600,
            "acceleration_mm_s2": 10000,
        },
        "quality_limit": {
            "velocity_mm_s": 300,
            "acceleration_mm_s2": 5000,
            "source": "Shake&Tune plus inspected ringing tower",
        },
        "safety": {"motion_factor": 0.80, "quality_factor": 0.80},
    }


class MotionEnvelopeTests(unittest.TestCase):
    def test_derives_separate_hard_quality_and_process_caps(self) -> None:
        caps = motion.derive_caps(active_envelope(), "Quality")
        self.assertEqual(caps.hard_velocity_mm_s, 480)
        self.assertEqual(caps.hard_acceleration_mm_s2, 8000)
        self.assertEqual(caps.quality_velocity_mm_s, 240)
        self.assertEqual(caps.quality_acceleration_mm_s2, 4000)
        self.assertEqual(caps.process_velocity_mm_s, 312)
        self.assertEqual(caps.process_acceleration_mm_s2, 4800)

    def test_rejects_independently_selected_maxima(self) -> None:
        envelope = active_envelope()
        envelope["selected_coupled_point"]["velocity_mm_s"] = 700
        with self.assertRaisesRegex(motion.EnvelopeError, "exactly match"):
            motion.validate_envelope(envelope)

    def test_rejects_nonzero_minimum_cruise_ratio(self) -> None:
        envelope = active_envelope()
        envelope["test_conditions"]["minimum_cruise_ratio"] = 0.5
        with self.assertRaisesRegex(motion.EnvelopeError, "must be 0"):
            motion.validate_envelope(envelope)

    def test_rejects_short_validation(self) -> None:
        envelope = active_envelope()
        envelope["coupled_points"][0]["iterations"] = 49
        with self.assertRaisesRegex(motion.EnvelopeError, "at least 50"):
            motion.validate_envelope(envelope)

    def test_rejects_unsupported_kinematics(self) -> None:
        envelope = active_envelope()
        envelope["kinematics"] = "cartesian"
        with self.assertRaisesRegex(motion.EnvelopeError, "CoreXY"):
            motion.validate_envelope(envelope)

    def test_rejects_untraceable_calibration_timestamp(self) -> None:
        envelope = active_envelope()
        envelope["calibrated_at"] = "sometime yesterday"
        with self.assertRaisesRegex(motion.EnvelopeError, "ISO-8601"):
            motion.validate_envelope(envelope)

    def test_caps_profiles_without_raising_lower_values(self) -> None:
        caps = motion.derive_caps(active_envelope(), "Quality")
        process = motion.apply_process_caps(
            {
                "outer_wall_speed": "280",
                "inner_wall_speed": "400",
                "top_surface_speed": "80",
                "default_acceleration": "7000",
                "outer_wall_acceleration": "5000",
                "initial_layer_travel_acceleration": "50%",
            },
            caps,
        )
        self.assertEqual(process["outer_wall_speed"], "240")
        self.assertEqual(process["inner_wall_speed"], "312")
        self.assertEqual(process["top_surface_speed"], "80")
        self.assertEqual(process["default_acceleration"], "4800")
        self.assertEqual(process["outer_wall_acceleration"], "4000")
        self.assertEqual(process["initial_layer_travel_acceleration"], "50%")

        machine = motion.apply_machine_caps(
            {
                "machine_max_speed_x": ["600"],
                "machine_max_speed_y": ["450"],
                "machine_max_speed_z": ["20"],
                "machine_max_acceleration_x": ["10000"],
            },
            caps,
        )
        self.assertEqual(machine["machine_max_speed_x"], ["480"])
        self.assertEqual(machine["machine_max_speed_y"], ["450"])
        self.assertEqual(machine["machine_max_speed_z"], ["20"])
        self.assertEqual(machine["machine_max_acceleration_x"], ["8000"])

    def test_registry_is_fail_closed_and_nozzle_specific(self) -> None:
        envelope = active_envelope()
        with tempfile.TemporaryDirectory() as temp_dir:
            registry = Path(temp_dir) / "registry.json"
            registry.write_text(
                json.dumps({"schema_version": 1, "envelopes": [envelope]}),
                encoding="utf-8",
            )
            loaded = motion.load_registry(registry)
        self.assertIsNotNone(motion.find_active_envelope(loaded, "Test CoreXY", "0.6"))
        self.assertIsNone(motion.find_active_envelope(loaded, "Test CoreXY", "0.4"))

        envelope["status"] = "motion-validated"
        motion.validate_envelope(envelope)
        self.assertIsNone(motion.find_active_envelope([envelope], "Test CoreXY", "0.6"))

    def test_profile_generator_consumes_only_matching_active_envelope(self) -> None:
        envelope = active_envelope()
        envelope["printer_model"] = "Qidi X-Plus 4"
        family = next(
            item for item in normalizer.FAMILIES if item.model == "Qidi X-Plus 4"
        )
        profile = normalizer.canonical_process(
            family,
            "0.6",
            "test source",
            {},
            normalizer.QUALITY_MODE,
            (envelope,),
        )
        self.assertEqual(profile["default_acceleration"], "4800")
        self.assertEqual(profile["travel_acceleration"], "4800")
        self.assertEqual(profile["outer_wall_acceleration"], "2400")

        envelope["status"] = "motion-validated"
        unchanged = normalizer.canonical_process(
            family,
            "0.6",
            "test source",
            {},
            normalizer.QUALITY_MODE,
            (envelope,),
        )
        self.assertEqual(unchanged["default_acceleration"], "6000")
        self.assertEqual(unchanged["travel_acceleration"], "9000")

        source_machine = {
            "nozzle_diameter": ["0.6"],
            "machine_max_speed_x": ["700"],
            "machine_max_speed_y": ["650"],
            "machine_max_acceleration_x": ["15000"],
            "machine_max_acceleration_y": ["14000"],
            "machine_max_acceleration_extruding": ["12000"],
            "machine_max_acceleration_retracting": ["11000"],
            "machine_max_acceleration_travel": ["16000"],
        }
        ratrig_family = next(
            item
            for item in normalizer.FAMILIES
            if item.model == "RatRig V-Core 4 IDEX 500"
        )
        ratrig_envelope = active_envelope()
        ratrig_envelope["printer_model"] = ratrig_family.model
        machine = normalizer.canonical_machine(
            ratrig_family,
            "0.6",
            "test source",
            source_machine,
            (ratrig_envelope,),
        )
        self.assertEqual(machine["machine_max_speed_x"], ["480"])
        self.assertEqual(machine["machine_max_speed_y"], ["480"])
        self.assertEqual(machine["machine_max_acceleration_x"], ["8000"])
        self.assertEqual(machine["machine_max_acceleration_travel"], ["8000"])


if __name__ == "__main__":
    unittest.main()
