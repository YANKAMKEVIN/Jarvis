"""Live tools, family « insights » : Consommation de tokens, métriques machine et sessions Claude.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def insights_tools(self) -> dict:
    @function_tool(
        name="token_usage",
        description=(
            "Rapporte la consommation de tokens de Claude Code sur une periode, "
            "lue en local : 'combien de tokens j'ai consomme', 'ma conso cette "
            "semaine'. period : 'today', 'yesterday', '7d', '30d', '90d' ou 'all'. "
            "Donne les tokens generes, en entree et lus en cache. Aucune donnee "
            "ne quitte la machine. Par modele : token_usage_by_model ; par "
            "projet : token_usage_by_project ; dans le temps : "
            "compare_token_usage. Un cout eventuel est une estimation "
            "equivalent API : l'abonnement n'est pas facture au token."
        ),
    )
    async def token_usage(period: str = "7d") -> dict:
        """Report local Claude Code token consumption for a period."""
        debug_live("tool_call", tool="token_usage", period=period)
        result = await asyncio.to_thread(self.usage.overview, period)
        self._debug_tool_result("token_usage", result)
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
        result = await asyncio.to_thread(self.usage.by_model, period)
        self._debug_tool_result("token_usage_by_model", result)
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
        result = await asyncio.to_thread(self.usage.by_project, period, limit)
        self._debug_tool_result("token_usage_by_project", result)
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
        result = await asyncio.to_thread(self.usage.trend, days)
        self._debug_tool_result("token_usage_trend", result)
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
        result = await asyncio.to_thread(self.usage.compare, period)
        self._debug_tool_result("compare_token_usage", result)
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
        result = await asyncio.to_thread(self.usage.recent_sessions, limit)
        self._debug_tool_result("recent_claude_sessions", result)
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
        result = await asyncio.to_thread(self.system_metrics.snapshot)
        self._debug_tool_result("system_snapshot", result)
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
        result = await asyncio.to_thread(self.system_metrics.top_processes, by, limit)
        self._debug_tool_result("top_processes", result)
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
        result = await asyncio.to_thread(self.system_metrics.history, metric, period)
        self._debug_tool_result("system_usage_history", result)
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
        result = await asyncio.to_thread(self.insights.check)
        self._debug_tool_result("check_anomalies", result)
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
            "confirmation, et c'est refuse en mode securite. Pour une fenetre "
            "Terminal interactive, utilise open_claude_session."
        ),
    )
    @self._journaled("run_claude_task")
    async def run_claude_task(prompt: str, directory: str = None) -> dict:
        """Prepare a one-shot Claude Code task (confirmation required)."""
        debug_live("tool_call", tool="run_claude_task",
                   prompt_length=len(prompt) if isinstance(prompt, str) else None)
        if not isinstance(prompt, str) or not prompt.strip():
            return ToolResult.failure("run_claude_task",
                                      "La consigne pour Claude est vide.",
                                      "invalid_prompt").to_livekit_dict()
        if not self.claude_sessions.available():
            return ToolResult.failure("run_claude_task",
                                      "Le CLI claude est introuvable.",
                                      "claude_missing").to_livekit_dict()

        def _executor():
            return self.claude_sessions.run_task(prompt, directory)

        async with self.confirmation_lock:
            token = self.pending_actions.register("run_claude_task", _executor)
        return ToolResult.success(
            "run_claude_task",
            "Tache Claude a confirmer. Annonce la consigne et le dossier, "
            "puis attends la confirmation avant confirm_action.",
            requires_confirmation=True, token=token,
            prompt=prompt.strip()[:160],
            directory=self.claude_sessions.resolve_directory(directory),
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
    @self._journaled("open_claude_session")
    async def open_claude_session(directory: str = None) -> dict:
        """Prepare opening an interactive Claude session (confirmation required)."""
        debug_live("tool_call", tool="open_claude_session")
        if not self.claude_sessions.available():
            return ToolResult.failure("open_claude_session",
                                      "Le CLI claude est introuvable.",
                                      "claude_missing").to_livekit_dict()

        def _executor():
            return self.claude_sessions.open_session(directory)

        async with self.confirmation_lock:
            token = self.pending_actions.register("open_claude_session", _executor)
        return ToolResult.success(
            "open_claude_session",
            "Ouverture de session Claude a confirmer. Annonce le dossier puis "
            "attends la confirmation avant confirm_action.",
            requires_confirmation=True, token=token,
            directory=self.claude_sessions.resolve_directory(directory),
        ).to_livekit_dict()

    @function_tool(
        name="draft_email",
        description=(
            "Cree un BROUILLON de mail dans Apple Mail (NON envoye) : "
            "'prepare un mail a ...', 'ecris un brouillon de reponse'. Le "
            "brouillon est enregistre dans Mail pour que l'utilisateur le relise "
            "et l'envoie lui-meme ; rien n'est envoye. recipient : adresse email ; "
            "subject : objet ; body : contenu."
        ),
    )
    @self._journaled("draft_email")
    @self._desktop_access
    async def draft_email(recipient: str, subject: str, body: str) -> dict:
        """Create an unsent Apple Mail draft."""
        debug_live("tool_call", tool="draft_email", body_length=len(body) if isinstance(body, str) else None)
        result = await asyncio.to_thread(self.mail.create_draft, recipient, subject, body)
        self._debug_tool_result("draft_email", result)
        return result.to_livekit_dict()

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
        "draft_email": draft_email,
    }
