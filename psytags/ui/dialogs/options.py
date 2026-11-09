"""Options dialog, column customization and tag panel customization."""
from __future__ import annotations

import copy

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton,
                               QTabWidget, QVBoxLayout, QWidget)

from ... import config, numbering
from ...config import Column, Options, PanelField
from ...i18n import tr
from ..persist import remember


def _buttons(dlg) -> QDialogButtonBox:
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
    bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


class _ListEditor(QDialog):
    """Shared list + detail form editor (columns, tag panel fields)."""

    def __init__(self, title, items, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(620, 420)
        self.items = copy.deepcopy(items)
        lay = QVBoxLayout(self)
        body = QHBoxLayout()
        lay.addLayout(body, 1)
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load)
        self.list.itemChanged.connect(self._checked)
        body.addWidget(self.list, 1)
        side = QVBoxLayout()
        for text, slot in ((tr("&Neu"), self.new), (tr("&Duplizieren"), self.duplicate),
                           (tr("&Löschen"), self.delete), (tr("Nach &oben"), lambda: self.move(-1)),
                           (tr("Nach &unten"), lambda: self.move(1))):
            b = QPushButton(text)
            b.clicked.connect(slot)
            side.addWidget(b)
        side.addStretch(1)
        body.addLayout(side)
        self.form = QFormLayout()
        lay.addLayout(self.form)
        lay.addWidget(_buttons(self))
        self._loading = False

    def _fill(self, row=0):
        self._loading = True
        self.list.clear()
        for it in self.items:
            li = QListWidgetItem(it.name.replace("&", ""))
            li.setFlags(li.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            li.setCheckState(Qt.CheckState.Checked if it.enabled else Qt.CheckState.Unchecked)
            self.list.addItem(li)
        self._loading = False
        if self.items:
            self.list.setCurrentRow(max(0, min(row, len(self.items) - 1)))

    def _checked(self, li):
        if not self._loading:
            self.items[self.list.row(li)].enabled = li.checkState() == Qt.CheckState.Checked

    def move(self, d):
        r = self.list.currentRow()
        if 0 <= r + d < len(self.items) and r >= 0:
            self.items[r], self.items[r + d] = self.items[r + d], self.items[r]
            self._fill(r + d)

    def delete(self):
        r = self.list.currentRow()
        if r >= 0:
            del self.items[r]
            self._fill(r)

    def duplicate(self):
        r = self.list.currentRow()
        if r >= 0:
            self.items.insert(r + 1, copy.deepcopy(self.items[r]))
            self._fill(r + 1)


class ColumnsDialog(_ListEditor):
    def __init__(self, columns: list[Column], parent=None):
        super().__init__(tr("Spalten anpassen..."), columns, parent)
        self.name, self.value, self.field, self.sort = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.numeric = QCheckBox(tr("Numerisch"))
        self.form.addRow(tr("Name:"), self.name)
        self.form.addRow(tr("Wert:"), self.value)
        self.form.addRow(tr("Feld:"), self.field)
        self.form.addRow(tr("Sortieren nach:"), self.sort)
        self.form.addRow(self.numeric)
        for w in (self.name, self.value, self.field, self.sort):
            w.textEdited.connect(self._store)
        self.numeric.toggled.connect(self._store)
        self._fill()
        remember(self, "columns")

    @property
    def columns(self):
        return self.items

    def _load(self, r):
        if r < 0 or r >= len(self.items):
            return
        c = self.items[r]
        self._loading = True
        self.name.setText(c.name)
        self.value.setText(c.value)
        self.field.setText(c.field)
        self.sort.setText(c.sort)
        self.numeric.setChecked(c.numeric)
        self._loading = False

    def _store(self, *_):
        r = self.list.currentRow()
        if self._loading or r < 0:
            return
        c = self.items[r]
        c.name, c.value, c.field, c.sort = (self.name.text(), self.value.text(),
                                            self.field.text(), self.sort.text())
        c.numeric = self.numeric.isChecked()
        self.list.item(r).setText(c.name.replace("&", ""))

    def new(self):
        self.items.append(Column(tr("Neue Spalte"), "%title%", field="%title%"))
        self._fill(len(self.items) - 1)


class PanelDialog(_ListEditor):
    def __init__(self, fields: list[PanelField], parent=None):
        super().__init__(tr("Tag-Panel anpassen..."), fields, parent)
        self.name, self.value = QLineEdit(), QComboBox()
        self.value.setEditable(True)
        from ...config import FIELDS
        self.value.addItems(FIELDS + ["_DIRECTORY"])
        self.size = QComboBox()
        self.size.addItems([tr("Ganze Breite"), "1/2", "1/3", "1/4"])
        self.form.addRow(tr("Name:"), self.name)
        self.form.addRow(tr("Feld:"), self.value)
        self.form.addRow(tr("Größe:"), self.size)
        self.name.textEdited.connect(self._store)
        self.value.editTextChanged.connect(self._store)
        self.size.currentIndexChanged.connect(self._store)
        self._fill()
        remember(self, "panel")

    @property
    def fields(self):
        return self.items

    def _load(self, r):
        if r < 0 or r >= len(self.items):
            return
        f = self.items[r]
        self._loading = True
        self.name.setText(f.name)
        self.value.setEditText(f.value)
        fracs = [1, 1 / 2, 1 / 3, 1 / 4]
        self.size.setCurrentIndex(min(range(4), key=lambda i: abs(fracs[i] - f.fraction)))
        self._loading = False

    def _store(self, *_):
        r = self.list.currentRow()
        if self._loading or r < 0:
            return
        f = self.items[r]
        f.name, f.value = self.name.text(), self.value.currentText().upper()
        f.size = (self.size.currentIndex() + 1) if f.version == 0 else 12 // (self.size.currentIndex() + 1)
        self.list.item(r).setText(f.name.replace("&", ""))

    def new(self):
        self.items.append(PanelField(tr("Neues Feld"), "COMMENT"))
        self._fill(len(self.items) - 1)


class OptionsDialog(QDialog):
    def __init__(self, opts: Options, parent=None, tab: str = ""):
        super().__init__(parent)
        self.opts = copy.deepcopy(opts)
        self.setWindowTitle(tr("Optionen"))
        self.resize(560, 420)
        lay = QVBoxLayout(self)
        tabs = self.tabs = QTabWidget()
        lay.addWidget(tabs)

        g = QWidget()
        f = QFormLayout(g)
        self.lang = QComboBox()
        self.lang.addItems(["Deutsch", "English"])
        self.lang.setCurrentIndex(0 if opts.language == "de" else 1)
        f.addRow(tr("Sprache (nach Neustart):"), self.lang)
        self.theme = QComboBox()
        self.theme.addItems([tr("Catppuccin Mocha (dunkel)"), tr("Catppuccin Latte (hell)")])
        self.theme.setCurrentIndex(1 if opts.theme == "latte" else 0)
        f.addRow(tr("Design (nach Neustart):"), self.theme)
        self.autosave = QCheckBox(tr("Tags beim Wechsel der Auswahl speichern"))
        self.autosave.setChecked(opts.save_on_selection_change)
        f.addRow(self.autosave)
        self.keep_mtime = QCheckBox(tr("Zeitstempel bei Dateien beibehalten"))
        self.keep_mtime.setChecked(opts.keep_mtime)
        f.addRow(self.keep_mtime)
        tabs.addTab(g, tr("Allgemein"))

        g = QWidget()
        f = QFormLayout(g)
        self.subfolders = QCheckBox(tr("Unterverzeichnisse einlesen"))
        self.subfolders.setChecked(opts.subfolders)
        f.addRow(self.subfolders)
        tabs.addTab(g, tr("Verzeichnisse"))

        g = QWidget()
        f = QFormLayout(g)
        self.id3 = QComboBox()
        self.id3.addItems(["ID3v2.3 UTF-16", "ID3v2.4 UTF-8"])
        self.id3.setCurrentIndex(0 if opts.id3_version == 3 else 1)
        f.addRow(tr("ID3v2-Version (MP3):"), self.id3)
        self.v1 = QCheckBox(tr("Zusätzlich ID3v1 schreiben"))
        self.v1.setChecked(opts.write_id3v1)
        f.addRow(self.v1)
        self.drop_comments = QCheckBox(tr("Kommentare standardmäßig löschen (MusicBrainz-Import, Vorauswahl im Tag-Panel)"))
        self.drop_comments.setChecked(opts.drop_comments)
        f.addRow(self.drop_comments)
        tabs.addTab(g, tr("Tags"))
        tabs.addTab(self._numbers_tab(), tr("Nummern"))
        tabs.addTab(self._cover_tab(), tr("Cover"))
        tabs.addTab(self._lastfm_tab(), tr("Last.fm"))

        lay.addWidget(_buttons(self))
        tabs.setCurrentIndex(int(config.settings().value("dialogs/options/tab", 0)))
        for i in range(tabs.count()):
            if tab and tabs.tabText(i) == tab:
                tabs.setCurrentIndex(i)
        tabs.currentChanged.connect(lambda i: config.settings().setValue("dialogs/options/tab", i))
        remember(self, "options")

    def _cover_tab(self) -> QWidget:
        from ...websources import coverprovider
        from ..theme import ERROR
        providers, problems = coverprovider.discover()
        g = QWidget()
        column = QVBoxLayout(g)
        explain = QLabel(tr("Von oben nach unten: Die erste Quelle, die ein Cover liefert, gewinnt."))
        explain.setWordWrap(True)
        column.addWidget(explain)
        self.cover_sources = QListWidget()
        for name, on in coverprovider.arranged(providers):
            it = QListWidgetItem(name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.cover_sources.addItem(it)
        column.addWidget(self.cover_sources, 1)
        row = QHBoxLayout()
        for text, step in ((tr("Nach &oben"), -1), (tr("Nach &unten"), 1)):
            b = QPushButton(text.replace("&", ""))
            b.clicked.connect(lambda _=False, step=step: self.move_cover_source(step))
            row.addWidget(b)
        row.addStretch(1)
        open_folder = QPushButton(tr("Ordner öffnen"))
        open_folder.clicked.connect(self._open_provider_folder)
        row.addWidget(open_folder)
        column.addLayout(row)
        for problem in problems:
            label = QLabel(problem)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {ERROR};")
            column.addWidget(label)
        return g

    def move_cover_source(self, step: int) -> None:
        row = self.cover_sources.currentRow()
        if row < 0 or not 0 <= row + step < self.cover_sources.count():
            return
        self.cover_sources.insertItem(row + step, self.cover_sources.takeItem(row))
        self.cover_sources.setCurrentRow(row + step)

    @staticmethod
    def _open_provider_folder() -> None:
        import os
        from ...websources import coverprovider
        os.makedirs(coverprovider.folder(), exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(coverprovider.folder()))

    def _lastfm_tab(self) -> QWidget:
        s = config.settings()
        g = QWidget()
        f = QVBoxLayout(g)
        stored = s.value("lastfm/api_key", "")
        self.lastfm_on = QCheckBox(tr("Genres von Last.fm holen"))
        self.lastfm_on.setChecked(s.value("lastfm/enabled", "false") in (True, "true") or not stored)
        f.addWidget(self.lastfm_on)
        link = QLabel(tr("API-Key (kostenlos unter <a href='https://www.last.fm/api/account/create'>"
                         "last.fm/api/account/create</a>):"))
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        f.addWidget(link)
        self.lastfm_key = QLineEdit(stored)
        f.addWidget(self.lastfm_key)
        f.addStretch(1)
        return g

    def _numbers_tab(self) -> QWidget:
        fmt = numbering.NumberFormat.load()
        g = QWidget()
        f = QFormLayout(g)
        self.number_boxes = {}
        for name, text in (("track_zeros", "Tracknummer mit führender Null"),
                           ("track_total", "Tracknummer mit Gesamtzahl"),
                           ("disc_on", "Discnummer schreiben"),
                           ("disc_zeros", "Discnummer mit führender Null"),
                           ("disc_total", "Discnummer mit Gesamtzahl")):
            box = QCheckBox(tr(text))
            box.setChecked(getattr(fmt, name))
            box.toggled.connect(self._number_example)
            self.number_boxes[name] = box
            f.addRow(box)
        self.number_sample = QLabel()
        f.addRow(self.number_sample)
        self._number_example()
        return g

    def _number_format(self) -> numbering.NumberFormat:
        return numbering.NumberFormat(**{name: box.isChecked() for name, box in self.number_boxes.items()})

    def _number_example(self, *_args) -> None:
        track, disc = numbering.example(self._number_format())
        self.number_sample.setText(tr("Beispiel: Track {1}, Disc {2}", track, disc) if disc else tr("Beispiel: Track {1}", track))

    def accept(self):
        from ...websources import coverprovider
        coverprovider.save_arrangement([(self.cover_sources.item(i).text(),
                                         self.cover_sources.item(i).checkState() == Qt.CheckState.Checked)
                                        for i in range(self.cover_sources.count())])
        self._number_format().save()
        s = config.settings()
        key = self.lastfm_key.text().strip()
        s.setValue("lastfm/api_key", key)
        s.setValue("lastfm/enabled", self.lastfm_on.isChecked() and bool(key))
        o = self.opts
        o.language = "de" if self.lang.currentIndex() == 0 else "en"
        o.theme = "latte" if self.theme.currentIndex() == 1 else "mocha"
        o.save_on_selection_change = self.autosave.isChecked()
        o.keep_mtime = self.keep_mtime.isChecked()
        o.subfolders = self.subfolders.isChecked()
        o.id3_version = 3 if self.id3.currentIndex() == 0 else 4
        o.write_id3v1 = self.v1.isChecked()
        o.drop_comments = self.drop_comments.isChecked()
        super().accept()
