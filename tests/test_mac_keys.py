"""Shortcuts on a Mac: system keys stay with macOS, the help speaks in Mac symbols."""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags.ui import keys


class MacTextTests(unittest.TestCase):
    def test_the_command_key_takes_ctrl(self):
        self.assertEqual(keys.mac_text("Strg+Shift+M"), "⇧⌘M")
        self.assertEqual(keys.mac_text("Ctrl+Alt+B"), "⌥⌘B")
        self.assertEqual(keys.mac_text("Alt+1"), "⌥1")

    def test_system_keys_go_to_control(self):
        self.assertEqual(keys.mac_text("Strg+Q"), "⌃Q")
        self.assertEqual(keys.mac_text("Ctrl+H"), "⌃H")
        self.assertEqual(keys.mac_text("Strg+Shift+Tab"), "⌃⇧⇥")

    def test_delete_and_clicks(self):
        self.assertEqual(keys.mac_text("Entf"), "⌫")
        self.assertEqual(keys.mac_text("Entfernen"), "Entfernen")
        self.assertEqual(keys.mac_text("Strg-Klick auf die Zeile"), "⌘-Klick auf die Zeile")

    def test_other_text_stays(self):
        self.assertEqual(keys.mac_text("F4 / F5, Taste Alt allein"), "F4 / F5, Taste Alt allein")


class MacKeysTests(unittest.TestCase):
    def test_only_a_mac_changes_keys(self):
        self.assertEqual(keys.mac_keys("Ctrl+Q", "darwin"), "Meta+Q")
        self.assertEqual(keys.mac_keys("Ctrl+Tab", "darwin"), "Meta+Tab")
        self.assertEqual(keys.mac_keys("Ctrl+Q", "win32"), "Ctrl+Q")
        self.assertEqual(keys.extra_keys("Del", "darwin"), ["Backspace"])
        self.assertEqual(keys.extra_keys("Del", "linux"), [])


class HelpTests(unittest.TestCase):
    def test_the_help_on_a_mac_shows_symbols(self):
        from psytags.i18n import set_language
        from psytags.ui import help as helppage
        set_language("de")
        with mock.patch.object(keys, "on_mac", return_value=True):
            text = helppage.page(helppage.SHORTCUTS_TOPIC)
        self.assertIn("⌃Q", text)
        self.assertNotIn("Strg", text)

    def test_elsewhere_the_help_stays(self):
        from psytags.i18n import set_language
        from psytags.ui import help as helppage
        set_language("de")
        with mock.patch.object(keys, "on_mac", return_value=False):
            self.assertIn("Strg+Q", helppage.page(helppage.SHORTCUTS_TOPIC))


if __name__ == "__main__":
    unittest.main()
