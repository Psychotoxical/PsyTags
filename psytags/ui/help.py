"""Help: the list of keyboard shortcuts."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from ..i18n import tr

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


def show_shortcuts(parent) -> None:
    html = ["<html><body style='font-size:10pt'>"]
    for group, items in SHORTCUTS:
        html.append(f"<h3>{tr(group)}</h3><table cellspacing=0 cellpadding=3>")
        for k, v in items:
            html.append(f"<tr><td width=190><b>{k}</b></td><td>{tr(v)}</td></tr>")
        html.append("</table>")
    html.append("</body></html>")
    d = QDialog(parent)
    d.setWindowTitle(tr("Tastaturkürzel"))
    d.resize(640, 600)
    lay = QVBoxLayout(d)
    tb = QTextBrowser()
    tb.setHtml("".join(html))
    lay.addWidget(tb)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    d.exec()
