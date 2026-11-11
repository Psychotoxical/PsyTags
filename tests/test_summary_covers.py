import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags.ui import mainwindow as mw
from psytags.websources import albumauto


def track(*covers):
    return NS(data=NS(covers=list(covers)), get=lambda name: [])


def cover(data, kind=3):
    return NS(data=data, type=kind)


def failed_entry(*tracks):
    entry = albumauto.BatchEntry("A", list(tracks), True, "A (2001) · kein Treffer", [], "kein Treffer", "")
    mw._remember_covers(entry)
    return entry


class NoticeTests(unittest.TestCase):
    def _notice(self, entry):
        mw.MainWindow._notice_new_covers(mock.MagicMock(_last_batch=[entry]))

    def test_a_new_cover_from_anywhere_ticks_the_box(self):
        t = track()
        e = failed_entry(t)
        t.data.covers = [cover(b"von Apple")]
        self._notice(e)
        self.assertEqual((e.cover, e.detail), ("", "A (2001)"))

    def test_a_replaced_old_cover_counts_too(self):
        t = track(cover(b"alt"))
        e = failed_entry(t)
        t.data.covers = [cover(b"neu")]
        self._notice(e)
        self.assertEqual(e.cover, "")

    def test_an_old_cover_that_stays_is_no_success(self):
        e = failed_entry(track(cover(b"alt")))
        self._notice(e)
        self.assertEqual((e.cover, e.detail), ("kein Treffer", "A (2001) · kein Treffer"))

    def test_only_the_front_cover_counts(self):
        t = track(cover(b"alt"))
        e = failed_entry(t)
        t.data.covers.append(cover(b"hinten", 4))
        self._notice(e)
        self.assertEqual(e.cover, "kein Treffer")

    def test_one_changed_file_of_an_album_is_enough(self):
        a, b = track(), track()
        e = failed_entry(a, b)
        b.data.covers = [cover(b"neu")]
        self._notice(e)
        self.assertEqual(e.cover, "")

    def test_an_entry_without_a_record_stays_as_it_is(self):
        t = track()
        e = albumauto.BatchEntry("A", [t], True, "A · kein Treffer", [], "kein Treffer", "")
        t.data.covers = [cover(b"neu")]
        self._notice(e)
        self.assertEqual(e.cover, "kein Treffer")

    def test_a_working_cover_step_needs_no_record(self):
        e = albumauto.BatchEntry("A", [track()], True, "A", [], "", "")
        mw._remember_covers(e)
        self.assertIsNone(e.cover_seen)


class WiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_the_run_records_the_covers_of_a_failed_step(self):
        t = track(cover(b"alt"))
        win = mock.MagicMock(_group_errors=[])
        win._background.side_effect = lambda label, call: call()
        win._import_match.return_value = ("kein Treffer", "")
        match = mock.MagicMock(leftover_keys=[], missing_last=False)
        with mock.patch.object(albumauto, "find_album", return_value=NS(match=match, reason="")), \
                mock.patch.object(albumauto, "album_title", return_value="A"), \
                mock.patch.object(albumauto, "release_label", return_value="A (2001)"):
            entry = mw.MainWindow._auto_one(win, NS(name="MusicBrainz"), [t])
        self.assertEqual(entry.cover_seen, mw._front_covers([t]))

    def _summary(self, win, dialogs):
        from psytags.ui.dialogs import tagsources as ts
        with mock.patch.object(ts, "BatchSummaryDialog", side_effect=dialogs):
            mw.MainWindow.show_batch_summary(win)

    def test_opening_the_summary_looks_at_the_files(self):
        win = mock.MagicMock(_last_batch=[object()])
        closed = mock.MagicMock(chosen=None, action="")
        closed.exec.return_value = 0
        self._summary(win, [closed])
        win._notice_new_covers.assert_called_once()

    def test_a_manually_tagged_album_is_recorded_too(self):
        t = track()
        e = albumauto.BatchEntry("A", [t], False, "offen", [], None, None)
        win = mock.MagicMock(_last_batch=[e], _auto_done={})
        mw.MainWindow._note_in_summary(win, "MusicBrainz", [t], ("kein Treffer", ""))
        self.assertEqual(e.cover_seen, mw._front_covers([t]))


if __name__ == "__main__":
    unittest.main()
