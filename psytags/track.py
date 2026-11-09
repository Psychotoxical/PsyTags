"""One audio file in the file list: tag fields, cover art and file information."""
from __future__ import annotations

import copy
import datetime
import os

from . import genremood, tags


def fmt_length(seconds: float) -> str:
    s = int(round(seconds))
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def fmt_size(n: int) -> str:
    for unit in ("Bytes", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            if unit == "Bytes":
                return f"{n} Bytes"
            return f"{n:.1f}{unit}".replace(".", ",")
        n /= 1024
    return str(n)


class Track:
    __slots__ = ("path", "data", "_saved", "size", "mtime", "ctime", "counter",
                 "total", "_script_vars", "error")

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        self.data = tags.TagData()
        self._saved = tags.TagData()
        self.size = 0
        self.mtime = 0.0
        self.ctime = 0.0
        self.counter = 0
        self.total = 0
        self.error = ""
        self._script_vars = {}

    # -- I/O -----------------------------------------------------------------
    def load(self) -> "Track":
        try:
            st = os.stat(self.path)
            self.size, self.mtime, self.ctime = st.st_size, st.st_mtime, st.st_ctime
            self.data = tags.read(self.path)
            self.error = ""
        except Exception as e:      # unreadable/corrupt files still appear in the list
            self.data = tags.TagData()
            self.error = str(e)
        self._saved = copy.deepcopy(self.data)
        return self

    def save(self, id3_version: int = 3, write_id3v1: bool = False,
             keep_mtime: bool = False) -> None:
        covers_changed = self.data.covers != self._saved.covers
        st = os.stat(self.path)
        tags.write(self.path, self.data.fields, self.data.covers if covers_changed else None,
                   id3_version=id3_version, write_id3v1=write_id3v1)
        if keep_mtime:
            os.utime(self.path, (st.st_atime, st.st_mtime))
        self.load()

    def remove_tags(self) -> None:
        tags.remove(self.path)
        self.load()

    @property
    def modified(self) -> bool:
        return (self.data.fields != self._saved.fields
                or self.data.covers != self._saved.covers)

    def revert(self) -> None:
        self.data = copy.deepcopy(self._saved)

    def snapshot(self) -> tuple:
        return (self.path, copy.deepcopy(self.data.fields), list(self.data.covers))

    # -- field access (scripting context) ------------------------------------
    @property
    def fields(self) -> dict[str, list[str]]:
        return self.data.fields

    def get(self, name: str) -> list[str]:
        return self.data.fields.get(name.upper(), [])

    def set(self, name: str, values: list[str] | str) -> None:
        name = name.upper()
        if name in genremood.LIST_FIELDS:
            values = genremood.join(values)
            values = [values] if values else []
        elif isinstance(values, str):
            values = values.split("\\\\") if values else []
        values = [v for v in values if v != ""]
        if values:
            self.data.fields[name] = values
        else:
            self.data.fields.pop(name, None)

    def field(self, name: str) -> list[str]:
        n = name.upper()
        if n.startswith("_"):
            v = self.placeholder(n)
            return [v] if v != "" else []
        return self.data.fields.get(n, [])

    def display(self, name: str) -> str:
        return "\\\\".join(self.get(name))

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)

    def placeholder(self, n: str) -> str:
        i = self.data.info
        base, ext = os.path.splitext(self.filename)
        if n == "_FILENAME":
            return base
        if n == "_FILENAME_EXT":
            return self.filename
        if n == "_EXTENSION":
            return ext.lstrip(".")
        if n in ("_PATH", "_FILENAME_PATH"):
            return self.path
        if n == "_FOLDERPATH":
            return self.folder + os.sep
        if n == "_FOLDERPATH_REL":
            return self.folder + os.sep
        if n == "_DIRECTORY":
            return os.path.basename(self.folder)
        if n == "_PARENT_DIRECTORY":
            return os.path.basename(os.path.dirname(self.folder))
        if n == "_DRIVE":
            return os.path.splitdrive(self.path)[0] or "/"
        if n == "_LENGTH":
            return fmt_length(i.length)
        if n == "_LENGTH_SECONDS":
            return str(int(round(i.length)))
        if n == "_LENGTH_SECONDS_FP":
            return f"{i.length:.3f}"
        if n == "_BITRATE":
            return str(i.bitrate) if i.bitrate else ""
        if n == "_SAMPLERATE":
            return str(i.samplerate) if i.samplerate else ""
        if n == "_BITSPERSAMPLE":
            return str(i.bits_per_sample) if i.bits_per_sample else ""
        if n == "_CHANNELS":
            return str(i.channels) if i.channels else ""
        if n == "_MODE":
            return i.mode or ("Stereo" if i.channels == 2 else "Mono" if i.channels == 1 else "")
        if n == "_CODEC":
            return i.codec
        if n == "_VBR":
            return i.bitrate_mode
        if n == "_TAG":
            return ", ".join(self.data.tag_types)
        if n == "_TAG_READ":
            return self.data.tag_types[0] if self.data.tag_types else ""
        if n == "_FILE_SIZE":
            return fmt_size(self.size)
        if n == "_FILE_SIZE_BYTES":
            return str(self.size)
        if n == "_FILE_SIZE_KB":
            return str(self.size // 1024)
        if n == "_FILE_SIZE_MB":
            return f"{self.size / 1048576:.2f}"
        if n in ("_FILE_MOD_DATE", "_FILE_CREATE_DATE"):
            t = self.mtime if n == "_FILE_MOD_DATE" else self.ctime
            return datetime.datetime.fromtimestamp(t).strftime("%d.%m.%Y %H:%M:%S")
        if n in ("_FILE_MOD_DATETIME_RAW", "_FILE_CREATE_DATETIME_RAW"):
            return str(int(self.mtime if "MOD" in n else self.ctime))
        if n == "_COUNTER":
            return str(self.counter)
        if n == "_TOTAL_FILES":
            return str(self.total)
        if n == "_COVERS":
            return ", ".join(tags.COVER_TYPES[c.type] if c.type < len(tags.COVER_TYPES)
                             else str(c.type) for c in self.data.covers)
        if n == "_COVER_SIZE":
            return fmt_size(sum(len(c.data) for c in self.data.covers)) if self.data.covers else ""
        if n == "_COVER_MIMETYPE":
            return self.data.covers[0].mime if self.data.covers else ""
        if n == "_COVER_TYPE":
            return tags.COVER_TYPES[self.data.covers[0].type] if self.data.covers else ""
        if n == "_COVER_DESCRIPTION":
            return self.data.covers[0].description if self.data.covers else ""
        if n == "_COVER_WIDTH" or n == "_COVER_HEIGHT" or n == "_COVER_DIMENSIONS":
            return _cover_dims(self.data.covers, n)
        if n == "_TAG_SIZE" or n == "_TAGSIZE":
            return ""
        if n == "_ALL":
            return ", ".join(f"{k}={'; '.join(v)}" for k, v in self.data.fields.items())
        if n == "_WORKINGDIR":
            return self.folder
        return ""


def _cover_dims(covers, n: str) -> str:
    if not covers:
        return ""
    from PySide6.QtGui import QImage
    img = QImage.fromData(covers[0].data)
    if img.isNull():
        return ""
    if n == "_COVER_WIDTH":
        return str(img.width())
    if n == "_COVER_HEIGHT":
        return str(img.height())
    return f"{img.width()}x{img.height()}"
