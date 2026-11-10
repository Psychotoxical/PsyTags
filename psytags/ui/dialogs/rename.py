"""Rename: the naming scheme is put together from chips, nothing has to be typed."""
from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
                               QListView, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from ... import convert, namescheme
from ...i18n import tr
from .. import theme
from ..persist import remember

ROLE = Qt.ItemDataRole.UserRole


class SchemeEditor(QWidget):
    """The chips of the naming scheme with a preview on the first of ``tracks``."""
    usable = Signal(bool)

    def __init__(self, tracks: list, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lay.addWidget(QLabel(tr("Zum Anfügen anklicken:")))
        lay.addLayout(self._palette(list(namescheme.DATA)))
        lay.addLayout(self._palette(list(namescheme.SEPARATORS) + [namescheme.FOLDER]))

        lay.addWidget(QLabel(tr("So wird benannt (anklicken entfernt, ziehen sortiert):")))
        self.chips = QListWidget()
        self.chips.setObjectName("SchemeChips")
        self.chips.setFlow(QListView.Flow.LeftToRight)
        self.chips.setWrapping(True)
        self.chips.setResizeMode(QListView.ResizeMode.Adjust)
        self.chips.setSpacing(2)
        self.chips.setFixedHeight(92)
        self.chips.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.chips.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.chips.itemClicked.connect(self.remove)
        model = self.chips.model()
        model.rowsInserted.connect(self._changed)
        model.rowsRemoved.connect(self._changed)
        model.rowsMoved.connect(self._changed)
        lay.addWidget(self.chips)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview.setMinimumHeight(self.fontMetrics().height() * 3)
        lay.addWidget(self.preview)

        self.cleanup_box = QCheckBox(tr("Alte Ordner und Reste wie Bilder in den Papierkorb verschieben"))
        self.cleanup_box.setChecked(namescheme.cleanup_enabled())
        lay.addWidget(self.cleanup_box)
        self.fill(namescheme.load())

    def _palette(self, tokens: list[str]) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        for token in tokens:
            b = QPushButton(namescheme.label(token))
            b.setObjectName("ChipButton")
            b.setAutoDefault(False)
            b.clicked.connect(lambda _=False, t=token: self.add(t))
            row.addWidget(b)
        row.addStretch(1)
        return row

    def add(self, token: str) -> None:
        item = QListWidgetItem(namescheme.label(token))
        item.setData(ROLE, token)
        if token == namescheme.FOLDER:
            item.setForeground(QColor(theme.ACCENT))
        self.chips.addItem(item)

    def fill(self, tokens: list[str]) -> None:
        self.chips.clear()
        for token in tokens:
            self.add(token)
        self._changed()

    def remove(self, item: QListWidgetItem) -> None:
        self.chips.takeItem(self.chips.row(item))

    def _changed(self, *_args) -> None:
        QTimer.singleShot(0, self.update_preview)             # after a drag has settled

    def tokens(self) -> list[str]:
        return [self.chips.item(i).data(ROLE) for i in range(self.chips.count())]

    def cleanup(self) -> bool:
        return self.cleanup_box.isChecked()

    def update_preview(self) -> None:
        t = self.tracks[0] if self.tracks else None
        target = namescheme.target_path(t, self.tokens()) if t is not None else ""
        usable = t is not None and bool(namescheme.segments(t, self.tokens()))
        self.usable.emit(usable)
        self.preview.setText(f"{t.filename}\n→ {convert.display_path(target, t)}" if usable else tr("Noch kein Name."))

    def save(self) -> None:
        namescheme.save(self.tokens())
        namescheme.set_cleanup(self.cleanup())


class RenameDialog(QDialog):
    def __init__(self, tracks: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Umbenennen"))
        self.setMinimumWidth(660)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        self.scheme = SchemeEditor(tracks)
        lay.addWidget(self.scheme)

        row = QHBoxLayout()
        reset = QPushButton(tr("Vorgabe"))
        reset.setAutoDefault(False)
        reset.clicked.connect(lambda: self.scheme.fill(namescheme.DEFAULT))
        row.addWidget(reset)
        row.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr("Umbenennen"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self.ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.scheme.usable.connect(self.ok.setEnabled)
        row.addWidget(buttons)
        lay.addLayout(row)
        remember(self, "rename")

    def tokens(self) -> list[str]:
        return self.scheme.tokens()

    def cleanup(self) -> bool:
        return self.scheme.cleanup()

    def accept(self) -> None:
        self.scheme.save()
        super().accept()
