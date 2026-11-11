import os
import shutil
import subprocess
import tempfile
import unittest

from psytags import tags
from psytags.track import Track


class FakeTrack:
    def __init__(self, fields=None, path="/music/Artist - Album/01 - Song.mp3"):
        self.fields = {k: (v if isinstance(v, list) else [v]) for k, v in (fields or {}).items()}
        self.path = path
        self._script_vars = {}
        self.data = type("D", (), {"covers": []})()

    @property
    def folder(self):
        return os.path.dirname(self.path)

    @property
    def filename(self):
        return os.path.basename(self.path)

    def get(self, n):
        return self.fields.get(n.upper(), [])

    def set(self, n, v):
        if isinstance(v, str):
            v = [v] if v else []
        if v:
            self.fields[n.upper()] = v
        else:
            self.fields.pop(n.upper(), None)

    def field(self, n):
        n = n.upper()
        if n == "_FILENAME":
            return [os.path.splitext(self.filename)[0]]
        if n == "_FILENAME_EXT":
            return [self.filename]
        if n == "_DIRECTORY":
            return [os.path.basename(self.folder)]
        return self.fields.get(n, [])


T = FakeTrack({"ARTIST": ["AC/DC", "Guest"], "TITLE": "Back in Black", "TRACK": "3/10",
               "ALBUM": "Back in Black", "YEAR": "1980"})


class GenreMoodTests(unittest.TestCase):
    def test_classify_lastfm_tags(self):
        from psytags import genremood
        tags_ = [("classic rock", 100), ("seen live", 90), ("hard rock", 80), ("melancholy", 40),
                 ("hip-hop", 30), ("70s", 25), ("Energetic", 20), ("blues rock", 5)]
        genres, moods = genremood.classify(tags_)
        self.assertEqual(genres, ["Classic Rock", "Hard Rock", "Hip Hop"])
        self.assertEqual(moods, ["Melancholic", "Energetic"])

    def test_list_fields_joined_with_semicolon(self):
        t = Track("x.mp3")
        t.set("GENRE", "Rock\\\\Pop; rock ;  Blues ")
        self.assertEqual(t.get("GENRE"), ["Rock; Pop; Blues"])
        t.set("MOOD", ["Dark", "Sad"])
        self.assertEqual(t.get("MOOD"), ["Dark; Sad"])
        t.set("ARTIST", "A\\\\B")
        self.assertEqual(t.get("ARTIST"), ["A", "B"])


class SettingsTests(unittest.TestCase):
    def test_string_list_single_entry(self):
        from PySide6.QtCore import QSettings
        from psytags import config
        d = tempfile.mkdtemp()
        try:
            ini = os.path.join(d, "t.ini")
            s = QSettings(ini, QSettings.Format.IniFormat)
            s.setValue("dirs/history", ["C:\\Musik\\Yes"])
            s.setValue("dirs/more", ["a", "b"])
            s.sync()
            s = QSettings(ini, QSettings.Format.IniFormat)
            self.assertEqual(config.string_list(s, "dirs/history"), ["C:\\Musik\\Yes"])
            self.assertEqual(config.string_list(s, "dirs/more"), ["a", "b"])
            self.assertEqual(config.string_list(s, "dirs/missing"), [])
        finally:
            shutil.rmtree(d)


class AsfPictureTests(unittest.TestCase):
    """A broken WM/Picture is skipped instead of stopping the folder reader."""

    def _read(self, data):
        import threading
        result = []
        worker = threading.Thread(target=lambda: result.append(tags._asf_picture_read(data)),
                                  daemon=True)
        worker.start()
        worker.join(2)
        self.assertFalse(worker.is_alive(), "parser does not return")
        return result[0]

    def test_cut_off_text_is_skipped(self):
        self.assertIsNone(self._read(bytes([3, 1, 0, 0, 0, 97, 98, 99])))

    def test_image_shorter_than_declared_is_skipped(self):
        good = tags._asf_picture_write(tags.Cover(b"12345", "image/png", 3, "x"))
        self.assertIsNone(self._read(good[:-2]))

    def test_intact_picture_reads_back(self):
        c = self._read(tags._asf_picture_write(tags.Cover(b"12345", "image/png", 4, "Back")))
        self.assertEqual((c.data, c.mime, c.type, c.description),
                         (b"12345", "image/png", 4, "Back"))


class TagWriteTests(unittest.TestCase):
    def test_id3_user_url_stays_wxxx(self):
        from mutagen import id3
        d = tempfile.mkdtemp()
        try:
            p = os.path.join(d, "a.mp3")
            open(p, "wb").close()
            t = id3.ID3()
            t.add(id3.WXXX(encoding=3, desc="Homepage", url="https://x.example"))
            t.save(p)
            td = tags.TagData()
            tags._read_id3(id3.ID3(p), td)          # file has no audio frames
            self.assertEqual(td.fields.get("WWWHOMEPAGE"), ["https://x.example"])
            tags.write(p, td.fields, None)
            frames = id3.ID3(p)
            self.assertEqual([f.FrameID for f in frames.values()], ["WXXX"])
            self.assertEqual(frames.getall("WXXX")[0].url, "https://x.example")
        finally:
            shutil.rmtree(d)

    def test_ape_covers_written_and_removed(self):
        from mutagen.apev2 import APEv2
        ape = APEv2()
        ape["Cover Art (Front)"] = tags.APEValue(b"old.jpg\0old", tags.BINARY)
        tags._write_ape(ape, {"TITLE": ["x"]}, [tags.Cover(b"\x89PNG new", "image/png", 3)])
        td = tags.TagData()
        tags._read_ape(ape, td)
        self.assertEqual(td.covers, [tags.Cover(b"\x89PNG new", "image/png", 3)])
        tags._write_ape(ape, {"TITLE": ["x"]}, None)          # None keeps covers
        self.assertIn("Cover Art (Front)", ape)
        tags._write_ape(ape, {"TITLE": ["x"]}, [])            # [] removes them
        self.assertNotIn("Cover Art (Front)", ape)


class UndoTests(unittest.TestCase):
    class _T:
        def __init__(self, title, fail=False):
            self.path = "/m/" + title
            self.data = tags.TagData({"TITLE": [title]})
            self._saved = tags.TagData({"TITLE": [title]})
            self.fail = fail

        def save(self, **_):
            if self.fail:
                raise OSError("read-only")
            self._saved = tags.TagData(dict(self.data.fields), list(self.data.covers))

        def revert(self):
            self.data = tags.TagData(dict(self._saved.fields), list(self._saved.covers))

    def test_failed_undo_keeps_entry_and_rolls_back(self):
        from types import SimpleNamespace
        from psytags.undo import Recorder, UndoStack
        opts = SimpleNamespace(id3_version=3, write_id3v1=False, keep_mtime=False)
        a, b = self._T("a"), self._T("b")
        rec = Recorder("x")
        for t in (a, b):
            rec.before(t)
            t.data.fields["TITLE"] = ["new"]
            t.save()
        st = UndoStack()
        st.push(rec.finish())
        a.fail = True                     # undo runs b first, then fails on a
        with self.assertRaises(OSError):
            st.undo(opts)
        self.assertEqual(len(st.undo_ops), 1)
        self.assertEqual(len(st.redo_ops), 0)
        self.assertEqual(b._saved.fields["TITLE"], ["new"])   # b rolled back
        a.fail = False
        st.undo(opts)
        self.assertEqual((a._saved.fields["TITLE"], b._saved.fields["TITLE"]), (["a"], ["b"]))
        self.assertEqual(len(st.redo_ops), 1)


class RealFileTests(unittest.TestCase):
    """Round-trip with real audio files (needs ffmpeg)."""

    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.files = []
        if not shutil.which("ffmpeg"):
            return
        for ext, codec in (("mp3", "libmp3lame"), ("flac", "flac"), ("m4a", "aac"),
                           ("opus", "libopus"), ("ogg", "libvorbis"), ("wma", "wmav2")):
            p = os.path.join(cls.dir, "t." + ext)
            r = subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                                "sine=frequency=440:duration=1", "-c:a", codec, p])
            if r.returncode == 0:
                cls.files.append(p)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir)

    def test_roundtrip(self):
        if not self.files:
            self.skipTest("ffmpeg not available")
        for p in self.files:
            t = Track(p).load()
            t.set("TITLE", "Tïtel")
            t.set("ARTIST", ["A", "B"])
            t.set("ALBUMARTIST", "AA")
            t.set("TRACK", "3/10")
            t.set("DISCNUMBER", "1/2")
            t.set("MUSICBRAINZ_ALBUMTYPE", "EP")
            t.data.covers = [tags.Cover(b"\x89PNG fake", "image/png", 3, "")]
            t.save()
            r = Track(p).load()
            self.assertEqual(r.get("TITLE"), ["Tïtel"], p)
            self.assertEqual(r.get("ALBUMARTIST"), ["AA"], p)
            self.assertEqual(r.get("TRACK"), ["3/10"], p)
            self.assertEqual(r.get("DISCNUMBER"), ["1/2"], p)
            self.assertEqual(r.get("MUSICBRAINZ_ALBUMTYPE"), ["EP"], p)
            self.assertEqual(len(r.data.covers), 1, p)
            self.assertIn(r.get("ARTIST"), (["A", "B"], ["A/B"]), p)
            r.remove_tags()
            self.assertEqual(Track(p).load().fields, {}, p)

    def test_vorbis_release_type_single_key(self):
        import mutagen
        vorbis = [p for p in self.files if p.endswith((".flac", ".opus", ".ogg"))]
        if not vorbis:
            self.skipTest("ffmpeg not available")
        for p in vorbis:
            f = mutagen.File(p)
            if f.tags is None:
                f.add_tags()
            f.tags["releasetype"] = ["album"]
            f.tags["musicbrainz_albumtype"] = ["Album"]
            f.save()
            t = Track(p).load()
            self.assertEqual([v.lower() for v in t.get("MUSICBRAINZ_ALBUMTYPE")], ["album"], p)
            t.set("TITLE", "x")
            t.save()
            keys = {k.upper() for k in mutagen.File(p).tags.keys()}
            self.assertIn("RELEASETYPE", keys, p)
            self.assertNotIn("MUSICBRAINZ_ALBUMTYPE", keys, p)
            Track(p).load().remove_tags()

    def _file(self, ext):
        p = [x for x in self.files if x.endswith("." + ext)]
        if not p:
            self.skipTest(f"ffmpeg cannot write {ext}")
        return p[0]

    def test_mp4_keeps_atoms_it_does_not_know(self):
        from mutagen.mp4 import MP4, MP4FreeForm
        p = self._file("m4a")
        f = MP4(p)
        if f.tags is None:
            f.add_tags()
        f.tags["\xa9nam"] = ["Before"]
        f.tags["\xa9alb"] = ["Album"]
        f.tags["rtng"] = [1]
        f.tags["pgap"] = True
        f.tags["----:org.example:CUSTOM"] = [MP4FreeForm(b"keep")]
        f.save()
        t = Track(p).load()
        t.set("TITLE", "After")
        t.set("ALBUM", "")
        t.save()
        tags_ = MP4(p).tags
        self.assertEqual(tags_["\xa9nam"], ["After"])
        self.assertNotIn("\xa9alb", tags_)                 # removed in PsyTags, removed in the file
        self.assertEqual(tags_["rtng"], [1])
        self.assertTrue(tags_["pgap"])
        self.assertEqual(bytes(tags_["----:org.example:CUSTOM"][0]), b"keep")
        Track(p).load().remove_tags()

    def test_wma_maps_the_usual_fields(self):
        from mutagen.asf import ASF
        p = self._file("wma")
        f = ASF(p)
        for k in list(f.tags.keys()):
            del f.tags[k]
        f.tags["Title"] = ["Before"]
        f.tags["Author"] = ["Artist"]
        f.tags["WM/AlbumTitle"] = ["Test Album"]
        f.tags["WM/TrackNumber"] = ["4"]
        f.tags["WM/Year"] = ["1999"]
        f.tags["WM/Mood"] = ["Calm"]
        f.save()
        t = Track(p).load()
        self.assertEqual(t.get("TITLE"), ["Before"])
        self.assertEqual(t.get("ARTIST"), ["Artist"])
        self.assertEqual(t.get("ALBUM"), ["Test Album"])
        self.assertEqual(t.get("TRACK"), ["4"])
        self.assertEqual(t.get("YEAR"), ["1999"])
        self.assertEqual(t.get("MOOD"), ["Calm"])
        t.set("TITLE", "After")
        t.save()
        keys = {str(k) for k in ASF(p).tags.keys()}
        self.assertIn("Title", keys)
        self.assertNotIn("TITLE", keys)
        self.assertIn("WM/AlbumTitle", keys)
        self.assertNotIn("WM/ALBUMTITLE", keys)
        r = Track(p).load()
        self.assertEqual(r.get("TITLE"), ["After"])
        self.assertEqual(r.get("ALBUM"), ["Test Album"])
        r.remove_tags()


if __name__ == "__main__":
    unittest.main()


class DefaultPanelTests(unittest.TestCase):
    def test_the_album_type_is_a_default_field_after_the_album_id(self):
        from psytags import config
        values = [f.value for f in config.DEFAULT_PANEL]
        self.assertEqual(values.index("MUSICBRAINZ_ALBUMTYPE"), values.index("MUSICBRAINZ_ALBUMID") + 1)
