"""The help window: every function explained, one page per topic, in the language of the program."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFrameFormat, QTextLength, QTextTable)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from .. import i18n
from ..i18n import tr
from . import theme
from .persist import remember

SHORTCUTS = [
    ("Arbeitsschritte", [
        ("Strg+Alt+B", "Alle Alben automatisch"), ("Strg+Shift+M", "Moods der Auswahl analysieren"),
        ("Strg+Alt+M", "Moods aller Dateien analysieren"),
        ("Strg+Shift+B", "MusicBrainz automatisch"), ("Strg+K", "Nummern schreiben"),
        ("Strg+Shift+L", "Genres von Last.fm holen"), ("Alt+1", "Umbenennen"),
    ]),
    ("Allgemein", [
        ("Strg+D", "Ordner öffnen"), ("Strg+H", "Ordner hinzufügen"), ("F5", "Aktualisieren"),
        ("Strg+F / F3", "Suchen"), ("Strg+S", "Tag speichern"), ("Strg+R", "Tag entfernen"),
        ("Strg+C", "Tag oder markierten Text kopieren"), ("Strg+V", "Tag oder Text einfügen"),
        ("Strg+Z", "Rückgängig"), ("Strg+Y", "Wiederholen"), ("Strg+A", "Alle Dateien auswählen"),
        ("Entf", "Dateien aus der Liste entfernen (bleiben auf der Festplatte)"),
        ("F4 / Strg+Shift+T", "Abspielen"), ("Alt+T", "Erweiterte Tags"), ("Strg+Q", "Tag-Panel ein-/ausblenden"),
        ("Strg+Alt+A", "Cover hinzufügen"), ("Strg+O", "Optionen"),
        ("Strg+Tab / Strg+Shift+Tab", "Zwischen Tag-Panel, Suchfeld und Dateiliste wechseln"),
    ]),
]

FIRST_TOPIC = "start"
SHORTCUTS_TOPIC = "shortcuts"
_HIGHLIGHTED = "summary"              # where every later correction starts
TOPIC_ROLE = Qt.ItemDataRole.UserRole
MAX_TEXT_WIDTH = 680                  # pixels: about 75 characters, also in a maximized window
_PAGE_MARGIN = 40
_BODY_POINTS = 10.5
_HEADINGS = {1: (20.0, 0, 14), 2: (13.5, 26, 8), 3: (11.5, 18, 6)}     # level: size, space above, below
_PROPORTIONAL = QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
_MONO_FONTS = ["Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]
TOPICS = (("Zuerst", (("start", "Bitte zuerst lesen"), ("workflow", "So läuft es ab"), ("summary", "Die Übersicht"))),
          ("Die Schritte", (("moods", "Moods"), ("sources", "MusicBrainz und Discogs"), ("numbers", "Nummern"),
                            ("covers", "Cover"), ("genres", "Genres"), ("rename", "Umbenennen"))),
          ("Im Alltag", (("editing", "Tags von Hand ändern"), ("settings", "Optionen"))),
          ("Erweitern", (("plugins", "Cover-Plugins"),)),
          ("Wenn es hakt", (("trouble", "Fehlersuche"), (SHORTCUTS_TOPIC, "Tastaturkürzel"))))


def topic_keys() -> list[str]:
    return [key for _group, topics in TOPICS for key, _title in topics]


def _shortcuts_page() -> str:
    lines = [f"# {tr('Tastaturkürzel')}", ""]
    for group, items in SHORTCUTS:
        lines += [f"## {tr(group)}", "", f"| {tr('Taste')} | {tr('Funktion')} |", "|---|---|"]
        for keys, what in items:
            if i18n.language() == "en":
                keys = keys.replace("Strg", "Ctrl").replace("Entf", "Del")
            lines.append(f"| {keys} | {tr(what)} |")
        lines.append("")
    return "\n".join(lines)


def page(topic: str) -> str:
    """The text of a page as Markdown."""
    if topic == SHORTCUTS_TOPIC:
        return _shortcuts_page()
    folder = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "resources", "help")
    with open(os.path.join(folder, "en" if i18n.language() == "en" else "de", f"{topic}.md"), encoding="utf-8") as fh:
        return fh.read()


def _style_heading(cursor: QTextCursor, block, level: int) -> None:
    size, above, below = _HEADINGS.get(level, _HEADINGS[3])
    fmt = QTextBlockFormat(block.blockFormat())
    fmt.setTopMargin(above)
    fmt.setBottomMargin(below)
    fmt.setLineHeight(120, _PROPORTIONAL)
    cursor.setPosition(block.position())
    cursor.setBlockFormat(fmt)
    text = QTextCharFormat()
    text.setFontPointSize(size)
    text.setFontWeight(QFont.Weight.DemiBold if level > 1 else QFont.Weight.Bold)
    text.setForeground(QColor(theme.TEXT))
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    cursor.setCharFormat(text)
    cursor.setBlockCharFormat(text)


def _style_code_block(cursor: QTextCursor, block) -> None:
    fmt = QTextBlockFormat(block.blockFormat())
    fmt.setBackground(QColor(theme.FIELD))
    fmt.setTextIndent(14)
    fmt.setTopMargin(0)
    fmt.setBottomMargin(0 if block.next().blockFormat().nonBreakableLines() else 14)
    fmt.setLineHeight(100, _PROPORTIONAL)
    cursor.setPosition(block.position())
    cursor.setBlockFormat(fmt)
    mono = QTextCharFormat()
    mono.setFontFamilies(_MONO_FONTS)
    cursor.movePosition(QTextCursor.MoveOperation.EndOfBlock, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(mono)


def _style_body(cursor: QTextCursor, block, in_table: bool) -> None:
    fmt = QTextBlockFormat(block.blockFormat())
    fmt.setLineHeight(125 if in_table else 135, _PROPORTIONAL)
    fmt.setTopMargin(0)
    inside_list = block.textList() is not None and block.next().textList() is not None
    fmt.setBottomMargin(0 if in_table else 3 if inside_list else 11)
    cursor.setPosition(block.position())
    cursor.setBlockFormat(fmt)


def _style_inline_code(cursor: QTextCursor, block) -> None:
    it = block.begin()
    while not it.atEnd():
        fragment = it.fragment()
        if fragment.isValid() and fragment.charFormat().fontFixedPitch():
            mono = QTextCharFormat()
            mono.setBackground(QColor(theme.FIELD))
            mono.setFontFamilies(_MONO_FONTS)
            cursor.setPosition(fragment.position())
            cursor.setPosition(fragment.position() + fragment.length(), QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(mono)
        it += 1


def _select_cell(cursor: QTextCursor, cell) -> None:
    cursor.setPosition(cell.firstPosition())
    cursor.setPosition(cell.lastPosition(), QTextCursor.MoveMode.KeepAnchor)


def _style_note(cursor: QTextCursor, table: QTextTable) -> None:
    """A table of one cell is a note: a calm colored box."""
    cell = table.cellAt(0, 0)
    fmt = cell.format().toTableCellFormat()
    fmt.setBackground(QColor(theme.WARNING_BACKGROUND))
    fmt.setPadding(14)
    cell.setFormat(fmt)
    text = QTextCharFormat()
    text.setFontWeight(QFont.Weight.Medium)
    text.setForeground(QColor(theme.TEXT))
    _select_cell(cursor, cell)
    cursor.mergeCharFormat(text)


def _style_grid(cursor: QTextCursor, table: QTextTable) -> None:
    """Rows divided by hairlines, the head of each column quiet."""
    for row in range(table.rows()):
        for column in range(table.columns()):
            cell = table.cellAt(row, column)
            fmt = cell.format().toTableCellFormat()
            fmt.setTopPadding(8)
            fmt.setBottomPadding(8)
            fmt.setLeftPadding(0 if column == 0 else 10)
            fmt.setRightPadding(14)
            fmt.setBottomBorder(1)
            fmt.setBottomBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_Solid)
            fmt.setBottomBorderBrush(QBrush(QColor(theme.BORDER if row == 0 else theme.BUTTON)))
            cell.setFormat(fmt)
            if row == 0:
                head = QTextCharFormat()
                head.setForeground(QColor(theme.SECONDARY))
                head.setFontWeight(QFont.Weight.DemiBold)
                _select_cell(cursor, cell)
                cursor.mergeCharFormat(head)


def _style_table(cursor: QTextCursor, table: QTextTable) -> None:
    fmt = table.format()
    fmt.setBorder(0)
    fmt.setBorderStyle(QTextFrameFormat.BorderStyle.BorderStyle_None)
    fmt.setBorderCollapse(True)
    fmt.setCellSpacing(0)
    fmt.setCellPadding(0)
    fmt.setWidth(QTextLength(QTextLength.Type.PercentageLength, 100))
    fmt.setTopMargin(4)
    fmt.setBottomMargin(16)
    table.setFormat(fmt)
    if table.rows() == 1 and table.columns() == 1:
        _style_note(cursor, table)
    else:
        _style_grid(cursor, table)


def polish(document: QTextDocument) -> None:
    """Turn the plain result of the Markdown import into a page that fits the program."""
    document.setUndoRedoEnabled(False)
    cursor = QTextCursor(document)
    cursor.beginEditBlock()
    block = document.begin()
    while block.isValid():
        cursor.setPosition(block.position())
        level = block.blockFormat().headingLevel()
        if level:
            _style_heading(cursor, block, level)
        elif block.blockFormat().nonBreakableLines():
            _style_code_block(cursor, block)
        else:
            _style_body(cursor, block, cursor.currentTable() is not None)
            _style_inline_code(cursor, block)
        block = block.next()
    for frame in document.rootFrame().childFrames():
        if isinstance(frame, QTextTable):
            _style_table(cursor, frame)
    cursor.endEditBlock()


class HelpDialog(QDialog):
    def __init__(self, parent=None, topic: str = ""):
        super().__init__(parent)
        self.setWindowTitle(tr("Hilfe"))
        self.resize(960, 720)
        self.setMinimumSize(720, 480)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.nav = QListWidget()
        self.nav.setObjectName("HelpNav")
        self.nav.setFixedWidth(232)
        self.text = QTextBrowser()
        self.text.setObjectName("HelpText")
        self.text.setOpenLinks(False)
        self.text.anchorClicked.connect(self._link)
        self._fill_nav()
        self.nav.currentItemChanged.connect(self._chosen)
        body.addWidget(self.nav)
        body.addWidget(self.text, 1)
        root.addLayout(body, 1)
        root.addWidget(self._footer())
        remember(self, "help")
        self.show_topic(topic)

    def _fill_nav(self) -> None:
        for group, topics in TOPICS:
            head = QListWidgetItem(tr(group))
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            head.setForeground(QBrush(QColor(theme.SECONDARY)))
            small = QFont(head.font())
            small.setPointSizeF(8.5)
            small.setWeight(QFont.Weight.DemiBold)
            head.setFont(small)
            head.setSizeHint(QSize(0, 34))
            head.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
            self.nav.addItem(head)
            for key, title in topics:
                item = QListWidgetItem(tr(title))
                item.setData(TOPIC_ROLE, key)
                item.setSizeHint(QSize(0, 28))
                if key == _HIGHLIGHTED:
                    font = QFont(item.font())
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QBrush(QColor(theme.ACCENT)))
                self.nav.addItem(item)

    def _footer(self) -> QWidget:
        foot = QWidget()
        foot.setObjectName("OptionsFooter")
        row = QHBoxLayout(foot)
        row.setContentsMargins(18, 12, 18, 12)
        row.addStretch(1)
        close = QPushButton(tr("Schließen"))
        close.setObjectName("DialogPrimary")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        return foot

    def current_topic(self) -> str:
        item = self.nav.currentItem()
        return item.data(TOPIC_ROLE) if item is not None else ""

    def show_topic(self, topic: str) -> None:
        wanted = topic if topic in topic_keys() else FIRST_TOPIC
        for i in range(self.nav.count()):
            if self.nav.item(i).data(TOPIC_ROLE) == wanted:
                self.nav.setCurrentRow(i)
                return

    def _chosen(self, item, _previous) -> None:
        if item is None:
            return
        document = self.text.document()
        font = QFont(self.font())
        font.setPointSizeF(_BODY_POINTS)
        document.setDefaultFont(font)
        self.text.setMarkdown(page(item.data(TOPIC_ROLE)))
        polish(document)
        self._fit_measure()
        self.text.verticalScrollBar().setValue(0)

    def _fit_measure(self) -> None:
        """The same reading width in any window size."""
        root = self.text.document().rootFrame()
        fmt = root.frameFormat()
        fmt.setTopMargin(30)
        fmt.setBottomMargin(30)
        fmt.setLeftMargin(_PAGE_MARGIN)
        fmt.setRightMargin(max(_PAGE_MARGIN, self.text.viewport().width() - _PAGE_MARGIN - MAX_TEXT_WIDTH))
        root.setFrameFormat(fmt)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._fit_measure()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._fit_measure()

    def _link(self, url: QUrl) -> None:
        if url.scheme() == "help":
            self.show_topic(url.path())
        else:
            QDesktopServices.openUrl(url)
