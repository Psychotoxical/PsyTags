import gc
import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QDialog

from psytags import config

_KEEP: list = []        # a finding must not be freed here, that is the crash itself


class DialogLifetimeTests(unittest.TestCase):
    """exec() hands a dialog to Python while Qt still holds it as a child of the window.
    If Python then drops it, the collector destroys a dialog Qt is still responsible for."""

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
        from psytags.ui.mainwindow import MainWindow
        self.window = MainWindow()
        _KEEP.append(self.window)

    def _garbage_after_closing(self, make) -> list:
        dialog = make()
        QTimer.singleShot(0, dialog.reject)
        dialog.exec()
        del dialog
        gc.set_debug(gc.DEBUG_SAVEALL)
        try:
            gc.collect()
        finally:
            gc.set_debug(0)
        found = [o for o in gc.garbage if isinstance(o, QDialog)]
        _KEEP.extend(gc.garbage)
        gc.garbage.clear()
        return found

    def test_the_setup_assistant_is_not_collected_after_it_closes(self):
        from psytags.ui.dialogs.setup import SetupDialog
        self.assertEqual(self._garbage_after_closing(lambda: SetupDialog(self.window.opts, self.window)), [])


if __name__ == "__main__":
    unittest.main()
