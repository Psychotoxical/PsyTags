import importlib.util
import pathlib
import unittest

import psytags

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("release_notes", ROOT / "packaging" / "release_notes.py")
release_notes = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(release_notes)

SAMPLE = """# Changelog

## [1.2.0] - 2026-01-02

### Added

- new

## [1.1.0] - 2026-01-01

### Fixed

- old
"""


class ChangelogTests(unittest.TestCase):
    def test_current_version_has_a_section(self):
        # the release draft takes its text from this section
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertTrue(release_notes.section(text, psytags.__version__),
                        f"CHANGELOG.md needs a section '## [{psytags.__version__}]'")

    def test_script_reads_the_package_version(self):
        self.assertEqual(release_notes.package_version(), psytags.__version__)

    def test_section_stops_at_the_next_version(self):
        self.assertEqual(release_notes.section(SAMPLE, "1.2.0"), "### Added\n\n- new")
        self.assertEqual(release_notes.section(SAMPLE, "1.1.0"), "### Fixed\n\n- old")

    def test_missing_version_is_an_error(self):
        self.assertEqual(release_notes.section(SAMPLE, "1.3.0"), "")
        with self.assertRaises(ValueError):
            release_notes.notes(SAMPLE, "1.3.0")

    def test_notes_lift_headings_and_list_all_downloads(self):
        text = release_notes.notes(SAMPLE, "1.2.0")
        self.assertTrue(text.startswith("## Added\n\n- new"))
        for name in ("PsyTags-Setup-1.2.0.exe", "psytags_1.2.0_amd64.deb",
                     "psytags-1.2.0-1.x86_64.rpm", "PsyTags-x86_64.AppImage"):
            self.assertIn(name, text)


if __name__ == "__main__":
    unittest.main()
