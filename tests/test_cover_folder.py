"""Adding a cover from a file starts in the folder of the selected album."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.track import Track


class CoverFolderTests(unittest.TestCase):
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

    def _start_folder(self, *paths):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        w._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(w.deleteLater)
        w.current_dir = os.path.join(tempfile.gettempdir(), "zuletzt")
        w.panel.load([Track(p) for p in paths])
        with mock.patch("psytags.ui.mainwindow.QFileDialog.getOpenFileName", return_value=("", "")) as ask:
            w._cover_command("add")
        return ask.call_args.args[2], w.current_dir

    def test_one_album_starts_in_its_folder(self):
        album = os.path.join(tempfile.gettempdir(), "Band - Album")
        start, _last = self._start_folder(os.path.join(album, "01.mp3"), os.path.join(album, "02.mp3"))
        self.assertEqual(start, album)

    def test_several_folders_start_where_the_last_one_was(self):
        start, last = self._start_folder(os.path.join(tempfile.gettempdir(), "A", "01.mp3"), os.path.join(tempfile.gettempdir(), "B", "01.mp3"))
        self.assertEqual(start, last)


if __name__ == "__main__":
    unittest.main()
