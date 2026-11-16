"""MusicBrainz as a tag source: search releases, load one release, load its cover."""
from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
import urllib.parse
from typing import Callable

from ..i18n import tr
from . import coverart, http
from .base import Album

API = "https://musicbrainz.org/ws/2/release/"
_INC = "?inc=artists+artist-credits+labels+recordings+release-groups+isrcs&fmt=json"
_INTERVAL = 1.1                         # MusicBrainz allows one request per second
_QUERY_SYNTAX = re.compile(r'[+!(){}\[\]^"~*?:\\]')
# Media that carry a film: their tracks are no audio files
_VIDEO_FORMATS = {"dvd", "dvd-video", "blu-ray", "blu-ray-r", "hd-dvd", "vhs", "betamax", "vcd", "svcd",
                  "laserdisc", "ced", "vhd", "umd"}
_lock = threading.Lock()
_last_call = [0.0]


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


def _get(url: str) -> dict:
    try:
        data = json.loads(_polite(lambda: http.fetch(url)))
    except ValueError as e:
        raise http.FetchError(tr("MusicBrainz hat keine lesbare Antwort geliefert")) from e
    if not isinstance(data, dict):
        raise http.FetchError(tr("MusicBrainz hat keine lesbare Antwort geliefert"))
    return data


def _encode(value: str) -> str:
    words = unicodedata.normalize("NFC", value.strip()).split()
    return "+".join(urllib.parse.quote(w, safe="-_.~", encoding="utf-8", errors="replace") for w in words)


def _text(value) -> str:
    return "" if value is None else str(value)


def _credits(entries: list | None) -> tuple[str, str, str]:
    """(names, sort names, artist IDs) of an artist credit."""
    names = sorts = ids = join = ""
    for entry in entries or []:
        artist = entry.get("artist") or {}
        names += join + _text(entry.get("name"))
        sorts += ("; " if join else "") + _text(artist.get("sort-name"))
        ids += (", " if join else "") + _text(artist.get("id"))
        join = _text(entry.get("joinphrase"))
    return names, sorts, ids


def _is_video(medium: dict) -> bool:
    return _text(medium.get("format")).casefold() in _VIDEO_FORMATS


def _audio_media(media: list) -> list | None:
    """The audio media of a release that also has video media, None if it is not such a mix."""
    audio = [m for m in media if not _is_video(m)]
    return audio if audio and len(audio) < len(media) else None


def _row(release: dict) -> dict[str, str]:
    rid = _text(release.get("id"))
    first_label = (release.get("label-info") or [{}])[0] or {}
    audio = _audio_media(release.get("media") or [])
    row = {
        "_preview": f"https://musicbrainz.org/release/{rid}",
        "_coverurl": f"{coverart.BASE}/release/{rid}/front-250",
        "_url": rid,
        "Score": _text(release.get("score")),
        "Type": _text((release.get("release-group") or {}).get("primary-type")),
        "Artist": _credits(release.get("artist-credit"))[0],
        "Album": _text(release.get("title")),
        "Tracks": _text(release.get("track-count")),
        "Year": _text(release.get("date")),
        "Country": _text(release.get("country")),
        "Format": ", ".join(_text(m.get("format")) for m in release.get("media") or []),
        "Publisher": _text((first_label.get("label") or {}).get("name")),
        "CatNo": _text(first_label.get("catalog-number")),
    }
    if audio:                           # a DVD beside the CDs: what a rip of the CDs has
        row["_audio_tracks"] = _text(sum(m.get("track-count") or 0 for m in audio))
    return row


def _joined(values: list[str]) -> str:
    out = ""
    for value in values:
        out += (", " if out else "") + value
    return out


def _parse_album(release: dict, audio_only: bool = False) -> Album:
    """``audio_only`` leaves out the video media and counts the discs without them."""
    rid = _text(release.get("id"))
    group = release.get("release-group") or {}
    secondary = ", ".join(_text(s) for s in group.get("secondary-types") or [])
    album_artist, album_sort, album_artist_ids = _credits(group.get("artist-credit"))
    labels = release.get("label-info") or []
    common = {
        "MUSICBRAINZ_ALBUMID": rid,
        "ALBUM": _text(release.get("title")),
        "ALBUMARTIST": album_artist,
        "ALBUMARTISTSORT": album_sort,
        "MUSICBRAINZ_ALBUMARTISTID": album_artist_ids,
        "MUSICBRAINZ_RELEASEGROUPID": _text(group.get("id")),
        "MUSICBRAINZ_ALBUMTYPE": _text(group.get("primary-type")) + (f", {secondary}" if secondary else ""),
        "COMPILATION": "1" if secondary == "Compilation" else "",
        "ORIGYEAR": _text(group.get("first-release-date")),
        "ASIN": _text(release.get("asin")),
        "YEAR": _text(release.get("date")),
        "CATALOGNUMBER": _joined([_text(l.get("catalog-number")) for l in labels]),
        "PUBLISHER": _joined([_text((l.get("label") or {}).get("name")) for l in labels]),
        "MUSICBRAINZ_ALBUMRELEASECOUNTRY": _text(release.get("country")),
        "BARCODE": _text(release.get("barcode")),
    }
    every = release.get("media") or []
    audio = _audio_media(every)
    media = audio if audio_only and audio else every
    rows: dict[str, list[str]] = {k: [] for k in (
        "SETSUBTITLE", "DISCNUMBER", "TRACK", "MUSICBRAINZ_TRACKID", "ISRC", "TITLE",
        "ARTIST", "ARTISTSORT", "MUSICBRAINZ_ARTISTID")}
    lengths: list[str] = []
    for disc, medium in enumerate(media, 1):
        position = disc if audio_only else _text(medium.get("position"))
        for track in medium.get("tracks") or []:
            recording = track.get("recording") or {}
            artist, sort, ids = _credits(recording.get("artist-credit"))
            rows["SETSUBTITLE"].append(_text(medium.get("title")))
            rows["DISCNUMBER"].append(f"{position}/{len(media)}" if len(media) > 1 else "")
            rows["TRACK"].append(f"{_text(track.get('position'))}/{_text(medium.get('track-count'))}")
            rows["MUSICBRAINZ_TRACKID"].append(_text(recording.get("id")))
            rows["ISRC"].append(", ".join(_text(i) for i in recording.get("isrcs") or []))
            rows["TITLE"].append(_text(recording.get("title")))
            rows["ARTIST"].append(artist)
            rows["ARTISTSORT"].append(sort)
            rows["MUSICBRAINZ_ARTISTID"].append(ids)
            lengths.append(_text(recording.get("length")))
    album = Album(tracks=len(rows["TITLE"]), lengths=lengths)
    album.fields = {k: [v] for k, v in common.items() if v}
    album.fields["DISCOGS_RELEASE_ID"] = [""]       # an earlier tagging from Discogs no longer applies
    for name, values in rows.items():
        if any(values):
            album.fields[name] = values
            album.per_track.add(name)
    if (release.get("cover-art-archive") or {}).get("front"):
        album.cover_url = f"{coverart.BASE}/release/{rid}/front"
    if audio and not audio_only:
        album.audio_only = _parse_album(release, True)
    return album


class Source:
    name = "MusicBrainz"
    search_fields = ("Album", "Interpret")
    index_columns = ("Score", "Type", "Artist", "Album", "Tracks", "Year", "Country", "Format", "Publisher", "CatNo")

    def prefill(self, tracks: list, album: str | None = None) -> list[str]:
        if not tracks:
            return ["", ""]
        t = tracks[0]
        title = (t.field("ALBUM") or [""])[0] if album is None else album
        artist = (t.field("ALBUMARTIST") or t.field("ARTIST") or [""])[0]
        return [_QUERY_SYNTAX.sub("", title).strip(), _QUERY_SYNTAX.sub("", artist).strip()]

    def search(self, values: list[str]) -> list[dict[str, str]]:
        album, artist = (list(values) + ["", ""])[:2]
        url = f"{API}?fmt=json&limit=50&query=release:{_encode(album)}%20AND%20artist:%28{_encode(artist)}%29"
        return [_row(r) for r in _get(url).get("releases") or []]

    def album(self, row: dict[str, str]) -> Album:
        return _parse_album(_get(API + row.get("_url", "") + _INC))

    def cover(self, album: Album) -> bytes | None:
        if not album.cover_url:
            return None
        return coverart.fetch_front(album.value("MUSICBRAINZ_ALBUMID", 0))
