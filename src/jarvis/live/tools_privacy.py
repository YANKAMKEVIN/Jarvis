"""Live tools, family « privacy » : Vie privée et mode sécurité.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.activity import default_store as default_activity_store
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from jarvis.live.productivity import checklist_store
from livekit.agents import function_tool
import asyncio


def privacy_tools(self) -> dict:
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
        async with self.memory_lock:
            mem = await asyncio.to_thread(self.memory.list_memories)
            act = await asyncio.to_thread(self.memory.recent_activity, 50)
            missions = await asyncio.to_thread(self.memory.recent_missions, 100)
        scheduled = await asyncio.to_thread(self.schedule_store.list, "pending")
        reminders = await asyncio.to_thread(self.reminder_store.list, "pending")
        checklists_count = 0
        store = checklist_store(self)
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
                f"{activity_count} action(s) récente(s) au journal ; "
                f"{mission_count} mission(s) dans l'historique ; {checklists_count} checklist(s) locale(s) ; "
                f"{tool_calls} appel(s) d'outil au journal d'activité (noms seulement)."
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
    @self._journaled("clear_personal_data", "scope")
    async def clear_personal_data(scope: str = "all") -> dict:
        """Prepare a confirmed purge of the data Jarvis stores."""
        debug_live("tool_call", tool="clear_personal_data", scope=scope)
        choice = (scope or "all").strip().lower()
        if choice not in ("context", "reminders", "scheduled", "checklists", "missions", "activity", "all"):
            return ToolResult.failure(
                action="clear_personal_data",
                message="scope doit être context, reminders, scheduled, checklists, missions, activity ou all.",
                error_code="invalid_scope",
            ).to_livekit_dict()

        def _executor():
            return self._purge_personal_data(choice)

        async with self.confirmation_lock:
            token = self.pending_actions.register("clear_personal_data", _executor)
        return ToolResult.success(
            action="clear_personal_data",
            message=(
                f"Effacement à confirmer ({choice}). Annonce ce qui sera effacé, "
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
    @self._journaled("enable_safe_mode")
    async def enable_safe_mode() -> dict:
        """Turn on session safe (read-only) mode."""
        debug_live("tool_call", tool="enable_safe_mode")
        already = self.read_only_mode
        self.read_only_mode = True
        return ToolResult.success(
            action="enable_safe_mode",
            message=(
                "Mode sécurité déjà actif." if already else
                "Mode sécurité activé : je reste en lecture seule et ne "
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
    @self._journaled("disable_safe_mode")
    async def disable_safe_mode() -> dict:
        """Turn off session safe (read-only) mode."""
        debug_live("tool_call", tool="disable_safe_mode")
        already = not self.read_only_mode
        self.read_only_mode = False
        return ToolResult.success(
            action="disable_safe_mode",
            message=(
                "Le mode sécurité n'était pas actif." if already else
                "Mode sécurité désactivé : je peux de nouveau agir sur le Mac "
                "et préparer des envois, toujours avec les confirmations "
                "habituelles."
            ),
            read_only_mode=False,
            state_confirmed=True,
        ).to_livekit_dict()

    return {
        "privacy_overview": privacy_overview,
        "clear_personal_data": clear_personal_data,
        "enable_safe_mode": enable_safe_mode,
        "disable_safe_mode": disable_safe_mode,
    }
