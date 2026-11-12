import unittest

from jarvis.capabilities.webread import WebReadCapability
from jarvis.knowledge.searxng import SearXNGError


class ModelTurn:
    def __init__(self, text):
        self.text = text
        self.tool_calls = []


class FakeModel:
    def __init__(self, text="Resume.", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def complete(self, messages, tools):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return ModelTurn(self.text)


class FakeFetcher:
    def __init__(self, text="", error=None):
        self.text = text
        self.error = error
        self.calls = []

    def fetch_text(self, url, max_chars=8000):
        self.calls.append(url)
        if self.error:
            raise self.error
        return self.text


class WebReadTests(unittest.TestCase):
    def test_summarizes_page(self):
        fetcher = FakeFetcher(text="Le produit coute 20 euros et sort en 2026.")
        model = FakeModel(text="Produit a 20 euros, sortie 2026.")
        cap = WebReadCapability(fetcher=fetcher, model=model)

        result = cap.summarize_url("https://example.com/x", "quel prix ?")

        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Produit a 20 euros, sortie 2026.")
        self.assertEqual(fetcher.calls, ["https://example.com/x"])
        self.assertIn("20 euros", model.calls[0][-1]["content"])

    def test_fetch_failure(self):
        cap = WebReadCapability(fetcher=FakeFetcher(error=SearXNGError("URL invalide")), model=FakeModel())
        result = cap.summarize_url("ftp://nope")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "fetch_failed")

    def test_empty_page(self):
        cap = WebReadCapability(fetcher=FakeFetcher(text="   "), model=FakeModel())
        result = cap.summarize_url("https://x.com")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "empty_page")

    def test_model_error(self):
        cap = WebReadCapability(fetcher=FakeFetcher(text="contenu"), model=FakeModel(error=RuntimeError("down")))
        result = cap.summarize_url("https://x.com")
        self.assertFalse(result.ok)
        self.assertEqual(result.error_code, "model_error")


class FetchTextValidationTests(unittest.TestCase):
    def test_rejects_non_http(self):
        from jarvis.knowledge.keyless import KeylessWebProvider
        provider = KeylessWebProvider(opener=lambda *a, **k: None)
        with self.assertRaises(SearXNGError):
            provider.fetch_text("file:///etc/passwd")
        with self.assertRaises(SearXNGError):
            provider.fetch_text("")


class _Page:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, *args):
        return self.body


def _resolving_to(*addresses):
    def resolve(host, port, *args, **kwargs):
        return [(None, None, None, "", (address, 0)) for address in addresses]

    return resolve


class FetchTextPrivateAddressTests(unittest.TestCase):
    def _provider(self, resolver=None):
        from jarvis.knowledge.keyless import KeylessWebProvider

        def forbidden(*args, **kwargs):
            raise AssertionError("a refused URL reached the network")

        return KeylessWebProvider(opener=forbidden, resolver=resolver)

    def test_rejects_literal_local_and_private_addresses(self):
        provider = self._provider()
        for url in (
            "http://127.0.0.1:11434/api/tags",
            "http://[::1]/",
            "http://10.0.0.5/admin",
            "http://192.168.1.1/",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url), self.assertRaises(SearXNGError):
                provider.fetch_text(url)

    def test_rejects_names_resolving_to_a_local_address(self):
        provider = self._provider(resolver=_resolving_to("127.0.0.1"))
        with self.assertRaises(SearXNGError):
            provider.fetch_text("http://localhost:11434/")

    def test_rejects_a_name_with_any_private_address(self):
        provider = self._provider(resolver=_resolving_to("93.184.216.34", "10.0.0.5"))
        with self.assertRaises(SearXNGError):
            provider.fetch_text("https://mixed.example/")

    def test_allows_a_name_resolving_to_a_public_address(self):
        from jarvis.knowledge.keyless import KeylessWebProvider

        provider = KeylessWebProvider(
            opener=lambda *a, **k: _Page(b"<p>Bonjour</p>"),
            resolver=_resolving_to("93.184.216.34"),
        )
        self.assertEqual(provider.fetch_text("https://site.example/"), "Bonjour")

    def test_redirect_to_a_local_address_is_refused(self):
        import urllib.error
        import urllib.request

        from jarvis.knowledge.keyless import _PublicRedirectHandler

        handler = _PublicRedirectHandler(_resolving_to("127.0.0.1"))
        request = urllib.request.Request("https://site.example/")
        with self.assertRaises(urllib.error.URLError):
            handler.redirect_request(request, None, 302, "Found", {}, "http://localhost:8080/")


class StripHtmlTests(unittest.TestCase):
    def test_script_and_style_content_is_not_page_text(self):
        from jarvis.knowledge.keyless import _strip_html

        markup = (
            "<html><head><style>body{color:red}</style>"
            "<script>window.__DATA__ = {secret: 1};</script></head>"
            "<body><h1>Titre</h1><noscript>Activez JS</noscript>"
            "<p>Un paragraphe.</p><script>track()</script></body></html>"
        )
        self.assertEqual(_strip_html(markup), "Titre Un paragraphe.")

    def test_adjacent_blocks_are_separate_words_but_inline_tags_are_not(self):
        from jarvis.knowledge.keyless import _strip_html

        self.assertEqual(_strip_html("<li>un</li><li>deux</li>"), "un deux")
        self.assertEqual(_strip_html("<p>in<b>visible</b>ment</p>"), "invisiblement")

    def test_text_after_a_script_is_kept(self):
        from jarvis.knowledge.keyless import _strip_html

        self.assertEqual(_strip_html("<script>a<b</script><p>apres</p>"), "apres")


if __name__ == "__main__":
    unittest.main()
