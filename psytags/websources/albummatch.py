"""Does a folder of files belong to a release? Used for the automatic album choice.

An album is one decision: a release is only accepted when every one of its tracks finds its own
file by title, independent of the file order. Lengths only break ties and catch other versions,
because files can differ from the database by many seconds and still be the same recording.
"""
from __future__ import annotations

import itertools
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from ..i18n import tr

THRESHOLD = 0.85                 # title similarity a track needs
LIMIT_EXACT = 60                 # seconds of difference allowed with an identical title
LIMIT_SIMILAR = 30               # ... with a merely similar title
MAX_LEFTOVERS = 3                # files without a track, also at most a quarter of all files
SAME_BUT_NOTES = 0.99            # identical except for bracketed notes: below a truly equal title
CONTAINED = 0.9                  # one title is part of the other, e.g. "Album – Title" and "Title"
LAST_SONG_MAX_GAP = 3.0          # seconds: a differently spelled last song needs this close a length
LAST_SONG_MIN_TRACKS = 4
MIN_LENGTH_MARGIN = 2.0          # seconds the length must favour one of two equally named tracks

_YEAR_FIELDS = ("YEAR", "ORIGYEAR")

_EDITION = r"edition|version|remaster(ed)?|deluxe|bonus|expanded|anniversary|reissue|ep|single"
_NOTE_IN_BRACKETS = re.compile(r"\s*[\(\[][^)\]]*[\)\]]\s*$")
_RECORDING = r"live|unplugged|acoustic|akustik|remix(es)?|instrumentals?|demos?|karaoke"
_NOTE_AFTER_DASH = re.compile(r"(\s+[-–—]\s+|:\s+)[^-–—:]*\b(" + _EDITION + "|" + _RECORDING + r")\b[^-–—:]*$",
                              re.IGNORECASE)
_NOTE_WORDS = re.compile(r"\s+((special|limited|deluxe|expanded|collector'?s?|tour|anniversary)\s+edition"
                         r"|deluxe|remastered)\s*$", re.IGNORECASE)
_OTHER_RECORDING = re.compile(r"\b(" + _RECORDING + r")\b", re.IGNORECASE)
_PART = re.compile(r"\b(part|pt|vol|volume)\b", re.IGNORECASE)


def clean_import(values: dict[str, str], has_mood: bool) -> dict[str, str]:
    """Values of a tag source as they get written: only the year of a date, and moods
    from the audio analysis are never replaced."""
    out: dict[str, str] = {}
    for name, value in values.items():
        upper = name.upper()
        if upper == "MOOD" and has_mood:
            continue
        if upper in _YEAR_FIELDS:
            m = re.match(r"\s*(\d{4})", value)
            if m:
                value = m.group(1)
        out[name] = value
    return out


def drop_comments(track) -> None:
    """Remove the comments of a file. iTunes keeps technical values in the same frames
    (gapless playback, loudness); those are no comments and stay."""
    for name in list(track.data.fields):
        if name == "COMMENT" or (name.startswith("COMMENT ") and not name.startswith("COMMENT ITUN")):
            track.set(name, "")


def base_title(album: str, drop_recording_notes: bool = False) -> str:
    """The album title without trailing edition notes, for another search: "Aftermath (Bonus
    Tracks Edition)" becomes "Aftermath". Notes about other recordings (live, remix) only go
    with ``drop_recording_notes``; another part (vol. 2) always stays. Returns the title
    unchanged if nothing can be removed."""
    out = album.strip()
    while True:
        for pattern in (_NOTE_IN_BRACKETS, _NOTE_AFTER_DASH, _NOTE_WORDS):
            m = pattern.search(out)
            if m and m.start() > 0 and not _PART.search(m.group(0)) \
                    and (drop_recording_notes or not _OTHER_RECORDING.search(m.group(0))):
                out = out[:m.start()].rstrip()
                break
        else:
            return out


def recording_note(album: str) -> str:
    """The word that marks other recordings in the title ("live"), or ""."""
    m = _OTHER_RECORDING.search(base_title(album)[len(base_title(album, True)):])
    return m.group(0).casefold() if m else ""


def seconds(v: str) -> float | None:
    """Track length from a tag source ("3:41", "221", "221000" ms) in seconds."""
    v = v.strip()
    if v.isdigit():
        return int(v) / 1000 if int(v) >= 6000 else float(int(v))
    m, _, s = v.partition(":")
    try:
        return int(m) * 60 + float(s) if s else None
    except ValueError:
        return None


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold().replace("&", " and ")
    return re.sub(r"[^\w]+", " ", s).strip()


def variants(s: str) -> set[str]:
    """The title as it is, and without bracketed additions and "feat."."""
    core = norm(re.sub(r"[\(\[][^)\]]*[\)\]]", " ", s or ""))
    core = re.sub(r"\b(feat|featuring|ft)\b.*$", "", core).strip()
    return {v for v in (norm(s), core) if v}


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if re.findall(r"\d+", a) != re.findall(r"\d+", b):       # "Part 1" is not "Part 2"
        return 0.0
    short, long = sorted((a.split(), b.split()), key=len)
    if len(short) >= 2 and any(long[i:i + len(short)] == short for i in range(len(long) - len(short) + 1)):
        return CONTAINED
    return SequenceMatcher(None, a, b).ratio()


def similarity(a: set[str], b: set[str]) -> float:
    return max((_ratio(x, y) for x in a for y in b), default=0.0)


def same_artist(a: str, b: str) -> bool:
    """Unknown artists do not count against a release; "Band" and "The Band" are the same."""
    x, y = norm(a), norm(b)
    if not x or not y:
        return True
    wx, wy = set(x.split()), set(y.split())
    return wx <= wy or wy <= wx or _ratio(x, y) >= THRESHOLD


@dataclass
class FileInfo:
    key: object
    titles: set[str]
    length: float
    full: set[str] = field(default_factory=set)     # the titles with their bracketed notes
    label: str = ""                                 # the title as messages show it


def file_info(key: object, title: str, filename: str, artist: str, length: float) -> FileInfo:
    """Title candidates come from the tag and the file name without number and artist."""
    stem = re.sub(r"\.[^.]+$", "", filename)
    who = norm(artist)
    parts = [p for p in re.split(r"\s+-\s+", stem) if not re.fullmatch(r"\s*\d+([-.]\d+)?\s*", p) and norm(p) != who]
    joined = re.sub(r"^\s*\d+([-.]\d+)?[\s._-]+", "", " - ".join(parts))
    last = re.sub(r"^\s*\d+([-.]\d+)?[\s._-]+", "", parts[-1]) if parts else ""
    titles = variants(title) | variants(joined) | variants(last)
    return FileInfo(key, titles, length or 0.0, {f for f in (norm(title), norm(joined), norm(last)) if f}, title or last)


@dataclass
class Release:
    key: object
    titles: list[str]
    lengths: list[float | None]
    year: str = ""
    digital: bool = False
    tight: bool = False               # another kind of recording: every length must agree closely


@dataclass
class Match:
    release: Release
    files: list[FileInfo]
    mapping: dict[int, int]           # file index -> track index
    leftovers: list[int]              # file indexes without a track
    worst: float
    missing_last: bool = False        # the release has one more track at its end than there are files

    @property
    def leftover_keys(self) -> list:
        return [self.files[i].key for i in self.leftovers]


@dataclass
class Decision:
    match: Match | None
    reason: str = ""


def align(files: list[FileInfo], release: Release) -> list[tuple[int, int, float]]:
    """(file index, track index, similarity): best titles first, the closer length breaks ties."""
    tracks = [variants(t) for t in release.titles]
    pairs = []
    for f, info in enumerate(files):
        for t, title in enumerate(tracks):
            s = 1.0 if norm(release.titles[t]) in info.full else min(similarity(info.titles, title), SAME_BUT_NOTES)
            have = release.lengths[t] if t < len(release.lengths) else None
            pairs.append((-round(s, 3), abs(have - info.length) if have and info.length else 0.0, f, t, s))
    pairs.sort()
    out: list[tuple[int, int, float]] = []
    used_f: set[int] = set()
    used_t: set[int] = set()
    for _rank, _gap, f, t, s in pairs:
        if f not in used_f and t not in used_t:
            used_f.add(f)
            used_t.add(t)
            out.append((f, t, s))
    return _best_for_equal_titles(files, release, out)


def _best_for_equal_titles(files: list[FileInfo], release: Release,
                           pairs: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    """The closest length first can cross two versions of a title; take the smaller total difference."""
    def length(t: int) -> float | None:
        return release.lengths[t] if t < len(release.lengths) else None

    for i, j in itertools.combinations(range(len(pairs)), 2):
        f1, t1, s1 = pairs[i]
        f2, t2, s2 = pairs[j]
        if norm(release.titles[t1]) != norm(release.titles[t2]):
            continue
        l1, l2, a, b = length(t1), length(t2), files[f1].length, files[f2].length
        gain = abs(l1 - a) + abs(l2 - b) - abs(l2 - a) - abs(l1 - b) if l1 and l2 and a and b else 0.0
        in_file_order = (f1 < f2) == (t1 < t2)
        if gain >= MIN_LENGTH_MARGIN or (abs(gain) < MIN_LENGTH_MARGIN and not in_file_order):
            pairs[i], pairs[j] = (f1, t2, s1), (f2, t1, s2)    # lengths decide, else the file order
    return pairs


def _ambiguous_title(files: list[FileInfo], release: Release, mapping: dict[int, int]) -> str:
    """A title that occurs twice and whose lengths are unknown, or "". With known lengths
    the closer one decides, and with nearly equal lengths the order of the files."""
    groups: dict[str, list[tuple[int, int]]] = {}
    for f, t in mapping.items():
        groups.setdefault(norm(release.titles[t]), []).append((f, t))
    for group in groups.values():
        for (f1, t1), (f2, t2) in itertools.combinations(group, 2):
            l1 = release.lengths[t1] if t1 < len(release.lengths) else None
            l2 = release.lengths[t2] if t2 < len(release.lengths) else None
            if not (l1 and l2 and files[f1].length and files[f2].length):
                return release.titles[t1]
    return ""


def _gap(files: list[FileInfo], release: Release, f: int, t: int) -> float | None:
    """Difference in seconds, None if a length is unknown."""
    have = release.lengths[t] if t < len(release.lengths) else None
    return abs(have - files[f].length) if have and files[f].length else None


def _song_with_other_length(files: list[FileInfo], release: Release, pairs: list[tuple[int, int, float]],
                            gaps: dict[int, float | None]) -> int | None:
    """The one track that may differ in length, e.g. a hidden track only on the CD: its title
    is identical, every other length agrees closely and no file is left over."""
    if len(files) != len(release.titles) or len(pairs) < LAST_SONG_MIN_TRACKS or release.tight:
        return None
    far = [(t, s) for _f, t, s in pairs if gaps[t] is not None and gaps[t] > LAST_SONG_MAX_GAP]
    if len(far) != 1 or far[0][1] < 1.0 or any(gaps[t] is None for t in gaps):
        return None
    return far[0][0]


def _is_last_free_song(files: list[FileInfo], release: Release, pairs: list[tuple[int, int, float]],
                       weak: list[tuple[int, int, float]]) -> bool:
    """One differently named song is accepted when everything else fits, no file is left over
    and its length agrees closely: "Brain Damage" in the file, "Brain Dance" in the database."""
    if len(weak) != 1 or len(files) != len(release.titles) or len(pairs) < LAST_SONG_MIN_TRACKS:
        return False
    f, t, _s = weak[0]
    have = release.lengths[t] if t < len(release.lengths) else None
    return bool(have and files[f].length) and abs(have - files[f].length) <= LAST_SONG_MAX_GAP


def _is_shortened(files: list[FileInfo], release: Release, f: int, t: int) -> bool:
    """"Expressions" for "Expressions of Invincibility": the file has the start of the title,
    no file is left over and the length agrees closely."""
    gap = _gap(files, release, f, t)
    if len(files) != len(release.titles) or gap is None or gap > LAST_SONG_MAX_GAP:
        return False
    for short in files[f].titles:
        for long in variants(release.titles[t]):
            words, whole = short.split(), long.split()
            if len(words) < len(whole) and whole[:len(words)] == words:
                return True
    return False


def _leftovers_allowed(n_left: int, n_files: int) -> bool:
    return n_left <= MAX_LEFTOVERS and n_left * 4 <= n_files


def _without_last_track(files: list[FileInfo], release: Release) -> Match | None:
    """A release whose last track has no file: every other track needs its title and a close length."""
    n = len(release.titles) - 1
    if len(files) != n or n < LAST_SONG_MIN_TRACKS:
        return None
    shorter = Release(release.key, release.titles[:n], release.lengths[:n], release.year, release.digital, release.tight)
    pairs = align(files, shorter)
    for f, t, s in pairs:
        gap = _gap(files, shorter, f, t)
        if s < THRESHOLD or gap is None or gap > LAST_SONG_MAX_GAP:
            return None
    mapping = {f: t for f, t, _s in pairs}
    if _ambiguous_title(files, shorter, mapping):
        return None
    return Match(release, files, mapping, [], min(s for _f, _t, s in pairs), missing_last=True)


def match_release(files: list[FileInfo], release: Release) -> Match | str:
    """A Match if the release fits, otherwise the reason it does not."""
    n = len(release.titles)
    without_last = _without_last_track(files, release)
    if without_last is not None:
        return without_last
    if not n or len(files) < n or not _leftovers_allowed(len(files) - n, len(files)):
        return tr("{1} Tracks / {2} Dateien", n, len(files))
    pairs = align(files, release)
    weak = [p for p in pairs if p[2] < THRESHOLD]
    shortened = [p for p in weak if _is_shortened(files, release, p[0], p[1])]
    if len(pairs) >= LAST_SONG_MIN_TRACKS and len(shortened) * 2 <= len(pairs):     # most titles must fit by themselves
        weak = [p for p in weak if p not in shortened]
    if weak and not _is_last_free_song(files, release, pairs, weak):
        return tr("Titel passt nicht: „{1}“ statt „{2}“", files[weak[0][0]].label, release.titles[weak[0][1]])
    worst = 1.0
    mapping: dict[int, int] = {}
    gaps = {t: _gap(files, release, f, t) for f, t, _s in pairs}
    pardoned = None if weak else _song_with_other_length(files, release, pairs, gaps)
    for f, t, s in pairs:
        title = release.titles[t]
        gap = gaps[t] or 0.0
        if release.tight and (gaps[t] is None or gap > LAST_SONG_MAX_GAP):
            return tr("Länge weicht {1} s ab: {2}", round(gap), title)
        if t != pardoned and s >= THRESHOLD and gap > (LIMIT_EXACT if s >= SAME_BUT_NOTES else LIMIT_SIMILAR):
            return tr("Länge weicht {1} s ab: {2}", round(gap), title)
        mapping[f] = t
        worst = min(worst, s)
    unclear = _ambiguous_title(files, release, mapping)
    if unclear:
        return tr("Titel nicht eindeutig: {1}", unclear)
    return Match(release, files, mapping, [i for i in range(len(files)) if i not in mapping], worst)


def _prefer(pool: list[Match], year: str) -> Match:
    pool = [m for m in pool if m.release.digital] or pool
    return next((m for m in pool if year and m.release.year == year), pool[0])


def decide(files: list[FileInfo], releases: list[Release], year: str = "") -> Decision:
    """The one release to use, or no match and the reason. Editions without leftover files
    come first; editions with the same track list are interchangeable."""
    results = [match_release(files, r) for r in releases]
    good = [r for r in results if isinstance(r, Match)]
    if not good:
        reasons = list(dict.fromkeys(r for r in results if isinstance(r, str)))
        return Decision(None, "; ".join(reasons[:3]) or tr("Keine passende Ausgabe gefunden"))
    good = [m for m in good if not m.missing_last] or good
    pool = [m for m in good if not m.leftovers] or good
    if _track_lists(pool) > 1:                  # the edition whose order fits the files, if only one does
        pool = [m for m in pool if _keeps_file_order(m)]
        if _track_lists(pool) != 1:
            return Decision(None, tr("Mehrere Ausgaben mit verschiedenen Tracklisten"))
    return Decision(_prefer(pool, year))


def _track_lists(pool: list[Match]) -> int:
    return len({tuple(norm(t) for t in m.release.titles) for m in pool})


def _keeps_file_order(match: Match) -> bool:
    order = [match.mapping[f] for f in sorted(match.mapping)]
    return order == sorted(order)
