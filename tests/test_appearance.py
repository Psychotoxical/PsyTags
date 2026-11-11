import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.config import Options
from psytags.i18n import set_language
from psytags.ui import icons, theme


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
        set_language("de")
        self.addCleanup(set_language, "de")
        self.addCleanup(lambda: theme.CURRENT != "mocha" and (theme.apply_theme(self.app, "mocha"), icons.refresh_colors()))


class SwitchTests(Base):
    def _window(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        MainWindow.current = w
        self.addCleanup(lambda: setattr(MainWindow, "current", None))
        return w

    def _switch(self, w, lang, name):
        new = w.apply_appearance(lang, name)
        self.addCleanup(new.deleteLater)
        return new

    def test_nothing_changed_keeps_the_window(self):
        w = self._window()
        self.addCleanup(w.deleteLater)
        self.assertIs(w.apply_appearance("de", "mocha"), w)

    def test_a_new_language_builds_a_new_window_with_the_same_state(self):
        from psytags.ui.mainwindow import MainWindow
        w = self._window()
        undo = w.undo
        w.search.setText("probe")
        new = self._switch(w, "en", "mocha")
        self.assertIsNot(new, w)
        self.assertIs(MainWindow.current, new)
        self.assertIs(new.undo, undo)
        self.assertEqual(new.search.text(), "probe")
        self.assertEqual(new.built_with, ("en", "mocha"))
        self.assertEqual(new.act_undo.text().replace("&", ""), "Undo")
        self.assertFalse(w.isVisible())

    def test_the_loaded_files_move_over(self):
        w = self._window()
        tracks = [mock.MagicMock(path=f"/x/{i}.mp3") for i in range(2)]
        with mock.patch.object(w.model, "set_tracks"):
            w.model.all = tracks
        with mock.patch("psytags.ui.filelist.FileListModel.set_tracks") as moved:
            self._switch(w, "en", "mocha")
        moved.assert_called_once_with(tracks)

    def test_a_new_theme_recolors_the_icons(self):
        w = self._window()
        before = icons.INK.name()
        self._switch(w, "de", "latte")
        self.assertEqual(theme.CURRENT, "latte")
        self.assertEqual(icons.INK.name(), theme.LATTE["ICON_INK"].lower())
        self.assertNotEqual(icons.INK.name(), before)


class DefaultLanguageTests(Base):
    def test_a_german_system_starts_in_german(self):
        with mock.patch.object(QLocale, "system", return_value=QLocale(QLocale.Language.German)):
            self.assertEqual(Options.load().language, "de")

    def test_any_other_system_starts_in_english(self):
        with mock.patch.object(QLocale, "system", return_value=QLocale(QLocale.Language.French)):
            self.assertEqual(Options.load().language, "en")

    def test_a_stored_choice_wins(self):
        Options(language="de").save()
        with mock.patch.object(QLocale, "system", return_value=QLocale(QLocale.Language.French)):
            self.assertEqual(Options.load().language, "de")
