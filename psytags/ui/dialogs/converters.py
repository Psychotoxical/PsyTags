"""Converter dialog (Alt+1)."""
from __future__ import annotations


from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFrame, QHBoxLayout, QLabel,
                               QMenu, QMessageBox, QPushButton, QToolButton, QVBoxLayout, QWidget)

from ... import config, convert
from ...i18n import tr
from ..persist import remember

FIELDS = ["TITLE", "ARTIST", "ALBUM", "YEAR", "TRACK", "GENRE", "COMMENT", "ALBUMARTIST",
          "COMPOSER", "DISCNUMBER", "BPM", "PUBLISHER", "CONDUCTOR", "LYRICIST", "ORIGARTIST",
          "ORIGALBUM", "ORIGYEAR", "MOOD", "INITIALKEY", "ISRC", "GROUPING", "SUBTITLE",
          "ENCODEDBY", "COPYRIGHT", "ALBUMSORT", "ARTISTSORT", "TITLESORT", "ALBUMARTISTSORT",
          "COMPOSERSORT", "MEDIATYPE", "LANGUAGE", "UNSYNCEDLYRICS", "MUSICBRAINZ_ALBUMTYPE"]

PLACEHOLDERS = ["_filename", "_filename_ext", "_extension", "_path", "_folderpath", "_directory",
                "_parent_directory", "_length", "_length_seconds", "_bitrate", "_samplerate",
                "_mode", "_codec", "_tag", "_tag_read", "_file_size", "_file_size_bytes",
                "_file_mod_date", "_file_create_date", "_counter", "_total_files", "_covers"]

FUNCS = ["$if(x,y,z)", "$if2(x,y)", "$if3(a1,a2,...,aN,else)", "$ifgreater(n1,n2,x,y)",
         "$iflonger(s,n,x,y)", "$eql(x,y)", "$neql(x,y)", "$and(x,y)", "$or(x,y)", "$not(x)",
         "$greater(x,y)", "$isdigit(x)", "$num(x,y)", "$left(x,y)", "$right(x,y)",
         "$mid(s,start,len)", "$len(x)", "$trim(x)", "$replace(x,y,z)", "$regexp(x,expr,repl)",
         "$caps(x)", "$caps2(x)", "$caps3(x)", "$upper(x)", "$lower(x)", "$strstr(s1,s2)",
         "$strrstr(s1,s2)", "$validate(x,y)", "$meta(x)", "$meta_sep(x,sep)", "$meta_num(x)",
         "$list(x,start,end,sep)", "$add(x,y)", "$sub(x,y)", "$mul(x,y)", "$div(x,y)",
         "$mod(x,y)", "$directory(x,n)", "$filename(x)", "$ext(x)", "$repeat(x,n)",
         "$fmtDate(fmt,ts)", "$removeDiacritics(x)"]


class FormatCombo(QWidget):
    """Format string combo box with history and the ▸ helper button (Ctrl+Space)."""

    def __init__(self, history_key: str, parent=None, fields_only=False):
        super().__init__(parent)
        self.key = history_key
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.combo.setMinimumContentsLength(30)
        self.combo.addItems(config.history(history_key))
        self.btn = QToolButton()
        self.btn.setText("▸")
        self.btn.setFixedSize(24, 22)
        self.btn.clicked.connect(self.show_helper)
        lay.addWidget(self.combo, 1)
        lay.addWidget(self.btn)
        QShortcut(QKeySequence("Ctrl+Space"), self.combo, self.show_helper)
        self.combo.installEventFilter(self)

    def eventFilter(self, obj, e):
        # Shift+Del removes the current entry from the history.
        if e.type() == e.Type.KeyPress and e.key() == Qt.Key.Key_Delete \
                and e.modifiers() & Qt.KeyboardModifier.ShiftModifier and self.combo.view().isVisible():
            i = self.combo.view().currentIndex().row()
            if i >= 0:
                self.combo.removeItem(i)
                return True
        return False

    def text(self) -> str:
        return self.combo.currentText()

    def set_text(self, s: str) -> None:
        self.combo.setEditText(s)

    def commit(self) -> None:
        config.push_history(self.key, self.text())

    def _insert(self, s: str) -> None:
        le = self.combo.lineEdit()
        le.insert(s)
        le.setFocus()

    def show_helper(self) -> None:
        m = QMenu(self)
        for f in FIELDS[:10]:
            m.addAction(f"%{f.lower()}%", lambda f=f: self._insert(f"%{f.lower()}%"))
        ext = m.addMenu(tr("Erweiterte Felder"))
        for f in FIELDS[10:]:
            ext.addAction(f"%{f.lower()}%", lambda f=f: self._insert(f"%{f.lower()}%"))
        info = m.addMenu(tr("Informationsfelder"))
        for p in PLACEHOLDERS:
            info.addAction(f"%{p}%", lambda p=p: self._insert(f"%{p}%"))
        fn = m.addMenu(tr("Funktionen"))
        for f in FUNCS:
            fn.addAction(f, lambda f=f: self._insert(f.split("(")[0] + "("))
        m.addSeparator()
        m.addAction(tr("Aus Liste entfernen"), self._remove_current)
        m.addAction(tr("Alle aus Liste entfernen..."), self._remove_all)
        m.exec(self.btn.mapToGlobal(self.btn.rect().bottomLeft()))

    def _remove_current(self):
        i = self.combo.findText(self.text())
        if i >= 0:
            self.combo.removeItem(i)
        config.settings().setValue(f"history/{self.key}",
                                   [self.combo.itemText(i) for i in range(self.combo.count())])

    def _remove_all(self):
        if QMessageBox.question(self, "PsyTags", tr("Sind Sie sicher, dass Sie alle Einträge aus der Liste entfernen möchten?")) \
                == QMessageBox.StandardButton.Yes:
            self.combo.clear()
            config.settings().setValue(f"history/{self.key}", [])


def _sep() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFrameShadow(QFrame.Shadow.Sunken)
    return f


class _Base(QDialog):
    def __init__(self, title: str, tracks, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.tracks = tracks
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(11, 11, 11, 11)
        self.lay.setSpacing(4)
        self.setMinimumWidth(440)
        self.preview = QLabel()
        self.preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.preview.setWordWrap(True)
        self.preview.setMinimumHeight(self.fontMetrics().height() * 2)

    def finish_layout(self, extra_button: QPushButton | None = None):
        self.lay.addWidget(self.preview)
        self.lay.addWidget(_sep())
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                              | QDialogButtonBox.StandardButton.Cancel
                              | QDialogButtonBox.StandardButton.Help)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText(tr("OK"))
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText(tr("Abbrechen"))
        bb.button(QDialogButtonBox.StandardButton.Help).setText(tr("&Hilfe"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.helpRequested.connect(self.help)
        row = QHBoxLayout()
        if extra_button is not None:
            row.addWidget(extra_button)
        row.addStretch(1)
        row.addWidget(bb)
        self.lay.addLayout(row)
        remember(self, type(self).__name__)

    def help(self):
        from ..help import show_help
        show_help(self, "format")

    @property
    def first(self):
        return self.tracks[0] if self.tracks else None


class TagToFilenameDialog(_Base):
    def __init__(self, tracks, parent=None):
        super().__init__(tr("Tag - Dateiname"), tracks, parent)
        self.lay.addWidget(QLabel(tr("Formatstring:")))
        self.fmt = FormatCombo("tag_filename")
        self.lay.addWidget(self.fmt)
        self.fmt.combo.editTextChanged.connect(self.update_preview)
        self.finish_layout()
        self.update_preview()

    def update_preview(self):
        t = self.first
        if t is None:
            self.preview.setText("")
            return
        new = convert.tag_to_filename(t, self.fmt.text())
        self.preview.setText(f"{t.filename}\n→ {convert.display_path(new, t)}")

    def accept(self):
        self.fmt.commit()
        super().accept()

    def format(self) -> str:
        return self.fmt.text()
