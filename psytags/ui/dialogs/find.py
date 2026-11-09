"""Find dialog (Edit > Find, Ctrl+F)."""
from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QHeaderView, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout)

from ... import config
from ...i18n import tr
from ..persist import remember

STRATEGIES = ["Enthält", "Ganzes Wort", "Ganzer Inhalt", "Beginnt mit", "Endet mit",
              "Regulärer Ausdruck"]


class FindDialog(QDialog):
    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle(tr("Suchen"))
        self.resize(640, 420)
        s = config.settings()
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.text = QComboBox()
        self.text.setEditable(True)
        self.text.addItems(config.string_list(s, "find/history"))
        self.text.setEditText("")
        row.addWidget(self.text, 1)
        self.strategy = QComboBox()
        self.strategy.addItems([tr(x) for x in STRATEGIES])
        self.strategy.setCurrentIndex(int(s.value("find/strategy", 0)))
        row.addWidget(self.strategy)
        self.case = QCheckBox(tr("&Groß-/Kleinschreibung"))
        row.addWidget(self.case)
        go = QPushButton(tr("&Suchen"))
        go.setDefault(True)
        go.clicked.connect(self.search)
        row.addWidget(go)
        lay.addLayout(row)
        self.results = QTreeWidget()
        self.results.setHeaderLabels([tr("Dateiname"), tr("Feld"), tr("Treffer")])
        self.results.setRootIsDecorated(False)
        self.results.setSortingEnabled(True)
        self.results.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.results.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.results.setColumnWidth(0, 260)
        self.results.itemSelectionChanged.connect(self._select)
        lay.addWidget(self.results, 1)
        self.status = QLabel()
        lay.addWidget(self.status)
        self.text.lineEdit().returnPressed.connect(self.search)
        self.case.setChecked(config.settings().value("find/case", "false") in (True, "true"))
        self.case.toggled.connect(lambda on: config.settings().setValue("find/case", on))
        remember(self, "find")

    def _matcher(self):
        q = self.text.currentText()
        flags = 0 if self.case.isChecked() else re.IGNORECASE
        e = re.escape(q)
        pat = [e, rf"\b{e}\b", rf"^{e}$", rf"^{e}", rf"{e}$", q][self.strategy.currentIndex()]
        try:
            return re.compile(pat, flags)
        except re.error:
            return None

    def search(self):
        q = self.text.currentText()
        if not q:
            return
        s = config.settings()
        hist = [x for x in config.string_list(s, "find/history") if x != q]
        s.setValue("find/history", [q] + hist[:29])
        s.setValue("find/strategy", self.strategy.currentIndex())
        rx = self._matcher()
        self.results.clear()
        if rx is None:
            return
        files = set()
        n = 0
        for t in self.main.model.rows:
            entries = [(tr("Dateiname"), t.filename)]
            for k, vals in t.fields.items():
                entries += [(k, v) for v in vals]
            for fld, val in entries:
                if rx.search(val):
                    it = QTreeWidgetItem([t.filename, fld, val])
                    it.setData(0, Qt.ItemDataRole.UserRole, t)
                    self.results.addTopLevelItem(it)
                    files.add(id(t))
                    n += 1
        if n == 0:
            self.status.setText(tr("Keine Treffer gefunden."))
        else:
            self.status.setText(tr("{1} Treffer in {2} Datei(en) gefunden.", n, len(files)))

    def _select(self):
        ts = []
        for it in self.results.selectedItems():
            t = it.data(0, Qt.ItemDataRole.UserRole)
            if t not in ts:
                ts.append(t)
        if ts:
            self.main.view.select_tracks(ts)
