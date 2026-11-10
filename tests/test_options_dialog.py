import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QStyleOptionViewItem, QTabWidget

from psytags import config
from psytags.config import Options
from psytags.ui.controls import Segmented, Switch
from psytags.ui.dialogs.options import OptionsDialog


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
        event = QMouseEvent(QEvent.Type.MouseButtonRelease, pos, Qt.MouseButton.LeftButton,
                            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier)
        self.assertTrue(delegate.editorEvent(event, view.model(), option, index))
        self.assertNotEqual(view.item(0).checkState(), before)


if __name__ == "__main__":
    unittest.main()
