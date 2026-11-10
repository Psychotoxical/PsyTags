import json
import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags import config
from psytags.websources import albumauto, discogs, http

RELEASE = {
    "id": 77, "title": "Big Album", "year": 2018, "released": "2018-10-11", "master_id": 5,
    "artists": [{"name": "Ann (3)", "anv": "", "join": "&"}, {"name": "Bob*", "anv": "", "join": ""}],
    "labels": [{"name": "Label A", "catno": "CAT1"}, {"name": "Label B", "catno": "none"}],
    "identifiers": [{"type": "Matrix", "value": "zzz"}, {"type": "Barcode", "value": "123"}],
    "images": [{"uri": "https://i.discogs.com/photo.jpg", "type": "primary"}],
    "tracklist": [
        {"type_": "heading", "position": "", "title": "Part One", "duration": ""},
        {"type_": "track", "position": "1", "title": "One", "duration": "4:33"},
        {"type_": "track", "position": "2", "title": "Two", "duration": "3:57",
         "artists": [{"name": "Guest (2)", "join": ""}]},
    ],
}
TWO_DISCS = dict(RELEASE, tracklist=[
    {"type_": "track", "position": "1-1", "title": "A", "duration": "1:00"},
    {"type_": "track", "position": "1-2", "title": "B", "duration": "1:00"},
    {"type_": "track", "position": "CD2-1", "title": "C", "duration": "1:00"},
])
MASTER = {"id": 5, "year": 2015}


def answers(*pages):
    pages = list(pages)
    return lambda url, *a, **k: json.dumps(pages.pop(0))


def album_from(release, master=MASTER):
    http._cache.clear()
    with mock.patch.object(http, "fetch", side_effect=answers(release, master)), \
            mock.patch.object(discogs, "_polite", lambda call: call()):
        return discogs.Source("t").album({"_url": "77"})


class SearchTests(unittest.TestCase):
    def _search(self, answer):
        with mock.patch.object(http, "fetch", return_value=json.dumps(answer)) as fetch, \
                mock.patch.object(discogs, "_polite", lambda call: call()):
            return discogs.Source("geheim").search(["Bär Album", "Ann B"]), fetch

    def test_the_query_names_album_and_artist(self):
        _rows, fetch = self._search({"results": []})
        url = fetch.call_args[0][0]
        self.assertIn("release_title=B%C3%A4r+Album", url)
        self.assertIn("artist=Ann+B", url)
        self.assertIn("type=release", url)

    def test_the_token_goes_in_the_header_not_the_address(self):
        _rows, fetch = self._search({"results": []})
        self.assertEqual(fetch.call_args[1]["headers"], {"Authorization": "Discogs token=geheim"})
        self.assertNotIn("geheim", fetch.call_args[0][0])

    def test_a_row_has_clean_names_and_says_digital(self):
        rows, _ = self._search({"results": [{"id": 9, "title": "Ann (3) - Big Album", "year": "2018",
                                             "format": ["File", "MP3"], "label": ["L"], "catno": "C", "country": "DE"}]})
        self.assertEqual(rows[0]["Artist"], "Ann")
        self.assertEqual(rows[0]["Album"], "Big Album")
        self.assertEqual(rows[0]["_url"], "9")
        self.assertTrue(albumauto.is_digital(rows[0]))

    def test_a_row_carries_no_picture(self):
        rows, _ = self._search({"results": [{"id": 9, "title": "A - B", "thumb": "x", "cover_image": "y"}]})
        self.assertFalse({"_coverurl", "thumb", "cover_image"} & set(rows[0]))


class AlbumTests(unittest.TestCase):
    def test_fields_of_the_release(self):
        a = album_from(RELEASE)
        self.assertEqual(a.value("ALBUM", 0), "Big Album")
        self.assertEqual(a.value("ALBUMARTIST", 0), "Ann & Bob")
        self.assertEqual(a.value("YEAR", 0), "2018")
        self.assertEqual(a.value("PUBLISHER", 0), "Label A, Label B")
        self.assertEqual(a.value("CATALOGNUMBER", 0), "CAT1")
        self.assertEqual(a.value("BARCODE", 0), "123")

    def test_the_first_year_comes_from_the_master(self):
        self.assertEqual(album_from(RELEASE).value("ORIGYEAR", 0), "2015")

    def test_without_a_master_the_first_year_is_the_release_year(self):
        http._cache.clear()
        release = dict(RELEASE, master_id=0)
        with mock.patch.object(http, "fetch", side_effect=answers(release)), \
                mock.patch.object(discogs, "_polite", lambda call: call()):
            self.assertEqual(discogs.Source("t").album({"_url": "77"}).value("ORIGYEAR", 0), "2018")

    def test_stray_tabs_stay_out_of_the_tags(self):
        release = dict(RELEASE, title="Big\tAlbum ", tracklist=[
            {"type_": "track", "position": "1", "title": "Don't Leave Me\t", "duration": "\t4:33"}])
        a = album_from(release)
        self.assertEqual(a.value("TITLE", 0), "Don't Leave Me")
        self.assertEqual(a.value("ALBUM", 0), "Big Album")
        self.assertEqual(a.lengths, ["4:33"])

    def test_headings_are_no_tracks(self):
        a = album_from(RELEASE)
        self.assertEqual(a.tracks, 2)
        self.assertEqual([a.value("TITLE", 0), a.value("TITLE", 1)], ["One", "Two"])
        self.assertEqual(a.lengths, ["4:33", "3:57"])

    def test_a_guest_stands_at_the_track(self):
        a = album_from(RELEASE)
        self.assertEqual([a.value("ARTIST", 0), a.value("ARTIST", 1)], ["Ann & Bob", "Guest"])

    def test_numbers_of_one_disc(self):
        a = album_from(RELEASE)
        self.assertEqual(a.value("TRACK", 1), "2/2")
        self.assertEqual(a.value("DISCNUMBER", 1), "")

    def test_numbers_of_two_discs(self):
        a = album_from(TWO_DISCS)
        self.assertEqual([a.value("TRACK", i) for i in range(3)], ["1/2", "2/2", "1/1"])
        self.assertEqual([a.value("DISCNUMBER", i) for i in range(3)], ["1/2", "1/2", "2/2"])

    def test_old_musicbrainz_ids_are_cleared(self):
        a = album_from(RELEASE)
        for name in ("MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_RELEASEGROUPID", "MUSICBRAINZ_TRACKID"):
            self.assertIn(name, a.fields)
            self.assertEqual(a.value(name, 0), "")

    def test_never_a_picture(self):
        a = album_from(RELEASE)
        self.assertEqual(a.cover_url, "")
        with mock.patch.object(http, "fetch_bytes") as download:
            self.assertIsNone(discogs.Source("t").cover(a))
        download.assert_not_called()


class ErrorTests(unittest.TestCase):
    def test_a_refused_token_says_so(self):
        with mock.patch.object(http, "fetch", side_effect=http.FetchError("HTTP 401 Unauthorized: x")), \
                mock.patch.object(discogs, "_polite", lambda call: call()), \
                self.assertRaisesRegex(http.FetchError, "Token"):
            discogs.Source("t").search(["A", "B"])

    def test_too_many_requests_are_asked_again(self):
        calls = [http.FetchError("HTTP 429 Too Many"), "ok"]

        def call():
            got = calls.pop(0)
            if isinstance(got, Exception):
                raise got
            return got
        with mock.patch.object(discogs.time, "sleep") as sleep:
            self.assertEqual(discogs._polite(call), "ok")
        sleep.assert_called()

    def test_verify_token_asks_who_it_is(self):
        with mock.patch.object(http, "fetch", return_value="{}") as fetch, \
                mock.patch.object(discogs, "_polite", lambda call: call()):
            discogs.verify_token("t")
        self.assertIn("/oauth/identity", fetch.call_args[0][0])


class SettingsTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_without_a_token_there_is_no_source(self):
        self.assertIsNone(discogs.from_settings())

    def test_with_a_token_there_is_one(self):
        config.settings().setValue("discogs/token", "abc")
        self.assertEqual(discogs.from_settings().token, "abc")

    def test_the_description_never_shows_the_address(self):
        self.assertEqual(http.describe("https://api.discogs.com/database/search?q=x"), "Discogs: Suche")
        self.assertEqual(http.describe("https://api.discogs.com/releases/1"), "Discogs: Album-Daten")


def _track(name, title, album="A", mbid=""):
    values = {"TITLE": [title], "ALBUM": [album], "ARTIST": ["Ann"]}
    if mbid:
        values["MUSICBRAINZ_ALBUMID"] = [mbid]
    t = NS(filename=name, folder="f", data=NS(info=NS(length=200.0)), get=lambda n: values.get(n, []),
           field=lambda n: values.get(n, []))
    return t


def _album(titles, length="3:20"):
    from psytags.websources.base import Album
    a = Album(tracks=len(titles), lengths=[length] * len(titles))
    a.fields = {"TITLE": list(titles), "ALBUM": ["A"], "ALBUMARTIST": ["Ann"]}
    a.per_track = {"TITLE"}
    return a


def _source(found, name="Discogs", tracks=""):
    row = {"_url": "1", "Album": "A", "Artist": "Ann", "Tracks": tracks}
    return NS(name=name, prefill=lambda t, title=None: ["A", "Ann"], search=lambda v: [row] if found else [],
              album=lambda r: found)


TITLES = ["One", "Two", "Three", "Four"]


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.files = [_track(f"{t}.mp3", t) for t in TITLES]

    def test_a_certain_musicbrainz_album_never_asks_the_second_source(self):
        second = mock.MagicMock()
        first = _source(_album(TITLES), "MusicBrainz", "4")
        used, res = albumauto.find_with_fallback(first, second, self.files)
        self.assertIs(used, first)
        self.assertIsNotNone(res.match)
        second.search.assert_not_called()

    def test_an_open_album_goes_to_the_second_source(self):
        first, second = _source(None, "MusicBrainz"), _source(_album(TITLES))
        used, res = albumauto.find_with_fallback(first, second, self.files)
        self.assertIs(used, second)
        self.assertIsNotNone(res.match)

    def test_without_a_second_source_the_album_stays_open(self):
        first = _source(None, "MusicBrainz")
        used, res = albumauto.find_with_fallback(first, None, self.files)
        self.assertIs(used, first)
        self.assertIsNone(res.match)

    def test_the_second_source_needs_every_length(self):
        release = _album(TITLES)
        release.lengths = ["3:20", "", "3:20", "3:20"]
        used, res = albumauto.find_with_fallback(_source(None, "MusicBrainz"), _source(release), self.files)
        self.assertIsNone(res.match)

    def test_the_same_release_without_lengths_passes_at_musicbrainz(self):
        release = _album(TITLES)
        release.lengths = ["3:20", "", "3:20", "3:20"]
        self.assertIsNotNone(albumauto.find_album(_source(release, "MusicBrainz", "4"), self.files).match)

    def test_the_second_source_does_not_get_a_musicbrainz_id(self):
        files = [_track(f"{t}.mp3", t, mbid="mb-id") for t in TITLES]
        asked = []
        second = _source(_album(TITLES))
        second.album = lambda row: asked.append(row["_url"]) or _album(TITLES)
        first = _source(None, "MusicBrainz")
        first.album = lambda row: _album(["Something else"])
        albumauto.find_with_fallback(first, second, files)
        self.assertEqual(asked, ["1"])

    def test_the_reason_of_musicbrainz_stays_when_the_second_finds_nothing(self):
        first = _source(None, "MusicBrainz")
        expected = albumauto.find_album(first, self.files).reason
        _used, res = albumauto.find_with_fallback(first, _source(None), self.files)
        self.assertEqual(res.reason, expected)

    def test_a_failing_second_source_is_mentioned(self):
        second = _source(None)
        second.search = mock.MagicMock(side_effect=http.FetchError("Discogs lehnt den Token ab"))
        used, res = albumauto.find_with_fallback(_source(None, "MusicBrainz"), second, self.files)
        self.assertIsNone(res.match)
        self.assertIn("Discogs lehnt den Token ab", res.reason)

    def test_rows_without_a_track_count_are_looked_at(self):
        got = albumauto.candidate_rows([NS(row={"_url": "a", "Tracks": "", "Format": "CD"})], 4)
        self.assertEqual(len(got), 1)

    def test_rows_with_the_right_count_come_first(self):
        rows = [NS(row={"_url": "none", "Tracks": "", "Format": "CD"}), NS(row={"_url": "four", "Tracks": "4", "Format": "CD"})]
        self.assertEqual(albumauto.candidate_rows(rows, 4)[0]["_url"], "four")


class WiringTests(unittest.TestCase):
    def test_a_discogs_album_still_runs_the_cover_sources(self):
        from psytags.ui import mainwindow as mw
        from psytags.websources.base import Album
        win = mock.MagicMock()
        win.settings.value.return_value = []
        match = mock.MagicMock(leftover_keys=[], release=NS(key=Album()))
        with mock.patch.object(albumauto, "plan_for", return_value=[]), \
                mock.patch.object(config, "string_list", return_value=[]):
            mw.MainWindow._import_match(win, NS(name="Discogs"), match, interactive=False)
        self.assertEqual(win._finish_source_import.call_args[1]["archive"], ("", ""))

    def test_the_summary_says_where_it_came_from(self):
        from psytags.ui import mainwindow as mw
        win = mock.MagicMock(_group_errors=[])
        win._background.side_effect = lambda label, call: call()
        win._import_match.return_value = ("", "")
        match = mock.MagicMock(leftover_keys=[], missing_last=False)
        first, second = NS(name="MusicBrainz"), NS(name="Discogs")
        with mock.patch.object(albumauto, "find_with_fallback", return_value=(second, NS(match=match, reason=""))), \
                mock.patch.object(albumauto, "album_title", return_value="A"), \
                mock.patch.object(albumauto, "release_label", return_value="A (2001)"), \
                mock.patch.object(discogs, "from_settings", return_value=second), \
                mock.patch.object(mw, "_remember_covers"):
            entry = mw.MainWindow._auto_one(win, first, [NS()])
        self.assertIn("Discogs", entry.detail)
        self.assertIs(win._import_match.call_args[0][0], second)


if __name__ == "__main__":
    unittest.main()
