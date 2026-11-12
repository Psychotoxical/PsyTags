"""Covers are held once in memory, however often a file is reloaded or how many share one."""
import gc
import os
import shutil
import tempfile
import unittest

from psytags import tags
from psytags.track import Track

# 128 kbit/s, 44.1 kHz MPEG-1 Layer III frames of silence
FRAME = b"\xff\xfb\x90\x64" + bytes(413)
PICTURE = b"\xff\xd8\xff\xe0" + os.urandom(50_000)


class CoverSharingTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.folder)

    def _file(self, name, picture=PICTURE):
        path = os.path.join(self.folder, name)
        with open(path, "wb") as fh:
            fh.write(FRAME * 20)
        tags.write(path, {"TITLE": [name]}, [tags.Cover(picture)])
        return path

    def test_a_reload_keeps_the_same_picture(self):
        t = Track(self._file("a.mp3")).load()
        before = t.data.covers[0]
        t.load()
        self.assertIs(t.data.covers[0], before)

    def test_the_files_of_an_album_share_their_cover(self):
        a, b = Track(self._file("a.mp3")).load(), Track(self._file("b.mp3")).load()
        self.assertIs(a.data.covers[0].data, b.data.covers[0].data)

    def test_different_pictures_stay_apart(self):
        a = Track(self._file("a.mp3")).load()
        b = Track(self._file("b.mp3", PICTURE + b"x")).load()
        self.assertIsNot(a.data.covers[0], b.data.covers[0])
        self.assertNotEqual(a.data.covers[0].data, b.data.covers[0].data)

    def test_an_unused_picture_is_let_go(self):
        t = Track(self._file("a.mp3")).load()
        count = len(tags._known_covers)
        t.data.covers = t._saved.covers = []
        gc.collect()
        self.assertEqual(len(tags._known_covers), count - 1)


if __name__ == "__main__":
    unittest.main()
