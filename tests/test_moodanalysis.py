import hashlib
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from psytags import genremood, moodanalysis as ma


def _values(**kw):
    """Activations at their reference level (lift 1) except the named classes."""
    return [kw.get(n, ma.REFERENCE[n]) for n in ma.MOOD_CLASSES]


class PickMoodsTests(unittest.TestCase):
    def test_nothing_above_the_thresholds(self):
        self.assertEqual(ma.pick_moods(_values()), [])

    def test_needs_value_and_lift(self):
        # "party" reaches lift 2 but stays below the minimum value
        self.assertEqual(ma.pick_moods(_values(party=0.03)), [])
        # "energetic" has a high value but lift below 1.2
        self.assertGreater(ma.REFERENCE["energetic"] * 1.1, ma.LEVELS["normal"].min_value)
        self.assertEqual(ma.pick_moods(_values(energetic=ma.REFERENCE["energetic"] * 1.1)), [])

    def test_ranked_by_value_times_lift(self):
        got = ma.pick_moods(_values(energetic=0.33, heavy=0.15, powerful=0.07))
        self.assertEqual(got, ["Energetic", "Heavy", "Powerful"])

    def test_at_most_four_and_no_duplicates(self):
        got = ma.pick_moods(_values(uplifting=0.2, inspiring=0.2, motivational=0.2, happy=0.3,
                                    sad=0.3, dark=0.4, epic=0.4))
        self.assertEqual(len(got), 4)
        self.assertEqual(len(set(got)), 4)

    def test_themes_never_become_moods(self):
        self.assertEqual(ma.pick_moods(_values(film=0.9, trailer=0.9, corporate=0.9, advertising=0.9)), [])

    def test_descriptive_classes_have_names(self):
        for name, label in (("action", "Action"), ("adventure", "Adventure"), ("ballad", "Ballad"), ("cool", "Cool"),
                            ("deep", "Deep"), ("fast", "Fast"), ("funny", "Funny"), ("love", "Romantic"),
                            ("melodic", "Melodic"), ("retro", "Retro"), ("slow", "Slow")):
            self.assertEqual(ma.pick_moods(_values(**{name: 0.5})), [label])

    def test_love_and_romantic_count_once(self):
        self.assertEqual(ma.pick_moods(_values(love=0.5, romantic=0.2)), ["Romantic"])

    def test_thirty_three_names(self):
        self.assertEqual(len(set(ma.MOOD_NAMES.values())), 33)

    def test_names_are_in_the_vocabulary(self):
        known = set(genremood.MOODS)        # "Ballad" is also a genre, see the next test
        self.assertEqual(set(ma.MOOD_NAMES.values()) - known, {"Ballad"})

    def test_ballad_from_lastfm_stays_a_genre(self):
        self.assertEqual(genremood.classify([("ballad", 100)]), (["Ballad"], []))


class FeatureTests(unittest.TestCase):
    def test_filterbank(self):
        fb = ma.filterbank()
        self.assertEqual(fb.shape, (96, 257))
        self.assertGreaterEqual(float(fb.min()), 0.0)
        self.assertAlmostEqual(float(fb[95].sum()) * 31.25, 1.0, delta=0.05)  # unit_tri: area 1

    def test_too_short(self):
        self.assertIsNone(ma.melspec(np.zeros(1000, dtype=np.float32)))
        self.assertIsNone(ma.melspec(np.zeros(0, dtype=np.float32)))

    def test_melspec_shape_and_peak(self):
        t = np.arange(48000) / 16000.0
        y = np.sin(2 * np.pi * 1000 * t).astype(np.float32)
        mel = ma.melspec(y)
        self.assertEqual(mel.shape, (1 + (48000 + 256 - 512) // 256, 96))
        peak = int(mel[50:100].mean(axis=0).argmax())
        fb = ma.filterbank()
        centre = int(fb[peak].argmax()) * 31.25
        self.assertLess(abs(centre - 1000), 120)

    def test_patches(self):
        p = ma.patches(np.zeros((300, 96), dtype=np.float32))
        self.assertEqual(p.shape, (3, 128, 96))        # starts at 0, 62, 124


class ModelFileTests(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name

    def _models(self, *contents):
        return {f"m{i}.onnx": (f"https://x/{i}", hashlib.sha256(c).hexdigest())
                for i, c in enumerate(contents)}

    def test_downloads_missing_files(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return b"good"
        with mock.patch.object(ma, "MODELS", self._models(b"good")):
            ma.ensure_models(os.path.join(self.dir, "new"), fetch=fetch)
            ma.ensure_models(os.path.join(self.dir, "new"), fetch=fetch)
        self.assertEqual(calls, ["https://x/0"])       # second call finds a valid file

    def test_wrong_checksum_leaves_nothing_behind(self):
        with mock.patch.object(ma, "MODELS", self._models(b"good")):
            with self.assertRaises(ma.MoodError):
                ma.ensure_models(self.dir, fetch=lambda url: b"broken")
        self.assertEqual(os.listdir(self.dir), [])

    def test_broken_file_is_replaced(self):
        with open(os.path.join(self.dir, "m0.onnx"), "wb") as fh:
            fh.write(b"old")
        with mock.patch.object(ma, "MODELS", self._models(b"good")):
            ma.ensure_models(self.dir, fetch=lambda url: b"good")
        with open(os.path.join(self.dir, "m0.onnx"), "rb") as fh:
            self.assertEqual(fh.read(), b"good")

    def test_decode_without_ffmpeg(self):
        with mock.patch.object(ma.shutil, "which", return_value=None):
            with self.assertRaises(ma.MoodError):
                ma.decode("x.mp3")


class AnalyzeFilesTests(unittest.TestCase):
    def test_bad_files_do_not_stop_the_run(self):
        def moods_of(path):
            if path == "bad":
                raise RuntimeError("corrupt")
            return None if path == "short" else ["Dark"] if path == "a" else []
        done = []
        r = ma.analyze_files(["a", "bad", "short", "b"], moods_of,
                             on_progress=lambda n, total: done.append((n, total)), workers=2)
        self.assertEqual(r.found, {"a": ["Dark"]})
        self.assertEqual(sorted(r.empty), ["b", "short"])
        self.assertEqual(r.failed, ["bad"])
        self.assertEqual(max(done), (4, 4))

    def test_stop_keeps_finished_songs(self):
        seen = []

        def moods_of(path):
            seen.append(path)
            return ["Calm"]
        r = ma.analyze_files(["a", "b", "c", "d"], moods_of, should_stop=lambda: len(seen) >= 2, workers=1)
        self.assertEqual(sorted(r.found), ["a", "b"])


class ThreadTests(unittest.TestCase):
    """Each song in progress holds about 600 MB: small computers analyze fewer at once."""

    def test_a_dual_core_analyzes_two_songs(self):
        self.assertEqual(ma.song_threads(2), 2)
        self.assertEqual(ma.song_threads(4), 2)            # two cores with hyper-threading

    def test_a_large_processor_stays_at_four(self):
        self.assertEqual(ma.song_threads(12), 4)
        self.assertEqual(ma.song_threads(32), 4)

    def test_one_core_one_song(self):
        self.assertEqual(ma.song_threads(1), 1)

    def test_the_model_threads_fill_the_processor(self):
        self.assertEqual(ma.model_threads(12), 3)          # as before: 4 songs x 3
        self.assertEqual(ma.model_threads(4), 2)
        self.assertEqual(ma.model_threads(2), 1)


if __name__ == "__main__":
    unittest.main()
