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


if __name__ == "__main__":
    unittest.main()
