"""File list (right side of the main window)."""
from __future__ import annotations

import os
import random
import re

from PySide6.QtCore import (QAbstractTableModel, QItemSelection, QItemSelectionModel,
                            QModelIndex, QMimeData, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QKeySequence, QPalette
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileIconProvider,
                               QHeaderView, QStyledItemDelegate, QTableView, QLineEdit)

from .theme import ERROR
from .. import script
from ..i18n import tr
from ..config import Column
from ..filterexpr import compile_filter
from ..albumorder import natural_key as _natural_key, sort_key
from ..track import Track

ICON_COL = 0


class FileListModel(QAbstractTableModel):
    edited = Signal(object, str, str, str)        # track, field, old, new

    def __init__(self, columns: list[Column], parent=None):
        super().__init__(parent)
        self.all: list[Track] = []
        self.rows: list[Track] = []
        self.columns = [c for c in columns if c.enabled]
        self.all_columns = columns
        self.sort_keys: list[tuple[int, bool]] = []     # (column, descending)
        self.filter_text = ""
        self._filter = None
        self._cache: dict[tuple[int, int], str] = {}
        self._icon = QFileIconProvider()
        self._file_icon = None
        self._publish_columns()

    # -- structure -----------------------------------------------------------
    def set_columns(self, columns: list[Column]) -> None:
        self.beginResetModel()
        sort_cols = [(self.columns[c - 1], d) for c, d in self.sort_keys if 0 < c <= len(self.columns)]
        self.all_columns = columns
        self.columns = [c for c in columns if c.enabled]
        self.sort_keys = [(self.columns.index(c) + 1, d) for c, d in sort_cols if c in self.columns]
        self._publish_columns()
        self._cache.clear()
        self.endResetModel()

    def _publish_columns(self) -> None:
        script.COLUMNS[:] = [(c.name.replace("&", ""), c.value) for c in self.columns]

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.columns) + 1

    def column(self, col: int) -> Column | None:
        return self.columns[col - 1] if col > 0 else None

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation != Qt.Orientation.Horizontal:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            return "" if section == ICON_COL else tr(self.columns[section - 1].name).replace("&", "")
        if role == Qt.ItemDataRole.TextAlignmentRole and section > 0:
            c = self.columns[section - 1]
            return (Qt.AlignmentFlag.AlignRight if c.numeric else Qt.AlignmentFlag.AlignLeft) \
                | Qt.AlignmentFlag.AlignVCenter
        return None

    def text(self, row: int, col: int) -> str:
        key = (id(self.rows[row]), col)
        v = self._cache.get(key)
        if v is None:
            v = script.format(self.columns[col - 1].value, self.rows[row])
            self._cache[key] = v
        return v

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        t = self.rows[r]
        if c == ICON_COL:
            if role == Qt.ItemDataRole.DecorationRole:
                if self._file_icon is None:
                    self._file_icon = self._icon.icon(QFileIconProvider.IconType.File)
                return self._file_icon
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.ToolTipRole):
            return self.text(r, c)
        if role == Qt.ItemDataRole.EditRole:
            col = self.columns[c - 1]
            return script.format(col.field, t) if col.field else self.text(r, c)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return (Qt.AlignmentFlag.AlignRight if self.columns[c - 1].numeric
                    else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and t.error:
            return QColor(ERROR)
        return None

    def flags(self, index):
        f = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        if index.column() > 0 and self.columns[index.column() - 1].field.strip():
            f |= Qt.ItemFlag.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role != Qt.ItemDataRole.EditRole or index.column() == 0:
            return False
        col = self.columns[index.column() - 1]
        m = re.fullmatch(r"%([^%]+)%", col.field.strip())
        if not m:
            return False
        t = self.rows[index.row()]
        name = m.group(1).upper()
        old = script.format(col.field, t)
        if value == old:
            return False
        self.edited.emit(t, name, old, value)
        return True

    # -- content -------------------------------------------------------------
    def set_tracks(self, tracks: list[Track]) -> None:
        self.beginResetModel()
        self.all = tracks
        self._cache.clear()
        self._apply()
        self.endResetModel()

    def add_tracks(self, tracks: list[Track]) -> None:
        known = {t.path for t in self.all}
        self.set_tracks(self.all + [t for t in tracks if t.path not in known])

    def sort_album(self, tracks: list[Track], last=()) -> None:
        """Order one album by disc and track on the list places it already occupies; ``last``
        (files without a track) go to the end of its block. Other rows do not move."""
        last_ids = {id(t) for t in last}
        ids = {id(t) for t in tracks} | last_ids
        slots = [i for i, t in enumerate(self.all) if id(t) in ids]
        body = sorted((self.all[i] for i in slots if id(self.all[i]) not in last_ids), key=sort_key)
        tail = sorted((self.all[i] for i in slots if id(self.all[i]) in last_ids), key=sort_key)
        self.beginResetModel()
        for i, t in zip(slots, body + tail):
            self.all[i] = t
        self._cache.clear()
        self._apply()
        self.endResetModel()

    def remove_tracks(self, tracks: list[Track]) -> None:
        ids = {id(t) for t in tracks}
        self.set_tracks([t for t in self.all if id(t) not in ids])

    def refresh_tracks(self, tracks=None) -> None:
        if tracks is None:
            self._cache.clear()
            if self.rows:
                self.dataChanged.emit(self.index(0, 0),
                                      self.index(len(self.rows) - 1, self.columnCount() - 1))
            return
        ids = {id(t) for t in tracks}
        self._cache = {k: v for k, v in self._cache.items() if k[0] not in ids}
        for r, t in enumerate(self.rows):
            if id(t) in ids:
                self.dataChanged.emit(self.index(r, 0), self.index(r, self.columnCount() - 1))

    def _number(self):
        for i, t in enumerate(self.rows, 1):
            t.counter = i
            t.total = len(self.rows)

    def _apply(self) -> None:
        rows = [t for t in self.all if self._filter is None or self._filter(t)]
        if self.sort_keys:
            for col, desc in reversed(self.sort_keys):
                c = self.columns[col - 1] if 0 < col <= len(self.columns) else None
                if c is None:
                    continue
                expr = c.sort or c.value
                if c.numeric:
                    def key(t, e=expr):
                        s = script.format(e, t)
                        m = re.match(r"\s*-?\d+(\.\d+)?", s)
                        return (0, float(m.group(0))) if m else (1, 0.0)
                else:
                    def key(t, e=expr):
                        return _natural_key(script.format(e, t))
                rows.sort(key=key, reverse=desc)
        self.rows = rows
        self._number()

    def set_filter(self, text: str) -> None:
        self.beginResetModel()
        self.filter_text = text
        self._filter = compile_filter(text) if text.strip() else None
        self._apply()
        self.endResetModel()

    def sort_by(self, col: int, add: bool) -> None:
        self.beginResetModel()
        if col == ICON_COL:
            self.sort_keys = []
            random.shuffle(self.rows)
            self._number()
        else:
            # Like Mp3tag the sort is stable on what is shown now: Track, then Disc,
            # then Album gives albums with discs in order and tracks in order.
            self._keep_current_order()
            existing = [i for i, (c, _) in enumerate(self.sort_keys) if c == col]
            if existing and (add or len(self.sort_keys) == 1 or existing[0] == 0):
                i = existing[0]
                c, d = self.sort_keys[i]
                self.sort_keys[i] = (c, not d)
                if not add:
                    self.sort_keys = [self.sort_keys[i]]
            elif add:
                self.sort_keys.append((col, False))
            else:
                self.sort_keys = [(col, False)]
            self._apply()
        self._cache.clear()
        self.endResetModel()

    def _keep_current_order(self) -> None:
        """Make the visible order the base order for the next (stable) sort."""
        order = {id(t): i for i, t in enumerate(self.rows)}
        self.all.sort(key=lambda t: order.get(id(t), 1 << 30))

    def resort(self) -> None:
        self.beginResetModel()
        self._apply()
        self._cache.clear()
        self.endResetModel()

    def move_rows(self, rows: list[int], target: int) -> None:
        """Manual reordering (Alt+Up/Down/PgUp/PgDn, Alt+drag)."""
        self.beginResetModel()
        moving = [self.rows[r] for r in sorted(rows)]
        rest = [t for i, t in enumerate(self.rows) if i not in set(rows)]
        target = max(0, min(target, len(rest)))
        self.rows = rest[:target] + moving + rest[target:]
        self._keep_current_order()
        self.sort_keys = []
        self._number()
        self.endResetModel()

    # -- drag & drop ---------------------------------------------------------
    def supportedDropActions(self):
        return Qt.DropAction.CopyAction | Qt.DropAction.MoveAction

    def mimeTypes(self):
        return ["text/uri-list"]

    def mimeData(self, indexes):
        md = QMimeData()
        rows = sorted({i.row() for i in indexes})
        md.setUrls([QUrl.fromLocalFile(self.rows[r].path) for r in rows])
        return md


class _EditDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        e = QLineEdit(parent)
        e.setFrame(True)
        return e


class FileListView(QTableView):
    files_dropped = Signal(list, bool)      # paths, add (Ctrl held)
    context_menu = Signal(object)
    columns_changed = Signal()              # width or order changed by the user
    sort_changed = Signal()

    def __init__(self, model: FileListModel, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.setItemDelegate(_EditDelegate(self))
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setShowGrid(False)
        self.setAlternatingRowColors(True)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerItem)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setTabKeyNavigation(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(lambda p: self.context_menu.emit(
            self.viewport().mapToGlobal(p)))
        vh = self.verticalHeader()
        vh.setVisible(False)
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        vh.setMinimumSectionSize(1)
        vh.setDefaultSectionSize(self.fontMetrics().height() + 1)
        hh = self.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setHighlightSections(False)
        hh.setStretchLastSection(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionsClickable(True)
        hh.setSortIndicatorShown(True)
        hh.sectionClicked.connect(self._header_clicked)
        hh.sectionResized.connect(self._resized)
        hh.sectionMoved.connect(lambda *_: QTimer.singleShot(0, self._reorder))
        self._applying = False
        self.apply_widths()

    def model(self) -> FileListModel:      # type: ignore[override]
        return super().model()

    def apply_widths(self) -> None:
        m = self.model()
        self._applying = True
        try:
            self.setColumnWidth(ICON_COL, 18)
            self.horizontalHeader().setSectionResizeMode(ICON_COL, QHeaderView.ResizeMode.Fixed)
            for i, c in enumerate(m.columns, 1):
                self.setColumnWidth(i, c.width)
        finally:
            self._applying = False
        self._update_indicator()

    def _resized(self, logical: int, old: int, new: int) -> None:
        m = self.model()
        if self._applying or logical <= 0 or logical > len(m.columns) or new <= 0:
            return
        m.columns[logical - 1].width = new
        self.columns_changed.emit()

    def _reorder(self) -> None:
        """Turn a header drag into a new column order (stored like Mp3tag's columns.ini)."""
        m = self.model()
        hh = self.horizontalHeader()
        n = len(m.columns)
        order = sorted(range(1, n + 1), key=hh.visualIndex)
        if order == list(range(1, n + 1)) and hh.visualIndex(ICON_COL) == ICON_COL:
            return
        new_visible = [m.columns[l - 1] for l in order]
        it = iter(new_visible)
        cols = [next(it) if c.enabled else c for c in m.all_columns]
        hh.blockSignals(True)
        for logical in range(hh.count()):            # back to identity mapping
            v = hh.visualIndex(logical)
            if v != logical:
                hh.moveSection(v, logical)
        hh.blockSignals(False)
        sel = self.selected_tracks()
        m.set_columns(cols)
        self.apply_widths()
        self.select_tracks(sel)
        self.columns_changed.emit()

    def store_widths(self) -> None:
        m = self.model()
        for i, c in enumerate(m.columns, 1):
            c.width = self.columnWidth(i)

    def _update_indicator(self) -> None:
        hh = self.horizontalHeader()
        m = self.model()
        if m.sort_keys:
            c, d = m.sort_keys[0]
            hh.setSortIndicator(c, Qt.SortOrder.DescendingOrder if d else Qt.SortOrder.AscendingOrder)
        else:
            hh.setSortIndicator(-1, Qt.SortOrder.AscendingOrder)

    def _header_clicked(self, section: int) -> None:
        sel = self.selected_tracks()
        add = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)
        self.model().sort_by(section, add)
        self._update_indicator()
        self.select_tracks(sel)
        self.sort_changed.emit()

    # -- selection helpers ---------------------------------------------------
    def selected_rows(self) -> list[int]:
        return sorted(i.row() for i in self.selectionModel().selectedRows())

    def selected_tracks(self) -> list[Track]:
        m = self.model()
        return [m.rows[r] for r in self.selected_rows()]

    def select_tracks(self, tracks: list[Track], current: Track | None = None) -> None:
        m = self.model()
        ids = {id(t) for t in tracks}
        sel = QItemSelection()
        first = None
        for r, t in enumerate(m.rows):
            if id(t) in ids:
                sel.select(m.index(r, 0), m.index(r, m.columnCount() - 1))
                if first is None:
                    first = r
        sm = self.selectionModel()
        sm.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        cur = first
        if current is not None:
            for r, t in enumerate(m.rows):
                if t is current:
                    cur = r
        if cur is not None:
            sm.setCurrentIndex(m.index(cur, max(1, self.currentIndex().column())),
                               QItemSelectionModel.SelectionFlag.NoUpdate)
            self.scrollTo(m.index(cur, 1))

    # -- drag & drop ---------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.source() is self:
            if e.modifiers() & Qt.KeyboardModifier.AltModifier:
                e.acceptProposedAction()
                return
            e.ignore()
            return
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if e.source() is self or e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if e.source() is self:
            target = self.rowAt(e.position().toPoint().y())
            rows = self.selected_rows()
            if target < 0:
                target = self.model().rowCount()
            sel = self.selected_tracks()
            before = sum(1 for r in rows if r < target)
            self.model().move_rows(rows, target - before)
            self.select_tracks(sel)
            e.acceptProposedAction()
            return
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            add = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.files_dropped.emit(paths, add)
            e.acceptProposedAction()

    def keyPressEvent(self, e):
        alt = e.modifiers() & Qt.KeyboardModifier.AltModifier
        if alt and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down, Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            rows = self.selected_rows()
            if rows:
                sel = self.selected_tracks()
                n = self.model().rowCount()
                target = {Qt.Key.Key_Up: rows[0] - 1, Qt.Key.Key_Down: rows[0] + 1,
                          Qt.Key.Key_PageUp: 0, Qt.Key.Key_PageDown: n - len(rows)}[e.key()]
                self.model().move_rows(rows, target)
                self.select_tracks(sel)
            return
        if e.matches(QKeySequence.StandardKey.Copy) or e.matches(QKeySequence.StandardKey.Paste) \
                or e.matches(QKeySequence.StandardKey.Cut) or e.matches(QKeySequence.StandardKey.SelectAll):
            e.ignore()           # handled by main window actions
            return
        super().keyPressEvent(e)

    def edit_first_editable(self) -> None:
        """F2: rename (first editable column) of the current file."""
        idx = self.currentIndex()
        if not idx.isValid():
            rows = self.selected_rows()
            if not rows:
                return
            idx = self.model().index(rows[0], 1)
        m = self.model()
        for c in range(1, m.columnCount()):
            i = m.index(idx.row(), c)
            if m.flags(i) & Qt.ItemFlag.ItemIsEditable:
                self.setCurrentIndex(i)
                self.edit(i)
                return
