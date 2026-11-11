"""Removing files from the list: the tag panel follows."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.track import Track


def track(title):
    t = Track(f"{title}.mp3")
    t.set("TITLE", title)
    t.set("ALBUM", "Album")
    return t


class RemoveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        os.makedirs(os.path.join(d.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: d.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _window(self, tracks):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        w._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(w.deleteLater)
        w.model.set_tracks(tracks)
        w.view.select_tracks(tracks)
        return w

    def test_removing_everything_empties_the_panel(self):
        w = self._window([track("a"), track("b")])
        self.assertTrue(w.panel.combos["ALBUM"].isEnabled())
        w.remove_from_list()
        self.assertEqual(w.model.rows, [])
        self.assertEqual(w.panel.tracks, [])
        self.assertEqual(w.panel.combos["ALBUM"].currentText(), "")
        self.assertFalse(w.panel.combos["ALBUM"].isEnabled())

    def test_removing_some_shows_the_next_file(self):
        a, b, c = track("a"), track("b"), track("c")
        w = self._window([a, b, c])
        w.view.select_tracks([a])
        w.remove_from_list()
        self.assertEqual(w.panel.tracks, [b])
        self.assertEqual(w.panel.combos["TITLE"].currentText(), "b")


if __name__ == "__main__":
    unittest.main()
