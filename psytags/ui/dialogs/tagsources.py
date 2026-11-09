"""Tag source dialogs: search, result list, adjust tag information."""
from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QUrl, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDesktopServices, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFormLayout, QHBoxLayout, QHeaderView, QLabel,
                               QListWidget, QListWidgetItem, QPushButton, QSplitter, QStyledItemDelegate,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from ..theme import ERROR, ICON_POSITIVE, WARNING, WARNING_BACKGROUND

from ... import config, script
from ...i18n import tr
from ...websources import albumauto
from ...websources.albummatch import seconds as _seconds
from ..persist import remember


class _Sig(QObject):
    done = Signal(object)


class _Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn, self.sig = fn, _Sig()

    def run(self):
        try:
            self.sig.done.emit(self.fn())
        except Exception:
            self.sig.done.emit(None)


def run_async(fn, cb):
    job = _Job(fn)
    job.sig.done.connect(cb)
    QThreadPool.globalInstance().start(job)
    return job


def _buttons(dlg, back=False, ok_text=None):
    """[< Back] [Next >] [Cancel]: Back sits directly left of Next/Save. Both get the
    accept role only for their place in the layout (the first accept button comes
    first); each is wired to its own result instead of the box's accepted().
    The box needs the dialog as parent right away: setDefault() only registers Next as
    the dialog's default button then; otherwise Qt picks e.g. "Vorschau" on show."""
    bb = QDialogButtonBox(dlg)
    if back:
        b = bb.addButton(tr("< &Zurück").replace("&", ""), QDialogButtonBox.ButtonRole.AcceptRole)
        b.setAutoDefault(False)
        b.clicked.connect(lambda: dlg.done(2))
    ok = QPushButton((ok_text or tr("&Weiter >")).replace("&", ""))
    ok.setObjectName("DialogPrimary")             # before the box lays it out: the style is cached then
    bb.addButton(ok, QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setDefault(True)
    ok.clicked.connect(dlg.accept)
    bb.addButton(tr("Abbrechen"), QDialogButtonBox.ButtonRole.RejectRole)
    bb.rejected.connect(dlg.reject)
    return bb


def _source_name(source) -> str:
    return source.name.replace("&", "").replace("#", " - ")


def _roomy(layout: QVBoxLayout) -> None:
    layout.setContentsMargins(22, 20, 22, 18)
    layout.setSpacing(14)


def _heading(title: str, subtitle: str = "") -> tuple[QWidget, QLabel, QLabel]:
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 0, 0, 0)
    column.setSpacing(2)
    head = QLabel(title)
    head.setObjectName("DialogTitle")
    head.setWordWrap(True)
    sub = QLabel(subtitle)
    sub.setObjectName("DialogSubtitle")
    sub.setWordWrap(True)
    column.addWidget(head)
    column.addWidget(sub)
    return box, head, sub


def _as_list(view) -> None:
    """Lists in these dialogs look like the file list: calm rows, no stripes."""
    view.setObjectName("DialogList")
    view.setAlternatingRowColors(False)


class SearchDialog(QDialog):
    def __init__(self, source, tracks, parent=None, values: list[str] | None = None):
        super().__init__(parent)
        self.source = source
        self.setWindowTitle(_source_name(source))
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        _roomy(lay)
        lay.addWidget(_heading(_source_name(source), tr("Welches Album soll gesucht werden?"))[0])
        self.inputs: list[QComboBox] = []
        s = config.settings()
        for i, f in enumerate(source.search_fields):
            c = QComboBox()
            c.setEditable(True)
            hist = config.string_list(s, f"tagsources/history/{f.label}")
            c.addItems(hist)
            if values is not None and i < len(values):
                c.setEditText(values[i])
            else:
                c.setEditText(script.format(f.fmt, tracks[0]).strip() if tracks else "")
            field = QVBoxLayout()
            field.setSpacing(4)
            label = QLabel(f.label.replace("&", ""))
            label.setObjectName("FieldLabel")
            field.addWidget(label)
            field.addWidget(c)
            lay.addLayout(field)
            self.inputs.append(c)
        lay.addWidget(_buttons(self, ok_text=tr("&Suchen")))
        remember(self, "ts_search")

    def values(self) -> list[str]:
        s = config.settings()
        out = []
        for f, c in zip(self.source.search_fields, self.inputs):
            v = c.currentText()
            hist = [x for x in config.string_list(s, f"tagsources/history/{f.label}") if x != v]
            s.setValue(f"tagsources/history/{f.label}", [v] + hist[:19])
            out.append(v)
        return out


class ResultsDialog(QDialog):
    """List of index results (one row per release)."""

    def __init__(self, source, rows: list[dict[str, str]], parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle(f"{tr('Suchergebnisse')} - {_source_name(source)}")
        self.resize(1040, 560)
        cols = [c for c in source.index_columns if not c.startswith("_")]
        self.cols = cols
        self._hits = tr("{1} Treffer", len(rows))
        self._lead = _source_name(source)
        self._note = ""
        lay = QVBoxLayout(self)
        _roomy(lay)
        box, self.title_label, self.subtitle_label = _heading(tr("Suchergebnisse"))
        lay.addWidget(box)
        self._show_subtitle()
        split = QSplitter()
        split.setHandleWidth(14)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(cols)
        self.tree.setRootIsDecorated(False)
        self.tree.setSortingEnabled(True)
        self.tree.setUniformRowHeights(True)
        _as_list(self.tree)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for i, r in enumerate(rows):
            it = QTreeWidgetItem([r.get(c, "") for c in cols])
            it.setData(0, Qt.ItemDataRole.UserRole, i)
            self.tree.addTopLevelItem(it)
        for i in range(len(cols)):
            self.tree.resizeColumnToContents(i)
            self.tree.setColumnWidth(i, min(self.tree.columnWidth(i), 260))
        self.tree.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.tree.itemDoubleClicked.connect(lambda *_: self.accept())
        self.tree.currentItemChanged.connect(self._current)
        split.addWidget(self.tree)
        side = QWidget()
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(10)
        self.cover = QLabel()
        self.cover.setObjectName("CoverBox")
        self.cover.setFixedSize(220, 220)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sl.addWidget(self.cover)
        self.preview_btn = QPushButton(tr("&Vorschau").replace("&", ""))
        self.preview_btn.clicked.connect(self._preview)
        sl.addWidget(self.preview_btn)
        sl.addStretch(1)
        split.addWidget(side)
        split.setStretchFactor(0, 1)
        lay.addWidget(split, 1)
        lay.addWidget(_buttons(self, back=True))
        self._jobs = []
        remember(self, "ts_results/" + source.name.replace("/", "_"))
        if rows:
            self.tree.setCurrentItem(self.tree.topLevelItem(0))

    def _show_subtitle(self) -> None:
        self.subtitle_label.setText(" · ".join(p for p in (self._lead, self._hits, self._note) if p))

    def set_heading(self, title: str, lead: str) -> None:
        self.setWindowTitle(title)
        self.title_label.setText(title)
        self._lead = lead
        self._show_subtitle()

    def add_note(self, note: str) -> None:
        self._note = note
        self._show_subtitle()

    def selected(self) -> dict[str, str] | None:
        it = self.tree.currentItem()
        return self.rows[it.data(0, Qt.ItemDataRole.UserRole)] if it else None

    def _preview(self):
        r = self.selected()
        if r and r.get("_preview"):
            QDesktopServices.openUrl(QUrl(r["_preview"]))

    def _current(self, *_):
        r = self.selected()
        self.preview_btn.setEnabled(bool(r and r.get("_preview")))
        self.cover.clear()
        url = (r or {}).get("_coverurl", "")
        if not url:
            return
        from ...websources.http import fetch_bytes

        def done(data, want=url):
            cur = self.selected()
            if data and cur and cur.get("_coverurl") == want:
                img = QImage.fromData(data)
                if not img.isNull():
                    self.cover.setPixmap(QPixmap.fromImage(img).scaled(
                        218, 218, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
        self._jobs.append(run_async(lambda: fetch_bytes(url), done))


class AdjustDialog(QDialog):
    """Adjust a tag source result: choose fields, align tracks with files."""

    def __init__(self, album, tracks, cover: bytes | None = None, parent=None):
        super().__init__(parent)
        self.album = album
        self.cover = cover
        # Fewer files than tracks: empty slots ("< keine Zuordnung >") fill the rest. They
        # can be moved like files, e.g. to the top when the first song is missing.
        # Files are placed by their titles; what has no track stands behind the last one.
        self.files = albumauto.prealign(list(tracks), album)
        self.setWindowTitle(tr("Tag-Informationen anpassen"))
        self.resize(1180, 660)
        lay = QVBoxLayout(self)
        _roomy(lay)
        about = " · ".join(v for v in (album.value("ALBUM", 0), album.value("ALBUMARTIST", 0),
                                       album.value("YEAR", 0)[:4]) if v)
        lay.addWidget(_heading(tr("Tag-Informationen anpassen"), about)[0])
        split = QSplitter()
        split.setHandleWidth(14)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)
        fields_label = QLabel(tr("Felder:"))
        fields_label.setObjectName("FieldLabel")
        ll.addWidget(fields_label)
        self.fields = QListWidget()
        _as_list(self.fields)
        s = config.settings()
        disabled = set(config.string_list(s, "tagsources/disabled_fields"))
        for name in album.fields:
            shown = tr("< mehrere Werte >") if name in album.per_track else album.value(name, 0)
            it = QListWidgetItem(f"{name}: {shown}")
            it.setData(Qt.ItemDataRole.UserRole, name)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked if name in disabled else Qt.CheckState.Checked)
            self.fields.addItem(it)
        ll.addWidget(self.fields, 1)
        self.cover_box = QCheckBox(tr("Cover"))
        self.cover_lbl = QLabel()
        self.cover_lbl.setObjectName("CoverBox")
        self.cover_lbl.setFixedSize(160, 160)
        self.cover_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if cover:
            img = QImage.fromData(cover)
            if not img.isNull():
                self.cover_lbl.setPixmap(QPixmap.fromImage(img).scaled(
                    158, 158, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.cover_box.setChecked(bool(cover))      # always on; unchecking applies to this import only
        self.cover_box.setEnabled(bool(cover))
        ll.addWidget(self.cover_box)
        ll.addWidget(self.cover_lbl)
        split.addWidget(left)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        explain = QLabel(tr("Links die Tracks der Quelle, rechts Ihre Dateien. Dateien per "
                            "Drag & Drop oder Alt+↑/↓ in die passende Zeile schieben:"))
        explain.setObjectName("DialogSubtitle")
        explain.setWordWrap(True)
        rl.addWidget(explain)
        pair = QSplitter()
        pair.setHandleWidth(14)
        self.source_table = _TrackTable([tr("Track"), tr("Titel (Quelle)"), tr("Länge")], 1)
        self.source_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table = _TrackTable([tr("Länge"), tr("Datei")], 1)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.reordered.connect(self._reordered)
        pair.addWidget(self.source_table)
        pair.addWidget(self.table)
        pair.setSizes([500, 500])
        # Same row, same scroll position on both sides.
        for a, b in ((self.source_table, self.table), (self.table, self.source_table)):
            a.verticalScrollBar().valueChanged.connect(b.verticalScrollBar().setValue)
            a.currentItemChanged.connect(lambda cur, _p, a=a, b=b: self._sync_current(a, b, cur))
        rl.addWidget(pair, 1)
        row = QHBoxLayout()
        for text, d, key in ((tr("Nach &oben"), -1, "Alt+Up"), (tr("Nach &unten"), 1, "Alt+Down")):
            b = QPushButton(text.replace("&", ""))
            b.clicked.connect(lambda _=False, d=d: self._move(d))
            row.addWidget(b)
            QShortcut(QKeySequence(key), self, lambda d=d: self._move(d))
        row.addStretch(1)
        self.hint = QLabel()
        self.hint.setStyleSheet(f"color: {WARNING};")
        row.addWidget(self.hint)
        rl.addLayout(row)
        split.addWidget(right)
        split.setStretchFactor(1, 3)
        split.setSizes([300, 860])
        lay.addWidget(split, 1)
        lay.addWidget(_buttons(self, back=True, ok_text=tr("&Speichern")))
        self._fill()
        remember(self, "ts_adjust")

    def _fill(self, sel=-1):
        warn = QBrush(QColor(WARNING_BACKGROUND))
        self.source_table.clear()
        self.table.clear()
        n_src = max(1, self.album.tracks)
        mismatches = 0
        for i in range(max(n_src, len(self.files))):
            src_len = _seconds(self.album.lengths[i]) if i < len(self.album.lengths) else None
            if i < n_src:
                self.source_table.addTopLevelItem(QTreeWidgetItem([
                    self.album.value("TRACK", i) or str(i + 1), self.album.value("TITLE", i),
                    _fmt_len(self.album.lengths[i]) if i < len(self.album.lengths) else ""]))
            else:                                  # more files than tracks: empty source row
                self.source_table.addTopLevelItem(QTreeWidgetItem(["", "", ""]))
            if i < len(self.files):
                t = self.files[i]
                file_len = t.data.info.length if t is not None else 0
                it = QTreeWidgetItem([_fmt_secs(file_len) if file_len else "",
                                      t.filename if t is not None else tr("< keine Zuordnung >")])
                if t is None:
                    it.setForeground(1, QBrush(self.palette().color(self.palette().ColorRole.PlaceholderText)))
                it.setData(0, Qt.ItemDataRole.UserRole, i)
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
                self.table.addTopLevelItem(it)
                # Lengths more than 3 s apart: this file probably belongs to another track.
                if src_len is not None and file_len and abs(src_len - file_len) > 3:
                    mismatches += 1
                    for tbl, item in ((self.source_table, self.source_table.topLevelItem(i)),
                                      (self.table, it)):
                        for c in range(tbl.columnCount()):
                            item.setBackground(c, warn)
        hints = []
        n_files = sum(1 for t in self.files if t is not None)
        if self.album.tracks and self.album.tracks != n_files:
            hints.append(tr("{1} Tracks / {2} Dateien", n_src, n_files))
        if mismatches:
            hints.append(tr("{1} Längen passen nicht", mismatches))
        self.hint.setText(" · ".join(hints))
        if 0 <= sel < len(self.files):
            self.table.setCurrentItem(self.table.topLevelItem(sel))

    def _sync_current(self, src, dst, cur):
        r = src.indexOfTopLevelItem(cur) if cur is not None else -1
        if 0 <= r < dst.topLevelItemCount() and dst.indexOfTopLevelItem(dst.currentItem()) != r:
            dst.blockSignals(True)
            dst.setCurrentItem(dst.topLevelItem(r))
            dst.blockSignals(False)

    def _reordered(self):
        order = [self.table.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                 for i in range(self.table.topLevelItemCount())]
        cur = self.table.indexOfTopLevelItem(self.table.currentItem())
        self.files = [self.files[i] for i in order]
        self._fill(cur)

    def _move(self, d):
        r = self.table.indexOfTopLevelItem(self.table.currentItem())
        if 0 <= r < len(self.files) and 0 <= r + d < len(self.files):
            self.files[r], self.files[r + d] = self.files[r + d], self.files[r]
            self._fill(r + d)

    def enabled_fields(self) -> list[str]:
        out, off = [], []
        for i in range(self.fields.count()):
            it = self.fields.item(i)
            (out if it.checkState() == Qt.CheckState.Checked else off).append(
                it.data(Qt.ItemDataRole.UserRole))
        s = config.settings()
        s.setValue("tagsources/disabled_fields", off)
        return out

    def plan(self) -> list[tuple[object, dict[str, str]]]:
        """(file, {field: value}) in the aligned order. Files beyond the number of
        tracks get nothing; empty per-track entries leave the field untouched."""
        names = self.enabled_fields()
        out = []
        n = self.album.tracks or len(self.files)
        for i, t in enumerate(self.files[:n]):
            if t is None:                          # "< keine Zuordnung >": track without file
                continue
            vals = {k: self.album.value(k, i) for k in names}
            out.append((t, {k: v for k, v in vals.items() if v != "" or k not in self.album.per_track}))
        return out

    def leftovers(self) -> list:
        """Files behind the last track: they get no tags."""
        n = self.album.tracks or len(self.files)
        placed = [t for t in self.files[:n] if t is not None]
        folders = {t.folder for t in placed}
        albums = {tuple(t.get("ALBUM")) for t in placed}
        return [t for t in self.files[n:]           # other albums in the selection are no leftovers
                if t is not None and t.folder in folders and tuple(t.get("ALBUM")) in albums]

    def use_cover(self) -> bool:
        return bool(self.cover) and self.cover_box.isChecked()


class _TrackTable(QTreeWidget):
    """Flat track list for the adjust dialog; ``reordered`` fires after a drag & drop."""
    reordered = Signal()

    def __init__(self, headers: list[str], stretch: int):
        super().__init__()
        self.setHeaderLabels(headers)
        self.setRootIsDecorated(False)
        _as_list(self)
        self.setUniformRowHeights(True)
        self.header().setSectionResizeMode(stretch, QHeaderView.ResizeMode.Stretch)
        self.invisibleRootItem().setFlags(self.invisibleRootItem().flags()
                                          | Qt.ItemFlag.ItemIsDropEnabled)

    def dropEvent(self, e):
        super().dropEvent(e)
        self.reordered.emit()


def _fmt_secs(secs: float) -> str:
    return f"{int(secs) // 60}:{int(secs) % 60:02d}"


def _fmt_len(v: str) -> str:
    v = v.strip()
    if v.isdigit():
        secs = int(v) / 1000 if int(v) >= 6000 else int(v)
        return f"{int(secs) // 60}:{int(secs) % 60:02d}"
    return v


class DiscogsTokenDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Discogs-Zugang"))
        lay = QVBoxLayout(self)
        lbl = QLabel(tr("Discogs verlangt für Suchen eine Anmeldung. Erzeugen Sie unter "
                        "<a href='https://www.discogs.com/settings/developers'>discogs.com → "
                        "Einstellungen → Developers</a> einen persönlichen Zugangstoken und fügen "
                        "Sie ihn hier ein."))
        lbl.setOpenExternalLinks(True)
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        from PySide6.QtWidgets import QLineEdit
        self.token = QLineEdit(config.settings().value("tagsources/discogs_token", ""))
        lay.addWidget(self.token)
        lay.addWidget(_buttons(self, ok_text=tr("OK")))

    def accept(self):
        config.settings().setValue("tagsources/discogs_token", self.token.text().strip())
        super().accept()


def outcome_mark(value: str | None) -> tuple[str, str | None]:
    """(mark, color) of a step: crossed box worked, empty box failed, dash did not run."""
    if value is None:
        return "–", None
    return ("☒", ICON_POSITIVE) if value == "" else ("☐", ERROR)


def summary_action(entry, column: int | None) -> str:
    """What opening a summary row does: "manual", "cover", "genres" or "" for nothing.
    A click on the cover or genre box only concerns that step."""
    if not entry.ok:
        return "manual"
    if column == 2:
        return "cover" if entry.cover else ""
    if column == 3:
        return "genres" if entry.genres else ""
    return "cover" if entry.cover else "genres" if entry.genres else ""


class _EvenRows(QStyledItemDelegate):
    """Every row of the summary is as high as one with a button."""

    def sizeHint(self, option, index):
        size = super().sizeHint(option, index)
        size.setHeight(30)
        return size


class BatchSummaryDialog(QDialog):
    """Result of "all albums automatically": open albums and files without a track."""

    def __init__(self, entries, trash, parent=None):
        super().__init__(parent)
        self.entries = entries
        self.trash = trash                 # callable(tracks) -> tracks still on disk
        self.chosen = None
        self.action = ""
        done = sum(1 for e in entries if e.ok)
        self.setWindowTitle(tr("Ergebnis des automatischen Laufs"))
        self.resize(900, 600)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("{1} erledigt, {2} offen", done, len(entries) - done)))
        self.table = QTreeWidget()
        self.table.setRootIsDecorated(False)
        self.table.setItemDelegate(_EvenRows(self.table))
        self.table.setHeaderLabels([tr("Album"), tr("Ergebnis"), tr("Cover"), tr("Genres"), tr("Details")])
        for column in range(4):
            self.table.header().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        self.table.header().setStretchLastSection(True)
        for e in sorted(entries, key=lambda x: x.ok):
            it = QTreeWidgetItem([e.title, tr("Erledigt") if e.ok else tr("Offen"), "", "", e.detail])
            it.setData(0, Qt.ItemDataRole.UserRole, e)
            for column, value in ((2, e.cover), (3, e.genres)):
                mark, color = outcome_mark(value)
                it.setText(column, mark)
                it.setTextAlignment(column, Qt.AlignmentFlag.AlignCenter)
                if color:
                    it.setForeground(column, QBrush(QColor(color)))
                if value:
                    it.setToolTip(column, value)
            self.table.addTopLevelItem(it)
            self._add_buttons(it, e)
        self.table.itemDoubleClicked.connect(lambda _it, column: self._open(column))
        lay.addWidget(self.table, 2)
        lay.addWidget(QLabel(tr("Dateien ohne Track (zum Löschen anhaken):")))
        self.left = QListWidget()
        for e in entries:
            for t in e.leftovers:
                it = QListWidgetItem(f"{e.title}: {t.filename}")
                it.setData(Qt.ItemDataRole.UserRole, t)
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                it.setCheckState(Qt.CheckState.Unchecked)
                self.left.addItem(it)
        lay.addWidget(self.left, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, self)
        trash_btn = bb.addButton(tr("In den Papierkorb"), QDialogButtonBox.ButtonRole.ActionRole)
        trash_btn.setEnabled(self.left.count() > 0)
        trash_btn.clicked.connect(self._trash_checked)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        remember(self, "ts_batch_summary2")

    def _add_buttons(self, item, entry) -> None:
        """What can still be done is a button in its own cell."""
        if not entry.ok:
            self._row_button(item, 1, tr("Bearbeiten"), tr("Manuell bearbeiten"))
            return
        for column, failed in ((2, entry.cover), (3, entry.genres)):
            if failed:
                self._row_button(item, column, tr("Nachholen"), failed)

    def _row_button(self, item, column: int, text: str, tip: str) -> None:
        button = QPushButton(text)
        button.setObjectName("RowAction")
        button.setAutoDefault(False)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setToolTip(tip)
        button.clicked.connect(lambda _=False: self._press(item, column))
        item.setText(column, "")
        self.table.setItemWidget(item, column, button)

    def _press(self, item, column: int) -> None:
        self.table.setCurrentItem(item)
        self._open(column)

    def _open(self, column=None):
        it = self.table.currentItem()
        e = it.data(0, Qt.ItemDataRole.UserRole) if it is not None else None
        action = summary_action(e, column) if e is not None else ""
        if action:
            self.chosen, self.action = e, action
            self.accept()

    def _checked(self) -> list:
        return [self.left.item(i) for i in range(self.left.count())
                if self.left.item(i).checkState() == Qt.CheckState.Checked]

    def _trash_checked(self):
        items = self._checked()
        kept = self.trash([it.data(Qt.ItemDataRole.UserRole) for it in items])
        kept_ids = {id(t) for t in kept}
        for it in items:
            t = it.data(Qt.ItemDataRole.UserRole)
            if id(t) not in kept_ids:
                for e in self.entries:
                    e.leftovers[:] = [x for x in e.leftovers if x is not t]
                self.left.takeItem(self.left.row(it))


class SourceSettingsDialog(QDialog):
    """Generic dialog for a .settings schema; values go to sources/settings.json."""

    def __init__(self, schema: dict, parent=None):
        super().__init__(parent)
        from ...i18n import language
        from ...websources import runner
        from PySide6.QtWidgets import QDoubleSpinBox, QFrame, QLineEdit
        self.schema = schema
        loc = {it.get("key"): it for it in schema.get("localizations", {}).get(language(), [])}
        self.setWindowTitle(loc.get(schema.get("key"), schema).get("title", schema.get("title", "")))
        lay = QVBoxLayout(self)
        form = QFormLayout()
        lay.addLayout(form)
        self.user = runner.load_user_settings()
        cur = self.user.get(schema.get("key", ""), {})
        self.widgets = {}
        for s in schema.get("settings", []):
            k, typ = s.get("key"), s.get("type")
            text = loc.get(k, s)
            title = text.get("title", s.get("title", ""))
            desc = text.get("description", s.get("description", ""))
            if typ == "heading":
                lbl = QLabel(f"<b>{title}</b>")
                form.addRow(lbl)
                continue
            if typ == "separator":
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                form.addRow(line)
                if title:
                    form.addRow(QLabel(title))
                continue
            val = cur.get(k, s.get("default"))
            if typ == "bool":
                w = QCheckBox(title)
                w.setChecked(bool(val))
                form.addRow(w)
            elif typ == "number":
                w = QDoubleSpinBox()
                w.setDecimals(0)
                w.setRange(-1e9, 1e9)
                w.setValue(float(val or 0))
                form.addRow(title, w)
            elif s.get("choices"):
                w = QComboBox()
                w.addItems([str(c) for c in s["choices"]])
                w.setCurrentText(str(val))
                form.addRow(title, w)
            else:
                w = QLineEdit(str(val or ""))
                form.addRow(title, w)
            if desc:
                w.setToolTip(desc)
            self.widgets[k] = (typ, w)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def accept(self):
        from ...websources import runner
        vals = {}
        for k, (typ, w) in self.widgets.items():
            if typ == "bool":
                vals[k] = w.isChecked()
            elif typ == "number":
                vals[k] = int(w.value())
            elif isinstance(w, QComboBox):
                vals[k] = w.currentText()
            else:
                vals[k] = w.text()
        self.user[self.schema.get("key", "")] = vals
        runner.save_user_settings(self.user)
        super().accept()
