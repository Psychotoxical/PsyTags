"""Settings. Columns, tag panel fields and custom values live in numbered INI files."""
from __future__ import annotations

import configparser
import os
import re
from dataclasses import dataclass, field, asdict

from PySide6.QtCore import QSettings, QStandardPaths

APP = "PsyTags"
FIELDS = ["TITLE", "ARTIST", "ALBUM", "YEAR", "TRACK", "GENRE", "COMMENT", "ALBUMARTIST",
          "COMPOSER", "DISCNUMBER", "BPM", "PUBLISHER", "CONDUCTOR", "LYRICIST", "ORIGARTIST",
          "ORIGALBUM", "ORIGYEAR", "MOOD", "INITIALKEY", "ISRC", "GROUPING", "SUBTITLE",
          "ENCODEDBY", "COPYRIGHT", "ALBUMSORT", "ARTISTSORT", "TITLESORT", "ALBUMARTISTSORT",
          "COMPOSERSORT", "MEDIATYPE", "LANGUAGE", "UNSYNCEDLYRICS", "MUSICBRAINZ_ALBUMTYPE"]


def config_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericConfigLocation)
    d = os.path.join(base, "psytags")
    os.makedirs(os.path.join(d, "data"), exist_ok=True)
    return d


def data_dir() -> str:
    return os.path.join(config_dir(), "data")


def settings() -> QSettings:
    return QSettings(os.path.join(config_dir(), "psytags.ini"), QSettings.Format.IniFormat)


# ---------------------------------------------------------------------------
# Numbered INI sections: [#0], [#1], ...

def _unescape(s: str) -> str:
    out = []
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            c = s[i + 1]
            if c == "\\":
                out.append("\\")
                i += 2
                continue
            if c == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", s[i + 2:i + 4]):
                out.append(chr(int(s[i + 2:i + 4], 16)))
                i += 4
                continue
            if c == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", s[i + 2:i + 6]):
                out.append(chr(int(s[i + 2:i + 6], 16)))
                i += 6
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _read_sections(path: str) -> list[dict[str, str]]:
    if not os.path.exists(path):
        return []
    cp = configparser.RawConfigParser(strict=False, interpolation=None)
    cp.optionxform = str
    with open(path, encoding="utf-8-sig") as fh:
        cp.read_file(fh)
    secs = [s for s in cp.sections() if s.startswith("#")]
    secs.sort(key=lambda s: int(s[1:]) if s[1:].isdigit() else 0)
    return [{k: _unescape(v) for k, v in cp.items(s)} for s in secs]


def _ini_escape(v) -> str:
    out = []
    for ch in str(v):
        if ch == "\\":
            out.append("\\\\")
        elif ord(ch) > 127 or ord(ch) < 32:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    return "".join(out)


def _write_sections(path: str, items: list[dict]) -> None:
    lines = []
    for i, it in enumerate(items):
        lines.append(f"[#{i}]")
        lines += [f"{k}={_ini_escape(v)}" for k, v in it.items()]
        lines.append("")
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:
        fh.write("\n".join(lines))


@dataclass
class Column:
    name: str
    value: str
    sort: str = ""
    field: str = ""
    width: int = 100
    numeric: bool = False
    enabled: bool = True


@dataclass
class PanelField:
    name: str          # label with & mnemonic
    value: str         # field name, e.g. TITLE, or a format string
    enabled: bool = True
    size: int = 1      # version 0: divisor (1 full, 2 half, 3 third, 4 quarter);
    version: int = 0   # version 1: width in twelfths (12 = full row)
    default: str = ""
    multiline: bool = False

    @property
    def fraction(self) -> float:
        if self.version >= 1:
            return max(1, min(self.size, 12)) / 12
        return 1.0 / max(1, min(self.size, 12))


DEFAULT_COLUMNS = [
    Column("Dateiname", "%_filename_ext%", "%_filename%", "%_filename_ext%", 289),
    Column("Pfad", "%_folderpath%", width=165, enabled=False),
    Column("Tag", "%_tag_read%[ (%_tag%)]", width=217, enabled=False),
    Column("Titel", "$meta_sep(title,\\\\)", field="%title%", width=256),
    Column("Interpret", "$meta_sep(artist,\\\\)", field="%artist%", width=262),
    Column("Album-Interpret", "$meta_sep(albumartist,\\\\)", field="%albumartist%", width=386),
    Column("Album", "$meta_sep(album,\\\\)", field="%album%", width=377),
    Column("Track", "%track%", "$num(%track%,3)", "%track%", 150, True),
    Column("Disc-Nummer", "%discnumber%", "$num(%discnumber%,3)", "%discnumber%", 150, True),
    Column("Jahr", "%year%", field="%year%", width=150),
    Column("Genre", "$meta_sep(genre,\\\\)", field="%genre%", width=150),
    Column("Kommentar", "%comment%", field="%comment%", width=150, enabled=False),
    Column("Länge", "%_length%", "%_length_seconds%", width=60, numeric=True, enabled=False),
    Column("Bitrate", "%_bitrate%", width=60, numeric=True, enabled=False),
    Column("Größe", "%_file_size%", "%_file_size_bytes%", width=80, numeric=True, enabled=False),
    Column("Geändert", "%_file_mod_date%", "%_file_mod_datetime_raw%", width=140, enabled=False),
    Column("Cover", "%_covers%", width=120, enabled=False),
]

DEFAULT_PANEL = [
    PanelField("&Titel", "TITLE"), PanelField("&Interpret", "ARTIST"),
    PanelField("Al&bum", "ALBUM"), PanelField("&Jahr", "YEAR", size=4),
    PanelField("T&rack", "TRACK", size=4), PanelField("&Genre", "GENRE", size=2),
    PanelField("Ko&mmentar", "COMMENT"), PanelField("Album-Interpret", "ALBUMARTIST"),
    PanelField("Komponist", "COMPOSER"), PanelField("Disc-Nummer", "DISCNUMBER", size=3),
    PanelField("&Verzeichnis", "_DIRECTORY"),
    PanelField("Label/Verlag", "PUBLISHER"),
    PanelField("MusicBrainz Album-ID", "MUSICBRAINZ_ALBUMID"),
]


def load_columns() -> list[Column]:
    items = _read_sections(os.path.join(data_dir(), "columns.ini"))
    if not items:
        return [Column(**asdict(c)) for c in DEFAULT_COLUMNS]
    out = []
    for it in items:
        out.append(Column(
            name=it.get("name", ""), value=it.get("value", ""), sort=it.get("sort", ""),
            field=it.get("field", ""), width=int(it.get("width", 100) or 100),
            numeric=it.get("numeric", "0") == "1", enabled=it.get("enabled", "1") == "1"))
    return out


def save_columns(cols: list[Column]) -> None:
    _write_sections(os.path.join(data_dir(), "columns.ini"), [
        {"width": c.width, "numeric": int(c.numeric), "name": c.name, "value": c.value,
         "sort": c.sort, "field": c.field, "enabled": int(c.enabled)} for c in cols])


def load_panel() -> list[PanelField]:
    items = _read_sections(os.path.join(data_dir(), "usrfields.ini"))
    if not items:
        return [PanelField(**asdict(f)) for f in DEFAULT_PANEL]
    return [PanelField(it.get("name", ""), it.get("value", ""), it.get("enabled", "1") == "1",
                       int(it.get("size", 1) or 1), int(it.get("version", 0) or 0),
                       it.get("default", ""), it.get("multiline", "0") == "1") for it in items]


def save_panel(fields: list[PanelField]) -> None:
    items = []
    for f in fields:
        it = {"name": f.name, "value": f.value, "enabled": int(f.enabled), "size": f.size}
        if f.version:
            it.update({"default": f.default, "multiline": int(f.multiline), "version": f.version})
        items.append(it)
    _write_sections(os.path.join(data_dir(), "usrfields.ini"), items)


def load_custom_values() -> dict[str, list[str]]:
    out = {}
    for it in _read_sections(os.path.join(data_dir(), "usrfieldvalues.ini")):
        vals = it.get("custom_values", "").split("\x0b")
        out[it.get("field", "").upper()] = [v for v in vals if v]
    return out


def save_custom_values(values: dict[str, list[str]]) -> None:
    _write_sections(os.path.join(data_dir(), "usrfieldvalues.ini"), [
        {"field": k, "custom_values": "\x0b".join(v), "prefer_tag": 1, "version": 1}
        for k, v in values.items()])


# ---------------------------------------------------------------------------
# Format-string histories (converter dialogs etc.)

DEFAULT_HISTORY = {
    "tag_filename": [
        "%albumartist% - (%year%) - %album%\\$num(%track%,2)%discnumber% - %artist% - %title%",
        "%albumartist% - (%year%) - %album%\\$num(%track%,2) - %artist% - %title%",
        "%artist% - %album% - %track% - %title%",
        "$num(%track%,2). %title%",
        "%artist% - %title%",
    ],
    "filename_tag": ["%artist% - %title%", "%track%. %title%", "%artist% - %album% - %track% - %title%"],
    "filename_filename": ["%artist% - %title%"],
    "tag_tag": ["%title%"],
    "copy_text": ["[%_counter%. ][%artist% - ]['['%album%[ CD%discnumber%][ #$num(%track%,2)]']' ]%title%"],
}


def string_list(s: QSettings, key: str) -> list[str]:
    """List value from QSettings. A one-element list comes back from the INI file as a
    plain string; list() on that would split it into characters."""
    v = s.value(key, [])
    if not v:
        return []
    return [str(x) for x in v] if isinstance(v, (list, tuple)) else [str(v)]


def history(key: str) -> list[str]:
    s = settings()
    v = s.value(f"history/{key}")
    if v is None:
        return list(DEFAULT_HISTORY.get(key, []))
    return list(v) if isinstance(v, (list, tuple)) else [v]


def push_history(key: str, value: str, limit: int = 30) -> None:
    h = [x for x in history(key) if x != value]
    h.insert(0, value)
    settings().setValue(f"history/{key}", h[:limit])


def system_language() -> str:
    """German on a German system, otherwise English: the language before any choice."""
    from PySide6.QtCore import QLocale
    return "de" if QLocale.system().language() == QLocale.Language.German else "en"


@dataclass
class Options:
    """General options."""
    id3_version: int = 3
    write_id3v1: bool = False
    keep_mtime: bool = False
    drop_comments: bool = True
    year_only: bool = True            # tag sources write 2026 instead of 2026-10-11
    mood_level: str = "normal"
    subfolders: bool = True
    save_on_selection_change: bool = True
    confirm_delete: bool = True
    alt_row_colors: bool = True
    language: str = "de"
    theme: str = "mocha"
    extensions: list[str] = field(default_factory=list)

    @classmethod
    def load(cls) -> "Options":
        s = settings()
        o = cls()
        for k, v in asdict(o).items():
            raw = s.value(f"options/{k}")
            if raw is None:
                continue
            if isinstance(v, bool):
                raw = raw in (True, "true", "1", 1)
            elif isinstance(v, int):
                raw = int(raw)
            elif isinstance(v, list):
                raw = list(raw) if isinstance(raw, (list, tuple)) else [raw]
            setattr(o, k, raw)
        if s.value("options/language") is None:
            o.language = system_language()
        return o

    def save(self) -> None:
        s = settings()
        for k, v in asdict(self).items():
            s.setValue(f"options/{k}", v)
