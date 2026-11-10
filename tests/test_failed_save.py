"""Inputs in the tag panel survive a failed save."""
import os
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QApplication, QMessageBox

from psytags import config
from psytags.track import Track

Button = QMessageBox.StandardButton


class FailedSaveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not available")
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tracks = []
        for i in range(2):
            p = os.path.join(folder.name, f"{i}.mp3")
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                            "anullsrc=r=44100:cl=stereo", "-t", "0.2", "-c:a", "libmp3lame", p],
                           check=True)
            t = Track(p).load()
            t.set("TITLE", f"Before {i}")
            t.save()
            self.tracks.append(t)
        from psytags.ui.mainwindow import MainWindow
        self.window = MainWindow()
        self.addCleanup(self.window.deleteLater)
        self.window.model.set_tracks(self.tracks)
        self.window.view.select_tracks([self.tracks[0]])
        title = self.window.panel.combos["TITLE"]
        title.setEditText("Unsaved edit")
        title.dirty = True

    def _failing(self, answer):
        """Every save fails; the question after the failure gets ``answer``."""
        stack = mock.patch.multiple(
            "psytags.ui.mainwindow.QMessageBox",
            warning=mock.DEFAULT,
            question=mock.DEFAULT,
        )
        mocks = stack.start()
        self.addCleanup(stack.stop)
        mocks["question"].return_value = answer
        save = mock.patch.object(Track, "save", side_effect=PermissionError("read only"))
        save.start()
        self.addCleanup(save.stop)
        return mocks

    def _title(self):
        return self.window.panel.combos["TITLE"].currentText()

    def test_failed_save_keeps_selection_and_inputs(self):
        self._failing(Button.Cancel)
        self.window.view.select_tracks([self.tracks[1]])
        self.assertEqual(self.window.view.selected_tracks(), [self.tracks[0]])
        self.assertEqual(self._title(), "Unsaved edit")
        self.assertTrue(self.window.panel.dirty)

    def test_dropping_the_inputs_moves_on(self):
        self._failing(Button.Discard)
        self.window.view.select_tracks([self.tracks[1]])
        self.assertEqual(self.window.view.selected_tracks(), [self.tracks[1]])
        self.assertEqual(self._title(), "Before 1")

    def test_failure_is_reported_once(self):
        mocks = self._failing(Button.Cancel)
        self.window.view.select_tracks([self.tracks[1]])
        self.assertEqual(mocks["warning"].call_count, 0)
        self.assertEqual(mocks["question"].call_count, 1)
        self.assertIn("read only", mocks["question"].call_args[0][2])

    def test_close_waits_when_save_failed(self):
        self._failing(Button.Cancel)
        e = QCloseEvent()
        self.window.closeEvent(e)
        self.assertFalse(e.isAccepted())
        self.assertEqual(self._title(), "Unsaved edit")

    def test_opening_a_folder_waits_when_save_failed(self):
        self._failing(Button.Cancel)
        before = self.window.current_dir
        self.window.load_paths([tempfile.gettempdir()], False)
        self.assertEqual(self.window.current_dir, before)
        self.assertEqual(self._title(), "Unsaved edit")

    def test_close_goes_on_after_dropping(self):
        self._failing(Button.Discard)
        e = QCloseEvent()
        self.window.closeEvent(e)
        self.assertTrue(e.isAccepted())


if __name__ == "__main__":
    unittest.main()
