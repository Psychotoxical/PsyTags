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
        d.set_heading("Cover von Apple Music", "Bitte das passende Album wählen")
        self.assertEqual(d.title_label.text(), "Cover von Apple Music")
        self.assertEqual(d.windowTitle(), "Cover von Apple Music")
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
