"""Status messages as a box at the foot of the tag panel: what runs now, and the last few messages."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget

from ..i18n import tr

HISTORY = 3
SETTING = "panel/status_box"


def enabled(settings) -> bool:
    """On unless switched off in "Customize Tag Panel"."""
    return settings.value(SETTING, True) in (True, "true")


class StatusBox(QFrame):
    """Mirrors the status messages and the progress of the main window."""

    def __init__(self, progress: QProgressBar, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBox")
        self._source = progress
        self._current = ""
        self._since = ""
        self.history: list[tuple[str, str]] = []
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 10, 12, 12)
        box.setSpacing(6)
        head = QLabel(tr("Aktivität"))
        head.setObjectName("FieldLabel")
        box.addWidget(head)
        self.now = QLabel(tr("Bereit"))
        self.now.setObjectName("StatusNow")
        self.now.setWordWrap(True)
        box.addWidget(self.now)
        self.detail = QLabel()
        self.detail.setObjectName("StatusOld")
        self.detail.setWordWrap(True)
        self.detail.hide()
        box.addWidget(self.detail)
        self.bar = QProgressBar()
        self.bar.setObjectName("StatusBar")
        self.bar.setTextVisible(False)
        self.bar.hide()
        box.addWidget(self.bar)
        self.rule = QFrame()
        self.rule.setObjectName("SectionRule")
        self.rule.hide()
        box.addWidget(self.rule)
        # fixed rows whose text changes: widgets made and dropped per message would pile up
        # while a long job runs, because deleteLater waits for the event loop
        self.rows: list[tuple[QLabel, QLabel]] = []
        for _ in range(HISTORY):
            row = QHBoxLayout()
            row.setSpacing(8)
            stamp = QLabel()
            stamp.setObjectName("StatusTime")
            row.addWidget(stamp, 0, Qt.AlignmentFlag.AlignTop)
            line = QLabel()
            line.setObjectName("StatusOld")
            line.setWordWrap(True)
            row.addWidget(line, 1)
            box.addLayout(row)
            stamp.hide()
            line.hide()
            self.rows.append((stamp, line))
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.follow)
        self.timer.start()

    def show_message(self, text: str) -> None:
        """A new message; the one before goes into the list below."""
        text = text or ""
        if text == self._current:
            return
        if self._current and self._current != tr("Bereit"):
            self.history.insert(0, (self._since, self._current))
            del self.history[HISTORY:]
            self._fill_history()
        self._current, self._since = text, time.strftime("%H:%M")
        self.now.setText(text or tr("Bereit"))

    def take_over(self, old: "StatusBox") -> None:
        """The messages of the box of a window that is being replaced."""
        self.history = list(old.history)
        self._current, self._since = old._current, old._since
        self.now.setText(old._current or tr("Bereit"))
        self._fill_history()

    def follow(self) -> None:
        """Progress and running requests of the main window."""
        from ..websources import http as wshttp
        src = self._source
        self.bar.setRange(src.minimum(), src.maximum())
        self.bar.setValue(src.value())
        self.bar.setVisible(not src.isHidden())
        running = wshttp.running()
        self.detail.setText(" · ".join(running))
        self.detail.setVisible(bool(running))

    def _fill_history(self) -> None:
        for i, (stamp, line) in enumerate(self.rows):
            when, text = self.history[i] if i < len(self.history) else ("", "")
            stamp.setText(when)
            line.setText(text)
            stamp.setVisible(bool(text))
            line.setVisible(bool(text))
        self.rule.setVisible(bool(self.history))


def holder(box: StatusBox) -> QWidget:
    """The box with the margins of the panel."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(12, 0, 12, 10)
    lay.addWidget(box)
    return w
