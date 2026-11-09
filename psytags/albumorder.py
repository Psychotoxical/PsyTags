"""Order of songs within an album: disc, then track, then file name."""
from __future__ import annotations

import os
import re

PLAYLIST_EXT = (".m3u", ".m3u8", ".pls", ".cue")
_DISC_DIR = re.compile(r"^(cd|disc|disk)[\s._-]*\d+$", re.IGNORECASE)


def is_disc_folder(folder: str) -> bool:
    return bool(_DISC_DIR.match(os.path.basename(folder)))


def album_root(folder: str) -> str:
    """The album's folder: a disc folder (CD1, Disc 2) belongs to the one above it."""
    return os.path.dirname(folder) if is_disc_folder(folder) else folder


def natural_key(s: str):
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower())
            for t in re.split(r"(\d+)", s) if t != ""]


def number(value: str) -> int | None:
    """The leading number of "1/2" or "01"; None if there is none."""
    m = re.match(r"\s*(\d+)", value or "")
    return int(m.group(1)) if m else None


def _first(track, name: str) -> str:
    values = track.get(name)
    return values[0] if values else ""


def sort_key(track):
    disc = number(_first(track, "DISCNUMBER"))
    no = number(_first(track, "TRACK"))
    return (1 if disc is None else disc, 0 if no is not None else 1, no or 0, natural_key(track.filename))


def sort_by_folder(tracks: list) -> list:
    """Sorts inside each folder; the folders keep their order."""
    groups: dict[str, list] = {}
    for t in tracks:
        groups.setdefault(t.folder, []).append(t)
    return [t for group in groups.values() for t in sorted(group, key=sort_key)]


def loaded_order(tracks: list, paths: list[str]) -> list:
    """Order of freshly loaded files; a playlist keeps its own order."""
    if any(p.lower().endswith(PLAYLIST_EXT) for p in paths):
        return list(tracks)
    return sort_by_folder(tracks)
