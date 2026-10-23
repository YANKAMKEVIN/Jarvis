import os
import re
import time
import unicodedata
import urllib.parse
from datetime import date, datetime, timedelta

from jarvis.knowledge.models import (
    KnowledgeAnswer,
    SearchMode,
    SearchResult,
    SourceType,
    SourceReference,
    TemporalStatus,
)
from jarvis.knowledge.searxng import SearXNGError, SearXNGProvider


class KnowledgeService:
    STOP_WORDS = {
        "actualite",
        "actualites",
        "aujourd",
        "hui",
        "cette",
        "dans",
        "dernier",
        "derniere",
        "dernieres",
        "des",
        "du",
        "est",
        "les",
        "nouvelles",
        "principales",
        "principal",
        "principaux",
        "que",
        "quel",
        "quelle",
        "quelles",
        "quels",
        "quoi",
        "semaine",
        "sont",
        "sur",
        "une",
        "voir",
    }
    TOPIC_ALIASES = {
        "intelligence artificielle": {"ia", "ai"},
    }

    def __init__(
        self,
        brain,
        provider=None,
        max_results: int = 5,
        today=date.today,
        now=datetime.now,
    ):
        self.brain = brain
        self.provider = (
            provider
            if provider is not None
            else SearXNGProvider()
        )
        self.max_results = max_results
        self.today = today
        self.now = now

    def answer(self, question: str) -> KnowledgeAnswer:
        total_start = time.perf_counter()
        timings = {}
        mode = self.detect_search_mode(question)
        current_date = self.today() if mode == SearchMode.NEWS else None

        selected = []
        unavailable = False
        for query, attempt_mode in self._search_attempts(question, mode):
            search_start = time.perf_counter()
            try:
                results = self.provider.search(query, mode=attempt_mode)
            except SearXNGError:
                unavailable = True
                continue
            finally:
                timings["search"] = timings.get("search", 0) + time.perf_counter() - search_start
            source_start = time.perf_counter()
            selected = self._select_results(results, mode=attempt_mode, question=question)
            timings["source_processing"] = timings.get("source_processing", 0) + time.perf_counter() - source_start
            if selected:
                mode = attempt_mode
                current_date = self.today() if mode == SearchMode.NEWS else None
                break

        if not selected:
            timings["total"] = time.perf_counter() - total_start
            self._debug_perf(timings)
            return KnowledgeAnswer(
                "Mes sources de recherche sont inaccessibles ou n’ont pas fourni de résultats exploitables."
                if unavailable else "Mes recherches n’ont renvoyé aucun résultat exploitable pour cette demande.",
                failure_reason="unavailable" if unavailable else "no_results",
            )

        if mode == SearchMode.NEWS:
            self._assign_temporal_statuses(selected, current_date)

        try:
            llm_start = time.perf_counter()
            message = self.brain.answer_from_sources(
                question,
                selected,
                search_mode=mode,
                current_date=current_date,
            )
            if not isinstance(message, str) or not message.strip():
                raise ValueError("Empty synthesis")
            timings["llm"] = time.perf_counter() - llm_start
        except Exception:
            timings["llm"] = time.perf_counter() - llm_start
            timings["total"] = time.perf_counter() - total_start
            self._debug_perf(timings)
            return KnowledgeAnswer(
                "Je n'arrive pas à synthétiser les informations récupérées pour le moment.",
                sources=self._source_references(selected),
                external_knowledge_retrieved=True,
                failure_reason="synthesis_failed",
            )

        timings["total"] = time.perf_counter() - total_start
        self._debug_perf(timings)

        return KnowledgeAnswer(
            message=message,
            sources=self._source_references(selected),
            external_knowledge_retrieved=True,
        )

    def _debug_perf(self, timings: dict) -> None:
        if os.environ.get("JARVIS_DEBUG_PERF") != "1":
            return

        metrics = getattr(self.brain, "last_ollama_metrics", {}) or {}

        print("============== JARVIS PERF ==============")
        print(f"SearXNG search       : {timings.get('search', 0):.2f} s")
        print(
            "Source processing    : "
            f"{timings.get('source_processing', 0):.2f} s"
        )
        print(f"LLM                  : {timings.get('llm', 0):.2f} s")
        print(f"Knowledge total      : {timings.get('total', 0):.2f} s")

        if metrics:
            print()
            print("Ollama:")
            self._print_duration_metric(metrics, "load_duration", "load")
            self._print_duration_metric(
                metrics,
                "prompt_eval_duration",
                "prompt eval",
            )
            self._print_duration_metric(metrics, "eval_duration", "generation")
            self._print_duration_metric(metrics, "total_duration", "total")

            if "prompt_eval_count" in metrics:
                print(f"prompt tokens        : {metrics['prompt_eval_count']}")

            if "eval_count" in metrics:
                print(f"generated tokens     : {metrics['eval_count']}")

        print("=========================================")

    @staticmethod
    def _print_duration_metric(
        metrics: dict,
        key: str,
        label: str,
    ) -> None:
        if key not in metrics:
            return

        value = metrics[key]

        try:
            seconds = float(value) / 1_000_000_000
        except (TypeError, ValueError):
            return

        print(f"{label:<21}: {seconds:.2f} s")

    def _select_results(
        self,
        results: list[SearchResult],
        mode: SearchMode = SearchMode.GENERAL,
        question: str = "",
    ) -> list[SearchResult]:
        if mode == SearchMode.NEWS:
            self._normalize_temporal_metadata(results)
            results = self._prioritize_news_results(results, question)

        selected = []
        seen_urls = set()

        for result in results:
            url = result.url.strip()

            try:
                parsed = urllib.parse.urlparse(url)
            except ValueError:
                continue
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or url in seen_urls:
                continue

            has_title = bool(result.title.strip())
            has_snippet = bool(result.snippet.strip())

            if not has_title and not has_snippet:
                continue

            selected.append(result)
            seen_urls.add(url)

            if len(selected) >= self.max_results:
                break

        self._assign_source_types(selected)

        return selected

    @classmethod
    def _search_attempts(cls, question, mode):
        """At most three distinct requests. Never synthesize without retrieved data."""
        compact = re.sub(
            r"^(?:donne[ -]moi|donne|peux[- ]tu me donner|cherche|recherche|trouve)\s+(?:(?:des|les)\s+)?(?:(?:infos|informations)\s+)?(?:sur\s+)?",
            "", question.strip(), flags=re.IGNORECASE,
        ).strip()
        alternate = SearchMode.GENERAL if mode == SearchMode.NEWS else SearchMode.NEWS
        attempts = [(question, mode), (compact, mode), (compact, alternate)]
        return list(dict.fromkeys(attempts))[:3]

    @classmethod
    def detect_search_mode(cls, question: str) -> SearchMode:
        normalized = cls._normalize(question)

        news_patterns = [
            r"\bactualites?\b",
            r"\bdernieres? nouvelles?\b",
            r"\bnouvelles?\b.*\b(?:semaine|jour|aujourd hui|tech|apple|ia|intelligence artificielle)\b",
            r"\bquoi de neuf\b",
            r"\bque s est il passe\b",
        ]

        if any(re.search(pattern, normalized) for pattern in news_patterns):
            return SearchMode.NEWS

        # Historical and explanatory sports questions are not live-score requests.
        historical = re.search(r"\b(?:19|20)\d{2}\b", normalized)
        explanatory = re.search(r"\b(?:comment|regles|format|histoire|definition)\b", normalized)
        sport = re.search(r"\b(?:wnba|nba|nfl|wimbledon|roland garros|ligue 1|tour de france)\b", normalized)
        event = re.search(r"\b(?:finale|playoffs|resultats?|score|classement|match)\b", normalized)
        if sport and event and not historical and not explanatory:
            return SearchMode.NEWS
        if sport and re.search(r"\bnouvelles\b", normalized) and not historical:
            return SearchMode.NEWS
        return SearchMode.GENERAL

    @classmethod
    def _prioritize_news_results(
        cls,
        results: list[SearchResult],
        question: str = "",
    ) -> list[SearchResult]:
        if not results:
            return []

        useful_results = [
            result
            for result in results
            if result.url.strip()
            and (
                result.title.strip()
                or result.snippet.strip()
            )
        ]

        article_like = [
            result
            for result in useful_results
            if not cls._looks_like_generic_section(result)
        ]

        candidates = article_like or useful_results
        topics = cls._extract_topic_terms(question)
        relevant_candidates = [
            result
            for result in candidates
            if cls._relevance_score(result, topics) > 0
        ]

        if len(relevant_candidates) >= min(2, cls._default_max_results()):
            candidates = relevant_candidates

        return sorted(
            candidates,
            key=lambda result: cls._news_rank(result, topics),
            reverse=True,
        )

    @classmethod
    def _news_rank(
        cls,
        result: SearchResult,
        topics: list[set[str]] | None = None,
    ) -> tuple[int, int, int, float]:
        normalized = result.normalized_datetime
        dated = 1 if normalized else 0
        timestamp = normalized.timestamp() if normalized else 0
        article_like = (
            0
            if cls._looks_like_generic_section(result)
            else 1
        )

        try:
            score = float(result.score or 0)
        except (TypeError, ValueError):
            score = 0.0

        return (
            cls._relevance_score(result, topics or []),
            int(timestamp) if dated else 0,
            article_like,
            score,
        )

    @classmethod
    def _extract_topic_terms(cls, question: str) -> list[set[str]]:
        normalized = cls._normalize(question)
        topics: list[set[str]] = []

        for phrase, aliases in cls.TOPIC_ALIASES.items():
            phrase_normalized = cls._normalize(phrase)
            alias_matches = {
                alias
                for alias in aliases
                if cls._contains_term(normalized, alias)
            }

            if phrase_normalized in normalized or alias_matches:
                topics.append({phrase_normalized, *aliases})

        for token in normalized.split():
            if token in cls.STOP_WORDS or len(token) <= 2:
                continue

            if any(token in group for group in topics):
                continue

            topics.append({token})

        return topics

    @classmethod
    def _relevance_score(
        cls,
        result: SearchResult,
        topics: list[set[str]],
    ) -> int:
        if not topics:
            return 0

        title = cls._normalize(result.title)
        snippet = cls._normalize(result.snippet)
        score = 0

        for topic_group in topics:
            title_match = any(
                cls._contains_term(title, topic)
                for topic in topic_group
            )
            snippet_match = any(
                cls._contains_term(snippet, topic)
                for topic in topic_group
            )

            if title_match:
                score += 6
            elif snippet_match:
                score += 2

        return score

    @staticmethod
    def _contains_term(text: str, term: str) -> bool:
        if " " in term:
            return term in text

        return re.search(rf"\b{re.escape(term)}\b", text) is not None

    @staticmethod
    def _default_max_results() -> int:
        return 5

    def _normalize_temporal_metadata(
        self,
        results: list[SearchResult],
    ) -> None:
        for result in results:
            result.normalized_datetime = self._normalize_result_datetime(result)

    def _normalize_result_datetime(
        self,
        result: SearchResult,
    ) -> datetime | None:
        return (
            self._parse_absolute_datetime(result.published_date)
            or self._parse_absolute_datetime(result.pubdate)
            or self._parse_relative_datetime(result.pubdate)
        )

    @staticmethod
    def _parse_absolute_datetime(value: str | None) -> datetime | None:
        if not value:
            return None

        text = str(value).strip()

        for date_format in (
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
        ):
            try:
                return datetime.strptime(text, date_format)
            except ValueError:
                pass

        if text.endswith("Z"):
            try:
                return datetime.fromisoformat(
                    text[:-1] + "+00:00"
                )
            except ValueError:
                return None

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _parse_relative_datetime(
        self,
        value: str | None,
    ) -> datetime | None:
        if not value:
            return None

        match = re.fullmatch(
            r"\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago\s*",
            str(value).lower(),
        )

        if not match:
            return None

        amount = int(match.group(1))
        unit = match.group(2)

        if unit.startswith("minute"):
            delta = timedelta(minutes=amount)
        elif unit.startswith("hour"):
            delta = timedelta(hours=amount)
        else:
            delta = timedelta(days=amount)

        return self.now() - delta

    @staticmethod
    def _assign_temporal_statuses(
        results: list[SearchResult],
        current_date: date | None,
    ) -> None:
        yesterday = (
            current_date - timedelta(days=1)
            if current_date is not None
            else None
        )

        for result in results:
            if result.normalized_datetime is None:
                result.temporal_status = TemporalStatus.UNKNOWN
                continue

            if current_date is None:
                result.temporal_status = TemporalStatus.RECENT
                continue

            result_date = result.normalized_datetime.date()

            if result_date == current_date:
                result.temporal_status = TemporalStatus.TODAY
            elif result_date == yesterday:
                result.temporal_status = TemporalStatus.YESTERDAY
            else:
                result.temporal_status = TemporalStatus.RECENT

    @classmethod
    def _assign_source_types(cls, results: list[SearchResult]) -> None:
        for result in results:
            result.source_type = cls._classify_source_type(result.url)

    @staticmethod
    def _classify_source_type(url: str) -> SourceType:
        hostname = urllib.parse.urlparse(url).hostname or ""
        hostname = hostname.lower()

        if hostname.startswith("www."):
            hostname = hostname[4:]

        official_domains = {
            "elysee.fr",
            "gouvernement.fr",
            "info.gouv.fr",
            "service-public.fr",
        }

        if hostname in official_domains or any(
            hostname.endswith(f".{domain}")
            for domain in official_domains
        ):
            return SourceType.OFFICIAL

        if hostname == "wikipedia.org" or hostname.endswith(".wikipedia.org"):
            return SourceType.REFERENCE

        news_markers = (
            "news.",
            "lemonde.fr",
            "lefigaro.fr",
            "france24.com",
            "bbc.com",
            "reuters.com",
        )

        if hostname.startswith(news_markers) or hostname in news_markers:
            return SourceType.NEWS

        return SourceType.OTHER

    @staticmethod
    def _looks_like_generic_section(result: SearchResult) -> bool:
        if result.published_date:
            return False

        parsed = urllib.parse.urlparse(result.url)
        path = parsed.path.rstrip("/").lower()
        title = KnowledgeService._normalize(result.title)

        section_markers = (
            "/tag/",
            "/tags/",
            "/topic/",
            "/topics/",
            "/rubrique/",
            "/dossier/",
            "/category/",
            "/categories/",
        )

        if any(marker in path for marker in section_markers):
            return True

        last_segment = path.rsplit("/", 1)[-1]

        broad_titles = {
            "actualite intelligence artificielle",
            "actualites intelligence artificielle",
            "intelligence artificielle",
        }

        if last_segment in {
            "actualite",
            "actualites",
            "ai",
            "ia",
            "intelligence-artificielle",
            "tech",
            "technologie",
        }:
            return title in broad_titles

        return title in broad_titles

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.lower()
        text = "".join(
            char
            for char in unicodedata.normalize("NFD", text)
            if unicodedata.category(char) != "Mn"
        )
        text = re.sub(r"[^a-z0-9àâçéèêëîïôûùüÿñæœ\s']", " ", text)
        text = text.replace("'", " ")
        return " ".join(text.split())

    @staticmethod
    def _source_references(
        results: list[SearchResult],
    ) -> list[SourceReference]:
        return [
            SourceReference(
                title=result.title or result.url,
                url=result.url,
            )
            for result in results
        ]
