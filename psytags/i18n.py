"""UI language. German texts are the source strings; English via lookup table."""
from __future__ import annotations

_lang = "de"

EN: dict[str, str] = {
    # menus
    "Tag-&Quellen": "Tag &Sources", "&Hilfe": "&Help",
    "Tag &speichern": "&Save tag", "Tag ent&fernen": "&Remove tag",
    "&Optionen...": "&Options...",
    "&Beenden": "E&xit",
    "&Rückgängig": "&Undo", "&Wiederholen": "&Redo", "K&opieren": "C&opy",
    "&Einfügen": "&Paste", "S&uchen...": "&Find...",
    "Cover": "Cover", "Umbenennen": "Rename",
    "E&ntfernen": "Re&move", "&Alle Dateien auswählen": "Select all &files",
    "Cover hinzu&fügen...": "&Add cover...", "Cover er&setzen...": "Rep&lace cover...",
    "Cover entfe&rnen": "&Remove cover",
    "&Aktualisieren": "R&efresh",
    "&Tag-Panel": "Tag panel",
    "Spalte&n": "&Columns", "Spalten anpassen...": "Customize columns...",
    "Über PsyTags...": "About PsyTags...",
    "Abspielen": "Play",
    # tag panel / widgets
    "Tag-Panel": "Tag Panel", "Bereit": "Ready",
    # dialogs
    "Abbrechen": "Cancel",
    "Feld:": "Field:",
    "Tag-Informationen gespeichert": "Tag information saved",
    "Die Eingaben ließen sich nicht speichern:": "Your changes could not be saved:",
    "Eingaben verwerfen?": "Discard your changes?",
    "Erscheinungsdatum": "Release date",
    "Nur das Jahr": "Year only",
    "Volles Datum": "Full date",
    "Gilt für MusicBrainz und Discogs. „Nur das Jahr“ schreibt 2026 statt 2026-10-11.":
        "Applies to MusicBrainz and Discogs. “Year only” writes 2026 instead of 2026-10-11.",
    "MusicBrainz und Discogs kennen oft das genaue Erscheinungsdatum. "
    "PsyTags kann es ganz übernehmen oder nur das Jahr schreiben.":
        "MusicBrainz and Discogs often know the exact release date. "
        "PsyTags can take it as it is or write only the year.",
    "„Nur das Jahr“ schreibt 2026, „Volles Datum“ 2026-10-11. Das gilt für Jahr und "
    "Original-Jahr. Sie können es später in den Optionen ändern.":
        "“Year only” writes 2026, “Full date” 2026-10-11. This applies to year and original year. "
        "You can change it later in the options.",
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
