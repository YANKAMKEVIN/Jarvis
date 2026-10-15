import unittest
import urllib.error

from jarvis.knowledge.keyless import (
    FallbackProvider,
    KeylessWebProvider,
    _decode_ddg_href,
    _rfc822_to_iso,
)
from jarvis.knowledge.models import SearchMode
from jarvis.knowledge.searxng import SearXNGError


GOOGLE_NEWS_RSS = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item>
  <title>OpenAI lance un nouveau modele</title>
  <link>https://news.google.com/articles/abc</link>
  <pubDate>Wed, 15 Oct 2026 08:00:00 GMT</pubDate>
  <description>&lt;a href="https://lemonde.fr/x"&gt;Le Monde&lt;/a&gt; details ici</description>
  <source url="https://lemonde.fr">Le Monde</source>
</item>
<item>
  <title>Autre actualite tech</title>
  <link>https://news.google.com/articles/def</link>
  <pubDate>Wed, 15 Oct 2026 07:00:00 GMT</pubDate>
  <description>resume court</description>
</item>
</channel></rss>"""

DDG_HTML = """
<html><body>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fen.wikipedia.org%2Fwiki%2FFrance&amp;rut=x">
    France
  </a>
  <a class="result__snippet">La France est un pays d'Europe.</a>
</div>
<div class="result">
  <a class="result__a" href="https://direct.example.com/page">Direct result</a>
  <div class="result__snippet">Snippet two</div>
</div>
</body></html>
""".encode("utf-8")


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, *args):
        return self.body


def opener_returning(body):
    def _open(request, timeout=None):
        return FakeResponse(body)

    return _open


def opener_raising(error):
    def _open(request, timeout=None):
        raise error

    return _open


class RecordingProvider:
    def __init__(self, results=None, error=None):
        self.results = results or []
        self.error = error
        self.calls = []

    def search(self, query, mode=SearchMode.GENERAL):
        self.calls.append((query, mode))
        if self.error is not None:
            raise self.error
        return list(self.results)


class KeylessNewsTests(unittest.TestCase):
    def test_parses_google_news_rss(self):
        provider = KeylessWebProvider(opener=opener_returning(GOOGLE_NEWS_RSS))
        results = provider.search("openai", mode=SearchMode.NEWS)

        self.assertEqual(len(results), 2)
        first = results[0]
        self.assertEqual(first.title, "OpenAI lance un nouveau modele")
        self.assertEqual(first.url, "https://news.google.com/articles/abc")
        self.assertEqual(first.pubdate, "Wed, 15 Oct 2026 08:00:00 GMT")
        # RFC 822 pubDate normalized to ISO so the service can date it.
        self.assertEqual(first.published_date, "2026-10-15T08:00:00+00:00")
        self.assertIn("Le Monde", first.snippet)

    def test_malformed_feed_yields_empty(self):
        provider = KeylessWebProvider(opener=opener_returning(b"not xml at all"))
        self.assertEqual(provider.search("x", mode=SearchMode.NEWS), [])

    def test_blank_query_yields_empty(self):
        provider = KeylessWebProvider(opener=opener_returning(GOOGLE_NEWS_RSS))
        self.assertEqual(provider.search("   ", mode=SearchMode.NEWS), [])

    def test_news_network_failure_raises(self):
        provider = KeylessWebProvider(
            opener=opener_raising(urllib.error.URLError("down"))
        )
        with self.assertRaises(SearXNGError):
            provider.search("openai", mode=SearchMode.NEWS)


class KeylessGeneralTests(unittest.TestCase):
    def test_parses_duckduckgo_html_and_decodes_redirect(self):
        provider = KeylessWebProvider(opener=opener_returning(DDG_HTML))
        results = provider.search("france", mode=SearchMode.GENERAL)

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].url, "https://en.wikipedia.org/wiki/France")
        self.assertEqual(results[0].title, "France")
        self.assertIn("Europe", results[0].snippet)
        self.assertEqual(results[1].url, "https://direct.example.com/page")

    def test_general_network_failure_degrades_to_empty(self):
        provider = KeylessWebProvider(
            opener=opener_raising(urllib.error.URLError("down"))
        )
        self.assertEqual(provider.search("france", mode=SearchMode.GENERAL), [])


class DecodeHrefTests(unittest.TestCase):
    def test_decodes_uddg_target(self):
        href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=z"
        self.assertEqual(_decode_ddg_href(href), "https://example.com/a")

    def test_passes_through_direct_url(self):
        self.assertEqual(
            _decode_ddg_href("https://example.com/a"), "https://example.com/a"
        )

    def test_empty_href(self):
        self.assertEqual(_decode_ddg_href(""), "")


class Rfc822DateTests(unittest.TestCase):
    def test_parses_rfc822(self):
        self.assertEqual(
            _rfc822_to_iso("Wed, 15 Oct 2026 08:00:00 GMT"),
            "2026-10-15T08:00:00+00:00",
        )

    def test_none_and_garbage_return_none(self):
        self.assertIsNone(_rfc822_to_iso(None))
        self.assertIsNone(_rfc822_to_iso("not a date"))


class FallbackProviderTests(unittest.TestCase):
    def test_uses_primary_when_it_returns_results(self):
        primary = RecordingProvider(results=["r1"])
        fallback = RecordingProvider(results=["r2"])
        provider = FallbackProvider(primary, fallback)

        self.assertEqual(provider.search("q", mode=SearchMode.NEWS), ["r1"])
        self.assertEqual(fallback.calls, [])
        self.assertEqual(primary.calls, [("q", SearchMode.NEWS)])

    def test_falls_back_when_primary_errors(self):
        primary = RecordingProvider(error=SearXNGError("down"))
        fallback = RecordingProvider(results=["r2"])
        provider = FallbackProvider(primary, fallback)

        self.assertEqual(provider.search("q"), ["r2"])
        self.assertEqual(fallback.calls, [("q", SearchMode.GENERAL)])

    def test_falls_back_when_primary_empty(self):
        primary = RecordingProvider(results=[])
        fallback = RecordingProvider(results=["r2"])
        provider = FallbackProvider(primary, fallback)

        self.assertEqual(provider.search("q"), ["r2"])

    def test_total_failure_raises_searxng_error(self):
        primary = RecordingProvider(error=RuntimeError("boom"))
        fallback = RecordingProvider(error=SearXNGError("also down"))
        provider = FallbackProvider(primary, fallback)

        with self.assertRaises(SearXNGError):
            provider.search("q")


if __name__ == "__main__":
    unittest.main()
