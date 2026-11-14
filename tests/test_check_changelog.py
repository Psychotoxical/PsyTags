import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check_changelog", ROOT / "packaging" / "check_changelog.py")
check_changelog = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_changelog)

BASE = """# Changelog

## [Unreleased]

### Fixed

- bug

## [1.2.0] - 2026-01-02

### Added

- new
"""


class CheckChangelogTests(unittest.TestCase):
    def test_new_entry_under_unreleased_counts(self):
        head = BASE.replace("- bug\n", "- bug\n- another bug\n")
        self.assertEqual(check_changelog.new_entries(BASE, head), {"- another bug"})

    def test_no_change_or_change_elsewhere_does_not_count(self):
        self.assertEqual(check_changelog.new_entries(BASE, BASE), set())
        elsewhere = BASE.replace("- new\n", "- new\n- old version edited\n")
        self.assertEqual(check_changelog.new_entries(BASE, elsewhere), set())
        heading_only = BASE.replace("### Fixed", "### Fixed\n\n### Changed")
        self.assertEqual(check_changelog.new_entries(BASE, heading_only), set())

    def test_missing_unreleased_has_no_entries(self):
        self.assertEqual(check_changelog.unreleased_entries("# Changelog\n"), set())


if __name__ == "__main__":
    unittest.main()
