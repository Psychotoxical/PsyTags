"""Discogs as the second tag source: it steps in when MusicBrainz leaves an album open.

Only texts come from here, never pictures: the images on Discogs are mostly photos by users.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse
from typing import Callable

from .. import config
from ..i18n import tr
from . import http
from .base import Album

API = "https://api.discogs.com"
SETTING = "discogs/token"
_INTERVAL = 1.05                        # Discogs allows 60 requests a minute with a token
_BUSY_WAIT = 30.0
_NUMBER_SUFFIX = re.compile(r"\s*\(\d+\)$")
_DISC_AND_TRACK = re.compile(r"^(?:[a-z]+\s*)?(\d+)[-.](\d+)$", re.IGNORECASE)
_MUSICBRAINZ_FIELDS = ("MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_RELEASEGROUPID", "MUSICBRAINZ_ALBUMARTISTID",
                       "MUSICBRAINZ_ALBUMTYPE", "MUSICBRAINZ_ALBUMRELEASECOUNTRY", "MUSICBRAINZ_TRACKID",
                       "MUSICBRAINZ_ARTISTID")
_lock = threading.Lock()
_last_call = [0.0]


def _polite(call: Callable, retries: int = 3):
    """One request per interval; "too many requests" (HTTP 429) gets a few more tries."""
    for attempt in range(retries + 1):
        with _lock:
            wait = _last_call[0] + _INTERVAL - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            _last_call[0] = time.monotonic()
        try:
            return call()
        except http.FetchError as e:
            if "HTTP 429" not in str(e) or attempt == retries:
                raise
            with http.activity(tr("Discogs ist ausgelastet, neuer Versuch gleich")):
                time.sleep(_BUSY_WAIT)


def _get(url: str, token: str) -> dict:
    headers = {"Authorization": f"Discogs token={token}"}      # a header: addresses end up in messages
    try:
        data = json.loads(_polite(lambda: http.fetch(url, headers=headers)))
    except ValueError as e:
        raise http.FetchError(tr("Discogs hat keine lesbare Antwort geliefert")) from e
    except http.NotFound:
        raise
    except http.FetchError as e:
        if "HTTP 401" in str(e):
            raise http.FetchError(tr("Discogs lehnt den Token ab")) from e
        raise
    if not isinstance(data, dict):
        raise http.FetchError(tr("Discogs hat keine lesbare Antwort geliefert"))
    return data


def verify_token(token: str) -> None:
    """Raises http.FetchError when Discogs does not take the token."""
    url = f"{API}/oauth/identity"
    http._cache.pop(url, None)          # the answer depends on the token, the address does not
    _get(url, token)


def _text(value) -> str:
    """Discogs texts can carry stray tabs and spaces."""
    return "" if value is None else " ".join(str(value).split())


def _clean_name(name: str) -> str:
    """Discogs tells artists of the same name apart: "Black Tiger (3)", and marks others with "*"."""
    return _NUMBER_SUFFIX.sub("", _text(name).strip().rstrip("*")).strip()


def _artists(entries: list | None) -> str:
    out = ""
    entries = entries or []
    for i, entry in enumerate(entries):
        out += _clean_name(entry.get("name"))
        join = _text(entry.get("join")).strip()
        if join and i < len(entries) - 1:
            out += ", " if join == "," else f" {join} "
    return out


def _row(result: dict) -> dict[str, str]:
    artist, _sep, album = _text(result.get("title")).partition(" - ")
    formats = result.get("format") or []
    labels = result.get("label") or []
    return {
        "_preview": f"https://www.discogs.com/release/{_text(result.get('id'))}",
        "_url": _text(result.get("id")),
        "Artist": _clean_name(artist),
        "Album": album.strip(),
        "Tracks": "",                   # the search does not tell
        "Year": _text(result.get("year")),
        "Country": _text(result.get("country")),
        "Format": ", ".join("Digital Media" if f == "File" else _text(f) for f in formats),
        "Publisher": _text(labels[0]) if labels else "",
        "CatNo": _text(result.get("catno")),
    }


def _year(data: dict) -> str:
    return _text(data.get("year") or "") if data.get("year") else _text(data.get("released"))[:4]


def _date(data: dict) -> str:
    """Release date as far as Discogs knows it; "00" stands for an unknown month or day."""
    parts = _text(data.get("released")).split("-")
    while len(parts) > 1 and parts[-1].strip("0") == "":
        parts.pop()
    date = "-".join(parts)
    return date if re.match(r"\d{4}", date) else _year(data)


def _positions(tracks: list[dict]) -> tuple[list[int], list[int]]:
    """Disc and running number of each track; vinyl sides and plain numbers are one disc."""
    discs = []
    for track in tracks:
        m = _DISC_AND_TRACK.match(_text(track.get("position")).strip())
        discs.append(int(m.group(1)) if m else 1)
    numbers, seen = [], {}
    for disc in discs:
        seen[disc] = seen.get(disc, 0) + 1
        numbers.append(seen[disc])
    return discs, numbers


def _parse_album(release: dict, first_year: str) -> Album:
    tracks = [t for t in release.get("tracklist") or [] if t.get("type_", "track") != "heading"]
    album_artist = _artists(release.get("artists"))
    labels = release.get("labels") or []
    barcode = next((_text(i.get("value")) for i in release.get("identifiers") or [] if i.get("type") == "Barcode"), "")
    numbers = [_text(l.get("catno")) for l in labels if _text(l.get("catno")).casefold() not in ("", "none")]
    common = {
        "ALBUM": _text(release.get("title")),
        "ALBUMARTIST": album_artist,
        "YEAR": _date(release),
        "ORIGYEAR": first_year or _year(release),
        "PUBLISHER": ", ".join(_clean_name(l.get("name")) for l in labels),
        "CATALOGNUMBER": ", ".join(numbers),
        "BARCODE": barcode,
        "DISCOGS_RELEASE_ID": _text(release.get("id")),     # marks the album as tagged from Discogs
    }
    discs, numbers_on_disc = _positions(tracks)
    several = len(set(discs)) > 1
    rows: dict[str, list[str]] = {
        "TITLE": [_text(t.get("title")) for t in tracks],
        "ARTIST": [_artists(t.get("artists")) or album_artist for t in tracks],
        "TRACK": [f"{n}/{discs.count(d)}" for d, n in zip(discs, numbers_on_disc)],
        "DISCNUMBER": [f"{d}/{len(set(discs))}" if several else "" for d in discs],
    }
    album = Album(tracks=len(tracks), lengths=[_text(t.get("duration")).strip() for t in tracks])
    album.fields = {k: [v] for k, v in common.items() if v}
    album.fields.update({name: [""] for name in _MUSICBRAINZ_FIELDS})     # IDs of an earlier tagging would now be wrong
    for name, values in rows.items():
        if any(values):
            album.fields[name] = values
            album.per_track.add(name)
    return album


class Source:
    name = "Discogs"
    search_fields = ("Album", "Interpret")
    index_columns = ("Artist", "Album", "Year", "Country", "Format", "Publisher", "CatNo")

    def __init__(self, token: str):
        self.token = token

    def prefill(self, tracks: list, album: str | None = None) -> list[str]:
        if not tracks:
            return ["", ""]
        t = tracks[0]
        title = (t.field("ALBUM") or [""])[0] if album is None else album
        artist = (t.field("ALBUMARTIST") or t.field("ARTIST") or [""])[0]
        return [title.strip(), artist.strip()]

    def search(self, values: list[str]) -> list[dict[str, str]]:
        album, artist = (list(values) + ["", ""])[:2]
        query = urllib.parse.urlencode({"release_title": album, "artist": artist, "type": "release", "per_page": 50})
        return [_row(r) for r in _get(f"{API}/database/search?{query}", self.token).get("results") or []]

    def album(self, row: dict[str, str]) -> Album:
        release = _get(f"{API}/releases/{row.get('_url', '')}", self.token)
        return _parse_album(release, self._first_year(release))

    def _first_year(self, release: dict) -> str:
        master = release.get("master_id")
        if not master:
            return ""
        try:
            return _year(_get(f"{API}/masters/{master}", self.token))
        except http.NotFound:
            return ""

    def cover(self, album: Album) -> bytes | None:
        return None


def from_settings() -> Source | None:
    """The source with the stored token, None without one."""
    token = _text(config.settings().value(SETTING, "")).strip()
    return Source(token) if token else None
