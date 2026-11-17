import json
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from psytags.websources import http, musicbrainz

RELEASE = {
    "id": "rel-1", "title": "Big Album", "date": "2001-05-02", "country": "DE", "barcode": "123",
    "asin": "B000", "cover-art-archive": {"front": True},
    "label-info": [{"catalog-number": "CAT1", "label": {"name": "Label A"}},
                   {"catalog-number": "CAT2", "label": {"name": "Label B"}}],
    "release-group": {
        "id": "group-1", "primary-type": "Album", "secondary-types": ["Live"],
        "first-release-date": "1999-01-01",
        "artist-credit": [
            {"name": "Ann", "joinphrase": " & ", "artist": {"id": "a1", "sort-name": "Ann, A"}},
            {"name": "Bob", "joinphrase": "", "artist": {"id": "a2", "sort-name": "Bob, B"}}]},
    "media": [
        {"position": 1, "track-count": 2, "title": "First", "format": "Digital Media", "tracks": [
            {"position": 1, "recording": {
                "id": "r1", "length": 61000, "title": "One", "isrcs": ["X1", "X2"],
                "artist-credit": [{"name": "Ann", "joinphrase": "", "artist": {"id": "a1", "sort-name": "Ann, A"}}]}},
            {"position": 2, "recording": {
                "id": "r2", "length": 62000, "title": "Two", "isrcs": [],
                "artist-credit": [{"name": "Bob", "joinphrase": "", "artist": {"id": "a2", "sort-name": "Bob, B"}}]}}]},
        {"position": 2, "track-count": 1, "title": "", "format": "CD", "tracks": [
            {"position": 1, "recording": {
                "id": "r3", "length": None, "title": "Three", "isrcs": [],
                "artist-credit": [{"name": "Ann", "joinphrase": "", "artist": {"id": "a1", "sort-name": "Ann, A"}}]}}]},
    ],
}


def album_from(data: dict):
    with mock.patch.object(http, "fetch", return_value=json.dumps(data)) as fetch, \
            mock.patch.object(musicbrainz, "_polite", lambda call: call()):
        return musicbrainz.Source().album({"_url": data["id"]}), fetch


def track(**fields):
    return NS(field=lambda name: fields.get(name.upper(), []))


class PrefillTest(unittest.TestCase):
    def test_takes_album_and_album_artist_without_query_syntax(self):
        t = track(ALBUM=['Foo (Live): "Bar"!'], ALBUMARTIST=["Ann & Bob"], ARTIST=["Other"])
        self.assertEqual(musicbrainz.Source().prefill([t]), ["Foo Live Bar", "Ann & Bob"])

    def test_falls_back_to_the_artist(self):
        self.assertEqual(musicbrainz.Source().prefill([track(ALBUM=["A"], ARTIST=["Solo"])]), ["A", "Solo"])

    def test_of_several_values_only_the_first_is_searched(self):
        t = track(ALBUM=["A", "B"], ALBUMARTIST=["Ann", "Bob"])
        self.assertEqual(musicbrainz.Source().prefill([t]), ["A", "Ann"])

    def test_another_title_replaces_only_the_album(self):
        t = track(ALBUM=["Long (Deluxe)"], ARTIST=["Solo"])
        self.assertEqual(musicbrainz.Source().prefill([t], "Long"), ["Long", "Solo"])


class SearchTest(unittest.TestCase):
    def _search(self, values, answer):
        with mock.patch.object(http, "fetch", return_value=json.dumps(answer)) as fetch, \
                mock.patch.object(musicbrainz, "_polite", lambda call: call()):
            return musicbrainz.Source().search(values), fetch

    def test_builds_the_release_query(self):
        _rows, fetch = self._search(["Foo Bär", "Ann B"], {"releases": []})
        self.assertEqual(fetch.call_args[0][0],
                         "https://musicbrainz.org/ws/2/release/?fmt=json&limit=50"
                         "&query=release:Foo+B%C3%A4r%20AND%20artist:%28Ann+B%29")

    def test_one_row_per_release_with_the_columns_of_the_list(self):
        rows, _ = self._search(["A", "B"], {"releases": [{
            "id": "rel-1", "score": 100, "title": "Big", "track-count": 3, "date": "2001", "country": "DE",
            "release-group": {"primary-type": "Album"},
            "artist-credit": [{"name": "Ann", "joinphrase": " feat. "}, {"name": "Bob"}],
            "media": [{"format": "Digital Media"}, {"format": "CD"}],
            "label-info": [{"catalog-number": "C1", "label": {"name": "Lab"}}, {"catalog-number": "C2"}]}]})
        self.assertEqual(rows, [{
            "_preview": "https://musicbrainz.org/release/rel-1",
            "_coverurl": "https://coverartarchive.org/release/rel-1/front-250",
            "_url": "rel-1", "Score": "100", "Type": "Album", "Artist": "Ann feat. Bob", "Album": "Big",
            "Tracks": "3", "Year": "2001", "Country": "DE", "Format": "Digital Media, CD", "Publisher": "Lab",
            "CatNo": "C1"}])

    def test_missing_values_stay_empty(self):
        rows, _ = self._search(["A", "B"], {"releases": [{"id": "r", "title": "T"}]})
        self.assertEqual((rows[0]["Type"], rows[0]["Format"], rows[0]["Publisher"], rows[0]["Tracks"]), ("", "", "", ""))

    def test_an_unreadable_answer_is_a_fetch_error(self):
        with mock.patch.object(http, "fetch", return_value="<html>busy</html>"), \
                mock.patch.object(musicbrainz, "_polite", lambda call: call()), \
                self.assertRaises(http.FetchError):
            musicbrainz.Source().search(["A", "B"])


class AlbumTest(unittest.TestCase):
    def setUp(self):
        self.album, self.fetch = album_from(RELEASE)

    def _track_values(self, name):
        return [self.album.value(name, i) for i in range(self.album.tracks)]

    def test_asks_for_the_release_with_everything_needed(self):
        self.assertEqual(self.fetch.call_args[0][0], "https://musicbrainz.org/ws/2/release/rel-1"
                         "?inc=artists+artist-credits+labels+recordings+release-groups+isrcs&fmt=json")

    def test_album_values(self):
        expected = {"MUSICBRAINZ_ALBUMID": "rel-1", "ALBUM": "Big Album", "ALBUMARTIST": "Ann & Bob",
                    "ALBUMARTISTSORT": "Ann, A; Bob, B", "MUSICBRAINZ_ALBUMARTISTID": "a1, a2",
                    "MUSICBRAINZ_RELEASEGROUPID": "group-1", "MUSICBRAINZ_ALBUMTYPE": "Album, Live",
                    "ORIGYEAR": "1999-01-01", "ASIN": "B000", "YEAR": "2001-05-02", "CATALOGNUMBER": "CAT1, CAT2",
                    "PUBLISHER": "Label A, Label B", "MUSICBRAINZ_ALBUMRELEASECOUNTRY": "DE", "BARCODE": "123"}
        self.assertEqual({k: self.album.value(k, 0) for k in expected}, expected)

    def test_track_values_run_across_the_discs(self):
        self.assertEqual(self.album.tracks, 3)
        self.assertEqual(self._track_values("TITLE"), ["One", "Two", "Three"])
        self.assertEqual(self._track_values("TRACK"), ["1/2", "2/2", "1/1"])
        self.assertEqual(self._track_values("DISCNUMBER"), ["1/2", "1/2", "2/2"])
        self.assertEqual(self._track_values("SETSUBTITLE"), ["First", "First", ""])
        self.assertEqual(self._track_values("ARTIST"), ["Ann", "Bob", "Ann"])
        self.assertEqual(self._track_values("ISRC"), ["X1, X2", "", ""])
        self.assertEqual(self._track_values("MUSICBRAINZ_TRACKID"), ["r1", "r2", "r3"])
        self.assertEqual(self.album.lengths, ["61000", "62000", ""])

    def test_a_single_disc_has_no_disc_number(self):
        one = dict(RELEASE, media=RELEASE["media"][:1])
        album, _ = album_from(one)
        self.assertNotIn("DISCNUMBER", album.fields)

    def test_a_field_empty_on_every_track_is_left_out(self):
        one = dict(RELEASE, media=[dict(RELEASE["media"][1])])
        album, _ = album_from(one)
        self.assertNotIn("SETSUBTITLE", album.fields)
        self.assertNotIn("ISRC", album.fields)

    def test_a_discogs_id_of_an_earlier_tagging_is_cleared(self):
        self.assertEqual(self.album.fields["DISCOGS_RELEASE_ID"], [""])
        self.assertNotIn("DISCOGS_RELEASE_ID", self.album.per_track)

    def test_empty_album_values_are_left_out(self):
        album, _ = album_from(dict(RELEASE, barcode="", asin=None))
        self.assertNotIn("BARCODE", album.fields)
        self.assertNotIn("ASIN", album.fields)

    def test_only_a_pure_compilation_sets_the_flag(self):
        group = dict(RELEASE["release-group"], **{"secondary-types": ["Compilation"]})
        self.assertEqual(album_from(dict(RELEASE, **{"release-group": group}))[0].value("COMPILATION", 0), "1")
        self.assertEqual(self.album.value("COMPILATION", 0), "")

    def test_cover_only_from_the_archive(self):
        self.assertEqual(self.album.cover_url, "https://coverartarchive.org/release/rel-1/front")
        without = dict(RELEASE, **{"cover-art-archive": {"front": False}})
        self.assertEqual(album_from(without)[0].cover_url, "")


class CoverTest(unittest.TestCase):
    def test_loads_the_front_of_this_release(self):
        album, _ = album_from(RELEASE)
        with mock.patch.object(musicbrainz.coverart, "fetch_front", return_value=b"img") as front:
            self.assertEqual(musicbrainz.Source().cover(album), b"img")
        front.assert_called_once_with("rel-1")

    def test_no_request_without_a_front_cover(self):
        album, _ = album_from(dict(RELEASE, **{"cover-art-archive": {"front": False}}))
        with mock.patch.object(musicbrainz.coverart, "fetch_front") as front:
            self.assertIsNone(musicbrainz.Source().cover(album))
        front.assert_not_called()


class PoliteTest(unittest.TestCase):
    def test_keeps_a_second_between_requests(self):
        waits = []
        with mock.patch.object(musicbrainz.time, "sleep", waits.append), \
                mock.patch.object(musicbrainz.time, "monotonic", return_value=100.0):
            musicbrainz._last_call[0] = 100.0
            self.assertEqual(musicbrainz._polite(lambda: "ok"), "ok")
        self.assertAlmostEqual(waits[0], musicbrainz._INTERVAL)

    def test_tries_again_when_the_server_is_busy(self):
        answers = [http.ServerError("HTTP 503"), "ok"]

        def call():
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer
        with mock.patch.object(musicbrainz.time, "sleep"):
            self.assertEqual(musicbrainz._polite(call), "ok")

    def _busy(self, retries, wait):
        """The pauses and the number of requests against a server that is always busy."""
        calls, pauses = [], []

        def call():
            calls.append(1)
            raise http.ServerError("HTTP 503")
        with mock.patch.object(musicbrainz, "_patience", return_value=(retries, wait)), \
                mock.patch.object(musicbrainz.time, "monotonic", return_value=0.0), \
                mock.patch.object(musicbrainz.time, "sleep"), \
                mock.patch.object(musicbrainz, "_count_down", lambda attempt, total, pause: pauses.append(pause)), \
                self.assertRaises(http.ServerError):
            musicbrainz._last_call[0] = -100.0
            musicbrainz._polite(call)
        return len(calls), pauses

    def test_the_pause_counts_down_second_by_second(self):
        seen = []
        with mock.patch.object(musicbrainz.time, "sleep", side_effect=lambda s: seen.append((s, http.running()))):
            musicbrainz._count_down(2, 8, 3)
        self.assertEqual(seen, [(1, [f"MusicBrainz ist ausgelastet, Versuch 2 von 8 in {left} s"]) for left in (3, 2, 1)])
        self.assertEqual(http.running(), [])

    def test_the_pause_grows_with_every_try(self):
        self.assertEqual(self._busy(3, 5), (4, [5, 10, 15]))

    def test_no_pause_is_longer_than_a_minute(self):
        self.assertEqual(self._busy(4, 25)[1], [25, 50, 60, 60])

    def test_without_further_tries_the_first_busy_answer_ends_it(self):
        self.assertEqual(self._busy(0, 5), (1, []))

    def test_the_patience_comes_from_the_options(self):
        s = musicbrainz.config.settings()
        old = s.value("options/mb_retries"), s.value("options/mb_wait")
        self.addCleanup(lambda: [s.setValue(k, v) if v is not None else s.remove(k)
                                 for k, v in zip(("options/mb_retries", "options/mb_wait"), old)])
        s.setValue("options/mb_retries", 9)
        s.setValue("options/mb_wait", 7)
        self.assertEqual(musicbrainz._patience(), (9, 7))
        s.setValue("options/mb_wait", "nonsense")
        self.assertEqual(musicbrainz._patience(), (6, 5))

    def test_other_errors_are_not_repeated(self):
        calls = []

        def call():
            calls.append(1)
            raise http.NotFound("HTTP 404")
        with mock.patch.object(musicbrainz.time, "sleep"), self.assertRaises(http.NotFound):
            musicbrainz._polite(call)
        self.assertEqual(len(calls), 1)


class UserAgentTest(unittest.TestCase):
    def test_names_program_and_repository(self):
        self.assertRegex(http.USER_AGENT, r"^PsyTags/\S+ \( https://github\.com/Psychotoxical/PsyTags \)$")


def _medium(position, fmt, titles):
    return {"position": position, "track-count": len(titles), "title": "", "format": fmt, "tracks": [
        {"position": n, "recording": {"id": f"{fmt}-{n}", "length": 60000, "title": title, "isrcs": [],
                                      "artist-credit": []}} for n, title in enumerate(titles, 1)]}


def _with_media(*media):
    return {**RELEASE, "media": list(media)}


class VideoMediaTest(unittest.TestCase):
    """A DVD beside the CDs: the files of a rip are the CDs."""

    def test_the_audio_discs_are_kept_apart(self):
        album, _ = album_from(_with_media(_medium(1, "DVD-Video", ["Film A", "Film B", "Film C"]),
                                          _medium(2, "CD", ["One", "Two"])))
        self.assertEqual(album.tracks, 5)
        slim = album.audio_only
        self.assertEqual(slim.fields["TITLE"], ["One", "Two"])
        self.assertEqual(slim.fields["TRACK"], ["1/2", "2/2"])
        self.assertNotIn("DISCNUMBER", slim.fields)          # one disc is left
        self.assertEqual(slim.cover_url, album.cover_url)
        self.assertIsNone(slim.audio_only)

    def test_the_discs_count_without_the_dvd(self):
        album, _ = album_from(_with_media(_medium(1, "CD", ["One"]), _medium(2, "DVD", ["Film"]),
                                          _medium(3, "CD", ["Two"])))
        self.assertEqual(album.audio_only.fields["DISCNUMBER"], ["1/2", "2/2"])
        self.assertEqual(album.fields["DISCNUMBER"], ["1/3", "2/3", "3/3"])

    def test_a_release_of_only_audio_or_only_video_stays_whole(self):
        for media in ((_medium(1, "CD", ["One"]), _medium(2, "DVD-Audio", ["Two"])),
                      (_medium(1, "DVD-Video", ["Film"]), _medium(2, "Blu-ray", ["Film"]))):
            album, _ = album_from(_with_media(*media))
            self.assertIsNone(album.audio_only)

    def test_the_files_decide_which_one_is_used(self):
        from psytags.websources import albumauto
        album, _ = album_from(_with_media(_medium(1, "DVD-Video", ["Film A", "Film B", "Film C"]),
                                          _medium(2, "CD", ["One", "Two"])))
        self.assertIs(albumauto.for_files(album, 2), album.audio_only)
        self.assertIs(albumauto.for_files(album, 5), album)          # ripped everything
        plain, _ = album_from(RELEASE)
        self.assertIs(albumauto.for_files(plain, 1), plain)

    def test_a_search_row_tells_its_audio_tracks(self):
        from psytags.websources import albumauto
        row = musicbrainz._row({"id": "x", "track-count": 23,
                                "media": [{"format": "CD", "track-count": 11},
                                          {"format": "DVD-Video", "track-count": 12}]})
        self.assertEqual(albumauto.track_count(row), 23)
        self.assertEqual(albumauto.track_count(row, 11), 11)
        self.assertEqual(albumauto.track_count(row, 23), 23)
        self.assertNotIn("_audio_tracks", musicbrainz._row({"id": "x", "track-count": 11,
                                           "media": [{"format": "CD", "track-count": 11}]}))


def _file(title):
    from psytags.track import Track
    t = Track(f"{title}.flac")
    t.set("TITLE", title)
    return t


class VideoTracksWithFilesTest(unittest.TestCase):
    """Files beside the CDs that are tracks of the DVD are matched with them."""

    def _album(self):
        return album_from(_with_media(_medium(1, "CD", ["One", "Two", "Three", "Four"]),
                                      _medium(2, "DVD-Video", ["Film", "Live Song", "Interview"])))[0]

    def test_the_tracks_of_the_dvd_are_known(self):
        self.assertEqual(self._album().video_tracks, [4, 5, 6])

    def test_a_file_with_the_title_of_a_dvd_track_brings_it_in(self):
        from psytags.websources import albumauto
        files = [_file(t) for t in ("One", "Two", "Three", "Four", "Live Song")]
        dvd = albumauto.with_video_tracks(self._album(), files)
        self.assertEqual(dvd.fields["TITLE"], ["One", "Two", "Three", "Four", "Live Song"])
        self.assertEqual(dvd.fields["TRACK"][-1], "2/3")              # numbers of the whole release
        self.assertEqual(dvd.fields["DISCNUMBER"][-1], "2/2")
        self.assertTrue(dvd.partial)
        self.assertIs(albumauto.for_tracks(self._album(), files).partial, True)

    def test_files_that_fit_no_dvd_track_leave_the_cds_alone(self):
        from psytags.websources import albumauto
        album = self._album()
        files = [_file(t) for t in ("One", "Two", "Three", "Four", "Something Else")]
        self.assertIsNone(albumauto.with_video_tracks(album, files))
        self.assertIs(albumauto.for_tracks(album, files), album.audio_only)
        self.assertIsNone(albumauto.with_video_tracks(album, files[:4]))   # only the CDs

    def test_a_cd_song_of_the_same_name_does_not_take_the_dvd_track(self):
        from psytags.websources import albumauto
        album = album_from(_with_media(_medium(1, "CD", ["One", "Two", "Three", "Four"]),
                                       _medium(2, "DVD-Video", ["One", "Bonus"])))[0]
        files = [_file(t) for t in ("One", "Two", "Three", "Four", "Other")]
        self.assertIsNone(albumauto.with_video_tracks(album, files))

    def test_a_search_row_with_room_for_dvd_files_is_a_candidate(self):
        from psytags.websources import albumauto
        row = musicbrainz._row({"id": "x", "track-count": 23,
                                "media": [{"format": "CD", "track-count": 11},
                                          {"format": "DVD-Video", "track-count": 12}]})
        match = NS(row=row)
        self.assertEqual(albumauto.candidate_rows([match], 18), [row])      # 11 CD tracks, 7 from the DVD
        self.assertEqual(albumauto.candidate_rows([match], 30), [])


if __name__ == "__main__":
    unittest.main()
