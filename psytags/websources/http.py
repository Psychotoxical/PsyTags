"""Downloads for tag sources (user agent, Discogs token, small in-memory cache)."""
from __future__ import annotations

import gzip
import http.client
import itertools
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from contextlib import contextmanager

from .. import __version__, config
from ..i18n import tr

USER_AGENT = f"PsyTags/{__version__} ( https://github.com/ )"
BROWSER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/140.0 Safari/537.36")
_cache: dict[str, bytes] = {}
RETRY_WAITS = (2.0, 5.0)                # seconds before the second and the third try
_CONNECTION_ERRORS = (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, EOFError, zlib.error)


class FetchError(Exception):
    pass


class NotFound(FetchError):
    """The server says it does not have this (HTTP 404)."""


class ServerError(FetchError):
    """The server failed by itself (HTTP 5xx); asking again later can work."""


def _host(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or url


_running: dict[int, str] = {}
_running_lock = threading.Lock()
_running_ids = itertools.count()


@contextmanager
def activity(text: str):
    """Lists ``text`` as running while the block lasts; any thread may use it."""
    key = next(_running_ids)
    with _running_lock:
        _running[key] = text
    try:
        yield
    finally:
        with _running_lock:
            _running.pop(key, None)


def running() -> list[str]:
    """What is going on right now, oldest first."""
    with _running_lock:
        return list(_running.values())


def describe(url: str) -> str:
    """A running request in words. Never the query of the address: it can hold an API key."""
    parts = urllib.parse.urlsplit(url)
    host = parts.hostname or ""
    if host.endswith("musicbrainz.org"):
        return tr("MusicBrainz: Suche") if "query=" in parts.query else tr("MusicBrainz: Album-Daten")
    if host.endswith("coverartarchive.org"):
        return tr("Cover Art Archive: Cover")
    if host.endswith("audioscrobbler.com"):
        return tr("Last.fm: Genres")
    return host


def _download(req: urllib.request.Request, url: str, timeout: float, read):
    """``read(response)``, again after a pause when the connection breaks: image servers
    drop connections now and then. An answer from the server, even an error, is final."""
    with activity(describe(url)):
        for wait in RETRY_WAITS + (None,):
            try:
                with urllib.request.urlopen(req, timeout=timeout) as r:
                    return read(r)
            except urllib.error.HTTPError as e:
                body = e.read()[:300].decode("utf-8", "replace") if e.fp else ""
                if e.code >= 500:
                    raise ServerError(tr("{1} antwortet gerade nicht (HTTP {2})", _host(url), e.code)) from e
                raise (NotFound if e.code == 404 else FetchError)(f"HTTP {e.code} {e.reason}: {url}\n{body}") from e
            except _CONNECTION_ERRORS as e:
                if wait is None:
                    raise FetchError(tr("Verbindung zu {1} abgebrochen", _host(url))) from e
                time.sleep(wait)


def fetch(url: str, user_agent: str = "1", timeout: float = 30) -> str:
    if url in _cache:
        return _decode(_cache[url])
    headers = {"Accept-Encoding": "gzip",
               "User-Agent": USER_AGENT if user_agent in ("", "1") else
               BROWSER_AGENT if user_agent == "2" else user_agent}
    host = urllib.parse.urlsplit(url).hostname or ""
    if host.endswith("discogs.com"):
        token = config.settings().value("tagsources/discogs_token", "")
        if token:
            headers["Authorization"] = f"Discogs token={token}"
    req = urllib.request.Request(url, headers=headers)

    def read(r):
        data = r.read()
        return gzip.decompress(data) if r.headers.get("Content-Encoding") == "gzip" else data
    data = _download(req, url, timeout, read)
    if len(_cache) > 200:
        _cache.clear()
    _cache[url] = data
    return _decode(data)


def fetch_bytes(url: str, timeout: float = 30, browser: bool = False) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": BROWSER_AGENT if browser else USER_AGENT})
    return _download(req, url, timeout, lambda r: r.read())


def _decode(data: bytes) -> str:
    for enc in ("utf-8", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def encode_query(text: str, encoding: str, word_sep: str) -> str:
    """Encode the search text as described by [Encoding] and [WordSeparator]."""
    enc = (encoding or "url").lower()
    words = text.split()
    if enc.startswith("url"):
        charset = "utf-8" if "utf-8" in enc else "latin-1"
        q = [urllib.parse.quote(w, safe="", encoding=charset, errors="replace") for w in words]
    else:
        q = words
    return (word_sep if word_sep else "+").join(q)
