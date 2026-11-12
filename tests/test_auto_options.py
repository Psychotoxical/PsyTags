"""The options that switch steps of the automatic run on and off."""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags.config import Options
from psytags.ui import mainwindow
from psytags.ui.mainwindow import MainWindow
from psytags.websources import albumauto


def _window(**options):
    win = mock.MagicMock()
    win.opts = Options(**options)
    win._lastfm_enabled.return_value = False
    win._cover_big_enough.return_value = True
    win._fill_gaps.return_value = None          # no album with files added later
    win._run_albums.side_effect = lambda *a: MainWindow._run_albums(win, *a)
    return win


def _track(covers=()):
    return SimpleNamespace(data=SimpleNamespace(covers=list(covers)), get=lambda name: [])


def _import(win, tracks, interactive=False, complete=True, cover=None):
    plan = [(t, {"TITLE": "x"}) for t in tracks]
    return MainWindow._finish_source_import(win, "MusicBrainz", plan, cover, [], interactive, complete, ("r", "g"))


class NumberTests(unittest.TestCase):
    def test_numbers_are_written_by_default(self):
        win = _window()
        _import(win, [_track()])
        win._renumber.assert_called_once()

    def test_switched_off_no_numbers_are_written(self):
        win = _window(auto_numbers=False)
        _import(win, [_track()])
        win._renumber.assert_not_called()


class CoverTests(unittest.TestCase):
    def test_the_cover_sources_run_by_default(self):
        win = _window()
        _import(win, [_track()])
        win.fetch_cover_chain.assert_called_once()

    def test_switched_off_no_cover_is_fetched(self):
        win = _window(auto_cover=False)
        self.assertIsNone(_import(win, [_track()])[0])
        win.fetch_cover_chain.assert_not_called()

    def test_an_album_with_a_cover_keeps_it_if_wanted(self):
        win = _window(replace_covers=False)
        _import(win, [_track(["old"]), _track(["old"])], cover=b"new")
        win.fetch_cover_chain.assert_not_called()
        win._cover_big_enough.assert_not_called()

    def test_an_album_without_a_cover_still_gets_one(self):
        win = _window(replace_covers=False)
        _import(win, [_track(["old"]), _track()])
        self.assertTrue(win.fetch_cover_chain.call_args.kwargs["keep"])     # but the file with a cover keeps it

    def test_the_source_cover_goes_only_to_files_without_one(self):
        win = _window(replace_covers=False)
        win._write.side_effect = lambda label, tracks, apply: [apply(t) for t in tracks] and len(tracks)
        old, empty = _track(["old"]), _track()
        for t in (old, empty):
            t.set, t.get = (lambda *a: None), (lambda name: [])
        _import(win, [old, empty], cover=b"new")
        self.assertEqual(old.data.covers, ["old"])
        self.assertEqual(len(empty.data.covers), 1)

    def test_a_chain_cover_keeps_existing_ones_per_file(self):
        from psytags.ui import mainwindow as mw
        win = _window()
        win._write.side_effect = lambda label, tracks, apply: [apply(t) for t in tracks]
        old, empty = _track(["old"]), _track()
        mw._store_front_cover(win, [old, empty], b"new", "Test", False, keep=True)
        self.assertEqual(old.data.covers, ["old"])
        self.assertEqual(empty.data.covers[0].data, b"new")

    def test_a_manual_import_always_follows_the_users_choice(self):
        win = _window(replace_covers=False)
        _import(win, [_track(["old"])], interactive=True)
        win.fetch_cover_chain.assert_called_once()


class SummaryTests(unittest.TestCase):
    """A manual import only closes an album of the summary when it really wrote all of it."""

    def test_a_failed_write_leaves_the_album_open(self):
        win = _window()
        win._write.return_value = 0                  # nothing could be saved
        _import(win, [_track(), _track()], interactive=True)
        win._note_in_summary.assert_not_called()

    def test_a_complete_write_is_noted(self):
        win = _window()
        tracks = [_track(), _track()]
        win._write.return_value = 2
        _import(win, tracks, interactive=True)
        win._note_in_summary.assert_called_once()

    def test_part_of_an_album_does_not_close_it(self):
        from psytags.websources.albumauto import BatchEntry
        a, b = _track(), _track()
        entry = BatchEntry("A", [a, b], False, "offen")
        win = mock.MagicMock(_last_batch=[entry], _auto_done={})
        MainWindow._note_in_summary(win, "MusicBrainz", [a], ("", ""))
        self.assertFalse(entry.ok)
        self.assertEqual(win._auto_done, {})
        MainWindow._note_in_summary(win, "MusicBrainz", [a, b], ("", ""))
        self.assertTrue(entry.ok)


class ManualCoverTests(unittest.TestCase):
    """A manual search takes its cover from the cover sources, like the automatic."""

    def _run(self, ticked=True, **options):
        from psytags.ui.dialogs import tagsources as ts
        from psytags.websources.base import Album
        album = Album(tracks=1, lengths=["3:20"])
        album.fields = {"TITLE": ["One"], "ALBUM": ["A"], "MUSICBRAINZ_ALBUMID": ["rel"]}
        album.cover_url = "http://cover"
        source = SimpleNamespace(name="MusicBrainz", prefill=lambda t, title=None: ["A", "Ann"],
                                 search=lambda v: [{"_url": "1"}], album=lambda r: album, cover=lambda a: b"shown")
        win = _window(**options)
        win.view.selected_tracks.return_value = [_track()]
        win._background.side_effect = lambda label, call: call()
        with mock.patch.object(ts, "SearchDialog") as search, mock.patch.object(ts, "ResultsDialog") as results, \
                mock.patch.object(ts, "AdjustDialog") as adjust:
            search.return_value.values.return_value = ["A", "Ann"]
            results.return_value.exec.return_value = 1
            adjust.return_value.exec.return_value = 1
            adjust.return_value.plan.return_value = []
            adjust.return_value.use_cover.return_value = ticked
            adjust.return_value.album = album
            MainWindow.run_source(win, src=source)
        call = win._finish_source_import.call_args
        return call.args[2], call.kwargs["archive"]

    def test_the_cover_sources_decide_even_when_a_cover_was_shown(self):
        cover, archive = self._run()
        self.assertIsNone(cover)
        self.assertEqual(archive[0], "rel")

    def test_an_unticked_cover_means_no_cover(self):
        self.assertEqual(self._run(ticked=False), (None, ()))

    def test_with_the_cover_step_off_the_shown_cover_is_taken(self):
        self.assertEqual(self._run(auto_cover=False), (b"shown", ()))


class MoodTests(unittest.TestCase):
    def _run(self, **options):
        win = _window(**options)
        win.model.rows = [SimpleNamespace(folder="f", get=lambda name: ["A"])]
        win._auto_done = {}
        win._mood_done = set()
        win.analyze_moods.return_value = True
        with mock.patch.object(mainwindow, "_StayingProgress") as progress:
            progress.return_value.stop.is_set.return_value = False
            MainWindow.auto_all_albums(win)
        return win

    def test_moods_are_analyzed_first_by_default(self):
        self._run().analyze_moods.assert_called_once()

    def test_switched_off_the_run_starts_without_moods(self):
        win = self._run(auto_moods=False)
        win.analyze_moods.assert_not_called()
        win._auto_one.assert_called_once()


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        from psytags.i18n import set_language
        set_language("de")

    def test_durations_read_naturally(self):
        self.assertEqual(mainwindow.duration_text(12.4), "12 s")
        self.assertEqual(mainwindow.duration_text(245), "4 min 05 s")
        self.assertEqual(mainwindow.duration_text(3725), "1 h 02 min")

    def test_the_run_is_summed_up(self):
        from psytags.websources.albumauto import BatchEntry
        entries = [BatchEntry("A", [1, 2], True, ""), BatchEntry("B", [3], False, "")]
        self.assertEqual(mainwindow.run_statistics(entries, 90),
                         "2 Alben (3 Dateien) in 1 min 30 s: 1 erledigt, 1 offen")

    def test_the_run_ends_with_its_statistics(self):
        win = _window(auto_moods=False)
        win.model.rows = [SimpleNamespace(folder="f", get=lambda name: ["A"])]
        win._auto_done, win._mood_done = {}, set()
        win._auto_one.return_value = SimpleNamespace(ok=True, tracks=win.model.rows)
        with mock.patch.object(mainwindow, "_StayingProgress") as progress:
            progress.return_value.stop.is_set.return_value = False
            MainWindow.auto_all_albums(win)
        self.assertIn("1 erledigt, 0 offen", win.message.call_args.args[0])


class DigitalTests(unittest.TestCase):
    @staticmethod
    def _m(fmt):
        return SimpleNamespace(row={"_url": fmt, "Tracks": "12", "Format": fmt})

    def test_digital_editions_come_first_by_default(self):
        got = albumauto.candidate_rows([self._m("CD"), self._m("Digital Media")], 12)
        self.assertEqual([r["_url"] for r in got], ["Digital Media", "CD"])

    def test_switched_off_the_order_of_the_search_stays(self):
        got = albumauto.candidate_rows([self._m("CD"), self._m("Digital Media")], 12, prefer_digital=False)
        self.assertEqual([r["_url"] for r in got], ["CD", "Digital Media"])

    def test_switched_off_the_score_alone_sorts_the_results(self):
        rows = [{"_url": "cd", "Score": "100", "Tracks": "9", "Format": "CD"},
                {"_url": "digital", "Score": "100", "Tracks": "9", "Format": "Digital Media"}]
        self.assertEqual([r["_url"] for r in albumauto.digital_first(rows, 9, False)], ["cd", "digital"])

    def test_switched_off_no_release_counts_as_digital(self):
        album = SimpleNamespace(tracks=0, lengths=[], value=lambda name, i: "")
        self.assertTrue(albumauto.to_release(album, {"Format": "Digital Media"}).digital)
        self.assertFalse(albumauto.to_release(album, {"Format": "Digital Media"}, prefer_digital=False).digital)


if __name__ == "__main__":
    unittest.main()
