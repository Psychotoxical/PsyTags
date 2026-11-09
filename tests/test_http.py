import unittest
import urllib.error
from unittest import mock

from psytags.websources import http


class _Reply:
    def __init__(self, data=b"ok"):
        self.data, self.headers = data, {}

    def read(self):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


URL = "https://images.example.invalid/cover.jpg"


class RetryTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(http.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)
        http._cache.clear()

    def _open(self, *results):
        patcher = mock.patch.object(http.urllib.request, "urlopen", side_effect=list(results))
        opened = patcher.start()
        self.addCleanup(patcher.stop)
        return opened

    def test_a_broken_connection_is_tried_again(self):
        opened = self._open(ConnectionResetError(10054, "reset"), _Reply(b"bild"))
        self.assertEqual(http.fetch_bytes(URL), b"bild")
        self.assertEqual(opened.call_count, 2)
        self.sleep.assert_called_once()

    def test_a_cut_off_download_is_tried_again(self):
        broken = mock.MagicMock()
        broken.__enter__.return_value.read.side_effect = http.http.client.IncompleteRead(b"x", 10)
        self._open(broken, _Reply(b"bild"))
        self.assertEqual(http.fetch_bytes(URL), b"bild")

    def test_it_gives_up_with_a_short_message(self):
        opened = self._open(*[urllib.error.URLError("reset")] * 3)
        with self.assertRaises(http.FetchError) as caught:
            http.fetch_bytes(URL)
        self.assertEqual(opened.call_count, 3)
        self.assertIn("images.example.invalid", str(caught.exception))
        self.assertNotIn("urlopen", str(caught.exception))

    def test_a_server_answer_is_not_repeated(self):
        error = urllib.error.HTTPError(URL, 404, "Not Found", {}, None)
        opened = self._open(error)
        with self.assertRaises(http.FetchError):
            http.fetch_bytes(URL)
        self.assertEqual(opened.call_count, 1)

    def test_a_server_error_has_its_own_type(self):
        self._open(urllib.error.HTTPError(URL, 500, "Internal Server Error", {}, None))
        with self.assertRaises(http.ServerError) as caught:
            http.fetch_bytes(URL)
        self.assertIn("HTTP 500", str(caught.exception))        # Last.fm looks for this

    def test_text_requests_are_tried_again_too(self):
        opened = self._open(ConnectionResetError(10054, "reset"), _Reply(b"seite"))
        self.assertEqual(http.fetch("https://images.example.invalid/search?term=x"), "seite")
        self.assertEqual(opened.call_count, 2)

    def test_other_images_name_the_program(self):
        opened = self._open(_Reply())
        http.fetch_bytes("https://coverartarchive.org/release/x/front")
        self.assertEqual(opened.call_args.args[0].get_header("User-agent"), http.USER_AGENT)


if __name__ == "__main__":
    unittest.main()
