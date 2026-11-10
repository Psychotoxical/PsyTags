import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

from psytags import convert, moodanalysis as ma


class BundledFfmpegTests(unittest.TestCase):
    def _package(self, folder, name=None):
        path = os.path.join(folder, "ffmpeg", name or ("ffmpeg.exe" if ma.sys.platform == "win32" else "ffmpeg"))
        os.makedirs(os.path.dirname(path))
        open(path, "wb").close()
        return path

    def test_each_system_looks_for_its_own_program_name(self):
        for platform, name in (("win32", "ffmpeg.exe"), ("linux", "ffmpeg")):
            with tempfile.TemporaryDirectory() as folder, \
                    mock.patch.object(ma.sys, "_MEIPASS", folder, create=True), \
                    mock.patch.object(ma.sys, "platform", platform), \
                    mock.patch.object(ma.shutil, "which", return_value=None):
                path = self._package(folder, name)
                self.assertEqual(ma._ffmpeg(), path)

    def test_the_package_uses_its_own_ffmpeg_first(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(ma.sys, "_MEIPASS", folder, create=True), \
                mock.patch.object(ma.shutil, "which", return_value="C:/other/ffmpeg.exe"):
            path = self._package(folder)
            self.assertEqual(ma._ffmpeg(), path)

    def test_the_package_needs_no_ffmpeg_in_the_path(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(ma.sys, "_MEIPASS", folder, create=True), \
                mock.patch.object(ma.shutil, "which", return_value=None):
            self._package(folder)
            self.assertTrue(ma.ffmpeg_available())

    def test_from_source_the_path_counts(self):
        with mock.patch.object(ma.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(ma._ffmpeg(), "/usr/bin/ffmpeg")

    def test_a_package_without_its_ffmpeg_falls_back_to_the_path(self):
        with tempfile.TemporaryDirectory() as folder, \
                mock.patch.object(ma.sys, "_MEIPASS", folder, create=True), \
                mock.patch.object(ma.shutil, "which", return_value="/usr/bin/ffmpeg"):
            self.assertEqual(ma._ffmpeg(), "/usr/bin/ffmpeg")

    def test_nothing_found_is_reported(self):
        with mock.patch.object(ma.shutil, "which", return_value=None):
            self.assertFalse(ma.ffmpeg_available())
            with self.assertRaises(ma.MoodError):
                ma._ffmpeg()

    def test_on_linux_the_message_names_the_package_manager(self):
        with mock.patch.object(ma.sys, "platform", "linux"):
            self.assertIn("Paketverwaltung", ma.ffmpeg_missing())

    def test_on_windows_the_message_names_the_path(self):
        with mock.patch.object(ma.sys, "platform", "win32"):
            self.assertIn("PATH", ma.ffmpeg_missing())


def long_name(n):
    return "ä" * n


class LinuxNameTests(unittest.TestCase):
    def _place(self, *parts, path=None):
        path = path or os.path.join(os.sep, "music", "old", "a.mp3")
        track = NS(path=path, folder=os.path.dirname(path))
        with mock.patch.object(convert.sys, "platform", "linux"):
            return convert.place(track, list(parts))

    def _sizes(self, target):
        return [len(p.encode("utf-8")) for p in target.split(os.sep)]

    def test_a_short_name_stays(self):
        self.assertTrue(self._place("Album", "01 - Song").endswith(os.path.join("Album", "01 - Song.mp3")))

    def test_a_file_name_is_limited_in_bytes_not_characters(self):
        target = self._place(long_name(200))                # 200 characters, 400 bytes
        self.assertLessEqual(self._sizes(target)[-1], 255)
        self.assertTrue(target.endswith(".mp3"))

    def test_no_character_is_cut_in_half(self):
        target = self._place(long_name(200))
        os.path.basename(target).encode("utf-8").decode("utf-8")
        self.assertNotIn("\ufffd", target)

    def test_a_folder_name_is_limited_as_well(self):
        target = self._place(long_name(200), "Song")
        self.assertLessEqual(max(self._sizes(target)), 255)

    def test_guests_go_first(self):
        name = "01 - Song feat. " + "x" * 300
        self.assertTrue(self._place(name).endswith("01 - Song.mp3"))

    def test_a_long_path_of_short_names_stays_on_linux(self):
        parts = ["a" * 200, "b" * 200, "c" * 200]
        self.assertTrue(self._place(*parts).endswith(os.path.join(*parts) + ".mp3"))

    def test_windows_still_limits_the_whole_path(self):
        path = os.path.join("C:" + os.sep, "m", "o", "a.mp3")
        track = NS(path=path, folder=os.path.dirname(path))
        with mock.patch.object(convert.sys, "platform", "win32"):
            target = convert.place(track, ["a" * 200, "b" * 200])
        self.assertLessEqual(len(target), convert.WINDOWS_PATH_LIMIT)


class FolderCaseTests(unittest.TestCase):
    def test_linux_leaves_folders_alone(self):
        with mock.patch.object(convert.sys, "platform", "linux"), \
                mock.patch.object(convert.os, "listdir") as listing, \
                mock.patch.object(convert.os, "rename") as renaming:
            convert.fix_folder_case([("x", os.path.join(os.sep, "music", "Rise of", "a.mp3"))])
        listing.assert_not_called()
        renaming.assert_not_called()

    def test_windows_still_looks(self):
        with mock.patch.object(convert.sys, "platform", "win32"), \
                mock.patch.object(convert.os, "listdir", return_value=[]) as listing:
            convert.fix_folder_case([("x", os.path.join(os.sep, "music", "Rise of", "a.mp3"))])
        listing.assert_called_once()


if __name__ == "__main__":
    unittest.main()
