"""Beatport as a further tag source and cover source, with the user's own API access.

Beatport gives API access only on request: a client ID and secret from Beatport, plus the
user's Beatport login. The login asks once for the password (OAuth password grant) and keeps
only the tokens; the access token lasts some hours and is renewed with the refresh token.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
from typing import Callable

from .. import config
from ..i18n import tr
from . import http
from .base import Album

NAME = "Beatport"
API = "https://api.beatport.com/v4"
SITE = "https://www.beatport.com"
CLIENT_ID = "beatport/client_id"
CLIENT_SECRET = "beatport/client_secret"
USERNAME = "beatport/username"
TOKEN = "beatport/token"                # JSON: access, refresh, expires (seconds since the epoch)
ORIGINAL_MIX = "Original Mix"           # Beatport's name for the plain version: not added to the title
VARIOUS = "Various Artists"
VARIOUS_FROM = 4                        # this many release artists or more make a compilation
_INTERVAL = 0.5
_EARLY = 60.0                           # renew the token this many seconds before it runs out
_MUSICBRAINZ_FIELDS = ("MUSICBRAINZ_ALBUMID", "MUSICBRAINZ_RELEASEGROUPID", "MUSICBRAINZ_ALBUMARTISTID",
                       "MUSICBRAINZ_ALBUMTYPE", "MUSICBRAINZ_ALBUMRELEASECOUNTRY", "MUSICBRAINZ_TRACKID",
                       "MUSICBRAINZ_ARTISTID", "DISCOGS_RELEASE_ID")
_lock = threading.Lock()
_token_lock = threading.Lock()
_last_call = [0.0]


class LoginNeeded(http.FetchError):
    """No usable login: the user has to sign in again under Options."""

    def __init__(self):
        super().__init__(tr("Beatport: bitte unter Optionen → Konten und Quellen anmelden"))


def _value(name: str) -> str:
    return str(config.settings().value(name, "") or "").strip()


def _stored_token() -> dict:
    try:
        token = json.loads(_value(TOKEN) or "{}")
    except ValueError:
        return {}
    return token if isinstance(token, dict) else {}


def configured() -> bool:
    """Client ID, secret and a login are there."""
    return bool(_value(CLIENT_ID) and _value(CLIENT_SECRET) and _stored_token().get("refresh"))


def _save_token(answer: str) -> str:
    try:
        data = json.loads(answer)
        access, refresh, lasts = str(data["access_token"]), str(data["refresh_token"]), float(data["expires_in"])
    except (ValueError, KeyError, TypeError) as e:
        raise http.FetchError(tr("Beatport hat keine lesbare Antwort geliefert")) from e
    config.settings().setValue(TOKEN, json.dumps({"access": access, "refresh": refresh,
                                                  "expires": time.time() + lasts}))
    return access


def login(client_id: str, secret: str, username: str, password: str) -> None:
    """Sign in; keeps client ID, secret, user name and the tokens, never the password.
    Raises http.FetchError when Beatport refuses."""
    try:
        answer = http.post_form(f"{API}/auth/o/token/", {
            "grant_type": "password", "client_id": client_id, "client_secret": secret,
            "username": username, "password": password})
    except http.FetchError as e:
        if any(f"HTTP {code}" in str(e) for code in (400, 401, 403)):
            raise http.FetchError(tr("Beatport lehnt die Anmeldung ab")) from e
        raise
    s = config.settings()
    s.setValue(CLIENT_ID, client_id)
    s.setValue(CLIENT_SECRET, secret)
    s.setValue(USERNAME, username)
    _save_token(answer)


def logout() -> None:
    """Forget the tokens; client ID, secret and user name stay for the next login."""
    config.settings().remove(TOKEN)


def _access_token() -> str:
    """A valid access token, renewed when it runs out. Raises LoginNeeded."""
    with _token_lock:
        token = _stored_token()
        if not (_value(CLIENT_ID) and _value(CLIENT_SECRET) and token.get("refresh")):
            raise LoginNeeded()
        if token.get("access") and float(token.get("expires", 0)) - _EARLY > time.time():
            return str(token["access"])
        try:
            answer = http.post_form(f"{API}/auth/o/token/", {
                "grant_type": "refresh_token", "refresh_token": str(token["refresh"]),
                "client_id": _value(CLIENT_ID), "client_secret": _value(CLIENT_SECRET)})
        except http.ServerError:
            raise
        except http.FetchError as e:
            logout()                    # the refresh token is spent or withdrawn
            raise LoginNeeded() from e
        return _save_token(answer)


def _polite(call: Callable):
    with _lock:
        wait = _last_call[0] + _INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()
    return call()


def _get(path: str, **params) -> dict:
    url = f"{API}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    headers = {"Authorization": f"Bearer {_access_token()}"}      # a header: addresses end up in messages
    try:
        data = json.loads(_polite(lambda: http.fetch(url, headers=headers)))
    except ValueError as e:
        raise http.FetchError(tr("Beatport hat keine lesbare Antwort geliefert")) from e
    except http.NotFound:
        raise
    except http.FetchError as e:
        if "HTTP 401" in str(e):
            raise LoginNeeded() from e
        raise
    if not isinstance(data, dict):
        raise http.FetchError(tr("Beatport hat keine lesbare Antwort geliefert"))
    return data


def _text(value) -> str:
    return "" if value is None else " ".join(str(value).split())


def _names(entries) -> list[str]:
    return [_text(e.get("name")) for e in entries or [] if isinstance(e, dict) and _text(e.get("name"))]


def _album_artist(release: dict) -> str:
    names = _names(release.get("artists"))
    return VARIOUS if len(names) >= VARIOUS_FROM else ", ".join(names)


def _name(entry) -> str:
    return _text(entry.get("name")) if isinstance(entry, dict) else ""


def _image(release: dict) -> str:
    image = release.get("image")
    return _text(image.get("uri")) if isinstance(image, dict) else ""


def _date(release: dict) -> str:
    date = _text(release.get("publish_date") or release.get("new_release_date"))
    return date if date[:4].isdigit() else ""


def _page(kind: str, entry: dict) -> str:
    slug, ident = _text(entry.get("slug")), _text(entry.get("id"))
    return f"{SITE}/{kind}/{slug}/{ident}" if slug and ident else ""


def _row(release: dict) -> dict[str, str]:
    return {
        "_preview": _page("release", release),
        "_url": _text(release.get("id")),
        "_coverurl": _image(release),
        "Artist": _album_artist(release),
        "Album": _text(release.get("name")),
        "Tracks": _text(release.get("track_count")),
        "Year": _date(release)[:4],
        "Format": "Digital Media",
        "Publisher": _name(release.get("label")),
        "CatNo": _text(release.get("catalog_number")),
    }


def title(track: dict) -> str:
    """The name with its mix, as Beatport shows it; the original mix needs no note."""
    name, mix = _text(track.get("name")), _text(track.get("mix_name"))
    return f"{name} ({mix})" if mix and mix.casefold() != ORIGINAL_MIX.casefold() else name


def initial_key(track: dict) -> str:
    """Beatport writes "A Minor" or "Eb Major"; the tag takes "Am" or "Eb"."""
    parts = _name(track.get("key")).split()
    if len(parts) != 2 or parts[1].casefold() not in ("major", "minor"):
        return ""
    return parts[0] + ("m" if parts[1].casefold() == "minor" else "")


def _length(track: dict) -> str:
    ms = track.get("length_ms")
    if isinstance(ms, (int, float)) and ms > 0:
        seconds = int(round(ms / 1000))
        return f"{seconds // 60}:{seconds % 60:02d}"
    return _text(track.get("length"))


def parse_album(release: dict, tracks: list[dict]) -> Album:
    tracks = sorted(tracks, key=lambda t: t.get("number") if isinstance(t.get("number"), int) else 10 ** 6)
    common = {
        "ALBUM": _text(release.get("name")),
        "ALBUMARTIST": _album_artist(release),
        "YEAR": _date(release),
        "PUBLISHER": _name(release.get("label")),
        "CATALOGNUMBER": _text(release.get("catalog_number")),
        "BARCODE": _text(release.get("upc")),
        "BEATPORT_RELEASE_ID": _text(release.get("id")),     # marks the album as tagged from Beatport
    }
    rows: dict[str, list[str]] = {
        "TITLE": [title(t) for t in tracks],
        "ARTIST": [", ".join(_names(t.get("artists"))) or common["ALBUMARTIST"] for t in tracks],
        "TRACK": [f"{i}/{len(tracks)}" for i in range(1, len(tracks) + 1)],
        "BPM": [_text(t.get("bpm")) for t in tracks],
        "INITIALKEY": [initial_key(t) for t in tracks],
        "ISRC": [_text(t.get("isrc")) for t in tracks],
    }
    album = Album(tracks=len(tracks), lengths=[_length(t) for t in tracks], cover_url=_image(release))
    album.fields = {k: [v] for k, v in common.items() if v}
    album.fields.update({name: [""] for name in _MUSICBRAINZ_FIELDS})     # IDs of an earlier tagging would now be wrong
    for name, values in rows.items():
        if any(values):
            album.fields[name] = values
            album.per_track.add(name)
    return album


def _results(answer: dict) -> list[dict]:
    found = answer.get("results")
    return [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []


def search_releases(album: str, artist: str) -> list[dict]:
    answer = _get("/catalog/search/", q=" ".join(v for v in (artist, album) if v), type="releases", per_page=25)
    found = answer.get("releases")
    return [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []


class Source:
    name = NAME
    search_fields = ("Album", "Interpret")
    index_columns = ("Artist", "Album", "Year", "Tracks", "Publisher", "CatNo")

    def prefill(self, tracks: list, album: str | None = None) -> list[str]:
        if not tracks:
            return ["", ""]
        t = tracks[0]
        name = (t.field("ALBUM") or [""])[0] if album is None else album
        artist = (t.field("ALBUMARTIST") or t.field("ARTIST") or [""])[0]
        return [name.strip(), artist.strip()]

    def search(self, values: list[str]) -> list[dict[str, str]]:
        album, artist = (list(values) + ["", ""])[:2]
        return [_row(r) for r in search_releases(album, artist)]

    def album(self, row: dict[str, str]) -> Album:
        ident = row.get("_url", "")
        release = _get(f"/catalog/releases/{ident}/")
        listed = _results(_get(f"/catalog/releases/{ident}/tracks/", per_page=100))
        # the list leaves out details such as the position, so every track is asked for itself
        tracks = [_get(f"/catalog/tracks/{_text(t.get('id'))}/") for t in listed if _text(t.get("id"))]
        return parse_album(release, tracks)

    def cover(self, album: Album) -> bytes | None:
        return http.fetch_bytes(album.cover_url) if album.cover_url else None


class Covers:
    """Beatport in the list of cover sources: the cover of a certain match."""
    name = NAME

    def search(self, artist: str, album: str) -> list[dict]:
        return [{"Album": _text(r.get("name")), "Artist": _album_artist(r), "Tracks": _text(r.get("track_count")),
                 "_preview": _page("release", r), "_image": _image(r), "_coverurl": _image(r), "_browser": False}
                for r in search_releases(album, artist) if _image(r)]

    def image(self, row: dict) -> bytes:
        return http.fetch_bytes(row["_image"])


def from_settings() -> Source | None:
    """The source with a stored login, None without one."""
    return Source() if configured() else None
