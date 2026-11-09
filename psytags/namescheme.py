"""Folder and file names built from chips: no format language, nothing to type."""
from __future__ import annotations

import json
import re

from . import config, convert
from .i18n import tr

FOLDER = "/"
DATA = {"albumartist": "Albuminterpret", "year": "Jahr", "album": "Album", "track": "Track",
        "disc": "Disc", "artist": "Interpret", "title": "Titel"}
SEPARATORS = {" - ": "–", "-": "-", "(": "(", ")": ")", "[": "[", "]": "]", " ": "Abstand", "_": "_", ".": "."}
DEFAULT = ["albumartist", " - ", "(", "year", ")", " - ", "album", FOLDER,
           "track", "-", "disc", " - ", "artist", " - ", "title"]

_FIELDS = {"albumartist": ("ALBUMARTIST", "ARTIST"), "year": ("YEAR", "ORIGYEAR"), "album": ("ALBUM",),
           "track": ("TRACK",), "disc": ("DISCNUMBER",), "artist": ("ARTIST", "ALBUMARTIST"), "title": ("TITLE",)}
_CLOSING = {"(": ")", "[": "]"}
_OPENING = set(_CLOSING)
_BRACKETS = _OPENING | set(_CLOSING.values())


def label(token: str) -> str:
    if token == FOLDER:
        return tr("Neuer Ordner")
    if token in DATA:
        return tr(DATA[token])
    return tr(SEPARATORS[token]) if token == " " else SEPARATORS[token]


def value(track, token: str) -> str:
    """The cleaned text of a data chip: characters a file name cannot hold are replaced."""
    values = next((v for v in (track.get(name) for name in _FIELDS[token]) if v), [])
    text = ", ".join(v for v in values if v).strip()
    number = re.match(r"\d+", text) if token == "track" else None     # before "/" goes: "3/10" is 03
    if number:
        return number.group(0).zfill(2)
    for bad, good in convert.FILENAME_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text[:4] if token == "year" else text.strip()


def _is_sep(part: tuple[bool, str]) -> bool:
    return not part[0]


def _join(tokens: list[str], track) -> str:
    """Values and separators of one folder or file name. Separators around an empty value
    disappear, so a missing year never leaves "()" or a doubled " - " behind."""
    parts = [(True, value(track, t)) if t in DATA else (False, t) for t in tokens]
    keep = [True] * len(parts)
    for i, (is_value, text) in enumerate(parts):
        if is_value and not text:
            keep[i] = False
            if 0 < i < len(parts) - 1 and _CLOSING.get(parts[i - 1][1]) == parts[i + 1][1] \
                    and _is_sep(parts[i - 1]) and _is_sep(parts[i + 1]):
                keep[i - 1] = keep[i + 1] = False
    parts = [p for p, k in zip(parts, keep) if k]
    collapsed: list[tuple[bool, str]] = []
    for part in parts:                                  # of several separators in a row the longest stays
        previous = collapsed[-1] if collapsed else None
        if previous and _is_sep(part) and _is_sep(previous) and part[1] not in _BRACKETS and previous[1] not in _BRACKETS:
            if len(part[1]) > len(previous[1]):
                collapsed[-1] = part
        else:
            collapsed.append(part)
    while collapsed and _is_sep(collapsed[0]) and collapsed[0][1] not in _OPENING:
        collapsed.pop(0)
    while collapsed and _is_sep(collapsed[-1]) and collapsed[-1][1] not in _CLOSING.values():
        collapsed.pop()
    if not any(is_value for is_value, _text in collapsed):
        return ""
    return "".join(text for _is_value, text in collapsed)


def segments(track, tokens: list[str]) -> list[str]:
    """Folder names, then the file name; parts without any value are left out."""
    out, current = [], []
    for token in list(tokens) + [FOLDER]:
        if token == FOLDER:
            text = _join(current, track)
            if text:
                out.append(text)
            current = []
        else:
            current.append(token)
    return out


def target_path(track, tokens: list[str]) -> str:
    return convert.place(track, segments(track, tokens))


# ---------------------------------------------------------------------------
# settings

def load() -> list[str]:
    raw = config.settings().value("rename/scheme", "")
    try:
        tokens = json.loads(raw) if raw else None
    except (TypeError, ValueError):
        tokens = None
    known = set(DATA) | set(SEPARATORS) | {FOLDER}
    if not isinstance(tokens, list) or not tokens or not all(t in known for t in tokens):
        return list(DEFAULT)
    return tokens


def save(tokens: list[str]) -> None:
    config.settings().setValue("rename/scheme", json.dumps(tokens))


def cleanup_enabled() -> bool:
    return config.settings().value("rename/cleanup", False) in (True, "true")


def set_cleanup(on: bool) -> None:
    config.settings().setValue("rename/cleanup", on)
