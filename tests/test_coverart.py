import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags.websources import coverart, http
from psytags.ui.mainwindow import MainWindow


def answers(mapping):
    """fetch_bytes stand-in: bytes for known URLs, 404 for all others."""
    calls = []

    def fetch(url, *args, **kwargs):
        calls.append(url)
        if url in mapping:
            return mapping[url]
        raise http.NotFound(url)
    return fetch, calls


BASE = "https://coverartarchive.org"


class FetchFrontTests(unittest.TestCase):
    def _run(self, mapping, release="r1", group="g1"):
        fetch, calls = answers(mapping)
        with mock.patch.object(coverart.http, "fetch_bytes", fetch):
            return coverart.fetch_front(release, group), calls

    def test_the_1200_version_of_the_release_comes_first(self):
        data, calls = self._run({f"{BASE}/release/r1/front-1200": b"a"})
        self.assertEqual(data, b"a")
        self.assertEqual(calls, [f"{BASE}/release/r1/front-1200"])

    def test_without_a_1200_version_the_original_is_taken(self):
        data, calls = self._run({f"{BASE}/release/r1/front": b"o"})
        self.assertEqual(data, b"o")
        self.assertEqual(len(calls), 2)

    def test_the_release_group_helps_out(self):
        data, _calls = self._run({f"{BASE}/release-group/g1/front-1200": b"g"})
        self.assertEqual(data, b"g")

    def test_no_cover_anywhere(self):
        data, calls = self._run({})
        self.assertIsNone(data)
        self.assertEqual(len(calls), 4)

    def test_without_ids_nothing_is_requested(self):
        data, calls = self._run({}, "", "")
        self.assertIsNone(data)
        self.assertEqual(calls, [])

    def test_a_server_error_is_asked_again(self):
        with mock.patch.object(coverart.http, "fetch_bytes", side_effect=[http.ServerError("HTTP 500"), b"bild"]) as fetch, \
                mock.patch.object(coverart.time, "sleep") as sleep:
            self.assertEqual(coverart.fetch_front("r1"), b"bild")
        self.assertEqual(fetch.call_count, 2)
        sleep.assert_called_once()

    def test_a_lasting_server_error_is_reported(self):
        with mock.patch.object(coverart.http, "fetch_bytes", side_effect=http.ServerError("HTTP 500")) as fetch, \
                mock.patch.object(coverart.time, "sleep"):
            with self.assertRaises(http.ServerError):
                coverart.fetch_front("r1")
        self.assertEqual(fetch.call_count, 3)

    def test_a_broken_connection_is_reported(self):
        with mock.patch.object(coverart.http, "fetch_bytes", side_effect=http.FetchError("weg")):
            with self.assertRaises(http.FetchError):
                coverart.fetch_front("r1")


class Track:
    def __init__(self, **fields):
        self.fields = fields
        self.data = NS(covers=[NS(type=4), NS(type=3)])

    def get(self, name):
        value = self.fields.get(name)
        return [value] if value else []


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _win(self):
        win = mock.MagicMock()
        win._background.side_effect = lambda label, call: call()
        win._cover_big_enough.return_value = True
        return win

    def _fetch(self, win, tracks, result=b"\x89PNGdata", ids=None, ask=False):
        with mock.patch.object(coverart, "fetch_front", return_value=result) as front:
            return MainWindow.fetch_archive_cover(win, tracks, ask, ids), front

    def test_a_found_cover_replaces_the_front_cover(self):
        win = self._win()
        t = Track(MUSICBRAINZ_ALBUMID="r1", MUSICBRAINZ_RELEASEGROUPID="g1")
        result, front = self._fetch(win, [t])
        self.assertEqual(result, "")
        front.assert_called_once_with("r1", "g1")
        apply = win._write.call_args.args[2]
        apply(t)
        self.assertEqual(t.data.covers[0].data, b"\x89PNGdata")
        self.assertEqual(t.data.covers[0].mime, "image/png")
        self.assertEqual([c.type for c in t.data.covers], [3, 4])

    def test_ids_of_the_match_win_over_the_tags(self):
        _result, front = self._fetch(self._win(), [Track()], ids=("r2", "g2"))
        front.assert_called_once_with("r2", "g2")

    def test_without_an_id_it_says_so(self):
        win = self._win()
        result, front = self._fetch(win, [Track()])
        self.assertEqual(result, "Keine MusicBrainz-ID")
        front.assert_not_called()

    def test_no_cover_is_reported(self):
        win = self._win()
        result, _front = self._fetch(win, [Track(MUSICBRAINZ_ALBUMID="r1")], result=None)
        self.assertIn("Cover Art Archive", result)
        win._write.assert_not_called()

    def test_a_too_small_cover_is_not_written(self):
        win = self._win()
        win._cover_big_enough.return_value = False
        result, _front = self._fetch(win, [Track(MUSICBRAINZ_ALBUMID="r1")])
        self.assertIn("zu klein", result)
        win._write.assert_not_called()

    def test_a_too_small_cover_names_its_size(self):
        from PySide6.QtCore import QBuffer, QIODevice
        from PySide6.QtGui import QImage
        buffer = QBuffer()
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        QImage(297, 297, QImage.Format.Format_RGB32).save(buffer, "PNG")
        win = self._win()
        win._cover_big_enough.return_value = False
        result, _front = self._fetch(win, [Track(MUSICBRAINZ_ALBUMID="r1")], result=bytes(buffer.data()))
        self.assertIn("297x297", result)

    def test_a_server_error_gets_a_short_reason(self):
        win = self._win()
        with mock.patch.object(coverart, "fetch_front", side_effect=http.ServerError("HTTP 500 x: https://lang")):
            result = MainWindow.fetch_archive_cover(win, [Track(MUSICBRAINZ_ALBUMID="r1")], False, None)
        self.assertEqual(result, "Cover Art Archive antwortet gerade nicht")

    def test_a_connection_problem_becomes_the_reason(self):
        win = self._win()
        with mock.patch.object(coverart, "fetch_front", side_effect=http.FetchError("Verbindung weg\nmehr")):
            result = MainWindow.fetch_archive_cover(win, [Track(MUSICBRAINZ_ALBUMID="r1")], False, None)
        self.assertEqual(result, "Verbindung weg")

    def test_a_retry_asks_the_archive(self):
        win = self._win()
        win.fetch_cover_chain.return_value = ""
        entry = NS(tracks=[Track()], cover="alt", detail="x · alt")
        MainWindow._retry_cover(win, entry)
        win.fetch_cover_chain.assert_called_once_with(entry.tracks, pick=True)
        self.assertEqual(entry.cover, "")
        self.assertEqual(entry.detail, "x")

    def test_a_declined_retry_ends_there_and_shows_why(self):
        win = self._win()
        win.fetch_cover_chain.return_value = "zu klein"
        entry = NS(tracks=[Track()], cover="alt", detail="x · alt")
        MainWindow._retry_cover(win, entry)
        win.fetch_cover_from_source.assert_not_called()
        self.assertEqual(entry.cover, "zu klein")
        self.assertEqual(entry.detail, "x · zu klein")

    def test_the_cover_menu_only_offers_musicbrainz(self):
        win = self._win()
        win.view.selected_tracks.return_value = [Track()]
        win._mb_cover_source.return_value = "mb.src"
        self.assertEqual(MainWindow._cover_fetch_entries(win), [("fetch_mb", "Cover von MusicBrainz laden")])

    def test_the_cover_menu_is_empty_without_a_selection(self):
        win = self._win()
        win.view.selected_tracks.return_value = []
        self.assertEqual(MainWindow._cover_fetch_entries(win), [])

    def test_the_musicbrainz_entry_opens_the_search(self):
        win = self._win()
        win._mb_cover_source.return_value = "mb.src"
        MainWindow._cover_command(win, "fetch_mb")
        win.fetch_cover_from_source.assert_called_once_with(win.view.selected_tracks.return_value, path="mb.src", manual=True)

    def test_no_second_cover_source_is_left(self):
        for name in ("_manual_cover_source", "_add_cover_source_menu"):
            self.assertFalse(hasattr(MainWindow, name), name)

    def _step(self, win, albums, stop=False):
        win.view.selected_tracks.return_value = [t for album in albums for t in album]
        with mock.patch("psytags.websources.albumauto.group_albums", return_value=albums), \
                mock.patch("psytags.ui.mainwindow._StayingProgress") as progress:
            progress.return_value.stop.is_set.return_value = stop
            MainWindow.fetch_covers(win)
        return progress

    def test_the_cover_step_works_album_by_album(self):
        win = self._win()
        win.fetch_cover_chain.side_effect = ["", "kein Cover"]
        progress = self._step(win, [[Track(ALBUM="A")], [Track(ALBUM="B")]])
        self.assertEqual(win.fetch_cover_chain.call_count, 2)
        self.assertIn("1 von 2", win.message.call_args.args[0])
        progress.return_value.finish.assert_called_once()

    def test_several_albums_never_ask_about_small_covers(self):
        win = self._win()
        win.fetch_cover_chain.return_value = ""
        self._step(win, [[Track(ALBUM="A")], [Track(ALBUM="B")]])
        self.assertFalse(win.fetch_cover_chain.call_args.kwargs["ask"])

    def test_a_single_album_may_ask_and_shows_its_reason(self):
        win = self._win()
        win.fetch_cover_chain.return_value = "Keine MusicBrainz-ID"
        progress = self._step(win, [[Track(ALBUM="A")]])
        self.assertTrue(win.fetch_cover_chain.call_args.kwargs["ask"])
        self.assertEqual(win.message.call_args.args[0], "Keine MusicBrainz-ID")
        progress.assert_not_called()

    def test_the_cover_step_can_be_stopped(self):
        win = self._win()
        self._step(win, [[Track(ALBUM="A")], [Track(ALBUM="B")]], stop=True)
        win.fetch_cover_chain.assert_not_called()

    def _import(self, win, cover=None, archive=None):
        win._lastfm_enabled.return_value = False
        win._cover_big_enough.return_value = bool(cover)
        t = Track()
        t.set = lambda *a: None
        return MainWindow._finish_source_import(win, "MB", "p", [(t, {})], cover, [], False, True, archive)

    def test_the_import_uses_the_archive_and_never_asks(self):
        win = self._win()
        win.fetch_cover_chain.return_value = ""
        self._import(win, archive=("r1", "g1"))
        win.fetch_cover_chain.assert_called_once()
        self.assertFalse(win.fetch_cover_chain.call_args.args[1])
        self.assertEqual(win.fetch_cover_chain.call_args.args[2], ("r1", "g1"))
        win.fetch_cover_from_source.assert_not_called()

    def test_a_cover_settled_in_the_dialog_is_not_fetched_again(self):
        win = self._win()
        result = self._import(win, cover=b"x", archive=())
        win.fetch_cover_chain.assert_not_called()
        win.fetch_cover_from_source.assert_not_called()
        self.assertEqual(result, (None, None))

    def test_other_tag_sources_have_no_cover_step(self):
        win = self._win()
        result = self._import(win)
        win.fetch_cover_chain.assert_not_called()
        win.fetch_cover_from_source.assert_not_called()
        self.assertEqual(result, (None, None))


class IdsTests(unittest.TestCase):
    def _album(self, **fields):
        return NS(value=lambda name, i: fields.get(name, ""))

    def test_ids_of_a_musicbrainz_result(self):
        album = self._album(MUSICBRAINZ_ALBUMID="r", MUSICBRAINZ_RELEASEGROUPID="g")
        self.assertEqual(coverart.ids_of(album), ("r", "g"))

    def test_other_sources_have_none(self):
        self.assertIsNone(coverart.ids_of(self._album()))

    def test_after_the_dialog_a_shown_cover_is_settled(self):
        album = self._album(MUSICBRAINZ_ALBUMID="r")
        self.assertEqual(coverart.ids_after_dialog(album, b"cover"), ())

    def test_after_the_dialog_without_a_cover_the_archive_is_asked(self):
        album = self._album(MUSICBRAINZ_ALBUMID="r", MUSICBRAINZ_RELEASEGROUPID="g")
        self.assertEqual(coverart.ids_after_dialog(album, None), ("r", "g"))

    def test_after_the_dialog_other_sources_stay_on_their_route(self):
        self.assertIsNone(coverart.ids_after_dialog(self._album(), b"cover"))


class NotFoundTests(unittest.TestCase):
    def test_404_is_its_own_error(self):
        import urllib.error
        error = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(http.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(http.NotFound):
                http.fetch_bytes("https://coverartarchive.org/release/x/front-1200")


if __name__ == "__main__":
    unittest.main()
