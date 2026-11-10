import json
import os
import re
import tempfile
import unittest
from types import SimpleNamespace as NS
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from psytags import config
from psytags.config import Options
from psytags.track import Track
from psytags.ui.mainwindow import MainWindow
from psytags.websources import coverfetch, coverprovider as cp, http

VALID = {"format": 1, "name": "Testquelle", "search_url": "https://api.example.invalid/s?q={artist}%20{album}",
         "results": "data.*", "album": "title", "artist": "artist.name", "image": "cover"}


class Guarded(unittest.TestCase):
    def setUp(self):
        d = tempfile.TemporaryDirectory()
        self.addCleanup(d.cleanup)
        self.dir = d.name
        os.makedirs(os.path.join(d.name, "data"))
        patcher = mock.patch.object(config, "config_dir", lambda: d.name)
        patcher.start()
        self.addCleanup(patcher.stop)

    def drop(self, name, content):
        os.makedirs(cp.folder(), exist_ok=True)
        path = os.path.join(cp.folder(), name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content if isinstance(content, str) else json.dumps(content))
        return path


class LoadTests(Guarded):
    def _problem(self, **changes):
        content = {**VALID, **changes}
        with self.assertRaises(cp.ProviderError) as caught:
            cp.load(self.drop("x.json", {k: v for k, v in content.items() if v is not None}))
        return str(caught.exception)

    def test_a_valid_file(self):
        p = cp.load(self.drop("x.json", VALID))
        self.assertEqual(p.name, "Testquelle")
        self.assertEqual(p.min_interval, 1.0)
        self.assertFalse(p.browser_agent)

    def test_broken_json_is_named(self):
        with self.assertRaises(cp.ProviderError) as caught:
            cp.load(self.drop("kaputt.json", "{nein"))
        self.assertIn("kaputt.json", str(caught.exception))

    def test_a_missing_field_is_named(self):
        self.assertIn("image", self._problem(image=None))

    def test_an_unknown_format_is_refused(self):
        self.assertIn("format", self._problem(format=9))

    def test_a_typing_error_in_a_field_name_is_named(self):
        self.assertIn("albun", self._problem(albun="x"))

    def test_only_web_addresses(self):
        self.assertIn("search_url", self._problem(search_url="file:///c:/x?{album}"))

    def test_the_address_needs_a_placeholder(self):
        self.assertIn("search_url", self._problem(search_url="https://a.example.invalid/"))

    def test_a_broken_pattern_is_named(self):
        self.assertIn("image_replace", self._problem(image_replace=[["(", "x"]]))

    def test_embedded_json_needs_one_group(self):
        self.assertIn("embedded_json", self._problem(embedded_json="<script>.*</script>"))

    def test_the_interval_must_be_a_number(self):
        self.assertIn("min_interval", self._problem(min_interval="schnell"))

    def test_the_built_in_name_is_taken(self):
        self.assertIn("name", self._problem(name=cp.ARCHIVE))


class DiscoverTests(Guarded):
    def test_no_folder_no_providers(self):
        self.assertEqual(cp.discover(), ([], []))

    def test_a_dropped_file_counts_at_once(self):
        self.assertEqual(cp.discover()[0], [])
        self.drop("a.json", VALID)
        self.assertEqual([p.name for p in cp.discover()[0]], ["Testquelle"])

    def test_a_bad_file_does_not_disturb_the_others(self):
        self.drop("a.json", VALID)
        self.drop("b.json", "{nein")
        providers, problems = cp.discover()
        self.assertEqual([p.name for p in providers], ["Testquelle"])
        self.assertEqual(len(problems), 1)
        self.assertIn("b.json", problems[0])

    def test_the_same_name_twice_is_reported(self):
        self.drop("a.json", VALID)
        self.drop("b.json", VALID)
        providers, problems = cp.discover()
        self.assertEqual(len(providers), 1)
        self.assertIn("b.json", problems[0])

    def test_other_files_are_ignored(self):
        self.drop("liesmich.txt", "hallo")
        self.assertEqual(cp.discover(), ([], []))


def provider(**changes):
    return cp.Provider(**{"name": "Testquelle", "search_url": VALID["search_url"], "results": "data.*",
                          "album": "title", "artist": "artist.name", "image": "cover", "min_interval": 0, **changes})


ANSWER = {"data": [{"title": "A", "artist": {"name": "B"}, "n": 9, "kind": "album", "cover": "https://i/1/{s}.jpg", "web": "https://w/1"},
                   {"title": "Song", "artist": {"name": "B"}, "kind": "song", "cover": "https://i/2/{s}.jpg"},
                   {"title": "A", "artist": {"name": "B"}, "kind": "album", "cover": "https://i/1/{s}.jpg"},
                   {"title": "Ohne Bild", "artist": {"name": "B"}, "kind": "album"}]}


class RowsTests(unittest.TestCase):
    def test_fields_come_from_their_paths(self):
        row = cp.rows(provider(tracks="n", page="web"), json.dumps(ANSWER))[0]
        self.assertEqual((row["Album"], row["Artist"], row["Tracks"], row["_preview"]), ("A", "B", "9", "https://w/1"))

    def test_same_picture_only_once_and_no_row_without_a_picture(self):
        self.assertEqual([r["Album"] for r in cp.rows(provider(), json.dumps(ANSWER))], ["A", "Song"])

    def test_a_hit_without_a_title_does_not_hide_a_later_one(self):
        doc = {"data": [{"cover": "x"}, {"title": "A", "artist": {"name": "B"}, "cover": "x"}]}
        rows = cp.rows(provider(), json.dumps(doc))
        self.assertEqual([r["Album"] for r in rows], ["A"])

    def test_only_if_filters(self):
        rows = cp.rows(provider(only_if={"kind": "album"}), json.dumps(ANSWER))
        self.assertEqual([r["Album"] for r in rows], ["A"])

    def test_list_positions_and_every_element(self):
        doc = {"a": [{"b": [{"t": [{"x": "tief"}], "pic": "p"}]}]}
        rows = cp.rows(provider(results="a.*.b.*", album="t.0.x", artist="nix", image="pic"), json.dumps(doc))
        self.assertEqual((rows[0]["Album"], rows[0]["Artist"]), ("tief", ""))

    def test_image_and_preview_addresses_are_rewritten(self):
        p = provider(image_replace=[[r"\{s\}", "3000"]], preview_replace=[[r"\{s\}", "600"]])
        row = cp.rows(p, json.dumps(ANSWER))[0]
        self.assertEqual((row["_image"], row["_coverurl"]), ("https://i/1/3000.jpg", "https://i/1/600.jpg"))

    def test_without_a_preview_rule_the_image_is_shown(self):
        row = cp.rows(provider(image_replace=[[r"\{s\}", "3000"]]), json.dumps(ANSWER))[0]
        self.assertEqual(row["_coverurl"], "https://i/1/3000.jpg")

    def test_json_inside_a_web_page(self):
        page = '<html><script id="d">' + json.dumps(ANSWER) + "</script></html>"
        rows = cp.rows(provider(embedded_json='<script id="d">(.*?)</script>'), page)
        self.assertEqual(rows[0]["Album"], "A")

    def test_an_unreadable_answer_is_an_error(self):
        with self.assertRaises(cp.ProviderError) as caught:
            cp.rows(provider(), "<html>")
        self.assertIn("Testquelle", str(caught.exception))

    def test_a_page_without_the_block_is_an_error(self):
        with self.assertRaises(cp.ProviderError):
            cp.rows(provider(embedded_json="<x>(.*?)</x>"), "<html>")

    def test_rows_fit_the_existing_rating(self):
        rows = cp.rows(provider(tracks="n"), json.dumps(ANSWER))
        self.assertEqual(coverfetch.rank(rows, "A", "B", 9)[0].row, rows[0])


class RequestTests(unittest.TestCase):
    def test_the_search_is_quoted(self):
        with mock.patch.object(cp.http, "fetch", return_value='{"data": []}') as fetch:
            cp.search(provider(), "AC/DC", "Back in Black")
        url = fetch.call_args.args[0]
        self.assertEqual(url, "https://api.example.invalid/s?q=AC%2FDC%20Back%20in%20Black")
        self.assertEqual(fetch.call_args.args[1], "1")
        self.assertEqual(fetch.call_args.kwargs["timeout"], cp.TIMEOUT)

    def test_a_provider_can_ask_like_a_browser(self):
        with mock.patch.object(cp.http, "fetch", return_value='{"data": []}') as fetch:
            cp.search(provider(browser_agent=True), "a", "b")
        self.assertEqual(fetch.call_args.args[1], "2")

    def test_the_picture_uses_the_same_identity(self):
        with mock.patch.object(cp.http, "fetch_bytes", return_value=b"bild") as fetch:
            self.assertEqual(cp.image(provider(browser_agent=True), {"_image": "https://i/x"}), b"bild")
        fetch.assert_called_once_with("https://i/x", timeout=cp.TIMEOUT, browser=True)

    def test_the_interval_between_requests_is_kept(self):
        p = provider(name="Takt", min_interval=2.0)
        cp._last_call.pop("Takt", None)
        with mock.patch.object(cp.time, "monotonic", side_effect=[100.0, 100.5, 102.0]), \
                mock.patch.object(cp.time, "sleep") as sleep:
            cp._wait_turn(p)
            cp._wait_turn(p)
        sleep.assert_called_once_with(1.5)

    def test_http_can_fetch_pictures_like_a_browser(self):
        reply = mock.MagicMock()
        reply.__enter__.return_value.read.return_value = b"x"
        with mock.patch.object(http.urllib.request, "urlopen", return_value=reply) as opened:
            http.fetch_bytes("https://i.example.invalid/x", browser=True)
        self.assertEqual(opened.call_args.args[0].get_header("User-agent"), http.BROWSER_AGENT)


class ArrangementTests(Guarded):
    def _with(self, *names):
        return [provider(name=n) for n in names]

    def test_the_archive_comes_first_and_new_providers_are_on(self):
        self.assertEqual(cp.arranged(self._with("A", "B")), [(cp.ARCHIVE, True), ("A", True), ("B", True)])

    def test_order_and_switches_are_kept(self):
        cp.save_arrangement([("A", True), (cp.ARCHIVE, False)])
        self.assertEqual(cp.arranged(self._with("A")), [("A", True), (cp.ARCHIVE, False)])

    def test_a_new_file_joins_at_the_end(self):
        cp.save_arrangement([("A", True), (cp.ARCHIVE, True)])
        self.assertEqual(cp.arranged(self._with("A", "Neu"))[-1], ("Neu", True))

    def test_a_removed_file_is_gone(self):
        cp.save_arrangement([("Weg", True), (cp.ARCHIVE, True)])
        self.assertEqual(cp.arranged([]), [(cp.ARCHIVE, True)])

    def test_active_sources_in_order(self):
        providers = self._with("A", "B")
        cp.save_arrangement([("B", True), (cp.ARCHIVE, True), ("A", False)])
        got = cp.active(providers)
        self.assertEqual(got[0].name, "B")
        self.assertEqual(got[1], cp.ARCHIVE)
        self.assertEqual(len(got), 2)


class Tagged:
    def __init__(self, **fields):
        self.fields = fields
        self.data = NS(covers=[NS(type=4), NS(type=3)])

    def get(self, name):
        value = self.fields.get(name)
        return [value] if value else []


class ChainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _chain(self, sources, **results):
        win = mock.MagicMock()
        win._cover_sources.return_value = sources
        win.fetch_archive_cover.return_value = results.get("archive", "")
        win.fetch_provider_cover.side_effect = results.get("providers", [""])
        return win, MainWindow.fetch_cover_chain(win, ["t"], True, ("r", "g"), True)

    def test_the_first_delivering_source_ends_it(self):
        win, result = self._chain([cp.ARCHIVE, provider()])
        self.assertEqual(result, "")
        win.fetch_provider_cover.assert_not_called()

    def test_the_next_source_helps_out(self):
        p = provider()
        win, result = self._chain([cp.ARCHIVE, p], archive="kein Cover")
        self.assertEqual(result, "")
        win.fetch_provider_cover.assert_called_once_with(p, ["t"], True, True)

    def test_a_provider_can_come_first(self):
        win, result = self._chain([provider(), cp.ARCHIVE])
        self.assertEqual(result, "")
        win.fetch_archive_cover.assert_not_called()

    def test_all_reasons_are_kept(self):
        _win, result = self._chain([cp.ARCHIVE, provider()], archive="eins", providers=["zwei"])
        self.assertEqual(result, "eins; zwei")

    def test_cancel_ends_the_chain(self):
        win, result = self._chain([provider(), cp.ARCHIVE], providers=["Abgebrochen"])
        self.assertEqual(result, "Abgebrochen")
        win.fetch_archive_cover.assert_not_called()

    def test_everything_off(self):
        _win, result = self._chain([])
        self.assertEqual(result, "Keine Cover-Quelle eingeschaltet")


FOUND = [{"Album": "A", "Artist": "B", "Tracks": "1", "_image": "https://i/1", "_coverurl": "https://i/1"}]


class ProviderCoverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _win(self):
        win = mock.MagicMock()
        win._background.side_effect = lambda label, call: call()
        win._waiting.side_effect = lambda label, call: call()
        win._cover_big_enough.return_value = True
        return win

    def _track(self, album="A"):
        return Tagged(ALBUM=album, ARTIST="B")

    def _fetch(self, win, tracks, rows=FOUND, ask=False, pick=False, data=b"\x89PNGdata"):
        with mock.patch.object(cp, "search", return_value=rows) as search, \
                mock.patch.object(cp, "image", return_value=data):
            return MainWindow.fetch_provider_cover(win, provider(), tracks, ask, pick), search

    def test_a_certain_match_replaces_the_front_cover(self):
        win = self._win()
        t = self._track()
        result, search = self._fetch(win, [t])
        self.assertEqual(result, "")
        self.assertEqual(search.call_args.args[1:], ("B", "A"))
        win._write.call_args.args[2](t)
        self.assertEqual(t.data.covers[0].mime, "image/png")
        self.assertEqual(t.data.covers[0].description, "Testquelle")
        self.assertEqual([c.type for c in t.data.covers], [3, 4])

    def test_album_artist_comes_first(self):
        win = self._win()
        t = Tagged(ALBUM="A", ARTIST="Gast", ALBUMARTIST="B")
        _result, search = self._fetch(win, [t])
        self.assertEqual(search.call_args.args[1], "B")

    def test_without_a_certain_match_a_run_moves_on(self):
        win = self._win()
        result, _search = self._fetch(win, [self._track("Ganz anders")])
        self.assertEqual(result, "Kein sicherer Treffer bei Testquelle")
        win._write.assert_not_called()

    def _picked(self, code):
        win = self._win()
        dialog = mock.MagicMock()
        dialog.exec.return_value = code
        dialog.selected.return_value = FOUND[0]
        with mock.patch("psytags.ui.dialogs.tagsources.ResultsDialog", return_value=dialog) as results:
            result, _search = self._fetch(win, [self._track("Ganz anders")], ask=True, pick=True)
        return win, result, results

    def test_on_demand_the_user_picks_from_the_list(self):
        win, result, results = self._picked(1)
        self.assertEqual(result, "")
        self.assertEqual(results.call_args.args[1], FOUND)
        win._write.assert_called_once()

    def test_closing_the_list_is_a_cancel(self):
        win, result, _results = self._picked(0)
        self.assertEqual(result, "Abgebrochen")
        win._write.assert_not_called()

    def test_no_hit_at_all(self):
        result, _search = self._fetch(self._win(), [self._track()], rows=[], pick=True)
        self.assertEqual(result, "Kein Cover bei Testquelle gefunden")

    def test_a_too_small_cover_is_not_written(self):
        win = self._win()
        win._cover_big_enough.return_value = False
        result, _search = self._fetch(win, [self._track()], ask=True)
        self.assertIn("zu klein", result)
        self.assertTrue(win._cover_big_enough.call_args.kwargs["ask"])
        win._write.assert_not_called()

    def test_network_problems_become_the_reason(self):
        win = self._win()
        with mock.patch.object(cp, "search", side_effect=http.FetchError("weg\nmehr")):
            self.assertEqual(MainWindow.fetch_provider_cover(win, provider(), [self._track()]), "weg")

    def test_a_changed_page_becomes_the_reason(self):
        win = self._win()
        with mock.patch.object(cp, "search", side_effect=cp.ProviderError("Testquelle: nicht lesbar")):
            self.assertEqual(MainWindow.fetch_provider_cover(win, provider(), [self._track()]), "Testquelle: nicht lesbar")

    def test_on_demand_it_can_be_canceled(self):
        from psytags.ui.mainwindow import _Canceled
        win = self._win()
        win._waiting.side_effect = _Canceled()
        result = MainWindow.fetch_provider_cover(win, provider(), [self._track()], True, True)
        self.assertEqual(result, "Abgebrochen")

    def test_on_demand_the_window_with_cancel_is_used(self):
        win = self._win()
        self._fetch(win, [self._track()], ask=True, pick=True)
        self.assertTrue(win._waiting.called)
        win._background.assert_not_called()

    def test_a_single_album_gets_the_window_too(self):
        win = self._win()
        self._fetch(win, [self._track()], ask=True)
        self.assertTrue(win._waiting.called)
        win._background.assert_not_called()

    def test_in_a_run_the_progress_window_is_already_there(self):
        win = self._win()
        self._fetch(win, [self._track()])
        self.assertTrue(win._background.called)
        win._waiting.assert_not_called()


class WindowTests(Guarded):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_the_cover_menu_lists_active_providers(self):
        win = mock.MagicMock()
        win.view.selected_tracks.return_value = ["t"]
        win._cover_sources.return_value = [cp.ARCHIVE, provider()]
        self.assertEqual(MainWindow._cover_fetch_entries(win), [("fetch_mb", "Cover von Cover Art Archive laden"),
                                                        ("provider:Testquelle", "Cover von Testquelle laden")])

    def test_the_menu_entry_lets_the_user_pick(self):
        win = mock.MagicMock()
        p = provider()
        win._cover_sources.return_value = [cp.ARCHIVE, p]
        win.fetch_provider_cover.return_value = "kein Cover"
        MainWindow._cover_command(win, "provider:Testquelle")
        win.fetch_provider_cover.assert_called_once_with(p, win.view.selected_tracks.return_value, True, True)
        self.assertEqual(win.message.call_args.args[0], "kein Cover")

    def test_a_bad_file_is_reported_once(self):
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        self.drop("b.json", "{nein")
        with mock.patch.object(w, "message") as message:
            self.assertEqual(w._cover_sources(), [cp.ARCHIVE])
            self.assertEqual(w._cover_sources(), [cp.ARCHIVE])
        message.assert_called_once()
        self.assertIn("b.json", message.call_args.args[0])

    def test_waiting_returns_the_answer_and_closes(self):
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        self.assertEqual(w._waiting("Bitte warten", lambda: 7), 7)
        with self.assertRaises(ValueError):
            w._waiting("Bitte warten", lambda: (_ for _ in ()).throw(ValueError("x")))

    def test_waiting_can_be_left_at_once(self):
        import threading
        from psytags.ui.mainwindow import _Canceled, _StayingProgress
        w = MainWindow()
        self.addCleanup(w.deleteLater)
        release = threading.Event()
        self.addCleanup(release.set)
        real = _StayingProgress

        def stopped(*args):
            dialog = real(*args)
            dialog.request_stop()
            return dialog
        with mock.patch("psytags.ui.mainwindow._StayingProgress", side_effect=stopped):
            with self.assertRaises(_Canceled):
                w._waiting("Bitte warten", release.wait)


class OptionsTests(Guarded):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self):
        from psytags.ui.dialogs.options import OptionsDialog
        d = OptionsDialog(Options())
        self.addCleanup(d.deleteLater)
        return d

    @staticmethod
    def _names(d):
        return [d.cover_sources.item(i).text() for i in range(d.cover_sources.count())]

    def test_the_tab_lists_all_sources(self):
        self.drop("a.json", VALID)
        self.assertEqual(self._names(self._dialog()), [cp.ARCHIVE, "Testquelle"])

    def test_order_and_switches_are_saved(self):
        from PySide6.QtCore import Qt
        self.drop("a.json", VALID)
        d = self._dialog()
        d.cover_sources.setCurrentRow(1)
        d.move_cover_source(-1)
        self.assertEqual(self._names(d), ["Testquelle", cp.ARCHIVE])
        self.assertEqual(d.cover_sources.currentRow(), 0)
        d.cover_sources.item(1).setCheckState(Qt.CheckState.Unchecked)
        d.accept()
        self.assertEqual(cp.arranged(cp.discover()[0]), [("Testquelle", True), (cp.ARCHIVE, False)])

    def test_moving_stops_at_the_ends(self):
        self.drop("a.json", VALID)
        d = self._dialog()
        d.cover_sources.setCurrentRow(0)
        d.move_cover_source(-1)
        self.assertEqual(self._names(d), [cp.ARCHIVE, "Testquelle"])

    def test_a_bad_file_is_shown(self):
        from PySide6.QtWidgets import QLabel
        self.drop("b.json", "{nein")
        d = self._dialog()
        self.assertTrue([l for l in d.findChildren(QLabel) if "b.json" in l.text()])


class DocumentationTests(Guarded):
    def test_the_example_in_the_repository_is_valid(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        p = cp.load(os.path.join(root, "docs", "cover-provider-example.json"))
        self.assertTrue(p.name)

    def test_every_field_is_documented(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "cover-provider.md"), encoding="utf-8") as fh:
            text = fh.read()
        for name in cp.KNOWN_FIELDS:
            self.assertIn(f"`{name}`", text)

    @staticmethod
    def _json_blocks() -> list[dict]:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "cover-provider.md"), encoding="utf-8") as fh:
            return [json.loads(b) for b in re.findall(r"```json\n(.*?)```", fh.read(), re.S)]

    def test_the_example_in_the_text_is_the_example_file(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "docs", "cover-provider-example.json"), encoding="utf-8") as fh:
            self.assertEqual(self._json_blocks()[1], json.load(fh))

    def test_the_worked_example_delivers_a_certain_cover(self):
        answer, description = self._json_blocks()
        description.pop("format")
        got = cp.rows(cp.Provider(**description), json.dumps(answer))
        self.assertEqual(got[0]["_image"], "https://img.example.com/1/1400x1400.jpg")
        self.assertEqual(got[0]["_coverurl"], "https://img.example.com/1/500x500.jpg")
        self.assertIsNotNone(coverfetch.confident(coverfetch.rank(got, "Example Album", "Example Band", 10)))

    def test_a_hit_without_an_artist_is_never_certain(self):
        rows = [{"Album": "Example Album", "Artist": "", "Tracks": "10"}]
        self.assertIsNone(coverfetch.confident(coverfetch.rank(rows, "Example Album", "Example Band", 10)))

    def test_the_message_about_the_address_shows_plain_placeholders(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "x.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(dict(VALID, search_url="https://example.invalid/"), fh)
            with self.assertRaises(cp.ProviderError) as caught:
                cp.load(path)
        self.assertIn("{album}", str(caught.exception))
        self.assertNotIn("{{", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
