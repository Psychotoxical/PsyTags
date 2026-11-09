"""UI language. German texts are the source strings; English via lookup table."""
from __future__ import annotations

_lang = "de"

EN: dict[str, str] = {
    # menus
    "&Datei": "&File", "&Bearbeiten": "&Edit", "A&nsicht": "&View", "&Konverter": "&Convert",
    "&Aktionen": "&Actions", "Tag-&Quellen": "Tag &Sources", "&Hilfe": "&Help",
    "Tag &speichern": "&Save tag", "Tag ent&fernen": "&Remove tag", "Tag &auslesen": "Read &tag",
    "Playlist (alle Dateien)": "Playlist (all files)",
    "Playlist (ausgewählte Dateien)": "Playlist (selected files)",
    "Playlists generieren...": "Generate Playlists...", "&Export...": "&Export...",
    "Verzeichnis wechseln...": "Change &directory...", "Verzeichnis hinzufügen...": "Add directory...",
    "Playlist/Cuesheet öffnen...": "Load Playlist/Cuesheet...", "Standardverzeichnis": "&Favorite directory",
    "Im Dateimanager öffnen": "&Open in file manager", "&Optionen...": "&Options...",
    "Konfiguration sichern...": "Save &configuration...",
    "Konfigurationsordner öffnen": "Open configuration folder",
    "Mp3tag-Konfiguration importieren...": "Import Mp3tag configuration...",
    "&Beenden": "E&xit",
    "&Rückgängig": "&Undo", "&Wiederholen": "&Redo", "Au&sschneiden": "C&ut", "K&opieren": "C&opy",
    "Kopieren als &Text...": "Copy as Text...", "&Einfügen": "&Paste", "S&uchen...": "&Find...",
    "Cover": "Cover", "Umbenennen": "Rename", "Kopieren...": "Copy...", "Verschieben...": "Move...",
    "E&ntfernen": "Re&move", "Löschen...": "Delete...", "&Alle Dateien auswählen": "Select all &files",
    "Auswahl &umkehren": "&Invert selection", "Auswahl auf&heben": "&Unselect all",
    "&Nächste Datei auswählen": "Select &next file",
    "Ähnliche Dateien auswählen": "Select similar files",
    "Nächste ähnliche Dateien auswählen": "Select next similar files",
    "Cover hinzu&fügen...": "&Add cover...", "Cover er&setzen...": "Rep&lace cover...",
    "Cover anpassen...": "Adjust cover...", "Cover entfe&rnen": "&Remove cover",
    "Cover &extrahieren...": "&Extract cover...", "Cover &verwalten...": "&Manage covers...",
    "Cover-&Typ ändern": "Set cover &type", "Cover-&Beschreibung ändern...": "Set cover &description...",
    "Cover in Zwischenablage &ausschneiden": "&Cut cover", "Cover in Zwischenablage kopieren": "Copy cover",
    "Cover aus Zwischenablage einfü&gen": "&Paste cover",
    "&Aktualisieren": "R&efresh", "&Sortieren nach": "&Sort by", "&Zufällig": "&Randomize",
    "&Erweiterte Tags...": "E&xtended Tags...", "&Tag-Panel": "Tag panel", "&Filter": "&Filter",
    "Sym&bolleisten": "Tool&bars", "&Hauptsymbolleiste": "&Main Toolbar",
    "Spalte&n": "&Columns", "Spalten anpassen...": "Customize columns...",
    "&Tag - Dateiname": "&Tag - Filename", "&Dateiname - Tag": "&Filename - Tag",
    "D&ateiname - Dateiname": "F&ilename - Filename", "Te&xtdatei - Tag": "Te&xt file - Tag",
    "Ta&g - Tag": "T&ag - Tag", "Tracknummern-Assistent...": "Auto-numbering wizard...",
    "&Aktionen (Schnell)": "Actions (&Quick)", "Aktionen...": "Actions...",
    "&Hilfethemen": "&Contents...", "&Tastaturkürzel": "&Keyboard Shortcuts", "Über PsyTags...": "About PsyTags...",
    "Utils": "Utils", "Extras": "Tools",
    "Alle &Eingabefelder zurücksetzen": "Restore all &Input fields",
    "Eingabefelder auf Standard&werte": "Default values in input fields",
    "Abspielen": "Play", "Eigenschaften...": "Properties...",
    "ID3v1 entfernen": "Remove ID3v1", "ID3v2 entfernen": "Remove ID3v2", "APEv2 entfernen": "Remove APEv2",
    "Übergeordnetes Verzeichnis": "Up", "Zurück": "Back", "Vorwärts": "Forward",
    # tag panel / widgets
    "Tag-Panel": "Tag Panel", "Filter:": "Filter:", "Bereit": "Ready",
    "< beibehalten >": "< keep >", "< leer >": "< blank >",
    "Unterschiedliche Cover": "Cover varies",
    # dialogs
    "Formatstring:": "Format string:", "Vorschau:": "Preview:", "OK": "OK", "Abbrechen": "Cancel",
    "Alter Dateiname:": "Old filename:", "Neuer Dateiname:": "New filename:",
    "Quell-Formatstring:": "Source format:", "Ziel-Formatstring:": "Target format:",
    "Feld:": "Field:", "Textdatei:": "Text file:",
    "Datei wählen...": "Browse...",
    "Unterverzeichnisse": "Subfolders",
    "Verzeichnis auswählen": "Select directory",
    "Tag-Informationen gespeichert": "Tag information saved",
    "Fehler": "Error",
}

from .i18n_en import EN_MORE  # noqa: E402  (dialogs, messages, tooltips)

for _k, _v in EN_MORE.items():
    EN.setdefault(_k, _v)                     # menu texts above win (they keep their & mnemonics)


def set_language(lang: str) -> None:
    global _lang
    _lang = lang


def language() -> str:
    return _lang


def tr(text: str, *args) -> str:
    s = EN.get(text, text) if _lang == "en" else text
    for i, a in enumerate(args, 1):
        s = s.replace("{%d}" % i, str(a))
    return s
