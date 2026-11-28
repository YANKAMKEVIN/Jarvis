"""Token usage, machine activity and Claude session tools.

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
        name="token_usage",
        description=(
            "Rapporte la consommation de tokens de Claude Code sur une periode, "
            "lue en local : 'combien de tokens j'ai consomme', 'ma conso cette "
            "semaine'. period : 'today', 'yesterday', '7d', '30d', '90d' ou 'all'. "
            "Donne les tokens generes, en entree et lus en cache. Aucune donnee "
            "ne quitte la machine."
        ),
    )
    async def token_usage(period: str = "7d") -> dict:
        """Report local Claude Code token consumption for a period."""
        debug_live("tool_call", tool="token_usage", period=period)
        result = await asyncio.to_thread(registry.usage.overview, period)
        registry._debug_tool_result("token_usage", result)
        return result.to_livekit_dict()

    @function_tool(
        name="token_usage_by_model",
        description=(
            "Repartit la consommation de tokens par modele (Opus, Sonnet...) sur "
            "une periode : 'ma conso par modele', 'quel modele consomme le plus'. "
            "period : 'today', '7d', '30d', '90d', 'all'. Inclut un cout estime "
            "equivalent API (indicatif ; l'abonnement n'est pas facture au token)."
        ),
    )
    async def token_usage_by_model(period: str = "30d") -> dict:
        """Break token usage down by model."""
        debug_live("tool_call", tool="token_usage_by_model", period=period)
        result = await asyncio.to_thread(registry.usage.by_model, period)
        registry._debug_tool_result("token_usage_by_model", result)
        return result.to_livekit_dict()

    @function_tool(
        name="token_usage_by_project",
        description=(
            "Repartit la consommation de tokens par projet (dossier de travail) "
            "sur une periode : 'ma conso par projet', 'sur quel projet je consomme "
            "le plus'. period : 'today', '7d', '30d', 'all' ; limit : nombre de "
            "projets a remonter."
        ),
    )
    async def token_usage_by_project(period: str = "30d", limit: int = 5) -> dict:
        """Break token usage down by project folder."""
        debug_live("tool_call", tool="token_usage_by_project", period=period, limit=limit)
        result = await asyncio.to_thread(registry.usage.by_project, period, limit)
        registry._debug_tool_result("token_usage_by_project", result)
        return result.to_livekit_dict()

    @function_tool(
        name="token_usage_trend",
        description=(
            "Donne la serie quotidienne de consommation de tokens pour tracer une "
            "courbe dans le temps : 'montre l'evolution de ma conso', 'un graphe "
            "sur deux semaines'. days : nombre de jours (2 a 120)."
        ),
    )
    async def token_usage_trend(days: int = 14) -> dict:
        """Daily token-usage series for charting."""
        debug_live("tool_call", tool="token_usage_trend", days=days)
        result = await asyncio.to_thread(registry.usage.trend, days)
        registry._debug_tool_result("token_usage_trend", result)
        return result.to_livekit_dict()

    @function_tool(
        name="compare_token_usage",
        description=(
            "Compare la consommation de tokens d'une periode avec la periode "
            "equivalente juste avant : 'est-ce que je consomme plus que la semaine "
            "derniere', 'compare ma conso'. period : '7d', '30d', '90d'."
        ),
    )
    async def compare_token_usage(period: str = "7d") -> dict:
        """Compare a period's token usage with the preceding equal window."""
        debug_live("tool_call", tool="compare_token_usage", period=period)
        result = await asyncio.to_thread(registry.usage.compare, period)
        registry._debug_tool_result("compare_token_usage", result)
        return result.to_livekit_dict()

    @function_tool(
        name="recent_claude_sessions",
        description=(
            "Liste tes dernieres sessions Claude Code avec, pour chacune, le "
            "projet, les tokens et un cout estime : 'mes dernieres sessions "
            "Claude', 'combien m'a coute ma derniere session'. Lecture locale. "
            "limit : nombre de sessions a remonter."
        ),
    )
    async def recent_claude_sessions(limit: int = 5) -> dict:
        """Recent Claude Code sessions with per-session tokens and cost."""
        debug_live("tool_call", tool="recent_claude_sessions", limit=limit)
        result = await asyncio.to_thread(registry.usage.recent_sessions, limit)
        registry._debug_tool_result("recent_claude_sessions", result)
        return result.to_livekit_dict()

    @function_tool(
        name="system_snapshot",
        description=(
            "Donne l'etat machine en direct : charge processeur, memoire, disque "
            "et batterie. 'comment va mon Mac', 'ma conso CPU la', 'il me reste "
            "combien de memoire'. Lecture locale instantanee."
        ),
    )
    async def system_snapshot() -> dict:
        """Live CPU/memory/disk/battery snapshot."""
        debug_live("tool_call", tool="system_snapshot")
        result = await asyncio.to_thread(registry.system_metrics.snapshot)
        registry._debug_tool_result("system_snapshot", result)
        return result.to_livekit_dict()

    @function_tool(
        name="top_processes",
        description=(
            "Liste les processus les plus gourmands du Mac : 'qu'est-ce qui "
            "bouffe mon CPU', 'quelle appli prend toute la memoire'. by : 'cpu' "
            "ou 'memory' ; limit : nombre de processus."
        ),
    )
    async def top_processes(by: str = "cpu", limit: int = 5) -> dict:
        """Heaviest processes by CPU or memory."""
        debug_live("tool_call", tool="top_processes", by=by, limit=limit)
        result = await asyncio.to_thread(registry.system_metrics.top_processes, by, limit)
        registry._debug_tool_result("top_processes", result)
        return result.to_livekit_dict()

    @function_tool(
        name="system_usage_history",
        description=(
            "Historique d'utilisation machine pour tracer une courbe dans le "
            "temps : 'l'evolution de mon CPU', 'un graphe de ma memoire sur la "
            "journee'. metric : 'cpu', 'memoire', 'disque', 'charge', 'batterie' ; "
            "period : '1h', '6h', '24h', '7d'. L'historique se remplit tant que "
            "Jarvis tourne."
        ),
    )
    async def system_usage_history(metric: str = "cpu", period: str = "24h") -> dict:
        """Bucketed machine-metric history for charting."""
        debug_live("tool_call", tool="system_usage_history", metric=metric, period=period)
        result = await asyncio.to_thread(registry.system_metrics.history, metric, period)
        registry._debug_tool_result("system_usage_history", result)
        return result.to_livekit_dict()

    @function_tool(
        name="check_anomalies",
        description=(
            "Verifie s'il se passe quelque chose d'anormal : processeur ou "
            "memoire satures depuis quelques minutes, disque presque plein, "
            "consommation de tokens Claude tres au-dessus de la normale du jour. "
            "'il y a un souci sur mon Mac', 'quelque chose d'anormal', 'pourquoi "
            "ca rame'. Lecture locale, rien ne quitte la machine."
        ),
    )
    async def check_anomalies() -> dict:
        """Explainable anomaly check over machine metrics and token usage."""
        debug_live("tool_call", tool="check_anomalies")
        result = await asyncio.to_thread(registry.insights.check)
        registry._debug_tool_result("check_anomalies", result)
        return result.to_livekit_dict()

    @function_tool(
        name="run_claude_task",
        description=(
            "Lance une session Claude Code EN TACHE DE FOND pour une consigne "
            "precise, recupere la reponse et la lit : 'demande a Claude de ...', "
            "'lance une session Claude pour ...'. prompt : la consigne ; "
            "directory : dossier de travail (optionnel, defaut : dossier "
            "personnel). Action consequente : renvoie un token et "
            "requires_confirmation. Annonce la consigne et le dossier, puis "
            "attends l'accord avant confirm_action. Rien n'est lance sans "
            "confirmation."
        ),
    )
    @registry._journaled("run_claude_task")
    # The schema exposes ``directory`` as a string defaulting to null; kept as-is.
    async def run_claude_task(
        prompt: str, directory: str = None,  # type: ignore[assignment]
    ) -> dict:
        """Prepare a one-shot Claude Code task (confirmation required)."""
        debug_live("tool_call", tool="run_claude_task",
                   prompt_length=len(prompt) if isinstance(prompt, str) else None)
        if not isinstance(prompt, str) or not prompt.strip():
            return ToolResult.failure("run_claude_task",
                                      "La consigne pour Claude est vide.",
                                      "invalid_prompt").to_livekit_dict()
        if not registry.claude_sessions.available():
            return ToolResult.failure("run_claude_task",
                                      "Le CLI claude est introuvable.",
                                      "claude_missing").to_livekit_dict()

        def _executor():
            return registry.claude_sessions.run_task(prompt, directory)

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("run_claude_task", _executor)
        return ToolResult.success(
            "run_claude_task",
            "Tache Claude a confirmer. Annonce la consigne et le dossier, "
            "puis attends la confirmation avant confirm_action.",
            requires_confirmation=True, token=token,
            prompt=prompt.strip()[:160],
            directory=registry.claude_sessions.resolve_directory(directory),
        ).to_livekit_dict()

    @function_tool(
        name="open_claude_session",
        description=(
            "Ouvre une session Claude Code INTERACTIVE dans une fenetre Terminal "
            "pour que l'utilisateur la pilote lui-meme : 'ouvre une session "
            "Claude', 'lance Claude dans le Terminal'. directory : dossier de "
            "travail (optionnel). Action consequente : renvoie un token et "
            "requires_confirmation. Annonce le dossier puis attends l'accord "
            "avant confirm_action."
        ),
    )
    @registry._journaled("open_claude_session")
    # The schema exposes ``directory`` as a string defaulting to null; kept as-is.
    async def open_claude_session(
        directory: str = None,  # type: ignore[assignment]
    ) -> dict:
        """Prepare opening an interactive Claude session (confirmation required)."""
        debug_live("tool_call", tool="open_claude_session")
        if not registry.claude_sessions.available():
            return ToolResult.failure("open_claude_session",
                                      "Le CLI claude est introuvable.",
                                      "claude_missing").to_livekit_dict()

        def _executor():
            return registry.claude_sessions.open_session(directory)

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("open_claude_session", _executor)
        return ToolResult.success(
            "open_claude_session",
            "Ouverture de session Claude a confirmer. Annonce le dossier puis "
            "attends la confirmation avant confirm_action.",
            requires_confirmation=True, token=token,
            directory=registry.claude_sessions.resolve_directory(directory),
        ).to_livekit_dict()

    return {
        "token_usage": token_usage,
        "token_usage_by_model": token_usage_by_model,
        "token_usage_by_project": token_usage_by_project,
        "token_usage_trend": token_usage_trend,
        "compare_token_usage": compare_token_usage,
        "recent_claude_sessions": recent_claude_sessions,
        "system_snapshot": system_snapshot,
        "top_processes": top_processes,
        "system_usage_history": system_usage_history,
        "check_anomalies": check_anomalies,
        "run_claude_task": run_claude_task,
        "open_claude_session": open_claude_session,
    }
