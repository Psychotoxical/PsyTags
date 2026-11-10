import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config


class Song:
    def __init__(self, path):
        self.path = path
        self.data = mock.MagicMock(covers=[])

    @property
    def folder(self):
        return os.path.dirname(self.path)

    def get(self, _name):
        return []


class PanelDirectoryTests(unittest.TestCase):
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
        from psytags.ui.mainwindow import MainWindow
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.panel = self.window.panel
        self.panel.set_directories("/musik/geoeffnet", ["/musik/geoeffnet", "/musik/alt"])

    def _shown(self):
        return self.panel.dir_combo.currentText()

    def test_the_field_shows_the_folder_of_the_selected_file(self):
        self.panel.load([Song("/musik/album/01.mp3")])
        self.assertEqual(self._shown(), os.path.normpath("/musik/album"))

    def test_several_albums_show_their_common_folder(self):
        self.panel.load([Song("/musik/a/01.mp3"), Song("/musik/b/01.mp3")])
        self.assertEqual(self._shown(), os.path.normpath("/musik"))

    def test_without_a_selection_the_opened_folder_is_shown(self):
        self.panel.load([Song("/musik/album/01.mp3")])
        self.panel.load([])
        self.assertEqual(self._shown(), "/musik/geoeffnet")

    def test_rebuilding_the_panel_keeps_the_real_folder(self):
        self.panel.load([Song("/musik/album/01.mp3")])
        self.panel.set_directories("/musik/geoeffnet", ["/musik/geoeffnet"])
        self.assertEqual(self._shown(), os.path.normpath("/musik/album"))

    def test_showing_a_folder_does_not_change_the_working_directory(self):
        before = self.window.current_dir
        with mock.patch.object(self.panel, "directory_chosen") as chosen:
            self.panel.load([Song("/musik/album/01.mp3")])
        chosen.emit.assert_not_called()
        self.assertEqual(self.window.current_dir, before)


if __name__ == "__main__":
    unittest.main()
