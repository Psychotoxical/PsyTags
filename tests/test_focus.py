"""PsyTags must not pull itself to the front while the user works in another program."""
import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QWidget

from psytags.ui import mainwindow as mw


class FocusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _state(self, state):
        return mock.patch.object(QApplication, "applicationState", return_value=state)

    def test_a_window_opened_in_the_background_does_not_take_the_focus(self):
        w = QWidget()
        self.addCleanup(w.deleteLater)
        with self._state(Qt.ApplicationState.ApplicationInactive):
            mw._quiet_if_inactive(w)
        self.assertTrue(w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))

    def test_in_the_foreground_it_opens_as_usual(self):
        w = QWidget()
        self.addCleanup(w.deleteLater)
        with self._state(Qt.ApplicationState.ApplicationActive):
            mw._quiet_if_inactive(w)
        self.assertFalse(w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating))

    def test_a_progress_window_gives_back_only_the_focus_it_had(self):
        parent = mock.MagicMock()
        dlg = mock.MagicMock(_guard=None)
        dlg.parentWidget.return_value = parent
        dlg.isActiveWindow.return_value = False
        mw._StayingProgress.finish(dlg)
        parent.activateWindow.assert_not_called()
        dlg.isActiveWindow.return_value = True
        mw._StayingProgress.finish(dlg)
        parent.activateWindow.assert_called_once()


if __name__ == "__main__":
    unittest.main()
