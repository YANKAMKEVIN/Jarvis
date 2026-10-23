import json
import socket
import urllib.error
import urllib.parse
import urllib.request

from jarvis.config import SEARXNG_BASE_URL, SEARXNG_TIMEOUT_SECONDS
from jarvis.knowledge.models import SearchMode, SearchResult


class SearXNGError(Exception):
    pass


class SearXNGProvider:
    def __init__(
        self,
        base_url: str = SEARXNG_BASE_URL,
        timeout: float = SEARXNG_TIMEOUT_SECONDS,
        urlopen=urllib.request.urlopen,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.urlopen = urlopen

    def build_search_url(
        self,
        query: str,
        mode: SearchMode = SearchMode.GENERAL,
    ) -> str:
        query_params = {
            "q": query,
            "format": "json",
        }

        if mode == SearchMode.NEWS:
            query_params["categories"] = "news"

        params = urllib.parse.urlencode(query_params)
        return f"{self.base_url}/search?{params}"

    def search(
        self,
        query: str,
        mode: SearchMode = SearchMode.GENERAL,
    ) -> list[SearchResult]:
        request = urllib.request.Request(
            self.build_search_url(query, mode=mode),
            headers={"Accept": "application/json"},
            method="GET",
        )

        try:
            with self.urlopen(request, timeout=self.timeout) as response:
                status = response.getcode()

                if status != 200:
                    raise SearXNGError(
                        f"SearXNG a retourne le statut HTTP {status}."
                    )

                raw_body = response.read()
        except (TimeoutError, socket.timeout) as error:
            raise SearXNGError("La recherche SearXNG a expire.") from error
        except urllib.error.URLError as error:
            raise SearXNGError("SearXNG est inaccessible.") from error

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise SearXNGError("La reponse SearXNG est invalide.") from error

        results = payload.get("results") if isinstance(payload, dict) else None

        if not isinstance(results, list):
            raise SearXNGError("La reponse SearXNG ne contient pas de resultats.")

        return [
            self._parse_result(item)
            for item in results
            if isinstance(item, dict)
        ]

    @staticmethod
    def _parse_result(item: dict) -> SearchResult:
        engines = item.get("engines") or []

        if not isinstance(engines, list):
            engines = []

        return SearchResult(
            title=str(item.get("title") or "").strip(),
            url=str(item.get("url") or "").strip(),
            snippet=str(item.get("content") or "").strip(),
            published_date=item.get("publishedDate"),
            pubdate=item.get("pubdate"),
            engines=[
                str(engine)
                for engine in engines
                if engine is not None
            ],
            score=item.get("score"),
        )
