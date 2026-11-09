"""Header and step bar above the list: the whole workflow, left to right."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from ..i18n import tr
from .icons import logo_pixmap


def shortcut_text(action: QAction) -> str:
    """The action's first shortcut in the words of the keyboard: Strg+Umschalt+M."""
    seq = action.shortcut().toString(QKeySequence.SequenceFormat.PortableText)
    return seq.replace("Ctrl", tr("Strg")).replace("Shift", tr("Umschalt"))


def _styled(widget: QWidget, name: str) -> QWidget:
    widget.setObjectName(name)
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    return widget


def _label(text: str, name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(name)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    return label


class ActionButton(QPushButton):
    """A button that triggers an action and follows its enabled state."""

    def __init__(self, action: QAction, text: str = "", name: str = "HeaderButton", parent=None):
        super().__init__(text, parent)
        self.setObjectName(name)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.action_ = action
        self.clicked.connect(action.trigger)
        action.changed.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self.setEnabled(self.action_.isEnabled())

    def sizeHint(self):                          # the labels live in a layout, not in the button text
        return self.layout().totalSizeHint() if self.layout() else super().sizeHint()

    def minimumSizeHint(self):
        return self.layout().totalMinimumSize() if self.layout() else super().minimumSizeHint()


class StepButton(ActionButton):
    """One numbered step of the workflow; also the way to run just this step."""

    def __init__(self, number: int, title: str, hint: str, action: QAction, parent=None):
        super().__init__(action, "", "Step", parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        row.addWidget(_label(str(number), "StepNumber"))
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addStretch(1)
        text.addWidget(_label(title, "StepTitle"))
        text.addWidget(_label(hint, "StepKey"))
        text.addStretch(1)
        row.addLayout(text, 1)


class SplitStep(QFrame):
    """A step with two ways to run it, e.g. on the selection or on the whole list."""

    def __init__(self, number: int, title: str, hint: str, choices: list[tuple[str, QAction]], parent=None):
        super().__init__(parent)
        self.setObjectName("StepSplit")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(10)
        row.addWidget(_label(str(number), "StepNumber"))
        text = QVBoxLayout()
        text.setSpacing(0)
        text.addStretch(1)
        text.addWidget(_label(title, "StepTitle"))
        text.addWidget(_label(hint, "StepKey"))
        text.addStretch(1)
        row.addLayout(text, 1)
        buttons = QVBoxLayout()
        buttons.setSpacing(2)
        buttons.addStretch(1)
        for label, action in choices:
            buttons.addWidget(ActionButton(action, label, "StepChoice"))
        buttons.addStretch(1)
        row.addLayout(buttons)


class PrimaryButton(ActionButton):
    def __init__(self, title: str, hint: str, action: QAction, parent=None):
        super().__init__(action, "", "Primary", parent)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        column = QVBoxLayout(self)
        column.setContentsMargins(22, 0, 22, 0)
        column.setSpacing(0)
        column.addStretch(1)
        column.addWidget(_label(title, "PrimaryTitle"))
        column.addWidget(_label(hint, "PrimaryKey"))
        column.addStretch(1)


class TopBar(QWidget):
    """Goes into the main window's menu widget slot, above list and tag panel."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._header(window))
        column.addWidget(self._steps(window))

    def _header(self, w) -> QWidget:
        bar = _styled(QWidget(), "Header")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(8)
        title = QLabel()
        title.setObjectName("Wordmark")
        title.setPixmap(logo_pixmap(32))
        title.setAccessibleName("PsyTags")
        row.addWidget(title)
        row.addWidget(ActionButton(w.act_dir, tr("Ordner öffnen")))
        row.addWidget(ActionButton(w.act_add_dir, tr("Ordner hinzufügen")))
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(tr("Suchen in allen Spalten"))
        self.search.setClearButtonEnabled(True)
        row.addWidget(self.search, 1)
        row.addWidget(ActionButton(w.act_undo, tr("Rückgängig")))
        row.addWidget(ActionButton(w.act_save, tr("Speichern")))
        row.addWidget(ActionButton(w.act_batch_summary, tr("Übersicht"), "SummaryButton"))
        menu = QToolButton()
        menu.setObjectName("MenuButton")
        menu.setText("≡")
        menu.setToolTip(tr("Menü"))
        menu.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu.setMenu(w.app_menu)
        row.addWidget(menu)
        return bar

    def _steps(self, w) -> QWidget:
        bar = _styled(QWidget(), "StepBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 12, 16, 12)
        row.setSpacing(6)
        row.addWidget(PrimaryButton(tr("Alle Alben automatisch"), shortcut_text(w.act_auto_all), w.act_auto_all))
        divider = QFrame()
        divider.setObjectName("StepDivider")
        divider.setFixedWidth(1)
        row.addSpacing(8)
        row.addWidget(divider)
        row.addSpacing(8)
        row.addWidget(SplitStep(1, tr("Moods"), shortcut_text(w.act_moods),
                                [(tr("Auswahl"), w.act_moods), (tr("Alle"), w.act_moods_all)]))
        steps = [("MusicBrainz", shortcut_text(w.act_auto_mb), w.act_auto_mb),
                 (tr("Nummern"), shortcut_text(w.act_numbers), w.act_numbers),
                 (tr("Cover"), "Cover Art Archive", w.act_cover_fetch),
                 (tr("Genres"), shortcut_text(w.act_lastfm), w.act_lastfm),
                 (tr("Umbenennen"), shortcut_text(w.act_ttf), w.act_ttf)]
        for number, (title, hint, action) in enumerate(steps, 2):
            row.addWidget(StepButton(number, title, hint, action))
        return bar
