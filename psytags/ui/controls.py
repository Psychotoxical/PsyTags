"""Small controls of the settings page: a switch and a row of exclusive buttons."""
from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QPushButton

from . import theme

SWITCH_SIZE = QSize(38, 22)


def paint_switch(painter: QPainter, rect: QRect, on: bool, focus: bool = False, enabled: bool = True) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setOpacity(1.0 if enabled else 0.45)
    radius = rect.height() / 2
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(theme.ACCENT if on else theme.HOVER))
    painter.drawRoundedRect(QRectF(rect), radius, radius)
    knob = rect.height() - 6
    x = rect.right() - knob - 2 if on else rect.left() + 3
    painter.setBrush(QColor(theme.ACCENT_TEXT if on else theme.TEXT))
    painter.drawEllipse(QRectF(x, rect.top() + 3, knob, knob))
    if focus:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(theme.TEXT), 1.5))
        painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), radius - 1, radius - 1)
    painter.restore()


class Switch(QCheckBox):
    """On or off, drawn as a switch; everything else works like a check box."""

    def __init__(self, parent=None):
        super().__init__("", parent)
        self.setFixedSize(SWITCH_SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)    # the ring shows for the keyboard only

    def hitButton(self, _pos) -> bool:
        return True

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        paint_switch(painter, self.rect(), self.isChecked(), self.hasFocus(), self.isEnabled())


class Segmented(QFrame):
    """Exclusive buttons in a row, read like a combo box."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmented")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self.buttons: list[QPushButton] = []
        self._data: list = []

    def addItem(self, text: str, data=None) -> None:
        button = QPushButton(text)
        button.setObjectName("SegmentButton")
        button.setCheckable(True)
        button.setAutoDefault(False)
        button.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._group.addButton(button, len(self.buttons))
        self._layout.addWidget(button)
        self.buttons.append(button)
        self._data.append(data)
        if len(self.buttons) == 1:
            button.setChecked(True)

    def count(self) -> int:
        return len(self.buttons)

    def findData(self, data) -> int:
        return self._data.index(data) if data in self._data else -1

    def currentIndex(self) -> int:
        return self._group.checkedId()

    def currentData(self):
        return self._data[self.currentIndex()]

    def setCurrentIndex(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)

    def select(self, data, fallback=None) -> None:
        """Select the item with this data, else the one with ``fallback``."""
        index = self.findData(data)
        self.setCurrentIndex(index if index >= 0 else self.findData(fallback))

    def as_swatches(self, colors: list[dict]) -> None:
        """Show the buttons as small previews of a theme, one colors dict per button."""
        self.setObjectName("Swatches")
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        for button, c in zip(self.buttons, colors):
            button.setObjectName("")
            button.setFixedSize(128, 62)
            button.setStyleSheet(
                f"QPushButton {{ background: {c['BACKGROUND']}; color: {c['TEXT']}; border: 2px solid {c['BORDER']};"
                f" border-radius: 8px; text-align: left; padding: 8px; }}"
                f" QPushButton:checked {{ border-color: {theme.ACCENT}; }}"
                f" QPushButton:focus {{ border-color: {theme.ACCENT_HOVER}; }}")
