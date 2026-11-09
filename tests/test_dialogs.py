import os
import shutil
import tempfile
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton

from psytags import config


class SummaryButtonTests(unittest.TestCase):
    """What can still be done in the result window is a button, one click away."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.dir = tempfile.mkdtemp()                 # dialogs remember their geometry
        cls.orig_config_dir = config.config_dir
        config.config_dir = lambda: cls.dir

    @classmethod
    def tearDownClass(cls):
        config.config_dir = cls.orig_config_dir
        shutil.rmtree(cls.dir, ignore_errors=True)

    @staticmethod
    def _entry(ok=True, cover="", genres=""):
        from psytags.websources import albumauto
        return albumauto.BatchEntry("A", [], ok, "A (2001)", [], cover, genres)

    def _dialog(self, *entries):
        from psytags.ui.dialogs.tagsources import BatchSummaryDialog
        d = BatchSummaryDialog(list(entries), lambda tracks: tracks)
        self.addCleanup(d.deleteLater)
        d.show()
        QApplication.processEvents()
        return d

    @staticmethod
    def _button(d, column, row=0):
        return d.table.itemWidget(d.table.topLevelItem(row), column)

    def test_a_failed_cover_can_be_fetched_with_one_click(self):
        e = self._entry(cover="zu klein")
        d = self._dialog(e)
        button = self._button(d, 2)
        self.assertEqual(button.text(), "Nachholen")
        self.assertEqual(button.toolTip(), "zu klein")
        self.assertEqual(d.table.topLevelItem(0).text(2), "")
        button.click()
        self.assertIs(d.chosen, e)
        self.assertEqual(d.action, "cover")
        self.assertEqual(d.result(), 1)

    def test_failed_genres_too(self):
        e = self._entry(genres="HTTP 502")
        d = self._dialog(e)
        self._button(d, 3).click()
        self.assertEqual(d.action, "genres")

    def test_an_open_album_can_be_edited_with_one_click(self):
        e = self._entry(ok=False, cover=None, genres=None)
        d = self._dialog(e)
        button = self._button(d, 1)
        self.assertEqual(button.text(), "Bearbeiten")
        self.assertEqual(d.table.topLevelItem(0).text(1), "")
        button.click()
        self.assertIs(d.chosen, e)
        self.assertEqual(d.action, "manual")

    def test_finished_steps_have_no_button(self):
        d = self._dialog(self._entry(cover="", genres=None))
        for column in (1, 2, 3):
            self.assertIsNone(self._button(d, column))
        self.assertEqual(d.table.topLevelItem(0).text(2), "\u2612")

    def test_enter_does_not_press_a_row_button(self):
        d = self._dialog(self._entry(cover="zu klein"))
        self.assertFalse(self._button(d, 2).autoDefault())
        self.assertEqual(self._button(d, 2).objectName(), "RowAction")

    def test_rows_stay_even_and_buttons_fit(self):
        d = self._dialog(self._entry(), self._entry(cover="zu klein"), self._entry(ok=False, cover=None, genres=None))
        d.table.doItemsLayout()
        rows = [d.table.topLevelItem(i) for i in range(3)]
        self.assertEqual(len({d.table.visualItemRect(r).height() for r in rows}), 1)
        for column in (1, 2):
            button = next(d.table.itemWidget(r, column) for r in rows if d.table.itemWidget(r, column))
            self.assertGreaterEqual(d.table.columnWidth(column), button.sizeHint().width())

    def test_the_text_of_a_button_always_fits(self):
        d = self._dialog(self._entry(cover="zu klein"))
        button = self._button(d, 2)
        needed = button.fontMetrics().horizontalAdvance(button.text()) + 26     # padding, border, margin
        self.assertGreaterEqual(button.minimumWidth(), needed)
        self.assertGreaterEqual(d.table.columnWidth(2), button.minimumWidth())

    def test_double_click_is_no_longer_explained(self):
        from PySide6.QtWidgets import QLabel
        d = self._dialog(self._entry(cover="zu klein"))
        self.assertFalse([l.text() for l in d.findChildren(QLabel) if "Doppelklick" in l.text()])
        self.assertFalse([b.text() for b in d.findChildren(QPushButton) if b.text() == "Manuell bearbeiten"])


class ResultOrderTests(unittest.TestCase):
    """The list keeps the order of the search: the best edition is on top and preselected."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.dir = tempfile.mkdtemp()
        cls.orig_config_dir = config.config_dir
        config.config_dir = lambda: cls.dir

    @classmethod
    def tearDownClass(cls):
        config.config_dir = cls.orig_config_dir
        shutil.rmtree(cls.dir, ignore_errors=True)

    ROWS = [{"Score": "100", "Album": "Richtig", "_preview": ""}, {"Score": "83", "Album": "Pt. II", "_preview": ""},
            {"Score": "33", "Album": "Anderes", "_preview": ""}, {"Score": "69", "Album": "Live", "_preview": ""}]

    def _dialog(self):
        from psytags.ui.dialogs.tagsources import ResultsDialog
        d = ResultsDialog(SimpleNamespace(name="Reihenfolge", index_columns=["Score", "Album"]), list(self.ROWS))
        self.addCleanup(d.deleteLater)
        d.show()
        QApplication.processEvents()
        return d

    @staticmethod
    def _albums(d):
        return [d.tree.topLevelItem(i).text(1) for i in range(d.tree.topLevelItemCount())]

    def test_a_lower_score_never_moves_above_100(self):
        d = self._dialog()
        self.assertEqual(self._albums(d), ["Richtig", "Pt. II", "Anderes", "Live"])
        self.assertIs(d.selected(), self.ROWS[0])

    def test_columns_can_still_be_sorted_by_hand(self):
        d = self._dialog()
        self.assertTrue(d.tree.isSortingEnabled())
        d.tree.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        self.assertEqual(self._albums(d)[0], "Anderes")

    def test_a_sorting_from_last_time_does_not_change_the_order(self):
        first = self._dialog()
        first.tree.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        first.accept()
        QApplication.processEvents()
        second = self._dialog()
        self.assertEqual(self._albums(second), ["Richtig", "Pt. II", "Anderes", "Live"])
        self.assertIs(second.selected(), self.ROWS[0])


class TagSourceButtonTests(unittest.TestCase):
    """Wizard buttons of the tag source dialogs: [< Back] [Next >] [Cancel], Enter = Next."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.dir = tempfile.mkdtemp()                 # dialogs remember their geometry
        cls.orig_config_dir = config.config_dir
        config.config_dir = lambda: cls.dir

    @classmethod
    def tearDownClass(cls):
        config.config_dir = cls.orig_config_dir
        shutil.rmtree(cls.dir, ignore_errors=True)

    def _dialog(self):
        from psytags.ui.dialogs.tagsources import ResultsDialog
        d = ResultsDialog(SimpleNamespace(name="Test", index_columns=["Album"]),
                          [{"Album": "Make Me Real", "_preview": "https://example.invalid"}])
        d.show()
        QApplication.processEvents()
        return d

    @staticmethod
    def _button(d, text):
        return next(b for b in d.findChildren(QPushButton) if text in b.text().replace("&", ""))

    def test_next_is_default_and_enter_continues(self):
        d = self._dialog()
        self.assertTrue(self._button(d, "Weiter").isDefault())
        self.assertFalse(self._button(d, "Vorschau").isDefault())
        QTest.keyClick(d.tree, Qt.Key.Key_Return)
        self.assertEqual(d.result(), 1)

    def test_heading_names_source_and_hits(self):
        d = self._dialog()
        self.assertEqual(d.title_label.text(), "Suchergebnisse")
        self.assertEqual(d.subtitle_label.text(), "Test · 1 Treffer")

    def test_note_joins_the_heading(self):
        d = self._dialog()
        d.add_note("Nicht sicher erkannt")
        self.assertEqual(d.subtitle_label.text(), "Test · 1 Treffer · Nicht sicher erkannt")

    def test_own_heading_replaces_title_and_lead(self):
        d = self._dialog()
        d.set_heading("Cover von MusicBrainz", "Bitte das passende Album wählen")
        self.assertEqual(d.title_label.text(), "Cover von MusicBrainz")
        self.assertEqual(d.windowTitle(), "Cover von MusicBrainz")
        self.assertEqual(d.subtitle_label.text(), "Bitte das passende Album wählen · 1 Treffer")

    def test_next_is_the_highlighted_button(self):
        d = self._dialog()
        self.assertEqual(self._button(d, "Weiter").objectName(), "DialogPrimary")
        self.assertNotIn("&", self._button(d, "Weiter").text())

    def test_back_sits_directly_left_of_next(self):
        d = self._dialog()
        back, nxt = self._button(d, "Zurück"), self._button(d, "Weiter")
        self.assertEqual(back.parent(), nxt.parent())
        self.assertLess(back.x(), nxt.x())
        self.assertLessEqual(nxt.x() - back.geometry().right(), 12)
        back.click()
        self.assertEqual(d.result(), 2)


if __name__ == "__main__":
    unittest.main()
