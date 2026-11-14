import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("bump_version", ROOT / "packaging" / "bump_version.py")
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)

MAIN = """# Changelog

Intro.

## [Unreleased]

### Added

- later
- feature

### Fixed

- bug

## [1.2.0] - 2026-01-02

### Added

- new
"""


class BumpVersionTests(unittest.TestCase):
    def test_next_version_skips_released_ones(self):
        self.assertEqual(bump_version.next_version("1.2.0", {"1.2.0"}), "1.2.1")
        self.assertEqual(bump_version.next_version("1.2.0", {"1.2.0", "1.2.1"}), "1.2.2")
        self.assertEqual(bump_version.next_version("1.2.1", {"1.2.0"}), "1.2.1")

    def test_version_lines_are_replaced(self):
        self.assertEqual(bump_version.set_init_version('__version__ = "1.2.0"\n', "1.2.1"),
                         '__version__ = "1.2.1"\n')
        project = '[project]\nversion = "1.2.0"\n\n[tool.ruff]\ntarget-version = "py311"\n'
        self.assertEqual(bump_version.set_pyproject_version(project, "1.2.1"),
                         '[project]\nversion = "1.2.1"\n\n[tool.ruff]\ntarget-version = "py311"\n')

    def test_unreleased_becomes_the_new_section(self):
        text = bump_version.release_unreleased(MAIN, "1.2.1", "2026-02-03")
        self.assertIn("## [Unreleased]\n\n## [1.2.1] - 2026-02-03\n\n### Added\n\n- later\n- feature\n\n"
                      "### Fixed\n\n- bug\n\n## [1.2.0] - 2026-01-02", text)
        self.assertTrue(text.startswith("# Changelog\n\nIntro.\n\n"))

    def test_existing_section_is_left_alone(self):
        self.assertEqual(bump_version.release_unreleased(MAIN, "1.2.0", "2026-02-03"), MAIN)

    def test_empty_unreleased_is_an_error(self):
        empty = "# Changelog\n\n## [Unreleased]\n\n## [1.2.0] - 2026-01-02\n\n- new\n"
        with self.assertRaises(ValueError):
            bump_version.release_unreleased(empty, "1.2.1", "2026-02-03")

    def test_sync_moves_released_entries_out_of_unreleased(self):
        # 'later' came to main after the release candidate and stays unreleased
        released = bump_version.release_unreleased(MAIN.replace("- later\n", ""), "1.2.1", "2026-02-03")
        text = bump_version.sync_released(MAIN, released, "1.2.1")
        self.assertIn("## [Unreleased]\n\n### Added\n\n- later\n\n## [1.2.1] - 2026-02-03\n\n"
                      "### Added\n\n- feature\n\n### Fixed\n\n- bug\n\n## [1.2.0]", text)
        self.assertEqual(bump_version.sync_released(text, released, "1.2.1"), text)

    def test_sync_with_nothing_left_keeps_an_empty_unreleased(self):
        released = bump_version.release_unreleased(MAIN, "1.2.1", "2026-02-03")
        self.assertEqual(bump_version.sync_released(MAIN, released, "1.2.1"), released)

    def test_sync_needs_the_released_section(self):
        with self.assertRaises(ValueError):
            bump_version.sync_released(MAIN, MAIN, "1.2.1")


if __name__ == "__main__":
    unittest.main()
