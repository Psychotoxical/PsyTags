import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QMainWindow

from psytags import config
from psytags.ui import persist


class WindowRestoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _window_on(self, desktop):
        from psytags.ui.mainwindow import MainWindow
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
            window = MainWindow()
            window._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(window.deleteLater)
        return window

    def _fullscreen_geometry(self):
        source = QMainWindow()
        self.addCleanup(source.deleteLater)
        source.showFullScreen()
        self.app.processEvents()
        return source.saveGeometry()

    def _save_on(self, desktop, window):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
            window.settings.setValue(persist.geometry_key("window/geometry"), self._fullscreen_geometry())
            window.settings.sync()

    def _dialog_on(self, desktop):
        dialog = QDialog()
        self.addCleanup(dialog.deleteLater)
        dialog.resize(333, 222)
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
            persist.remember(dialog, "probe")
        return dialog

    def _close_resized_on(self, desktop):
        dialog = self._dialog_on(desktop)
        dialog.resize(611, 407)
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desktop}):
            dialog.done(0)

    def test_dialog_size_returns_on_the_desktop_it_was_saved_on(self):
        self._close_resized_on("tiling")
        self.assertEqual(self._dialog_on("tiling").size().toTuple(), (611, 407))

    def test_dialog_size_does_not_carry_over_to_another_desktop(self):
        self._close_resized_on("tiling")
        self.assertEqual(self._dialog_on("floating").size().toTuple(), (333, 222))

    def test_fullscreen_returns_on_the_desktop_it_was_saved_on(self):
        self._save_on("tiling", self._window_on("tiling"))
        self.assertTrue(self._window_on("tiling").isFullScreen())

    def test_fullscreen_does_not_carry_over_to_another_desktop(self):
        self._save_on("tiling", self._window_on("tiling"))
        self.assertFalse(self._window_on("floating").isFullScreen())

    def test_without_a_desktop_name_the_plain_key_is_used(self):
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": ""}):
            self.assertEqual(persist.geometry_key("window/geometry"), "window/geometry")


if __name__ == "__main__":
    unittest.main()

    def _owner(self, x, y):
        owner = QMainWindow()
        self.addCleanup(owner.deleteLater)
        owner.setGeometry(x, y, 300, 200)
        owner.show()
        self.app.processEvents()
        return owner

    def _child(self, owner, show=True):
        dialog = QDialog(owner)
        dialog.resize(200, 100)
        persist.remember(dialog, "child")
        if show:
            dialog.show()
            self.app.processEvents()
        return dialog

    def test_a_moved_dialog_keeps_its_place_relative_to_its_window(self):
        owner = self._owner(100, 100)
        dialog = self._child(owner)
        dialog.move(owner.pos().x() + 40, owner.pos().y() + 60)
        dialog.done(0)
        owner.move(300, 250)
        self.app.processEvents()
        again = self._child(owner, show=False)
        self.assertEqual((again.pos() - owner.pos()).toTuple(), (40, 60))

    def test_a_dialog_nobody_moved_stays_centred(self):
        owner = self._owner(100, 100)
        self._child(owner).done(0)
        again = self._child(owner, show=False)
        self.assertFalse(again.testAttribute(Qt.WidgetAttribute.WA_Moved))

    def test_a_place_outside_every_screen_is_not_used(self):
        owner = self._owner(100, 100)
        dialog = self._child(owner)
        dialog.move(owner.pos().x() + 40, owner.pos().y() + 60)
        dialog.done(0)
        owner.move(5000, 5000)                  # the window went to a screen that is gone now
        self.app.processEvents()
        again = self._child(owner, show=False)
        self.assertFalse(again.testAttribute(Qt.WidgetAttribute.WA_Moved))

    def test_a_geometry_of_an_older_version_gives_the_size_but_not_the_place(self):
        old = QDialog()
        self.addCleanup(old.deleteLater)
        old.setGeometry(500, 400, 410, 310)
        s = config.settings()
        s.setValue(persist.geometry_key("dialogs/child/geometry"), old.saveGeometry())
        again = self._child(self._owner(100, 100), show=False)
        self.assertEqual(again.size().toTuple(), (410, 310))
        self.assertFalse(again.testAttribute(Qt.WidgetAttribute.WA_Moved))
