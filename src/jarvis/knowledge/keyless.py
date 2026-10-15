"""Keyless web search providers: work with no infrastructure and no API key.

These implement the same contract as SearXNGProvider -- `search(query, mode)
-> list[SearchResult]` -- so KnowledgeService uses them unchanged. News goes
through Google News' public RSS (clean XML, reliable); general queries go
through DuckDuckGo's HTML endpoint (best effort, degrades to an empty list
rather than raising on a parse miss).

FallbackProvider lets the voice assistant prefer a local SearXNG when it is
running and fall back to the keyless providers otherwise, with no config.
A total failure is reported as SearXNGError so KnowledgeService's existing
"source unavailable" handling applies without any change to the service.
"""

from __future__ import annotations

import html
import socket
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from jarvis.knowledge.models import SearchMode, SearchResult
from jarvis.knowledge.searxng import SearXNGError


GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"
DUCKDUCKGO_HTML = "https://html.duckduckgo.com/html/"

# A desktop UA avoids the empty bodies some endpoints return to blank agents.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
DEFAULT_TIMEOUT_SECONDS = 6.0
# A keyless HTML page can be large; cap what we pull into memory.
MAX_RESPONSE_BYTES = 2_000_000


class KeylessWebProvider:
    """Web search with no API key and no local service.

    News -> Google News RSS; general -> DuckDuckGo HTML. The opener is
    injectable so every flow is testable without touching the network.
    """

    def __init__(
        self,
        opener=None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        lang: str = "fr",
        region: str = "FR",
        max_results: int = 10,
        user_agent: str = DEFAULT_USER_AGENT,
    ):
        self._open = opener or urllib.request.urlopen
        self.timeout = float(timeout)
        self.lang = lang
        self.region = region
        self.max_results = max_results
        self.user_agent = user_agent

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.GENERAL,
    ) -> list[SearchResult]:
        if not isinstance(query, str) or not query.strip():
            return []
        if mode == SearchMode.NEWS:
            return self._search_news(query.strip())
        return self._search_general(query.strip())

    # -- news -------------------------------------------------------------

    def _search_news(self, query: str) -> list[SearchResult]:
        ceid = f"{self.region}:{self.lang}"
        params = urllib.parse.urlencode(
            {
                "q": query,
                "hl": f"{self.lang}-{self.region}",
                "gl": self.region,
                "ceid": ceid,
            }
        )
        body = self._fetch(f"{GOOGLE_NEWS_RSS}?{params}")
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return []

        results: list[SearchResult] = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link:
                continue
            description = item.findtext("description") or ""
            source_el = item.find("source")
            source_name = (source_el.text or "").strip() if source_el is not None else ""
            snippet = _strip_html(description)
            if source_name and source_name not in snippet:
                snippet = f"{source_name} — {snippet}" if snippet else source_name
            raw_pubdate = (item.findtext("pubDate") or "").strip() or None
            results.append(
                SearchResult(
                    title=title,
                    url=link,
                    snippet=snippet,
                    # RSS pubDate is RFC 822; expose it as ISO 8601 so the
                    # knowledge service can date and rank the article (it only
                    # parses ISO). Keep the raw value too, harmlessly.
                    published_date=_rfc822_to_iso(raw_pubdate),
                    pubdate=raw_pubdate,
                )
            )
            if len(results) >= self.max_results:
                break
        return results

    # -- general ----------------------------------------------------------

    def _search_general(self, query: str) -> list[SearchResult]:
        params = urllib.parse.urlencode({"q": query, "kl": f"{self.region.lower()}-{self.lang}"})
        try:
            body = self._fetch(f"{DUCKDUCKGO_HTML}?{params}")
        except SearXNGError:
            # General web is best effort: a blocked scrape yields no results
            # rather than taking down the whole answer.
            return []
        parser = _DuckDuckGoResultParser()
        try:
            parser.feed(body.decode("utf-8", errors="replace"))
        except Exception:
            return []
        results: list[SearchResult] = []
        for title, url, snippet in parser.results:
            if not url:
                continue
            results.append(SearchResult(title=title, url=url, snippet=snippet))
            if len(results) >= self.max_results:
                break
        return results

    # -- transport --------------------------------------------------------

    def _fetch(self, url: str) -> bytes:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": self.user_agent, "Accept-Language": f"{self.lang}"},
            method="GET",
        )
        try:
            with self._open(request, timeout=self.timeout) as response:
                return response.read(MAX_RESPONSE_BYTES)
        except (TimeoutError, socket.timeout) as error:
            raise SearXNGError("La recherche web a expire.") from error
        except urllib.error.URLError as error:
            raise SearXNGError("La source web est inaccessible.") from error


class FallbackProvider:
    """Try a primary provider (e.g. SearXNG); fall back on failure.

    A refused connection to a local SearXNG is immediate, so trying it first
    costs nothing when it is down. If every provider fails, raise SearXNGError
    so KnowledgeService reports "source unavailable" as it already does.
    """

    def __init__(self, primary, fallback):
        self.primary = primary
        self.fallback = fallback

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.GENERAL,
    ) -> list[SearchResult]:
        try:
            results = self.primary.search(query, mode=mode)
            if results:
                return results
        except Exception:
            results = []
        try:
            return self.fallback.search(query, mode=mode)
        except SearXNGError:
            raise
        except Exception as error:  # a fallback bug must not crash the session
            raise SearXNGError("Les sources web ont echoue.") from error


def _rfc822_to_iso(value: str | None) -> str | None:
    """Convert an RSS RFC 822 date (e.g. 'Wed, 15 Oct 2026 08:00:00 GMT') to
    ISO 8601, which KnowledgeService can parse. Returns None when absent or
    unparseable, so a missing date simply stays unknown."""
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return parsed.isoformat() if parsed is not None else None


def _strip_html(markup: str) -> str:
    extractor = _TextExtractor()
    try:
        extractor.feed(markup)
    except Exception:
        return ""
    return " ".join("".join(extractor.chunks).split())


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []

    def handle_data(self, data: str) -> None:
        self.chunks.append(data)


class _DuckDuckGoResultParser(HTMLParser):
    """Pull (title, url, snippet) tuples from DuckDuckGo's HTML results page.

    Result links carry class 'result__a' and a redirect href of the form
    //duckduckgo.com/l/?uddg=<encoded target>; snippets carry 'result__snippet'.
    Unknown markup is ignored, so a layout change degrades to fewer or no
    results instead of an error.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[tuple[str, str, str]] = []
        self._in_title = False
        self._in_snippet = False
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []
        self._pending_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value or "" for key, value in attrs}
        classes = attributes.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._in_title = True
            self._title_parts = []
            self._pending_url = _decode_ddg_href(attributes.get("href", ""))
        elif ("result__snippet" in classes) and tag in ("a", "div", "span"):
            self._in_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_title and tag == "a":
            self._in_title = False
            title = " ".join("".join(self._title_parts).split())
            url = self._pending_url or ""
            self.results.append((title, url, ""))
            self._pending_url = None
        elif self._in_snippet and tag in ("a", "div", "span"):
            self._in_snippet = False
            snippet = " ".join("".join(self._snippet_parts).split())
            if snippet and self.results:
                title, url, _ = self.results[-1]
                self.results[-1] = (title, url, snippet)

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self._title_parts.append(data)
        elif self._in_snippet:
            self._snippet_parts.append(data)


def _decode_ddg_href(href: str) -> str:
    if not href:
        return ""
    href = html.unescape(href)
    if href.startswith("//"):
        href = "https:" + href
    parsed = urllib.parse.urlparse(href)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg")
        if target:
            return target[0]
    return href
