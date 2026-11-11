"""Albums that Discogs tagged stand out in the summary and can go to MusicBrainz again."""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags.i18n import set_language
from psytags.ui.dialogs import tagsources as ts
from psytags.ui.mainwindow import MainWindow
from psytags.websources.albumauto import BatchEntry


def _entry(source, ok=True):
    return BatchEntry(f"A {source}", [], ok, "Album (2020)", [], "", "", source=source)


class ActionTests(unittest.TestCase):
    def test_only_a_finished_album_from_another_source_counts(self):
        self.assertTrue(ts.from_second_source(_entry("Discogs")))
        self.assertFalse(ts.from_second_source(_entry("MusicBrainz")))
        self.assertFalse(ts.from_second_source(_entry("Discogs", ok=False)))

    def test_the_details_column_of_a_discogs_album_goes_to_musicbrainz(self):
        self.assertEqual(ts.summary_action(_entry("Discogs"), 4), "musicbrainz")
        self.assertEqual(ts.summary_action(_entry("MusicBrainz"), 4), "")

    def test_everything_with_work_left_comes_first(self):
        done = _entry("MusicBrainz")
        no_cover = _entry("MusicBrainz")
        no_cover.cover = "Kein Cover gefunden"
        no_genres = _entry("MusicBrainz")
        no_genres.genres = "Last.fm: keine Genres"
        rows = [done, no_cover, _entry("Discogs"), no_genres, _entry("MusicBrainz", ok=False)]
        order = sorted(rows, key=ts.summary_rank)
        self.assertFalse(order[0].ok)
        self.assertEqual(order[1].source, "Discogs")
        self.assertEqual(set(map(id, order[2:4])), {id(no_cover), id(no_genres)})
        self.assertIs(order[4], done)


class DialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        set_language("de")

    def test_a_discogs_album_says_so_and_offers_musicbrainz(self):
        d = ts.BatchSummaryDialog([_entry("MusicBrainz"), _entry("Discogs")], lambda t: t)
        self.addCleanup(d.deleteLater)
        first = d.table.topLevelItem(0)                 # done from Discogs comes before done from MusicBrainz
        self.assertEqual(first.text(1), "Erledigt · Discogs")
        button = d.table.itemWidget(first, 4)
        self.assertEqual(button.text(), "MusicBrainz erneut versuchen")
        button.click()
        self.assertEqual((d.chosen.source, d.action), ("Discogs", "musicbrainz"))
        self.assertIsNone(d.table.itemWidget(d.table.topLevelItem(1), 4))

    def test_the_button_opens_the_musicbrainz_search(self):
        e = _entry("Discogs")
        dlg = mock.MagicMock(chosen=e, action="musicbrainz")
        dlg.exec.return_value = 1
        win = mock.MagicMock(_last_batch=[e])
        with mock.patch.object(ts, "BatchSummaryDialog", return_value=dlg):
            MainWindow.show_batch_summary(win)
        win.run_source.assert_called_once_with(quick=True, note="Bisher von Discogs")


if __name__ == "__main__":
    unittest.main()
