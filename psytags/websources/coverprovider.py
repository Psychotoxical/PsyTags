"""Further cover sources as plain description files, without any code to run.

A valid ``*.json`` file in the folder ``cover-provider`` of the configuration is a source; the
files are read anew on every use, so a file that was just dropped in counts at once. The format
is documented in ``docs/cover-provider.md``.
"""
from __future__ import annotations

import glob
import json
import os
import re
import threading
import time
import urllib.parse
from dataclasses import dataclass, field

from .. import config
from ..i18n import tr
from . import http

FOLDER = "cover-provider"
ARCHIVE = "Cover Art Archive"           # the built-in source, in the order of the sources
FORMAT = 1
TIMEOUT = 15                            # seconds; a provider must not hold up a run for long
_ORDER_KEY = "coverprovider/order"
_OFF_KEY = "coverprovider/off"

_REQUIRED = ("name", "search_url", "results", "album", "artist", "image")
_OPTIONAL = ("tracks", "page", "only_if", "embedded_json", "browser_agent", "min_interval",
             "image_replace", "preview_replace")
KNOWN_FIELDS = ("format",) + _REQUIRED + _OPTIONAL


class ProviderError(Exception):
    """A file that cannot be used, or an answer that cannot be read. The text says what is wrong."""


@dataclass
class Provider:
    name: str
    search_url: str
    results: str
    album: str
    artist: str
    image: str
    tracks: str = ""
    page: str = ""
    only_if: dict = field(default_factory=dict)
    embedded_json: str = ""
    browser_agent: bool = False
    min_interval: float = 1.0
    image_replace: list = field(default_factory=list)
    preview_replace: list = field(default_factory=list)
    path: str = ""


def folder() -> str:
    return os.path.join(config.config_dir(), FOLDER)


def _check_replacements(where: str, key: str, value) -> None:
    good = isinstance(value, list) and all(
        isinstance(p, list) and len(p) == 2 and all(isinstance(s, str) for s in p) for p in value)
    if not good:
        raise ProviderError(tr("{1}: {2} muss eine Liste aus Paaren [Muster, Ersatz] sein", where, key))
    for pattern, _new in value:
        _compile(where, key, pattern)


def _compile(where: str, key: str, pattern: str) -> re.Pattern:
    try:
        return re.compile(pattern, re.S)
    except re.error as e:
        raise ProviderError(tr("{1}: Muster in {2} ist ungültig ({3})", where, key, e)) from e


def load(path: str) -> Provider:
    """The provider described by this file; raises ProviderError with what is wrong."""
    where = os.path.basename(path)
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
    except (OSError, ValueError) as e:
        raise ProviderError(tr("{1}: keine gültige JSON-Datei ({2})", where, e)) from e
    if not isinstance(data, dict):
        raise ProviderError(tr("{1}: keine gültige JSON-Datei ({2})", where, "{ }"))
    if data.get("format") != FORMAT:
        raise ProviderError(tr("{1}: format muss {2} sein", where, FORMAT))
    unknown = [k for k in data if k not in KNOWN_FIELDS]
    if unknown:
        raise ProviderError(tr("{1}: unbekanntes Feld {2}", where, unknown[0]))
    for key in _REQUIRED:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ProviderError(tr("{1}: Feld {2} fehlt", where, key))
    if data["name"].strip().casefold() == ARCHIVE.casefold():
        raise ProviderError(tr("{1}: name {2} ist schon vergeben", where, ARCHIVE))
    url = data["search_url"]
    if not re.match(r"https?://", url) or not ("{album}" in url or "{artist}" in url):
        raise ProviderError(tr("{1}: search_url braucht http(s) und {{album}} oder {{artist}}", where))
    if "embedded_json" in data:
        if _compile(where, "embedded_json", str(data["embedded_json"])).groups != 1:
            raise ProviderError(tr("{1}: embedded_json braucht genau eine Klammer-Gruppe", where))
    for key in ("image_replace", "preview_replace"):
        if key in data:
            _check_replacements(where, key, data[key])
    interval = data.get("min_interval", 1.0)
    if isinstance(interval, bool) or not isinstance(interval, (int, float)) or interval < 0:
        raise ProviderError(tr("{1}: min_interval muss eine Zahl ab 0 sein", where))
    if not isinstance(data.get("only_if", {}), dict):
        raise ProviderError(tr("{1}: only_if muss ein Objekt sein", where))
    values = {k: data[k] for k in KNOWN_FIELDS if k in data and k != "format"}
    return Provider(**values, path=path)


def discover() -> tuple[list[Provider], list[str]]:
    """The usable providers by name, and what is wrong with the other files."""
    found: dict[str, Provider] = {}
    problems: list[str] = []
    for path in sorted(glob.glob(os.path.join(glob.escape(folder()), "*.json"))):
        try:
            provider = load(path)
        except ProviderError as e:
            problems.append(str(e))
            continue
        key = provider.name.casefold()
        if key in found:
            problems.append(tr("{1}: name {2} ist schon vergeben", os.path.basename(path), provider.name))
        else:
            found[key] = provider
    return [found[k] for k in sorted(found)], problems


def arranged(providers: list[Provider]) -> list[tuple[str, bool]]:
    """(name, on) of all sources in the saved order. The archive starts on top, new files join at the end."""
    s = config.settings()
    names = [ARCHIVE] + [p.name for p in providers]
    saved = [n for n in config.string_list(s, _ORDER_KEY) if n in names]
    off = set(config.string_list(s, _OFF_KEY))
    return [(n, n not in off) for n in saved + [n for n in names if n not in saved]]


def save_arrangement(sources: list[tuple[str, bool]]) -> None:
    s = config.settings()
    s.setValue(_ORDER_KEY, [n for n, _on in sources])
    s.setValue(_OFF_KEY, [n for n, on in sources if not on])


def active(providers: list[Provider]) -> list:
    """The sources that are switched on, in order: ``ARCHIVE`` or a Provider."""
    by_name = {p.name: p for p in providers}
    return [ARCHIVE if n == ARCHIVE else by_name[n] for n, on in arranged(providers) if on]


_last_call: dict[str, float] = {}
_lock = threading.Lock()


def _wait_turn(provider: Provider) -> None:
    with _lock:
        now = time.monotonic()
        wait = _last_call.get(provider.name, -1e9) + provider.min_interval - now
        if wait > 0:
            time.sleep(wait)
            now = time.monotonic()
        _last_call[provider.name] = now


def _walk(value, path: str) -> list:
    """The values at a dotted path; ``*`` is every element of a list, a number one element."""
    found = [value]
    for part in path.split("."):
        following = []
        for v in found:
            if part == "*":
                if isinstance(v, list):
                    following.extend(v)
            elif isinstance(v, dict):
                if part in v:
                    following.append(v[part])
            elif isinstance(v, list) and part.isdigit() and int(part) < len(v):
                following.append(v[int(part)])
        found = following
    return found


def _text(item, path: str) -> str:
    values = _walk(item, path) if path else []
    return "" if not values or values[0] is None else str(values[0])


def _rewrite(url: str, replacements: list) -> str:
    for pattern, new in replacements:
        url = re.sub(pattern, new, url)
    return url


def rows(provider: Provider, answer: str) -> list[dict]:
    """The hits in an answer, as rows for the existing rating and the result list."""
    unreadable = ProviderError(tr("{1}: Antwort nicht lesbar", provider.name))
    if provider.embedded_json:
        block = re.search(provider.embedded_json, answer, re.S)
        if block is None:
            raise unreadable
        answer = block.group(1)
    try:
        document = json.loads(answer)
    except ValueError as e:
        raise unreadable from e
    out: list[dict] = []
    seen: set[str] = set()
    for item in _walk(document, provider.results):
        if any(_text(item, path) != str(wanted) for path, wanted in provider.only_if.items()):
            continue
        title, image = _text(item, provider.album), _text(item, provider.image)
        if not title or not image or image in seen:
            continue
        seen.add(image)
        out.append({"Album": title, "Artist": _text(item, provider.artist),
                    "Tracks": _text(item, provider.tracks), "_preview": _text(item, provider.page),
                    "_image": _rewrite(image, provider.image_replace),
                    "_coverurl": _rewrite(image, provider.preview_replace or provider.image_replace),
                    "_browser": provider.browser_agent})
    return out


def search(provider: Provider, artist: str, album: str) -> list[dict]:
    quote = lambda text: urllib.parse.quote(text.strip(), safe="")
    url = provider.search_url.replace("{artist}", quote(artist)).replace("{album}", quote(album))
    _wait_turn(provider)
    return rows(provider, http.fetch(url, "2" if provider.browser_agent else "1", timeout=TIMEOUT))


def image(provider: Provider, row: dict) -> bytes:
    _wait_turn(provider)
    return http.fetch_bytes(row["_image"], timeout=TIMEOUT, browser=provider.browser_agent)
