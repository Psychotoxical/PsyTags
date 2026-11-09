import os
import random
import unittest
from types import SimpleNamespace

from psytags.albumorder import loaded_order, number, sort_by_folder
from psytags.track import Track
from psytags.websources import albumauto
from psytags.websources.albummatch import (Match, Release, clean_import, decide, file_info,
                                          match_release)
from psytags.websources.runner import Album


def F(title, length=200.0, name=None):
    return file_info(title, title, name or f"{title}.mp3", "Artist", length)


def R(titles, lengths=None, year="2001", digital=False):
    return Release("album", list(titles), list(lengths or [200.0] * len(titles)), year, digital)


TITLES = [f"Song Number {w}" for w in ("One", "Two", "Three", "Four", "Five", "Six", "Seven",
                                       "Eight", "Nine", "Ten", "Eleven", "Twelve")]


class CleanImportTests(unittest.TestCase):
    def test_only_the_year(self):
        got = clean_import({"YEAR": "2014-07-24", "ORIGYEAR": "1999-01", "ALBUM": "2014-07-24"}, False)
        self.assertEqual(got, {"YEAR": "2014", "ORIGYEAR": "1999", "ALBUM": "2014-07-24"})
        self.assertEqual(clean_import({"YEAR": "2014"}, False), {"YEAR": "2014"})
        self.assertEqual(clean_import({"YEAR": ""}, False), {"YEAR": ""})

    def test_existing_moods_stay(self):
        self.assertEqual(clean_import({"MOOD": "Sad", "GENRE": "Rock"}, True), {"GENRE": "Rock"})
        self.assertEqual(clean_import({"MOOD": "Sad"}, False), {"MOOD": "Sad"})


class MatchReleaseTests(unittest.TestCase):
    def test_typo_in_title_passes(self):
        m = match_release([F("Gorls Own Love")], R(["Girls Own Love"]))
        self.assertIsInstance(m, Match)
        self.assertLess(m.worst, 1.0)

    def test_file_name_gives_the_title(self):
        f = file_info("k", "", "Andy James - 01 - Enter Through Fire.mp3", "Andy James", 200.0)
        self.assertIn("enter through fire", f.titles)
        f = file_info("k", "", "01 - Andrew W.K. - Party Hard.mp3", "Andrew W.K.", 200.0)
        self.assertIn("party hard", f.titles)
        f = file_info("k", "", "2-03 - Other Song.flac", "", 200.0)
        self.assertIn("other song", f.titles)

    def test_bracket_additions_do_not_matter(self):
        self.assertIsInstance(match_release([F("Refugium (Live)")], R(["Refugium"])), Match)

    def test_order_of_files_is_irrelevant(self):
        files = [F(t) for t in TITLES]
        rel = R(TITLES)
        base = {files[f].key: t for f, t in match_release(files, rel).mapping.items()}
        shuffled = files[:]
        random.Random(3).shuffle(shuffled)
        again = {shuffled[f].key: t for f, t in match_release(shuffled, rel).mapping.items()}
        self.assertEqual(again, base)

    def test_foreign_file_stops(self):
        files = [F(t) for t in TITLES[:-1]] + [F("Something Completely Different", 350.0)]
        self.assertIsInstance(match_release(files, R(TITLES)), str)

    def test_fewer_files_than_tracks_stops(self):
        self.assertIsInstance(match_release([F(t) for t in TITLES[:-1]], R(TITLES)), str)

    def test_leftover_file_is_reported(self):
        files = [F(t) for t in TITLES[:11]] + [F("Flight Of Icarus (Bonus Track)")]
        m = match_release(files, R(TITLES[:11]))
        self.assertIsInstance(m, Match)
        self.assertEqual(m.leftover_keys, ["Flight Of Icarus (Bonus Track)"])

    def test_a_single_never_takes_over_an_album(self):
        self.assertIsInstance(match_release([F(t) for t in TITLES], R(TITLES[:1])), str)

    def test_at_most_three_leftovers_and_a_quarter(self):
        self.assertIsInstance(match_release([F(t) for t in TITLES[:12]], R(TITLES[:9])), Match)
        self.assertIsInstance(match_release([F(t) for t in TITLES[:12]], R(TITLES[:8])), str)
        self.assertIsInstance(match_release([F(t) for t in TITLES[:4]], R(TITLES[:2])), str)

    def test_length_limits(self):
        exact = [F("Long Song", 234.0)]
        self.assertIsInstance(match_release(exact, R(["Long Song"], [200.0])), Match)
        self.assertIsInstance(match_release([F("Long Song", 261.0)], R(["Long Song"], [200.0])), str)
        self.assertIsInstance(match_release([F("Gorls Own Love", 231.0)], R(["Girls Own Love"], [200.0])), str)
        self.assertIsInstance(match_release([F("Gorls Own Love", 229.0)], R(["Girls Own Love"], [200.0])), Match)

    def test_unknown_length_is_no_obstacle(self):
        self.assertIsInstance(match_release([F("Song", 200.0)], R(["Song"], [None])), Match)
        self.assertIsInstance(match_release([F("Song", 0.0)], R(["Song"], [100.0])), Match)

    def test_same_title_twice_goes_by_length(self):
        files = [file_info("short", "Intro", "a.mp3", "", 60.0), file_info("long", "Intro", "b.mp3", "", 120.0)]
        m = match_release(list(reversed(files)), R(["Intro", "Intro"], [121.0, 59.0]))
        by_key = {m.files[f].key: t for f, t in m.mapping.items()}
        self.assertEqual(by_key, {"long": 0, "short": 1})


class DecideTests(unittest.TestCase):
    def test_no_leftovers_beat_leftovers(self):
        files = [F(t) for t in TITLES[:4]]
        d = decide(files, [R(TITLES[:3]), R(TITLES[:4])])
        self.assertEqual(len(d.match.release.titles), 4)

    def test_different_track_lists_are_not_decided(self):
        files = [F(t) for t in TITLES[:4]]
        d = decide(files, [R(TITLES[:3]), R(TITLES[:2] + TITLES[3:4])])
        self.assertIsNone(d.match)
        self.assertTrue(d.reason)

    def test_digital_before_year_before_first(self):
        files = [F(t) for t in TITLES[:2]]
        a, b, c = R(TITLES[:2], year="2001"), R(TITLES[:2], year="2005"), R(TITLES[:2], year="2014", digital=True)
        self.assertIs(decide(files, [a, b, c], "2001").match.release, c)
        self.assertIs(decide(files, [b, a], "2001").match.release, a)
        self.assertIs(decide(files, [b, a]).match.release, b)

    def test_no_candidates(self):
        d = decide([F("x")], [])
        self.assertIsNone(d.match)
        self.assertTrue(d.reason)


class CandidateTests(unittest.TestCase):
    @staticmethod
    def _m(tracks, fmt="CD"):
        return SimpleNamespace(row={"_url": f"{tracks}-{fmt}", "Tracks": str(tracks), "Format": fmt})

    def test_order_and_limit(self):
        got = albumauto.candidate_rows(
            [self._m(11), self._m(12), self._m(12, "Digital Media"), self._m(1), self._m(13)], 12)
        self.assertEqual([r["_url"] for r in got], ["12-Digital Media", "12-CD", "11-CD"])
        many = albumauto.candidate_rows([self._m(12) for _ in range(20)], 12)
        self.assertEqual(len(many), albumauto.MAX_CANDIDATES)

    def test_id_from_tags_is_an_extra_candidate(self):
        got = albumauto.candidate_rows([self._m(12)], 12, "abc-def")
        self.assertTrue(got[0]["_url"].startswith("abc-def?"))
        self.assertEqual(len(albumauto.candidate_rows([self._m(12)], 12, "12-cd")), 1)

    def test_digital_first_is_stable(self):
        rows = [{"_url": "a", "Tracks": "9", "Format": "CD"}, {"_url": "b", "Tracks": "9", "Format": "Digital Media"},
                {"_url": "c", "Tracks": "8", "Format": "Digital Media"}, {"_url": "d", "Tracks": "9", "Format": "CD"}]
        self.assertEqual([r["_url"] for r in albumauto.digital_first(rows, 9)], ["b", "a", "c", "d"])

    def test_rows_without_format_stay(self):
        rows = [{"_url": "a"}, {"_url": "b"}]
        self.assertEqual(albumauto.digital_first(rows, 2), rows)


def _track(path, title="", album="A", disc="", track=""):
    t = Track(path)
    for k, v in (("TITLE", title), ("ALBUM", album), ("DISCNUMBER", disc), ("TRACK", track)):
        if v:
            t.set(k, v)
    return t


def _album(titles):
    return Album(fields={"TITLE": list(titles), "ALBUM": ["A"], "MOOD": ["x"]},
                 per_track={"TITLE"}, tracks=len(titles), lengths=[])


class PlanAndAlignTests(unittest.TestCase):
    def test_prealign(self):
        a, b, c = _track("a.mp3", "One"), _track("b.mp3", "Two"), _track("c.mp3", "Bonus Song Here")
        self.assertEqual(albumauto.prealign([c, b, a], _album(["One", "Two"])), [a, b, c])

    def test_prealign_keeps_the_order_without_hints(self):
        a, b = _track("a.mp3", "Xyz"), _track("b.mp3", "Qrs")
        self.assertEqual(albumauto.prealign([a, b], _album(["One", "Two"])), [a, b])

    def test_prealign_empty_slot_for_a_missing_song(self):
        b = _track("b.mp3", "Two")
        self.assertEqual(albumauto.prealign([b], _album(["One", "Two"])), [None, b])

    def test_plan_respects_disabled_fields(self):
        a, b = _track("a.mp3", "One"), _track("b.mp3", "Two")
        album = _album(["One", "Two"])
        files = albumauto.file_infos([b, a])
        m = Match(Release(album, ["One", "Two"], [None, None]), files, {0: 1, 1: 0}, [], 1.0)
        got = albumauto.plan_for(m, {"MOOD"})
        self.assertEqual(got, [(a, {"TITLE": "One", "ALBUM": "A"}), (b, {"TITLE": "Two", "ALBUM": "A"})])


class GroupTests(unittest.TestCase):
    @staticmethod
    def _t(folder, album):
        return _track(os.path.join("Temp", folder, "x.mp3"), album=album)

    def test_album_folders_side_by_side_stay_apart(self):
        a, b = self._t("A - (2001) - Greatest Hits", "Greatest Hits"), self._t("B - (2003) - Greatest Hits", "Greatest Hits")
        self.assertEqual(albumauto.group_albums([a, b]), [[a], [b]])

    def test_disc_folders_belong_together(self):
        a, b = self._t(os.path.join("Album", "CD1"), "X"), self._t(os.path.join("Album", "cd 2"), "X")
        self.assertEqual(albumauto.group_albums([a, b]), [[a, b]])

    def test_disc_folders_with_other_album_name_stay_apart(self):
        a, b = self._t(os.path.join("Album", "CD1"), "X"), self._t(os.path.join("Album", "CD2"), "Y")
        self.assertEqual(albumauto.group_albums([a, b]), [[a], [b]])

    def test_other_subfolders_stay_apart(self):
        a, b = self._t(os.path.join("Album", "Bonus"), "X"), self._t(os.path.join("Album", "Main"), "X")
        self.assertEqual(albumauto.group_albums([a, b]), [[a], [b]])


class OrderTests(unittest.TestCase):
    def test_number(self):
        self.assertEqual([number(v) for v in ("1/2", "01", " 3", "", "x")], [1, 1, 3, None, None])

    def test_double_album_in_one_folder(self):
        tracks = [_track(n, disc=d, track=t) for n, d, t in
                  (("01 - a.mp3", "1/2", "1"), ("01 - b.mp3", "2/2", "1"), ("02 - a.mp3", "1/2", "2"), ("02 - b.mp3", "2/2", "2"))]
        self.assertEqual([t.filename for t in sort_by_folder(tracks)],
                         ["01 - a.mp3", "02 - a.mp3", "01 - b.mp3", "02 - b.mp3"])

    def test_mixed_disc_values(self):
        a, b, c, d = (_track("a.mp3", disc="02", track="1"), _track("b.mp3", track="2"),
                      _track("c.mp3", disc="1/2", track="1"), _track("d.mp3", disc="1"))
        self.assertEqual(sort_by_folder([a, b, c, d]), [c, b, d, a])

    def test_no_tags_natural_file_names(self):
        tracks = [_track(n) for n in ("10.mp3", "9.mp3")]
        self.assertEqual([t.filename for t in sort_by_folder(tracks)], ["9.mp3", "10.mp3"])

    def test_folders_keep_their_order(self):
        a = _track(os.path.join("z", "1.mp3"), track="2")
        b = _track(os.path.join("z", "2.mp3"), track="1")
        c = _track(os.path.join("a", "1.mp3"), track="1")
        self.assertEqual(sort_by_folder([a, b, c]), [b, a, c])

    def test_playlist_keeps_its_order(self):
        a, b = _track("a.mp3", track="2"), _track("b.mp3", track="1")
        self.assertEqual(loaded_order([a, b], ["x.m3u8"]), [a, b])
        self.assertEqual(loaded_order([a, b], ["folder"]), [b, a])


if __name__ == "__main__":
    unittest.main()


class _FakeTrack:
    filename = "x.mp3"
    modified = True

    def __init__(self, name):
        self.path = name
        self._saved = SimpleNamespace(fields={}, covers=[])
        self.data = SimpleNamespace(fields={}, covers=[])

    def save(self, *args):
        self._saved = SimpleNamespace(fields=dict(self.data.fields), covers=list(self.data.covers))

    def revert(self):
        self.data = SimpleNamespace(fields=dict(self._saved.fields), covers=list(self._saved.covers))


class UndoGroupTests(unittest.TestCase):
    def _win(self):
        from unittest import mock
        from psytags.undo import UndoStack
        return mock.MagicMock(_group_rec=None, _group_errors=[], undo=UndoStack())

    def _fill(self, t, name, value):
        t.data.fields[name] = [value]

    def test_several_writes_are_one_step(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from psytags.ui.mainwindow import MainWindow
        win = self._win()
        t = _FakeTrack("a")
        with MainWindow._undo_group(win, "Album"):
            MainWindow._write(win, "tags", [t], lambda x: self._fill(x, "ALBUM", "A"))
            MainWindow._write(win, "genres", [t], lambda x: self._fill(x, "GENRE", "Rock"))
        self.assertEqual(len(win.undo.undo_ops), 1)
        self.assertEqual(win.undo.undo_ops[0].changes[0].after_fields, {"ALBUM": ["A"], "GENRE": ["Rock"]})

    def test_without_group_each_write_is_a_step(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from psytags.ui.mainwindow import MainWindow
        win = self._win()
        t = _FakeTrack("a")
        MainWindow._write(win, "tags", [t], lambda x: self._fill(x, "ALBUM", "A"))
        MainWindow._write(win, "genres", [t], lambda x: self._fill(x, "GENRE", "Rock"))
        self.assertEqual(len(win.undo.undo_ops), 2)


class BaseTitleTests(unittest.TestCase):
    def test_edition_notes_go(self):
        from psytags.websources.albummatch import base_title
        for album, want in (("Aftermath (Bonus Tracks Edition)", "Aftermath"),
                            ("Hidden Evolution (Special Edition)", "Hidden Evolution"),
                            ("Foo [Deluxe]", "Foo"), ("Foo - Remastered 2011", "Foo"),
                            ("Foo: Deluxe Edition", "Foo"), ("Foo Deluxe Edition", "Foo"),
                            ("Foo (Deluxe) [2CD]", "Foo"), ("Foo - EP", "Foo"),
                            ("Foo (Live at Wacken) [Deluxe]", "Foo (Live at Wacken)"),
                            ("Mental Funeral (Remaster 2003)", "Mental Funeral"),
                            ("Path Of The Immortal [Japanese Edition]", "Path Of The Immortal")):
            self.assertEqual(base_title(album), want, album)

    def test_recording_notes_go_only_on_request(self):
        from psytags.websources.albummatch import base_title, recording_note
        self.assertEqual(base_title("BLACK LITURGY (Live)", True), "BLACK LITURGY")
        self.assertEqual(base_title("Foo - Live at Wacken", True), "Foo")
        self.assertEqual(base_title("Foo (Live) [Deluxe]", True), "Foo")
        self.assertEqual(base_title("Foo (Vol. 2)", True), "Foo (Vol. 2)")
        self.assertEqual(recording_note("BLACK LITURGY (Live)"), "live")
        self.assertEqual(recording_note("Foo (Bonus Tracks Edition)"), "")

    def test_other_titles_stay(self):
        from psytags.websources.albummatch import base_title
        for album in ("Hey (Live)", "(What's the Story) Morning Glory?", "(Untitled)", "Unplugged",
                      "Foo - The Best Of", "Foo (Vol. 2)", "Foo (Remixes)", "Plain Title"):
            self.assertEqual(base_title(album), album)


class SecondSearchTests(unittest.TestCase):
    """find_album searches once more without the edition note, and only when it has to."""

    class _Src:
        search_fields = []

    def _run(self, album, first_rows, second_rows, album_type="Album"):
        from unittest import mock
        from psytags.websources import runner
        t = _track("a.mp3", "One", album=album)
        seen = []

        def prefill(_src, tracks):
            return [tracks[0].field("ALBUM")[0]]

        def run_index(_src, values):
            seen.append(values[0])
            return first_rows if len(seen) == 1 else second_rows
        rel = Album(fields={"TITLE": ["One"], "YEAR": ["2001"], "MUSICBRAINZ_ALBUMTYPE": [album_type]},
                    per_track={"TITLE"}, tracks=1, lengths=[])
        with mock.patch.object(runner, "prefill", prefill), mock.patch.object(runner, "run_index", run_index), \
                mock.patch.object(runner, "album_target", lambda *_a: ("u", "p")), \
                mock.patch.object(runner, "run_album", lambda *_a: rel), \
                mock.patch.object(albumauto, "_INTERVAL", 0):
            return albumauto.find_album(self._Src(), [t]), seen

    @staticmethod
    def _row(title):
        return {"_url": "x", "Album": title, "Tracks": "1", "Artist": "", "Type": "Album"}

    def test_retries_without_the_note(self):
        res, seen = self._run("Foo (Bonus Tracks Edition)", [], [self._row("Foo")])
        self.assertIsNotNone(res.match)
        self.assertEqual(seen, ["Foo (Bonus Tracks Edition)", "Foo"])

    def test_found_at_once_needs_no_retry(self):
        res, seen = self._run("Foo (Bonus Tracks Edition)", [self._row("Foo (Bonus Tracks Edition)")], [])
        self.assertIsNotNone(res.match)
        self.assertEqual(len(seen), 1)

    def test_live_album_found_without_the_note_must_be_live(self):
        res, seen = self._run("Foo (Live)", [], [self._row("Foo")], "Album, Live")
        self.assertIsNotNone(res.match)
        self.assertEqual(seen, ["Foo (Live)", "Foo"])

    def test_live_album_never_lands_on_the_studio_album(self):
        res, _seen = self._run("Foo (Live)", [], [self._row("Foo")], "Album")
        self.assertIsNone(res.match)

    def test_no_note_no_retry(self):
        res, seen = self._run("Foo", [], [self._row("Foo")])
        self.assertIsNone(res.match)
        self.assertEqual(seen, ["Foo"])


class ReviewCaseTests(unittest.TestCase):
    def test_bracket_only_differences_are_not_crossed(self):
        files = [F("Song (Mono)", 180.6), F("Song (Stereo)", 180.9)]
        m = match_release(files, R(["Song (Mono)", "Song (Stereo)"], [181.0, 180.0]))
        self.assertEqual({m.files[f].key: t for f, t in m.mapping.items()}, {"Song (Mono)": 0, "Song (Stereo)": 1})

    def test_without_lengths_bracket_titles_still_match(self):
        files = [F("Song (Club Mix)"), F("Song (Radio Edit)")]
        m = match_release(list(reversed(files)), R(["Song (Club Mix)", "Song (Radio Edit)"], [None, None]))
        self.assertEqual({m.files[f].key: t for f, t in m.mapping.items()},
                         {"Song (Club Mix)": 0, "Song (Radio Edit)": 1})

    def test_exact_title_beats_bracket_variant_for_the_leftover(self):
        files = [F("One"), F("Two"), F("Three"), F("Song", 240.0), F("Song (Live)", 233.0)]
        m = match_release(files, R(["One", "Two", "Three", "Song"], [200.0, 200.0, 200.0, 233.5]))
        self.assertIsInstance(m, Match)
        self.assertEqual(m.leftover_keys, ["Song (Live)"])

    def test_same_title_without_usable_lengths_is_not_guessed(self):
        files = [F("Intro", 100.0, "a.mp3"), F("Intro", 100.5, "b.mp3")]
        self.assertIsInstance(match_release(files, R(["Intro", "Intro"], [100.0, 100.0])), Match)   # file order
        self.assertIsInstance(match_release(files, R(["Intro", "Intro"], [None, None])), str)

    def test_numbers_in_titles_must_agree(self):
        self.assertIsInstance(match_release([F("Symphony No. 4")], R(["Symphony No. 5"])), str)
        self.assertIsInstance(match_release([F("Part 1")], R(["Part 2"])), str)
        self.assertIsInstance(match_release([F("Gorls Own Love 2")], R(["Girls Own Love 2"])), Match)

    def test_other_order_is_another_track_list(self):
        files = [F(t) for t in TITLES[:3]]
        d = decide(files, [R([TITLES[1], TITLES[2], TITLES[0]]), R([TITLES[2], TITLES[0], TITLES[1]], digital=True)])
        self.assertIsNone(d.match)
        self.assertTrue(d.reason)


class ReleaseKindTests(unittest.TestCase):
    @staticmethod
    def _album(title="Foo", kind="Album", artist="Band"):
        return Album(fields={"ALBUM": [title], "MUSICBRAINZ_ALBUMTYPE": [kind], "ALBUMARTIST": [artist]},
                     per_track=set(), tracks=1, lengths=[])

    def test_word_not_substring(self):
        self.assertFalse(albumauto._fits_album(self._album("Alive"), "Alive (Live)", "Band"))
        self.assertFalse(albumauto._fits_album(self._album("Demon Days"), "Demon Days (Demo)", "Band"))
        self.assertTrue(albumauto._fits_album(self._album("Alive", "Album, Live"), "Alive (Live)", "Band"))
        self.assertTrue(albumauto._fits_album(self._album("Foo", "Album, Remix"), "Foo (Remixes)", "Band"))

    def test_live_release_for_a_plain_title_needs_tight_lengths(self):
        live = self._album("As the Stages Burn! (Live at Wacken 2016)", "Album, Live")
        self.assertTrue(albumauto._fits_album(live, "As the Stages Burn", "Band"))
        self.assertTrue(albumauto._needs_tight_lengths(live, "As the Stages Burn"))
        self.assertFalse(albumauto._needs_tight_lengths(self._album("Live in Tokyo", "Album, Live"), "Live in Tokyo"))
        self.assertFalse(albumauto._needs_tight_lengths(self._album("Foo"), "Foo"))

    def test_other_artist_is_rejected(self):
        self.assertFalse(albumauto._fits_album(self._album(artist="Karaoke Kings"), "Foo", "Band"))
        self.assertTrue(albumauto._fits_album(self._album(artist="The Band"), "Foo", "Band"))
        self.assertTrue(albumauto._fits_album(self._album(artist="Beyoncé"), "Foo", "Beyonce"))
        self.assertTrue(albumauto._fits_album(self._album(artist=""), "Foo", "Band"))
        self.assertTrue(albumauto._fits_album(self._album(artist="Band"), "Foo", ""))


class LeftoverSelectionTests(unittest.TestCase):
    def test_only_files_of_the_same_album_are_leftovers(self):
        from psytags.ui.dialogs.tagsources import AdjustDialog
        a1 = _track(os.path.join("a", "1.mp3"), "One", album="A")
        extra = _track(os.path.join("a", "2.mp3"), "Bonus Thing Here", album="A")
        other = _track(os.path.join("b", "1.mp3"), "Zzz", album="B")
        ns = SimpleNamespace(album=_album(["One"]), files=[a1, extra, other])
        self.assertEqual(AdjustDialog.leftovers(ns), [extra])


class StayingProgressTests(unittest.TestCase):
    def test_cancel_keeps_the_dialog_open(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from psytags.ui.mainwindow import _StayingProgress
        app = QApplication.instance() or QApplication([])
        d = _StayingProgress("x", 3, None)
        d.show()
        d.canceled.emit()
        app.processEvents()
        self.assertTrue(d.isVisible())
        self.assertTrue(d.stop.is_set())
        d.finish()
        self.assertFalse(d.isVisible())


class FollowUpTests(unittest.TestCase):
    @staticmethod
    def _app():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        return QApplication.instance() or QApplication([])

    def test_finishing_the_progress_gives_the_window_back(self):
        app = self._app()
        from PySide6.QtWidgets import QWidget
        from psytags.ui.mainwindow import _StayingProgress
        win = QWidget()
        win.show()
        win.activateWindow()
        app.processEvents()
        d = _StayingProgress("x", 3, win)
        d.show()
        app.processEvents()
        d.finish()
        app.processEvents()
        self.assertTrue(win.isActiveWindow())

    def _finish(self, complete):
        self._app()
        from unittest import mock
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win._lastfm_enabled.return_value = False
        t = _track("a.mp3", "One")
        MainWindow._finish_source_import(win, "MB", "p", [(t, {"TITLE": "One"})], None, [], False, complete)
        return win, t

    def test_a_complete_album_gets_numbered(self):
        win, t = self._finish(True)
        win._renumber.assert_called_once_with([t])

    def test_a_partial_import_is_not_numbered(self):
        win, _t = self._finish(False)
        win._renumber.assert_not_called()

    def _auto_all(self, analysis_ok):
        self._app()
        from unittest import mock
        from psytags.ui import mainwindow as mw
        win = mock.MagicMock(_auto_done={}, _mood_done={})
        t = _track("a.mp3", "One")
        win.model.rows = [t]
        win._load_mb_source.return_value = ("p", object())
        win.analyze_moods.return_value = analysis_ok
        with mock.patch.object(mw, "_StayingProgress") as dlg:
            dlg.return_value.stop.is_set.return_value = False
            mw.MainWindow.auto_all_albums(win)
        return win, t

    def test_all_albums_analyzes_first(self):
        win, t = self._auto_all(True)
        win.analyze_moods.assert_called_once_with([t])
        win._auto_one.assert_called_once()

    def test_canceled_analysis_stops_the_run(self):
        win, _t = self._auto_all(False)
        win._auto_one.assert_not_called()

    def test_songs_analyzed_before_are_not_repeated(self):
        self._app()
        from unittest import mock
        from psytags.ui import mainwindow as mw
        t = _track("a.mp3", "One")
        win = mock.MagicMock(_auto_done={}, _mood_done={id(t): t})
        win.model.rows = [t]
        win._load_mb_source.return_value = ("p", object())
        win.analyze_moods.return_value = True
        with mock.patch.object(mw, "_StayingProgress") as dlg:
            dlg.return_value.stop.is_set.return_value = False
            mw.MainWindow.auto_all_albums(win)
        win.analyze_moods.assert_called_once_with([])


class SummaryOutcomeTests(unittest.TestCase):
    def test_marks(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from psytags.ui.dialogs.tagsources import outcome_mark
        self.assertEqual(outcome_mark(None), ("–", None))
        self.assertEqual(outcome_mark("")[0], "☒")
        self.assertEqual(outcome_mark("Kein Treffer")[0], "☐")

    def test_import_reports_cover_and_genres(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win._lastfm_enabled.return_value = True
        win.fetch_archive_cover.return_value = "kein Treffer"
        win.finish_lastfm.return_value = ""
        result = MainWindow._finish_source_import(win, "MB", "p", [(_track("a.mp3", "One"), {})], None, [], False,
                                                  archive=("r", "g"))
        self.assertEqual(result, ("kein Treffer", ""))

    def test_lastfm_off_is_reported_as_not_run(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win._lastfm_enabled.return_value = False
        self.assertEqual(MainWindow._finish_source_import(win, "MB", "p", [], None, [], False), (None, None))


class CoverRetryTests(unittest.TestCase):
    @staticmethod
    def _entry(ok, cover):
        return albumauto.BatchEntry("A", [], ok, "A (2001) · kein Treffer" if cover else "A (2001)", [], cover, None)

    def _chosen(self, entry):
        from PySide6.QtCore import Qt
        from unittest import mock
        from psytags.ui.dialogs.tagsources import BatchSummaryDialog
        item = mock.MagicMock()
        item.data.return_value = entry
        ns = mock.MagicMock(chosen=None)
        ns.table.currentItem.return_value = item
        BatchSummaryDialog._open(ns)
        item.data.assert_called_with(0, Qt.ItemDataRole.UserRole)
        return ns.chosen

    def test_which_rows_can_be_opened(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        failed, opened, done, not_run = (self._entry(True, "kein Treffer"), self._entry(False, None),
                                         self._entry(True, ""), self._entry(True, None))
        self.assertIs(self._chosen(failed), failed)
        self.assertIs(self._chosen(opened), opened)
        self.assertIsNone(self._chosen(done))
        self.assertIsNone(self._chosen(not_run))

    def _retry(self, result):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win.fetch_archive_cover.return_value = result
        e = self._entry(True, "kein Treffer")
        MainWindow._retry_cover(win, e)
        win.fetch_archive_cover.assert_called_once_with(e.tracks)
        win.fetch_cover_from_source.assert_not_called()
        return e

    def test_a_new_cover_ticks_the_box(self):
        e = self._retry("")
        self.assertEqual((e.cover, e.detail), ("", "A (2001)"))

    def test_a_failed_retry_shows_the_new_reason(self):
        e = self._retry("zu klein")
        self.assertEqual((e.cover, e.detail), ("zu klein", "A (2001) · zu klein"))

    def test_summary_returns_after_the_cover_step(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui import mainwindow as mw
        from psytags.ui.dialogs import tagsources as ts
        e = self._entry(True, "kein Treffer")
        first, second = mock.MagicMock(chosen=e, action="cover"), mock.MagicMock(chosen=None, action="")
        first.exec.return_value, second.exec.return_value = 1, 0
        win = mock.MagicMock(_last_batch=[e])
        with mock.patch.object(ts, "BatchSummaryDialog", side_effect=[first, second]):
            mw.MainWindow.show_batch_summary(win)
        win._retry_cover.assert_called_once_with(e)
        win.run_source.assert_not_called()


class GenreRetryTests(unittest.TestCase):
    @staticmethod
    def _entry(ok=True, cover="", genres="HTTP 503"):
        return albumauto.BatchEntry("A", [], ok, "A (2001) · HTTP 503", [], cover, genres)

    def test_which_step_a_click_means(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from psytags.ui.dialogs.tagsources import summary_action as action
        both = self._entry(cover="kein Treffer")
        self.assertEqual(action(both, 2), "cover")
        self.assertEqual(action(both, 3), "genres")
        self.assertEqual(action(both, 0), "cover")
        self.assertEqual(action(self._entry(), 0), "genres")
        self.assertEqual(action(self._entry(), 2), "")          # this box is fine
        self.assertEqual(action(self._entry(ok=False, genres=None), 3), "manual")
        self.assertEqual(action(self._entry(genres=""), 4), "")

    def _retry(self, result):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui.mainwindow import MainWindow
        win = mock.MagicMock()
        win.finish_lastfm.return_value = result
        e = self._entry()
        MainWindow._retry_genres(win, e)
        return e

    def test_success_ticks_the_box(self):
        e = self._retry("")
        self.assertEqual((e.genres, e.detail), ("", "A (2001)"))

    def test_failure_shows_the_new_reason(self):
        e = self._retry("HTTP 502")
        self.assertEqual((e.genres, e.detail), ("HTTP 502", "A (2001) · HTTP 502"))


class LastfmRetryTests(unittest.TestCase):
    def _run(self, answers):
        from unittest import mock
        from psytags.websources import http, lastfm
        calls = []

        def fetch(_url):
            calls.append(1)
            a = answers[min(len(calls) - 1, len(answers) - 1)]
            if isinstance(a, Exception):
                raise a
            return a
        with mock.patch.object(http, "fetch", fetch), mock.patch.object(lastfm.time, "sleep"):
            try:
                return lastfm._top_tags("album.gettoptags", "SECRET", artist="A"), len(calls)
            except lastfm.LastfmError as e:
                return str(e), len(calls)

    def test_temporary_error_is_retried(self):
        from psytags.websources.http import FetchError
        body = '{"toptags": {"tag": [{"name": "rock", "count": 100}]}}'
        got, calls = self._run([FetchError("HTTP 503 Service Unavailable: https://x?api_key=SECRET"), body])
        self.assertEqual(got, [("rock", 100)])
        self.assertEqual(calls, 2)

    def test_gives_up_with_a_short_message(self):
        from psytags.websources.http import FetchError
        got, calls = self._run([FetchError("HTTP 503 Service Unavailable: https://x?api_key=SECRET")])
        self.assertEqual(calls, 3)
        self.assertEqual(got, "HTTP 503 Service Unavailable")

    def test_other_errors_are_not_retried(self):
        from psytags.websources.http import FetchError
        _got, calls = self._run([FetchError("HTTP 403 Forbidden: https://x")])
        self.assertEqual(calls, 1)


class RealAlbumCaseTests(unittest.TestCase):
    def test_two_versions_of_a_title_are_not_crossed(self):
        # Annihilator, Bag of Tricks: the closest length alone would cross them
        files = [file_info("remaster", "Alison Hell", "01.mp3", "", 306.8),
                 file_info("86", "Alison Hell", "15.mp3", "", 313.3)]
        m = match_release(files, R(["Alison Hell", "Alison Hell"], [300.7, 309.2]))
        self.assertIsInstance(m, Match)
        self.assertEqual({m.files[f].key: t for f, t in m.mapping.items()}, {"remaster": 0, "86": 1})

    def test_album_name_in_front_of_the_title(self):
        # Angra, OMNI: "OMNI – Silence Inside" at MusicBrainz, "Silence Inside" in the file
        m = match_release([F("Silence Inside", 511.0)], R(["ØMNI – Silence Inside"], [511.0]))
        self.assertIsInstance(m, Match)
        self.assertLess(m.worst, 0.99)

    def test_a_single_common_word_is_not_enough(self):
        self.assertIsInstance(match_release([F("Love", 200.0)], R(["Love Song"], [200.0])), str)

    def test_contained_title_still_needs_a_fitting_length(self):
        self.assertIsInstance(match_release([F("Silence Inside", 560.0)], R(["ØMNI – Silence Inside"], [511.0])), str)


class LastFreeSongTests(unittest.TestCase):
    @staticmethod
    def _album(last_length=292.1, others=3):
        names = [f"Song Title {w}" for w in ("Alpha", "Bravo", "Charlie", "Delta")[:others]]
        return [F(t) for t in names] + [F("Brain Damage", last_length)], R(names + ["Brain Dance"], [200.0] * others + [292.2])

    def test_one_different_name_with_the_same_length_passes(self):
        files, rel = self._album()
        m = match_release(files, rel)
        self.assertIsInstance(m, Match)
        self.assertEqual({m.files[f].key: t for f, t in m.mapping.items()}["Brain Damage"], 3)

    def test_length_must_be_close(self):
        files, rel = self._album(296.0)
        self.assertIsInstance(match_release(files, rel), str)

    def test_needs_enough_other_songs(self):
        files, rel = self._album(others=2)
        self.assertIsInstance(match_release(files, rel), str)

    def test_two_different_names_stop(self):
        files, rel = self._album()
        files[0] = F("Totally Other Name", 200.0)
        self.assertIsInstance(match_release(files, rel), str)

    def test_not_with_a_leftover_file(self):
        files, rel = self._album()
        files.append(F("Bonus Track Here", 200.0))
        self.assertIsInstance(match_release(files, rel), str)

    def test_unknown_length_is_not_enough(self):
        files, rel = self._album()
        rel.lengths[3] = None
        self.assertIsInstance(match_release(files, rel), str)


class FitPathTests(unittest.TestCase):
    FOLDER = "C:\\" + "x" * 150

    def _path(self, name):
        return self.FOLDER + "\\" + name

    def _fit(self, name, limit=200):
        import ntpath
        from unittest import mock
        from psytags import convert
        with mock.patch.object(convert.os, "path", ntpath):
            return convert.fit_path(self._path(name), limit)

    def test_short_paths_stay(self):
        self.assertEqual(self._fit("01 - Song.mp3"), self._path("01 - Song.mp3"))

    def test_guest_artists_go_first(self):
        got = self._fit("06-0101 - Anneke with Agua feat. Arjen Anthony Lucassen - Valley of the Queens.mp3", 210)
        self.assertEqual(got, self._path("06-0101 - Anneke with Agua - Valley of the Queens.mp3"))

    def test_then_the_end_of_the_name(self):
        got = self._fit("01 - " + "Very Long Title " * 8 + ".mp3")
        self.assertLessEqual(len(got), 200)
        self.assertTrue(got.endswith(".mp3"))
        self.assertTrue(got.startswith(self._path("01 - Very Long")))


class OldFolderTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.temp = os.path.join(d.name, "a", "b", "Temp")

    def _file(self, *parts):
        p = os.path.join(self.temp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").close()
        return p

    def _new(self, name="New Album"):
        return os.path.join(self.temp, name, "01 x.mp3")

    def _folders(self, moves):
        from psytags.convert import emptied_album_folders
        return [os.path.relpath(f, self.temp) for f in emptied_album_folders(moves)]

    def test_folder_with_only_leftovers_goes(self):
        self._file("Old", "Folder.jpg")
        self._file("Old", "album.cue")
        self._file("Old", "Scans", "back.png")
        self.assertEqual(self._folders([(os.path.join(self.temp, "Old", "01.mp3"), self._new())]), ["Old"])

    def test_remaining_audio_keeps_the_folder(self):
        self._file("Old", "12 Bonus.mp3")
        self.assertEqual(self._folders([(os.path.join(self.temp, "Old", "01.mp3"), self._new())]), [])

    def test_audio_in_a_subfolder_keeps_the_folder(self):
        self._file("Old", "Bonus", "x.flac")
        self.assertEqual(self._folders([(os.path.join(self.temp, "Old", "01.mp3"), self._new())]), [])

    def test_disc_folders_remove_the_whole_album(self):
        self._file("Old", "CD1", "cover.jpg")
        self._file("Old", "CD2", "cover.jpg")
        moves = [(os.path.join(self.temp, "Old", "CD1", "01.mp3"), self._new()),
                 (os.path.join(self.temp, "Old", "CD2", "01.mp3"), self._new())]
        self.assertEqual(self._folders(moves), ["Old"])

    def test_target_inside_the_old_folder_keeps_it(self):
        self._file("Old", "x.jpg")
        moves = [(os.path.join(self.temp, "Old", "01.mp3"), os.path.join(self.temp, "Old", "Sub", "01.mp3"))]
        self.assertEqual(self._folders(moves), [])

    def test_unchanged_files_do_not_count(self):
        p = os.path.join(self.temp, "Old", "01.mp3")
        self._file("Old", "x.jpg")
        self.assertEqual(self._folders([(p, p)]), [])

    def test_shallow_folders_are_never_removed(self):
        from psytags.convert import emptied_album_folders
        self.assertEqual(emptied_album_folders([(os.path.join(os.sep, "x.mp3"), os.path.join(os.sep, "n", "x.mp3"))]), [])


class ManualFromSummaryTests(unittest.TestCase):
    def _run(self, outcome):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from unittest import mock
        from PySide6.QtWidgets import QApplication
        QApplication.instance() or QApplication([])
        from psytags.ui import mainwindow as mw
        from psytags.ui.dialogs import tagsources as ts
        t = _track("a.mp3", "One")
        e = albumauto.BatchEntry("A", [t], False, "Titel passt nicht: X")
        dlg = mock.MagicMock(chosen=e, action="manual")
        dlg.exec.return_value = 1
        win = mock.MagicMock(_last_batch=[e], _auto_done={})
        win._mb_tag_source.return_value = "p"
        win.run_source.return_value = outcome
        with mock.patch.object(ts, "BatchSummaryDialog", return_value=dlg):
            mw.MainWindow.show_batch_summary(win)
        return e, win, t

    def test_saving_marks_the_album_done(self):
        e, win, t = self._run(("", "kein Treffer"))
        self.assertTrue(e.ok)
        self.assertEqual((e.cover, e.genres), ("", "kein Treffer"))
        self.assertEqual(e.detail, "Manuell getaggt · kein Treffer")
        self.assertIn(id(t), win._auto_done)

    def test_canceling_leaves_it_open(self):
        e, win, _t = self._run(None)
        self.assertFalse(e.ok)
        self.assertEqual(e.detail, "Titel passt nicht: X")
        self.assertEqual(win._auto_done, {})


class OpenAlbumCaseTests(unittest.TestCase):
    def test_edition_in_the_order_of_the_files_wins(self):
        # Will To Power: a digital edition starts with another song than the CDs and the files
        files = [F(t) for t in TITLES[:3]]
        cd, digital = R(TITLES[:3]), R([TITLES[1], TITLES[2], TITLES[0]], digital=True)
        self.assertIs(decide(files, [digital, cd]).match.release, cd)

    def test_tight_release_needs_every_length(self):
        files = [F(t, 200.0) for t in TITLES[:3]]
        tight = R(TITLES[:3], [200.5, 199.0, 201.0])
        tight.tight = True
        self.assertIsInstance(match_release(files, tight), Match)
        tight.lengths[1] = 210.0
        self.assertIsInstance(match_release(files, tight), str)
        tight.lengths[1] = None
        self.assertIsInstance(match_release(files, tight), str)

    def test_equal_titles_with_equal_lengths_keep_the_file_order(self):
        # Archetype, Dawning: "Hands of Time" twice, both 4:30
        infos = [file_info("02", "Hands of Time", "02.mp3", "", 270.1), file_info("13", "Hands of Time", "13.mp3", "", 270.0)]
        from psytags.websources.albummatch import align
        got = {infos[f].key: t for f, t, _s in align(infos, R(["Hands of Time", "Hands of Time"], [269.0, 270.0]))}
        self.assertEqual(got, {"02": 0, "13": 1})

    def test_label_without_a_date_has_no_empty_brackets(self):
        def match(fields):
            album = Album(fields=fields, per_track=set(), tracks=1, lengths=[])
            return Match(Release(album, ["x"], [None], (fields.get("YEAR") or [""])[0]), [], {}, [], 1.0)
        self.assertEqual(albumauto.release_label(match({"ALBUM": ["A"], "YEAR": ["2001"]})), "A (2001)")
        self.assertEqual(albumauto.release_label(match({"ALBUM": ["A"], "ORIGYEAR": ["1999-05-21"]})), "A (1999)")
        self.assertEqual(albumauto.release_label(match({"ALBUM": ["A"]})), "A")


class InPlaceRenameTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.temp = os.path.join(d.name, "a", "b", "Temp")

    def _file(self, *parts):
        p = os.path.join(self.temp, *parts)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").close()
        return p

    def _left(self, moves):
        from psytags.convert import leftovers_in_renamed_albums
        return sorted(os.path.relpath(f, self.temp) for f in leftovers_in_renamed_albums(moves))

    def test_junk_beside_the_renamed_files_goes(self):
        new = self._file("Album", "01-0101 - X.mp3")
        self._file("Album", "Folder.jpg")
        self._file("Album", "album.cue")
        self._file("Album", "Scans", "back.png")
        old = os.path.join(self.temp, "Album", "01 - X.mp3")
        self.assertEqual(self._left([(old, new)]), [os.path.join("Album", "Folder.jpg"), os.path.join("Album", "Scans"),
                                                    os.path.join("Album", "album.cue")])

    def test_folder_with_other_audio_keeps_its_junk(self):
        new = self._file("Album", "01-0101 - X.mp3")
        self._file("Album", "14 Bonus.mp3")
        self._file("Album", "Folder.jpg")
        self.assertEqual(self._left([(os.path.join(self.temp, "Album", "01.mp3"), new)]), [])

    def test_album_moved_elsewhere_is_not_touched_here(self):
        self._file("Old", "Folder.jpg")
        new = self._file("New", "01.mp3")
        self.assertEqual(self._left([(os.path.join(self.temp, "Old", "01.mp3"), new)]), [])

    def test_renaming_again_cleans_up_too(self):
        p = self._file("Album", "01-0101 - X.mp3")
        self._file("Album", "Folder.jpg")
        self.assertEqual(self._left([(p, p)]), [os.path.join("Album", "Folder.jpg")])

    def test_disc_folders_stay_with_their_audio(self):
        a = self._file("Album", "CD1", "01.mp3")
        self._file("Album", "CD1", "cover.jpg")
        self._file("Album", "Folder.jpg")
        got = self._left([(a, a)])
        self.assertEqual(got, [os.path.join("Album", "CD1", "cover.jpg"), os.path.join("Album", "Folder.jpg")])

    @unittest.skipUnless(os.name == "nt", "case-insensitive file system")
    def test_folder_spelling_is_corrected(self):
        from psytags.convert import fix_folder_case
        self._file("Rise Of The Tyrant", "01.mp3")
        new = os.path.join(self.temp, "Rise of the Tyrant", "01.mp3")
        fix_folder_case([("x", new)])
        self.assertEqual(os.listdir(self.temp), ["Rise of the Tyrant"])
        self.assertTrue(os.path.exists(new))


class HiddenTrackTests(unittest.TestCase):
    NAMES = ["Final Day", "Hands of Time", "Dawning", "Years Ago"]

    def _case(self, last=139.0, other=200.0, title="Years Ago"):
        files = [F(n, other) for n in self.NAMES[:3]] + [F(title, last)]
        return files, R(self.NAMES, [200.0, 200.5, 199.0, 783.0])

    def test_one_track_may_differ_in_length(self):
        files, rel = self._case()
        self.assertIsInstance(match_release(files, rel), Match)

    def test_title_must_be_identical(self):
        files, rel = self._case(title="Years Agoo")
        self.assertIsInstance(match_release(files, rel), str)

    def test_all_others_must_agree_closely(self):
        files, rel = self._case(other=204.0)
        self.assertIsInstance(match_release(files, rel), str)

    def test_only_one_track(self):
        files, rel = self._case()
        rel.lengths[0] = 500.0
        self.assertIsInstance(match_release(files, rel), str)

    def test_not_with_a_leftover_file(self):
        files, rel = self._case()
        files.append(F("Bonus Thing Here", 200.0))
        self.assertIsInstance(match_release(files, rel), str)

    def test_needs_enough_tracks(self):
        files, rel = self._case()
        short = R(self.NAMES[2:], [199.0, 783.0])
        self.assertIsInstance(match_release(files[2:], short), str)

    def test_not_together_with_a_different_title(self):
        files, rel = self._case()
        files[0] = F("Something Else Entirely", 200.0)
        self.assertIsInstance(match_release(files, rel), str)
