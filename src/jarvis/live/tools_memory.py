"""Live tools, family « memory » : Mémoire et journal.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def memory_tools(self) -> dict:
    @function_tool(
        name="remember",
        description=(
            "Enregistre un souvenir durable UNIQUEMENT quand l'utilisateur "
            "demande explicitement de retenir quelque chose (souviens-toi, "
            "retiens, note que...). kind : profile (infos sur l'utilisateur), "
            "person (subject = surnom ou relation comme 'ma mere', content = "
            "nom exact du contact dans les apps ; si le nom differe selon "
            "l'app, subject = 'ma mere sur Telegram'), preference (subject = "
            "domaine comme 'musique', content = la preference, par exemple "
            "'Spotify' ou 'Apple Music'), fact (autre "
            "information utile). Un souvenir de meme kind et subject est mis "
            "a jour. Pour une information que tu as seulement deduite, "
            "utilise propose_memory. Les secrets sont toujours refuses."
        ),
    )
    @self._journaled("remember")
    async def remember(kind: str, subject: str, content: str) -> dict:
        """Store an explicitly requested long-term memory."""
        debug_live("tool_call", tool="remember", kind=kind)
        async with self.memory_lock:
            result = await asyncio.to_thread(
                self.memory.remember, kind, subject, content, "user",
            )
        self._debug_tool_result("remember", result)
        return result.to_livekit_dict()

    @function_tool(
        name="propose_memory",
        description=(
            "Propose de retenir une information que tu as DEDUITE sans que "
            "l'utilisateur demande de la retenir (par exemple il corrige deux "
            "fois le meme nom de contact). N'enregistre rien : renvoie un "
            "token et requires_confirmation. Demande alors a l'utilisateur, "
            "en une phrase, s'il veut que tu retiennes cette information ; "
            "seulement apres un oui clair, appelle confirm_action(token). "
            "Sinon cancel_action(token). Memes kind que remember."
        ),
    )
    async def propose_memory(kind: str, subject: str, content: str) -> dict:
        """Register an inferred memory that is stored only on confirmation."""
        debug_live("tool_call", tool="propose_memory", kind=kind)
        refusal = self.memory.check_proposal(kind, subject, content)
        if refusal is not None:
            return refusal.to_livekit_dict()

        def _executor():
            return self.memory.remember(kind, subject, content, "inferred")

        async with self.confirmation_lock:
            token = self.pending_actions.register("remember_inferred", _executor)

        return ToolResult.success(
            action="propose_memory",
            message=(
                "Rien n'est enregistré. Demande à l'utilisateur s'il veut que "
                "tu retiennes cette information, puis confirm_action ou "
                "cancel_action."
            ),
            requires_confirmation=True,
            token=token,
        ).to_livekit_dict()

    @function_tool(
        name="recall",
        description=(
            "Cherche dans la memoire durable de l'utilisateur (profil, "
            "personnes, preferences, faits). Utilise ce tool quand "
            "l'utilisateur pose une question sur ce qu'il t'a demande de "
            "retenir, ou quand une information personnelle manque pour "
            "repondre (par exemple le nom de son dentiste). kind optionnel "
            "pour filtrer. Ne reponds jamais 'je ne sais pas' sur un sujet "
            "personnel sans avoir appele recall."
        ),
    )
    async def recall(query: str, kind: str | None = None) -> dict:
        """Search long-term memory."""
        debug_live("tool_call", tool="recall", kind=kind)
        async with self.memory_lock:
            result = await asyncio.to_thread(self.memory.recall, query, kind)
        self._debug_tool_result("recall", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_memories",
        description=(
            "Liste les souvenirs enregistres, eventuellement filtres par kind. "
            "Utilise ce tool pour 'qu'est-ce que tu sais sur moi' ou 'quels "
            "contacts tu connais'."
        ),
    )
    async def list_memories(kind: str | None = None) -> dict:
        """List stored memories."""
        debug_live("tool_call", tool="list_memories", kind=kind)
        async with self.memory_lock:
            result = await asyncio.to_thread(self.memory.list_memories, kind)
        self._debug_tool_result("list_memories", result)
        return result.to_livekit_dict()

    @function_tool(
        name="forget",
        description=(
            "Oublie definitivement un souvenir quand l'utilisateur le demande "
            "(oublie que..., efface ce que tu sais sur...). Fournis memory_id "
            "si tu le connais, sinon query. Si ambiguous_memory est retourne, "
            "rien n'est efface : presente les candidats et demande lequel."
        ),
    )
    @self._journaled("forget")
    async def forget(memory_id: int | None = None, query: str | None = None) -> dict:
        """Delete one memory by id or unambiguous query."""
        debug_live("tool_call", tool="forget", memory_id=memory_id)
        async with self.memory_lock:
            result = await asyncio.to_thread(self.memory.forget, memory_id, query)
        self._debug_tool_result("forget", result)
        return result.to_livekit_dict()

    @function_tool(
        name="recent_activity",
        description=(
            "Relit le journal des dernieres actions realisees par Jarvis "
            "(ouvrir une app, changer le volume, preparer ou envoyer un "
            "message, ouvrir un site...), avec l'heure et le resultat. Le "
            "journal ne contient jamais le texte des messages ni le contenu "
            "manipule. Utilise ce tool pour 'qu'est-ce que tu as fait', "
            "'tu as bien envoye le message ?' ou 'refais comme tout a l'heure'."
        ),
    )
    async def recent_activity(limit: int = 10) -> dict:
        """Read the most recent journaled actions."""
        debug_live("tool_call", tool="recent_activity", limit=limit)
        async with self.memory_lock:
            result = await asyncio.to_thread(self.memory.recent_activity, limit)
        self._debug_tool_result("recent_activity", result)
        return result.to_livekit_dict()

    @function_tool(
        name="recent_missions",
        description=(
            "Liste les dernieres missions en arriere-plan (run_task) avec leur "
            "objectif, leur statut final (terminee, echec, annulee...) et "
            "l'heure. Contrairement a task_status qui ne voit que la session "
            "en cours, cet historique est conserve localement et SURVIT a un "
            "redemarrage de Jarvis. Utilise ce tool pour 'quelles etaient mes "
            "dernieres missions', 'qu'est-ce que tu as lance tout a l'heure', "
            "'la mission d'hier a-t-elle abouti'."
        ),
    )
    async def recent_missions(limit: int = 10) -> dict:
        """Read the most recent persisted missions (survives restarts)."""
        debug_live("tool_call", tool="recent_missions", limit=limit)
        async with self.memory_lock:
            result = await asyncio.to_thread(self.memory.recent_missions, limit)
        self._debug_tool_result("recent_missions", result)
        return result.to_livekit_dict()

    return {
        "remember": remember,
        "propose_memory": propose_memory,
        "recall": recall,
        "list_memories": list_memories,
        "forget": forget,
        "recent_activity": recent_activity,
        "recent_missions": recent_missions,
    }
