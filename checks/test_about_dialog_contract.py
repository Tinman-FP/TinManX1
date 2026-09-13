#!/usr/bin/env python3
"""Guard About branding and attribution; rendered layout is checked in the app."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/slic3r/GUI/AboutDialog.cpp").read_text(encoding="utf-8")
ABOUT = SOURCE.split("AboutDialog::AboutDialog()", 1)[1].split(
    "void AboutDialog::on_dpi_changed", 1
)[0]


class AboutDialogContract(unittest.TestCase):
    def assertContains(self, text, source):
        self.assertTrue(text in source, f"Missing About content: {text}")

    def test_native_identity_does_not_depend_on_svg_text(self):
        self.assertContains('"TinManX1_192px"', ABOUT)
        self.assertContains('"TinManX1"', ABOUT)
        self.assertContains("wxStaticText", ABOUT)
        self.assertContains("wxString::FromUTF8(TINMANX1_REVISION)", ABOUT)
        self.assertContains("GIT_COMMIT_HASH", ABOUT)
        self.assertFalse('"TinManX1_about' in ABOUT, "About identity must not rely on SVG text")

    def test_project_link_and_credit_entry_point(self):
        self.assertContains("https://github.com/Tinman-FP/TinManX1", ABOUT)
        self.assertContains("Credits and Licenses", ABOUT)
        self.assertFalse("https://www.orcaslicer.com" in ABOUT, "Primary link must point to TinManX1")

    def test_project_and_upstream_credits_are_visible(self):
        for name in (
            "William Tinney", "OpenAI Codex", "SoftFever", "Bambu Lab",
            "Prusa Research", "Alessandro Ranellucci", "SuperSlicer", "Cura",
        ):
            with self.subTest(name=name):
                self.assertContains(name, SOURCE)
        self.assertContains("PrusaSlicer 3.0.0-alpha11", ABOUT)
        self.assertContains("not a full PrusaSlicer 3 rebase", ABOUT)

    def test_feature_authors_and_license_remain_accessible(self):
        for name in (
            "Dennis Klappe", "Janis A. Andersons", "Salome Sanchez", "Tom Vaneker",
            "Steven McCulloch", "Nicolai Wachenschwan", "Kelsch", "Rieks Kaiser",
            "Anonoei", "Andrew Ellis", "Frix-x", "CNC Kitchen", "ModBot",
            "MechaniCalc", "Klipper", "Moonraker",
        ):
            with self.subTest(name=name):
                self.assertContains(name, SOURCE)
        self.assertContains("https://www.gnu.org/licenses/agpl-3.0.html", SOURCE)
        self.assertContains("ATTRIBUTION.md", SOURCE)
        self.assertContains("wxHW_SCROLLBAR_AUTO", SOURCE)

    def test_current_dependency_acknowledgments(self):
        for name in ("FFmpeg", "Clipper2", "OpenSSL", "OpenCV", "FreeType", "MCUT", "MD4C", "QOI", "Shapely"):
            with self.subTest(name=name):
                self.assertTrue(name in SOURCE, f"Missing dependency credit: {name}")


if __name__ == "__main__":
    unittest.main()
