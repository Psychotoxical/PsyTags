import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config


class FoldingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        from psytags.ui.mainwindow import MainWindow
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.bar = self.window.topbar

    def test_with_room_everything_is_shown(self):
        self.bar._fit(3000)
        self.assertEqual(self.bar.header_buttons[0].text(), self.bar.header_buttons[0].full_text)
        for step in self.bar.step_widgets:
            self.assertFalse(step.hint_label.isHidden())
            self.assertFalse(step.title_label.isHidden())
            self.assertEqual(step.toolTip(), "")

    def test_in_a_narrow_tile_the_steps_keep_their_number_and_a_tooltip(self):
        self.bar._fit(300)
        for step in self.bar.step_widgets[1:]:
            self.assertTrue(step.title_label.isHidden())
            self.assertTrue(step.hint_label.isHidden())
            self.assertIn(step.title_label.text(), step.toolTip())

    def test_header_buttons_fold_to_their_icon_and_stay_named(self):
        self.bar._fit(300)
        for button in self.bar.header_buttons:
            self.assertEqual(button.text(), "")
            self.assertFalse(button.icon().isNull())
            self.assertEqual(button.toolTip(), button.full_text)
            self.assertEqual(button.accessibleName(), button.full_text)

    def test_getting_wide_again_restores_the_full_bar(self):
        self.bar._fit(300)
        self.bar._fit(3000)
        self.assertEqual(self.bar.header_buttons[0].toolTip(), "")
        self.assertTrue(self.bar.header_buttons[0].icon().isNull())
        self.assertFalse(self.bar.step_widgets[1].title_label.isHidden())
        self.assertEqual(self.bar.step_widgets[0].title_label.text(), self.bar.step_widgets[0].title)

    def test_the_bars_do_not_hold_the_window_wide(self):
        self.assertEqual(self.bar.minimumSizeHint().width(), 0)


if __name__ == "__main__":
    unittest.main()
