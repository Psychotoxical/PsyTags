"""Genres from Last.fm tags: album tags, else the artist's tags."""
from __future__ import annotations

import json
import re
import time
import urllib.parse

from .. import genremood
from . import http

API_URL = "https://ws.audioscrobbler.com/2.0/"
RETRIES = 2                            # Last.fm often answers 5xx for a moment
RETRY_WAIT = 3.0


class LastfmError(Exception):
    pass


def _fetch(url: str) -> str:
    """One request; a server error gets a few more tries before it counts."""
    for attempt in range(RETRIES + 1):
        try:
            return http.fetch(url)
        except http.FetchError as e:
            if attempt == RETRIES or not re.search(r"HTTP 5\d\d", str(e)):
                raise
            time.sleep(RETRY_WAIT)
    raise AssertionError("unreachable")


def _top_tags(method: str, api_key: str, **params: str) -> list[tuple[str, int]]:
    q = {"method": method, "api_key": api_key, "format": "json", "autocorrect": "1", **params}
    try:
        data = json.loads(_fetch(API_URL + "?" + urllib.parse.urlencode(q)))
    except http.FetchError as e:
        # Last.fm answers unknown albums with HTTP 4xx and an error code in the body.
        if '"error":6' in str(e).replace(" ", ""):
            return []
        raise LastfmError(re.sub(r":\s*https?://\S+", "", str(e))) from e
    except ValueError as e:
        raise LastfmError(f"Last.fm: {e}") from e
    if "error" in data:
        if data.get("error") == 6:                     # album/artist/track not found
            return []
        raise LastfmError(f"Last.fm: {data.get('message', data['error'])}")
    tags = (data.get("toptags") or {}).get("tag") or []
    if isinstance(tags, dict):
        tags = [tags]
    out = []
    for t in tags:
        try:
            out.append((str(t.get("name", "")), int(t.get("count", 0))))
        except (TypeError, ValueError):
            continue
    return out


def album_genres(artist: str, album: str, api_key: str) -> list[str]:
    genres: list[str] = []
    if artist and album:
        genres = genremood.classify(_top_tags("album.gettoptags", api_key, artist=artist, album=album))[0]
    if artist and not genres:
        genres = genremood.classify(_top_tags("artist.gettoptags", api_key, artist=artist))[0]
    return genres
