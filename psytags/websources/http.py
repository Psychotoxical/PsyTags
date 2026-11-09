"""Downloads for tag sources (user agent, Discogs token, small in-memory cache)."""
from __future__ import annotations

import gzip
import http.client
import urllib.error
import urllib.parse
import urllib.request
import zlib

from .. import __version__, config

USER_AGENT = f"PsyTags/{__version__} ( https://github.com/ )"
BROWSER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                 "Chrome/140.0 Safari/537.36")
_cache: dict[str, bytes] = {}


class FetchError(Exception):
    pass


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        raise FetchError(f"HTTP {e.code} {e.reason}: {url}\n{body}") from e
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, EOFError, zlib.error) as e:
        raise FetchError(f"{e}: {url}") from e
    if len(_cache) > 200:
        _cache.clear()
    _cache[url] = data
    return _decode(data)


def fetch_bytes(url: str, timeout: float = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except http.client.HTTPException as e:
        raise FetchError(f"{e}: {url}") from e


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
