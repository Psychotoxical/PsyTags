"""Search -> index -> album pipeline of a tag source (docs/spec/websources.md §3-§5, §9)."""
from __future__ import annotations

import html
import json
import os
import re
import unicodedata
import urllib.parse
from dataclasses import dataclass, field

from .. import config, script
from ..i18n import tr
from . import http
from .interpreter import Interpreter, ScriptError, compile_script
from .srcfile import Source

COMPAT_VERSION = (3, 36)
SPECIAL_OUTPUTS = {"output", "tracks", "_length", "coverurl", "currenturl", "currentpreview",
                   "_preview", "preview"}


@dataclass
class Album:
    fields: dict[str, list[str]] = field(default_factory=dict)  # per-track lists or 1 common value
    per_track: set[str] = field(default_factory=set)
    tracks: int = 0
    lengths: list[str] = field(default_factory=list)
    cover_url: str = ""
    preview: str = ""

    def value(self, name: str, i: int) -> str:
        vals = self.fields.get(name, [])
        if name not in self.per_track:
            return vals[0] if vals else ""
        return vals[i] if i < len(vals) else ""


# ---------------------------------------------------------------------------
# settings (.settings schema + shared settings.json)

def sources_dir() -> str:
    return os.path.join(config.data_dir(), "sources")


def load_schema(src: Source) -> dict | None:
    name = src.get("settings")
    if not name:
        return None
    p = name if os.path.isabs(name) else os.path.join(os.path.dirname(src.path), name)
    try:
        with open(p, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def load_user_settings() -> dict:
    try:
        with open(os.path.join(sources_dir(), "settings.json"), encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_user_settings(data: dict) -> None:
    with open(os.path.join(sources_dir(), "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def _var_text(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def variables(src: Source) -> dict[str, str]:
    schema = load_schema(src)
    if not schema:
        return {}
    user = load_user_settings().get(schema.get("key", ""), {})
    out = {}
    for s in schema.get("settings", []):
        k = s.get("key")
        if not k or s.get("type") in ("heading", "separator"):
            continue
        out[k] = _var_text(user.get(k, s.get("default", "")))
    return out


def check_version(src: Source) -> str | None:
    v = src.get("minappversionwin")
    m = re.match(r"(\d+)\.(\d+)", v or "")
    if m and (int(m.group(1)), int(m.group(2))) > COMPAT_VERSION:
        return tr("Diese Tag-Quelle benötigt mindestens Mp3tag v{1}.", v)
    return None


# ---------------------------------------------------------------------------
# URLs

def encode_value(value: str, encoding: str, word_sep: str) -> str:
    value = unicodedata.normalize("NFC", value.strip())
    enc = (encoding or "url-utf-8").lower()
    words = value.split()
    if enc in ("url-utf-8", "url"):
        cs = "utf-8" if enc == "url-utf-8" else "cp1252"
        words = [urllib.parse.quote(w, safe="-_.~", encoding=cs, errors="replace") for w in words]
    return word_sep.join(words)


def word_separator(src: Source) -> str:
    return src.get("wordseparator") or src.get("wordseperator") or "%20"


def has_index(src: Source) -> bool:
    return bool(src.get("indexurl")) and bool(compile_script(src.index_script or []))


def index_url(src: Source, values: list[str]) -> str:
    enc, sep = src.get("encoding"), word_separator(src)
    q = "".join(f.url_part.replace("%s", encode_value(v, enc, sep))
                for f, v in zip(src.search_fields, values))
    base = src.get("indexurl")
    return base.replace("%s", q) if "%s" in base else base + q


def album_url(src: Source, url_part: str, direct: bool = False) -> str:
    base = src.get("albumurl")
    if direct:
        url_part = encode_value(url_part, src.get("encoding"), word_separator(src))
    if not base:
        return url_part
    return base.replace("%s", url_part) if "%s" in base else base + url_part


def cover_download_url(url: str) -> str:
    """Host-specific rewrites (Mp3tag image proxy, MusicBrainz cover size)."""
    m = re.match(r"https?://cache\.mp3tag\.de/coxy/(.+)", url)
    if m:
        rest = m.group(1)
        return rest if rest.startswith("http") else "https://i.discogs.com/" + rest
    if "coverartarchive.org" in url and url.endswith("/front"):
        size = config.settings().value("tagsources/mb_cover_size", "1200")
        if size and size != "original":
            return f"{url}-{size}"
    return url


# ---------------------------------------------------------------------------
# steps

def run_index(src: Source, values: list[str]) -> list[dict[str, str]]:
    url = index_url(src, values)
    text = http.fetch(url, src.get("useragent"))
    it = Interpreter(text, variables(src), current_url=url)
    it.run(compile_script(src.index_script or []))
    cols = src.index_columns
    rows = []
    for line in re.split(r"\r?\n", it.out("Output")):
        if not line.strip():
            continue
        parts = [_unmask(p) for p in line.split("|")]
        row = {c: (parts[i] if i < len(parts) else "") for i, c in enumerate(cols)}
        rows.append(row)
    return rows


def _unmask(s: str) -> str:
    return s.replace("$verticalBar()", "|").replace("$char(124)", "|")


def run_album(src: Source, url: str, preview: str = "") -> Album:
    text = http.fetch(url, src.get("useragent"))
    it = Interpreter(text, variables(src), current_url=url, current_preview=preview)
    it.run(compile_script(src.album_script or []))
    return build_album(it, decode_entities=not it.json_used)


def build_album(it: Interpreter, decode_entities: bool = True) -> Album:
    a = Album()
    counts = []
    for name, text in it.output_items():
        low = name.lower()
        if low == "tracks":
            a.tracks = len(_split_track(text))
            continue
        if low == "_length":
            a.lengths = _split_track(text)
            continue
        if low == "coverurl":
            a.cover_url = text.strip()
            continue
        if low in ("_preview", "preview"):
            a.preview = text.strip()
            continue
        if low in SPECIAL_OUTPUTS or low.startswith("_") or not text:
            continue
        key = name.upper()
        if "|" in text:
            vals = [_clean(v, decode_entities) for v in _split_track(text)]
            if not any(vals):
                continue
            a.fields[key] = vals
            a.per_track.add(key)
            counts.append(len(vals))
        else:
            v = _clean(text, decode_entities)
            if v:
                a.fields[key] = [v]
    if not a.tracks:
        a.tracks = max(counts) if counts else 0
    if "TITLE" not in a.fields and it.out("tracks").strip("|"):
        a.fields["TITLE"] = [_clean(v, decode_entities) for v in _split_track(it.out("tracks"))]
        a.per_track.add("TITLE")
    return a


def _split_track(text: str) -> list[str]:
    if text.endswith("|"):
        text = text[:-1]
    return text.split("|")


def _clean(v: str, decode_entities: bool) -> str:
    v = _unmask(v)
    if decode_entities:
        v = html.unescape(v)
        v = re.sub(r"\\x\{([0-9a-fA-F]{1,6})\}", lambda m: chr(int(m.group(1), 16)), v)
    return v


def album_target(src: Source, row: dict[str, str] | None, direct_value: str = "") -> tuple[str, str]:
    """-> (album url, preview url) for a chosen result or a direct (no index) search."""
    if row is None:
        url = album_url(src, direct_value, direct=True)
        prev = src.get("previewurl").replace("%s", direct_value) if src.get("previewurl") else url
        return url, prev
    url = album_url(src, row.get("_url", ""))
    prev = row.get("_preview") or (src.get("previewurl").replace("%s", row.get("_url", ""))
                                   if src.get("previewurl") else url)
    return url, prev


def prefill(src: Source, tracks) -> list[str]:
    t = tracks[0] if tracks else None
    return [script.format(f.fmt, t).strip() if t else "" for f in src.search_fields]


__all__ = ["Album", "ScriptError", "run_index", "run_album", "album_target", "has_index",
           "prefill", "variables", "check_version", "cover_download_url", "load_schema",
           "load_user_settings", "save_user_settings"]
