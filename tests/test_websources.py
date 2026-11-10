import unittest


class CoverMatchTests(unittest.TestCase):
    def test_rank(self):
        from psytags.websources.coverfetch import confident, rank
        rows = [{"_url": "a", "Title": "Zeit (Remixes) - Single", "Artist": "Rammstein", "Tracks": "2", "Kind": "Album"},
                {"_url": "b", "Title": "Zeit", "Artist": "Rammstein", "Tracks": "11", "Kind": "Album"},
                {"_url": "c", "Title": "Zeit", "Artist": "Rammstein", "Tracks": "1", "Kind": "Song"},
                {"_url": "d", "Title": "Zeit (Deluxe Edition)", "Artist": "Rammstein", "Tracks": "14", "Kind": "Album"}]
        m = rank(rows, "Zeit", "Rammstein", 11)
        self.assertEqual(m[0].row["_url"], "b")
        self.assertNotIn("c", [x.row["_url"] for x in m])
        self.assertEqual(confident(m).row["_url"], "b")
        self.assertIsNone(confident(rank(rows, "Mutter", "Rammstein", 11)))

    def test_release_row(self):
        from psytags.websources.coverfetch import release_row
        rid = "18f7d742-6858-4f7d-866b-ea7e1ae00000"
        rows = [{"_url": "0a1b2c3d-0000-0000-0000-000000000000?inc=artists&fmt=json"},
                {"_url": rid.upper() + "?inc=artists+recordings&fmt=json"}]
        self.assertIs(release_row(rows, rid), rows[1])
        self.assertIsNone(release_row(rows, ""))
        self.assertIsNone(release_row(rows, "ffffffff-0000-0000-0000-000000000000"))

    def test_candidates(self):
        from psytags.websources.coverfetch import Match, candidates
        rows = [{"_url": u} for u in "abcdefg"]
        matches = [Match(rows[0], 90), Match(rows[1], 85), Match(rows[2], 79), Match(rows[3], 60)]
        # the release from the tags first, then every confident match, no duplicates, no weak ones
        self.assertEqual([r["_url"] for r in candidates(matches, rows[2])], ["c", "a", "b"])
        self.assertEqual([r["_url"] for r in candidates(matches, None)], ["a", "b", "c"])
        self.assertEqual(candidates([Match(rows[3], 60)], None), [])
        many = [Match(r, 100) for r in rows]
        self.assertEqual(len(candidates(many, None, limit=5)), 5)

    def test_first_cover_skips_releases_without_cover(self):
        # MusicBrainz: the best match (a CD without artwork in the Cover Art Archive) must not
        # end the search while other releases of the album have a cover
        from psytags.websources.coverfetch import first_cover
        covers = {"a": None, "b": (b"\xff\xd8jpeg", "image/jpeg"), "c": (b"\x89PNG", "image/png")}
        tried = []

        def fetch(src, row):
            tried.append(row["_url"])
            return covers[row["_url"]]
        rows = [{"_url": u} for u in "abc"]
        row, got = first_cover(None, rows, fetch=fetch)
        self.assertEqual(row["_url"], "b")
        self.assertEqual(got, covers["b"])
        self.assertEqual(tried, ["a", "b"])
        self.assertIsNone(first_cover(None, rows[:1], fetch=fetch))
        self.assertIsNone(first_cover(None, [], fetch=fetch))


class LastfmGenreTests(unittest.TestCase):
    def _run(self, answers):
        from unittest import mock
        from psytags.websources import lastfm
        calls = []

        def fake(method, key, **kw):
            calls.append(method)
            return answers.get(method, [])
        with mock.patch.object(lastfm, "_top_tags", fake):
            return lastfm.album_genres("Artist", "Album", "key"), calls

    def test_album_tags_need_one_request(self):
        got, calls = self._run({"album.gettoptags": [("doom metal", 100), ("sad", 100)]})
        self.assertEqual(got, ["Doom Metal"])
        self.assertEqual(calls, ["album.gettoptags"])

    def test_falls_back_to_artist_tags_and_never_asks_per_song(self):
        got, calls = self._run({"artist.gettoptags": [("power metal", 100)]})
        self.assertEqual(got, ["Power Metal"])
        self.assertEqual(calls, ["album.gettoptags", "artist.gettoptags"])
