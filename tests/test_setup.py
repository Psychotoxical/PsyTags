import io
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication, QLabel

from psytags import config, moodanalysis as ma, namescheme, numbering
from psytags.config import Options
from psytags.ui.dialogs import setup
from psytags.ui.dialogs.setup import SetupDialog
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

    def _dialog(self, page=None):
        d = SetupDialog(Options())
        self.addCleanup(d.deleteLater)
        if page:
            d.go_to(page)
        return d


class FirstStartTests(Base):
    def test_a_new_installation_is_a_first_start(self):
        self.assertTrue(setup.is_first_start())

    def test_an_installation_in_use_is_not(self):
        config.settings().setValue("lastfm/api_key", "x")
        self.assertFalse(setup.is_first_start())

    def test_closing_the_assistant_ends_the_first_start(self):
        d = self._dialog()
        d.reject()
        self.assertFalse(setup.is_first_start())

    def test_the_window_opens_it_and_takes_the_options(self):
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        chosen = Options(language="en")
        with mock.patch.object(setup, "SetupDialog") as dialog:
            dialog.return_value.opts = chosen
            MainWindow.show_setup(win)
        dialog.return_value.exec.assert_called_once()
        self.assertIs(win.opts, chosen)
        self.assertEqual(Options.load().language, "en")


class NavigationTests(Base):
    def test_the_pages_follow_the_plan(self):
        self.assertEqual(self._dialog().page_keys(),
                         ["welcome", "appearance", "lastfm", "discogs", "date", "moods", "rename", "numbers"])

    def test_it_starts_with_the_warning_about_copies(self):
        d = self._dialog()
        self.assertEqual(d.current_page(), "welcome")
        text = " ".join(label.text() for label in d.findChildren(QLabel))
        self.assertIn("Kopien", text)

    def test_next_and_back(self):
        d = self._dialog()
        d.next_page()
        self.assertEqual(d.current_page(), "appearance")
        d.previous_page()
        self.assertEqual(d.current_page(), "welcome")

    def test_the_last_page_finishes(self):
        d = self._dialog("numbers")
        finished = []
        d.finished.connect(finished.append)
        d.next_page()
        self.assertEqual(len(finished), 1)

    def test_the_welcome_page_cannot_be_skipped_but_the_others_can(self):
        d = self._dialog()
        self.assertTrue(d.skip_button.isHidden())
        d.next_page()
        self.assertFalse(d.skip_button.isHidden())


class PageTests(Base):
    def test_language_and_theme_are_taken(self):
        d = self._dialog("appearance")
        d.lang.setCurrentIndex(d.lang.findData("en"))
        d.theme_choice.setCurrentIndex(d.theme_choice.findData("latte"))
        d.next_page()
        self.assertEqual((d.opts.language, d.opts.theme), ("en", "latte"))

    def test_the_full_date_can_be_chosen(self):
        d = self._dialog("date")
        self.assertEqual(d.date_choice.currentData(), "year")
        d.date_choice.setCurrentIndex(d.date_choice.findData("date"))
        d.next_page()
        self.assertFalse(d.opts.year_only)

    def test_skipping_changes_nothing(self):
        d = self._dialog("appearance")
        d.lang.setCurrentIndex(d.lang.findData("en"))
        d.skip()
        self.assertEqual(d.opts.language, "de")

    def test_a_lastfm_key_switches_the_genres_on(self):
        d = self._dialog("lastfm")
        d.lastfm_key.setText(" abc ")
        d.next_page()
        s = config.settings()
        self.assertEqual(s.value("lastfm/api_key"), "abc")
        self.assertIn(s.value("lastfm/enabled"), (True, "true"))

    def test_without_a_key_the_genres_stay_off(self):
        d = self._dialog("lastfm")
        d.next_page()
        self.assertNotIn(config.settings().value("lastfm/enabled", False), (True, "true"))

    def _check_key(self, d):
        d.check_lastfm_key()
        QThreadPool.globalInstance().waitForDone()
        self.app.processEvents()

    def test_the_key_check_reports_success(self):
        d = self._dialog("lastfm")
        d.lastfm_key.setText("abc")
        with mock.patch.object(lastfm, "verify_key") as verify:
            self._check_key(d)
        verify.assert_called_once_with("abc")
        self.assertEqual(d.lastfm_result.text(), "Der Schlüssel funktioniert.")

    def test_the_key_check_reports_failure(self):
        d = self._dialog("lastfm")
        d.lastfm_key.setText("abc")
        with mock.patch.object(lastfm, "verify_key", side_effect=lastfm.LastfmError("nein")):
            self._check_key(d)
        self.assertIn("nicht angenommen", d.lastfm_result.text())

    def test_a_discogs_token_is_saved(self):
        d = self._dialog("discogs")
        d.discogs_token.setText(" abc ")
        d.next_page()
        self.assertEqual(config.settings().value("discogs/token"), "abc")

    def test_skipping_leaves_the_discogs_token_alone(self):
        d = self._dialog("discogs")
        d.discogs_token.setText("abc")
        d.skip()
        self.assertFalse(config.settings().value("discogs/token", ""))

    def test_the_token_check_reports_success(self):
        d = self._dialog("discogs")
        d.discogs_token.setText("abc")
        with mock.patch.object(discogs, "verify_token") as verify:
            d.check_discogs_token()
            QThreadPool.globalInstance().waitForDone()
            self.app.processEvents()
        verify.assert_called_once_with("abc")
        self.assertEqual(d.discogs_result.text(), "Der Token funktioniert.")

    def test_the_token_check_reports_failure(self):
        d = self._dialog("discogs")
        d.discogs_token.setText("abc")
        with mock.patch.object(discogs, "verify_token", side_effect=http.FetchError("nein")):
            d.check_discogs_token()
            QThreadPool.globalInstance().waitForDone()
            self.app.processEvents()
        self.assertIn("nicht angenommen", d.discogs_result.text())

    def test_the_rename_scheme_is_saved_and_old_folders_stay_by_default(self):
        d = self._dialog("rename")
        self.assertFalse(d.scheme.cleanup_box.isChecked())
        d.scheme.fill(["title"])
        d.next_page()
        self.assertEqual(namescheme.load(), ["title"])
        self.assertFalse(namescheme.cleanup_enabled())

    def test_the_number_format_is_saved(self):
        d = self._dialog("numbers")
        d.numbers.boxes["track_total"].setChecked(False)
        d.next_page()
        self.assertFalse(numbering.NumberFormat.load().track_total)


class MoodPageTests(Base):
    def test_it_offers_the_download_while_models_are_missing(self):
        with mock.patch.object(ma, "models_present", return_value=False):
            d = self._dialog("moods")
        self.assertFalse(d.model_button.isHidden())

    def test_no_download_when_the_models_are_there(self):
        with mock.patch.object(ma, "models_present", return_value=True):
            d = self._dialog("moods")
        self.assertTrue(d.model_button.isHidden())

    def test_it_says_when_ffmpeg_is_missing(self):
        with mock.patch.object(ma, "ffmpeg_available", return_value=False):
            d = self._dialog("moods")
        self.assertIn("ffmpeg", d.ffmpeg_status.text())
        self.assertIn("nicht", d.ffmpeg_status.text())

    def test_the_download_shows_progress_and_ends_ready(self):
        def ensure(folder, on_progress=None):
            on_progress(50, 100)
        with mock.patch.object(ma, "models_present", return_value=False):
            d = self._dialog("moods")
        with mock.patch.object(ma, "ensure_models", ensure), mock.patch.object(ma, "models_present", return_value=True):
            d.load_models()
            d.download_thread.join()
            d.poll_download()
        self.assertEqual(d.model_progress.value(), d.model_progress.maximum())
        self.assertTrue(d.model_button.isHidden())

    def test_a_failed_download_is_explained(self):
        def ensure(folder, on_progress=None):
            raise ma.MoodError("kein Netz")
        with mock.patch.object(ma, "models_present", return_value=False):
            d = self._dialog("moods")
            with mock.patch.object(ma, "ensure_models", ensure):
                d.load_models()
                d.download_thread.join()
                d.poll_download()
        self.assertIn("kein Netz", d.model_status.text())
        self.assertFalse(d.model_button.isHidden())
        self.assertTrue(d.model_button.isEnabled())


class ModelDownloadTests(unittest.TestCase):
    def test_the_download_reports_its_bytes(self):
        seen = []

        class Answer(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False
        with mock.patch.object(ma.urllib.request, "urlopen", return_value=Answer(b"x" * 200000)):
            self.assertEqual(len(ma._download("https://example.invalid/m", seen.append)), 200000)
        self.assertEqual(seen[-1], 200000)
        self.assertGreater(len(seen), 1)

    def test_models_present_needs_the_right_files(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertFalse(ma.models_present(folder))


class LastfmCheckTests(unittest.TestCase):
    def test_a_rejected_key_raises(self):
        with mock.patch.object(lastfm, "_top_tags", side_effect=lastfm.LastfmError("x")), \
                self.assertRaises(lastfm.LastfmError):
            lastfm.verify_key("abc")


if __name__ == "__main__":
    unittest.main()
