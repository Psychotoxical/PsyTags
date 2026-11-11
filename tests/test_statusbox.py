"""Status messages as a box in the tag panel, switchable in "Customize Tag Panel"."""
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QProgressBar

from psytags import config
from psytags.i18n import set_language
from psytags.ui import statusbox, theme
from psytags.ui.statusbox import StatusBox


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        set_language("de")

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)


class BoxTests(Base):
    def _box(self):
        bar = QProgressBar()
        box = StatusBox(bar)
        self.addCleanup(box.deleteLater)
        self.addCleanup(bar.deleteLater)
        return box, bar

    def test_the_newest_message_is_on_top_and_the_old_ones_below(self):
        box, _bar = self._box()
        for text in ("eins", "zwei", "drei", "vier", "fünf"):
            box.show_message(text)
        self.assertEqual(box.now.text(), "fünf")
        self.assertEqual([text for _when, text in box.history], ["vier", "drei", "zwei"])

    def test_the_rows_are_reused_not_rebuilt(self):
        # deleteLater waits for the event loop, which a long job keeps busy: no widget may pile up
        box, _bar = self._box()
        before = len(box.findChildren(QLabel))
        for i in range(20):
            box.show_message(f"Meldung {i}")
        self.assertEqual(len(box.findChildren(QLabel)), before)
        shown = [line.text() for _stamp, line in box.rows if not line.isHidden()]
        self.assertEqual(shown, ["Meldung 18", "Meldung 17", "Meldung 16"])

    def test_ready_is_not_kept(self):
        box, _bar = self._box()
        box.show_message("")
        box.show_message("eins")
        box.show_message("")
        self.assertEqual(box.now.text(), "Bereit")
        self.assertEqual([text for _when, text in box.history], ["eins"])

    def test_it_follows_the_progress_of_the_window(self):
        box, bar = self._box()
        bar.setRange(0, 24)
        bar.setValue(7)
        bar.show()
        box.follow()
        self.assertEqual((box.bar.maximum(), box.bar.value()), (24, 7))
        self.assertFalse(box.bar.isHidden())
        bar.hide()
        box.follow()
        self.assertTrue(box.bar.isHidden())


class WindowTests(Base):
    def _window(self):
        from psytags.ui.mainwindow import MainWindow
        w = MainWindow()
        w._autosave.stop()       # the test's config folder goes away before 20 s
        self.addCleanup(w.deleteLater)
        return w

    def test_on_by_default_messages_go_to_the_box(self):
        w = self._window()
        self.assertTrue(statusbox.enabled(config.settings()))
        w.message("Suche bei MusicBrainz")
        self.assertEqual(w.status_box.now.text(), "Suche bei MusicBrainz")
        self.assertFalse(w._status_holder.isHidden())
        self.assertTrue(w.status_msg.isHidden())

    def test_a_change_of_language_or_theme_keeps_the_messages(self):
        w = self._window()
        w.message("eins")
        w.message("zwei")
        new = w.apply_appearance("en", "latte")
        self.addCleanup(new.deleteLater)
        self.addCleanup(set_language, "de")         # the next tests read German texts
        self.addCleanup(theme.apply_theme, self.app, "mocha")
        self.assertIsNot(new, w)
        self.assertEqual(new.status_box.now.text(), "zwei")
        self.assertEqual([text for _when, text in new.status_box.history], ["eins"])

    def test_an_older_timeout_does_not_clear_a_newer_message(self):
        w = self._window()
        w.message("Moods: 9 Dateien", 10000)
        w.message("Statistik")                     # meant to stay
        self.assertFalse(w._message_timer.isActive())
        w.message("kurz", 5000)
        self.assertTrue(w._message_timer.isActive())
        w._message_timer.timeout.emit()
        self.assertEqual(w.status_box.now.text(), "Bereit")

    def test_the_description_of_a_button_goes_by_itself(self):
        from PySide6.QtCore import QCoreApplication
        from PySide6.QtGui import QStatusTipEvent
        w = self._window()
        QCoreApplication.sendEvent(w, QStatusTipEvent("Schreibt Track- und Discnummern."))
        self.assertEqual(w.statusBar().currentMessage(), "Schreibt Track- und Discnummern.")
        with mock.patch.object(w.statusBar(), "showMessage") as show:
            QCoreApplication.sendEvent(w, QStatusTipEvent("Neu"))
        show.assert_called_once_with("Neu", w.STATUS_TIP_MS)          # with a timeout, not for good
        QCoreApplication.sendEvent(w, QStatusTipEvent(""))
        self.assertEqual(w.statusBar().currentMessage(), "")

    def test_switched_off_the_status_bar_shows_them_as_before(self):
        config.settings().setValue(statusbox.SETTING, False)
        w = self._window()
        w.message("Suche bei MusicBrainz")
        self.assertEqual(w.status_msg.text(), "Suche bei MusicBrainz")
        self.assertTrue(w._status_holder.isHidden())
        self.assertFalse(w.status_msg.isHidden())

    def test_the_panel_dialog_switches_it(self):
        from psytags.ui.dialogs.options import PanelDialog
        w = self._window()
        d = PanelDialog(config.load_panel())
        self.addCleanup(d.deleteLater)
        self.assertTrue(d.status_box.isChecked())
        d.status_box.setChecked(False)
        with mock.patch("psytags.ui.dialogs.options.PanelDialog", return_value=d), \
                mock.patch.object(d, "exec", return_value=1):
            w.customize_panel()
        self.assertFalse(statusbox.enabled(config.settings()))
        self.assertTrue(w._status_holder.isHidden())


if __name__ == "__main__":
    unittest.main()
