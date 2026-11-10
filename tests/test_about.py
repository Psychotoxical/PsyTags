import os
import pathlib
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QPlainTextEdit, QPushButton

from psytags import config

ROOT = pathlib.Path(__file__).resolve().parent.parent


class AboutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _dialog(self):
        from psytags.ui.dialogs.about import AboutDialog
        d = AboutDialog()
        self.addCleanup(d.deleteLater)
        return d

    def test_the_program_license_is_the_full_text(self):
        from psytags.ui.dialogs.about import license_text
        self.assertIn("TERMS AND CONDITIONS", license_text("gpl-3.0.txt"))

    def test_every_entry_says_what_it_is_for_and_has_a_text(self):
        from psytags.ui.dialogs.about import sections
        for _title, _intro, entries in sections():
            for entry in entries:
                self.assertTrue(entry.use, entry.name)
                self.assertTrue(entry.label, entry.name)
                self.assertTrue(entry.text.strip(), entry.name)

    def test_the_window_names_no_other_tag_editor(self):
        d = self._dialog()
        shown = " ".join(w.text() for w in d.findChildren(QLabel))
        self.assertNotIn("mp3tag", shown.lower())

    def test_a_license_button_opens_and_closes_its_text(self):
        d = self._dialog()
        button = next(b for b in d.findChildren(QPushButton) if b.text() == "GPL-3.0-or-later")
        text = next(t for t in d.findChildren(QPlainTextEdit) if "GNU GENERAL PUBLIC LICENSE" in t.toPlainText())
        self.assertTrue(text.isHidden())
        button.click()
        self.assertFalse(text.isHidden())
        button.click()
        self.assertTrue(text.isHidden())

    def test_there_is_a_jump_for_every_section(self):
        from psytags.ui.dialogs.about import sections
        d = self._dialog()
        links = [b.text() for b in d.findChildren(QPushButton) if b.objectName() == "SectionLink"]
        self.assertEqual(links, [s[0] for s in sections()])

    def _ffmpeg_label(self, notice):
        from psytags.ui.dialogs import about
        with tempfile.TemporaryDirectory() as package, mock.patch.object(about.sys, "_MEIPASS", package, create=True):
            if notice is not None:
                os.makedirs(os.path.join(package, "ffmpeg"))
                with open(os.path.join(package, "ffmpeg", "LICENSE"), "w", encoding="utf-8") as fh:
                    fh.write(notice)
            entries = [e for _t, _i, group in about.sections() for e in group]
        return next(e for e in entries if e.name == "FFmpeg").label

    def test_the_slim_ffmpeg_names_its_license(self):
        notice = "                  GNU LESSER GENERAL PUBLIC LICENSE\n                       Version 2.1, February 1999\n"
        self.assertEqual(self._ffmpeg_label(notice), "LGPL-2.1-or-later")

    def test_a_gpl_build_names_its_license(self):
        notice = "                    GNU GENERAL PUBLIC LICENSE\n                       Version 3, 29 June 2007\n"
        self.assertEqual(self._ffmpeg_label(notice), "GPL-3.0-or-later")

    def test_an_unknown_notice_claims_nothing(self):
        self.assertEqual(self._ffmpeg_label("Some other text"), "je nach Build")

    def test_without_a_package_it_depends_on_the_build(self):
        self.assertEqual(self._ffmpeg_label(None), "je nach Build")

    def test_the_repository_carries_the_full_license(self):
        repository = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("TERMS AND CONDITIONS", repository)
        self.assertEqual(repository, (ROOT / "psytags" / "resources" / "licenses" / "gpl-3.0.txt").read_text(encoding="utf-8"))

    def test_the_license_texts_are_part_of_an_installation(self):
        self.assertIn("resources/licenses/*.txt", (ROOT / "pyproject.toml").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
