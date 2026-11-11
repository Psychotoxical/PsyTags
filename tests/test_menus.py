"""The right-click menu of the file list: manual search and cover sources."""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMenu

from psytags.i18n import set_language
from psytags.ui.mainwindow import MainWindow


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        set_language("de")

    def _menu(self):
        menu = QMenu()
        self.addCleanup(menu.deleteLater)
        return menu

    @staticmethod
    def _window(selected=True):
        win = mock.MagicMock()
        win.view.selected_tracks.return_value = [NS()] if selected else []
        win._tag_fallback.return_value = None
        win._cover_fetch_entries.return_value = [("fetch_mb", "Cover von Cover Art Archive laden"),
                                                 ("provider:Example", "Cover von Example laden")]
        return win


class ManualSearchTests(Base):
    def test_the_entries_say_that_a_window_opens(self):
        menu = self._menu()
        MainWindow._add_source_entries(self._window(), menu)
        self.assertEqual(menu.actions()[0].text(), "MusicBrainz …")


class CoverEntryTests(Base):
    def _entries(self, win):
        menu = self._menu()
        MainWindow._add_cover_entries(win, menu)
        return {a.text(): a for a in menu.actions() if a.text()}

    def test_every_cover_source_is_offered(self):
        win = self._window()
        entries = self._entries(win)
        self.assertEqual(list(entries), ["Alle Quellen der Reihe nach", "Cover von Cover Art Archive laden",
                                         "Cover von Example laden"])
        entries["Cover von Example laden"].trigger()
        win._cover_command.assert_called_once_with("provider:Example")

    def test_all_sources_runs_the_cover_step(self):
        win = self._window()
        self._entries(win)["Alle Quellen der Reihe nach"].trigger()
        win.fetch_covers.assert_called_once()

    def test_without_a_selection_the_whole_chain_is_off(self):
        self.assertFalse(self._entries(self._window(selected=False))["Alle Quellen der Reihe nach"].isEnabled())


class ContextMenuTests(Base):
    def setUp(self):
        import tempfile
        from psytags import config
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_the_file_list_menu_has_both_submenus(self):
        win = MainWindow()
        win._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(win.deleteLater)
        shown = []

        class Recording(QMenu):
            def exec(self, *args):
                shown.append(self)

        with mock.patch("psytags.ui.mainwindow.QMenu", Recording):
            win._context_menu(None)
        titles = [a.text() for a in shown[0].actions()]
        self.assertIn("&Manuell suchen", titles)
        self.assertIn("Cover &holen", titles)
        self.assertNotIn("Tag-&Quellen", titles)


if __name__ == "__main__":
    unittest.main()
