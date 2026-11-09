"""Help: keyboard shortcut list and format string reference."""
from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from ..i18n import tr

SHORTCUTS = [
    ("Allgemein", [
        ("Strg+A", "Alle Dateien auswählen"), ("Strg+Shift+A", "Auswahl umkehren"),
        ("Strg+B", "Alle Eingabefelder zurücksetzen"), ("Strg+C", "Tag oder markierten Text kopieren"),
        ("Strg+D", "Verzeichnis wechseln"),
        ("Strg+Shift+D", "Übergeordnetes Verzeichnis"),
        ("Entf", "Dateien aus der Liste entfernen (bleiben auf der Festplatte)"),
        ("Strg+Entf", "Dateien in den Papierkorb verschieben"),
        ("Strg+Shift+Entf", "Dateien endgültig löschen"),
        ("Strg+F", "Suchen"), ("Strg+G", "Ähnliche Dateien auswählen"),
        ("Strg+Shift+G", "Nächste ähnliche Dateien auswählen"), ("Strg+H", "Verzeichnis hinzufügen"),
        ("Strg+K", "Tracknummern-Assistent"), ("Strg+M", "Standardverzeichnis"),
        ("Strg+Alt+A", "Cover hinzufügen"), ("Strg+Alt+M", "Cover verwalten"),
        ("Strg+N", "Nächste Datei auswählen"), ("Strg+O", "Optionen"),
        ("Strg+Q", "Tag-Panel ein-/ausblenden"), ("Strg+R", "Tag entfernen"),
        ("Strg+S", "Tag speichern"), ("Strg+T", "Tag auslesen"),
        ("Strg+Shift+T / F4", "Abspielen"), ("Strg+U", "Auswahl aufheben"),
        ("Strg+V", "Tag oder Text einfügen"),
        ("Strg+X", "Tag oder Text ausschneiden"), ("Strg+Z", "Rückgängig"),
        ("Strg+Y", "Wiederholen"),
        ("F2", "Umbenennen"), ("F3", "Suchen"), ("F5", "Aktualisieren"),
        ("Alt+←/→", "Verzeichnisverlauf zurück/vor"), ("Alt+Enter", "Eigenschaften"),
        ("Alt+T", "Erweiterte Tags"), ("Alt+↑/↓", "Datei in der Liste verschieben"),
        ("Alt+Bild↑/↓", "Dateien an Anfang/Ende der Liste"),
    ]),
    ("Konverter", [
        ("Alt+1", "Tag - Dateiname"),
    ]),
    ("Hilfen", [
        ("Strg+Leertaste", "Formatstring-Hilfsmenü"),
        ("Strg+Tab / Strg+Shift+Tab", "Zwischen Tag-Panel, Suchfeld und Dateiliste wechseln"),
        ("Strg+Num+", "Spaltenbreiten an Inhalt anpassen"),
        ("Shift+Entf", "Eintrag aus Formatstring-Liste löschen"),
        ("Shift+Enter", "Feldinhalt als benutzerdefinierten Wert speichern"),
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
    _show(parent, tr("Tastaturkürzel"), "".join(html))


def show_help(parent, topic: str = "") -> None:
    from .dialogs.converters import FUNCS, PLACEHOLDERS
    intro = tr("<code>%feld%</code> – Wert eines Tag-Feldes, <code>$funktion(…)</code> – Skriptfunktion, "
               "<code>[…]</code> – nur anzeigen, wenn ein enthaltenes Feld nicht leer ist, "
               "<code>'…'</code> – wörtlicher Text. <code>\\</code> im Dateinamen-Formatstring legt "
               "Verzeichnisse an.")
    html = [f"<h3>{tr('Formatstrings')}</h3><p>{intro}</p><h4>{tr('Informationsfelder')}</h4><p>",
            ", ".join(f"<code>%{p}%</code>" for p in PLACEHOLDERS), f"</p><h4>{tr('Funktionen')}</h4><p>",
            "<br>".join(f"<code>{f}</code>" for f in FUNCS), "</p>"]
    _show(parent, tr("Hilfethemen"), "".join(html))


def _show(parent, title: str, html: str) -> None:
    d = QDialog(parent)
    d.setWindowTitle(title)
    d.resize(640, 600)
    lay = QVBoxLayout(d)
    tb = QTextBrowser()
    tb.setHtml(html)
    lay.addWidget(tb)
    bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    bb.rejected.connect(d.reject)
    lay.addWidget(bb)
    d.exec()
