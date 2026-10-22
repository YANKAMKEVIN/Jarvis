"""Web knowledge for the voice session: search + synthesize, as a ToolResult.

Thin wrapper over the existing KnowledgeService (SearXNG / keyless search +
local synthesis). Read-only: it never acts on the Mac and never sends anything,
so it needs no confirmation. "Verify, don't assume" maps here to
state_confirmed = did we actually retrieve web data, so the voice layer never
states facts it did not get.
"""

from __future__ import annotations

from jarvis.capabilities.results import ToolResult


class KnowledgeCapability:
    def __init__(self, service):
        self.service = service

    def answer(self, question: str) -> ToolResult:
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure(
                action="web_answer",
                message="La question de recherche est vide.",
                error_code="invalid_question",
            )

        try:
            answer = self.service.answer(question.strip())
        except Exception:
            return ToolResult.failure(
                action="web_answer",
                message="La recherche web a échoué. Réessayez dans un instant.",
                error_code="system_error",
            )

        sources = [
            {"title": source.title, "url": source.url}
            for source in getattr(answer, "sources", [])
        ]
        retrieved = bool(getattr(answer, "external_knowledge_retrieved", False))

        return ToolResult.success(
            action="web_answer",
            message=getattr(answer, "message", "") or "",
            sources=sources,
            source_count=len(sources),
            external_knowledge_retrieved=retrieved,
            # The command (search) ran; the state (real web data) is confirmed
            # only when the source actually returned something.
            state_confirmed=retrieved,
            search_status=getattr(answer, "failure_reason", None) or "answered",
        )


def web_announcement_for(result: ToolResult) -> str:
    """Instructions for the voice model to speak a finished web search."""
    message = (result.message or "").strip()

    if result.data.get("search_status") == "synthesis_failed":
        return (
            "Des sources ont été récupérées, mais leur synthèse a échoué. "
            f"Explique cette limite sans inventer de réponse : « {message} »"
        )

    if not result.ok or not result.data.get("external_knowledge_retrieved"):
        return (
            "La recherche web n'a pas abouti. "
            f"Dis-le brievement a l'utilisateur, sans inventer d'information : « {message} » "
            "Propose de reessayer plus tard."
        )

    count = result.data.get("source_count", 0)
    return (
        "La recherche web est terminee. Transmets ce resultat a l'utilisateur en une a "
        "trois phrases, sans rien ajouter qui n'y figure pas et sans lire d'URL a voix "
        f"haute : « {message} » "
        f"Tu t'appuies sur {count} source(s) web. "
        "Ensuite, en une courte phrase, propose d'aller plus loin (creuser un point ou "
        "lui preparer un recap a envoyer), sans le faire sans son accord."
    )
