"""UI language. The code holds German texts; ``EN`` turns them into English, and English is
the key of every other language: one file per language, ``resources/locales/<code>.json``.
A text a language file lacks shows in English. A value can be an object of CLDR plural forms
("one", "few", "many", "other"), chosen by the first number among the arguments."""
from __future__ import annotations

import json
import os

_lang = "de"
_catalogs: dict[str, dict] = {}

# Code and own name of every language, in the order of the selection lists
LANGUAGES: tuple[tuple[str, str], ...] = (
    ("en", "English"), ("de", "Deutsch"), ("es", "Español"), ("fr", "Français"),
    ("nb", "Norsk bokmål"), ("nl", "Nederlands"), ("ro", "Română"), ("ru", "Русский"),
    ("zh", "中文"), ("ja", "日本語"), ("hu", "Magyar"), ("pl", "Polski"),
    ("bg", "Български"), ("it", "Italiano"), ("uk", "Українська"), ("el", "Ελληνικά"))
CODES = tuple(code for code, _name in LANGUAGES)
LOCALES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "locales")

EN: dict[str, str] = {
    # menus
    "&Taggen": "&Tagging", "&Manuell suchen": "Search &manually", "Cover &holen": "&Fetch cover",
    "Alle Quellen der Reihe nach": "All sources in order", "&Hilfe": "&Help",
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
    _lang = lang if lang in CODES else "en"


def language() -> str:
    return _lang


def native_name(code: str) -> str:
    return dict(LANGUAGES).get(code, code)


def system_code(name: str) -> str:
    """The language of a locale name such as "pt_BR" or "nb_NO", English if PsyTags lacks it."""
    code = name.replace("-", "_").split("_")[0].lower()
    code = {"no": "nb", "nn": "nb"}.get(code, code)
    return code if code in CODES else "en"


def catalog(code: str) -> dict:
    """The language file of ``code``: English text -> text or plural forms. Empty if there is none."""
    if code not in _catalogs:
        try:
            with open(os.path.join(LOCALES, f"{code}.json"), encoding="utf-8") as fh:
                _catalogs[code] = json.load(fh)
        except (OSError, ValueError):
            _catalogs[code] = {}
    return _catalogs[code]


def plural_form(code: str, n: int) -> str:
    """The CLDR plural category of a whole number ``n`` in language ``code``."""
    n = abs(n)
    if code in ("ja", "zh"):
        return "other"
    if code == "fr":
        return "one" if n in (0, 1) else "other"
    if code in ("ru", "uk", "pl"):
        if n == 1 if code == "pl" else (n % 10 == 1 and n % 100 != 11):
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    if code == "ro":
        if n == 1:
            return "one"
        return "few" if n == 0 or 1 <= n % 100 <= 19 else "other"
    return "one" if n == 1 else "other"


def _pick(value, code: str, args: tuple) -> str:
    if isinstance(value, str):
        return value
    n = next((a for a in args if isinstance(a, int) and not isinstance(a, bool)), None)
    form = plural_form(code, n) if n is not None else "other"
    return value.get(form) or value.get("other") or next(iter(value.values()), "")


def tr(text: str, *args) -> str:
    if _lang == "de":
        s = text
    else:
        english = EN.get(text, text)
        s = _pick(catalog(_lang).get(english, english), _lang, args)
    for i, a in enumerate(args, 1):
        s = s.replace("{%d}" % i, str(a))
    return s
