"""Options dialog, column customization and tag panel customization."""
from __future__ import annotations

import copy

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from ... import config
from ...config import Column, Options, PanelField
from ...i18n import tr
from .. import theme
from ..controls import SWITCH_SIZE, NumberFormatEditor, Segmented, add_row, add_switch, paint_switch
from ..persist import remember
from ...websources import discogs, lastfm
from .tagsources import run_async


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


class KeyField(QWidget):
    """A hidden key or token, with a mark that says whether its server takes it."""

    def __init__(self, stored: str, verify):
        super().__init__()
        self.state = ""                 # "": nothing known, "ok", "bad"
        self._verify = verify
        self._asked = ""
        self._jobs: list = []
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.input = QLineEdit(stored)
        self.input.setEchoMode(QLineEdit.EchoMode.Password)
        row.addWidget(self.input, 1)
        self.mark = QLabel()
        self.mark.setFixedWidth(18)
        self.mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row.addWidget(self.mark)
        self.input.textChanged.connect(self._edited)
        self.input.editingFinished.connect(self.check)

    def check(self) -> None:
        """Ask the server, once per input. The dialog stays usable meanwhile."""
        key = self.input.text().strip()
        if not key or key == self._asked:
            return
        self._asked = key
        verify = self._verify

        def work() -> tuple[str, bool]:
            try:
                verify(key)
            except Exception:
                return key, False
            return key, True
        self._jobs.append(run_async(work, self._answered))

    def _edited(self) -> None:
        self._asked = ""
        self._show("")

    def _answered(self, answer: tuple[str, bool]) -> None:
        key, works = answer
        if key == self.input.text().strip():    # else it was typed over meanwhile
            self._show("ok" if works else "bad")

    def _show(self, state: str) -> None:
        self.state = state
        text, color, tip = {"ok": ("✓", theme.ICON_POSITIVE, tr("Verbindung klappt")),
                            "bad": ("✗", theme.ERROR, tr("Nicht angenommen, oder der Server ist gerade nicht erreichbar")),
                            "": ("", "", "")}[state]
        self.mark.setText(text)
        self.mark.setToolTip(tip)
        self.mark.setStyleSheet(f"color: {color}; font-size: 16px; font-weight: 700;" if color else "")


class _SourceDelegate(QStyledItemDelegate):
    """A cover source as a row: grip for dragging, name, switch."""
    ROW = 46

    def sizeHint(self, option, index) -> QSize:
        return QSize(0, self.ROW)                       # the list gives the row its full width

    @staticmethod
    def switch_rect(rect: QRect) -> QRect:
        return QRect(rect.right() - 12 - SWITCH_SIZE.width(), rect.center().y() - SWITCH_SIZE.height() // 2 + 1,
                     SWITCH_SIZE.width(), SWITCH_SIZE.height())

    def paint(self, painter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = option.rect.adjusted(0, 3, -1, -3)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        painter.setPen(QPen(QColor(theme.ACCENT if selected else theme.BUTTON), 1))
        painter.setBrush(QColor(theme.CHROME))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QPen(QColor(theme.SECONDARY), 1.6))
        for y in (box.center().y() - 3, box.center().y() + 3):
            painter.drawLine(box.left() + 13, y, box.left() + 26, y)
        painter.setPen(QColor(theme.TEXT))
        painter.drawText(box.adjusted(38, 0, -60, 0), Qt.AlignmentFlag.AlignVCenter, index.data())
        painter.restore()
        paint_switch(painter, self.switch_rect(option.rect), self._is_on(index))

    @staticmethod
    def _is_on(index) -> bool:
        return index.data(Qt.ItemDataRole.CheckStateRole) in (Qt.CheckState.Checked, Qt.CheckState.Checked.value)

    def editorEvent(self, event, model, option, index) -> bool:
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick, QEvent.Type.MouseButtonRelease) \
                and self.switch_rect(option.rect).contains(event.position().toPoint()):
            if event.type() == QEvent.Type.MouseButtonRelease:
                model.setData(index, Qt.CheckState.Unchecked if self._is_on(index) else Qt.CheckState.Checked,
                              Qt.ItemDataRole.CheckStateRole)
            return True
        return super().editorEvent(event, model, option, index)


class OptionsDialog(QDialog):
    """One page in the order of the work: the steps of the main window, then files and program."""
    SECTIONS = (("moods", "1", "Moods", "Analyse aus dem Audio"),
                ("musicbrainz", "2", "MusicBrainz", "Tags aus der Datenbank"),
                ("discogs", "", "Discogs", "Wenn MusicBrainz ein Album offen lässt"),
                ("numbers", "3", "Nummern", "Format von Track und Disc"),
                ("cover", "4", "Cover", "Die erste Quelle, die ein Cover liefert, gewinnt."),
                ("genres", "5", "Genres", "Von Last.fm"),
                ("files", "", "Dateien", "Lesen und Schreiben"),
                ("program", "", "Programm", "Gilt nach einem Neustart"))

    def __init__(self, opts: Options, parent=None, section: str = ""):
        super().__init__(parent)
        self.opts = copy.deepcopy(opts)
        self.setWindowTitle(tr("Optionen"))
        self.resize(860, 720)
        self.setMinimumSize(720, 480)
        self._blocks: dict[str, QWidget] = {}
        self._links: dict[str, QPushButton] = {}
        self._jumping = False
        keys = self.section_keys()
        self._wanted = section if section in keys else ""
        self._current = self._wanted or keys[0]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        page = QWidget()
        page.setObjectName("OptionsPage")
        self._column = QVBoxLayout(page)
        self._column.setContentsMargins(30, 6, 30, 6)
        self._column.setSpacing(0)
        fill = {"moods": self._moods, "musicbrainz": self._musicbrainz, "discogs": self._discogs, "numbers": self._numbers,
                "cover": self._cover, "genres": self._genres, "files": self._files, "program": self._program}
        for i, (key, number, title, what) in enumerate(self.SECTIONS):
            if i:
                rule = QFrame()
                rule.setObjectName("SectionRule")
                self._column.addWidget(rule)
            self._column.addWidget(self._block(key, number, title, what, fill[key]))
        self._column.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidget(page)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().valueChanged.connect(self._follow_scroll)
        root.addWidget(self.scroll, 1)
        root.addWidget(self._footer())
        self._mark_current()
        remember(self, "options2")

    # ------------------------------------------------------------------ frame
    def _header(self) -> QWidget:
        head = QWidget()
        head.setObjectName("OptionsHeader")
        row = QHBoxLayout(head)
        row.setContentsMargins(30, 18, 30, 12)
        title = QLabel(tr("Optionen"))
        title.setObjectName("DialogTitle")
        row.addWidget(title)
        row.addStretch(1)
        group = QButtonGroup(head)
        for key, _number, text, _what in self.SECTIONS:
            link = QPushButton(tr(text))
            link.setObjectName("SectionLink")
            link.setCheckable(True)
            link.setAutoDefault(False)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _=False, key=key: self.show_section(key))
            group.addButton(link)
            row.addWidget(link)
            self._links[key] = link
        return head

    def _footer(self) -> QWidget:
        foot = QWidget()
        foot.setObjectName("OptionsFooter")
        row = QHBoxLayout(foot)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(8)
        row.addStretch(1)
        cancel = QPushButton(tr("Abbrechen"))
        cancel.setAutoDefault(False)
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        save = QPushButton(tr("&Speichern").replace("&", ""))
        save.setObjectName("DialogPrimary")
        save.setDefault(True)
        save.clicked.connect(self.accept)
        row.addWidget(save)
        return foot

    def _block(self, key, number, title, what, fill) -> QWidget:
        block = QWidget()
        grid = QHBoxLayout(block)
        grid.setContentsMargins(0, 18, 0, 18)
        grid.setSpacing(24)
        side = QWidget()
        side.setFixedWidth(190)
        info = QVBoxLayout(side)
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(5)
        line = QHBoxLayout()
        line.setSpacing(9)
        if number:
            badge = QLabel(number)
            badge.setObjectName("StepBadge")
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            line.addWidget(badge)
        heading = QLabel(tr(title))
        heading.setObjectName("SectionTitle")
        line.addWidget(heading)
        line.addStretch(1)
        info.addLayout(line)
        note = QLabel(tr(what))
        note.setObjectName("DialogSubtitle")
        note.setWordWrap(True)
        info.addWidget(note)
        info.addStretch(1)
        grid.addWidget(side)
        area = QVBoxLayout()
        area.setSpacing(12)
        fill(area)
        grid.addLayout(area, 1)
        self._blocks[key] = block
        return block

    _row = staticmethod(add_row)
    _switch = staticmethod(add_switch)

    @staticmethod
    def _segmented(items, chosen, fallback=None) -> Segmented:
        seg = Segmented()
        for text, data in items:
            seg.addItem(text, data)
        seg.select(chosen, fallback)
        return seg

    @staticmethod
    def _hint(area: QVBoxLayout, text: str) -> None:
        label = QLabel(text)
        label.setObjectName("DialogSubtitle")
        label.setWordWrap(True)
        area.addWidget(label)

    # ------------------------------------------------------------------ navigation
    def section_keys(self) -> list[str]:
        return [s[0] for s in self.SECTIONS]

    def current_section(self) -> str:
        return self._current

    def show_section(self, key: str) -> None:
        self._current = key
        self._mark_current()
        self._jumping = True
        self.scroll.verticalScrollBar().setValue(self._blocks[key].y())
        self._jumping = False

    def _mark_current(self) -> None:
        self._links[self._current].setChecked(True)

    def _follow_scroll(self, value: int) -> None:
        if self._jumping:
            return
        self._current = [k for k in self.section_keys() if self._blocks[k].y() <= value + 24][-1]
        self._mark_current()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.lastfm_field.check()
        self.discogs_field.check()
        if self._wanted:
            key, self._wanted = self._wanted, ""
            QTimer.singleShot(0, lambda: self.show_section(key))    # the page has its final layout then

    # ------------------------------------------------------------------ sections
    def _moods(self, area: QVBoxLayout) -> None:
        self.mood_level = self._segmented(((tr("Wenige"), "few"), (tr("Normal"), "normal"), (tr("Viele"), "many")),
                                          self.opts.mood_level, "normal")
        self._row(area, tr("Menge der Moods"), self.mood_level)
        self._hint(area, tr("Gilt für neue Analysen. Vorhandene Moods ändern sich erst, wenn die Songs neu analysiert werden."))

    def _musicbrainz(self, area: QVBoxLayout) -> None:
        self.drop_comments = self._switch(area, tr("Kommentare standardmäßig löschen"), self.opts.drop_comments)

    def _discogs(self, area: QVBoxLayout) -> None:
        self._hint(area, tr("Bleibt ein Album bei MusicBrainz offen, sieht PsyTags mit diesem Token bei Discogs nach. "
                            "Von dort kommen nur Texte, keine Cover."))
        link = QLabel(tr("Discogs-Token (kostenlos unter <a href='https://www.discogs.com/settings/developers'>"
                         "discogs.com/settings/developers</a>):"))
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        area.addWidget(link)
        self.discogs_field = KeyField(config.settings().value("discogs/token", ""), lambda key: discogs.verify_token(key))
        self.discogs_token = self.discogs_field.input
        area.addWidget(self.discogs_field)

    def _numbers(self, area: QVBoxLayout) -> None:
        self.numbers = NumberFormatEditor()
        self.number_boxes, self.number_sample = self.numbers.boxes, self.numbers.sample
        area.addWidget(self.numbers)

    def _cover(self, area: QVBoxLayout) -> None:
        from ...websources import coverprovider
        providers, problems = coverprovider.discover()
        self.cover_sources = QListWidget()
        self.cover_sources.setObjectName("CoverSources")
        self.cover_sources.setItemDelegate(_SourceDelegate(self.cover_sources))
        self.cover_sources.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.cover_sources.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.cover_sources.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cover_sources.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.cover_sources.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.cover_sources.setToolTip(tr("Zum Sortieren ziehen oder Alt+↑/↓"))
        for name, on in coverprovider.arranged(providers):
            it = QListWidgetItem(name)
            it.setFlags((it.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsDropEnabled)
            it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
            self.cover_sources.addItem(it)
        self.cover_sources.setFixedHeight(self.cover_sources.count() * _SourceDelegate.ROW + 2)
        area.addWidget(self.cover_sources)
        for key, step in (("Alt+Up", -1), ("Alt+Down", 1)):
            QShortcut(QKeySequence(key), self.cover_sources, lambda step=step: self.move_cover_source(step))
        open_folder = QPushButton(tr("Plugin-Ordner öffnen"))
        open_folder.setAutoDefault(False)
        open_folder.clicked.connect(self._open_provider_folder)
        guide = QPushButton(tr("Anleitung für Plugins"))
        guide.setAutoDefault(False)
        guide.clicked.connect(self._open_plugin_guide)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(open_folder)
        buttons.addWidget(guide)
        buttons.addStretch(1)
        area.addLayout(buttons)
        for problem in problems:
            label = QLabel(problem)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {theme.ERROR};")
            area.addWidget(label)

    def move_cover_source(self, step: int) -> None:
        row = self.cover_sources.currentRow()
        if row < 0 or not 0 <= row + step < self.cover_sources.count():
            return
        self.cover_sources.insertItem(row + step, self.cover_sources.takeItem(row))
        self.cover_sources.setCurrentRow(row + step)

    def _open_plugin_guide(self) -> None:
        from .. import help as uihelp
        uihelp.HelpDialog(self, "plugins").exec()

    @staticmethod
    def _open_provider_folder() -> None:
        import os
        from ...websources import coverprovider
        os.makedirs(coverprovider.folder(), exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(coverprovider.folder()))

    def _genres(self, area: QVBoxLayout) -> None:
        s = config.settings()
        stored = s.value("lastfm/api_key", "")
        self.lastfm_on = self._switch(area, tr("Genres von Last.fm holen"),
                                      s.value("lastfm/enabled", "false") in (True, "true") or not stored)
        link = QLabel(tr("API-Key (kostenlos unter <a href='https://www.last.fm/api/account/create'>"
                         "last.fm/api/account/create</a>):"))
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        area.addWidget(link)
        self.lastfm_field = KeyField(stored, lambda key: lastfm.verify_key(key))
        self.lastfm_key = self.lastfm_field.input
        area.addWidget(self.lastfm_field)

    def _files(self, area: QVBoxLayout) -> None:
        o = self.opts
        self.id3 = self._segmented((("v2.3 UTF-16", 3), ("v2.4 UTF-8", 4)), o.id3_version, 3)
        self._row(area, tr("ID3v2-Version für MP3"), self.id3)
        self.v1 = self._switch(area, tr("Zusätzlich ID3v1 schreiben"), o.write_id3v1)
        self.subfolders = self._switch(area, tr("Unterordner mit einlesen"), o.subfolders)
        self.autosave = self._switch(area, tr("Tags beim Wechsel der Auswahl speichern"), o.save_on_selection_change)
        self.keep_mtime = self._switch(area, tr("Zeitstempel der Dateien beibehalten"), o.keep_mtime)

    def _program(self, area: QVBoxLayout) -> None:
        o = self.opts
        self.lang = self._segmented((("Deutsch", "de"), ("English", "en")), o.language, "de")
        self._row(area, tr("Sprache"), self.lang)
        self.theme = self._segmented((("Mocha, " + tr("dunkel"), "mocha"), ("Latte, " + tr("hell"), "latte")), o.theme, "mocha")
        self.theme.as_swatches([theme.MOCHA, theme.LATTE])
        area.addWidget(self.theme, 0, Qt.AlignmentFlag.AlignLeft)

    # ------------------------------------------------------------------ values
    def accept(self):
        from ...websources import coverprovider
        coverprovider.save_arrangement([(self.cover_sources.item(i).text(),
                                         self.cover_sources.item(i).checkState() == Qt.CheckState.Checked)
                                        for i in range(self.cover_sources.count())])
        self.numbers.format().save()
        s = config.settings()
        key = self.lastfm_key.text().strip()
        s.setValue("lastfm/api_key", key)
        s.setValue("lastfm/enabled", self.lastfm_on.isChecked() and bool(key))
        s.setValue("discogs/token", self.discogs_token.text().strip())
        o = self.opts
        o.language = self.lang.currentData()
        o.theme = self.theme.currentData()
        o.save_on_selection_change = self.autosave.isChecked()
        o.keep_mtime = self.keep_mtime.isChecked()
        o.subfolders = self.subfolders.isChecked()
        o.id3_version = self.id3.currentData()
        o.write_id3v1 = self.v1.isChecked()
        o.drop_comments = self.drop_comments.isChecked()
        o.mood_level = self.mood_level.currentData()
        super().accept()
