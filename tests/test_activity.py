import os
import tempfile
import unittest
import urllib.error
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from psytags import config
from psytags.websources import albumauto, http

MB = "https://musicbrainz.org/ws/2/release/"


class DescribeTests(unittest.TestCase):
    def test_musicbrainz_search(self):
        self.assertEqual(http.describe(MB + "?fmt=json&limit=50&query=release:x"), "MusicBrainz: Suche")

    def test_musicbrainz_album(self):
        self.assertEqual(http.describe(MB + "766e374e?inc=artists&fmt=json"), "MusicBrainz: Album-Daten")

    def test_cover_art_archive(self):
        self.assertEqual(http.describe("https://coverartarchive.org/release/x/front-1200"), "Cover Art Archive: Cover")

    def test_lastfm_never_shows_the_key(self):
        text = http.describe("https://ws.audioscrobbler.com/2.0/?method=album.gettoptags&api_key=GEHEIM&artist=x")
        self.assertEqual(text, "Last.fm: Genres")

    def test_any_other_server_shows_only_its_name(self):
        text = http.describe("https://music.apple.com/de/search?term=geheim&token=GEHEIM")
        self.assertEqual(text, "music.apple.com")


class RunningTests(unittest.TestCase):
    def test_nothing_runs_at_rest(self):
        self.assertEqual(http.running(), [])

    def test_activity_is_listed_while_it_lasts(self):
        with http.activity("eins"):
            with http.activity("zwei"):
                self.assertEqual(http.running(), ["eins", "zwei"])
        self.assertEqual(http.running(), [])

    def test_an_error_does_not_leave_it_behind(self):
        with self.assertRaises(ValueError):
            with http.activity("eins"):
                raise ValueError
        self.assertEqual(http.running(), [])

    def test_a_request_is_listed_while_it_runs(self):
        seen = []

        def opened(req, timeout):
            seen.append(http.running())
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", {}, None)
        with mock.patch.object(http.urllib.request, "urlopen", opened):
            with self.assertRaises(http.NotFound):
                http.fetch_bytes("https://coverartarchive.org/release/x/front")
        self.assertEqual(seen, [["Cover Art Archive: Cover"]])
        self.assertEqual(http.running(), [])


class AlbumSearchTests(unittest.TestCase):
    def test_a_busy_musicbrainz_is_shown_while_waiting(self):
        seen = []
        replies = [http.ServerError("musicbrainz.org antwortet gerade nicht (HTTP 503)"), "ok"]

        def call():
            reply = replies.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        with mock.patch.object(albumauto.time, "sleep", side_effect=lambda s: seen.append(http.running())):
            self.assertEqual(albumauto._polite(call), "ok")
        self.assertIn(["MusicBrainz ist ausgelastet, neuer Versuch gleich"], seen)

    def test_the_editions_are_counted(self):
        seen = []
        track = NS(get=lambda name: [])

        def run_album(src, url, prev):
            seen.append(http.running())
            return mock.MagicMock()
        with mock.patch.object(albumauto, "search_rows", return_value=[]), \
                mock.patch.object(albumauto.coverfetch, "rank", return_value=[]), \
                mock.patch.object(albumauto, "candidate_rows", return_value=[{}, {}]), \
                mock.patch.object(albumauto.runner, "album_target", return_value=("u", "p")), \
                mock.patch.object(albumauto.runner, "run_album", run_album), \
                mock.patch.object(albumauto, "_polite", lambda call: call()), \
                mock.patch.object(albumauto, "_fits_album", return_value=False), \
                mock.patch.object(albumauto, "file_infos", return_value=[]), \
                mock.patch.object(albumauto.albummatch, "decide", return_value=NS(match=None, reason="x")):
            albumauto._search(None, [track], "A", [], "A")
        self.assertEqual(seen, [["Ausgabe 1 von 2"], ["Ausgabe 2 von 2"]])


class WindowTests(unittest.TestCase):
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

    def _dialog(self):
        from psytags.ui.mainwindow import _StayingProgress
        d = _StayingProgress("Titel", 3, None)
        self.addCleanup(d.finish)
        return d

    def test_the_line_is_hidden_unless_it_is_wanted(self):
        d = self._dialog()
        self.assertTrue(d.activity_label.isHidden())
        self.assertFalse(d.activity_timer.isActive())

    def test_it_shows_what_is_running(self):
        d = self._dialog()
        d.follow_activity()
        self.assertFalse(d.activity_label.isHidden())
        with http.activity("Ausgabe 1 von 2"), http.activity("MusicBrainz: Album-Daten"):
            d.show_activity()
        self.assertEqual(d.activity_label.text(), "Ausgabe 1 von 2 · MusicBrainz: Album-Daten")

    def test_the_last_text_stays_between_two_requests(self):
        d = self._dialog()
        d.follow_activity()
        with http.activity("eins"):
            d.show_activity()
        d.show_activity()
        self.assertEqual(d.activity_label.text(), "eins")

    def test_a_long_line_does_not_widen_the_window(self):
        d = self._dialog()
        d.follow_activity()
        width = d.width()
        with http.activity("x" * 400):
            d.show_activity()
        QApplication.processEvents()
        self.assertEqual(d.width(), width)

    def test_the_timer_stops_with_the_window(self):
        from psytags.ui.mainwindow import _StayingProgress
        d = _StayingProgress("Titel", 3, None)
        d.follow_activity()
        self.assertTrue(d.activity_timer.isActive())
        d.finish()
        self.assertFalse(d.activity_timer.isActive())

    def test_the_automatic_run_and_the_cover_step_use_it(self):
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock(_last_batch=[])
        a = NS(get=lambda name: [], folder="/musik/a")
        win.view.selected_tracks.return_value = [a, a]
        with mock.patch("psytags.websources.albumauto.group_albums", return_value=[[a], [a]]), \
                mock.patch("psytags.ui.mainwindow._StayingProgress") as progress:
            progress.return_value.stop.is_set.return_value = False
            MainWindow.fetch_covers(win)
        progress.return_value.follow_activity.assert_called_once()

    def test_the_style_is_small(self):
        from psytags.ui import theme
        self.assertIn("QLabel#ProgressActivity", theme.style_sheet())
        self.assertIsInstance(self._dialog().activity_label, QLabel)


if __name__ == "__main__":
    unittest.main()
