"""Automatic album choice from a tag source: candidates, lookups, and what gets written."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from ..albumorder import is_disc_folder
from ..i18n import tr
from . import albummatch, coverfetch, http
from .albummatch import Decision, FileInfo, Match, Release
from .base import Album, TagSource

MAX_CANDIDATES = 8


def _first(track, name: str) -> str:
    values = track.get(name)
    return values[0] if values else ""


def track_count(row: dict) -> int | None:
    m = re.match(r"\s*(\d+)", row.get("Tracks", ""))
    return int(m.group(1)) if m else None


def is_digital(row: dict) -> bool:
    return "digital" in row.get("Format", "").lower()


def _score(row: dict) -> int:
    m = re.match(r"\s*(\d+)", row.get("Score", ""))
    return int(m.group(1)) if m else 0


def digital_first(rows: list[dict], n_files: int) -> list[dict]:
    """Search results by score; among equal scores, digital editions of the right size on top."""
    return sorted(rows, key=lambda r: (-_score(r), not (is_digital(r) and track_count(r) == n_files)))


def candidate_rows(matches: list, n_files: int, mbid: str = "") -> list[dict]:
    """Releases worth a lookup: a track count that can work, no leftover files first,
    digital editions first within that. One track more than files can work too: the search
    counts a hidden track before the first one (pregap). An ID from the tags is one more candidate."""
    lowest = n_files - min(albummatch.MAX_LEFTOVERS, n_files // 4)
    fit = [m.row for m in matches                   # a search may not tell the count: the lookup will
           if (c := track_count(m.row)) is None or lowest <= c <= n_files + 1]
    fit.sort(key=lambda r: (track_count(r) != n_files, (track_count(r) or 0) > n_files, not is_digital(r)))
    if mbid and not any(mbid.lower() in r.get("_url", "").lower() for r in fit):
        fit.insert(0, {"_url": mbid})
    return fit[:MAX_CANDIDATES]


def file_infos(tracks: list) -> list[FileInfo]:
    out = []
    for t in tracks:
        artist = _first(t, "ARTIST") or _first(t, "ALBUMARTIST")
        length = getattr(getattr(t.data, "info", None), "length", 0) or 0
        out.append(albummatch.file_info(t, _first(t, "TITLE"), t.filename, artist, length))
    return out


def to_release(album: Album, row: dict, tight: bool = False) -> Release:
    n = album.tracks
    lengths = [albummatch.seconds(album.lengths[i]) if i < len(album.lengths) else None for i in range(n)]
    return Release(album, [album.value("TITLE", i) for i in range(n)], lengths,
                   album.value("YEAR", 0)[:4], is_digital(row), tight)


@dataclass
class AutoResult:
    match: Match | None
    reason: str = ""

    @property
    def album(self) -> Album | None:
        return self.match.release.key if self.match else None


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


def fallback_searches(src: TagSource, tracks: list) -> list[list[str]]:
    """Search values without the notes behind the album title, most specific first."""
    return [src.prefill(tracks, title) for title in _title_steps(_first(tracks[0], "ALBUM"))]


def needs_second_search(rows: list[dict], tracks: list) -> bool:
    """True if the results contain nothing that looks like this album."""
    artist = _first(tracks[0], "ALBUMARTIST") or _first(tracks[0], "ARTIST")
    return not coverfetch.rank(rows, _first(tracks[0], "ALBUM"), artist, len(tracks))


def find_album(src: TagSource, tracks: list, strict: bool = False) -> AutoResult:
    """Search and decide; if that fails or leaves files without a track, again without the
    notes behind the album title: the words of a note can hide the edition that fits.
    ``strict``: for a source besides MusicBrainz, every track must have a known length.
    Raises http.FetchError."""
    album = _first(tracks[0], "ALBUM")
    if not album:
        return AutoResult(None, tr("Kein Album-Tag"))
    result = _search(src, tracks, album, src.prefill(tracks), album, strict)
    for title in _title_steps(album):
        if result.match is not None and not result.match.leftover_keys:
            break
        step = _search(src, tracks, title, src.prefill(tracks, title), album, strict)
        if step.match is not None and (result.match is None or len(step.match.leftover_keys) < len(result.match.leftover_keys)):
            result = step
        elif result.match is None:
            result = AutoResult(None, step.reason or result.reason)
    return result


def find_with_fallback(src: TagSource, second: TagSource | None, tracks: list) -> tuple[TagSource, AutoResult]:
    """(source that decided, result): ``second`` only gets the albums ``src`` leaves open.
    Its failure must not end the run, the album stays open and the reason says why."""
    result = find_album(src, tracks)
    if result.match is not None or second is None:
        return src, result
    try:
        found = find_album(second, tracks, strict=True)
    except http.FetchError as e:
        return src, AutoResult(None, f"{result.reason} · {str(e).splitlines()[0]}")
    return (second, found) if found.match is not None else (src, result)


_KINDS = {"live": ("live",), "remix": ("remix", "remixes"), "demo": ("demo", "demos")}


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _fits_album(found: Album, album: str, artist: str) -> bool:
    """Same artist, and a title that says "(Live)" never lands on a release of another kind."""
    if not albummatch.same_artist(found.value("ALBUMARTIST", 0), artist):
        return False
    note = albummatch.recording_note(album)
    if not note:
        return True
    forms = next((f for f in _KINDS.values() if note in f), (note,))
    return bool((_words(found.value("MUSICBRAINZ_ALBUMTYPE", 0)) | _words(found.value("ALBUM", 0))) & set(forms))


def _needs_tight_lengths(found: Album, album: str) -> bool:
    """A live release for files whose album tag does not say so: only the lengths can tell
    whether these really are the live recordings and not the studio songs."""
    kind_of_release, in_tag = _words(found.value("MUSICBRAINZ_ALBUMTYPE", 0)), _words(album)
    return any(kind_of_release & set(f) and not in_tag & set(f) for f in _KINDS.values())


def _all_lengths_known(found: Album) -> bool:
    return len(found.lengths) == found.tracks and all(albummatch.seconds(v) for v in found.lengths)


def _search(src: TagSource, tracks: list, title: str, values: list[str], album: str, strict: bool = False) -> AutoResult:
    artist = _first(tracks[0], "ALBUMARTIST") or _first(tracks[0], "ARTIST")
    rows = src.search(values)
    matches = coverfetch.rank(rows, title, artist, len(tracks))
    releases = []
    candidates = candidate_rows(matches, len(tracks), "" if strict else _first(tracks[0], "MUSICBRAINZ_ALBUMID"))
    for number, row in enumerate(candidates, 1):
        with http.activity(tr("Ausgabe {1} von {2}", number, len(candidates))):
            found = src.album(row)
        if _fits_album(found, album, artist) and (not strict or _all_lengths_known(found)):
            releases.append(to_release(found, row, _needs_tight_lengths(found, album)))
    d: Decision = albummatch.decide(file_infos(tracks), releases, _first(tracks[0], "YEAR")[:4])
    return AutoResult(d.match, d.reason)


def release_year(match: Match) -> str:
    album = match.release.key
    return match.release.year or album.value("ORIGYEAR", 0)[:4]


def match_notes(match: Match) -> list[str]:
    """What the overview should say about an accepted release."""
    return [tr("Letzter Track fehlt: {1}", match.release.titles[-1])] if match.missing_last else []


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


def prealign(tracks: list, album: Album) -> list:
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
