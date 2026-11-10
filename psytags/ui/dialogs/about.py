"""About: the program, what it is built on, and the licenses to read."""
from __future__ import annotations

import importlib
import os
import sys
from typing import NamedTuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from ... import __version__
from ...i18n import tr
from ..icons import logo_pixmap
from ..persist import remember

REPOSITORY = "https://github.com/Psychotoxical/PsyTags"
_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "resources", "licenses")


class Entry(NamedTuple):
    name: str
    version: str
    use: str
    label: str
    text: str
    url: str = ""


def license_text(name: str) -> str:
    with open(os.path.join(_FOLDER, name), encoding="utf-8") as handle:
        return handle.read()


def _version(module: str, attribute: str = "__version__") -> str:
    try:
        return str(getattr(importlib.import_module(module), attribute))
    except (ImportError, OSError, AttributeError):
        return ""


def _ffmpeg_notice() -> str:
    """The license that came with the packaged ffmpeg, "" if the package brings none."""
    package = getattr(sys, "_MEIPASS", "")
    notice = os.path.join(package, "ffmpeg", "LICENSE") if package else ""
    if notice and os.path.isfile(notice):
        with open(notice, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    return ""


def _ffmpeg_text() -> str:
    return _ffmpeg_notice() or tr("FFmpeg kommt aus der Paketverwaltung. Es gilt die Lizenz des installierten Builds.")


def _ffmpeg_label() -> str:
    """The license named at the top of the packaged notice, whichever build was packaged."""
    head = " ".join(_ffmpeg_notice()[:400].split()).upper()
    if "GNU LESSER GENERAL PUBLIC LICENSE VERSION 2.1" in head:
        return "LGPL-2.1-or-later"
    if "GNU GENERAL PUBLIC LICENSE VERSION 3" in head:
        return "GPL-3.0-or-later"
    return tr("je nach Build")


def sections() -> list[tuple[str, str, list[Entry]]]:
    return [
        ("PsyTags", tr("Schlanker Tag-Editor mit Automatik und Mood-Analyse aus dem Audio."), [
            Entry("PsyTags", __version__, tr("Freie Software unter den Bedingungen der GPL"),
                  "GPL-3.0-or-later", license_text("gpl-3.0.txt"))]),
        (tr("Bibliotheken"), tr("Diese Programme und Bibliotheken stecken in PsyTags."), [
            Entry("Qt / PySide6", _version("PySide6"), tr("Oberfläche"), "LGPL-3.0", license_text("lgpl-3.0.txt")),
            Entry("mutagen", _version("mutagen", "version_string"), tr("Tags lesen und schreiben"),
                  "GPL-2.0-or-later", license_text("mutagen.txt")),
            Entry("NumPy", _version("numpy"), tr("Berechnungen für die Mood-Analyse"),
                  "BSD-3-Clause", license_text("numpy.txt")),
            Entry("ONNX Runtime", _version("onnxruntime"), tr("Führt die Mood-Modelle aus"),
                  "MIT", license_text("onnxruntime.txt")),
            Entry("FFmpeg", "", tr("Liest das Audio für die Mood-Analyse"), _ffmpeg_label(), _ffmpeg_text())]),
        (tr("Daten und Dienste"), tr("Von hier kommen Modelle, Tags, Cover und Farben."), [
            Entry("Music Technology Group", "", tr("Mood-Modelle, werden beim ersten Mal geladen"), "CC BY-NC-SA 4.0",
                  tr("Die Modelle discogs-effnet und mtg_jamendo_moodtheme liegen nicht im Paket."),
                  "https://essentia.upf.edu/models.html"),
            Entry("MusicBrainz", "", tr("Tags"), "CC0", tr("Die Kerndaten von MusicBrainz stehen unter CC0."),
                  "https://musicbrainz.org"),
            Entry("Cover Art Archive", "", tr("Cover"), tr("Hinweis"),
                  tr("Die Cover gehören ihren jeweiligen Rechteinhabern."), "https://coverartarchive.org"),
            Entry("Last.fm", "", tr("Genres, mit eigenem API-Schlüssel"), tr("Nicht kommerziell"),
                  tr("Die Bedingungen von Last.fm erlauben nur nicht kommerzielle Nutzung."), "https://www.last.fm"),
            Entry("Discogs", "", tr("Zweite Quelle für offene Alben, mit eigenem Token"), tr("Hinweis"),
                  tr("Von Discogs kommen nur Texte, keine Cover."), "https://www.discogs.com"),
            Entry("Catppuccin", "", tr("Farben Mocha und Latte"), "MIT", license_text("catppuccin.txt"),
                  "https://catppuccin.com")]),
    ]


class _Row(QWidget):
    """Name, version and purpose of one entry; its button shows the license."""

    def __init__(self, entry: Entry, parent: QWidget):
        super().__init__(parent)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 8, 0, 8)
        box.setSpacing(2)
        line = QHBoxLayout()
        box.addLayout(line)
        line.setSpacing(8)
        name = QLabel(f'<b><a href="{entry.url}">{entry.name}</a></b>' if entry.url else f"<b>{entry.name}</b>", self)
        name.setOpenExternalLinks(True)
        line.addWidget(name)
        if entry.version:
            version = QLabel(entry.version, self)
            version.setObjectName("DialogSubtitle")
            line.addWidget(version)
        line.addStretch(1)
        self.button = QPushButton(entry.label, self)
        self.button.setObjectName("ChipButton")
        self.button.setCheckable(True)
        self.button.setAutoDefault(False)
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        line.addWidget(self.button)
        use = QLabel(entry.use, self)
        use.setObjectName("DialogSubtitle")
        use.setWordWrap(True)
        box.addWidget(use)
        self.text = self._text_widget(entry.text)
        self.text.hide()
        box.addWidget(self.text)
        self.button.toggled.connect(self.text.setVisible)

    def _text_widget(self, text: str) -> QWidget:
        if "\n" not in text.strip():
            label = QLabel(text, self)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            return label
        view = QPlainTextEdit(text, self)
        view.setReadOnly(True)
        view.setFixedHeight(220)
        return view


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Über PsyTags..."))
        self.resize(780, 640)
        self.setMinimumSize(620, 460)
        self._blocks: dict[str, QWidget] = {}
        all_sections = sections()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._header(all_sections))
        page = QWidget(self)
        page.setObjectName("OptionsPage")
        column = QVBoxLayout(page)
        column.setContentsMargins(30, 6, 30, 6)
        column.setSpacing(0)
        for i, (title, intro, entries) in enumerate(all_sections):
            if i:
                rule = QFrame(page)
                rule.setObjectName("SectionRule")
                column.addWidget(rule)
            column.addWidget(self._block(page, title, intro, entries))
        column.addStretch(1)
        self.scroll = QScrollArea(self)
        self.scroll.setWidget(page)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)
        root.addWidget(self._footer())
        remember(self, "about")

    def _header(self, all_sections) -> QWidget:
        head = QWidget(self)
        head.setObjectName("OptionsHeader")
        row = QHBoxLayout(head)
        row.setContentsMargins(30, 16, 30, 10)
        logo = QLabel(head)
        logo.setPixmap(logo_pixmap(30))
        logo.setAccessibleName("PsyTags")
        row.addWidget(logo)
        row.addStretch(1)
        for title, _intro, _entries in all_sections:
            link = QPushButton(title, head)
            link.setObjectName("SectionLink")
            link.setAutoDefault(False)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda _=False, key=title: self.show_section(key))
            row.addWidget(link)
        return head

    def _footer(self) -> QWidget:
        foot = QWidget(self)
        foot.setObjectName("OptionsFooter")
        row = QHBoxLayout(foot)
        row.setContentsMargins(18, 12, 18, 12)
        row.setSpacing(8)
        link = QLabel(f'<a href="{REPOSITORY}">{tr("Projekt auf GitHub")}</a>', foot)
        link.setOpenExternalLinks(True)
        row.addWidget(link)
        row.addStretch(1)
        close = QPushButton(tr("Schließen"), foot)
        close.setObjectName("DialogPrimary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        return foot

    def _block(self, page: QWidget, title: str, intro: str, entries: list[Entry]) -> QWidget:
        block = QWidget(page)
        box = QVBoxLayout(block)
        box.setContentsMargins(0, 18, 0, 18)
        box.setSpacing(6)
        heading = QLabel(title, block)
        heading.setObjectName("SectionTitle")
        box.addWidget(heading)
        note = QLabel(intro, block)
        note.setObjectName("DialogSubtitle")
        note.setWordWrap(True)
        box.addWidget(note)
        for entry in entries:
            box.addWidget(_Row(entry, block))
        self._blocks[title] = block
        return block

    def show_section(self, title: str) -> None:
        self.scroll.verticalScrollBar().setValue(self._blocks[title].y())
