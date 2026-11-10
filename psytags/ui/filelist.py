"""File list (left side of the main window), grouped by album."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from PySide6.QtCore import (QAbstractTableModel, QItemSelection, QItemSelectionModel,
                            QModelIndex, QMimeData, QPoint, QRect, QRectF, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QFileIconProvider, QFrame,
                               QHeaderView, QStyledItemDelegate, QStyleOptionViewItem, QTableView, QLineEdit)

from . import theme
from .. import columnformat
from ..i18n import tr
from ..config import Column
from ..albumorder import natural_key as _natural_key, sort_key
from ..track import Track

ICON_COL = 0
ROW_HEIGHT = 28
BAND_HEIGHT = 36


@dataclass
class AlbumBand:
    """The heading above an album in the list."""
    tracks: list
    title: str
    info: str
    status: list[tuple[str, bool]] = field(default_factory=list)


def _status(tracks: list) -> list[tuple[str, bool]]:
    return [("Album", all(t.get("MUSICBRAINZ_ALBUMID") for t in tracks)),
            ("Cover", all(getattr(t.data, "covers", None) for t in tracks)),
            ("Genres", all(t.get("GENRE") for t in tracks)),
            ("Moods", any(t.get("MOOD") for t in tracks))]


def album_bands(rows: list) -> dict[int, AlbumBand]:
    """First row of each album run -> its heading. A sort that tears the albums apart gets
    none, because a heading above nearly every row would only be in the way."""
    from ..websources.albumauto import album_title, group_albums
    owner = {id(t): i for i, group in enumerate(group_albums(list(rows))) for t in group}
    runs: list[tuple[int, list]] = []
    for r, t in enumerate(rows):
        if runs and owner[id(runs[-1][1][-1])] == owner[id(t)]:
            runs[-1][1].append(t)
        else:
            runs.append((r, [t]))
    if len(runs) > 1 and len(runs) * 3 > len(rows) * 2:
        return {}
    out = {}
    for start, tracks in runs:
        year = next((y[0][:4] for y in (t.get("YEAR") or t.get("ORIGYEAR") for t in tracks) if y), "")
        count = tr("{1} Titel", len(tracks))
        out[start] = AlbumBand(tracks, album_title(tracks), f"{year} · {count}" if year else count, _status(tracks))
    return out


class FileListModel(QAbstractTableModel):
    edited = Signal(object, str, str, str)        # track, field, old, new

    def __init__(self, columns: list[Column], parent=None):
        super().__init__(parent)
        self.all: list[Track] = []
        self.rows: list[Track] = []
        self.columns = [c for c in columns if c.enabled]
        self.all_columns = columns
        self.sort_keys: list[tuple[int, bool]] = []     # (column, descending)
        self.keep_scroll = False                        # the next reset is no new list
        self.filter_text = ""
        self._filter = None
        self._cache: dict[tuple[int, int], str] = {}
        self._icon = QFileIconProvider()
        self._file_icon = None

    # -- structure -----------------------------------------------------------
    def set_columns(self, columns: list[Column]) -> None:
        self.beginResetModel()
        sort_cols = [(self.columns[c - 1], d) for c, d in self.sort_keys if 0 < c <= len(self.columns)]
        self.all_columns = columns
        self.columns = [c for c in columns if c.enabled]
        self.sort_keys = [(self.columns.index(c) + 1, d) for c, d in sort_cols if c in self.columns]
        self._cache.clear()
        self.endResetModel()

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
            v = columnformat.format(self.columns[col - 1].value, self.rows[row])
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
            return columnformat.format(col.field, t) if col.field else self.text(r, c)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return (Qt.AlignmentFlag.AlignRight if self.columns[c - 1].numeric
                    else Qt.AlignmentFlag.AlignLeft) | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and t.error:
            return QColor(theme.ERROR)
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
        old = columnformat.format(col.field, t)
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
        self.keep_scroll = True
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
                        s = columnformat.format(e, t)
                        m = re.match(r"\s*-?\d+(\.\d+)?", s)
                        return (0, float(m.group(0))) if m else (1, 0.0)
                else:
                    def key(t, e=expr):
                        return _natural_key(columnformat.format(e, t))
                rows.sort(key=key, reverse=desc)
        self.rows = rows
        self._number()

    def set_filter(self, text: str) -> None:
        self.beginResetModel()
        self.filter_text = text
        words = text.casefold().split()
        self._filter = (lambda t: self._matches(t, words)) if words else None
        self._apply()
        self.endResetModel()

    def _matches(self, t: Track, words: list[str]) -> bool:
        """Every word has to appear somewhere in the visible columns or the file name."""
        text = " ".join([columnformat.format(c.value, t) for c in self.columns] + [t.filename]).casefold()
        return all(w in text for w in words)

    def sort_by(self, col: int, add: bool) -> None:
        self.beginResetModel()
        # The sort is stable on what is shown now: Track, then Disc, then Album gives
        # albums with discs in order and tracks in order.
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


class _RowDelegate(_EditDelegate):
    """Keeps the cells of an album's first row below its heading."""

    def __init__(self, view: "FileListView"):
        super().__init__(view)
        self.view = view

    def _cell(self, option, index) -> QRect:
        rect = QRect(option.rect)
        if index.row() in self.view.bands:
            rect.setTop(rect.top() + BAND_HEIGHT)
        return rect

    def paint(self, painter, option, index):
        cell = QStyleOptionViewItem(option)
        cell.rect = self._cell(option, index)
        super().paint(painter, cell, index)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(self._cell(option, index))


class FileListView(QTableView):
    files_dropped = Signal(list, bool)      # paths, add (Ctrl held)
    context_menu = Signal(object)
    columns_changed = Signal()              # width or order changed by the user
    sort_changed = Signal()
    header_menu = Signal(object)            # global position of a right click on the header

    def __init__(self, model: FileListModel, parent=None):
        super().__init__(parent)
        self.bands: dict[int, AlbumBand] = {}
        self._restore_scroll: int | None = None
        self.setModel(model)
        self.setItemDelegate(_RowDelegate(self))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.SelectedClicked
                             | QAbstractItemView.EditTrigger.EditKeyPressed)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
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
        vh.setDefaultSectionSize(ROW_HEIGHT)
        hh = self.horizontalHeader()
        hh.setSectionsMovable(True)
        hh.setHighlightSections(False)
        hh.setStretchLastSection(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setSectionsClickable(True)
        hh.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        hh.customContextMenuRequested.connect(lambda p: self.header_menu.emit(hh.mapToGlobal(p)))
        hh.setSortIndicatorShown(True)
        hh.sectionClicked.connect(self._header_clicked)
        hh.sectionResized.connect(self._resized)
        hh.sectionMoved.connect(lambda *_: QTimer.singleShot(0, self._reorder))
        self._applying = False
        self.apply_widths()
        self._band_timer = QTimer(self)
        self._band_timer.setSingleShot(True)
        self._band_timer.setInterval(0)
        self._band_timer.timeout.connect(self._refresh_bands)
        model.modelAboutToBeReset.connect(self._remember_scroll)
        model.modelReset.connect(self._forget_bands)
        model.dataChanged.connect(lambda *_: self._band_timer.start())

    def model(self) -> FileListModel:      # type: ignore[override]
        return super().model()

    def apply_widths(self) -> None:
        m = self.model()
        self._applying = True
        try:
            self.setColumnHidden(ICON_COL, True)
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
        """Turn a header drag into a new, saved column order."""
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

    # -- album headings ------------------------------------------------------
    def _remember_scroll(self) -> None:
        m = self.model()
        self._restore_scroll = self.verticalScrollBar().value() if m.keep_scroll else None
        m.keep_scroll = False

    def _forget_bands(self) -> None:
        self.bands = {}
        self._band_timer.start()

    def _refresh_bands(self) -> None:
        new = album_bands(self.model().rows)
        vh = self.verticalHeader()
        for r in range(self.model().rowCount()):       # a reset keeps the old heights, so check every row
            height = ROW_HEIGHT + BAND_HEIGHT if r in new else ROW_HEIGHT
            if vh.sectionSize(r) != height:
                vh.resizeSection(r, height)
        self.bands = new
        if self._restore_scroll is not None:
            self.updateGeometries()                  # the range has to know the new row heights
            self.verticalScrollBar().setValue(self._restore_scroll)
            self._restore_scroll = None
        self.viewport().update()

    def _band_at(self, pos: QPoint) -> AlbumBand | None:
        r = self.rowAt(pos.y())
        if r in self.bands and pos.y() < self.rowViewportPosition(r) + BAND_HEIGHT:
            return self.bands[r]
        return None

    def mousePressEvent(self, e):
        band = self._band_at(e.position().toPoint()) if e.button() == Qt.MouseButton.LeftButton else None
        if band is not None:                         # a click on the heading selects the album
            self.select_tracks(band.tracks, band.tracks[0])
            return
        super().mousePressEvent(e)

    def paintEvent(self, e):
        super().paintEvent(e)
        if not self.bands:
            return
        first, last = self.rowAt(0), self.rowAt(self.viewport().height() - 1)
        if first < 0:
            return
        last = self.model().rowCount() - 1 if last < 0 else last
        p = QPainter(self.viewport())
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        for r in range(first, last + 1):
            if r in self.bands:
                self._paint_band(p, r)
        p.end()

    def _paint_band(self, p: QPainter, row: int) -> None:
        band = self.bands[row]
        rect = QRect(0, self.rowViewportPosition(row), self.viewport().width(), BAND_HEIGHT)
        p.fillRect(rect, QColor(theme.CHROME))
        p.fillRect(QRect(rect.left(), rect.bottom(), rect.width(), 1), QColor(theme.BORDER))
        right = self._paint_chips(p, rect, band.status)
        strong = QFont(self.font())
        strong.setWeight(QFont.Weight.DemiBold)
        p.setFont(strong)
        p.setPen(QColor(theme.TEXT))
        room = QRect(rect.left() + 14, rect.top(), max(0, right - rect.left() - 24), rect.height())
        title = p.fontMetrics().elidedText(band.title, Qt.TextElideMode.ElideRight, room.width())
        p.drawText(room, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, title)
        used = p.fontMetrics().horizontalAdvance(title) + 12
        p.setFont(self.font())
        p.setPen(QColor(theme.SECONDARY))
        rest = room.adjusted(used, 0, 0, 0)
        info = p.fontMetrics().elidedText(band.info, Qt.TextElideMode.ElideRight, max(0, rest.width()))
        p.drawText(rest, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, info)

    def _paint_chips(self, p: QPainter, rect: QRect, status: list[tuple[str, bool]]) -> int:
        """Paints from the right edge inward; returns the free space's right end."""
        small = QFont(self.font())
        small.setPixelSize(11)
        small.setWeight(QFont.Weight.Medium)
        p.setFont(small)
        x = rect.right() - 12
        for name, ok in reversed(status):
            text = tr(name)
            width = p.fontMetrics().horizontalAdvance(text) + 32
            chip = QRectF(x - width, rect.center().y() - 10, width, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(theme.OK_BACKGROUND if ok else theme.BAD_BACKGROUND))
            p.drawRoundedRect(chip, 10, 10)
            ink = QColor(theme.OK_TEXT if ok else theme.BAD_TEXT)
            p.setPen(QPen(ink, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            mx, my = chip.left() + 13, chip.center().y()
            if ok:
                p.drawPolyline([QPoint(int(mx - 4), int(my)), QPoint(int(mx - 1), int(my + 3)), QPoint(int(mx + 4), int(my - 3))])
            else:
                p.drawLine(QPoint(int(mx - 3), int(my - 3)), QPoint(int(mx + 3), int(my + 3)))
                p.drawLine(QPoint(int(mx + 3), int(my - 3)), QPoint(int(mx - 3), int(my + 3)))
            p.setPen(ink)
            p.drawText(chip.adjusted(22, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            x -= width + 6
        return x

    # -- selection helpers ---------------------------------------------------
    def selected_rows(self) -> list[int]:
        return sorted(i.row() for i in self.selectionModel().selectedRows())

    def selected_tracks(self) -> list[Track]:
        m = self.model()
        return [m.rows[r] for r in self.selected_rows()]

    def select_tracks(self, tracks: list[Track], current: Track | None = None, scroll: bool = True) -> None:
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
            if scroll:
                self.scrollTo(m.index(cur, 1))

    # -- drag & drop ---------------------------------------------------------
    def dragEnterEvent(self, e):
        if e.source() is not self and e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if e.source() is not self and e.mimeData().hasUrls():
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            add = bool(e.modifiers() & Qt.KeyboardModifier.ControlModifier)
            self.files_dropped.emit(paths, add)
            e.acceptProposedAction()

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.StandardKey.Copy) or e.matches(QKeySequence.StandardKey.Paste) \
                or e.matches(QKeySequence.StandardKey.Cut) or e.matches(QKeySequence.StandardKey.SelectAll):
            e.ignore()           # handled by main window actions
            return
        super().keyPressEvent(e)
