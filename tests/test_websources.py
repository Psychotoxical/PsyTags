import unittest

from psytags.websources import runner
from psytags.websources.interpreter import Interpreter, ScriptError, compile_script


def run(text, script, variables=None):
    it = Interpreter(text, variables)
    it.run(compile_script(script.splitlines()))
    return it


class TextModeTests(unittest.TestCase):
    PAGE = "<html>\n<h1>Album: Zeit</h1>\n<li>1. Armee der Tristen (4:05)</li>\n" \
           "<li>2. Zeit (5:21)</li>\n</html>"

    def test_find_and_say(self):
        it = run(self.PAGE, '''
            findline "<h1>"
            findinline "Album: "
            outputto "ALBUM"
            sayuntil "</h1>"
            do
              findline "<li>" 1 1
              ifnot ""
                findinline ". "
                outputto "TITLE"
                sayuntil " ("
                say "|"
                movechar 2
                outputto "_LENGTH"
                sayuntil ")"
                say "|"
                outputto "tracks"
                say "|"
                moveline 1 1
              endif
            while "<li>" 10
        ''')
        a = runner.build_album(it)
        self.assertEqual(a.fields["ALBUM"], ["Zeit"])
        self.assertEqual(a.fields["TITLE"], ["Armee der Tristen", "Zeit"])
        self.assertEqual(a.lengths, ["4:05", "5:21"])
        self.assertEqual(a.tracks, 2)

    def test_quotes_escapes_and_comments(self):
        it = run('say "x"', r'''
            say "a\"b\\c\d"   # trailing comment
            Say "|"
        ''')
        self.assertEqual(it.out("Output"), 'a"b\\c\\d|')

    def test_replace_is_line_local(self):
        it = run("foo bar\nfoo baz", '''
            replace "foo" "X"
            sayrest
            moveline 1
            say "/"
            sayrest
        ''')
        self.assertEqual(it.out("Output"), "X bar/foo baz")

    def test_errors(self):
        with self.assertRaises(ScriptError):
            run("abc", 'findline "zzz"')
        with self.assertRaises(ScriptError):
            compile_script(['if "a"', 'say "b"'])
        with self.assertRaises(ScriptError):
            compile_script(['bogus "x"'])
        run("abc", 'findline "zzz" 1 1\nif ""\nsay "notfound"\nendif')

    def test_trim_and_set(self):
        it = run("  spaced  ", 'sayrest\noutputto "B"\ngotochar 1\ntrim "off"\nsayrest\nset "C" "v"\nset "B"')
        self.assertEqual(it.out("Output"), "spaced")
        self.assertEqual(it.out("B"), "")
        self.assertEqual(it.out("C"), "v")


class JsonModeTests(unittest.TestCase):
    DATA = '''{"title": "Artist - Album", "year": 1999, "explicit": true, "tags": ["a", "b"],
               "label": [{"name": "L1"}, {"name": "L2"}],
               "tracks": [{"title": "One", "pos": "1", "artists": [{"name": "X"}, {"name": "Y"}]},
                          {"title": "Two", "pos": "2", "artists": []}],
               "empty": []}'''

    def test_select_foreach(self):
        it = run(self.DATA, '''
            json "on"
            json_select "title"
            outputto "ARTIST"
            sayuntil " - "
            movechar 3
            outputto "ALBUM"
            sayrest
            outputto "YEAR"
            json_select "year"
            sayrest
            outputto "EXPLICIT"
            json_select "explicit"
            sayrest
            outputto "GENRE"
            json_select_array "tags" -1 "\\\\"
            sayrest
            outputto "PUBLISHER"
            json_select_array "label" 2
            json_select "name"
            sayrest
            json_unselect_object
            json_foreach "tracks"
              outputto "TITLE"
              json_select "title"
              sayrest
              say "|"
              outputto "PERFORMER"
              json_select_many "artists" "name" ", " " & "
              sayrest
              say "|"
              outputto "N"
              json_foreach_counter 2
              sayrest
              say "|"
            json_foreach_end
            outputto "TRACKS"
            json_select_many_count "tracks"
            sayrest
            json_foreach "empty"
              outputto "NEVER"
              say "x"
            json_foreach_end
        ''')
        o = it.out
        self.assertEqual((o("ARTIST"), o("ALBUM"), o("YEAR"), o("EXPLICIT")), ("Artist", "Album", "1999", "1"))
        self.assertEqual(o("GENRE"), "a\\b")       # script "\\\\" (Python-escaped) -> one backslash
        self.assertEqual(o("PUBLISHER"), "L2")
        self.assertEqual(o("TITLE"), "One|Two|")
        self.assertEqual(o("PERFORMER"), "X & Y||")
        self.assertEqual(o("N"), "01|02|")
        self.assertEqual(o("TRACKS"), "2")
        self.assertEqual(o("NEVER"), "")

    def test_failed_select_object_and_floor(self):
        it = run('{"a": [1, 2], "o": {"k": "v"}}', '''
            json "on"
            json_select_object "a"
            json_unselect_object
            json_select_object "o"
            json_select "k"
            sayrest
            json_unselect_object
            json_unselect_object
            json_select_object "o"
            ifnot ""
              say "!"
            endif
        ''')
        self.assertEqual(it.out("Output"), "v!")

    def test_json_current_and_vars(self):
        it = run('<script>{"x": "y"}</script>', '''
            regexpreplace "<script>(.*)</script>" "$1"
            json "on" "current"
            ifvar "mode" "true"
              json_select "x"
              sayrest
            else
              say "no"
            endif
            json "off"
        ''', {"mode": "true"})
        self.assertEqual(it.out("Output"), "y")


class AlbumTests(unittest.TestCase):
    def test_build_album(self):
        it = Interpreter("")
        it.outputs = {"album": ["ALBUM", "A &amp; B"], "title": ["TITLE", "x|y|"],
                      "temp": ["temp", ""], "coverurl": ["coverurl", "http://c/front"],
                      "output": ["Output", "ignored"], "genre": ["GENRE", "Rock$verticalBar()Pop"]}
        a = runner.build_album(it)
        self.assertEqual(a.fields["ALBUM"], ["A & B"])
        self.assertEqual(a.fields["TITLE"], ["x", "y"])
        self.assertEqual(a.fields["GENRE"], ["Rock|Pop"])
        self.assertEqual(a.tracks, 2)
        self.assertEqual(a.cover_url, "http://c/front")
        self.assertNotIn("OUTPUT", a.fields)
        self.assertEqual(a.value("ALBUM", 1), "A & B")

    def test_urls(self):
        from psytags.websources.srcfile import Source
        s = Source("x", "x", {"indexurl": "https://h/s?q=", "wordseparator": "+",
                              "encoding": "url-utf-8",
                              "searchby": "Album||%album%||release:%s||Artist||%artist%||%20AND%20artist:%28%s%29"})
        self.assertEqual(runner.index_url(s, ["Zeit Mutter", "Röyksopp"]),
                         "https://h/s?q=release:Zeit+Mutter%20AND%20artist:%28R%C3%B6yksopp%29")
        self.assertEqual(runner.cover_download_url("http://cache.mp3tag.de/coxy/abc/def.jpg"),
                         "https://i.discogs.com/abc/def.jpg")


if __name__ == "__main__":
    unittest.main()


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
        row, got = first_cover(None, rows, fetch=fetch, pause=0)
        self.assertEqual(row["_url"], "b")
        self.assertEqual(got, covers["b"])
        self.assertEqual(tried, ["a", "b"])
        self.assertIsNone(first_cover(None, rows[:1], fetch=fetch, pause=0))
        self.assertIsNone(first_cover(None, [], fetch=fetch, pause=0))


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
