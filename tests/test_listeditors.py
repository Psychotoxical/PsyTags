import copy
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.i18n import set_language


class EnglishNamesTests(unittest.TestCase):
    """The default names are stored in German and shown in the chosen language."""

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
        set_language("en")
        self.addCleanup(set_language, "de")

    def _columns(self):
        from psytags.ui.dialogs.options import ColumnsDialog
        d = ColumnsDialog(copy.deepcopy(config.DEFAULT_COLUMNS))
        self.addCleanup(d.deleteLater)
        return d

    def test_the_column_list_is_english(self):
        d = self._columns()
        self.assertEqual(d.list.item(0).text(), "Filename")
        d.list.setCurrentRow(0)
        self.assertEqual(d.name.text(), "Filename")

    def test_the_panel_list_is_english(self):
        from psytags.ui.dialogs.options import PanelDialog
        d = PanelDialog(copy.deepcopy(config.DEFAULT_PANEL))
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.list.item(0).text(), "Title")

    def test_editing_another_field_keeps_the_stored_name(self):
        d = self._columns()
        d.list.setCurrentRow(0)
        d.value.setText("%_filename%")
        d.value.textEdited.emit("%_filename%")
        self.assertEqual(d.columns[0].name, "Dateiname")
        self.assertEqual(d.columns[0].value, "%_filename%")

    def test_an_own_name_is_kept(self):
        d = self._columns()
        d.list.setCurrentRow(0)
        d.name.setText("File")
        d.name.textEdited.emit("File")
        self.assertEqual(d.columns[0].name, "File")
        self.assertEqual(d.list.item(0).text(), "File")


if __name__ == "__main__":
    unittest.main()
