import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.config import Options
from psytags.track import Track
from psytags.ui.mainwindow import MainWindow
from psytags.ui.tagpanel import blank_text, keep_text
from psytags.websources import albummatch

GAPLESS = "COMMENT ITUNSMPB"
OLD_RIP = "COMMENT ID3V1 COMMENT"


def track(fields=None):
    t = Track("x.mp3")
    for name, value in (fields or {}).items():
        t.set(name, value)
    return t


def commented():
    return track({"COMMENT": "gerippt von wem", OLD_RIP: "alt", GAPLESS: "00000000 0210"})


class DropCommentsTests(unittest.TestCase):
    def test_comments_go_and_technical_itunes_values_stay(self):
        t = commented()
        albummatch.drop_comments(t)
        self.assertEqual(t.get("COMMENT"), [])
        self.assertEqual(t.get(OLD_RIP), [])
        self.assertEqual(t.get(GAPLESS), ["00000000 0210"])

    def test_a_file_without_comments_is_fine(self):
        t = track({"TITLE": "A"})
        albummatch.drop_comments(t)
        self.assertEqual(t.get("TITLE"), ["A"])


class CommentNameTests(unittest.TestCase):
    def _written(self, existing, fields):
        from mutagen import id3
        from psytags import tags
        frames = id3.ID3()
        for desc in existing:
            frames.add(id3.COMM(encoding=3, lang="eng", desc=desc, text=["x"]))
        tags._write_id3(frames, fields, None)
        return sorted(f.desc for f in frames.getall("COMM"))

    def test_the_spelling_in_the_file_is_kept(self):
        got = self._written(["iTunSMPB", "Meine Notiz"], {"COMMENT ITUNSMPB": ["x"], "COMMENT MEINE NOTIZ": ["x"]})
        self.assertEqual(got, ["Meine Notiz", "iTunSMPB"])

    def test_itunes_names_already_in_capitals_are_repaired(self):
        for damaged, right in (("ITUNSMPB", "iTunSMPB"), ("ITUNNORM", "iTunNORM"), ("ITUNPGAP", "iTunPGAP")):
            self.assertEqual(self._written([damaged], {"COMMENT " + damaged: ["x"]}), [right])

    def test_a_field_without_a_frame_keeps_its_name(self):
        self.assertEqual(self._written([], {"COMMENT NOTIZ": ["x"]}), ["NOTIZ"])


class ImportTests(unittest.TestCase):
    def _imported(self, drop=True, archive=("r", "g"), values=None):
        win = mock.MagicMock()
        win.opts.drop_comments = drop
        win._lastfm_enabled.return_value = False
        win._cover_big_enough.return_value = False
        t = commented()
        MainWindow._finish_source_import(win, "MB", [(t, values or {"TITLE": "neu"})], None, [], False, True, archive)
        win._write.call_args_list[0].args[2](t)
        return t

    def test_a_musicbrainz_import_removes_the_comments(self):
        t = self._imported()
        self.assertEqual(t.get("COMMENT"), [])
        self.assertEqual(t.get("TITLE"), ["neu"])

    def test_a_cover_settled_in_the_dialog_is_still_a_musicbrainz_import(self):
        self.assertEqual(self._imported(archive=()).get("COMMENT"), [])

    def test_the_option_can_switch_it_off(self):
        self.assertEqual(self._imported(drop=False).get("COMMENT"), ["gerippt von wem"])

    def test_other_tag_sources_leave_comments_alone(self):
        self.assertEqual(self._imported(archive=None).get("COMMENT"), ["gerippt von wem"])

    def test_a_comment_from_the_source_itself_is_written(self):
        t = self._imported(values={"COMMENT": "von der Quelle"})
        self.assertEqual(t.get("COMMENT"), ["von der Quelle"])


class GuardedTests(unittest.TestCase):
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

    def _window(self):
        w = MainWindow()
        w._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(w.deleteLater)
        return w


class PanelTests(GuardedTests):
    def _loaded(self, *comments):
        w = self._window()
        w.panel.blank_comments = True               # the option is on
        w.panel.load([track({"COMMENT": c}) for c in comments])
        return w.panel, w.panel.combos["COMMENT"]

    def test_several_files_start_on_blank_without_counting_as_an_edit(self):
        panel, combo = self._loaded("a", "b")
        self.assertEqual(combo.currentText(), blank_text())
        self.assertFalse(panel.dirty)
        self.assertEqual(panel.pending(), {})
        self.assertEqual(panel.pending(True), {"COMMENT": None})

    def test_equal_comments_on_several_files_start_on_blank_too(self):
        _panel, combo = self._loaded("a", "a")
        self.assertEqual(combo.currentText(), blank_text())

    def test_one_file_shows_its_comment(self):
        panel, combo = self._loaded("a")
        self.assertEqual(combo.currentText(), "a")
        self.assertEqual(panel.pending(True), {})

    def test_keep_can_still_be_chosen(self):
        panel, combo = self._loaded("a", "b")
        combo.setEditText(keep_text())
        combo.dirty = True
        self.assertEqual(panel.pending(True), {})

    def test_a_typed_comment_wins(self):
        panel, combo = self._loaded("a", "b")
        combo.setEditText("neu")
        combo.dirty = True
        self.assertEqual(panel.pending(True), {"COMMENT": "neu"})

    def test_switched_off_several_files_keep_their_comments(self):
        w = self._window()
        w.panel.blank_comments = False
        w.panel.load([track({"COMMENT": "a"}), track({"COMMENT": "b"})])
        self.assertEqual(w.panel.combos["COMMENT"].currentText(), keep_text())
        self.assertEqual(w.panel.pending(True), {})

    def test_other_fields_stay_on_keep(self):
        w = self._window()
        w.panel.load([track({"ALBUM": "a"}), track({"ALBUM": "b"})])
        self.assertEqual(w.panel.combos["ALBUM"].currentText(), keep_text())

    def test_ctrl_s_and_enter_are_the_real_saves(self):
        with mock.patch.object(MainWindow, "save_by_user") as save:
            w = self._window()
            w.act_save.setEnabled(True)
            w.act_save.trigger()
            w.panel.save_requested.emit()
        self.assertEqual(save.call_count, 2)


class SaveTests(unittest.TestCase):
    def test_a_real_save_takes_the_preselection(self):
        win = mock.MagicMock()
        MainWindow.save_by_user(win)
        win.save_tags.assert_called_once_with(True)

    def test_saving_from_elsewhere_does_not(self):
        win = mock.MagicMock()
        tracks = [commented()]
        win.view.selected_tracks.return_value = tracks
        MainWindow.save_tags(win)
        win._write_panel.assert_called_once_with(tracks, False)

    def _write_panel(self, pending, preselected):
        win = mock.MagicMock()
        win.panel.pending.return_value = pending
        win.panel.covers_dirty = False
        t = commented()
        MainWindow._write_panel(win, [t], preselected)
        win.panel.pending.assert_called_once_with(preselected)
        win._write.call_args.args[2](t)
        return t

    def test_a_blank_comment_on_a_real_save_takes_all_comments(self):
        t = self._write_panel({"COMMENT": None}, True)
        self.assertEqual(t.get("COMMENT"), [])
        self.assertEqual(t.get(OLD_RIP), [])
        self.assertEqual(t.get(GAPLESS), ["00000000 0210"])

    def test_a_save_without_the_preselection_leaves_them(self):
        t = self._write_panel({}, False)
        self.assertEqual(t.get("COMMENT"), ["gerippt von wem"])
        self.assertEqual(t.get(OLD_RIP), ["alt"])


class OptionTests(GuardedTests):
    def test_comments_stay_by_default(self):
        # a new user must not lose comments without having chosen so
        self.assertFalse(Options().drop_comments)
        self.assertFalse(Options.load().drop_comments)
        self.assertFalse(self._window().panel.blank_comments)

    def test_a_stored_choice_to_delete_them_stays(self):
        Options(drop_comments=True).save()
        self.assertTrue(Options.load().drop_comments)
        self.assertTrue(self._window().panel.blank_comments)

    def test_the_options_dialog_can_switch_it_on(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        self.assertFalse(d.drop_comments.isChecked())
        d.drop_comments.setChecked(True)
        d.accept()
        self.assertTrue(d.opts.drop_comments)

    def test_a_new_setting_reaches_the_panel(self):
        win = mock.MagicMock()
        with mock.patch("psytags.ui.dialogs.options.OptionsDialog") as dialog:
            dialog.return_value.exec.return_value = 1
            dialog.return_value.opts = Options(drop_comments=False)
            MainWindow._open_options(win)
        self.assertFalse(win.panel.blank_comments)

    def test_the_setting_is_read_at_the_start(self):
        Options(drop_comments=False).save()
        self.assertFalse(self._window().panel.blank_comments)


if __name__ == "__main__":
    unittest.main()
