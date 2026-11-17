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
        from psytags.ui import theme
        d = self._dialog(self._entry(cover="zu klein"))
        d.setStyleSheet(theme.style_sheet())    # the style sheet decides the real size of the button
        d.show()
        self.addCleanup(d.close)
        QApplication.processEvents()
        button = self._button(d, 2)
        needed = button.fontMetrics().horizontalAdvance(button.text()) + 26     # padding, border, margin
        self.assertGreaterEqual(button.width(), needed)

    def test_the_close_button_speaks_the_language_of_the_app(self):
        from PySide6.QtWidgets import QDialogButtonBox
        d = self._dialog(self._entry(cover="zu klein"))
        close = d.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Close)
        self.assertEqual(close.text(), "Schließen")

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


class BlockMoveTests(unittest.TestCase):
    """Several marked files move together in the adjust dialog and stay marked."""

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

    def _dialog(self, n=6):
        from psytags.track import Track
        from psytags.ui.dialogs.tagsources import AdjustDialog
        from psytags.websources.base import Album
        folder = os.path.join(tempfile.gettempdir(), "album")
        self.files = [Track(os.path.join(folder, f"file{i}.mp3")) for i in range(n)]
        album = Album(fields={"TITLE": [f"Song {i}" for i in range(n)]}, per_track={"TITLE"}, tracks=n)
        d = AdjustDialog(album, list(self.files))
        self.addCleanup(d.deleteLater)
        return d

    def _mark(self, d, *rows):
        d.table.clearSelection()
        for r in rows:
            d.table.topLevelItem(r).setSelected(True)

    def _order(self, d):
        return [self.files.index(f) for f in d.files]

    def test_a_block_moves_up_and_stays_marked(self):
        d = self._dialog()
        self._mark(d, 2, 3, 4)
        d._move(-1)
        self.assertEqual(self._order(d), [0, 2, 3, 4, 1, 5])
        self.assertEqual(d.table.selected_rows(), [1, 2, 3])
        d._move(-1)
        self.assertEqual(self._order(d), [2, 3, 4, 0, 1, 5])

    def test_a_block_at_the_edge_stays_together(self):
        d = self._dialog()
        self._mark(d, 0, 1)
        d._move(-1)
        self.assertEqual(self._order(d), [0, 1, 2, 3, 4, 5])
        self._mark(d, 4, 5)
        d._move(1)
        self.assertEqual(self._order(d), [0, 1, 2, 3, 4, 5])
        self.assertEqual(d.table.selected_rows(), [4, 5])

    def test_a_block_moves_down(self):
        d = self._dialog()
        self._mark(d, 0, 1)
        d._move(1)
        self.assertEqual(self._order(d), [2, 0, 1, 3, 4, 5])
        self.assertEqual(d.table.selected_rows(), [1, 2])

    def test_dropped_files_land_together_in_front_of_the_target(self):
        d = self._dialog()
        d.table.dropped.emit([1, 4], 3)                    # two files that were apart
        self.assertEqual(self._order(d), [0, 2, 1, 4, 3, 5])
        self.assertEqual(d.table.selected_rows(), [2, 3])
        d.table.dropped.emit([2, 3], 6)                    # behind the last row
        self.assertEqual(self._order(d), [0, 2, 3, 5, 1, 4])
        d.table.dropped.emit([4, 5], 0)
        self.assertEqual(self._order(d), [1, 4, 0, 2, 3, 5])

    def test_one_file_still_moves_by_the_current_row(self):
        d = self._dialog()
        d.table.clearSelection()
        d.table.setCurrentItem(d.table.topLevelItem(3))
        d._move(-1)
        self.assertEqual(self._order(d), [0, 1, 3, 2, 4, 5])


class DvdTracksBoxTests(unittest.TestCase):
    """The adjust dialog offers the tracks of a DVD only when files are left for them."""

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

    def _dialog(self, titles):
        from psytags.track import Track
        from psytags.ui.dialogs.tagsources import AdjustDialog
        from psytags.websources.base import Album
        folder = os.path.join(tempfile.gettempdir(), "album")
        files = []
        for title in titles:
            t = Track(os.path.join(folder, f"{title}.mp3"))
            t.set("TITLE", title)
            files.append(t)
        whole = Album(fields={"TITLE": ["One", "Two", "Film", "Live Song"]}, per_track={"TITLE"},
                      tracks=4, video_tracks=[2, 3])
        whole.audio_only = Album(fields={"TITLE": ["One", "Two"]}, per_track={"TITLE"}, tracks=2)
        d = AdjustDialog(whole.audio_only, files, whole=whole)
        self.addCleanup(d.deleteLater)
        return d

    def test_files_of_the_cds_alone_get_no_box(self):
        d = self._dialog(["One", "Two"])
        self.assertTrue(d.dvd_box.isHidden())

    def test_a_file_left_over_gets_the_box_unticked(self):
        d = self._dialog(["One", "Two", "Other"])
        self.assertFalse(d.dvd_box.isHidden())
        self.assertFalse(d.dvd_box.isChecked())
        self.assertEqual(d.album.tracks, 2)
        d.dvd_box.setChecked(True)
        self.assertEqual(d.album.tracks, 4)
        self.assertEqual(d.source_table.topLevelItemCount(), 4)

    def test_a_file_with_a_dvd_title_ticks_it_and_lands_there(self):
        d = self._dialog(["One", "Two", "Live Song"])
        self.assertTrue(d.dvd_box.isChecked())
        self.assertEqual(d.files[3].filename, "Live Song.mp3")
        self.assertEqual([t.filename for t, _v in d.plan()], ["One.mp3", "Two.mp3", "Live Song.mp3"])
        d.dvd_box.setChecked(False)
        self.assertEqual([t.filename for t in d.leftovers()], ["Live Song.mp3"])


class DropScrollTests(unittest.TestCase):
    """After a drop the list stays where it is, wherever Qt thinks the pointer is."""

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

    def test_the_scrolling_at_the_edge_ends_with_the_drop(self):
        import time
        from PySide6.QtCore import QPointF
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QAbstractItemView
        from psytags.track import Track
        from psytags.ui.dialogs.tagsources import AdjustDialog
        from psytags.websources.base import Album
        n = 60
        files = [Track(os.path.join(tempfile.gettempdir(), "album", f"file{i}.mp3")) for i in range(n)]
        album = Album(fields={"TITLE": [f"Song {i}" for i in range(n)]}, per_track={"TITLE"}, tracks=n)
        d = AdjustDialog(album, files)
        self.addCleanup(d.deleteLater)
        d.resize(1180, 660)
        d.show()
        self.app.processEvents()
        table, bar = d.table, d.table.verticalScrollBar()
        bar.setValue(bar.maximum())
        table.setCurrentItem(table.topLevelItem(50))
        table.setState(QAbstractItemView.State.DraggingState)
        table.startAutoScroll()                          # as while dragging near the edge

        class Drop:
            def source(self):
                return table

            def position(self):
                return QPointF(table.visualItemRect(table.topLevelItem(45)).center())

            def setDropAction(self, _action):
                pass

            def accept(self):
                pass
        table.dropEvent(Drop())
        kept = bar.value()
        QCursor.setPos(-500, -500)                       # a pointer Qt places above the list
        end = time.monotonic() + 0.8
        while time.monotonic() < end:
            self.app.processEvents()
        self.assertGreater(kept, 0)
        self.assertEqual(bar.value(), kept)
