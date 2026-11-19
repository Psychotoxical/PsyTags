import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags import config
from psytags.websources import albumauto, beatport, coverprovider, http

# The shape of the API v4 answers as other clients read them: name, mix_name, artists,
# length_ms, number, key.name, bpm on a track; name, artists, label, catalog_number,
# publish_date, image.uri, slug on a release.
RELEASE = {"id": 9, "name": "Night Works", "slug": "night-works", "catalog_number": "CAT001",
           "publish_date": "2026-03-06", "label": {"id": 3, "name": "Label A"},
           "artists": [{"id": 1, "name": "Ann"}, {"id": 2, "name": "Bob"}],
           "image": {"uri": "https://geo-media.example/cover.jpg"}}
TRACKS = [
    {"id": 12, "number": 2, "name": "Second", "mix_name": "Extended Mix", "length_ms": 401000,
     "bpm": 124, "key": {"name": "Eb Major"}, "artists": [{"id": 2, "name": "Bob"}]},
    {"id": 11, "number": 1, "name": "First", "mix_name": "Original Mix", "length_ms": 359600,
     "bpm": 128, "key": {"name": "A Minor"}, "artists": [{"id": 1, "name": "Ann"}, {"id": 2, "name": "Bob"}]},
]


def _temp_config(case: unittest.TestCase) -> None:
    folder = tempfile.TemporaryDirectory()
    case.addCleanup(folder.cleanup)
    os.makedirs(os.path.join(folder.name, "data"))
    patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
    patcher.start()
    case.addCleanup(patcher.stop)


def _signed_in(expires_in: float = 3600) -> None:
    s = config.settings()
    s.setValue(beatport.CLIENT_ID, "id")
    s.setValue(beatport.CLIENT_SECRET, "secret")
    s.setValue(beatport.TOKEN, json.dumps({"access": "old", "refresh": "r1", "expires": time.time() + expires_in}))


class AlbumTests(unittest.TestCase):
    def setUp(self):
        self.album = beatport.parse_album(RELEASE, TRACKS)

    def test_tracks_follow_their_position(self):
        self.assertEqual(self.album.fields["TITLE"], ["First", "Second (Extended Mix)"])
        self.assertEqual(self.album.fields["TRACK"], ["1/2", "2/2"])

    def test_bpm_key_and_lengths(self):
        self.assertEqual(self.album.fields["BPM"], ["128", "124"])
        self.assertEqual(self.album.fields["INITIALKEY"], ["Am", "Eb"])
        self.assertEqual(self.album.lengths, ["6:00", "6:41"])

    def test_album_values(self):
        value = lambda name: self.album.value(name, 0)
        self.assertEqual((value("ALBUM"), value("ALBUMARTIST"), value("YEAR")), ("Night Works", "Ann, Bob", "2026-03-06"))
        self.assertEqual((value("PUBLISHER"), value("CATALOGNUMBER")), ("Label A", "CAT001"))
        self.assertEqual(value("BEATPORT_RELEASE_ID"), "9")
        self.assertEqual(self.album.value("ARTIST", 0), "Ann, Bob")
        self.assertEqual(self.album.cover_url, "https://geo-media.example/cover.jpg")

    def test_ids_of_other_sources_are_cleared(self):
        for name in ("MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_TRACKID", "DISCOGS_RELEASE_ID"):
            self.assertEqual(self.album.fields[name], [""])

    def test_many_artists_make_a_compilation(self):
        many = dict(RELEASE, artists=[{"name": n} for n in "ABCD"])
        self.assertEqual(beatport.parse_album(many, TRACKS).value("ALBUMARTIST", 0), beatport.VARIOUS)

    def test_odd_keys_stay_empty(self):
        self.assertEqual(beatport.initial_key({"key": {"name": "Unknown"}}), "")
        self.assertEqual(beatport.initial_key({}), "")
        self.assertEqual(beatport.initial_key({"key": {"name": "C# Minor"}}), "C#m")

    def test_the_source_asks_for_every_track(self):
        asked = []

        def get(path, **params):
            asked.append(path)
            if path.endswith("/tracks/"):
                return {"results": [{"id": 12}, {"id": 11}]}
            if path.startswith("/catalog/tracks/"):
                return next(t for t in TRACKS if f"/{t['id']}/" in path)
            return RELEASE
        with mock.patch.object(beatport, "_get", get):
            album = beatport.Source().album({"_url": "9"})
        self.assertEqual(asked, ["/catalog/releases/9/", "/catalog/releases/9/tracks/",
                                 "/catalog/tracks/12/", "/catalog/tracks/11/"])
        self.assertEqual(album.fields["TITLE"], ["First", "Second (Extended Mix)"])

    def test_search_rows(self):
        with mock.patch.object(beatport, "_get", lambda path, **p: {"releases": [RELEASE]}):
            rows = beatport.Source().search(["Night Works", "Ann"])
        self.assertEqual((rows[0]["_url"], rows[0]["Album"], rows[0]["Year"], rows[0]["CatNo"]),
                         ("9", "Night Works", "2026", "CAT001"))
        self.assertEqual(rows[0]["_preview"], "https://www.beatport.com/release/night-works/9")


class LoginTests(unittest.TestCase):
    def setUp(self):
        _temp_config(self)

    def test_without_login_there_is_no_source(self):
        self.assertIsNone(beatport.from_settings())
        self.assertFalse(beatport.configured())

    def test_login_keeps_the_tokens_but_never_the_password(self):
        sent = {}

        def post(url, fields, timeout=30):
            sent.update(fields)
            return json.dumps({"access_token": "a1", "refresh_token": "r1", "expires_in": 36000})
        with mock.patch.object(http, "post_form", post):
            beatport.login("id", "secret", "tester", "pw-123")
        self.assertEqual(sent["grant_type"], "password")
        self.assertTrue(beatport.configured())
        stored = {k: str(config.settings().value(k)) for k in config.settings().allKeys()}
        self.assertFalse(any("pw-123" in v for v in stored.values()))
        self.assertIsNotNone(beatport.from_settings())

    def test_a_refused_login_says_so(self):
        with mock.patch.object(http, "post_form", side_effect=http.FetchError("HTTP 401 Unauthorized: x")):
            with self.assertRaises(http.FetchError) as caught:
                beatport.login("id", "secret", "tester", "wrong")
        self.assertIn("Beatport lehnt die Anmeldung ab", str(caught.exception))
        self.assertFalse(beatport.configured())

    def test_a_fresh_token_is_used_as_it_is(self):
        _signed_in()
        with mock.patch.object(http, "post_form") as post:
            self.assertEqual(beatport._access_token(), "old")
        post.assert_not_called()

    def test_an_old_token_is_renewed(self):
        _signed_in(expires_in=10)
        answer = json.dumps({"access_token": "new", "refresh_token": "r2", "expires_in": 36000})
        with mock.patch.object(http, "post_form", return_value=answer) as post:
            self.assertEqual(beatport._access_token(), "new")
        self.assertEqual(post.call_args[0][1]["grant_type"], "refresh_token")
        self.assertEqual(beatport._stored_token()["refresh"], "r2")

    def test_a_refused_renewal_asks_for_a_new_login(self):
        _signed_in(expires_in=10)
        with mock.patch.object(http, "post_form", side_effect=http.FetchError("HTTP 400 Bad Request: x")):
            with self.assertRaises(beatport.LoginNeeded):
                beatport._access_token()
        self.assertFalse(beatport.configured())

    def test_requests_carry_the_token_in_a_header(self):
        _signed_in()
        seen = {}

        def fetch(url, *a, headers=None, **k):
            seen.update(url=url, headers=headers)
            return "{}"
        with mock.patch.object(http, "fetch", fetch), mock.patch.object(beatport, "_INTERVAL", 0):
            beatport._get("/catalog/search/", q="x")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer old")
        self.assertNotIn("old", seen["url"])

    def test_the_description_never_shows_the_address(self):
        self.assertEqual(http.describe("https://api.beatport.com/v4/catalog/search/?q=x"), "Beatport: Suche")
        self.assertEqual(http.describe("https://api.beatport.com/v4/auth/o/token/"), "Beatport: Anmeldung")


class CoverListTests(unittest.TestCase):
    def setUp(self):
        _temp_config(self)

    def test_beatport_joins_the_cover_sources_once_signed_in(self):
        self.assertEqual([n for n, _on in coverprovider.arranged([])], [coverprovider.ARCHIVE])
        _signed_in()
        self.assertEqual([n for n, _on in coverprovider.arranged([])], [coverprovider.ARCHIVE, beatport.NAME])
        self.assertIsInstance(coverprovider.active([])[1], beatport.Covers)

    def test_a_plugin_cannot_take_the_name(self):
        folder = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(folder, ignore_errors=True))
        path = os.path.join(folder, "beatport.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"format": 1, "name": "Beatport", "search_url": "https://x/{album}", "results": "r",
                       "album": "a", "artist": "b", "image": "c"}, fh)
        with self.assertRaises(coverprovider.ProviderError) as caught:
            coverprovider.load(path)
        self.assertIn("schon vergeben", str(caught.exception))

    def test_cover_search_goes_to_beatport(self):
        with mock.patch.object(beatport, "_get", lambda path, **p: {"releases": [RELEASE]}):
            rows = coverprovider.search(beatport.Covers(), "Ann", "Night Works")
        self.assertEqual(rows[0]["_image"], "https://geo-media.example/cover.jpg")


def _track(title):
    values = {"TITLE": [title], "ALBUM": ["A"], "ARTIST": ["Ann"]}
    return NS(filename=f"{title}.mp3", folder="f", data=NS(info=NS(length=200.0)),
              get=lambda n: values.get(n, []), field=lambda n: values.get(n, []))


def _source(found, name):
    from psytags.websources.base import Album
    album = None
    if found:
        album = Album(tracks=2, lengths=["3:20", "3:20"])
        album.fields = {"TITLE": ["One", "Two"], "ALBUM": ["A"], "ALBUMARTIST": ["Ann"]}
        album.per_track = {"TITLE"}
    row = {"_url": "1", "Album": "A", "Artist": "Ann", "Tracks": ""}
    return NS(name=name, prefill=lambda t, title=None: ["A", "Ann"], search=lambda v: [row] if found else [],
              album=lambda r: album)


class FallbackOrderTests(unittest.TestCase):
    def setUp(self):
        self.files = [_track("One"), _track("Two")]

    def test_beatport_gets_what_discogs_leaves_open(self):
        third = _source(True, "Beatport")
        used, res = albumauto.find_with_fallback(_source(False, "MusicBrainz"), [_source(False, "Discogs"), third], self.files)
        self.assertIs(used, third)
        self.assertIsNotNone(res.match)

    def test_a_failing_source_does_not_stop_the_next(self):
        second, third = _source(False, "Discogs"), _source(True, "Beatport")
        second.search = mock.MagicMock(side_effect=http.FetchError("Discogs lehnt den Token ab"))
        used, _res = albumauto.find_with_fallback(_source(False, "MusicBrainz"), [second, third], self.files)
        self.assertIs(used, third)

    def test_discogs_comes_first(self):
        second = _source(True, "Discogs")
        third = mock.MagicMock()
        used, _res = albumauto.find_with_fallback(_source(False, "MusicBrainz"), [second, third], self.files)
        self.assertIs(used, second)
        third.search.assert_not_called()


if __name__ == "__main__":
    unittest.main()
