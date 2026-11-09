"""Slim dock title bars like Mp3tag's: grip lines plus a small close button."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QPalette, QPainter, QPen
from PySide6.QtWidgets import QBoxLayout, QDockWidget, QToolButton, QWidget


class _Close(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAutoRaise(True)
        self.setFixedSize(12, 12)
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        if self.underMouse():
            p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Highlight))
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.WindowText), 1))
        r = self.rect().adjusted(3, 3, -4, -4)
        p.drawLine(r.topLeft(), r.bottomRight())
        p.drawLine(r.topRight(), r.bottomLeft())
        p.end()


class DockTitle(QWidget):
    def __init__(self, dock: QDockWidget, vertical: bool = False):
        super().__init__(dock)
        self.dock = dock
        self.vertical = vertical
        lay = QBoxLayout(QBoxLayout.Direction.TopToBottom if vertical else QBoxLayout.Direction.RightToLeft, self)
        lay.setContentsMargins(1, 1, 1, 1)
        lay.setSpacing(0)
        btn = _Close(self)
        btn.clicked.connect(dock.close)
        lay.addWidget(btn, 0, Qt.AlignmentFlag.AlignTop if vertical else Qt.AlignmentFlag.AlignRight)
        lay.addStretch(1)

    def sizeHint(self):
        return QSize(14, 40) if self.vertical else QSize(40, 14)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(QPen(self.palette().color(QPalette.ColorRole.Mid), 1))
        r = self.rect()
        if self.vertical:
            for x in (r.center().x() - 1, r.center().x() + 2):
                p.drawLine(x, 16, x, r.bottom() - 3)
        else:
            for y in (r.center().y() - 1, r.center().y() + 2):
                p.drawLine(3, y, r.right() - 16, y)
        p.end()
