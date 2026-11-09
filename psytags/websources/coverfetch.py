"""Cover-only fetch from a second tag source (e.g. Apple Music after a MusicBrainz import).

The search uses the source's own [SearchBy] prefill on the freshly written tags; the best
index row is chosen by album title, artist and track count.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from . import http, runner, srcfile

# Release-type suffixes that streaming services add to album titles.
_SUFFIX = re.compile(r"\s*[-–]\s*(single|ep)\s*$", re.IGNORECASE)
_EXTRA = re.compile(r"\s*[\(\[][^)\]]*(edition|version|remaster(ed)?|deluxe|bonus|expanded|anniversary)"
                    r"[^)\]]*[\)\]]", re.IGNORECASE)


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    s = s.replace("&", " and ").replace("’", "'")
    return re.sub(r"[^\w]+", " ", s).strip()


def _title_variants(t: str) -> tuple[str, str]:
    base = _SUFFIX.sub("", t or "")
    return _norm(base), _norm(_EXTRA.sub("", base))


@dataclass
class Match:
    row: dict
    score: float


def rank(rows: list[dict], album: str, artist: str, tracks: int) -> list[Match]:
    """Score index rows; columns are looked up loosely (Title/Album, Artist, Tracks, Kind)."""
    want_full, want_core = _title_variants(album)
    want_artist = _norm(artist)
    out = []
    for r in rows:
        low = {k.lower(): v for k, v in r.items()}
        kind = low.get("kind", low.get("type", "")).lower()
        if kind and kind not in ("album", "single", "ep", "compilation"):
            continue                      # songs, videos, playlists
        full, core = _title_variants(low.get("title") or low.get("album") or "")
        score = 0.0
        if full == want_full:
            score += 60
        elif core == want_core and core:
            score += 45
        elif want_core and (want_core in full or full in want_core):
            score += 20
        else:
            continue
        a = _norm(low.get("artist", ""))
        if want_artist and a:
            if a == want_artist:
                score += 30
            elif want_artist in a or a in want_artist:
                score += 15
        try:
            n = int(re.match(r"\d+", low.get("tracks", "")).group(0))
            score += 10 if n == tracks else max(0, 6 - abs(n - tracks))
        except (AttributeError, ValueError):
            pass
        out.append(Match(r, score))
    out.sort(key=lambda m: -m.score)
    return out


CONFIDENT = 75


def confident(matches: list[Match]) -> Match | None:
    """Accept the top match automatically when title and artist agree (score >= 75).
    Ties (e.g. clean/explicit editions) share the same artwork, so the first one is fine."""
    if not matches or matches[0].score < CONFIDENT:
        return None
    return matches[0]


def candidates(matches: list[Match], exact: dict | None, limit: int = 5) -> list[dict]:
    """Rows to try automatically, best first: the release from the tags, then every confident
    match. Several are needed because a release may lack artwork (MusicBrainz releases
    without a front cover in the Cover Art Archive) while other releases of the album have one."""
    out = [exact] if exact is not None else []
    out += [m.row for m in matches if m.score >= CONFIDENT and m.row is not exact]
    return out[:limit]


def first_cover(src: srcfile.Source, rows: list[dict], fetch=None,
                pause: float = 1.0) -> tuple[dict, tuple[bytes, str]] | None:
    """(row, (data, mime)) of the first row that delivers a cover, else None.
    ``pause`` between album requests keeps within MusicBrainz' one request per second."""
    fetch = fetch or fetch_cover
    for i, row in enumerate(rows):
        if i and pause:
            time.sleep(pause)
        got = fetch(src, row)
        if got:
            return row, got
    return None


def release_row(rows: list[dict], release_id: str) -> dict | None:
    """The index row of exactly this MusicBrainz release (its album URL contains the ID),
    so files tagged from MusicBrainz get the cover of their own release."""
    rid = (release_id or "").strip().lower()
    if not rid:
        return None
    return next((r for r in rows if rid in (r.get("_url") or "").lower()), None)


def search(src_path: str, tracks) -> tuple[srcfile.Source, list[dict], list[Match]]:
    src = srcfile.load(src_path)
    values = runner.prefill(src, tracks)
    rows = runner.run_index(src, values) if runner.has_index(src) else []
    t = tracks[0]
    album = (t.get("ALBUM") or [""])[0]
    artist = (t.get("ALBUMARTIST") or t.get("ARTIST") or [""])[0]
    return src, rows, rank(rows, album, artist, len(tracks))


def fetch_cover(src: srcfile.Source, row: dict) -> tuple[bytes, str] | None:
    url, prev = runner.album_target(src, row)
    album = runner.run_album(src, url, prev)
    if not album.cover_url:
        return None
    data = http.fetch_bytes(runner.cover_download_url(album.cover_url))
    mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg"
    return data, mime
