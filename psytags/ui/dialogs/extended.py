"""The dialog with every field of a file (All fields, Alt+T)."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QHeaderView)

from ...i18n import tr
from ..tagpanel import CoverView, keep_text
from ...config import FIELDS
from ..persist import remember


class FieldEditor(QDialog):
    def __init__(self, name: str, value: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Feld bearbeiten"))
        self.resize(420, 240)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Feld:")))
        self.name = QComboBox()
        self.name.setEditable(True)
        self.name.addItems(FIELDS)
        self.name.setEditText(name)
        lay.addWidget(self.name)
        lay.addWidget(QLabel(tr("Wert:")))
        self.value = QPlainTextEdit(value)
        lay.addWidget(self.value, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        QShortcut(QKeySequence("Ctrl+Return"), self.value, lambda: self.value.insertPlainText("\n"))
        QShortcut(QKeySequence("Return"), self, self.accept)
        remember(self, "field_editor")


class ExtendedTagsDialog(QDialog):
    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.setWindowTitle(tr("Alle Felder") + (f" - {tracks[0].filename}" if len(tracks) == 1
                                                      else f" - {len(tracks)} " + tr("Dateien")))
        self.resize(760, 480)
        # rows: (field, value or KEEP); one row per value of multi-value fields
        self.rows: list[list[str]] = []
        names: list[str] = []
        for t in tracks:
            for k in t.fields:
                if k not in names:
                    names.append(k)
        for k in sorted(names):
            vals = [t.get(k) for t in tracks]
            if all(v == vals[0] for v in vals):
                for v in vals[0]:
                    self.rows.append([k, v])
            else:
                self.rows.append([k, keep_text()])
        self.removed: set[str] = set()
        self.touched: set[str] = set()

        lay = QHBoxLayout(self)
        left = QVBoxLayout()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels([tr("Feld"), tr("Wert")])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 200)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda _: self.edit())
        left.addWidget(self.table, 1)
        row = QHBoxLayout()
        for text, slot, key in ((tr("Feld hinzufügen..."), self.new, "Ins"),
                                (tr("Feld bearbeiten..."), self.edit, "F2"),
                                (tr("Feld löschen"), self.remove, "Del")):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
            QShortcut(QKeySequence(key), self.table, slot)
        row.addStretch(1)
        left.addLayout(row)
        lay.addLayout(left, 1)
        right = QVBoxLayout()
        self.cover = CoverView()
        first = tracks[0].data.covers
        same = all(t.data.covers == first for t in tracks[1:])
        self.cover.show_covers(list(first) if same else [], not same)
        self.cover_dirty = False
        self.cover.changed.connect(lambda: setattr(self, "cover_dirty", True))
        self.cover.request.connect(self._cover_cmd)
        right.addWidget(self.cover)
        right.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        lay.addLayout(right)
        self._fill()
        remember(self, "extended_tags")

    def _fill(self, select=-1):
        self.table.setRowCount(len(self.rows))
        for i, (k, v) in enumerate(self.rows):
            self.table.setItem(i, 0, QTableWidgetItem(k))
            self.table.setItem(i, 1, QTableWidgetItem(v.replace("\n", " ⏎ ")))
        if 0 <= select < len(self.rows):
            self.table.selectRow(select)

    def new(self):
        d = FieldEditor("", "", self)
        if d.exec() and d.name.currentText().strip():
            k = d.name.currentText().strip().upper()
            self.rows.append([k, d.value.toPlainText()])
            self.touched.add(k)
            self.rows.sort(key=lambda r: r[0])
            self._fill(next(i for i, r in enumerate(self.rows) if r[0] == k))

    def edit(self):
        r = self.table.currentRow()
        if r < 0:
            return
        k, v = self.rows[r]
        d = FieldEditor(k, v, self)
        if d.exec():
            nk = d.name.currentText().strip().upper()
            self.touched.update({k, nk})
            if nk != k:
                self.removed.add(k) if not any(x[0] == k for i, x in enumerate(self.rows) if i != r) else None
            self.rows[r] = [nk, d.value.toPlainText()]
            self._fill(r)

    def remove(self):
        r = self.table.currentRow()
        if r < 0:
            return
        k = self.rows[r][0]
        del self.rows[r]
        self.touched.add(k)
        if not any(x[0] == k for x in self.rows):
            self.removed.add(k)
        self._fill(min(r, len(self.rows) - 1))

    def _cover_cmd(self, cmd):
        if cmd == "remove":
            self.cover.remove_current()
        elif cmd == "add":
            from PySide6.QtWidgets import QFileDialog
            p, _ = QFileDialog.getOpenFileName(self, tr("Cover hinzufügen"), self.tracks[0].folder,
                                               tr("Bilder (*.jpg *.jpeg *.png)"))
            if p:
                with open(p, "rb") as fh:
                    self.cover.set_cover(fh.read(), "image/png" if p.lower().endswith(".png")
                                         else "image/jpeg", replace=False)

    def apply_to(self, t) -> None:
        keep = keep_text()
        for k in self.removed:
            t.fields.pop(k, None)
        for k in self.touched - self.removed:
            vals = [v for kk, v in self.rows if kk == k]
            if keep in vals:
                continue
            t.set(k, vals)
        if self.cover_dirty:
            t.data.covers = list(self.cover.covers)
