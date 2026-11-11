"""Tag panel: input fields for the selected files plus the cover art area."""
from __future__ import annotations

import os

from mutagen._constants import GENRES
from PySide6.QtCore import QByteArray, QBuffer, QMimeData, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QDrag, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QCompleter, QFrame, QHBoxLayout, QLabel, QMenu, QScrollArea, QSizePolicy,
                               QToolButton, QVBoxLayout, QWidget)

from .. import genremood, tags
from ..config import PanelField
from ..i18n import tr

KEEP = "(je Datei lassen)"
BLANK = "(leeren)"


def keep_text() -> str:
    return tr(KEEP)


def blank_text() -> str:
    return tr(BLANK)


class FieldCombo(QComboBox):
    """Editable combo box; remembers whether the user changed the text."""
    user_edited = Signal()
    shift_enter = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.setMaxVisibleItems(20)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        c = self.completer()
        if c is not None:
            c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.dirty = False
        self._loading = False
        self.lineEdit().textEdited.connect(self._edited)
        self.activated.connect(self._edited)

    def _edited(self, *_):
        if not self._loading:
            self.dirty = True
            self.user_edited.emit()

    def set_values(self, current: str, choices: list[str]) -> None:
        self._loading = True
        self.clear()
        self.addItems(choices)
        self.setEditText(current)
        self.lineEdit().setCursorPosition(0)
        self.dirty = False
        self._loading = False

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and e.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.shift_enter.emit()
            return
        super().keyPressEvent(e)


class CoverView(QFrame):
    """Cover art at the top of the tag panel."""
    changed = Signal()
    request = Signal(str)        # menu command name

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.Box)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setStyleSheet("CoverView { background: palette(base); border: 1px solid palette(mid); }")
        self.setFixedSize(112, 112)
        self.setAcceptDrops(True)
        self.covers: list[tags.Cover] = []
        self.varies = False
        self.index = 0
        self._img: QImage | None = None
        self.fetch_entries = None    # callable -> [(command, menu text)] for "load cover from ..."
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._menu)
        self._prev = QToolButton(self)
        self._prev.setArrowType(Qt.ArrowType.LeftArrow)
        self._prev.setAutoRaise(True)
        self._next = QToolButton(self)
        self._next.setArrowType(Qt.ArrowType.RightArrow)
        self._next.setAutoRaise(True)
        self._prev.clicked.connect(lambda: self._step(-1))
        self._next.clicked.connect(lambda: self._step(1))
        self._drag_start: QPoint | None = None
        self.show_covers([], False)

    def resizeEvent(self, e):
        self._prev.move(2, self.height() - 22)
        self._next.move(self.width() - 22, self.height() - 22)
        super().resizeEvent(e)

    def show_covers(self, covers: list[tags.Cover], varies: bool) -> None:
        self.covers = covers
        self.varies = varies
        self.index = min(self.index, max(0, len(covers) - 1))
        self._load()

    def _load(self):
        self._img = None
        if self.covers:
            img = QImage.fromData(self.covers[self.index].data)
            self._img = None if img.isNull() else img
        many = len(self.covers) > 1
        self._prev.setVisible(many)
        self._next.setVisible(many)
        self.setToolTip(self.info_text())
        self.update()

    def info_text(self) -> str:
        if not self.covers:
            return tr("Verschiedene Cover") if self.varies else ""
        c = self.covers[self.index]
        typ = tags.COVER_TYPES[c.type] if c.type < len(tags.COVER_TYPES) else str(c.type)
        dims = f"{self._img.width()}x{self._img.height()}" if self._img else "?"
        fmt = c.mime.split("/")[-1].upper()
        n = f" ({self.index + 1}/{len(self.covers)})" if len(self.covers) > 1 else ""
        text = f"{typ}{n}\n{fmt} {dims} - {len(c.data) // 1024} KB"
        if c.description:          # tag sources store their name here, e.g. "Cover Art Archive"
            text += "\n" + tr("Quelle: {1}", c.description)
        return text

    def _step(self, d: int):
        if self.covers:
            self.index = (self.index + d) % len(self.covers)
            self._load()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = self.contentsRect()
        if self._img is not None:
            img = self._img.scaled(r.size(), Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            p.drawImage(r.x() + (r.width() - img.width()) // 2,
                        r.y() + (r.height() - img.height()) // 2, img)
        else:
            self._paint_placeholder(p, r)
            if self.varies:
                p.setPen(self.palette().color(self.palette().ColorRole.PlaceholderText))
                p.drawText(r.adjusted(0, 0, 0, -12), Qt.AlignmentFlag.AlignHCenter
                           | Qt.AlignmentFlag.AlignBottom, tr("Verschiedene Cover"))
        p.end()

    def _paint_placeholder(self, p: QPainter, r: QRect):
        # Grey disc symbol for "no cover".
        c = r.center()
        col = self.palette().color(self.palette().ColorRole.PlaceholderText)
        p.setPen(QPen(col, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, 20, 20)
        p.drawEllipse(c, 6, 6)
        p.setPen(QPen(col, 1.5))
        p.drawArc(QRect(c.x() - 14, c.y() - 14, 28, 28), 30 * 16, 60 * 16)
        p.drawArc(QRect(c.x() - 14, c.y() - 14, 28, 28), 210 * 16, 60 * 16)

    def mouseDoubleClickEvent(self, e):
        if self._img is not None:
            self.request.emit("preview")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._drag_start = e.position().toPoint()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag_start is None or self._img is None:
            return
        if (e.position().toPoint() - self._drag_start).manhattanLength() < QApplication.startDragDistance():
            return
        md = QMimeData()
        md.setImageData(self._img)
        c = self.covers[self.index]
        md.setData(c.mime, QByteArray(c.data))
        d = QDrag(self)
        d.setMimeData(md)
        d.setPixmap(QPixmap.fromImage(self._img.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio)))
        d.exec(Qt.DropAction.CopyAction)
        self._drag_start = None

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasImage() or any(u.isLocalFile() and u.toLocalFile().lower().endswith(
                (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")) for u in md.urls()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        data, mime = None, "image/jpeg"
        for u in md.urls():
            if u.isLocalFile():
                path = u.toLocalFile()
                with open(path, "rb") as fh:
                    data = fh.read()
                mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
                break
        if data is None and md.hasImage():
            data, mime = image_to_bytes(md.imageData()), "image/jpeg"
        if data:
            self.set_cover(data, mime, replace=not (e.modifiers() & Qt.KeyboardModifier.ControlModifier))
            e.acceptProposedAction()

    def set_cover(self, data: bytes, mime: str, replace: bool = True) -> None:
        new = tags.Cover(data, mime, 3, "")
        self.covers = [new] if replace else self.covers + [new]
        self.varies = False
        self.index = len(self.covers) - 1
        self._load()
        self.changed.emit()

    def remove_current(self) -> None:
        if self.covers:
            del self.covers[self.index]
            self.index = max(0, self.index - 1)
        self.varies = False
        self._load()
        self.changed.emit()

    def _menu(self, pos):
        m = QMenu(self)
        has = self._img is not None
        for key, text, enabled in (
                ("add", tr("Cover hinzu&fügen..."), True),
                ("replace", tr("Cover er&setzen..."), has or self.varies),
                ("remove", tr("Cover entfe&rnen"), has or self.varies),
                ("preview", tr("Cover ansehen"), has)):
            a = m.addAction(text)
            a.setEnabled(bool(enabled))
            a.triggered.connect(lambda _=False, k=key: self.request.emit(k))
        entries = self.fetch_entries() if self.fetch_entries else []
        if entries:                                 # e.g. "Cover von MusicBrainz laden"
            m.addSeparator()
        for key, label in entries:
            m.addAction(label).triggered.connect(lambda _=False, k=key: self.request.emit(k))
        m.exec(self.mapToGlobal(pos))


def image_to_bytes(img: QImage, fmt: str = "JPG") -> bytes:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    img.save(buf, fmt, 95)
    return bytes(ba.data())


class TagPanel(QWidget):
    changed = Signal()                 # any user edit (enables "save")
    directory_chosen = Signal(str)
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.fields: list[PanelField] = []
        self.combos: dict[str, FieldCombo] = {}
        self.blank_comments = True                  # several files start with the comment on "< blank >"
        self.comment_preset = False
        self.dir_combo: QComboBox | None = None
        self.custom_values: dict[str, list[str]] = {}
        self.tracks = []
        self.covers_dirty = False
        self._opened_dir = ""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll)
        self.inner = QWidget()
        self.scroll.setWidget(self.inner)
        self.grid = QVBoxLayout(self.inner)
        self.grid.setContentsMargins(12, 4, 12, 10)
        self.grid.setSpacing(8)
        self.cover = CoverView()
        self.cover.changed.connect(self._cover_changed)
        self.cover_info = QLabel()
        self.cover_info.setObjectName("FieldLabel")
        self.cover_info.setWordWrap(True)
        self.cover_row = QWidget()
        top = QHBoxLayout(self.cover_row)
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)
        top.addWidget(self.cover)
        top.addWidget(self.cover_info, 1, Qt.AlignmentFlag.AlignBottom)
        self.setMinimumWidth(200)

    # -- layout ----------------------------------------------------------------
    def build(self, fields: list[PanelField], custom_values: dict[str, list[str]]) -> None:
        self.fields = [f for f in fields if f.enabled]
        self.custom_values = custom_values
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().setParent(None)
            elif it.layout():
                _clear_layout(it.layout())
        self.combos.clear()
        self.dir_combo = None
        self.grid.addWidget(self.cover_row)
        row: QHBoxLayout | None = None
        used = 0.0
        for f in self.fields:
            frac = f.fraction
            if row is None or used + frac > 1.0001:
                if row is not None and used < 0.999:
                    row.addStretch(int(round((1 - used) * 1000)))
                row = QHBoxLayout()
                row.setSpacing(8)
                self.grid.addLayout(row)
                used = 0.0
            used += frac
            box = QVBoxLayout()
            box.setSpacing(3)
            lab = QLabel(tr(f.name).replace("&", ""))   # default labels are translated, own ones stay
            lab.setObjectName("FieldLabel")
            box.addWidget(lab)
            if f.value.upper() == "_DIRECTORY":
                combo = QComboBox()
                combo.setEditable(True)
                combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                combo.setMinimumContentsLength(1)
                combo.activated.connect(lambda i, c=combo: self.directory_chosen.emit(c.itemText(i)))
                combo.lineEdit().returnPressed.connect(
                    lambda c=combo: self.directory_chosen.emit(c.currentText()))
                self.dir_combo = combo
            else:
                combo = FieldCombo()
                combo.user_edited.connect(self.changed)
                combo.shift_enter.connect(lambda fv=f.value, c=combo: self._save_custom(fv, c))
                combo.lineEdit().returnPressed.connect(self.save_requested)
                self.combos[f.value.upper()] = combo
            lab.setBuddy(combo)
            box.addWidget(combo)
            row.addLayout(box, int(round(frac * 1000)))
        if row is not None and used < 0.999:
            row.addStretch(int(round((1 - used) * 1000)))
        self.grid.addStretch(1)
        self.load(self.tracks)

    def _save_custom(self, field: str, combo: FieldCombo) -> None:
        v = combo.currentText()
        if v and v not in (keep_text(), blank_text()):
            lst = self.custom_values.setdefault(field.upper(), [])
            if v not in lst:
                lst.append(v)
                from ..config import save_custom_values
                save_custom_values(self.custom_values)

    def set_directories(self, current: str, history: list[str]) -> None:
        if self.dir_combo is None:
            return
        self._opened_dir = current
        self.dir_combo.blockSignals(True)
        self.dir_combo.clear()
        self.dir_combo.addItems(history)
        self.dir_combo.blockSignals(False)
        self._show_folder()

    def _show_folder(self) -> None:
        """The real folder of the selection; several albums show what they share."""
        if self.dir_combo is None:
            return
        folders = sorted({t.folder for t in self.tracks})
        try:
            text = os.path.commonpath(folders) if folders else self._opened_dir
        except ValueError:                               # different drives on Windows
            text = self._opened_dir
        self.dir_combo.blockSignals(True)
        self.dir_combo.setEditText(text)
        self.dir_combo.lineEdit().setCursorPosition(0)
        self.dir_combo.blockSignals(False)

    # -- data --------------------------------------------------------------------
    def load(self, tracks) -> None:
        self.tracks = list(tracks)
        n = len(self.tracks)
        self.comment_preset = n > 1 and self.blank_comments
        for name, combo in self.combos.items():
            if name in genremood.LIST_FIELDS:            # "Rock; Pop" instead of "Rock\\Pop"
                values = [genremood.join(t.get(name)) for t in self.tracks]
            else:
                values = ["\\\\".join(t.get(name)) for t in self.tracks]
            distinct = []
            for v in values:
                if v and v not in distinct:
                    distinct.append(v)
            if n == 0:
                current = ""
            elif len(set(values)) == 1:
                current = values[0]
            else:
                current = keep_text()
            if name == "COMMENT" and self.comment_preset:
                current = blank_text()
            choices = [keep_text(), blank_text()] if n else []
            choices += sorted(distinct, key=str.lower)
            extra = list(self.custom_values.get(name, []))
            if name == "GENRE":
                extra += sorted(GENRES)
            choices += [e for e in extra if e not in choices]
            combo.set_values(current, choices)
            combo.setEnabled(n > 0)
        self.covers_dirty = False
        if n == 0:
            self.cover.show_covers([], False)
        else:
            first = self.tracks[0].data.covers
            same = all(t.data.covers == first for t in self.tracks[1:])
            self.cover.show_covers(list(first) if same else [], not same)
        self.cover_info.setText(self.cover.info_text())
        self._show_folder()

    def _cover_changed(self):
        self.covers_dirty = True
        self.cover_info.setText(self.cover.info_text())
        self.changed.emit()

    @property
    def dirty(self) -> bool:
        return self.covers_dirty or any(c.dirty for c in self.combos.values())

    def pending(self, with_preset: bool = False) -> dict[str, str | None]:
        """Changed fields -> new value (None = blank/remove). KEEP values are skipped.
        ``with_preset``: also the comment that starts out blank; only a real save takes it,
        never an automatic one when the selection changes or the window closes."""
        out: dict[str, str | None] = {}
        for name, combo in self.combos.items():
            if not combo.dirty:
                if with_preset and name == "COMMENT" and self.comment_preset:
                    out[name] = None
                continue
            v = combo.currentText()
            if v == keep_text():
                continue
            out[name] = None if v in ("", blank_text()) else v
        return out

    def clear_dirty(self) -> None:
        for c in self.combos.values():
            c.dirty = False
        self.covers_dirty = False

    def focus_first(self) -> None:
        for c in self.combos.values():
            c.setFocus()
            c.lineEdit().selectAll()
            return

    def editing_widget(self):
        w = QApplication.focusWidget()
        while w is not None:
            if w is self:
                return QApplication.focusWidget()
            w = w.parentWidget()
        return None


def _clear_layout(lay):
    while lay.count():
        it = lay.takeAt(0)
        if it.widget():
            it.widget().setParent(None)
        elif it.layout():
            _clear_layout(it.layout())
