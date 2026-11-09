"""Automatic album choice from a tag source: candidates, lookups, and what gets written."""
from __future__ import annotations

import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from ..albumorder import is_disc_folder
from ..i18n import tr
from . import albummatch, coverfetch, http, runner, srcfile
from .albummatch import Decision, FileInfo, Match, Release

MAX_CANDIDATES = 8
_INC = "?inc=artists+artist-credits+labels+recordings+release-groups+isrcs&fmt=json"
_INTERVAL = 1.1                         # MusicBrainz allows one request per second
_lock = threading.Lock()
_last_call = [0.0]


def _first(track, name: str) -> str:
    values = track.get(name)
    return values[0] if values else ""


def _polite(call: Callable, retries: int = 4):
    """One request per second; a busy server (HTTP 503) gets a few more tries."""
    for attempt in range(retries + 1):
        with _lock:
            wait = _last_call[0] + _INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.monotonic()
        try:
            return call()
        except http.FetchError as e:
            if "503" not in str(e) or attempt == retries:
                raise
            with http.activity(tr("MusicBrainz ist ausgelastet, neuer Versuch gleich")):
                time.sleep(4)


def track_count(row: dict) -> int | None:
    m = re.match(r"\s*(\d+)", row.get("Tracks", ""))
    return int(m.group(1)) if m else None


def is_digital(row: dict) -> bool:
    return "digital" in row.get("Format", "").lower()


def digital_first(rows: list[dict], n_files: int) -> list[dict]:
    """Search results with digital editions of the right size on top; otherwise unchanged."""
    return sorted(rows, key=lambda r: not (is_digital(r) and track_count(r) == n_files))


def candidate_rows(matches: list, n_files: int, mbid: str = "") -> list[dict]:
    """Releases worth a lookup: a track count that can work, no leftover files first,
    digital editions first within that. An ID from the tags is one more candidate."""
    lowest = n_files - min(albummatch.MAX_LEFTOVERS, n_files // 4)
    fit = [m.row for m in matches
           if (c := track_count(m.row)) is not None and lowest <= c <= n_files]
    fit.sort(key=lambda r: (track_count(r) != n_files, not is_digital(r)))
    if mbid and not any(mbid.lower() in r.get("_url", "").lower() for r in fit):
        fit.insert(0, {"_url": mbid + _INC})
    return fit[:MAX_CANDIDATES]


def file_infos(tracks: list) -> list[FileInfo]:
    out = []
    for t in tracks:
        artist = _first(t, "ARTIST") or _first(t, "ALBUMARTIST")
        length = getattr(getattr(t.data, "info", None), "length", 0) or 0
        out.append(albummatch.file_info(t, _first(t, "TITLE"), t.filename, artist, length))
    return out


def to_release(album: runner.Album, row: dict, tight: bool = False) -> Release:
    n = album.tracks
    lengths = [albummatch.seconds(album.lengths[i]) if i < len(album.lengths) else None for i in range(n)]
    return Release(album, [album.value("TITLE", i) for i in range(n)], lengths,
                   album.value("YEAR", 0)[:4], is_digital(row), tight)


@dataclass
class AutoResult:
    match: Match | None
    reason: str = ""

    @property
    def album(self) -> runner.Album | None:
        return self.match.release.key if self.match else None


class _WithAlbum:
    """A track whose ALBUM reads differently, to fill a search form with another title."""

    def __init__(self, track, album: str):
        self._track, self._album = track, album

    def field(self, name: str) -> list[str]:
        return [self._album] if name.upper() == "ALBUM" else self._track.field(name)

    def __getattr__(self, name: str):
        return getattr(self._track, name)


def _title_steps(album: str) -> list[str]:
    """Further titles to search: first without edition notes, then without notes like "(Live)"."""
    steps = []
    base = albummatch.base_title(album)
    if base and base != album.strip():
        steps.append(base)
    bare = albummatch.base_title(album, True)
    if bare and bare != base:
        steps.append(bare)
    return steps


def _values_for(src: srcfile.Source, tracks: list, title: str) -> list[str]:
    return runner.prefill(src, [_WithAlbum(tracks[0], title)])


def fallback_searches(src: srcfile.Source, tracks: list) -> list[list[str]]:
    """Search values without the notes behind the album title, most specific first."""
    return [_values_for(src, tracks, title) for title in _title_steps(_first(tracks[0], "ALBUM"))]


def search_rows(src: srcfile.Source, values: list[str]) -> list[dict]:
    return _polite(lambda: runner.run_index(src, values))


def needs_second_search(rows: list[dict], tracks: list) -> bool:
    """True if the results contain nothing that looks like this album."""
    artist = _first(tracks[0], "ALBUMARTIST") or _first(tracks[0], "ARTIST")
    return not coverfetch.rank(rows, _first(tracks[0], "ALBUM"), artist, len(tracks))


def find_album(src: srcfile.Source, tracks: list) -> AutoResult:
    """Search and decide; if that fails, again without the notes behind the album title.
    Raises http.FetchError or runner.ScriptError."""
    album = _first(tracks[0], "ALBUM")
    if not album:
        return AutoResult(None, tr("Kein Album-Tag"))
    result = _search(src, tracks, album, runner.prefill(src, tracks), album)
    for title in _title_steps(album):
        if result.match is not None:
            break
        step = _search(src, tracks, title, _values_for(src, tracks, title), album)
        result = step if step.match is not None else AutoResult(None, step.reason or result.reason)
    return result


_KINDS = {"live": ("live",), "remix": ("remix", "remixes"), "demo": ("demo", "demos")}


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _fits_album(found: runner.Album, album: str, artist: str) -> bool:
    """Same artist, and a title that says "(Live)" never lands on a release of another kind."""
    if not albummatch.same_artist(found.value("ALBUMARTIST", 0), artist):
        return False
    note = albummatch.recording_note(album)
    if not note:
        return True
    forms = next((f for f in _KINDS.values() if note in f), (note,))
    return bool((_words(found.value("MUSICBRAINZ_ALBUMTYPE", 0)) | _words(found.value("ALBUM", 0))) & set(forms))


def _needs_tight_lengths(found: runner.Album, album: str) -> bool:
    """A live release for files whose album tag does not say so: only the lengths can tell
    whether these really are the live recordings and not the studio songs."""
    kind_of_release, in_tag = _words(found.value("MUSICBRAINZ_ALBUMTYPE", 0)), _words(album)
    return any(kind_of_release & set(f) and not in_tag & set(f) for f in _KINDS.values())


def _search(src: srcfile.Source, tracks: list, title: str, values: list[str], album: str) -> AutoResult:
    artist = _first(tracks[0], "ALBUMARTIST") or _first(tracks[0], "ARTIST")
    rows = search_rows(src, values)
    matches = coverfetch.rank(rows, title, artist, len(tracks))
    releases = []
    candidates = candidate_rows(matches, len(tracks), _first(tracks[0], "MUSICBRAINZ_ALBUMID"))
    for number, row in enumerate(candidates, 1):
        url, prev = runner.album_target(src, row)
        with http.activity(tr("Ausgabe {1} von {2}", number, len(candidates))):
            found = _polite(lambda: runner.run_album(src, url, prev))
        if _fits_album(found, album, artist):
            releases.append(to_release(found, row, _needs_tight_lengths(found, album)))
    d: Decision = albummatch.decide(file_infos(tracks), releases, _first(tracks[0], "YEAR")[:4])
    return AutoResult(d.match, d.reason)


def release_year(match: Match) -> str:
    album = match.release.key
    return match.release.year or album.value("ORIGYEAR", 0)[:4]


def release_label(match: Match) -> str:
    """ "Album (Year)", without brackets if the release has no date at all."""
    album, year = match.release.key.value("ALBUM", 0), release_year(match)
    return f"{album} ({year})" if year else album


def plan_for(match: Match, disabled: set[str]) -> list[tuple[object, dict[str, str]]]:
    """(file, {field: value}) like the adjust dialog would produce them."""
    album = match.release.key
    names = [k for k in album.fields if k not in disabled]
    out = []
    for f, t in sorted(match.mapping.items(), key=lambda item: item[1]):
        vals = {k: album.value(k, t) for k in names}
        out.append((match.files[f].key, {k: v for k, v in vals.items() if v != "" or k not in album.per_track}))
    return out


def prealign(tracks: list, album: runner.Album) -> list:
    """Files in the order of the source's tracks, as far as the titles tell; the rest fills the
    free slots, and what is left over stands behind the last track."""
    n = max(album.tracks, 1)
    infos = file_infos(tracks)
    release = Release(None, [album.value("TITLE", i) for i in range(album.tracks)],
                      [albummatch.seconds(v) for v in album.lengths[:album.tracks]])
    slots: list = [None] * n
    placed: set[int] = set()
    for f, t, s in albummatch.align(infos, release):
        if s >= albummatch.THRESHOLD:
            slots[t] = tracks[f]
            placed.add(f)
    rest = [t for i, t in enumerate(tracks) if i not in placed]
    for i in range(n):
        if slots[i] is None and rest:
            slots[i] = rest.pop(0)
    return slots + rest


def group_albums(tracks: list) -> list[list]:
    """One album per folder and album name; disc folders (CD1, Disc 2) of an album belong
    together. Album folders side by side never merge."""
    groups: dict[tuple, list] = {}
    for t in tracks:
        folder, album = t.folder, _first(t, "ALBUM")
        if is_disc_folder(folder):
            key = (os.path.dirname(folder), album, "discs")
        else:
            key = (folder, album)
        groups.setdefault(key, []).append(t)
    return list(groups.values())


def album_title(tracks: list) -> str:
    t = tracks[0]
    album = _first(t, "ALBUM")
    artist = _first(t, "ALBUMARTIST") or _first(t, "ARTIST")
    return f"{artist} - {album}" if artist and album else album or os.path.basename(t.folder)


@dataclass
class BatchEntry:
    title: str
    tracks: list
    ok: bool
    detail: str
    leftovers: list = field(default_factory=list)
    cover: str | None = None           # cover source: None did not run, "" worked, else why not
    genres: str | None = None          # Last.fm: same meaning
    cover_seen: list | None = None     # the front covers when the cover step failed
