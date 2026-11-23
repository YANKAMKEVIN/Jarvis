"""Live tools, family « missions » : Missions du planificateur, procédures, routines et contexte.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.context_store import ContextError
from jarvis.live.config import debug_live
from jarvis.macros import MacroError
from livekit.agents import function_tool
import asyncio


def missions_tools(self) -> dict:
    @function_tool(
        name="run_task",
        description=(
            "Confie a Jarvis une TACHE LONGUE en plusieurs etapes qui demande "
            "de chercher, verifier et enchainer plusieurs actions (par exemple : "
            "retrouve le dernier PDF telecharge, renomme-le et range-le dans "
            "Documents). La tache tourne en arriere-plan avec un planificateur "
            "local plus lent (souvent une minute) ; le resultat sera annonce a la "
            "fin. N'utilise PAS ce tool pour une demande simple ou un enchainement "
            "court que tu peux faire directement avec tes autres tools (volume, "
            "media, ouvrir une app ou un site, envoyer un message). goal : "
            "l'objectif complet et autonome, en francais. read_only=true pour une recherche sans action sur le Mac ; seuls les outils de lecture autorises seront disponibles. Sinon la mission reserve le bureau et attend son tour. Jusqu'a deux missions executent en parallele, six demandes actives maximum. Le retour contient task_id. after_id optionnel lance cette mission seulement apres le statut completed d’une mission existante ; echec, annulation ou accord vocal requis bloquent la suite sans action. Aucun resultat ni argument n’est automatiquement recopie entre missions."
        ),
    )
    @self._journaled("run_task")
    async def run_task(goal: str, read_only: bool = False, after_id: str | None = None) -> dict:
        """Start a multi-step planner task in the background."""
        debug_live(
            "tool_call",
            tool="run_task",
            goal_length=len(goal) if isinstance(goal, str) else None,
        )
        return self.tasks.start(goal, read_only=read_only, after_id=after_id)

    @function_tool(
        name="task_status",
        description=(
            "Donne l'avancement de la tache en arriere-plan (en cours, nombre "
            "d'etapes, duree) ou le resultat de la derniere tache. Utilise ce "
            "tool pour 'ou en est la tache', 'c'est bientot fini ?'. Sans task_id, liste les missions. Avec task_id, cible exactement cette mission."
        ),
    )
    async def task_status(task_id: str | None = None) -> dict:
        """Report the background task progress or last result."""
        debug_live("tool_call", tool="task_status")
        return self.tasks.status(task_id)

    @function_tool(
        name="cancel_task",
        description=(
            "Annule la tache en arriere-plan quand l'utilisateur dit stop, "
            "annule ou laisse tomber pendant qu'une tache tourne. Elle s'arrete "
            "avant l'etape suivante. Fournis task_id si plusieurs missions sont actives. Sans identifiant et avec plusieurs missions, demande laquelle annuler ; ne devine jamais."
        ),
    )
    @self._journaled("cancel_task")
    async def cancel_task(task_id: str | None = None) -> dict:
        """Request cancellation of the running background task."""
        debug_live("tool_call", tool="cancel_task")
        return self.tasks.cancel(task_id)

    @function_tool(
        name="save_task_procedure",
        description=(
            "Retient la DERNIERE tache reussie comme procedure reutilisable "
            "sous un nom (par exemple 'preparer ma reunion'), pour pouvoir "
            "dire ensuite 'refais comme d'habitude'. N'enregistre que "
            "l'enchainement des outils, jamais le contenu. Utilise ce tool "
            "quand l'utilisateur dit 'retiens cette tache' ou 'garde ca comme "
            "procedure'. S'il n'y a pas de tache reussie recente, dis-le."
        ),
    )
    @self._journaled("save_task_procedure", target_arg="name")
    async def save_task_procedure(name: str) -> dict:
        """Learn the last successful task as a named, reusable procedure."""
        debug_live("tool_call", tool="save_task_procedure")
        last = self.tasks.last_completed()
        if last is None:
            return ToolResult.failure(
                action="save_task_procedure",
                message="Aucune tache recente reussie a retenir comme procedure.",
                error_code="no_completed_task",
            ).to_livekit_dict()
        _goal, tool_names = last
        steps = [{"tool": name_, "target": None} for name_ in tool_names]
        async with self.memory_lock:
            result = await asyncio.to_thread(
                self.memory.save_procedure, name, steps, "user",
            )
        self._debug_tool_result("save_task_procedure", result)
        return result.to_livekit_dict()

    @function_tool(
        name="run_procedure",
        description=(
            "Rejoue une procedure enregistree par son nom (par exemple 'refais "
            "comme d'habitude pour preparer ma reunion'). Charge l'enchainement "
            "habituel et lance une tache en arriere-plan qui l'adapte et verifie "
            "chaque etape. Si aucune procedure ne porte ce nom, dis-le sans rien "
            "lancer."
        ),
    )
    @self._journaled("run_procedure", target_arg="name")
    async def run_procedure(name: str) -> dict:
        """Replay a saved procedure as a background task seeded by its steps."""
        debug_live("tool_call", tool="run_procedure")
        async with self.memory_lock:
            got = await asyncio.to_thread(self.memory.get_procedure, name)
        if not got.ok:
            return got.to_livekit_dict()
        steps = got.data.get("procedure", {}).get("steps") or []
        skeleton = ", ".join(
            step["tool"] for step in steps if isinstance(step, dict) and step.get("tool")
        )
        goal = (
            f"Refais la procedure habituelle « {name} ». Enchainement habituel "
            f"des outils (adapte si besoin et verifie chaque etape) : {skeleton}."
        )
        return self.tasks.start(goal)

    @function_tool(
        name="save_macro",
        description=(
            "Enregistre une MACRO : un workflow reutilisable defini a l'avance "
            "par un nom et un objectif en langage naturel ('enregistre une macro "
            "reunion : ouvre Zoom et prepare un message a l'equipe'). name : le "
            "nom court ; goal : l'objectif complet. Pour la lancer ensuite, "
            "run_macro. Differe des procedures (apprises apres une tache reussie)."
        ),
    )
    @self._journaled("save_macro", "name")
    async def save_macro(name: str, goal: str) -> dict:
        """Save a named goal macro."""
        debug_live("tool_call", tool="save_macro")
        try:
            row = await asyncio.to_thread(self.macro_store.save, name, goal)
        except MacroError as error:
            return ToolResult.failure(
                action="save_macro", message=error.message, error_code=error.code,
            ).to_livekit_dict()
        return ToolResult.success(
            action="save_macro", message=f"Macro « {row['name']} » enregistree.",
            name=row["name"],
        ).to_livekit_dict()

    @function_tool(
        name="run_macro",
        description=(
            "Lance une macro enregistree par son nom ('lance la macro reunion'). "
            "Demarre une tache en arriere-plan avec l'objectif de la macro. Si "
            "aucune macro ne porte ce nom, le dit sans rien lancer."
        ),
    )
    @self._journaled("run_macro", "name")
    async def run_macro(name: str) -> dict:
        """Run a saved macro as a background planner task."""
        debug_live("tool_call", tool="run_macro")
        macro = await asyncio.to_thread(self.macro_store.get, name)
        if macro is None:
            return ToolResult.failure(
                action="run_macro",
                message=f"Aucune macro nommee « {name} ».",
                error_code="macro_not_found",
            ).to_livekit_dict()
        return self.tasks.start(macro["goal"])

    @function_tool(
        name="list_macros",
        description="Liste les macros enregistrees (nom et objectif).",
    )
    async def list_macros() -> dict:
        """List saved macros."""
        debug_live("tool_call", tool="list_macros")
        rows = await asyncio.to_thread(self.macro_store.list)
        macros = [{"name": r["name"], "goal": r["goal"]} for r in rows]
        return ToolResult.success(
            action="list_macros", message=f"{len(macros)} macro(s) enregistree(s).",
            macros=macros, count=len(macros),
        ).to_livekit_dict()

    @function_tool(
        name="delete_macro",
        description="Supprime une macro enregistree par son nom.",
    )
    @self._journaled("delete_macro", "name")
    async def delete_macro(name: str) -> dict:
        """Delete a saved macro."""
        debug_live("tool_call", tool="delete_macro")
        deleted = await asyncio.to_thread(self.macro_store.delete, name)
        if not deleted:
            return ToolResult.failure(
                action="delete_macro", message=f"Aucune macro nommee « {name} ».",
                error_code="macro_not_found",
            ).to_livekit_dict()
        return ToolResult.success(
            action="delete_macro", message=f"Macro « {name} » supprimee.", name=name,
        ).to_livekit_dict()

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
    @self._journaled("remember_context")
    async def remember_context(text: str) -> dict:
        """Record a rolling conversation-context note."""
        debug_live("tool_call", tool="remember_context")
        try:
            row = await asyncio.to_thread(self.context_store.add, text)
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
        rows = await asyncio.to_thread(self.context_store.recent)
        entries = [r["text"] for r in rows]
        if entries:
            message = "Voici ou on en etait : " + " ; ".join(entries)
        else:
            message = "Je n'ai pas encore de contexte recent enregistre."
        return ToolResult.success(
            action="recall_context", message=message, context=entries, count=len(entries),
        ).to_livekit_dict()

    return {
        "run_task": run_task,
        "task_status": task_status,
        "cancel_task": cancel_task,
        "save_task_procedure": save_task_procedure,
        "run_procedure": run_procedure,
        "save_macro": save_macro,
        "run_macro": run_macro,
        "list_macros": list_macros,
        "delete_macro": delete_macro,
        "remember_context": remember_context,
        "recall_context": recall_context,
    }
