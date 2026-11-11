"""Files added to an album that is already tagged take the album's values from the others."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.track import Track
from psytags.websources import albumauto

ALBUM_ID = "release-1"


def tagged(n, artist="Band"):
    t = Track(os.path.join(tempfile.gettempdir(), "Album", f"{n:02}.mp3"))
    for name, value in {"ALBUM": "Album", "ARTIST": artist, "ALBUMARTIST": "Band",
                        "MUSICBRAINZ_ALBUMID": ALBUM_ID, "MUSICBRAINZ_RELEASEGROUPID": "rg",
                        "MUSICBRAINZ_ALBUMARTISTID": "aa", "ORIGYEAR": "2026", "YEAR": "2026",
                        "ARTISTSORT": artist, "ALBUMARTISTSORT": "Band", "MUSICBRAINZ_ARTISTID": "a",
                        "MUSICBRAINZ_TRACKID": f"track-{n}", "TITLE": f"Song {n}", "TRACK": f"{n}/13"}.items():
        t.set(name, value)
    return t


def bonus(n, artist="Band"):
    t = Track(os.path.join(tempfile.gettempdir(), "Album", f"{n:02}.mp3"))
    for name, value in {"ALBUM": "Album", "ARTIST": artist, "ALBUMARTIST": "Band",
                        "YEAR": "2026", "TITLE": f"Bonus {n}", "TRACK": f"{n}/13"}.items():
        t.set(name, value)
    return t


class GapTests(unittest.TestCase):
    def test_a_bonus_track_takes_the_album_values(self):
        extra = bonus(8)
        plan = albumauto.album_gaps([tagged(1), tagged(2), extra])
        self.assertEqual([t for t, _values in plan], [extra])
        values = plan[0][1]
        self.assertEqual(values["MUSICBRAINZ_ALBUMID"], [ALBUM_ID])
        self.assertEqual(values["MUSICBRAINZ_RELEASEGROUPID"], ["rg"])
        self.assertEqual(values["MUSICBRAINZ_ALBUMARTISTID"], ["aa"])
        self.assertEqual(values["ORIGYEAR"], ["2026"])
        self.assertEqual(values["ALBUMARTISTSORT"], ["Band"])
        self.assertEqual(values["ARTISTSORT"], ["Band"])
        self.assertEqual(values["MUSICBRAINZ_ARTISTID"], ["a"])

    def test_what_belongs_to_one_song_is_never_copied(self):
        values = albumauto.album_gaps([tagged(1), tagged(2), bonus(8)])[0][1]
        for name in ("MUSICBRAINZ_TRACKID", "TITLE", "TRACK"):
            self.assertNotIn(name, values)

    def test_values_the_file_already_has_stay(self):
        extra = bonus(8)
        extra.set("YEAR", "2025")
        values = albumauto.album_gaps([tagged(1), extra])[0][1]
        self.assertNotIn("YEAR", values)

    def test_another_artist_does_not_get_the_sort_name_of_the_album_artist(self):
        values = albumauto.album_gaps([tagged(1), tagged(2), bonus(8, artist="Gast")])[0][1]
        self.assertNotIn("ARTISTSORT", values)
        self.assertNotIn("MUSICBRAINZ_ARTISTID", values)
        self.assertEqual(values["MUSICBRAINZ_ALBUMID"], [ALBUM_ID])

    def test_nothing_without_a_gap_or_without_tagged_files(self):
        self.assertEqual(albumauto.album_gaps([tagged(1), tagged(2)]), [])
        self.assertEqual(albumauto.album_gaps([bonus(1), bonus(2)]), [])

    def test_two_different_releases_are_left_to_musicbrainz(self):
        other = tagged(2)
        other.set("MUSICBRAINZ_ALBUMID", "anderes")
        self.assertEqual(albumauto.album_gaps([tagged(1), other, bonus(8)]), [])

    def test_a_value_the_tagged_files_disagree_on_is_left_out(self):
        other = tagged(2)
        other.set("ORIGYEAR", "2025")
        values = albumauto.album_gaps([tagged(1), other, bonus(8)])[0][1]
        self.assertNotIn("ORIGYEAR", values)
        self.assertIn("MUSICBRAINZ_ALBUMID", values)


class RunTests(unittest.TestCase):
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

    def _window(self, tracks):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        w._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(w.deleteLater)
        w.model.set_tracks(tracks)
        w.opts.auto_moods = False
        return w

    def test_the_automatic_run_fills_the_gap_without_asking_musicbrainz(self):
        tracks = [tagged(1), tagged(2), bonus(8)]
        w = self._window(tracks)
        saved = []
        with mock.patch.object(w, "_auto_one") as search, \
                mock.patch.object(w, "_write", side_effect=lambda _label, ts, mutate: [mutate(t) for t in ts]
                                  and saved.extend(ts) or len(ts)), \
                mock.patch.object(w, "show_batch_summary"):
            w.auto_all_albums()
        search.assert_not_called()
        self.assertEqual(saved, [tracks[2]])
        self.assertEqual(tracks[2].get("MUSICBRAINZ_ALBUMID"), [ALBUM_ID])
        entry = w._last_batch[0]
        self.assertTrue(entry.ok)
        self.assertIn(id(tracks[2]), w._auto_done)

    def test_musicbrainz_automatic_on_one_album_fills_it_too(self):
        tracks = [tagged(1), bonus(8)]
        w = self._window(tracks)
        w.view.select_tracks(tracks)
        with mock.patch.object(w, "_background") as search, \
                mock.patch.object(w, "_write", side_effect=lambda _label, ts, mutate: [mutate(t) for t in ts]
                                  and len(ts)):
            w.auto_musicbrainz()
        search.assert_not_called()
        self.assertEqual(tracks[1].get("MUSICBRAINZ_ALBUMID"), [ALBUM_ID])

    def test_an_album_without_tagged_files_is_searched_as_before(self):
        tracks = [bonus(1), bonus(2)]
        w = self._window(tracks)
        with mock.patch.object(w, "_auto_one", return_value=albumauto.BatchEntry("x", tracks, False, "")) as search, \
                mock.patch.object(w, "show_batch_summary"):
            w.auto_all_albums()
        search.assert_called_once()


if __name__ == "__main__":
    unittest.main()
