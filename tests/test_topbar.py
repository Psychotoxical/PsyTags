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
        self.window._autosave.stop()       # the test's config folder goes away before 20 s
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

    def test_the_header_controls_are_equally_high(self):
        from PySide6.QtWidgets import QLineEdit, QPushButton, QToolButton
        from psytags.ui import theme
        self.window.setStyleSheet(theme.style_sheet())
        self.window.show()
        self.addCleanup(self.window.hide)
        QApplication.processEvents()
        bar = self.bar.header_bar
        heights = {w.height() for w in bar.findChildren(QPushButton) + bar.findChildren(QLineEdit)
                   + [b for b in bar.findChildren(QToolButton) if b.objectName() == "MenuButton"]}
        self.assertEqual(len(heights), 1, heights)

    def test_the_bars_do_not_hold_the_window_wide(self):
        self.assertEqual(self.bar.minimumSizeHint().width(), 0)


class ShortcutTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _action(self, keys):
        from PySide6.QtGui import QAction, QKeySequence
        action = QAction()
        action.setShortcut(QKeySequence(keys))
        return action

    def test_windows_and_linux_name_the_keys(self):
        from psytags.i18n import set_language
        from psytags.ui import topbar
        set_language("de")
        self.addCleanup(set_language, "de")
        with mock.patch.object(topbar.sys, "platform", "win32"):
            self.assertEqual(topbar.shortcut_text(self._action("Ctrl+Shift+M")), "Strg+Umschalt+M")

    def test_a_mac_shows_its_symbols(self):
        from psytags.ui import topbar
        action = self._action("Ctrl+Shift+M")
        with mock.patch.object(topbar.sys, "platform", "darwin"), \
                mock.patch.object(topbar.QKeySequence, "toString", lambda seq, fmt: str(fmt)):
            self.assertIn("NativeText", topbar.shortcut_text(action))

    @unittest.skipUnless(os.sys.platform == "darwin", "only a Mac draws the symbols")
    def test_on_a_mac_ctrl_is_the_command_key(self):
        from psytags.ui import topbar
        self.assertEqual(topbar.shortcut_text(self._action("Ctrl+Shift+M")), "⇧⌘M")


class MacSystemKeyTests(unittest.TestCase):
    """⌘Q quits and ⌘H hides every Mac program; PsyTags puts its own on the Control key there."""

    def test_on_a_mac_q_and_h_go_to_control(self):
        from psytags.ui.mainwindow import mac_keys
        self.assertEqual(mac_keys("Ctrl+Q", "darwin"), "Meta+Q")
        self.assertEqual(mac_keys("Ctrl+H", "darwin"), "Meta+H")
        self.assertEqual(mac_keys("Ctrl+S", "darwin"), "Ctrl+S")

    def test_elsewhere_nothing_changes(self):
        from psytags.ui.mainwindow import mac_keys
        self.assertEqual(mac_keys("Ctrl+Q", "win32"), "Ctrl+Q")
        self.assertEqual(mac_keys("Ctrl+H", "linux"), "Ctrl+H")

    @unittest.skipUnless(os.sys.platform == "darwin", "only a Mac has the Command key")
    def test_the_window_uses_them(self):
        from PySide6.QtGui import QKeySequence
        from psytags.ui.mainwindow import MainWindow
        app = QApplication.instance() or QApplication([])  # noqa: F841
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with mock.patch.object(config, "config_dir", lambda: folder.name):
            w = MainWindow()
            w._autosave.stop()
            self.addCleanup(w.deleteLater)
            self.assertEqual(w.act_panel.shortcut(), QKeySequence("Meta+Q"))
            self.assertEqual(w.act_add_dir.shortcut(), QKeySequence("Meta+H"))


class ButtonOrderTests(unittest.TestCase):
    """macOS puts the default button on the right; PsyTags keeps the Windows order everywhere."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _order(self, sheet):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout
        old = self.app.styleSheet()
        self.addCleanup(self.app.setStyleSheet, old)
        self.app.setStyleSheet(sheet)
        d = QDialog()
        self.addCleanup(d.deleteLater)
        bb = QDialogButtonBox(d)
        for text, role in (("back", QDialogButtonBox.ButtonRole.AcceptRole),
                           ("next", QDialogButtonBox.ButtonRole.AcceptRole),
                           ("cancel", QDialogButtonBox.ButtonRole.RejectRole)):
            bb.addButton(text, role)
        QVBoxLayout(d).addWidget(bb)
        d.resize(500, 100)
        d.show()
        self.app.processEvents()
        return [b.text() for b in sorted(bb.buttons(), key=lambda b: b.x())]

    def test_the_mac_order_differs(self):
        self.assertEqual(self._order("QDialogButtonBox { button-layout: 1; }"), ["next", "cancel", "back"])

    def test_the_theme_keeps_back_next_cancel(self):
        from psytags.ui import theme
        self.assertEqual(self._order(theme.style_sheet()), ["back", "next", "cancel"])


if __name__ == "__main__":
    unittest.main()
