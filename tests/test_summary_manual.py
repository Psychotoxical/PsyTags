"""An album of the automatic run that is tagged by hand leaves the open rows of the summary."""
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags.ui import mainwindow as mw
from psytags.websources import albumauto


def track(path=""):
    return NS(data=NS(covers=[]), get=lambda name: [], path=path)


class ManualSaveTests(unittest.TestCase):
    def _note(self, entry, written, leftovers=()):
        win = mock.MagicMock(_last_batch=[entry], _auto_done={})
        mw.MainWindow._note_in_summary(win, "MusicBrainz", written, ("", ""), list(leftovers))
        return win

    def test_files_without_a_track_that_went_to_the_bin_do_not_keep_it_open(self):
        tagged, gone = track(), track(os.path.join(tempfile.gettempdir(), "psytags-gone", "bonus.flac"))
        e = albumauto.BatchEntry("A", [tagged, gone], False, "Keine passende Ausgabe gefunden")
        self._note(e, [tagged], [gone])
        self.assertTrue(e.ok)
        self.assertEqual(e.leftovers, [])

    def test_files_without_a_track_that_were_kept_are_listed_for_the_bin(self):
        with tempfile.NamedTemporaryFile(suffix=".flac") as f:
            tagged, kept = track(), track(f.name)
            e = albumauto.BatchEntry("A", [tagged, kept], False, "Keine passende Ausgabe gefunden")
            self._note(e, [tagged], [kept])
            self.assertTrue(e.ok)
            self.assertEqual(e.leftovers, [kept])

    def test_an_album_only_partly_saved_stays_open(self):
        tagged, other = track(), track()
        e = albumauto.BatchEntry("A", [tagged, other], False, "Keine passende Ausgabe gefunden")
        self._note(e, [tagged])
        self.assertFalse(e.ok)


if __name__ == "__main__":
    unittest.main()
