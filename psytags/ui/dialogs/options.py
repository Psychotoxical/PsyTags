"""Options dialog, column customization and tag panel customization."""
from __future__ import annotations

import copy

from PySide6.QtCore import QEvent, QRect, QSize, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                               QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QScrollArea, QSpinBox, QStackedWidget, QStyle, QStyledItemDelegate,
                               QVBoxLayout, QWidget)

from ... import config
from ...config import Column, Options, PanelField
from ...i18n import tr
from .. import theme
from ..controls import SWITCH_SIZE, NumberFormatEditor, Segmented, Switch, add_row, add_switch, paint_switch
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
            li = QListWidgetItem(tr(it.name).replace("&", ""))
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
        self.name.setText(tr(c.name))
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
        if self.name.text() != tr(c.name):      # a default name stays German, so it follows the language
            c.name = self.name.text()
        c.value, c.field, c.sort = self.value.text(), self.field.text(), self.sort.text()
        c.numeric = self.numeric.isChecked()
        self.list.item(r).setText(tr(c.name).replace("&", ""))

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
        from .. import statusbox
        self.status_box = QCheckBox(tr("Statusmeldungen als Kasten im Tag-Panel zeigen"))
        self.status_box.setChecked(statusbox.enabled(config.settings()))
        self.form.addRow(self.status_box)
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
        self.name.setText(tr(f.name))
        self.value.setEditText(f.value)
        fracs = [1, 1 / 2, 1 / 3, 1 / 4]
        self.size.setCurrentIndex(min(range(4), key=lambda i: abs(fracs[i] - f.fraction)))
        self._loading = False

    def _store(self, *_):
        r = self.list.currentRow()
        if self._loading or r < 0:
            return
        f = self.items[r]
        if self.name.text() != tr(f.name):
            f.name = self.name.text()
        f.value = self.value.currentText().upper()
        f.size = (self.size.currentIndex() + 1) if f.version == 0 else 12 // (self.size.currentIndex() + 1)
        self.list.item(r).setText(tr(f.name).replace("&", ""))

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
    """Four pages behind cards: the steps of the automatic run, accounts and sources, files, program."""
    PAGES = ("automatic", "sources", "files", "program")
    STEPS = ("moods", "musicbrainz", "numbers", "cover", "genres")
    # where every part lives; callers may open the dialog at any of them
    SECTION_PAGE = {**{s: "automatic" for s in STEPS}, "discogs": "sources", "lastfm": "sources",
                    "plugins": "sources", "files": "files", "program": "program"}

    def __init__(self, opts: Options, parent=None, section: str = ""):
        super().__init__(parent)
        self.opts = copy.deepcopy(opts)
        self.setWindowTitle(tr("Optionen"))
        self.resize(860, 720)
        self.setMinimumSize(720, 480)
        self._blocks: dict[str, QWidget] = {}
        self._tabs: dict[str, QPushButton] = {}
        self._scrolls: dict[str, QScrollArea] = {}
        self._wanted = section if section in self.SECTION_PAGE or section in self.PAGES else ""
        self._current = self._wanted or self.PAGES[0]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header())
        self.stack = QStackedWidget()
        fill = {"automatic": self._automatic, "sources": self._sources, "files": self._files_page,
                "program": self._program_page}
        for key in self.PAGES:
            page = QWidget()
            page.setObjectName("OptionsPage")
            column = QVBoxLayout(page)
            column.setContentsMargins(30, 16, 30, 16)
            column.setSpacing(12)
            fill[key](column)
            column.addStretch(1)
            scroll = QScrollArea()
            scroll.setWidget(page)
            scroll.setWidgetResizable(True)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self._scrolls[key] = scroll
            self.stack.addWidget(scroll)
        root.addWidget(self.stack, 1)
        root.addWidget(self._footer())
        self._show_page(self.page_of(self._current))
        remember(self, "options3")

    # ------------------------------------------------------------------ frame
    def _header(self) -> QWidget:
        head = QWidget()
        head.setObjectName("OptionsHeader")
        column = QVBoxLayout(head)
        column.setContentsMargins(30, 18, 30, 14)
        column.setSpacing(12)
        title = QLabel(tr("Optionen"))
        title.setObjectName("DialogTitle")
        column.addWidget(title)
        row = QHBoxLayout()
        row.setSpacing(8)
        group = QButtonGroup(head)
        texts = {"automatic": (tr("Automatik"), tr("Schritte des automatischen Laufs")),
                 "sources": (tr("Konten und Quellen"), tr("Schlüssel, Token, Cover-Plugins")),
                 "files": (tr("Dateien"), tr("Lesen und Schreiben")),
                 "program": (tr("Programm"), tr("Sprache und Design"))}
        for key in self.PAGES:
            name, what = texts[key]
            tab = QPushButton()
            tab.setObjectName("PageCard")
            tab.setCheckable(True)
            tab.setAutoDefault(False)
            tab.setCursor(Qt.CursorShape.PointingHandCursor)
            tab.setAccessibleName(name)
            inner = QVBoxLayout(tab)
            inner.setContentsMargins(12, 9, 12, 9)
            inner.setSpacing(2)
            heading = QLabel(name)
            heading.setObjectName("StepTitle")
            inner.addWidget(heading)
            note = QLabel(what)
            note.setObjectName("StepKey")
            inner.addWidget(note)
            tab.clicked.connect(lambda _=False, key=key: self.show_section(key))
            group.addButton(tab)
            row.addWidget(tab, 1)
            self._tabs[key] = tab
        column.addLayout(row)
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

    def _card(self, column: QVBoxLayout, key: str, title: str, what: str = "", number: str = "",
              switch: bool | None = None) -> tuple[QVBoxLayout, Switch | None]:
        """A card with a heading; ``switch`` adds a switch to the heading that turns the
        whole card on or off. Returns the layout for the content and the switch."""
        card = QFrame()
        card.setObjectName("OptionsCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 12, 16, 14)
        box.setSpacing(10)
        head = QHBoxLayout()
        head.setSpacing(10)
        if number:
            badge = QLabel(number)
            badge.setObjectName("StepNumber")
            head.addWidget(badge)
        heading = QLabel(title)
        heading.setObjectName("StepTitle")
        head.addWidget(heading)
        if what:
            note = QLabel(what)
            note.setObjectName("StepKey")
            head.addWidget(note)
        head.addStretch(1)
        on = None
        if switch is not None:
            on = Switch()
            on.setChecked(switch)
            on.setAccessibleName(title)
            head.addWidget(on)
        box.addLayout(head)
        body = QWidget()
        area = QVBoxLayout(body)
        area.setContentsMargins(0, 0, 0, 0)
        area.setSpacing(12)
        box.addWidget(body)
        if on is not None:
            on.toggled.connect(body.setEnabled)
            body.setEnabled(on.isChecked())
        column.addWidget(card)
        self._blocks[key] = card
        return area, on

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
        return list(self.SECTION_PAGE)

    def page_of(self, key: str) -> str:
        return key if key in self.PAGES else self.SECTION_PAGE[key]

    def current_page(self) -> str:
        return self.PAGES[self.stack.currentIndex()]

    def current_section(self) -> str:
        return self._current

    def show_section(self, key: str) -> None:
        """Show the page of ``key``; a part of a page is scrolled into view."""
        self._current = key
        page = self.page_of(key)
        self._show_page(page)
        if key in self._blocks:
            self._scrolls[page].verticalScrollBar().setValue(self._blocks[key].y() - 16)

    def _show_page(self, page: str) -> None:
        self.stack.setCurrentIndex(self.PAGES.index(page))
        self._tabs[page].setChecked(True)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.lastfm_field.check()
        self.discogs_field.check()
        if self._wanted:
            key, self._wanted = self._wanted, ""
            QTimer.singleShot(0, lambda: self.show_section(key))    # the page has its final layout then

    # ------------------------------------------------------------------ pages
    def _automatic(self, column: QVBoxLayout) -> None:
        self._hint(column, tr("Diese Schritte laufen bei „Alle Alben automatisch“ in dieser Reihenfolge, Nummern "
                              "und Cover auch nach einer manuellen Suche. Was Sie nicht brauchen, schalten Sie aus."))
        o = self.opts
        area, self.auto_moods = self._card(column, "moods", tr("Moods"), tr("Analyse aus dem Audio"), "1", o.auto_moods)
        self.mood_level = self._segmented(((tr("Wenige"), "few"), (tr("Normal"), "normal"), (tr("Viele"), "many")),
                                          o.mood_level, "normal")
        self._row(area, tr("Menge der Moods"), self.mood_level)
        self._hint(area, tr("Gilt für neue Analysen. Vorhandene Moods ändern sich erst, wenn die Songs neu analysiert werden."))

        area, _ = self._card(column, "musicbrainz", tr("MusicBrainz"), tr("Tags aus der Datenbank"), "2")
        self.drop_comments = self._switch(area, tr("Kommentare standardmäßig löschen"), o.drop_comments)
        self.date_choice = self._segmented(((tr("Nur das Jahr"), "year"), (tr("Volles Datum"), "date")),
                                           "year" if o.year_only else "date", "year")
        self._row(area, tr("Erscheinungsdatum"), self.date_choice)
        self._hint(area, tr("Gilt für MusicBrainz und Discogs. „Nur das Jahr“ schreibt 2026 statt 2026-10-11."))
        self.prefer_digital = self._switch(area, tr("Digitale Ausgaben bevorzugen"), o.prefer_digital)
        self._hint(area, tr("Passen mehrere Ausgaben gleich gut, nimmt PsyTags die digitale. Ausgeschaltet zählt nur, "
                            "wie gut Titel und Längen passen. Bleibt ein Album offen, springt Discogs ein, "
                            "wenn unter „Konten und Quellen“ ein Token steht."))

        area, self.auto_numbers = self._card(column, "numbers", tr("Nummern"), tr("Format von Track und Disc"), "3",
                                             o.auto_numbers)
        self._hint(area, tr("Schreibt Track- und Discnummern, sobald jede Datei ihren Track gefunden hat."))
        self.numbers = NumberFormatEditor()
        self.number_boxes, self.number_sample = self.numbers.boxes, self.numbers.sample
        area.addWidget(self.numbers)

        area, self.auto_cover = self._card(column, "cover", tr("Cover"),
                                           tr("Die erste Quelle, die ein Cover liefert, gewinnt."), "4", o.auto_cover)
        self._cover_list(area)
        self.replace_covers = self._switch(area, tr("Vorhandene Cover ersetzen"), o.replace_covers)
        self._hint(area, tr("Ausgeschaltet behalten Alben, die schon ein Cover haben, ihr Cover. "
                            "Holen Sie ein Cover von Hand, wird es immer ersetzt."))
        self.cover_min = QSpinBox()
        self.cover_min.setRange(0, 10000)
        self.cover_min.setSingleStep(100)
        self.cover_min.setSuffix(" px")
        self.cover_min.setValue(_cover_min_size())
        self._row(area, tr("Mindestgröße (0 = jede Größe)"), self.cover_min)

        s = config.settings()
        stored = s.value("lastfm/api_key", "")
        area, self.lastfm_on = self._card(column, "genres", tr("Genres"), tr("Von Last.fm"), "5",
                                          s.value("lastfm/enabled", "false") in (True, "true") or not stored)
        self._hint(area, tr("Braucht den API-Key von Last.fm unter „Konten und Quellen“."))

    def _cover_list(self, area: QVBoxLayout) -> None:
        from ...websources import coverprovider
        providers, self._provider_problems = coverprovider.discover()
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

    def _sources(self, column: QVBoxLayout) -> None:
        area, _ = self._card(column, "discogs", tr("Discogs"), tr("Wenn MusicBrainz ein Album offen lässt"))
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

        area, _ = self._card(column, "lastfm", tr("Last.fm"), tr("Genres"))
        link = QLabel(tr("API-Key (kostenlos unter <a href='https://www.last.fm/api/account/create'>"
                         "last.fm/api/account/create</a>):"))
        link.setOpenExternalLinks(True)
        link.setWordWrap(True)
        area.addWidget(link)
        self.lastfm_field = KeyField(config.settings().value("lastfm/api_key", ""), lambda key: lastfm.verify_key(key))
        self.lastfm_key = self.lastfm_field.input
        area.addWidget(self.lastfm_field)

        area, _ = self._card(column, "plugins", tr("Cover-Plugins"), tr("Weitere Cover-Quellen"))
        self._hint(area, tr("Ein Plugin ist eine kleine Datei im Plugin-Ordner. Seine Quelle erscheint danach "
                            "in der Liste der Cover-Quellen unter „Automatik“."))
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
        for problem in self._provider_problems:
            label = QLabel(problem)
            label.setWordWrap(True)
            label.setStyleSheet(f"color: {theme.ERROR};")
            area.addWidget(label)

    def _files_page(self, column: QVBoxLayout) -> None:
        o = self.opts
        area, _ = self._card(column, "files", tr("Dateien"), tr("Lesen und Schreiben"))
        self.id3 = self._segmented((("v2.3 UTF-16", 3), ("v2.4 UTF-8", 4)), o.id3_version, 3)
        self._row(area, tr("ID3v2-Version für MP3"), self.id3)
        self.v1 = self._switch(area, tr("Zusätzlich ID3v1 schreiben"), o.write_id3v1)
        self.subfolders = self._switch(area, tr("Unterordner mit einlesen"), o.subfolders)
        self.autosave = self._switch(area, tr("Tags beim Wechsel der Auswahl speichern"), o.save_on_selection_change)
        self.keep_mtime = self._switch(area, tr("Änderungsdatum der Dateien nicht anfassen"), o.keep_mtime)

    def _program_page(self, column: QVBoxLayout) -> None:
        o = self.opts
        area, _ = self._card(column, "program", tr("Programm"), tr("Sprache und Design"))
        self.lang = self._segmented((("Deutsch", "de"), ("English", "en")), o.language, "de")
        self._row(area, tr("Sprache"), self.lang)
        self.theme = self._segmented((("Mocha, " + tr("dunkel"), "mocha"), ("Latte, " + tr("hell"), "latte")), o.theme, "mocha")
        self.theme.as_swatches([theme.MOCHA, theme.LATTE])
        area.addWidget(self.theme, 0, Qt.AlignmentFlag.AlignLeft)

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
        s.setValue("tagsources/cover_min_size", self.cover_min.value())
        o = self.opts
        o.language = self.lang.currentData()
        o.theme = self.theme.currentData()
        o.save_on_selection_change = self.autosave.isChecked()
        o.keep_mtime = self.keep_mtime.isChecked()
        o.subfolders = self.subfolders.isChecked()
        o.id3_version = self.id3.currentData()
        o.write_id3v1 = self.v1.isChecked()
        o.drop_comments = self.drop_comments.isChecked()
        o.year_only = self.date_choice.currentData() == "year"
        o.mood_level = self.mood_level.currentData()
        o.auto_moods = self.auto_moods.isChecked()
        o.auto_numbers = self.auto_numbers.isChecked()
        o.auto_cover = self.auto_cover.isChecked()
        o.prefer_digital = self.prefer_digital.isChecked()
        o.replace_covers = self.replace_covers.isChecked()
        super().accept()


def _cover_min_size() -> int:
    try:
        return int(config.settings().value("tagsources/cover_min_size", 1000))
    except (TypeError, ValueError):
        return 1000
