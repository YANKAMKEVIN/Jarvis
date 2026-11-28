"""Memory, activity, personal context, privacy and safe-mode tools.

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.activity import default_store as default_activity_store
from jarvis.capabilities.results import ToolResult
from jarvis.context_store import ContextError
from jarvis.live.config import debug_live
from jarvis.live.productivity import checklist_store

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
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
    @registry._journaled("remember")
    async def remember(kind: str, subject: str, content: str) -> dict:
        """Store an explicitly requested long-term memory."""
        debug_live("tool_call", tool="remember", kind=kind)
        async with registry.memory_lock:
            result = await asyncio.to_thread(
                registry.memory.remember, kind, subject, content, "user",
            )
        registry._debug_tool_result("remember", result)
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
        refusal = registry.memory.check_proposal(kind, subject, content)
        if refusal is not None:
            return refusal.to_livekit_dict()

        def _executor():
            return registry.memory.remember(kind, subject, content, "inferred")

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("remember_inferred", _executor)

        return ToolResult.success(
            action="propose_memory",
            message=(
                "Rien n'est enregistre. Demande a l'utilisateur s'il veut que "
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
        async with registry.memory_lock:
            result = await asyncio.to_thread(registry.memory.recall, query, kind)
        registry._debug_tool_result("recall", result)
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
        async with registry.memory_lock:
            result = await asyncio.to_thread(registry.memory.list_memories, kind)
        registry._debug_tool_result("list_memories", result)
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
    @registry._journaled("forget")
    async def forget(memory_id: int | None = None, query: str | None = None) -> dict:
        """Delete one memory by id or unambiguous query."""
        debug_live("tool_call", tool="forget", memory_id=memory_id)
        async with registry.memory_lock:
            result = await asyncio.to_thread(registry.memory.forget, memory_id, query)
        registry._debug_tool_result("forget", result)
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
        async with registry.memory_lock:
            result = await asyncio.to_thread(registry.memory.recent_activity, limit)
        registry._debug_tool_result("recent_activity", result)
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
        async with registry.memory_lock:
            result = await asyncio.to_thread(registry.memory.recent_missions, limit)
        registry._debug_tool_result("recent_missions", result)
        return result.to_livekit_dict()

    @function_tool(
        name="remember_context",
        description=(
            "Note en une phrase ce sur quoi vous travaillez, pour pouvoir "
            "reprendre plus tard, meme dans une autre session ('retiens ou on "
            "en est', ou de toi-meme a un point d'etape). text : un court resume "
            "de l'etat d'avancement. Different de remember (faits durables) et "
            "de save_note (notes dictees)."
        ),
    )
    @registry._journaled("remember_context")
    async def remember_context(text: str) -> dict:
        """Record a rolling conversation-context note."""
        debug_live("tool_call", tool="remember_context")
        try:
            row = await asyncio.to_thread(registry.context_store.add, text)
        except ContextError as error:
            return ToolResult.failure(
                action="remember_context", message=error.message, error_code=error.code,
            ).to_livekit_dict()
        return ToolResult.success(
            action="remember_context", message="Contexte retenu.", context_id=row["id"],
        ).to_livekit_dict()

    @function_tool(
        name="recall_context",
        description=(
            "Rappelle ce sur quoi vous travailliez recemment, pour reprendre le "
            "fil ('reprends ou on en etait', 'on faisait quoi deja'). Renvoie les "
            "dernieres notes de contexte."
        ),
    )
    async def recall_context() -> dict:
        """Return recent conversation-context notes."""
        debug_live("tool_call", tool="recall_context")
        rows = await asyncio.to_thread(registry.context_store.recent)
        entries = [r["text"] for r in rows]
        if entries:
            message = "Voici ou on en etait : " + " ; ".join(entries)
        else:
            message = "Je n'ai pas encore de contexte recent enregistre."
        return ToolResult.success(
            action="recall_context", message=message, context=entries, count=len(entries),
        ).to_livekit_dict()

    @function_tool(
        name="privacy_overview",
        description=(
            "Donne un apercu de ce que Jarvis garde sur l'utilisateur : nombre "
            "de souvenirs, d'actions recentes au journal, de messages planifies "
            "et de rappels en attente. Pour 'qu'est-ce que tu sais sur moi', "
            "'qu'est-ce que tu gardes'. Pour voir le detail, utilise "
            "list_memories, list_scheduled_messages, list_reminders ou "
            "recent_activity ; pour effacer, forget."
        ),
    )
    async def privacy_overview() -> dict:
        """Aggregate what Jarvis stores, read-only."""
        debug_live("tool_call", tool="privacy_overview")
        async with registry.memory_lock:
            mem = await asyncio.to_thread(registry.memory.list_memories)
            act = await asyncio.to_thread(registry.memory.recent_activity, 50)
            missions = await asyncio.to_thread(registry.memory.recent_missions, 100)
        scheduled = await asyncio.to_thread(registry.schedule_store.list, "pending")
        reminders = await asyncio.to_thread(registry.reminder_store.list, "pending")
        checklists_count = 0
        store = checklist_store(registry)
        if store.path.exists():
            overview = await asyncio.to_thread(store.manage, 'list')
            checklists_count = len(overview.data.get('lists', [])) if overview.ok else 0
        memory_count = mem.data.get("count", 0) if mem.ok else 0
        activity_count = len(act.data.get("episodes", [])) if act.ok else 0
        mission_count = missions.data.get("count", 0) if missions.ok else 0
        try:
            journal = default_activity_store()
            tool_calls = await asyncio.to_thread(journal.count, "tool")
        except Exception:
            tool_calls = 0
        return ToolResult.success(
            action="privacy_overview",
            message=(
                f"Je garde {memory_count} souvenir(s), {len(scheduled)} message(s) "
                f"planifie(s) et {len(reminders)} rappel(s) en attente ; "
                f"{activity_count} action(s) recente(s) au journal ; "
                f"{mission_count} mission(s) dans l'historique ; {checklists_count} checklist(s) locale(s) ; "
                f"{tool_calls} appel(s) d'outil au journal d'activite (noms seulement)."
            ),
            memory_count=memory_count,
            activity_count=activity_count,
            mission_count=mission_count,
            tool_call_count=tool_calls,
            scheduled_count=len(scheduled),
            reminder_count=len(reminders),
            checklists_count=checklists_count,
        ).to_livekit_dict()

    @function_tool(
        name="clear_personal_data",
        description=(
            "EFFACE des donnees que Jarvis garde, apres confirmation. scope : "
            "'context' (notes de contexte de conversation), 'reminders' (rappels "
            "en attente), 'scheduled' (messages planifies en attente), 'missions' "
            "(historique des missions), 'activity' (journal des outils, reveils et alertes "
            "du tableau de bord), ou 'all' (ces donnees et les checklists). "
            "scope checklists efface uniquement les checklists. Renvoie un token et requires_confirmation : annonce ce "
            "qui sera efface, puis confirm_action seulement sur un oui clair. Pour "
            "effacer un souvenir precis, utilise plutot forget."
        ),
    )
    @registry._journaled("clear_personal_data", "scope")
    async def clear_personal_data(scope: str = "all") -> dict:
        """Prepare a confirmed purge of the data Jarvis stores."""
        debug_live("tool_call", tool="clear_personal_data", scope=scope)
        choice = (scope or "all").strip().lower()
        if choice not in ("context", "reminders", "scheduled", "checklists", "missions", "activity", "all"):
            return ToolResult.failure(
                action="clear_personal_data",
                message="scope doit etre context, reminders, scheduled, checklists, missions, activity ou all.",
                error_code="invalid_scope",
            ).to_livekit_dict()

        def _executor():
            return registry._purge_personal_data(choice)

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("clear_personal_data", _executor)
        return ToolResult.success(
            action="clear_personal_data",
            message=(
                f"Effacement a confirmer ({choice}). Annonce ce qui sera efface, "
                "puis attends la confirmation avant confirm_action."
            ),
            requires_confirmation=True,
            token=token,
            scope=choice,
        ).to_livekit_dict()

    @function_tool(
        name="enable_safe_mode",
        description=(
            "Active le mode securite (lecture seule) pour la session : Jarvis "
            "peut encore lire, chercher, analyser, prendre des notes et gerer "
            "ses propres rappels, mais toute action qui modifie le Mac ou "
            "envoie quelque chose vers l'exterieur (ouvrir/fermer une app, "
            "fichiers, presse-papiers, clavier/souris, mail, agenda, messages, "
            "navigation web, confirmation d'action, effacement) est bloquee. "
            "Utilise ce tool quand l'utilisateur demande 'passe en mode "
            "securite', 'mode lecture seule', 'ne touche a rien', 'mode sur'."
        ),
    )
    @registry._journaled("enable_safe_mode")
    async def enable_safe_mode() -> dict:
        """Turn on session safe (read-only) mode."""
        debug_live("tool_call", tool="enable_safe_mode")
        already = registry.read_only_mode
        registry.read_only_mode = True
        return ToolResult.success(
            action="enable_safe_mode",
            message=(
                "Mode securite deja actif." if already else
                "Mode securite active : je reste en lecture seule et ne "
                "modifie rien ni n'envoie rien tant qu'il est actif."
            ),
            read_only_mode=True,
            state_confirmed=True,
        ).to_livekit_dict()

    @function_tool(
        name="disable_safe_mode",
        description=(
            "Desactive le mode securite (lecture seule) et redonne a Jarvis "
            "l'acces complet a ses actions. Utilise ce tool quand l'utilisateur "
            "demande 'quitte le mode securite', 'reactive tout', 'desactive la "
            "lecture seule'."
        ),
    )
    @registry._journaled("disable_safe_mode")
    async def disable_safe_mode() -> dict:
        """Turn off session safe (read-only) mode."""
        debug_live("tool_call", tool="disable_safe_mode")
        already = not registry.read_only_mode
        registry.read_only_mode = False
        return ToolResult.success(
            action="disable_safe_mode",
            message=(
                "Le mode securite n'etait pas actif." if already else
                "Mode securite desactive : je peux de nouveau agir sur le Mac "
                "et preparer des envois, toujours avec les confirmations "
                "habituelles."
            ),
            read_only_mode=False,
            state_confirmed=True,
        ).to_livekit_dict()

    return {
        "remember": remember,
        "propose_memory": propose_memory,
        "recall": recall,
        "list_memories": list_memories,
        "forget": forget,
        "recent_activity": recent_activity,
        "recent_missions": recent_missions,
        "remember_context": remember_context,
        "recall_context": recall_context,
        "privacy_overview": privacy_overview,
        "clear_personal_data": clear_personal_data,
        "enable_safe_mode": enable_safe_mode,
        "disable_safe_mode": disable_safe_mode,
    }
