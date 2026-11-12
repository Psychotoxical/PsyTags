"""The steps MusicBrainz, numbers, cover and genres also run on the whole list."""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags.ui import mainwindow
from psytags.ui.mainwindow import MainWindow


def _track(album, release=""):
    fields = {"ALBUM": [album], "ALBUMARTIST": ["Band"]}
    if release:
        fields["MUSICBRAINZ_ALBUMID"] = [release]
    return SimpleNamespace(folder=album, get=lambda name: fields.get(name, []))


def _window(rows):
    win = mock.MagicMock(_auto_done={}, _mood_done={})
    win.model.rows = rows
    win._fill_gaps.return_value = None
    win._run_albums.side_effect = lambda *a: MainWindow._run_albums(win, *a)
    win._auto_one.side_effect = lambda src, tracks: SimpleNamespace(ok=True, tracks=tracks)
    return win


def _run(win, method):
    with mock.patch.object(mainwindow, "_StayingProgress") as progress:
        progress.return_value.stop.is_set.return_value = False
        method(win)


class MusicBrainzAllTests(unittest.TestCase):
    def test_albums_with_a_release_are_skipped(self):
        tagged = [_track("Album 1", "release-1"), _track("Album 1", "release-1")]
        open_ = [_track("Album 2")]
        win = _window(tagged + open_)
        _run(win, MainWindow.musicbrainz_all)
        self.assertEqual([c.args[1] for c in win._auto_one.call_args_list], [open_])

    def test_an_album_with_added_files_is_not_skipped(self):
        album = [_track("Album 1", "release-1"), _track("Album 1")]
        win = _window(album)
        _run(win, MainWindow.musicbrainz_all)
        win._fill_gaps.assert_called_once_with(album)

    def test_no_moods_are_analyzed(self):
        win = _window([_track("Album 2")])
        _run(win, MainWindow.musicbrainz_all)
        win.analyze_moods.assert_not_called()

    def test_with_everything_tagged_nothing_runs(self):
        win = _window([_track("Album 1", "release-1")])
        _run(win, MainWindow.musicbrainz_all)
        win._auto_one.assert_not_called()
        self.assertIn("MusicBrainz", win.message.call_args.args[0])


class OtherStepsTests(unittest.TestCase):
    def test_numbers_take_the_given_files(self):
        from psytags.websources import albumauto
        rows = [_track("Album 1"), _track("Album 2")]
        win = mock.MagicMock()
        win.view.selected_tracks.return_value = []
        with mock.patch.object(albumauto, "group_albums", return_value=[rows[:1], rows[1:]]) as groups:
            MainWindow.number_selected(win, rows)
        groups.assert_called_once_with(rows)
        self.assertEqual(win._renumber.call_count, 2)

    def test_numbers_without_files_use_the_selection(self):
        from psytags.websources import albumauto
        chosen = [_track("Album 1")]
        win = mock.MagicMock()
        win.view.selected_tracks.return_value = chosen
        with mock.patch.object(albumauto, "group_albums", return_value=[chosen]) as groups:
            MainWindow.number_selected(win)
        groups.assert_called_once_with(chosen)

    def test_covers_take_the_given_files(self):
        rows = [_track("Album 1")]
        win = mock.MagicMock()
        win.view.selected_tracks.return_value = []
        win.fetch_cover_chain.return_value = ""
        MainWindow.fetch_covers(win, rows)
        win.fetch_cover_chain.assert_called_once()
        self.assertEqual(win.fetch_cover_chain.call_args.args[0], rows)


class WiringTests(unittest.TestCase):
    """The buttons of the real window call the selection or the whole list."""

    def test_selection_and_all_reach_their_function(self):
        import tempfile
        from PySide6.QtWidgets import QApplication
        from psytags import config
        app = QApplication.instance() or QApplication([])  # noqa: F841
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        with mock.patch.object(config, "config_dir", lambda: folder.name):
            w = MainWindow()
        w._autosave.stop()
        self.addCleanup(w.deleteLater)
        rows = [object()]
        w.model.rows = rows
        for name, selection, everything in (("number_selected", w.act_numbers, w.act_numbers_all),
                                            ("fetch_covers", w.act_cover_fetch, w.act_cover_fetch_all)):
            spy = mock.MagicMock()
            setattr(w, name, spy)
            selection.setEnabled(True)
            selection.trigger()
            everything.setEnabled(True)
            everything.trigger()
            self.assertEqual([c.args for c in spy.call_args_list], [(), (rows,)], name)
        w.fetch_lastfm = mock.MagicMock()
        w.act_lastfm_all.setEnabled(True)
        w.act_lastfm_all.trigger()
        w.fetch_lastfm.assert_called_once_with(rows)
        w.musicbrainz_all = mock.MagicMock()
        w.act_auto_mb_all.setEnabled(True)
        w.act_auto_mb_all.trigger()
        w.musicbrainz_all.assert_called_once()


if __name__ == "__main__":
    unittest.main()
