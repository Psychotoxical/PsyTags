"""Header and step bar above the list: the whole workflow, left to right."""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtCore import QSize
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from ..i18n import tr
from .icons import logo_pixmap

STEP_LEVELS = 3         # full, without the shortcuts, numbers only
HEADER_LEVELS = 2       # text, icons only
SEARCH_MIN_WIDTH = 120


def shortcut_text(action: QAction) -> str:
    """The action's first shortcut in the words of the keyboard: Strg+Umschalt+M, on a Mac
    with its symbols (⇧⌘M), where Qt puts Ctrl on the Command key."""
    if sys.platform == "darwin":
        return action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
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
        self.full_text = text
        self.setAccessibleName(text)
        self.clicked.connect(action.trigger)
        action.changed.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        self.setEnabled(self.action_.isEnabled())

    def set_level(self, level: int) -> None:
        """Level 1 shows the action's icon instead of the text."""
        self.setText("" if level else self.full_text)
        self.setIcon(self.action_.icon() if level else QIcon())
        self.setToolTip(self.full_text if level else "")

    def sizeHint(self):                          # the labels live in a layout, not in the button text
        return self.layout().totalSizeHint() if self.layout() else super().sizeHint()

    def minimumSizeHint(self):
        return self.layout().totalMinimumSize() if self.layout() else super().minimumSizeHint()


class _StepText:
    """Title and shortcut of a step, which give way when the bar gets narrow."""

    def _add_step_text(self, row: QHBoxLayout, number: int, title: str, hint: str) -> None:
        self.tip = f"{title} ({hint})"
        self.title_label = _label(title, "StepTitle")
        self.hint_label = _label(hint, "StepKey")
        self.text_layout = QVBoxLayout()
        self.text_layout.setSpacing(0)
        self.text_layout.addStretch(1)
        self.text_layout.addWidget(self.title_label)
        self.text_layout.addWidget(self.hint_label)
        self.text_layout.addStretch(1)
        row.addWidget(_label(str(number), "StepNumber"))
        row.addLayout(self.text_layout, 1)

    def set_level(self, level: int) -> None:
        self.hint_label.setVisible(level == 0)
        self.title_label.setVisible(level < 2)
        self.setToolTip(self.tip if level else "")
        self.text_layout.invalidate()
        self.layout().invalidate()
        self.updateGeometry()


class StepButton(_StepText, ActionButton):
    """One numbered step of the workflow; also the way to run just this step."""

    def __init__(self, number: int, title: str, hint: str, action: QAction, parent=None):
        super().__init__(action, "", "Step", parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(10)
        self._add_step_text(row, number, title, hint)


class SplitStep(_StepText, QFrame):
    """A step with two ways to run it, e.g. on the selection or on the whole list."""

    def __init__(self, number: int, title: str, hint: str, choices: list[tuple[str, QAction]], parent=None):
        super().__init__(parent)
        self.setObjectName("StepSplit")
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 8, 0)
        row.setSpacing(10)
        self._add_step_text(row, number, title, hint)
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
        self.title = title
        self.tip = f"{title} ({hint})"
        self.title_label = _label(title, "PrimaryTitle")
        self.hint_label = _label(hint, "PrimaryKey")
        column.addStretch(1)
        column.addWidget(self.title_label)
        column.addWidget(self.hint_label)
        column.addStretch(1)

    def set_level(self, level: int) -> None:
        self.hint_label.setVisible(level == 0)
        self.title_label.setText(self.title if level < 2 else tr("Auto"))
        self.setToolTip(self.tip if level else "")
        self.layout().invalidate()
        self.updateGeometry()


class TopBar(QWidget):
    """Goes into the main window's menu widget slot, above list and tag panel."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.header_buttons: list[ActionButton] = []
        self.step_widgets: list = []
        column = QVBoxLayout(self)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        self.header_bar = self._header(window)
        self.step_bar = self._steps(window)
        column.addWidget(self.header_bar)
        column.addWidget(self.step_bar)

    def minimumSizeHint(self) -> QSize:          # the bars fold, so they never hold the window wide
        return QSize(0, super().minimumSizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.isVisible():
            self._fit(event.size().width())

    def showEvent(self, event) -> None:          # only now the style sheet decides the real sizes
        super().showEvent(event)
        self._fit(self.width())

    def _fit(self, width: int) -> None:
        self._fold(self.header_bar, self.header_buttons, HEADER_LEVELS, width)
        self._fold(self.step_bar, self.step_widgets, STEP_LEVELS, width)

    @staticmethod
    def _fold(bar: QWidget, widgets: list, levels: int, width: int) -> None:
        """Use the fullest level that fits; the last one is the floor."""
        for level in range(levels):
            for widget in widgets:
                widget.set_level(level)
            bar.layout().invalidate()
            if bar.layout().totalSizeHint().width() <= width:      # minimum sizes would clip the labels
                return

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
        def add(action: QAction, text: str, name: str = "HeaderButton") -> None:
            button = ActionButton(action, text, name)
            self.header_buttons.append(button)
            row.addWidget(button)
        add(w.act_dir, tr("Ordner öffnen"))
        add(w.act_add_dir, tr("Ordner hinzufügen"))
        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText(tr("Suchen in allen Spalten"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(SEARCH_MIN_WIDTH)
        row.addWidget(self.search, 1)
        add(w.act_undo, tr("Rückgängig"))
        add(w.act_save, tr("Speichern"))
        add(w.act_batch_summary, tr("Übersicht"), "SummaryButton")
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
        primary = PrimaryButton(tr("Alle Alben automatisch"), shortcut_text(w.act_auto_all), w.act_auto_all)
        row.addWidget(primary)
        divider = QFrame()
        divider.setObjectName("StepDivider")
        divider.setFixedWidth(1)
        row.addSpacing(8)
        row.addWidget(divider)
        row.addSpacing(8)
        moods = SplitStep(1, tr("Moods"), shortcut_text(w.act_moods),
                          [(tr("Auswahl"), w.act_moods), (tr("Alle"), w.act_moods_all)])
        row.addWidget(moods)
        self.step_widgets += [primary, moods]
        steps = [("MusicBrainz", shortcut_text(w.act_auto_mb), w.act_auto_mb, w.act_auto_mb_all),
                 (tr("Nummern"), shortcut_text(w.act_numbers), w.act_numbers, w.act_numbers_all),
                 (tr("Cover"), "Cover Art Archive", w.act_cover_fetch, w.act_cover_fetch_all),
                 (tr("Genres"), shortcut_text(w.act_lastfm), w.act_lastfm, w.act_lastfm_all)]
        for number, (title, hint, selection, everything) in enumerate(steps, 2):
            step = SplitStep(number, title, hint, [(tr("Auswahl"), selection), (tr("Alle"), everything)])
            self.step_widgets.append(step)
            row.addWidget(step)
        rename = SplitStep(6, tr("Umbenennen"), shortcut_text(w.act_ttf),
                           [(tr("Auswahl"), w.act_ttf), (tr("Alle"), w.act_ttf_all)])
        self.step_widgets.append(rename)
        row.addWidget(rename)
        return bar
