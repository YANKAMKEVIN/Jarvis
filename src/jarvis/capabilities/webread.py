"""Summarize a web page the user points to (fetch + local model).

Reads the page text with the keyless fetcher and answers/summarizes strictly
from that content via the free planner model. The URL comes from the user; this
never follows links found in other content.
"""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult
from jarvis.knowledge.searxng import SearXNGError


_SYSTEM = (
    "Tu resumes ou reponds a partir UNIQUEMENT du contenu de la page fourni. "
    "Si l'information demandee n'y est pas, dis-le sans inventer. Reste concis, "
    "pour une reponse vocale. Reponds en francais si la demande est en francais."
)


class WebReadCapability:
    def __init__(self, fetcher=None, model=None):
        self._fetcher = fetcher
        self._model = model

    def _get_fetcher(self):
        if self._fetcher is None:
            from jarvis.knowledge.keyless import KeylessWebProvider

            self._fetcher = KeylessWebProvider()
        return self._fetcher

    def _get_model(self):
        if self._model is None:
            from jarvis.planner.models import build_planner_model

            self._model = build_planner_model()
        return self._model

    def summarize_url(self, url: str, question: str | None = None) -> ToolResult:
        try:
            text = self._get_fetcher().fetch_text(url)
        except SearXNGError as error:
            return ToolResult.failure(
                action="summarize_url", message=str(error), error_code="fetch_failed",
            )
        except Exception as error:
            return ToolResult.failure(
                action="summarize_url", message=f"Lecture de la page impossible : {error}",
                error_code="fetch_failed",
            )
        if not text.strip():
            return ToolResult.failure(
                action="summarize_url",
                message="La page ne contient pas de texte lisible.",
                error_code="empty_page",
            )

        ask = question.strip() if isinstance(question, str) and question.strip() else (
            "Resume cette page en quelques phrases."
        )
        messages = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Demande : {ask}\n\nContenu de la page :\n{text}"},
        ]
        try:
            turn = self._get_model().complete(messages, [])
        except Exception as error:
            return ToolResult.failure(
                action="summarize_url", message=f"La synthese a echoue : {error}",
                error_code="model_error",
            )
        answer = (turn.text or "").strip()
        if not answer:
            return ToolResult.failure(
                action="summarize_url", message="Le modele n'a pas renvoye de reponse.",
                error_code="empty_result",
            )
        return ToolResult.success(action="summarize_url", message=answer, url=url.strip())
