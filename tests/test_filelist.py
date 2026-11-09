import unittest

from psytags import config
from psytags.track import Track
from psytags.ui import theme
from psytags.ui.filelist import FileListModel, album_bands


def _track(album, disc, track):
    t = Track(f"{album}-{disc}-{track}.mp3")
    t.set("ALBUM", album)
    t.set("DISCNUMBER", f"{disc}/2")
    t.set("TRACK", str(track))
    return t


class SortTests(unittest.TestCase):
    def test_click_sorting_is_stable_like_mp3tag(self):
        tracks = [_track(a, d, n) for a in ("Beta", "Alpha") for d in (2, 1) for n in (3, 1, 2)]
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks(tracks)
        col = {c.name: i + 1 for i, c in enumerate(m.columns)}
        for name in ("Track", "Disc-Nummer", "Album"):        # one plain click each
            m.sort_by(col[name], add=False)
        got = [(t.get("ALBUM")[0], t.get("DISCNUMBER")[0][0], t.get("TRACK")[0]) for t in m.rows]
        want = [(a, d, n) for a in ("Alpha", "Beta") for d in "12" for n in "123"]
        self.assertEqual(got, want)


class SortAlbumTests(unittest.TestCase):
    def _model(self, tracks):
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks(tracks)
        return m

    def test_only_this_album_moves(self):
        x1, x2 = _track("Other", 1, 9), _track("Other", 1, 1)
        a1, a2, a3 = _track("A", 1, 1), _track("A", 1, 2), _track("A", 2, 1)
        m = self._model([x1, a3, a2, x2, a1])
        m.sort_album([a1, a2, a3])
        self.assertEqual(m.rows, [x1, a1, a2, x2, a3])

    def test_files_without_a_track_end_the_block(self):
        a1, a2, extra, x = _track("A", 1, 1), _track("A", 1, 2), _track("A", 1, 1), _track("Z", 1, 1)
        extra.path = extra.path.replace("A-1-1", "A-bonus")
        m = self._model([extra, a2, a1, x])
        m.sort_album([a1, a2], last=[extra])
        self.assertEqual(m.rows, [a1, a2, extra, x])


class SearchTests(unittest.TestCase):
    def _model(self):
        a, b = _track("Hollow Meridian", 1, 1), _track("Oaths in Copper", 1, 2)
        a.set("ARTIST", "Ashen Vale")
        b.set("ARTIST", "Iron Cantor")
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks([a, b])
        return m, a, b

    def test_every_word_must_appear_in_some_column(self):
        m, a, _b = self._model()
        m.set_filter("ashen HOLLOW")
        self.assertEqual(m.rows, [a])

    def test_no_match_and_clearing(self):
        m, a, b = self._model()
        m.set_filter("ashen copper")
        self.assertEqual(m.rows, [])
        m.set_filter("")
        self.assertEqual(m.rows, [a, b])


class AlbumBandTests(unittest.TestCase):
    def test_one_band_per_album_run(self):
        a1, a2, b1 = _track("A", 1, 1), _track("A", 1, 2), _track("B", 1, 1)
        bands = album_bands([a1, a2, b1])
        self.assertEqual(sorted(bands), [0, 2])
        self.assertEqual(bands[0].tracks, [a1, a2])
        self.assertEqual(bands[2].tracks, [b1])

    def test_no_bands_when_the_sort_breaks_albums_apart(self):
        a1, a2, b1, b2 = _track("A", 1, 1), _track("A", 1, 2), _track("B", 1, 1), _track("B", 1, 2)
        self.assertEqual(album_bands([a1, b1, a2, b2]), {})

    def test_single_file_still_gets_its_band(self):
        self.assertEqual(sorted(album_bands([_track("A", 1, 1)])), [0])

    def test_status_of_an_album(self):
        a1, a2 = _track("A", 1, 1), _track("A", 1, 2)
        for t in (a1, a2):
            t.set("MUSICBRAINZ_ALBUMID", "x")
            t.data.covers = [object()]
        a1.set("GENRE", "Rock")
        a1.set("MOOD", "Dark")
        status = dict(album_bands([a1, a2])[0].status)
        self.assertEqual(status, {"Album": True, "Cover": True, "Genres": False, "Moods": True})


class ThemeTests(unittest.TestCase):
    def tearDown(self):
        theme.use("mocha")

    def test_both_themes_define_the_same_colors(self):
        self.assertEqual(set(theme.MOCHA), set(theme.LATTE))

    def test_use_switches_the_colors(self):
        theme.use("latte")
        self.assertEqual(theme.ACCENT, "#8839ef")
        theme.use("mocha")
        self.assertEqual(theme.ACCENT, "#cba6f7")

    def test_unknown_theme_falls_back_to_mocha(self):
        theme.use("sepia")
        self.assertEqual(theme.CURRENT, "mocha")

    def test_style_sheet_is_complete(self):
        self.assertNotIn("$", theme.style_sheet())


if __name__ == "__main__":
    unittest.main()
