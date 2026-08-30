#!/usr/bin/env python3
"""Regression tests for installed TinManX1 nozzle capability contracts."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "scripts/source-helpers"
sys.path.insert(0, str(HELPERS))

from codex_filament_contracts import (  # noqa: E402
    MICRO_SWISS_CM2_BUCKETS,
    MICRO_SWISS_CHT_BUCKETS,
    apply_contract,
    load_contract,
)

NORMALIZER_PATH = HELPERS / "normalize_tinman_machine_catalog.py"
SPEC = importlib.util.spec_from_file_location("tinman_machine_catalog_nozzle_test", NORMALIZER_PATH)
assert SPEC and SPEC.loader
normalizer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = normalizer
SPEC.loader.exec_module(normalizer)


def family(model: str):
    return next(item for item in normalizer.FAMILIES if item.model == model)


class NozzleCapabilityTests(unittest.TestCase):
    def test_only_x1c_and_k2_use_cm2_cht(self) -> None:
        cht_models = {
            item.model
            for item in normalizer.FAMILIES
            if item.nozzle_capability == "cm2_cht"
        }
        self.assertEqual(cht_models, {"Bambu Lab X1 Carbon", "Creality K2 Plus"})
        self.assertEqual(
            MICRO_SWISS_CHT_BUCKETS,
            {"Bambu X1C HF", "Creality K2 Plus"},
        )
        self.assertEqual(
            MICRO_SWISS_CM2_BUCKETS,
            {
                "Bambu X1C HF",
                "Creality K2 Plus",
                "Elegoo Centauri",
                "FibreSeek 3",
                "Prusa Core One",
                "Qidi X-Plus 4",
                "RatRig V-Core 4",
                "Sovol SV08 MAX",
            },
        )

    def test_standard_cm2_machines_are_not_labeled_high_flow(self) -> None:
        for model in (
            "Elegoo Centauri Carbon",
            "Prusa CORE One L",
            "Qidi X-Plus 4",
            "QidiMaxEz",
            "RatRig V-Core 4 IDEX 500",
            "Sovol SV08 MAX",
            "FibreSeek Seeker 3",
        ):
            selected = family(model)
            self.assertEqual(selected.nozzle_capability, "cm2_standard")
            self.assertEqual(normalizer.nozzle_flow_types(selected, 1), ["Standard"])

    def test_h2d_retains_native_high_flow_and_snapmaker_stays_standard(self) -> None:
        h2d = family("Bambu Lab H2D")
        snapmaker = family("Snapmaker U1")
        self.assertEqual(h2d.nozzle_capability, "stock_high_flow")
        self.assertEqual(normalizer.nozzle_flow_types(h2d, 1), ["High Flow"])
        self.assertEqual(snapmaker.nozzle_capability, "stock_standard")
        self.assertEqual(normalizer.nozzle_flow_types(snapmaker, 1), ["Standard"])

    def test_cht_speed_gain_targets_hidden_paths(self) -> None:
        x1c = normalizer.mode_settings(normalizer.QUALITY_MODE, "0.4", family("Bambu Lab X1 Carbon"))
        k2 = normalizer.mode_settings(normalizer.QUALITY_MODE, "0.4", family("Creality K2 Plus"))
        qidi = normalizer.mode_settings(normalizer.QUALITY_MODE, "0.4", family("Qidi X-Plus 4"))

        self.assertEqual(x1c["inner_wall_speed"], "120")
        self.assertEqual(x1c["sparse_infill_speed"], "156")
        self.assertEqual(x1c["outer_wall_speed"], "63")
        self.assertEqual(k2["inner_wall_speed"], "120")
        self.assertEqual(qidi["inner_wall_speed"], "100")
        self.assertEqual(qidi["sparse_infill_speed"], "130")
        self.assertEqual(qidi["default_acceleration"], "6000")

    def test_only_cht_buckets_select_high_flow_reference_values(self) -> None:
        contract = load_contract()
        for bucket in ("Bambu X1C HF", "Creality K2 Plus"):
            profile = apply_contract({}, "ABS", "Bambu", bucket, contract)
            self.assertEqual(profile["filament_max_volumetric_speed"], ["25"])

        for bucket in ("Elegoo Centauri", "Prusa Core One", "Qidi X-Plus 4"):
            profile = apply_contract({}, "ABS", "Bambu", bucket, contract)
            self.assertEqual(profile["filament_max_volumetric_speed"], ["16"])


if __name__ == "__main__":
    unittest.main()
