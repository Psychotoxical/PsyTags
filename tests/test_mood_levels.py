import os
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config, moodanalysis as ma
from psytags.config import Options


def _values(**kw):
    return [kw.get(n, 0.0) for n in ma.MOOD_CLASSES]


def _threshold(level, name):
    return max(ma.LEVELS[level].min_value, ma.REFERENCE[name] * ma.LEVELS[level].min_lift)


class LevelTests(unittest.TestCase):
    def test_normal_is_the_default(self):
        v = _values(heavy=_threshold("normal", "heavy") * 1.01)
        self.assertEqual(ma.pick_moods(v), ma.pick_moods(v, "normal"))
        self.assertEqual(ma.pick_moods(v), ["Heavy"])

    def test_few_drops_what_normal_only_just_accepts(self):
        v = _values(heavy=_threshold("normal", "heavy") * 1.01)
        self.assertEqual(ma.pick_moods(v, "few"), [])

    def test_many_accepts_what_normal_drops(self):
        value = _threshold("many", "heavy") * 1.01
        self.assertLess(value, _threshold("normal", "heavy"))
        v = _values(heavy=value)
        self.assertEqual(ma.pick_moods(v, "many"), ["Heavy"])
        self.assertEqual(ma.pick_moods(v, "normal"), [])

    def test_every_level_keeps_its_limit(self):
        v = [0.9 for _ in ma.MOOD_CLASSES]
        for name, level in ma.LEVELS.items():
            self.assertEqual(len(ma.pick_moods(v, name)), level.max_moods, name)

    def test_the_limits_rise_from_few_to_many(self):
        self.assertLess(ma.LEVELS["few"].max_moods, ma.LEVELS["normal"].max_moods)
        self.assertLess(ma.LEVELS["normal"].max_moods, ma.LEVELS["many"].max_moods)

    def test_an_unknown_level_counts_as_normal(self):
        v = _values(heavy=_threshold("normal", "heavy") * 1.01)
        self.assertEqual(ma.pick_moods(v, "kaputt"), ["Heavy"])

    def test_the_analyzer_passes_the_level_on(self):
        v = _values(heavy=_threshold("normal", "heavy") * 1.01)
        analyzer = NS(song_values=lambda _path: NS(tolist=lambda: v))
        self.assertEqual(ma.Analyzer.moods(analyzer, "a.mp3"), ["Heavy"])
        self.assertEqual(ma.Analyzer.moods(analyzer, "a.mp3", "few"), [])


class SettingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        os.makedirs(os.path.join(folder.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: folder.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_normal_is_the_stored_default(self):
        self.assertEqual(Options.load().mood_level, "normal")

    def test_the_choice_is_kept(self):
        Options(mood_level="few").save()
        self.assertEqual(Options.load().mood_level, "few")

    def test_the_dialog_offers_three_levels_and_saves_the_choice(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        self.assertEqual(d.mood_level.count(), 3)
        self.assertEqual(d.mood_level.currentData(), "normal")
        d.mood_level.setCurrentIndex(d.mood_level.findData("many"))
        d.accept()
        self.assertEqual(d.opts.mood_level, "many")

    def test_the_analysis_uses_the_chosen_level(self):
        from psytags.ui import mainwindow as mw
        win = mock.MagicMock(opts=Options(mood_level="few"), _mood_done={})
        win._background.side_effect = lambda _label, call: call()
        seen = {}

        def analyze_files(paths, moods_of, **_kw):
            seen["moods_of"] = moods_of
            return ma.AnalysisResult()
        with mock.patch.object(ma, "ensure_models"), mock.patch.object(ma, "Analyzer") as analyzer, \
                mock.patch.object(ma, "analyze_files", analyze_files), \
                mock.patch.object(mw, "_StayingProgress") as dialog:
            dialog.return_value.stop.is_set.return_value = False
            mw.MainWindow.analyze_moods(win, [NS(path="a.mp3")])
            seen["moods_of"]("a.mp3")
        analyzer.return_value.moods.assert_called_once_with("a.mp3", "few")


if __name__ == "__main__":
    unittest.main()
