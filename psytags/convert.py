"""Target paths and renames, without UI."""
from __future__ import annotations

import os
import pathlib
import re
import sys

from .albumorder import album_root

# What happens to characters in tag values that a file name cannot hold.
# "/" is dropped: DISCNUMBER "01/01" -> "0101", "AC/DC" -> "ACDC".
FILENAME_REPLACEMENTS = {"\\": "-", "/": "", ":": "-", "*": "", "?": "", '"': "''",
                         "<": "", ">": "", "|": ""}

# The folder that was opened; previews show target paths relative to it. Set by the UI.
working_dir = ""


WINDOWS_PATH_LIMIT = 259                  # MAX_PATH without its terminator
LINUX_NAME_LIMIT = 255                    # bytes of one file or folder name
_GUESTS = re.compile(r"\s+(feat\.?|ft\.?|featuring)\s.*?(?=\s+-\s|$)", re.IGNORECASE)


def place(track, parts: list[str]) -> str:
    """Absolute target for name parts (folders, then the file name); the extension is kept.
    With folders the new album goes next to the old one, which then goes away."""
    parts = [p.strip().rstrip(". ") or "_" for p in parts if p.strip()]
    if not parts:
        return track.path
    rel = os.path.join(*parts) + os.path.splitext(track.path)[1]
    target = os.path.normpath(os.path.join(os.path.dirname(album_root(track.folder)) if len(parts) > 1 else track.folder, rel))
    return fit_path(target) if sys.platform == "win32" else fit_names(target)


def fit_path(path: str, limit: int = WINDOWS_PATH_LIMIT) -> str:
    """Shorten a file name that would make the path too long for Windows: guest artists
    ("feat. X") go first, then the end of the name. Folders and tags stay as they are."""
    if len(path) <= limit:
        return path
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    stem = _GUESTS.sub("", stem)
    room = limit - len(folder) - 1 - len(ext)
    if len(stem) > room > 0:
        stem = stem[:room].rstrip(" .-")
    return os.path.join(folder, stem + ext)


def _cut_bytes(text: str, limit: int) -> str:
    """At most ``limit`` bytes of UTF-8, never half a character."""
    return text.encode("utf-8")[:limit].decode("utf-8", "ignore").rstrip(" .-")


def fit_names(path: str, limit: int = LINUX_NAME_LIMIT) -> str:
    """Linux limits every single name, in bytes: too long folders are cut, in a file name
    guest artists go first and then the end of the name."""
    folder, name = os.path.split(path)
    stem, ext = os.path.splitext(name)
    if len(name.encode("utf-8")) > limit:
        stem = _GUESTS.sub("", stem)
        stem = _cut_bytes(stem, limit - len(ext.encode("utf-8")))
    parts = [_cut_bytes(p, limit) if len(p.encode("utf-8")) > limit else p for p in folder.split(os.sep)]
    return os.path.join(os.sep.join(parts), stem + ext)


def _has_audio(folder: str) -> bool:
    from .tags import SUPPORTED_EXTENSIONS
    return any(os.path.splitext(name)[1].lower().lstrip(".") in SUPPORTED_EXTENSIONS
               for _root, _dirs, names in os.walk(folder) for name in names)


def _is_inside(path: str, folder: str) -> bool:
    return os.path.normcase(os.path.normpath(path)).startswith(os.path.normcase(os.path.normpath(folder)) + os.sep)


def emptied_album_folders(moves: list[tuple[str, str]]) -> list[str]:
    """Album folders no longer needed after ``moves`` (old path, new path): no file went into
    them and no audio file is left anywhere below them. Other leftovers do not count."""
    targets: dict[str, list[str]] = {}
    for old, new in moves:
        if os.path.normcase(old) != os.path.normcase(new):
            targets.setdefault(album_root(os.path.dirname(old)), []).append(new)
    return [root for root, news in targets.items()
            if len(pathlib.PurePath(root).parts) > 2                       # never a drive or a top folder
            and not any(_is_inside(new, root) for new in news) and not _has_audio(root)]


def _is_audio(name: str) -> bool:
    from .tags import SUPPORTED_EXTENSIONS
    return os.path.splitext(name)[1].lower().lstrip(".") in SUPPORTED_EXTENSIONS


def _junk_in(folder: str) -> list[str]:
    """Everything below ``folder`` that is not audio; a subfolder without audio counts as one."""
    out: list[str] = []
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if os.path.isdir(path):
            out += _junk_in(path) if _has_audio(path) else [path]
        elif not _is_audio(name):
            out.append(path)
    return out


def leftovers_in_renamed_albums(moves: list[tuple[str, str]]) -> list[str]:
    """Albums that stayed in their folder (same name, or only the case differs): what is left
    beside the audio files (images, cue sheets, ...). Skipped if the folder holds other audio."""
    news: dict[str, set[str]] = {}
    for old, new in moves:
        news.setdefault(album_root(os.path.dirname(old)), set()).add(os.path.normcase(os.path.normpath(new)))
    out: list[str] = []
    for root, targets in news.items():
        if not os.path.isdir(root) or len(pathlib.PurePath(root).parts) <= 2:
            continue
        here = os.path.normcase(os.path.normpath(root)) + os.sep
        audio = {os.path.normcase(os.path.normpath(os.path.join(d, n)))
                 for d, _dirs, names in os.walk(root) for n in names if _is_audio(n)}
        if all(t.startswith(here) for t in targets) and audio == targets:
            out += _junk_in(root)
    return out


def fix_folder_case(moves: list[tuple[str, str]]) -> None:
    """Windows keeps an existing folder's spelling: "Rise Of" must become "Rise of" by hand.
    Elsewhere the two are different folders, and nothing must be touched."""
    if sys.platform != "win32":
        return
    for folder in {os.path.dirname(new) for _old, new in moves}:
        parent, name = os.path.split(folder)
        try:
            actual = next((n for n in os.listdir(parent) if n.lower() == name.lower()), name)
            if actual != name:
                os.rename(os.path.join(parent, actual), folder + ".psytags-tmp")
                os.rename(folder + ".psytags-tmp", folder)
        except OSError:
            continue                                # the spelling is not worth an error


def display_path(new: str, track) -> str:
    """Target path for previews: relative to the working directory or the file's folder."""
    for base in (working_dir, os.path.dirname(album_root(track.folder)), track.folder):
        try:
            rel = os.path.relpath(new, base) if base else ""
        except ValueError:                               # other drive
            continue
        if rel and not rel.startswith(".."):
            return rel
    return new


def rename(track, new_path: str) -> str:
    """Rename a file (creating folders as needed). Returns the old path."""
    import shutil
    old = track.path
    if new_path == old:
        return old
    # On case-insensitive file systems (Windows) the target "exists" when only the
    # case changes; that is the same file and must still be renamed.
    if os.path.exists(new_path) and not _same_file(new_path, old):
        raise FileExistsError(new_path)
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    try:
        os.rename(old, new_path)
    except OSError:
        if os.path.exists(new_path):
            raise
        shutil.move(old, new_path)                   # e.g. across drives
    track.path = new_path
    return old


def _same_file(a: str, b: str) -> bool:
    try:
        return os.path.samefile(a, b)
    except OSError:
        return False
