"""Files whose path is longer than Windows' MAX_PATH can be read, saved and renamed."""
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

from psytags import convert, longpath
from psytags.track import Track

# 128 kbit/s, 44.1 kHz MPEG-1 Layer III frames of silence
FRAME = b"\xff\xfb\x90\x64" + bytes(413)


def _deep_folder(root: str) -> str:
    folder = root
    while len(folder) < 230:
        folder = os.path.join(folder, "Album " + "x" * 40)
    os.makedirs(longpath.io(folder))
    return folder


@unittest.skipUnless(sys.platform == "win32", "only Windows limits the path length")
class LongPathTests(unittest.TestCase):
    def setUp(self):
        root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, "\\\\?\\" + root)    # rmtree also needs the long form
        self.folder = _deep_folder(root)
        self.path = os.path.join(self.folder, "01 - Band feat. " + "Guest, " * 8 + "- Title.mp3")
        self.assertGreater(len(self.path), 260)
        with open(longpath.io(self.path), "wb") as fh:
            fh.write(FRAME * 40)

    def test_short_paths_stay_as_they_are(self):
        self.assertEqual(longpath.io(r"C:\Music\a.mp3"), r"C:\Music\a.mp3")

    def test_a_long_path_gets_the_long_form(self):
        self.assertTrue(longpath.io(self.path).startswith("\\\\?\\"))

    def test_a_file_with_a_long_path_is_saved_and_read(self):
        t = Track(self.path).load()
        self.assertEqual(t.error, "")
        t.set("TITLE", "Title")
        t.save(keep_mtime=True)
        self.assertEqual(Track(self.path).load().get("TITLE"), ["Title"])

    def test_a_file_with_a_long_path_is_renamed(self):
        t = Track(self.path).load()
        new = os.path.join(self.folder, "01 - Title.mp3")
        convert.rename(t, new)
        self.assertTrue(os.path.exists(new))
        self.assertFalse(os.path.exists(longpath.io(self.path)))


class OtherSystemsTests(unittest.TestCase):
    def test_nothing_changes_elsewhere(self):
        from unittest import mock
        with mock.patch.object(longpath, "sys", SimpleNamespace(platform="linux")):
            self.assertEqual(longpath.io("/x" * 200), "/x" * 200)


if __name__ == "__main__":
    unittest.main()
