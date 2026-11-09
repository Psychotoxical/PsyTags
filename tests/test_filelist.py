import unittest

from psytags import config
from psytags.track import Track
from psytags.ui.filelist import FileListModel


def _track(album, disc, track):
    t = Track(f"{album}-{disc}-{track}.mp3")
    t.set("ALBUM", album)
    t.set("DISCNUMBER", f"{disc}/2")
    t.set("TRACK", str(track))
    return t


class SortTests(unittest.TestCase):
    def test_click_sorting_is_stable_like_mp3tag(self):
        tracks = [_track(a, d, n) for a in ("Beta", "Alpha") for d in (2, 1) for n in (3, 1, 2)]
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks(tracks)
        col = {c.name: i + 1 for i, c in enumerate(m.columns)}
        for name in ("Track", "Disc-Nummer", "Album"):        # one plain click each
            m.sort_by(col[name], add=False)
        got = [(t.get("ALBUM")[0], t.get("DISCNUMBER")[0][0], t.get("TRACK")[0]) for t in m.rows]
        want = [(a, d, n) for a in ("Alpha", "Beta") for d in "12" for n in "123"]
        self.assertEqual(got, want)


class SortAlbumTests(unittest.TestCase):
    def _model(self, tracks):
        m = FileListModel([config.Column(**c.__dict__) for c in config.DEFAULT_COLUMNS])
        m.set_tracks(tracks)
        return m

    def test_only_this_album_moves(self):
        x1, x2 = _track("Other", 1, 9), _track("Other", 1, 1)
        a1, a2, a3 = _track("A", 1, 1), _track("A", 1, 2), _track("A", 2, 1)
        m = self._model([x1, a3, a2, x2, a1])
        m.sort_album([a1, a2, a3])
        self.assertEqual(m.rows, [x1, a1, a2, x2, a3])

    def test_files_without_a_track_end_the_block(self):
        a1, a2, extra, x = _track("A", 1, 1), _track("A", 1, 2), _track("A", 1, 1), _track("Z", 1, 1)
        extra.path = extra.path.replace("A-1-1", "A-bonus")
        m = self._model([extra, a2, a1, x])
        m.sort_album([a1, a2], last=[extra])
        self.assertEqual(m.rows, [a1, a2, extra, x])


if __name__ == "__main__":
    unittest.main()
