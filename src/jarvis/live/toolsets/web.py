"""Web knowledge tools (background search, URL summary, briefing).

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
    @function_tool(
        name="search_the_web",
        description=(
            "Cherche une information a jour sur le web et la synthetise a voix "
            "haute : actualites, meteo, prix, cours, resultats, 'qui est', 'quelles "
            "sont les nouvelles', 'quoi de neuf sur X'. La recherche tourne en "
            "arriere-plan (quelques secondes) ; des que tu appelles ce tool, dis a "
            "l'utilisateur que tu regardes, puis le resultat sera annonce tout seul. "
            "Si l'utilisateur ne precise pas de domaine pour 'les nouvelles', ne "
            "bloque pas : prends les grands titres a la une et propose d'affiner. "
            "N'utilise pas ce tool pour agir sur le Mac ni pour une question dont la "
            "reponse ne depend pas d'une information actuelle. question : la question "
            "complete en francais."
        ),
    )
    @registry._journaled("search_the_web")
    async def search_the_web(question: str) -> dict:
        """Start a background web search; its result is announced by voice."""
        debug_live(
            "tool_call",
            tool="search_the_web",
            question_length=len(question) if isinstance(question, str) else None,
        )
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure(
                action="search_the_web",
                message="La question de recherche est vide.",
                error_code="invalid_question",
            ).to_livekit_dict()
        if registry._web_running():
            return ToolResult.failure(
                action="search_the_web",
                message="Une recherche web est deja en cours ; attends son resultat.",
                error_code="web_search_running",
            ).to_livekit_dict()
        registry._web_task = asyncio.get_running_loop().create_task(
            registry._run_web_search(question.strip())
        )
        return ToolResult.success(
            action="search_the_web",
            message=(
                "Recherche lancee. Dis simplement a l'utilisateur que tu regardes ; "
                "le resultat sera annonce dans un instant."
            ),
            search_started=True,
        ).to_livekit_dict()

    @function_tool(
        name="summarize_url",
        description=(
            "Lit une page web dont l'utilisateur donne l'adresse et la resume ou "
            "repond a une question a son sujet : 'resume cette page', 'que dit "
            "cet article sur ...'. url : l'adresse http/https ; question : une "
            "demande precise optionnelle. N'utilise que des URL fournies par "
            "l'utilisateur."
        ),
    )
    @registry._journaled("summarize_url")
    async def summarize_url(url: str, question: str | None = None) -> dict:
        """Fetch a user-provided URL and summarize/answer from its content."""
        debug_live("tool_call", tool="summarize_url")
        result = await asyncio.to_thread(registry.webread.summarize_url, url, question)
        registry._debug_tool_result("summarize_url", result)
        return result.to_livekit_dict()

    @function_tool(
        name="morning_briefing",
        description=(
            "Prepare un point du jour parle : la date, un apercu de l'agenda et "
            "les principales actualites. Pour 'fais-moi le point', 'briefing du "
            "matin', 'quoi de neuf aujourd'hui'. Tourne en arriere-plan : des que "
            "tu l'appelles, dis que tu prepares le point ; le resultat sera "
            "annonce tout seul. topic : theme d'actualite optionnel."
        ),
    )
    @registry._journaled("morning_briefing")
    async def morning_briefing(topic: str | None = None) -> dict:
        """Start a background briefing (date + agenda + news), announced by voice."""
        debug_live("tool_call", tool="morning_briefing")
        if registry._briefing_running():
            return ToolResult.failure(
                action="morning_briefing",
                message="Un briefing est deja en cours de preparation.",
                error_code="briefing_running",
            ).to_livekit_dict()
        registry._briefing_task = asyncio.get_running_loop().create_task(
            registry._run_briefing(topic)
        )
        return ToolResult.success(
            action="morning_briefing",
            message=(
                "Briefing en preparation. Dis a l'utilisateur que tu prepares le "
                "point du jour ; le resultat sera annonce dans un instant."
            ),
            briefing_started=True,
        ).to_livekit_dict()

    @function_tool(
        name="web_answer",
        description=(
            "Recherche une information a jour sur le web et renvoie une reponse "
            "synthetisee avec ses sources. Outil reserve aux taches longues : il "
            "BLOQUE le temps de la recherche (quelques secondes). Appuie-toi "
            "uniquement sur sa reponse et ses sources, n'invente rien. question : "
            "la question complete en francais."
        ),
    )
    @registry._journaled("web_answer")
    async def web_answer(question: str) -> dict:
        """Blocking web search for the planner (not exposed to the voice model)."""
        debug_live(
            "tool_call",
            tool="web_answer",
            question_length=len(question) if isinstance(question, str) else None,
        )
        result = await asyncio.to_thread(registry.knowledge.answer, question)
        return result.to_livekit_dict()

    return {
        "search_the_web": search_the_web,
        "summarize_url": summarize_url,
        "morning_briefing": morning_briefing,
        "web_answer": web_answer,
    }
