"""Unified tag access on top of mutagen.

Fields are exposed with upper-case names (TITLE, ARTIST, TRACK, ...)
mapped to a list of string values. Each concrete tag format translates those
names to its native keys.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import mutagen
from mutagen import id3
from mutagen.apev2 import APEv2, APENoHeaderError, APEValue, BINARY
from mutagen.asf import ASF, ASFBoolAttribute, ASFByteArrayAttribute, ASFUnicodeAttribute
from mutagen.flac import FLAC, Picture
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4Cover, MP4FreeForm

SUPPORTED_EXTENSIONS = (
    "aac aif aifc aiff ape dsf flac m4a m4b mp2 mp3 mp4 mpc oga ogg opus "
    "spx tak tta wav wma wv"
).split()

# ---------------------------------------------------------------------------
# ID3v2

ID3_TEXT = {
    "TITLE": "TIT2", "ARTIST": "TPE1", "ALBUM": "TALB", "TRACK": "TRCK",
    "GENRE": "TCON", "ALBUMARTIST": "TPE2", "COMPOSER": "TCOM",
    "DISCNUMBER": "TPOS", "BPM": "TBPM", "PUBLISHER": "TPUB", "COPYRIGHT": "TCOP",
    "ENCODEDBY": "TENC", "ENCODERSETTINGS": "TSSE", "LYRICIST": "TEXT",
    "CONDUCTOR": "TPE3", "MIXARTIST": "TPE4", "CONTENTGROUP": "TIT1",
    "GROUPING": "GRP1", "SUBTITLE": "TIT3", "ORIGALBUM": "TOAL",
    "ORIGARTIST": "TOPE", "ORIGLYRICIST": "TOLY", "ORIGFILENAME": "TOFN",
    "ISRC": "TSRC", "LANGUAGE": "TLAN", "MEDIATYPE": "TMED", "MOOD": "TMOO",
    "INITIALKEY": "TKEY", "ALBUMSORT": "TSOA", "ARTISTSORT": "TSOP",
    "TITLESORT": "TSOT", "ALBUMARTISTSORT": "TSO2", "COMPOSERSORT": "TSOC",
    "COMPILATION": "TCMP", "FILEOWNER": "TOWN", "LENGTH": "TLEN",
    "NETRADIOSTATION": "TRSN", "NETRADIOOWNER": "TRSO", "SETSUBTITLE": "TSST",
    "MOVEMENTNAME": "MVNM", "MOVEMENT": "MVIN", "PODCASTID": "TGID",
    "PODCASTDESC": "TDES", "PODCASTCATEGORY": "TCAT", "PODCASTKEYWORDS": "TKWD",
    "RELEASETIME": "TDRL", "ENCODINGTIME": "TDEN", "TAGGINGTIME": "TDTG",
}
ID3_URL = {
    "WWWARTIST": "WOAR", "WWWAUDIOFILE": "WOAF", "WWWAUDIOSOURCE": "WOAS",
    "WWWCOMMERCIALINFO": "WCOM", "WWWCOPYRIGHT": "WCOP", "WWWPAYMENT": "WPAY",
    "WWWPUBLISHER": "WPUB", "WWWRADIOPAGE": "WORS",
}
# TXXX descriptions other taggers use for well-known fields.
ID3_TXXX = {
    "MUSICBRAINZ_ALBUMID": "MusicBrainz Album Id",
    "MUSICBRAINZ_ARTISTID": "MusicBrainz Artist Id",
    "MUSICBRAINZ_ALBUMARTISTID": "MusicBrainz Album Artist Id",
    "MUSICBRAINZ_RELEASEGROUPID": "MusicBrainz Release Group Id",
    "MUSICBRAINZ_RELEASETRACKID": "MusicBrainz Release Track Id",
    "MUSICBRAINZ_WORKID": "MusicBrainz Work Id",
    "MUSICBRAINZ_DISCID": "MusicBrainz Disc Id",
    "MUSICBRAINZ_ALBUMTYPE": "MusicBrainz Album Type",
    "MUSICBRAINZ_ALBUMSTATUS": "MusicBrainz Album Status",
    "MUSICBRAINZ_ALBUMRELEASECOUNTRY": "MusicBrainz Album Release Country",
    "MUSICBRAINZ_ORIGINALALBUMID": "MusicBrainz Original Album Id",
    "MUSICBRAINZ_ORIGINALARTISTID": "MusicBrainz Original Artist Id",
    "MUSICBRAINZ_TRMID": "MusicBrainz TRM Id",
    "ACOUSTID_ID": "Acoustid Id",
    "ACOUSTID_FINGERPRINT": "Acoustid Fingerprint",
    "CATALOGNUMBER": "CATALOGNUMBER",
    "BARCODE": "BARCODE",
}
_ID3_TEXT_REV = {v: k for k, v in ID3_TEXT.items()}
# iTunes' own comment names, also where an earlier version wrote them in capitals
_ITUNES_COMMENTS = {n.upper(): n for n in ("iTunSMPB", "iTunNORM", "iTunPGAP")}
_ID3_URL_REV = {v: k for k, v in ID3_URL.items()}
_ID3_TXXX_REV = {v.upper(): k for k, v in ID3_TXXX.items()}

# ---------------------------------------------------------------------------
# Vorbis comments (FLAC, Ogg, Opus). Most fields are stored verbatim; these
# are the default renames (Options > Tags > Mapping in the user's setup).
# The MusicBrainz release fields use Picard's Vorbis keys. The legacy keys
# (MUSICBRAINZ_ALBUMTYPE, ...) are still read but never written: servers like
# Navidrome treat them as aliases and would show the value twice.
VORBIS_READ = {"DATE": "YEAR", "TRACKNUMBER": "TRACK", "ORGANIZATION": "PUBLISHER",
               "DESCRIPTION": "COMMENT", "LYRICS": "UNSYNCEDLYRICS",
               "RELEASETYPE": "MUSICBRAINZ_ALBUMTYPE",
               "RELEASESTATUS": "MUSICBRAINZ_ALBUMSTATUS",
               "RELEASECOUNTRY": "MUSICBRAINZ_ALBUMRELEASECOUNTRY"}
VORBIS_WRITE = {"YEAR": "DATE", "TRACK": "TRACKNUMBER", "PUBLISHER": "ORGANIZATION",
                "UNSYNCEDLYRICS": "LYRICS",
                "MUSICBRAINZ_ALBUMTYPE": "RELEASETYPE",
                "MUSICBRAINZ_ALBUMSTATUS": "RELEASESTATUS",
                "MUSICBRAINZ_ALBUMRELEASECOUNTRY": "RELEASECOUNTRY"}
_VORBIS_ALIASED = {v for k, v in VORBIS_READ.items() if k.startswith("RELEASE")}

# ---------------------------------------------------------------------------
# MP4 atoms
MP4_TEXT = {
    "TITLE": "\xa9nam", "ARTIST": "\xa9ART", "ALBUM": "\xa9alb", "YEAR": "\xa9day",
    "GENRE": "\xa9gen", "COMMENT": "\xa9cmt", "ALBUMARTIST": "aART",
    "COMPOSER": "\xa9wrt", "GROUPING": "\xa9grp", "UNSYNCEDLYRICS": "\xa9lyr",
    "COPYRIGHT": "cprt", "ENCODEDBY": "\xa9too", "ARTISTSORT": "soar",
    "ALBUMSORT": "soal", "TITLESORT": "sonm", "ALBUMARTISTSORT": "soaa",
    "COMPOSERSORT": "soco", "DESCRIPTION": "desc", "TVSHOW": "tvsh",
    "TVNETWORK": "tvnn", "TVEPISODEID": "tven", "PODCASTURL": "purl",
    "PODCASTID": "egid", "SUBTITLE": "\xa9st3", "WORK": "\xa9wrk",
    "MOVEMENTNAME": "\xa9mvn",
}
_MP4_TEXT_REV = {v: k for k, v in MP4_TEXT.items()}
MP4_FREEFORM = "----:com.apple.iTunes:"

# ---------------------------------------------------------------------------
# APEv2
APE_READ = {"ALBUM ARTIST": "ALBUMARTIST", "DISC": "DISCNUMBER",
            "ORIGINAL ARTIST": "ORIGARTIST", "ORIGINAL ALBUM": "ORIGALBUM"}
APE_WRITE = {"TITLE": "Title", "ARTIST": "Artist", "ALBUM": "Album", "YEAR": "Year",
             "TRACK": "Track", "GENRE": "Genre", "COMMENT": "Comment",
             "ALBUMARTIST": "Album Artist", "COMPOSER": "Composer",
             "DISCNUMBER": "Disc", "PUBLISHER": "Publisher"}

# ---------------------------------------------------------------------------
# ASF (WMA): the attribute names Windows Media Player and Picard use.
ASF_WRITE = {
    "TITLE": "Title", "ARTIST": "Author", "ALBUM": "WM/AlbumTitle",
    "ALBUMARTIST": "WM/AlbumArtist", "YEAR": "WM/Year", "TRACK": "WM/TrackNumber",
    "DISCNUMBER": "WM/PartOfSet", "GENRE": "WM/Genre", "COMMENT": "Description",
    "COMPOSER": "WM/Composer", "COPYRIGHT": "Copyright", "PUBLISHER": "WM/Publisher",
    "BPM": "WM/BeatsPerMinute", "MOOD": "WM/Mood", "UNSYNCEDLYRICS": "WM/Lyrics",
    "ENCODEDBY": "WM/EncodedBy", "CONDUCTOR": "WM/Conductor", "LYRICIST": "WM/Writer",
    "GROUPING": "WM/ContentGroupDescription", "SUBTITLE": "WM/SubTitle",
    "ISRC": "WM/ISRC", "LANGUAGE": "WM/Language", "INITIALKEY": "WM/InitialKey",
    "ALBUMSORT": "WM/AlbumSortOrder", "ARTISTSORT": "WM/ArtistSortOrder",
    "TITLESORT": "WM/TitleSortOrder", "ALBUMARTISTSORT": "WM/AlbumArtistSortOrder",
    "COMPOSERSORT": "WM/ComposerSortOrder", "COMPILATION": "WM/IsCompilation",
    "MEDIATYPE": "WM/Media", "ORIGALBUM": "WM/OriginalAlbumTitle",
    "ORIGARTIST": "WM/OriginalArtist", "ORIGYEAR": "WM/OriginalReleaseYear",
    "CATALOGNUMBER": "WM/CatalogNo", "BARCODE": "WM/Barcode",
    "MUSICBRAINZ_ALBUMID": "MusicBrainz/Album Id",
    "MUSICBRAINZ_ARTISTID": "MusicBrainz/Artist Id",
    "MUSICBRAINZ_ALBUMARTISTID": "MusicBrainz/Album Artist Id",
    "MUSICBRAINZ_RELEASEGROUPID": "MusicBrainz/Release Group Id",
    "MUSICBRAINZ_TRACKID": "MusicBrainz/Track Id",
    "MUSICBRAINZ_RELEASETRACKID": "MusicBrainz/Release Track Id",
    "MUSICBRAINZ_WORKID": "MusicBrainz/Work Id",
    "MUSICBRAINZ_DISCID": "MusicBrainz/Disc Id",
    "MUSICBRAINZ_ALBUMTYPE": "MusicBrainz/Album Type",
    "MUSICBRAINZ_ALBUMSTATUS": "MusicBrainz/Album Status",
    "MUSICBRAINZ_ALBUMRELEASECOUNTRY": "MusicBrainz/Album Release Country",
    "ACOUSTID_ID": "Acoustid/Id", "ACOUSTID_FINGERPRINT": "Acoustid/Fingerprint",
}
_ASF_READ = {v.upper(): k for k, v in ASF_WRITE.items()}
ASF_PICTURE = "WM/Picture"

# Front cover = 3 (ID3 APIC picture types are shared by FLAC pictures).
COVER_TYPES = [
    "Other", "32x32 pixels file icon", "Other file icon", "Cover (front)",
    "Cover (back)", "Leaflet page", "Media", "Lead artist/lead performer/soloist",
    "Artist/performer", "Conductor", "Band/Orchestra", "Composer",
    "Lyricist/text writer", "Recording Location", "During recording",
    "During performance", "Movie/video screen capture", "A bright coloured fish",
    "Illustration", "Band/artist logotype", "Publisher/Studio logotype",
]


@dataclass
class Cover:
    data: bytes
    mime: str = "image/jpeg"
    type: int = 3
    description: str = ""


@dataclass
class AudioInfo:
    length: float = 0.0
    bitrate: int = 0          # kbit/s
    samplerate: int = 0
    channels: int = 0
    bits_per_sample: int = 0
    codec: str = ""
    mode: str = ""            # e.g. "Joint Stereo", "CBR"/"VBR" for MP3
    bitrate_mode: str = ""


@dataclass
class TagData:
    fields: dict[str, list[str]] = field(default_factory=dict)
    covers: list[Cover] = field(default_factory=list)
    tag_types: list[str] = field(default_factory=list)   # e.g. ["ID3v2.3", "ID3v1"]
    info: AudioInfo = field(default_factory=AudioInfo)


def _add(fields: dict[str, list[str]], name: str, values) -> None:
    vals = [str(v) for v in values if str(v) != ""]
    if vals:
        fields.setdefault(name, []).extend(vals)


# ---------------------------------------------------------------------------
# Reading

def read(path: str) -> TagData:
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("mp3", "mp2", "aac"):
        return _read_mp3(path)
    f = mutagen.File(path)
    td = TagData()
    if f is None:
        return td
    _fill_info(td.info, f)
    if isinstance(f, MP4):
        _read_mp4(f, td)
    elif hasattr(f, "tags") and isinstance(f.tags, id3.ID3):   # AIFF, WAV, DSF
        _read_id3(f.tags, td)
    elif f.tags is not None and isinstance(f.tags, APEv2):
        _read_ape(f.tags, td)
    elif isinstance(f, ASF):
        _read_asf(f, td)
    elif f.tags is not None and hasattr(f.tags, "as_dict"):        # Vorbis comments
        td.tag_types.append("FLAC" if isinstance(f, FLAC) else "Vorbis Comment")
        for k, vals in f.tags.as_dict().items():
            k = k.upper()
            if k == "METADATA_BLOCK_PICTURE":
                continue
            _add(td.fields, VORBIS_READ.get(k, k), vals)
        _merge_aliases(td.fields, _VORBIS_ALIASED)
        if isinstance(f, FLAC):
            td.covers = [Cover(p.data, p.mime, p.type, p.desc) for p in f.pictures]
        else:
            import base64
            for b64 in f.tags.get("metadata_block_picture", []):
                try:
                    p = Picture(base64.b64decode(b64))
                    td.covers.append(Cover(p.data, p.mime, p.type, p.desc))
                except Exception:
                    pass
    elif f.tags is not None:   # ASF and other dict-like containers
        td.tag_types.append(type(f.tags).__name__)
        for k in f.tags.keys():
            _add(td.fields, str(k).upper(), f.tags[k] if isinstance(f.tags[k], list) else [f.tags[k]])
    return td


def _merge_aliases(fields: dict[str, list[str]], names) -> None:
    """Drop values a field got twice from two keys ("album" and "Album")."""
    for name in names:
        vals = fields.get(name)
        if vals:
            seen: set[str] = set()
            fields[name] = [v for v in vals
                            if not (v.casefold() in seen or seen.add(v.casefold()))]


def _fill_info(info: AudioInfo, f) -> None:
    i = getattr(f, "info", None)
    if i is None:
        return
    info.length = float(getattr(i, "length", 0) or 0)
    info.bitrate = int((getattr(i, "bitrate", 0) or 0) / 1000)
    info.samplerate = int(getattr(i, "sample_rate", 0) or 0)
    info.channels = int(getattr(i, "channels", 0) or 0)
    info.bits_per_sample = int(getattr(i, "bits_per_sample", 0) or 0)
    info.codec = type(f).__name__


def _read_mp3(path: str) -> TagData:
    td = TagData()
    try:
        f = MP3(path)
    except mutagen.MutagenError:
        return td
    _fill_info(td.info, f)
    i = f.info
    td.info.codec = f"MPEG {i.version:g} Layer {i.layer}"
    td.info.mode = {0: "Stereo", 1: "Joint Stereo", 2: "Dual Channel", 3: "Mono"}.get(i.mode, "")
    td.info.bitrate_mode = "VBR" if str(i.bitrate_mode).endswith(("VBR", "ABR")) else "CBR"
    if f.tags is not None:
        _read_id3(f.tags, td)
    try:
        ape = APEv2(path)
        if not td.fields:
            _read_ape(ape, td)
        else:
            td.tag_types.append("APEv2")
    except (APENoHeaderError, mutagen.MutagenError):
        pass
    if _has_id3v1(path):
        td.tag_types.append("ID3v1")
    return td


def _has_id3v1(path: str) -> bool:
    try:
        with open(path, "rb") as fh:
            fh.seek(-128, os.SEEK_END)
            return fh.read(3) == b"TAG"
    except OSError:
        return False


def _read_id3(tags: id3.ID3, td: TagData) -> None:
    td.tag_types.insert(0, f"ID3v2.{tags.version[1]}")
    for frame in tags.values():
        fid = frame.FrameID
        if fid in ("TDRC", "TYER", "TDAT", "TIME", "TORY", "TDOR"):
            name = "YEAR" if fid in ("TDRC", "TYER") else "ORIGYEAR"
            if fid in ("TDAT", "TIME"):
                continue
            _add(td.fields, name, [str(t) for t in frame.text])
        elif fid == "TXXX":
            name = _ID3_TXXX_REV.get(frame.desc.upper(), frame.desc.upper())
            _add(td.fields, name, frame.text)
        elif fid in _ID3_TEXT_REV:
            vals = [str(t) for t in frame.text]
            if fid == "TCON":
                vals = frame.genres
            _add(td.fields, _ID3_TEXT_REV[fid], vals)
        elif fid in _ID3_URL_REV:
            _add(td.fields, _ID3_URL_REV[fid], [frame.url])
        elif fid == "WXXX":
            _add(td.fields, "WWW" + frame.desc.upper() if frame.desc else "WWW", [frame.url])
        elif fid == "COMM":
            name = "COMMENT" if not frame.desc else "COMMENT " + frame.desc.upper()
            _add(td.fields, name, frame.text)
        elif fid == "USLT":
            _add(td.fields, "UNSYNCEDLYRICS", [frame.text])
        elif fid == "POPM":
            _add(td.fields, "RATING", [str(frame.rating)])
        elif fid == "APIC":
            td.covers.append(Cover(frame.data, frame.mime, int(frame.type), frame.desc))


def _read_ape(tags: APEv2, td: TagData) -> None:
    td.tag_types.insert(0, "APEv2")
    for k, v in tags.items():
        if v.kind != 0:      # binary (cover art) / external
            if k.lower().startswith("cover art"):
                data = bytes(v.value)
                _, _, img = data.partition(b"\0")
                mime = "image/png" if img.startswith(b"\x89PNG") else "image/jpeg"
                td.covers.append(Cover(img, mime, 3 if "front" in k.lower() else 4))
            continue
        name = APE_READ.get(k.upper(), k.upper())
        _add(td.fields, name, list(v))


def _asf_is_field(key: str, values) -> bool:
    """Attributes PsyTags shows as fields: the mapped ones and any plain text.
    Everything else (technical numbers, binary data) stays untouched in the file."""
    if key.upper() in _ASF_READ:
        return True
    return bool(values) and all(isinstance(v, ASFUnicodeAttribute) for v in values)


def _read_asf(f: ASF, td: TagData) -> None:
    td.tag_types.append("ASF")
    for key in f.tags.keys():
        values = f.tags[key]
        if key == ASF_PICTURE:
            for v in values:
                cover = _asf_picture_read(bytes(v.value)) if isinstance(v, ASFByteArrayAttribute) else None
                if cover:
                    td.covers.append(cover)
            continue
        if not _asf_is_field(key, values):
            continue
        name = _ASF_READ.get(key.upper(), key.upper())
        if name == "COMPILATION":
            vals = ["1" if v.value else "0" for v in values]
        else:
            vals = [str(v.value) for v in values]
        _add(td.fields, name, vals)


def _asf_picture_read(data: bytes) -> "Cover | None":
    """WM/Picture: type (1 byte), size (4 bytes), MIME and description as
    null-terminated UTF-16LE, then the image."""
    import struct
    try:
        kind, size = struct.unpack_from("<BI", data)
        pos = 5
        texts = []
        for _ in range(2):
            end = pos
            while data[end:end + 2] != b"\0\0":
                end += 2
            texts.append(data[pos:end].decode("utf-16-le"))
            pos = end + 2
        return Cover(data[pos:pos + size], texts[0] or "image/jpeg", kind, texts[1])
    except (struct.error, UnicodeDecodeError, IndexError):
        return None


def _asf_picture_write(c: Cover) -> bytes:
    import struct
    return (struct.pack("<BI", c.type, len(c.data)) + (c.mime + "\0").encode("utf-16-le")
            + (c.description + "\0").encode("utf-16-le") + c.data)


def _read_mp4(f: MP4, td: TagData) -> None:
    td.tag_types.append("MP4")
    tags = f.tags or {}
    for k, v in tags.items():
        if k == "trkn" or k == "disk":
            n, t = v[0]
            s = str(n) + (f"/{t}" if t else "")
            _add(td.fields, "TRACK" if k == "trkn" else "DISCNUMBER", [s])
        elif k == "tmpo":
            _add(td.fields, "BPM", [str(x) for x in v])
        elif k == "cpil":
            _add(td.fields, "COMPILATION", ["1" if v else "0"])
        elif k == "covr":
            for c in v:
                mime = "image/png" if c.imageformat == MP4Cover.FORMAT_PNG else "image/jpeg"
                td.covers.append(Cover(bytes(c), mime, 3))
        elif k.startswith(MP4_FREEFORM):
            _add(td.fields, k[len(MP4_FREEFORM):].upper(),
                 [bytes(x).decode("utf-8", "replace") for x in v])
        elif k in _MP4_TEXT_REV:
            _add(td.fields, _MP4_TEXT_REV[k], v)


# ---------------------------------------------------------------------------
# Writing

def write(path: str, fields: dict[str, list[str]], covers: list[Cover] | None,
          id3_version: int = 3, write_id3v1: bool = False) -> None:
    """Replace the tag of ``path`` with ``fields`` (and ``covers`` if not None)."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    fields = {k.upper(): [v for v in vals if v != ""] for k, vals in fields.items()}
    fields = {k: v for k, v in fields.items() if v and not k.startswith("_")}
    if ext in ("mp3", "mp2", "aac"):
        try:
            tags = id3.ID3(path)
        except id3.ID3NoHeaderError:
            tags = id3.ID3()
        _write_id3(tags, fields, covers)
        tags.save(path, v2_version=id3_version, v23_sep="/" if id3_version == 3 else None,
                  v1=2 if write_id3v1 else 0)
        return
    f = mutagen.File(path)
    if f is None:
        raise ValueError(f"Unsupported file: {path}")
    if isinstance(f, MP4):
        if f.tags is None:
            f.add_tags()
        _write_mp4(f, fields, covers)
    elif isinstance(f, ASF):
        _write_asf(f, fields, covers)
    elif isinstance(f.tags, id3.ID3) or _is_id3_container(f):
        if f.tags is None:
            f.add_tags()
        _write_id3(f.tags, fields, covers)
    elif isinstance(f.tags, APEv2) or ext in ("ape", "mpc", "wv", "tak", "ofr"):
        if f.tags is None:
            f.add_tags()
        _write_ape(f.tags, fields, covers)
    else:
        if f.tags is None:
            f.add_tags()
        _write_vorbis(f, fields, covers)
    f.save()


def _is_id3_container(f) -> bool:
    return type(f).__name__ in ("AIFF", "WAVE", "DSF")


def _write_id3(tags: id3.ID3, fields: dict[str, list[str]], covers) -> None:
    keep = {"APIC"} if covers is None else set()
    comment_names = {f.desc.upper(): f.desc for f in tags.getall("COMM")}     # fields only know capitals
    for key in list(tags.keys()):
        fid = key[:4]
        if fid in keep or fid in ("PRIV", "UFID", "MCDI", "GEOB", "SYLT", "CHAP", "CTOC"):
            continue
        del tags[key]
    for name, vals in fields.items():
        if name == "YEAR":
            tags.add(id3.TDRC(encoding=3, text=vals))
        elif name == "ORIGYEAR":
            tags.add(id3.TDOR(encoding=3, text=vals))
        elif name in ID3_TEXT:
            cls = getattr(id3, ID3_TEXT[name])
            tags.add(cls(encoding=3, text=vals))
        elif name in ID3_URL:
            tags.add(getattr(id3, ID3_URL[name])(url=vals[0]))
        elif name.startswith("WWW"):          # user-defined URL (read from WXXX)
            tags.add(id3.WXXX(encoding=3, desc=name[3:], url=vals[0]))
        elif name == "COMMENT":
            tags.add(id3.COMM(encoding=3, lang="eng", desc="", text=vals))
        elif name.startswith("COMMENT "):
            desc = _ITUNES_COMMENTS.get(name[8:]) or comment_names.get(name[8:], name[8:])
            tags.add(id3.COMM(encoding=3, lang="eng", desc=desc, text=vals))
        elif name == "UNSYNCEDLYRICS":
            tags.add(id3.USLT(encoding=3, lang="eng", desc="", text=vals[0]))
        elif name == "RATING":
            try:
                tags.add(id3.POPM(email="", rating=int(vals[0]), count=0))
            except ValueError:
                pass
        else:
            tags.add(id3.TXXX(encoding=3, desc=ID3_TXXX.get(name, name), text=vals))
    for c in covers or []:
        tags.add(id3.APIC(encoding=3, mime=c.mime, type=c.type, desc=c.description, data=c.data))


_MP4_FIELD_ATOMS = {"trkn", "disk", "tmpo", "cpil", *MP4_TEXT.values()}


def _write_mp4(f: MP4, fields: dict[str, list[str]], covers) -> None:
    # Only replace what PsyTags reads; atoms it does not know (rating, gapless
    # playback, other freeform namespaces, ...) stay as they are.
    for k in list(f.tags.keys()):
        if k in _MP4_FIELD_ATOMS or k.startswith(MP4_FREEFORM)                 or (k == "covr" and covers is not None):
            del f.tags[k]
    for name, vals in fields.items():
        if name in ("TRACK", "DISCNUMBER"):
            n, _, t = vals[0].partition("/")
            try:
                f.tags["trkn" if name == "TRACK" else "disk"] = [(int(n or 0), int(t or 0))]
            except ValueError:
                pass
        elif name == "BPM":
            try:
                f.tags["tmpo"] = [int(float(vals[0]))]
            except ValueError:
                pass
        elif name == "COMPILATION":
            f.tags["cpil"] = vals[0] not in ("0", "")
        elif name in MP4_TEXT:
            f.tags[MP4_TEXT[name]] = vals
        else:
            f.tags[MP4_FREEFORM + name] = [MP4FreeForm(v.encode("utf-8")) for v in vals]
    if covers is not None:
        if covers:
            f.tags["covr"] = [MP4Cover(c.data, MP4Cover.FORMAT_PNG if c.mime == "image/png"
                                       else MP4Cover.FORMAT_JPEG) for c in covers]


def _write_asf(f: ASF, fields: dict[str, list[str]], covers) -> None:
    existing = {k.upper(): k for k in f.tags.keys()}
    for k in list(f.tags.keys()):
        if _asf_is_field(k, f.tags[k]) or (k == ASF_PICTURE and covers is not None):
            del f.tags[k]
    for name, vals in fields.items():
        key = ASF_WRITE.get(name) or existing.get(name, name)
        if name == "COMPILATION":
            f.tags[key] = [ASFBoolAttribute(vals[0] not in ("0", ""))]
        else:
            f.tags[key] = [ASFUnicodeAttribute(v) for v in vals]
    if covers:
        f.tags[ASF_PICTURE] = [ASFByteArrayAttribute(_asf_picture_write(c)) for c in covers]


def _write_ape(tags: APEv2, fields: dict[str, list[str]], covers=None) -> None:
    for k in list(tags.keys()):
        if tags[k].kind == 0 or (covers is not None and k.lower().startswith("cover art")):
            del tags[k]
    for name, vals in fields.items():
        tags[APE_WRITE.get(name, name)] = vals
    for c in covers or []:
        key = {3: "Cover Art (Front)", 4: "Cover Art (Back)"}.get(c.type, "Cover Art (Other)")
        if key in tags:                       # APEv2 keys are unique
            continue
        ext = "png" if c.mime == "image/png" else "jpg"
        tags[key] = APEValue(f"cover.{ext}".encode() + b"\0" + c.data, BINARY)


def _write_vorbis(f, fields: dict[str, list[str]], covers) -> None:
    for k in list(f.tags.keys()):
        if k.upper() == "METADATA_BLOCK_PICTURE" and covers is None:
            continue
        del f.tags[k]
    for name, vals in fields.items():
        f.tags[VORBIS_WRITE.get(name, name)] = vals
    if covers is None:
        return
    if isinstance(f, FLAC):
        f.clear_pictures()
        for c in covers:
            f.add_picture(_picture(c))
    else:
        import base64
        if covers:
            f.tags["METADATA_BLOCK_PICTURE"] = [
                base64.b64encode(_picture(c).write()).decode("ascii") for c in covers]


def _picture(c: Cover) -> Picture:
    p = Picture()
    p.data, p.mime, p.type, p.desc = c.data, c.mime, c.type, c.description
    return p


def remove(path: str) -> None:
    """Remove all tags."""
    ext = os.path.splitext(path)[1].lower().lstrip(".")
    if ext in ("mp3", "mp2", "aac"):
        _remove_mp3(path)
        return
    f = mutagen.File(path)
    if f is not None and f.tags is not None:
        f.delete()
        if isinstance(f, FLAC):
            f.clear_pictures()
            f.save()


def _remove_mp3(path: str) -> None:
    try:
        id3.ID3(path).delete(path, delete_v1=True, delete_v2=True)
    except id3.ID3NoHeaderError:
        id3.delete(path, delete_v1=True, delete_v2=True)
    try:
        APEv2(path).delete(path)
    except (APENoHeaderError, mutagen.MutagenError):
        pass
