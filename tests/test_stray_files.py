"""Files left without a release in the folder of an album the run tagged show up with that album."""
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from psytags.track import Track
from psytags.websources import albumauto


def files(folder, *names, album="Album"):
    out = []
    for name in names:
        t = Track(os.path.join(tempfile.gettempdir(), folder, f"{name}.mp3"))
        t.set("ALBUM", album)
        out.append(t)
    return out


class StrayTests(unittest.TestCase):
    def test_a_bonus_track_with_another_album_tag_joins_the_finished_album(self):
        cd = files("Album", "01", "02", "03", "04")
        extra = files("Album", "13", album="Album (old tag)")
        done = albumauto.BatchEntry("Band - Album", cd, True, "Album (2026)")
        stray = albumauto.BatchEntry("Band - Album (old tag)", extra, False, "No matching edition found")
        entries = albumauto.attach_strays([done, stray])
        self.assertEqual(entries, [done])
        self.assertEqual(done.leftovers, extra)

    def test_files_already_left_over_stay_once(self):
        cd = files("Album", "01", "02", "03")
        old = files("Album", "12")
        extra = files("Album", "13", album="Other")
        done = albumauto.BatchEntry("A", cd, True, "", list(old))
        entries = albumauto.attach_strays([done, albumauto.BatchEntry("B", extra, False, "")])
        self.assertEqual(done.leftovers, old + extra)
        self.assertEqual(len(entries), 1)

    def test_an_open_album_elsewhere_or_a_large_one_stays_its_own_row(self):
        done = albumauto.BatchEntry("A", files("Album", "01", "02"), True, "")
        elsewhere = albumauto.BatchEntry("B", files("Other", "01"), False, "")
        large = albumauto.BatchEntry("C", files("Album", "x1", "x2", "x3", "x4", album="Second album"), False, "")
        entries = albumauto.attach_strays([done, elsewhere, large])
        self.assertEqual(entries, [done, elsewhere, large])
        self.assertEqual(done.leftovers, [])

    def test_two_finished_albums_in_one_folder_take_nothing(self):
        a = albumauto.BatchEntry("A", files("Split", "01"), True, "")
        b = albumauto.BatchEntry("B", files("Split", "02", album="Other"), True, "")
        stray = albumauto.BatchEntry("C", files("Split", "03", album="Third"), False, "")
        self.assertEqual(albumauto.attach_strays([a, b, stray]), [a, b, stray])


if __name__ == "__main__":
    unittest.main()
