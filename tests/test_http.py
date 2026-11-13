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
        self.assertIn("HTTP 500", str(caught.exception))        # Last.fm and MusicBrainz look for the code
        self.assertIn("images.example.invalid", str(caught.exception))
        self.assertNotIn("://", str(caught.exception))
        self.assertEqual(len(str(caught.exception).splitlines()), 1)

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


class CertificateTests(unittest.TestCase):
    """A Linux build carries an OpenSSL that may look for certificates where the
    running distribution keeps none; the system bundle is loaded by path then."""

    def test_the_first_existing_bundle_is_taken(self):
        with mock.patch.object(http.os.path, "isfile", side_effect=lambda p: p == "/b"):
            self.assertEqual(http.system_ca_file(("/a", "/b", "/c")), "/b")

    def test_no_bundle_means_none(self):
        with mock.patch.object(http.os.path, "isfile", return_value=False):
            self.assertIsNone(http.system_ca_file(("/a",)))

    def test_linux_loads_the_system_bundle(self):
        ctx = mock.Mock()
        http.ssl_context.cache_clear()
        self.addCleanup(http.ssl_context.cache_clear)
        with mock.patch.object(http.sys, "platform", "linux"), \
                mock.patch.object(http.ssl, "create_default_context", return_value=ctx), \
                mock.patch.object(http, "system_ca_file", return_value="/etc/ssl/cert.pem"), \
                mock.patch.object(http, "bundled_ca_file", return_value="/b/cacert.pem"):
            self.assertIs(http.ssl_context(), ctx)
        self.assertEqual(ctx.load_verify_locations.call_args_list,
                         [mock.call(cafile="/etc/ssl/cert.pem"), mock.call(cafile="/b/cacert.pem")])

    def test_macos_loads_the_system_bundle(self):
        ctx = mock.Mock()
        http.ssl_context.cache_clear()
        self.addCleanup(http.ssl_context.cache_clear)
        with mock.patch.object(http.sys, "platform", "darwin"), \
                mock.patch.object(http.ssl, "create_default_context", return_value=ctx), \
                mock.patch.object(http, "system_ca_file", return_value="/etc/ssl/cert.pem"), \
                mock.patch.object(http, "bundled_ca_file", return_value="/b/cacert.pem"):
            self.assertIs(http.ssl_context(), ctx)
        self.assertEqual(ctx.load_verify_locations.call_args_list,
                         [mock.call(cafile="/etc/ssl/cert.pem"), mock.call(cafile="/b/cacert.pem")])

    def test_windows_adds_mozillas_roots(self):
        """Windows fills its root store lazily; a root no site has needed yet is missing."""
        ctx = mock.Mock()
        http.ssl_context.cache_clear()
        self.addCleanup(http.ssl_context.cache_clear)
        with mock.patch.object(http.sys, "platform", "win32"), \
                mock.patch.object(http.ssl, "create_default_context", return_value=ctx), \
                mock.patch.object(http, "bundled_ca_file", return_value="C:/b/cacert.pem"):
            self.assertIs(http.ssl_context(), ctx)
        ctx.load_verify_locations.assert_called_once_with(cafile="C:/b/cacert.pem")

    def test_without_certifi_the_system_list_stays(self):
        ctx = mock.Mock()
        http.ssl_context.cache_clear()
        self.addCleanup(http.ssl_context.cache_clear)
        with mock.patch.object(http.sys, "platform", "win32"), \
                mock.patch.object(http.ssl, "create_default_context", return_value=ctx), \
                mock.patch.object(http, "bundled_ca_file", return_value=None):
            self.assertIs(http.ssl_context(), ctx)
        ctx.load_verify_locations.assert_not_called()

    def test_mozillas_list_is_installed(self):
        self.assertIsNotNone(http.bundled_ca_file())

    def test_requests_use_that_context(self):
        http._cache.clear()
        with mock.patch.object(http.urllib.request, "urlopen", return_value=_Reply(b"x")) as opened:
            http.fetch_bytes(URL)
        self.assertIs(opened.call_args.kwargs["context"], http.ssl_context())
