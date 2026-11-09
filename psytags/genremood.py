"""Genre and mood lists: vocabulary, clean spelling and the "; " separator.

GENRE and MOOD are stored as one value, e.g. ``Hard Rock; Blues Rock``. Servers
like Navidrome split both fields on ";".
"""
from __future__ import annotations

import os
import re

LIST_FIELDS = ("GENRE", "MOOD")
SEPARATOR = "; "

# Mood vocabulary: canonical spelling -> extra spellings found in Last.fm tags.
# Includes the mood ids Psysonic uses (happy, excited, calm, peaceful, angry,
# tense, sad, melancholic).
MOODS: dict[str, tuple[str, ...]] = {
    "Aggressive": ("aggression",), "Angry": ("anger",), "Atmospheric": ("atmosphere",),
    "Bittersweet": (), "Brooding": (), "Calm": (), "Cheerful": (), "Chill": ("chilled", "chill out"),
    "Dark": (), "Depressive": ("depressing",), "Dramatic": (), "Dreamy": (), "Emotional": (), "Energetic": ("energy",),
    "Epic": (), "Ethereal": (), "Euphoric": ("euphoria",), "Excited": ("exciting",),
    "Feel Good": ("feelgood", "feel-good"), "Fun": (), "Gloomy": (), "Groovy": (),
    "Happy": (), "Haunting": (), "Heavy": (), "Hopeful": (), "Hypnotic": (), "Intense": (), "Introspective": (),
    "Lonely": (), "Meditative": (), "Melancholic": ("melancholy", "melancholia"), "Mellow": (),
    "Moody": (), "Mysterious": (), "Nostalgic": ("nostalgia",), "Ominous": (), "Party": (),
    "Passionate": (), "Peaceful": (), "Playful": (), "Powerful": (), "Quirky": (),
    "Relaxing": ("relax", "relaxed", "relaxation"), "Romantic": ("romance",), "Sad": ("sadness",),
    "Sensual": (), "Sentimental": (), "Sexy": (), "Smooth": (), "Soothing": (), "Spiritual": (),
    "Tense": (), "Triumphant": (), "Upbeat": (), "Uplifting": (), "Warm": (), "Wistful": (),
}

# Words kept in this exact spelling when genre names are capitalized.
_SPECIAL = {"r&b": "R&B", "idm": "IDM", "ebm": "EBM", "edm": "EDM", "uk": "UK", "us": "US",
            "dj": "DJ", "nwobhm": "NWOBHM", "lo-fi": "Lo-Fi", "hi-nrg": "Hi-NRG", "mpb": "MPB",
            "aor": "AOR", "nyhc": "NYHC", "oi!": "Oi!", "'n'": "'n'"}
_SMALL = {"and", "of", "the", "in", "n", "de", "da", "la", "le", "y"}

_genres: dict[str, str] | None = None
_moods: dict[str, str] | None = None


def _key(s: str) -> str:
    return re.sub(r"[^0-9a-z&]+", "", s.casefold())


def nice_case(name: str) -> str:
    """'hard rock' -> 'Hard Rock', 'hip hop' -> 'Hip Hop', 'r&b' -> 'R&B'."""
    out = []
    for i, word in enumerate(name.split()):
        low = word.lower()
        if low in _SPECIAL:
            out.append(_SPECIAL[low])
        elif i and low in _SMALL:
            out.append(low)
        else:
            out.append("-".join(p[:1].upper() + p[1:] for p in low.split("-")))
    return " ".join(out)


def genre_names() -> dict[str, str]:
    """MusicBrainz genre list (resources/genres.txt), key -> nicely cased name."""
    global _genres
    if _genres is None:
        path = os.path.join(os.path.dirname(__file__), "resources", "genres.txt")
        _genres = {}
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        _genres.setdefault(_key(line), nice_case(line.strip()))
        except OSError:
            pass
    return _genres


def mood_names() -> dict[str, str]:
    global _moods
    if _moods is None:
        _moods = {}
        for name, alts in MOODS.items():
            for s in (name, *alts):
                _moods[_key(s)] = name
    return _moods


def split(values: list[str] | str) -> list[str]:
    """Single entries from "a; b", "a\\\\b" or several values; duplicates removed."""
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        for part in re.split(r";|\\\\", v):
            part = " ".join(part.split())
            if part and part.casefold() not in seen:
                seen.add(part.casefold())
                out.append(part)
    return out


def join(values: list[str] | str) -> str:
    return SEPARATOR.join(split(values))


def classify(tags: list[tuple[str, int]], min_count: int = 10,
             max_genres: int = 4, max_moods: int = 4) -> tuple[list[str], list[str]]:
    """Sort weighted tags (e.g. Last.fm) into clean genres and moods."""
    genres, moods = genre_names(), mood_names()
    g_out: list[str] = []
    m_out: list[str] = []
    for name, count in sorted(tags, key=lambda t: -t[1]):
        if count < min_count:
            continue
        k = _key(name)
        if k in moods:
            if moods[k] not in m_out and len(m_out) < max_moods:
                m_out.append(moods[k])
        elif k in genres:
            if genres[k] not in g_out and len(g_out) < max_genres:
                g_out.append(genres[k])
    return g_out, m_out
