"""Front covers from the Cover Art Archive, by MusicBrainz release or release group."""
from __future__ import annotations

import time

from . import http

BASE = "https://coverartarchive.org"
NAME = "Cover Art Archive"
SERVER_WAITS = (2.0, 5.0)               # seconds before the second and the third try


def _download(url: str) -> bytes:
    """The servers behind the archive fail for a moment now and then: ask again before giving up."""
    for wait in SERVER_WAITS + (None,):
        try:
            return http.fetch_bytes(url)
        except http.ServerError:
            if wait is None:
                raise
            time.sleep(wait)
    raise AssertionError("unreachable")


def _front(kind: str, mbid: str) -> bytes | None:
    """The 1200 px version keeps files small (originals can have 10 MB and more);
    images that are too old or too small for it only exist as the original."""
    for suffix in ("front-1200", "front"):
        try:
            return _download(f"{BASE}/{kind}/{mbid}/{suffix}")
        except http.NotFound:
            continue
    return None


def ids_of(album) -> tuple[str, str] | None:
    """Release and release group of a tag source's result; None if it is not from MusicBrainz."""
    ids = (album.value("MUSICBRAINZ_ALBUMID", 0), album.value("MUSICBRAINZ_RELEASEGROUPID", 0))
    return ids if any(ids) else None


def ids_after_dialog(album, shown_cover: bytes | None) -> tuple | None:
    """What is left to do after the adjust dialog: ``()`` nothing, because the user has already
    decided about the cover shown there; the IDs to ask the archive; None for other sources."""
    ids = ids_of(album)
    return () if ids and shown_cover else ids


def fetch_front(release_id: str, group_id: str = "") -> bytes | None:
    """The cover of this very release, else the one of its release group, else None."""
    for kind, mbid in (("release", release_id), ("release-group", group_id)):
        if mbid:
            data = _front(kind, mbid)
            if data:
                return data
    return None
