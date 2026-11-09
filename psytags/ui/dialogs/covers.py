"""Manage covers (Edit > Cover > Manage covers, Ctrl+Alt+M)."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QHBoxLayout, QInputDialog, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QHeaderView)

from ... import tags
from ...i18n import tr
from ..persist import remember


class ManageCoversDialog(QDialog):
    """Edits one list of covers that is written to every selected file.
    Covers present in only some files are shown with their file count."""

    def __init__(self, tracks, parent=None):
        super().__init__(parent)
        self.tracks = tracks
        self.setWindowTitle(tr("Cover verwalten"))
        self.resize(720, 460)
        # Union of covers in order of first appearance, with file counts.
        self.covers: list[tags.Cover] = []
        self.counts: list[int] = []
        for t in tracks:
            for c in t.data.covers:
                if c in self.covers:
                    self.counts[self.covers.index(c)] += 1
                else:
                    self.covers.append(c)
                    self.counts.append(1)
        self.origin: list[tags.Cover | None] = list(self.covers)
        lay = QHBoxLayout(self)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Cover"), tr("Metadaten"), tr("Status")])
        self.tree.setIconSize(QSize(64, 64))
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tree, 1)
        side = QVBoxLayout()
        for text, slot in ((tr("&Hinzufügen..."), self.add), (tr("E&rsetzen..."), self.replace),
                           (tr("&Entfernen"), self.remove), (tr("Cover-&Typ ändern"), self.set_type),
                           (tr("Cover-&Beschreibung ändern..."), self.set_desc),
                           (tr("Nach &oben"), lambda: self.move(-1)),
                           (tr("Nach &unten"), lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            side.addWidget(b)
        QShortcut(QKeySequence("Del"), self.tree, self.remove)
        QShortcut(QKeySequence("Ins"), self.tree, self.add)
        side.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
                              Qt.Orientation.Vertical)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        side.addWidget(bb)
        lay.addLayout(side)
        self._fill()
        remember(self, "manage_covers")

    def _status(self, n: int) -> str:
        if n >= len(self.tracks):
            return tr("Cover in allen Dateien")
        return tr("Cover in 1 Datei") if n == 1 else tr("Cover in {1} Dateien", n)

    def _fill(self, sel: int = -1):
        self.tree.clear()
        for c, n in zip(self.covers, self.counts):
            img = QImage.fromData(c.data)
            typ = tags.COVER_TYPES[c.type] if c.type < len(tags.COVER_TYPES) else str(c.type)
            meta = f"{typ}\n{c.mime.split('/')[-1].upper()} {img.width()}x{img.height()}, " \
                   f"{len(c.data) // 1024} KB" + (f"\n{c.description}" if c.description else "")
            it = QTreeWidgetItem(["", meta, self._status(n)])
            if not img.isNull():
                it.setIcon(0, QIcon(QPixmap.fromImage(img.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio,
                                                                 Qt.TransformationMode.SmoothTransformation))))
            self.tree.addTopLevelItem(it)
        self.tree.setColumnWidth(0, 80)
        if 0 <= sel < len(self.covers):
            self.tree.setCurrentItem(self.tree.topLevelItem(sel))

    def _row(self) -> int:
        it = self.tree.currentItem()
        return self.tree.indexOfTopLevelItem(it) if it else -1

    def _pick(self) -> tags.Cover | None:
        p, _ = QFileDialog.getOpenFileName(self, tr("Cover hinzufügen"), self.tracks[0].folder if self.tracks else "",
                                           tr("Bilder (*.jpg *.jpeg *.png)"))
        if not p:
            return None
        with open(p, "rb") as fh:
            return tags.Cover(fh.read(), "image/png" if p.lower().endswith(".png") else "image/jpeg", 3)

    def add(self):
        c = self._pick()
        if c:
            self.covers.append(c)
            self.counts.append(len(self.tracks))
            self.origin.append(None)
            self._fill(len(self.covers) - 1)

    def replace(self):
        r = self._row()
        c = self._pick() if r >= 0 else None
        if c:
            old = self.covers[r]
            self.covers[r] = tags.Cover(c.data, c.mime, old.type, old.description)
            self._fill(r)

    def remove(self):
        r = self._row()
        if r >= 0:
            del self.covers[r]
            del self.counts[r]
            del self.origin[r]
            self._fill(min(r, len(self.covers) - 1))

    def set_type(self):
        r = self._row()
        if r < 0:
            return
        c = self.covers[r]
        name, ok = QInputDialog.getItem(self, tr("Cover-Typ ändern"), tr("Typ:"), tags.COVER_TYPES,
                                        c.type, False)
        if ok:
            self.covers[r] = tags.Cover(c.data, c.mime, tags.COVER_TYPES.index(name), c.description)
            self._fill(r)

    def set_desc(self):
        r = self._row()
        if r < 0:
            return
        c = self.covers[r]
        s, ok = QInputDialog.getText(self, tr("Cover-Beschreibung ändern"), tr("Beschreibung:"),
                                     text=c.description)
        if ok:
            self.covers[r] = tags.Cover(c.data, c.mime, c.type, s)
            self._fill(r)

    def move(self, d: int):
        r = self._row()
        if 0 <= r < len(self.covers) and 0 <= r + d < len(self.covers):
            for lst in (self.covers, self.counts, self.origin):
                lst[r], lst[r + d] = lst[r + d], lst[r]
            self._fill(r + d)

    def apply_to(self, t) -> None:
        """New covers and covers present in all files go to every file; a cover that
        was only in some files stays limited to those files (edited if changed)."""
        t.data.covers = [c for c, n, o in zip(self.covers, self.counts, self.origin)
                         if o is None or n >= len(self.tracks) or o in t.data.covers]
