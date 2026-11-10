import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config, convert, namescheme, numbering


class Fake:
    size = 0                                   # the status bar sums sizes and lengths

    def __init__(self, path="/music/Old/01.mp3", **fields):
        self.fields = {k.upper(): (v if isinstance(v, list) else [v]) for k, v in fields.items()}
        self.path = path
        self.data = mock.MagicMock(covers=[])
        self.data.info.length = 0

    @property
    def folder(self):
        return os.path.dirname(self.path)

    @property
    def filename(self):
        return os.path.basename(self.path)

    def get(self, name):
        return self.fields.get(name.upper(), [])


FULL = dict(albumartist="Madball", artist="Madball", year="2024", album="Hellfest", track="01/20",
            discnumber="01/01", title="Heavenhell")


def names(tokens=None, **changes):
    fields = {**FULL, **changes}
    return namescheme.segments(Fake(**{k: v for k, v in fields.items() if v}), tokens or namescheme.DEFAULT)


class SchemeTests(unittest.TestCase):
    def test_default_scheme_gives_the_usual_names(self):
        self.assertEqual(names(), ["Madball - (2024) - Hellfest", "01-0101 - Madball - Heavenhell"])

    def test_empty_year_takes_its_brackets_and_one_separator_along(self):
        self.assertEqual(names(year="")[0], "Madball - Hellfest")

    def test_empty_disc_leaves_a_clean_separator(self):
        self.assertEqual(names(discnumber="")[1], "01 - Madball - Heavenhell")

    def test_separators_at_the_edges_disappear(self):
        self.assertEqual(names(album="")[0], "Madball - (2024)")

    def test_album_artist_falls_back_to_the_artist(self):
        self.assertEqual(names(albumartist="")[0], "Madball - (2024) - Hellfest")

    def test_forbidden_characters_are_replaced(self):
        self.assertEqual(names(["title"], title='Who: What?'), ["Who- What"])
        self.assertEqual(names(["artist"], artist="AC/DC"), ["ACDC"])

    def test_several_values_are_listed(self):
        self.assertEqual(names(["artist"], artist=["A", "B"]), ["A, B"])

    def test_track_is_two_digits_without_the_total(self):
        self.assertEqual(names(["track"], track="3/10"), ["03"])

    def test_year_is_only_the_year(self):
        self.assertEqual(names(["year"], year="2014-07-24"), ["2014"])

    def test_only_separators_give_nothing(self):
        self.assertEqual(namescheme.segments(Fake(), [" - ", "(", ")"]), [])

    def test_a_folder_without_values_is_skipped(self):
        self.assertEqual(names(["album", namescheme.FOLDER, "title"], album=""), ["Heavenhell"])


class TargetTests(unittest.TestCase):
    def setUp(self):
        self.root = os.path.abspath(os.path.join(os.sep, "rip"))
        self.t = Fake(os.path.join(self.root, "Old Name", "CD1", "track03.flac"), album="Close to the Edge",
                      track="3", title="Siberian Khatru")

    def test_with_a_folder_the_album_goes_next_to_the_old_one(self):
        got = namescheme.target_path(self.t, ["album", namescheme.FOLDER, "track", " ", "title"])
        self.assertEqual(got, os.path.join(self.root, "Close to the Edge", "03 Siberian Khatru.flac"))

    def test_without_a_folder_the_file_stays(self):
        self.assertEqual(namescheme.target_path(self.t, ["title"]),
                         os.path.join(self.root, "Old Name", "CD1", "Siberian Khatru.flac"))

    def test_nothing_to_build_keeps_the_path(self):
        self.assertEqual(namescheme.target_path(self.t, []), self.t.path)
        self.assertEqual(convert.place(self.t, []), self.t.path)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        patcher = mock.patch.object(config, "config_dir", lambda: d.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_defaults_for_a_new_install(self):
        self.assertEqual(namescheme.load(), namescheme.DEFAULT)
        self.assertFalse(namescheme.cleanup_enabled())

    def test_scheme_and_cleanup_are_remembered(self):
        namescheme.save(["title", " ", "artist"])
        namescheme.set_cleanup(True)
        self.assertEqual(namescheme.load(), ["title", " ", "artist"])
        self.assertTrue(namescheme.cleanup_enabled())

    def test_a_broken_scheme_falls_back_to_the_default(self):
        config.settings().setValue("rename/scheme", '["nonsense"]')
        self.assertEqual(namescheme.load(), namescheme.DEFAULT)

    def test_number_format_is_remembered(self):
        self.assertEqual(numbering.NumberFormat.load(), numbering.NumberFormat())
        numbering.NumberFormat(track_total=False, disc_on=False).save()
        got = numbering.NumberFormat.load()
        self.assertFalse(got.track_total)
        self.assertFalse(got.disc_on)
        self.assertTrue(got.track_zeros)


def plan(tracks, **fmt):
    out = numbering.plan(tracks, numbering.NumberFormat(**fmt))
    return [out[id(t)] for t in tracks]


class NumberingTests(unittest.TestCase):
    def test_default_format(self):
        tracks = [Fake() for _ in range(3)]
        self.assertEqual(plan(tracks)[1], {"TRACK": "02/03", "DISCNUMBER": "01/01"})

    def test_no_total_and_no_zeros(self):
        tracks = [Fake() for _ in range(2)]
        self.assertEqual(plan(tracks, track_total=False, track_zeros=False, disc_total=False, disc_zeros=False)[1],
                         {"TRACK": "2", "DISCNUMBER": "1"})

    def test_disc_number_can_be_left_out(self):
        self.assertEqual(plan([Fake()], disc_on=False), [{"TRACK": "01/01"}])

    def test_two_discs_restart_the_tracks(self):
        tracks = [Fake(discnumber="1/2"), Fake(discnumber="1/2"), Fake(discnumber="2/2")]
        self.assertEqual(plan(tracks), [{"TRACK": "01/02", "DISCNUMBER": "01/02"},
                                        {"TRACK": "02/02", "DISCNUMBER": "01/02"},
                                        {"TRACK": "01/01", "DISCNUMBER": "02/02"}])

    def test_two_discs_always_get_their_numbers(self):
        tracks = [Fake(discnumber="1"), Fake(discnumber="2")]
        self.assertEqual([p["DISCNUMBER"] for p in plan(tracks, disc_on=False)], ["01/02", "02/02"])

    def test_wide_numbers_keep_their_width(self):
        tracks = [Fake() for _ in range(100)]
        self.assertEqual(plan(tracks)[0]["TRACK"], "001/100")

    def test_example_shows_the_format(self):
        self.assertEqual(numbering.example(numbering.NumberFormat()), ("03/12", "01/02"))
        self.assertEqual(numbering.example(numbering.NumberFormat(track_total=False, track_zeros=False, disc_on=False)),
                         ("3", ""))


class DialogTests(unittest.TestCase):
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

    def test_app_icon_comes_in_all_sizes(self):
        from PySide6.QtCore import QSize
        from psytags.ui.icons import icon
        sizes = icon("app").availableSizes()
        for side in (16, 32, 64, 256):
            self.assertIn(QSize(side, side), sizes)

    def test_logo_takes_the_color_of_the_theme(self):
        from PySide6.QtGui import QColor
        from psytags.ui import icons, theme
        self.addCleanup(theme.use, "mocha")
        for name in ("mocha", "latte"):
            theme.use(name)
            image = icons.logo_pixmap(32).toImage()
            self.assertEqual(image.height(), 32)
            solid = {image.pixelColor(x, y).name() for x in range(image.width()) for y in range(image.height())
                     if image.pixelColor(x, y).alpha() == 255}
            self.assertEqual(solid, {QColor(theme.ACCENT).name()})

    def test_moods_step_only_analyzes_the_selection(self):
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        chosen = [object()]
        win.view.selected_tracks.return_value = chosen
        win.model.rows = chosen + [object(), object()]
        MainWindow.analyze_selected_moods(win)
        win.analyze_moods.assert_called_once_with(chosen)

    def test_moods_step_can_also_take_the_whole_list(self):
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win.model.rows = [object(), object()]
        MainWindow.analyze_all_moods(win)
        win.analyze_moods.assert_called_once_with(win.model.rows)

    def test_moods_step_offers_selection_and_all(self):
        from PySide6.QtWidgets import QPushButton
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        choices = [b.text() for b in w.topbar.findChildren(QPushButton) if b.objectName() == "StepChoice"]
        self.assertEqual(choices, ["Auswahl", "Alle", "Auswahl", "Alle"])
        w.model.rows = [object()]
        w._update_actions()
        self.assertFalse(w.act_moods.isEnabled())
        self.assertTrue(w.act_moods_all.isEnabled())

    def test_rename_step_offers_selection_and_all(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.model.rows = [object()]
        w._update_actions()
        self.assertFalse(w.act_ttf.isEnabled())
        self.assertTrue(w.act_ttf_all.isEnabled())

    def test_renaming_all_takes_the_whole_list(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        rows = [Fake(path="/music/A/1.mp3"), Fake(path="/music/B/2.mp3")]
        w.model.rows = rows
        dialog = mock.MagicMock()
        dialog.return_value.exec.return_value = 1
        dialog.return_value.tokens.return_value = namescheme.DEFAULT
        dialog.return_value.cleanup.return_value = False
        with mock.patch("psytags.ui.dialogs.rename.RenameDialog", dialog), \
                mock.patch.object(namescheme, "target_path", lambda t, _tokens: t.path + ".neu"), \
                mock.patch.object(w, "_rename") as rename:
            w.rename_all_files()
        self.assertEqual(dialog.call_args.args[0], rows)
        self.assertEqual([pair[0] for pair in rename.call_args.args[0]], rows)

    def test_moods_step_needs_a_selection(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        w.model.rows = [object()]
        w._update_actions()
        self.assertFalse(w.act_moods.isEnabled())
        self.assertTrue(w.act_auto_all.isEnabled())

    def _window(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        return w

    def test_the_summary_button_stands_out_once_there_is_a_result(self):
        from PySide6.QtWidgets import QPushButton
        from psytags.ui import theme
        self.addCleanup(theme.use, "mocha")
        for name in theme.THEMES:
            theme.use(name)
            w = self._window()
            button = next(b for b in w.topbar.findChildren(QPushButton) if b.text() == "Übersicht")
            button.setStyleSheet(theme.style_sheet())
            self.assertFalse(button.isEnabled())
            image = button.grab().toImage()
            self.assertEqual(image.pixelColor(image.width() // 2, 3).name(), theme.BUTTON, name)
            w._last_batch = [object()]
            w._update_actions()
            self.assertTrue(button.isEnabled())
            image = button.grab().toImage()
            self.assertEqual(image.pixelColor(image.width() // 2, 3).name(), theme.ACCENT, name)

    def test_during_a_run_the_list_can_only_be_scrolled(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QLabel
        from psytags.ui.mainwindow import _ScrollOnlyGuard
        w = self._window()
        guard = _ScrollOnlyGuard(w)
        T = QEvent.Type
        port, bar = w.view.viewport(), w.view.verticalScrollBar()
        self.assertFalse(guard.eventFilter(port, QEvent(T.Wheel)))
        self.assertFalse(guard.eventFilter(bar, QEvent(T.Wheel)))
        self.assertFalse(guard.eventFilter(bar, QEvent(T.MouseButtonPress)))
        self.assertTrue(guard.eventFilter(port, QEvent(T.MouseButtonPress)))
        self.assertTrue(guard.eventFilter(port, QEvent(T.KeyPress)))
        self.assertTrue(guard.eventFilter(port, QEvent(T.Drop)))
        self.assertTrue(guard.eventFilter(w.panel, QEvent(T.Wheel)))
        self.assertTrue(guard.eventFilter(w.view.horizontalHeader().viewport(), QEvent(T.MouseButtonPress)))
        self.assertTrue(guard.eventFilter(w.act_save, QEvent(T.Shortcut)))
        self.assertFalse(guard.eventFilter(port, QEvent(T.Paint)))
        other = QLabel()
        self.assertFalse(guard.eventFilter(other, QEvent(T.MouseButtonPress)))

    def test_during_a_run_the_window_cannot_be_closed(self):
        from PySide6.QtGui import QCloseEvent
        from psytags.ui.mainwindow import _ScrollOnlyGuard
        w = self._window()
        close = QCloseEvent()
        self.assertTrue(_ScrollOnlyGuard(w).eventFilter(w, close))
        self.assertFalse(close.isAccepted())

    def test_progress_window_leaves_the_main_window_scrollable(self):
        from PySide6.QtCore import Qt
        from psytags.ui.mainwindow import _StayingProgress
        w = self._window()
        d = _StayingProgress("x", 2, w)
        self.assertEqual(d.windowModality(), Qt.WindowModality.NonModal)
        self.assertIsNotNone(d._guard)
        d.finish()
        self.assertIsNone(d._guard)

    def test_a_row_without_heading_loses_the_extra_height(self):
        from psytags.ui.filelist import BAND_HEIGHT, ROW_HEIGHT
        w = self._window()
        tracks = [Fake(**FULL) for _ in range(3)]
        w.model.set_tracks(tracks)
        w.view.verticalHeader().resizeSection(1, ROW_HEIGHT + BAND_HEIGHT)    # left over from an earlier order
        w.view._forget_bands()
        w.view._refresh_bands()
        self.assertEqual(w.view.rowHeight(0), ROW_HEIGHT + BAND_HEIGHT)
        self.assertEqual(w.view.rowHeight(1), ROW_HEIGHT)
        self.assertEqual(w.view.rowHeight(2), ROW_HEIGHT)

    def test_selecting_can_leave_the_scroll_position_alone(self):
        w = self._window()
        tracks = [Fake(**FULL), Fake(**FULL)]
        w.model.set_tracks(tracks)
        w.view.scrollTo = mock.MagicMock()
        w.view.select_tracks([tracks[1]], scroll=False)
        w.view.scrollTo.assert_not_called()
        w.view.select_tracks([tracks[1]])
        w.view.scrollTo.assert_called_once()

    def test_sorting_an_album_keeps_the_scroll_position(self):
        w = self._window()
        tracks = [Fake(**FULL), Fake(**FULL)]
        w.model.set_tracks(tracks)
        w.view.verticalScrollBar().setRange(0, 500)
        w.view.verticalScrollBar().setValue(120)
        w.model.keep_scroll = True
        w.view._remember_scroll()
        self.assertEqual(w.view._restore_scroll, 120)
        self.assertFalse(w.model.keep_scroll)
        w.view._remember_scroll()
        self.assertIsNone(w.view._restore_scroll)

    def test_progress_window_can_show_a_hint(self):
        from psytags.ui.mainwindow import _StayingProgress
        d = _StayingProgress("x", 2, None)
        self.assertTrue(d.hint_label.isHidden())
        d.set_hint("Das kann dauern.")
        self.assertFalse(d.hint_label.isHidden())
        self.assertEqual(d.hint_label.text(), "Das kann dauern.")
        d.finish()

    def test_progress_window_shows_the_count(self):
        from psytags.ui.mainwindow import _StayingProgress
        d = _StayingProgress("Moods", 4, None)
        d.setValue(1)
        self.assertEqual(d.bar.value(), 1)
        self.assertEqual(d.count_label.text(), "1 von 4 · 25 %")
        self.assertGreaterEqual(d.width(), 560)
        d.finish()

    def test_starts_with_an_empty_list(self):
        from psytags.ui.mainwindow import MainWindow
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        config.settings().setValue("dirs/last", folder.name)
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        QApplication.processEvents()
        self.assertIsNone(w._loader_thread)
        self.assertEqual(w.model.rows, [])

    def test_lastfm_key_is_entered_in_the_options(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(config.Options.load(), None, "genres")
        self.assertEqual(d.current_section(), "genres")
        d.lastfm_key.setText(" abc ")
        d.accept()
        s = config.settings()
        self.assertEqual(s.value("lastfm/api_key"), "abc")
        self.assertIn(s.value("lastfm/enabled"), (True, "true"))

    def test_without_a_key_lastfm_stays_off(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(config.Options.load())
        d.accept()
        self.assertNotIn(config.settings().value("lastfm/enabled"), (True, "true"))

    def test_tag_panel_always_shows_genres_and_moods(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        self.assertFalse(w._lastfm_enabled())
        self.assertIn("MOOD", w.panel.combos)
        self.assertIn("GENRE", w.panel.combos)
        self.assertEqual([f.value for f in w.panel.fields[-2:]], ["GENRE", "MOOD"])

    def _rename(self):
        from psytags.ui.dialogs.rename import RenameDialog
        return RenameDialog([Fake(**FULL)])

    def test_options_show_and_save_the_number_format(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(config.Options.load())
        d.number_boxes["track_total"].setChecked(False)
        self.assertEqual(d.number_sample.text(), "Beispiel: Track 03, Disc 01/02")
        d.accept()
        self.assertFalse(numbering.NumberFormat.load().track_total)

    def test_rename_dialog_starts_with_the_saved_scheme(self):
        d = self._rename()
        self.assertEqual(d.tokens(), namescheme.DEFAULT)
        d.scheme.update_preview()
        self.assertIn("Madball - (2024) - Hellfest", d.scheme.preview.text())

    def test_clicking_a_chip_removes_it_and_a_button_adds_it(self):
        d = self._rename()
        d.scheme.remove(d.scheme.chips.item(0))
        self.assertEqual(d.tokens(), namescheme.DEFAULT[1:])
        d.scheme.add("title")
        self.assertEqual(d.tokens()[-1], "title")

    def test_without_a_name_ok_is_off(self):
        d = self._rename()
        d.scheme.fill([" - "])
        d.scheme.update_preview()
        self.assertFalse(d.ok.isEnabled())

    def test_accept_remembers_scheme_and_cleanup(self):
        d = self._rename()
        d.scheme.fill(["title"])
        d.scheme.cleanup_box.setChecked(True)
        d.accept()
        self.assertEqual(namescheme.load(), ["title"])
        self.assertTrue(namescheme.cleanup_enabled())


if __name__ == "__main__":
    unittest.main()
