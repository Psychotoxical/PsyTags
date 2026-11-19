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


def track_count(row: dict, n_files: int | None = None) -> int | None:
    """Tracks of a search result. With ``n_files``: of a release with video media only the
    audio tracks, unless there are files for every track (see ``for_files``)."""
    m = re.match(r"\s*(\d+)", row.get("Tracks", ""))
    count = int(m.group(1)) if m else None
    audio = row.get("_audio_tracks", "")
    if audio.isdigit() and n_files is not None and (count is None or n_files < count):
        return int(audio)
    return count


def _dvd_tracks_possible(row: dict, n_files: int) -> bool:
    """More files than the CDs of a release with a DVD have: some may be tracks of the DVD."""
    audio, whole = row.get("_audio_tracks", ""), re.match(r"\s*(\d+)", row.get("Tracks", ""))
    return audio.isdigit() and whole is not None and int(audio) < n_files < int(whole.group(1))


def for_files(album: Album, n_files: int) -> Album:
    """A release with a DVD beside its CDs: the files of a rip are the CDs, so only the audio
    media count. The whole release stays when there are files for every track."""
    slim = album.audio_only
    return slim if slim is not None and n_files < album.tracks else album


def _release_of(album: Album, indexes: list[int]) -> Release:
    return Release(None, [album.value("TITLE", i) for i in indexes],
                   [albummatch.seconds(album.lengths[i]) if i < len(album.lengths) else None for i in indexes])


def _subset(album: Album, indexes: list[int]) -> Album:
    """The tracks ``indexes`` of a release; their numbers stay those of the whole release."""
    out = Album(tracks=len(indexes), cover_url=album.cover_url, partial=True,
                lengths=[album.lengths[i] if i < len(album.lengths) else "" for i in indexes],
                video_tracks=[n for n, i in enumerate(indexes) if i in set(album.video_tracks)])
    out.per_track = set(album.per_track)
    out.fields = {k: [album.value(k, i) for i in indexes] if k in album.per_track else list(v)
                  for k, v in album.fields.items()}
    return out


def with_video_tracks(album: Album, tracks: list) -> Album | None:
    """A release with a DVD beside its CDs and more files than CD tracks: the CD tracks plus
    the DVD tracks whose titles the files without a CD track have. None if no file fits one."""
    slim = album.audio_only
    if slim is None or not album.video_tracks or not slim.tracks < len(tracks) < album.tracks:
        return None
    infos = file_infos(tracks)
    video = album.video_tracks
    cd = [i for i in range(album.tracks) if i not in set(video)]
    on_cd = {f for f, _t, s in albummatch.align(infos, _release_of(album, cd)) if s >= albummatch.THRESHOLD}
    extra = [info for f, info in enumerate(infos) if f not in on_cd]
    fits = [video[t] for _f, t, s in albummatch.align(extra, _release_of(album, video)) if s >= albummatch.THRESHOLD]
    return _subset(album, sorted(cd + fits)) if fits else None


def _leftover_count(tracks: list, album: Album) -> int | None:
    """Files without a track if ``album`` fits the files, None if it does not."""
    m = albummatch.match_release(file_infos(tracks), _release_of(album, list(range(album.tracks))))
    return len(m.leftovers) if isinstance(m, Match) else None


def for_tracks(album: Album, tracks: list) -> Album:
    """``for_files``, but DVD tracks that files fit count as well when that leaves fewer files over."""
    slim = for_files(album, len(tracks))
    dvd = with_video_tracks(album, tracks)
    if dvd is None:
        return slim
    with_dvd, without = _leftover_count(tracks, dvd), _leftover_count(tracks, slim)
    return dvd if with_dvd is not None and (without is None or with_dvd < without) else slim


def is_digital(row: dict) -> bool:
    return "digital" in row.get("Format", "").lower()


def _score(row: dict) -> int:
    m = re.match(r"\s*(\d+)", row.get("Score", ""))
    return int(m.group(1)) if m else 0


def digital_first(rows: list[dict], n_files: int, prefer_digital: bool = True) -> list[dict]:
    """Search results by score; among equal scores, digital editions of the right size on top."""
    if not prefer_digital:
        return sorted(rows, key=lambda r: -_score(r))
    return sorted(rows, key=lambda r: (-_score(r), not (is_digital(r) and track_count(r, n_files) == n_files)))


def candidate_rows(matches: list, n_files: int, mbid: str = "", prefer_digital: bool = True) -> list[dict]:
    """Releases worth a lookup: a track count that can work, no leftover files first,
    digital editions first within that. One track more than files can work too: the search
    counts a hidden track before the first one (pregap). An ID from the tags is one more candidate."""
    lowest = n_files - min(albummatch.MAX_LEFTOVERS, n_files // 4)
    fit = [m.row for m in matches                   # a search may not tell the count: the lookup will
           if (c := track_count(m.row, n_files)) is None or lowest <= c <= n_files + 1
           or _dvd_tracks_possible(m.row, n_files)]
    fit.sort(key=lambda r: (track_count(r, n_files) != n_files, (track_count(r, n_files) or 0) > n_files,
                            prefer_digital and not is_digital(r)))
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


def to_release(album: Album, row: dict, tight: bool = False, prefer_digital: bool = True) -> Release:
    n = album.tracks
    lengths = [albummatch.seconds(album.lengths[i]) if i < len(album.lengths) else None for i in range(n)]
    return Release(album, [album.value("TITLE", i) for i in range(n)], lengths,
                   album.value("YEAR", 0)[:4], prefer_digital and is_digital(row), tight)


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


def find_album(src: TagSource, tracks: list, strict: bool = False, prefer_digital: bool = True) -> AutoResult:
    """Search and decide; if that fails or leaves files without a track, again without the
    notes behind the album title: the words of a note can hide the edition that fits.
    ``strict``: for a source besides MusicBrainz, every track must have a known length.
    ``prefer_digital``: among equally good editions the digital one wins.
    Raises http.FetchError."""
    album = _first(tracks[0], "ALBUM")
    if not album:
        return AutoResult(None, tr("Kein Album-Tag"))
    result = _search(src, tracks, album, src.prefill(tracks), album, strict, prefer_digital)
    for title in _title_steps(album):
        if result.match is not None and not result.match.leftover_keys:
            break
        step = _search(src, tracks, title, src.prefill(tracks, title), album, strict, prefer_digital)
        if step.match is not None and (result.match is None or len(step.match.leftover_keys) < len(result.match.leftover_keys)):
            result = step
        elif result.match is None:
            result = AutoResult(None, step.reason or result.reason)
    return result


def find_with_fallback(src: TagSource, fallbacks: TagSource | list | None, tracks: list,
                       prefer_digital: bool = True) -> tuple[TagSource, AutoResult]:
    """(source that decided, result): the ``fallbacks``, one source or several in order, only
    get the albums ``src`` leaves open. A failure must not end the run: the album stays open
    and the reason says why."""
    result = find_album(src, tracks, prefer_digital=prefer_digital)
    if result.match is not None:
        return src, result
    others = fallbacks if isinstance(fallbacks, list) else [fallbacks] if fallbacks is not None else []
    for second in others:
        try:
            found = find_album(second, tracks, strict=True, prefer_digital=prefer_digital)
        except http.FetchError as e:
            result = AutoResult(None, f"{result.reason} · {str(e).splitlines()[0]}")
            continue
        if found.match is not None:
            return second, found
    return src, result


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


def _search(src: TagSource, tracks: list, title: str, values: list[str], album: str, strict: bool = False,
            prefer_digital: bool = True) -> AutoResult:
    artist = _first(tracks[0], "ALBUMARTIST") or _first(tracks[0], "ARTIST")
    rows = src.search(values)
    matches = coverfetch.rank(rows, title, artist, len(tracks))
    releases = []
    candidates = candidate_rows(matches, len(tracks), "" if strict else _first(tracks[0], "MUSICBRAINZ_ALBUMID"),
                                prefer_digital)
    for number, row in enumerate(candidates, 1):
        with http.activity(tr("Ausgabe {1} von {2}", number, len(candidates))):
            found = for_tracks(src.album(row), tracks)
        if _fits_album(found, album, artist) and (not strict or _all_lengths_known(found)):
            releases.append(to_release(found, row, _needs_tight_lengths(found, album), prefer_digital))
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


def album_folder(tracks: list) -> str:
    """The folder of an album from ``group_albums``; disc folders count as their parent."""
    folder = tracks[0].folder
    return os.path.dirname(folder) if is_disc_folder(folder) else folder


# What one release gives every file alike; a file added to a tagged album may take it over
ALBUM_FIELDS = ("MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_RELEASEGROUPID", "MUSICBRAINZ_ALBUMARTISTID",
                "MUSICBRAINZ_ALBUMTYPE", "MUSICBRAINZ_ALBUMRELEASECOUNTRY", "ALBUMARTIST",
                "ALBUMARTISTSORT", "ORIGYEAR", "YEAR", "ASIN", "CATALOGNUMBER", "PUBLISHER", "BARCODE",
                "COMPILATION")
# Belongs to the artist of a song: only from files of the same artist
ARTIST_FIELDS = ("ARTISTSORT", "MUSICBRAINZ_ARTISTID")


def _shared(tracks: list, name: str) -> list[str]:
    """The value all ``tracks`` have alike, else nothing."""
    values = {tuple(t.get(name)) for t in tracks}
    return list(values.pop()) if len(values) == 1 else []


def album_gaps(tracks: list) -> list[tuple]:
    """Files of an album without a MusicBrainz release while the others have one, e.g. bonus
    tracks added later: (file, values from the others). Only empty fields are filled; nothing
    when the tagged files belong to different releases."""
    tagged = [t for t in tracks if _first(t, "MUSICBRAINZ_ALBUMID")]
    bare = [t for t in tracks if not _first(t, "MUSICBRAINZ_ALBUMID")]
    if not tagged or not bare or len({_first(t, "MUSICBRAINZ_ALBUMID") for t in tagged}) != 1:
        return []
    plan = []
    for t in bare:
        values = {}
        same_artist = [s for s in tagged if s.get("ARTIST") == t.get("ARTIST")]
        for names, source in ((ALBUM_FIELDS, tagged), (ARTIST_FIELDS, same_artist)):
            for name in names:
                shared = _shared(source, name) if source else []
                if shared and not t.get(name):
                    values[name] = shared
        plan.append((t, values))
    return plan


def attach_strays(entries: list) -> list:
    """A few files the run could not place, in the folder of an album it finished (a bonus track
    whose album tag differs, say), are that album's files without a track and not an album of
    their own; left alone, they would stay unnoticed beside the renamed album. A folder with two
    finished albums keeps its open rows: it is not clear which album they belong to."""
    finished: dict[str, list] = {}
    for e in entries:
        if e.ok and e.tracks:
            finished.setdefault(album_folder(e.tracks), []).append(e)
    out = []
    for e in entries:
        hosts = finished.get(album_folder(e.tracks), []) if not e.ok and e.tracks else []
        if len(hosts) == 1 and len(e.tracks) <= albummatch.MAX_LEFTOVERS:
            hosts[0].leftovers.extend(t for t in e.tracks if not any(t is x for x in hosts[0].leftovers))
            continue
        out.append(e)
    return out


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
    genres_seen: list | None = None    # the genres when the genre step failed
    source: str = ""                   # the tag source that tagged the album
