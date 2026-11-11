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
    def test_click_sorting_is_stable(self):
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

    def test_an_album_from_discogs_is_marked_as_such(self):
        from psytags.ui.filelist import DISCOGS
        a1, a2 = _track("A", 1, 1), _track("A", 1, 2)
        for t in (a1, a2):
            t.set("DISCOGS_RELEASE_ID", "77")
        self.assertEqual(album_bands([a1, a2])[0].status[0], ("Discogs", DISCOGS))
        a1.set("MUSICBRAINZ_ALBUMID", "x")             # MusicBrainz clears the Discogs ID of its files
        a1.set("DISCOGS_RELEASE_ID", [])
        self.assertEqual(album_bands([a1, a2])[0].status[0], ("Album", False))
        a2.set("MUSICBRAINZ_ALBUMID", "x")
        self.assertEqual(album_bands([a1, a2])[0].status[0], ("Album", True))


class BandClickTests(unittest.TestCase):
    """A click on an album heading selects the album; with Ctrl it adds the album or takes it out."""

    def setUp(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from psytags.ui.filelist import FileListView
        self.app = QApplication.instance() or QApplication([])
        self.a = [_track("A", 1, 1), _track("A", 1, 2)]
        self.b = [_track("B", 1, 1), _track("B", 1, 2)]
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks(self.a + self.b)
        self.view = FileListView(m)
        self.addCleanup(self.view.deleteLater)
        self.view.resize(600, 400)
        self.view._refresh_bands()

    def _click_band(self, tracks, ctrl=False):
        from PySide6.QtCore import QPoint, Qt
        from PySide6.QtTest import QTest
        row = self.view.model().rows.index(tracks[0])
        y = self.view.rowViewportPosition(row) + 4
        mods = Qt.KeyboardModifier.ControlModifier if ctrl else Qt.KeyboardModifier.NoModifier
        QTest.mouseClick(self.view.viewport(), Qt.MouseButton.LeftButton, mods, QPoint(40, y))

    def _selected(self):
        return self.view.selected_tracks()

    def test_a_click_selects_only_that_album(self):
        self._click_band(self.a)
        self._click_band(self.b)
        self.assertEqual(self._selected(), self.b)

    def test_ctrl_adds_a_second_album(self):
        self._click_band(self.a)
        self._click_band(self.b, ctrl=True)
        self.assertEqual(self._selected(), self.a + self.b)

    def test_ctrl_adds_an_album_to_single_songs(self):
        self.view.select_tracks([self.a[1]])
        self._click_band(self.b, ctrl=True)
        self.assertEqual(self._selected(), [self.a[1]] + self.b)

    def test_ctrl_on_a_selected_album_takes_it_out(self):
        self._click_band(self.a)
        self._click_band(self.b, ctrl=True)
        self._click_band(self.a, ctrl=True)
        self.assertEqual(self._selected(), self.b)


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

    def test_fields_with_a_list_show_an_arrow_in_both_themes(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QColor
        from PySide6.QtWidgets import QApplication, QComboBox
        self.app = QApplication.instance() or QApplication([])
        self.addCleanup(theme.use, "mocha")
        for name in theme.THEMES:
            theme.use(name)
            combo = QComboBox()
            combo.setEditable(True)
            combo.addItems(["a", "b"])
            combo.setStyleSheet(theme.style_sheet())
            combo.resize(200, 30)
            image = combo.grab().toImage()
            background = QColor(theme.FIELD).name()
            drawn = [(x, y) for x in range(image.width() - 18, image.width() - 2) for y in range(3, image.height() - 3)
                     if QColor(image.pixel(x, y)).name() != background]
            self.assertTrue(drawn, name)
            xs, ys = [x for x, _y in drawn], [y for _x, y in drawn]
            width, middle = max(xs) - min(xs) + 1, (max(xs) + min(xs)) // 2
            self.assertGreater(width, max(ys) - min(ys) + 1, name)
            top = [x for x, y in drawn if y == min(ys)]             # two tips at the top ...
            bottom = [x for x, y in drawn if y == max(ys)]          # ... one point in the middle at the bottom
            self.assertNotIn(middle, top, name)
            self.assertLess(max(bottom) - min(bottom), width / 2, name)
            combo.setEnabled(False)                                 # nothing to open, so no arrow
            image = combo.grab().toImage()
            self.assertFalse([1 for x in range(image.width() - 18, image.width() - 2)
                              for y in range(3, image.height() - 3)
                              if QColor(image.pixel(x, y)).name() != background], name)

    def test_column_borders_show_in_both_themes(self):
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtGui import QColor, QStandardItemModel
        from PySide6.QtWidgets import QApplication, QTableView
        self.app = QApplication.instance() or QApplication([])
        self.addCleanup(theme.use, "mocha")
        for name in theme.THEMES:
            theme.use(name)
            model = QStandardItemModel(1, 3)
            view = QTableView()
            view.setModel(model)
            view.setStyleSheet(theme.style_sheet())
            view.resize(500, 120)
            header = view.horizontalHeader()
            image = view.grab().toImage()
            top = header.mapTo(view, header.rect().center()).y()
            x = header.mapTo(view, header.rect().topLeft()).x() + header.sectionSize(0) - 1
            self.assertEqual(QColor(image.pixel(x, top)).name(), theme.FIELD_BORDER, name)
            self.assertEqual(QColor(image.pixel(x - 8, top)).name(), theme.BACKGROUND, name)


if __name__ == "__main__":
    unittest.main()
