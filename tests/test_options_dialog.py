import os
import tempfile
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt, QThreadPool
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTabWidget

from psytags import config
from psytags.config import Options
from psytags.ui.controls import Segmented, Switch
from psytags.ui.dialogs.options import OptionsDialog
from psytags.websources import discogs, http, lastfm


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)


class DateTests(Base):
    def test_only_the_year_by_default(self):
        self.assertTrue(Options().year_only)
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.date_choice.currentData(), "year")

    def test_the_full_date_is_kept_as_option(self):
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        d.date_choice.setCurrentIndex(d.date_choice.findData("date"))
        d.accept()
        self.assertFalse(d.opts.year_only)
        d.opts.save()
        self.assertFalse(Options.load().year_only)


class DiscogsTokenTests(Base):
    def test_the_token_is_saved_without_spaces(self):
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        d.discogs_token.setText(" abc ")
        d.accept()
        self.assertEqual(config.settings().value("discogs/token"), "abc")

    def test_a_stored_token_is_shown_hidden(self):
        config.settings().setValue("discogs/token", "abc")
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.discogs_token.text(), "abc")
        self.assertEqual(d.discogs_token.echoMode(), d.discogs_token.EchoMode.Password)


class KeyMarkTests(Base):
    def _dialog(self):
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        return d

    def _settle(self):
        QThreadPool.globalInstance().waitForDone()
        self.app.processEvents()

    def _shown_with_token(self, verify):
        config.settings().setValue("discogs/token", "abc")
        with mock.patch.object(discogs, "verify_token", verify):
            d = self._dialog()
            d.show()
            self._settle()
        return d

    def test_only_building_the_dialog_asks_no_server(self):
        config.settings().setValue("discogs/token", "abc")
        with mock.patch.object(discogs, "verify_token") as verify:
            self._dialog()
            self._settle()
        verify.assert_not_called()

    def test_a_working_token_gets_the_green_mark(self):
        verify = mock.MagicMock()
        d = self._shown_with_token(verify)
        verify.assert_called_once_with("abc")
        self.assertEqual(d.discogs_field.state, "ok")
        self.assertEqual(d.discogs_field.mark.text(), "✓")

    def test_a_refused_token_gets_no_green_mark(self):
        d = self._shown_with_token(mock.MagicMock(side_effect=http.FetchError("nein")))
        self.assertEqual(d.discogs_field.state, "bad")
        self.assertNotEqual(d.discogs_field.mark.text(), "✓")

    def test_an_empty_field_asks_no_server(self):
        with mock.patch.object(discogs, "verify_token") as verify:
            d = self._dialog()
            d.show()
            self._settle()
        verify.assert_not_called()
        self.assertEqual(d.discogs_field.state, "")

    def test_typing_takes_the_old_mark_away(self):
        d = self._shown_with_token(mock.MagicMock())
        d.discogs_token.setText("abcd")
        self.assertEqual(d.discogs_field.state, "")

    def test_finishing_the_input_checks_the_new_token(self):
        d = self._dialog()
        with mock.patch.object(discogs, "verify_token") as verify:
            d.discogs_token.setText("neu")
            d.discogs_token.editingFinished.emit()
            self._settle()
        verify.assert_called_once_with("neu")
        self.assertEqual(d.discogs_field.state, "ok")

    def test_the_same_token_is_not_asked_twice(self):
        verify = mock.MagicMock()
        d = self._shown_with_token(verify)
        with mock.patch.object(discogs, "verify_token", verify):
            d.discogs_token.editingFinished.emit()
            self._settle()
        verify.assert_called_once()

    def test_an_answer_for_an_older_input_is_ignored(self):
        d = self._dialog()
        d.discogs_token.setText("neu")
        d.discogs_field._answered(("alt", True))
        self.assertEqual(d.discogs_field.state, "")

    def test_closing_before_the_answer_is_harmless(self):
        import shiboken6
        d = OptionsDialog(Options())
        release = threading.Event()
        with mock.patch.object(discogs, "verify_token", lambda key: release.wait(5)):
            d.discogs_token.setText("abc")
            d.discogs_field.check()
            shiboken6.delete(d)
            release.set()
            self._settle()

    def test_lastfm_has_the_mark_too(self):
        config.settings().setValue("lastfm/api_key", "abc")
        with mock.patch.object(lastfm, "verify_key") as verify:
            d = self._dialog()
            d.show()
            self._settle()
        verify.assert_called_once_with("abc")
        self.assertEqual(d.lastfm_field.state, "ok")


class SwitchTests(Base):
    def test_a_click_turns_it_on_and_off(self):
        switch = Switch()
        self.addCleanup(switch.deleteLater)
        switch.resize(switch.sizeHint())
        self.assertFalse(switch.isChecked())
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
        self.assertTrue(switch.isChecked())
        QTest.mouseClick(switch, Qt.MouseButton.LeftButton)
        self.assertFalse(switch.isChecked())


class SegmentedTests(Base):
    def _segmented(self):
        seg = Segmented()
        self.addCleanup(seg.deleteLater)
        for text, data in (("Wenige", "few"), ("Normal", "normal"), ("Viele", "many")):
            seg.addItem(text, data)
        return seg

    def test_the_first_item_starts_selected(self):
        self.assertEqual(self._segmented().currentData(), "few")

    def test_only_one_item_is_selected(self):
        seg = self._segmented()
        seg.setCurrentIndex(2)
        self.assertEqual(seg.currentData(), "many")
        self.assertEqual(sum(b.isChecked() for b in seg.buttons), 1)

    def test_it_finds_items_by_their_data(self):
        seg = self._segmented()
        self.assertEqual(seg.count(), 3)
        self.assertEqual(seg.findData("normal"), 1)
        self.assertEqual(seg.findData("gibt es nicht"), -1)


class DialogTests(Base):
    def _dialog(self, opts=None, section=""):
        d = OptionsDialog(opts or Options(), None, section)
        self.addCleanup(d.deleteLater)
        return d

    def test_there_are_no_tabs_any_more(self):
        self.assertIsNone(self._dialog().findChild(QTabWidget))

    def test_the_page_follows_the_workflow(self):
        self.assertEqual(self._dialog().section_keys(),
                         ["moods", "musicbrainz", "discogs", "numbers", "cover", "genres", "files", "program"])

    def test_the_discogs_token_stands_in_its_own_section(self):
        d = self._dialog()
        self.assertTrue(d._blocks["discogs"].isAncestorOf(d.discogs_token))
        self.assertFalse(d._blocks["musicbrainz"].isAncestorOf(d.discogs_token))

    def test_it_can_open_at_a_section(self):
        self.assertEqual(self._dialog(section="genres").current_section(), "genres")

    def test_it_starts_at_the_top(self):
        self.assertEqual(self._dialog().current_section(), "moods")

    def test_a_link_goes_to_its_section(self):
        d = self._dialog()
        d.show_section("cover")
        self.assertEqual(d.current_section(), "cover")

    def test_the_controls_start_from_the_options(self):
        d = self._dialog(Options(language="en", theme="latte", id3_version=4, keep_mtime=True, subfolders=False))
        self.assertEqual((d.lang.currentData(), d.theme.currentData(), d.id3.currentData()), ("en", "latte", 4))
        self.assertTrue(d.keep_mtime.isChecked())
        self.assertFalse(d.subfolders.isChecked())

    def test_saving_keeps_every_choice(self):
        d = self._dialog()
        d.lang.setCurrentIndex(d.lang.findData("en"))
        d.theme.setCurrentIndex(d.theme.findData("latte"))
        d.id3.setCurrentIndex(d.id3.findData(4))
        d.v1.setChecked(True)
        d.keep_mtime.setChecked(True)
        d.subfolders.setChecked(False)
        d.autosave.setChecked(False)
        d.accept()
        o = d.opts
        self.assertEqual((o.language, o.theme, o.id3_version), ("en", "latte", 4))
        self.assertEqual((o.write_id3v1, o.keep_mtime, o.subfolders, o.save_on_selection_change), (True, True, False, False))

    def test_a_cover_source_row_takes_its_width_from_the_list(self):
        view = self._dialog().cover_sources
        option = QStyleOptionViewItem()
        option.rect.setRect(0, 0, 5000, 46)
        self.assertEqual(view.itemDelegate().sizeHint(option, view.model().index(0, 0)).width(), 0)
        self.assertEqual(view.horizontalScrollBarPolicy(), Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

    def test_the_switch_in_a_cover_source_row_turns_it_off(self):
        d = self._dialog()
        view = d.cover_sources
        index = view.model().index(0, 0)
        delegate = view.itemDelegate()
        option = QStyleOptionViewItem()
        option.rect = view.visualRect(index)
        if option.rect.isEmpty():
            option.rect.setRect(0, 0, 400, 46)
        pos = QPointF(delegate.switch_rect(option.rect).center())
        before = view.item(0).checkState()
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, pos, pos, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        self.assertTrue(delegate.editorEvent(event, view.model(), option, index))
        self.assertNotEqual(view.item(0).checkState(), before)


if __name__ == "__main__":
    unittest.main()
