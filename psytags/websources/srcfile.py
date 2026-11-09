"""Parsing of Web Sources Framework files (.src with optional [Include]=*.inc)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

_KEY = re.compile(r"^\[([A-Za-z0-9_]+)\]=(.*)$")


@dataclass
class SearchField:
    label: str          # label in the search dialog
    fmt: str            # format string evaluated on the first selected file
    url_part: str       # appended to IndexUrl; %s = encoded search text


@dataclass
class Source:
    path: str
    name: str                       # menu name (from file name, `#` = submenu)
    keys: dict[str, str] = field(default_factory=dict)
    index_script: list[str] | None = None
    album_script: list[str] | None = None

    def get(self, key: str, default: str = "") -> str:
        return self.keys.get(key.lower(), default)

    @property
    def search_fields(self) -> list[SearchField]:
        raw = self.get("searchby")
        if not raw:
            return [SearchField("Suche", "$if2(%albumartist%,%artist%) %album%", "%s")]
        parts = raw.split("||")
        if len(parts) < 3:
            # legacy single-field form: label||format  or just a format
            return [SearchField(parts[0] if len(parts) > 1 else "Suche",
                                parts[-1] if len(parts) > 1 else parts[0], "%s")]
        out = []
        for i in range(0, len(parts) - 2, 3):
            out.append(SearchField(parts[i], parts[i + 1], parts[i + 2]))
        return out

    @property
    def index_columns(self) -> list[str]:
        fmt = self.get("indexformat")
        return [c.strip("%") for c in fmt.split("|")] if fmt else []


def load(path: str, name: str | None = None) -> Source:
    src = Source(path, name or os.path.splitext(os.path.basename(path))[0])
    lines = _read_with_includes(path, set())
    current: list[str] | None = None
    for raw in lines:
        line = raw.rstrip("\r\n")
        m = _KEY.match(line)
        if m and not line.startswith((" ", "\t")):
            key, val = m.group(1).lower(), m.group(2)
            if key in ("parserscriptindex", "parserscriptalbum") and val.strip() == "...":
                current = []
                if key == "parserscriptindex":
                    src.index_script = current
                else:
                    src.album_script = current
                continue
            current = None
            src.keys[key] = val
            continue
        if current is not None:
            current.append(line)
    return src


def _read_with_includes(path: str, seen: set[str]) -> list[str]:
    real = os.path.realpath(path)
    if real in seen:
        return []
    seen.add(real)
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return []
    out: list[str] = []
    for line in text.splitlines():
        m = _KEY.match(line.strip())
        if m and m.group(1).lower() == "include":
            inc = m.group(2).strip()
            inc_path = inc if os.path.isabs(inc) else os.path.join(os.path.dirname(path), inc)
            out.extend(_read_with_includes(inc_path, seen))
            continue
        out.append(line)
    return out
