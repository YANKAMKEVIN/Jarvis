"""Live tools, family « system » : Système, son, applications, média et raccourcis.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def system_tools(self) -> dict:
    # The avatar on screen IS Jarvis: results are worded so the model says
    # "je danse", never that a command or request was sent to something else.
    @function_tool(name="dance_avatar", description="Te fait danser toi-même, Jarvis, à l'écran pendant huit secondes, quand l'utilisateur te demande de danser ou si tu sais danser. stop=True arrête ta danse, sans couper le vocal. Aucune musique. Si les animations sont réduites ou ton apparence est abstraite, l'écran l'indique.")
    async def dance_avatar(stop: bool = False) -> dict:
        observer = self.presentation_observer
        if observer is None:
            return {"ok": False, "error": "desktop_unavailable",
                    "message": "Tu ne peux pas danser ici : ton avatar n'est pas affiché. Dis-le simplement, à la première personne."}
        observer({"type": "avatar_dance", "action": "stop" if stop else "start"})
        if stop:
            return {"ok": True, "status": "stopped",
                    "message": "Tu t'arrêtes de danser. Dis-le en quelques mots, à la première personne."}
        return {"ok": True, "status": "dancing",
                "message": "Tu danses maintenant, pendant huit secondes. Dis-le tout de suite à la première personne, avec une phrase courte et joueuse (« Et je danse ! »). Ne parle ni de commande, ni de demande, ni de compagnon."}

    @function_tool(
        name="set_volume",
        description=(
            "Modifie réellement le volume de sortie du Mac de l'utilisateur. "
            "Utilise ce tool quand l'utilisateur demande de mettre, régler, "
            "monter ou baisser le volume à un niveau précis entre 0 et 100."
        ),
    )
    @self._journaled("set_volume")
    async def set_volume(volume: int) -> dict:
        """Set the Mac output volume to a value between 0 and 100."""
        debug_live("tool_call", tool="set_volume", volume=volume)
        result = await asyncio.to_thread(self.audio.set_volume, volume)

        if result.ok:
            debug_live(
                "tool_succeeded",
                tool="set_volume",
                volume=result.data.get("volume"),
            )
        else:
            debug_live(
                "tool_failed",
                tool="set_volume",
                error=result.error_code,
            )

        return result.to_livekit_dict()

    @function_tool(
        name="get_volume",
        description=(
            "Lit le volume de sortie actuel du Mac de l'utilisateur. "
            "Utilise ce tool quand l'utilisateur demande le volume actuel."
        ),
    )
    async def get_volume() -> dict:
        """Read the current Mac output volume."""
        debug_live("tool_call", tool="get_volume")
        result = await asyncio.to_thread(self.audio.get_volume)

        if result.ok:
            debug_live(
                "tool_succeeded",
                tool="get_volume",
                volume=result.data.get("volume"),
            )
        else:
            debug_live(
                "tool_failed",
                tool="get_volume",
                error=result.error_code,
            )

        return result.to_livekit_dict()

    @function_tool(
        name="open_app",
        description=(
            "Ouvre réellement une application macOS par son nom exact. "
            "Utilise ce tool quand l'utilisateur demande d'ouvrir, lancer "
            "ou démarrer une application comme Safari, Spotify ou "
            "Visual Studio Code."
        ),
    )
    @self._journaled("open_app", "app_name")
    @self._desktop_access
    async def open_app(app_name: str) -> dict:
        """Open a macOS application by name."""
        debug_live("tool_call", tool="open_app", app_name=app_name)
        result = await asyncio.to_thread(self.apps.open_app, app_name)

        if result.ok:
            debug_live(
                "tool_succeeded",
                tool="open_app",
                target=result.data.get("target"),
            )
        else:
            debug_live(
                "tool_failed",
                tool="open_app",
                error=result.error_code,
            )

        return result.to_livekit_dict()

    @function_tool(
        name="close_app",
        description=(
            "Ferme réellement une application macOS par son nom exact. "
            "Utilise ce tool quand l'utilisateur demande de fermer, "
            "quitter ou arrêter une application."
        ),
    )
    @self._journaled("close_app", "app_name")
    @self._desktop_access
    async def close_app(app_name: str) -> dict:
        """Close a macOS application by name."""
        debug_live("tool_call", tool="close_app", app_name=app_name)
        result = await asyncio.to_thread(self.apps.close_app, app_name)

        if result.ok:
            debug_live(
                "tool_succeeded",
                tool="close_app",
                target=result.data.get("target"),
            )
        else:
            debug_live(
                "tool_failed",
                tool="close_app",
                error=result.error_code,
            )

        return result.to_livekit_dict()

    @function_tool(
        name="is_app_running",
        description=(
            "Vérifie si une application macOS est actuellement ouverte "
            "ou en cours d'exécution. Utilise ce tool quand l'utilisateur "
            "demande si une application est ouverte, lancée ou tourne."
        ),
    )
    async def is_app_running(app_name: str) -> dict:
        """Check whether a macOS application is currently running."""
        debug_live("tool_call", tool="is_app_running", app_name=app_name)
        result = await asyncio.to_thread(
            self.apps.is_app_running,
            app_name,
        )

        if result.ok:
            debug_live(
                "tool_succeeded",
                tool="is_app_running",
                target=result.data.get("target"),
                running=result.data.get("running"),
            )
        else:
            debug_live(
                "tool_failed",
                tool="is_app_running",
                error=result.error_code,
            )

        return result.to_livekit_dict()

    @function_tool(
        name="play_pause",
        description=(
            "Met en pause ou reprend la lecture du média actif compatible "
            "sur le Mac. Utilise ce tool pour les demandes comme pause, "
            "reprends la lecture, play ou mets la musique en pause."
        ),
    )
    @self._journaled("play_pause")
    @self._desktop_access
    async def play_pause() -> dict:
        """Toggle play/pause for the active supported media app."""
        debug_live("tool_call", tool="play_pause")
        async with self.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await self._preferred_media_app()
            result = await (
                asyncio.to_thread(self.media.play_pause, preferred)
                if preferred
                else asyncio.to_thread(self.media.play_pause)
            )
        self._debug_tool_result("play_pause", result)
        return result.to_livekit_dict()

    @function_tool(
        name="next_track",
        description=(
            "Passe au morceau suivant dans l'application média compatible "
            "active. Utilise ce tool quand l'utilisateur demande la "
            "suivante, le titre suivant ou de passer au prochain morceau."
        ),
    )
    @self._journaled("next_track")
    @self._desktop_access
    async def next_track() -> dict:
        """Skip to the next track in the active supported media app."""
        debug_live("tool_call", tool="next_track")
        async with self.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await self._preferred_media_app()
            result = await (
                asyncio.to_thread(self.media.next_track, preferred)
                if preferred
                else asyncio.to_thread(self.media.next_track)
            )
        self._debug_tool_result("next_track", result)
        return result.to_livekit_dict()

    @function_tool(
        name="previous_track",
        description=(
            "Revient au morceau précédent dans l'application média "
            "compatible active. Utilise ce tool quand l'utilisateur "
            "demande la chanson précédente ou de revenir en arrière."
        ),
    )
    @self._journaled("previous_track")
    @self._desktop_access
    async def previous_track() -> dict:
        """Go back to the previous track in the active supported media app."""
        debug_live("tool_call", tool="previous_track")
        async with self.media_lock:
            # Inside the lock so concurrent media calls keep their order.
            preferred = await self._preferred_media_app()
            result = await (
                asyncio.to_thread(self.media.previous_track, preferred)
                if preferred
                else asyncio.to_thread(self.media.previous_track)
            )
        self._debug_tool_result("previous_track", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_media_state",
        description=(
            "Lit l'état réel du média actif compatible sur le Mac. "
            "Utilise ce tool quand l'utilisateur demande ce qui joue, "
            "quel morceau est en cours ou si la lecture est active."
        ),
    )
    async def get_media_state() -> dict:
        """Read the current supported media playback state."""
        debug_live("tool_call", tool="get_media_state")
        async with self.media_lock:
            result = await asyncio.to_thread(self.media.get_media_state)
        self._debug_tool_result("get_media_state", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_battery_status",
        description=(
            "Lit l'etat reel de la batterie du Mac : pourcentage, charge "
            "en cours et alimentation secteur."
        ),
    )
    async def get_battery_status() -> dict:
        """Read the current Mac battery status."""
        debug_live("tool_call", tool="get_battery_status")
        result = await asyncio.to_thread(self.system.get_battery_status)
        self._debug_tool_result("get_battery_status", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_system_info",
        description=(
            "Lit les informations materielles reelles du Mac utilise, "
            "comme le modele, l'identifiant modele, la puce et la memoire."
        ),
    )
    async def get_system_info() -> dict:
        """Read current Mac hardware information."""
        debug_live("tool_call", tool="get_system_info")
        result = await asyncio.to_thread(self.system.get_system_info)
        self._debug_tool_result("get_system_info", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_storage_status",
        description=(
            "Lit l'espace disque reel du Mac (libre, utilise, total) et signale "
            "si l'espace est faible. Utilise ce tool pour 'combien de place il me "
            "reste', 'mon disque est-il plein'."
        ),
    )
    async def get_storage_status() -> dict:
        """Read current disk space."""
        debug_live("tool_call", tool="get_storage_status")
        result = await asyncio.to_thread(self.system.get_storage_status)
        self._debug_tool_result("get_storage_status", result)
        return result.to_livekit_dict()

    @function_tool(
        name="self_check",
        description=(
            "Diagnostic : indique quelles capacites et permissions sont "
            "disponibles (accessibilite, enregistrement d'ecran, vision, modele "
            "local Ollama, IMAP) et ce qui manque, avec une piste de correction. "
            "Pour 'fais un check', 'qu'est-ce qui fonctionne', 'tes permissions'."
        ),
    )
    async def self_check() -> dict:
        """Report available capabilities and permissions."""
        debug_live("tool_call", tool="self_check")
        result = await asyncio.to_thread(self.diagnostics.self_check)
        return result.to_livekit_dict()

    @function_tool(
        name="run_shortcut",
        description=(
            "Lance un Raccourci (Shortcuts) macOS par son nom : 'active Ne pas "
            "deranger', 'lance mon raccourci Focus travail'. C'est le moyen "
            "fiable d'activer des automatisations que l'utilisateur a creees "
            "(Focus/DND, luminosite, etc.). name : le nom exact du raccourci. "
            "Utilise list_shortcuts si tu n'es pas sur du nom."
        ),
    )
    @self._journaled("run_shortcut", "name")
    @self._desktop_access
    async def run_shortcut(name: str) -> dict:
        """Run a macOS Shortcut by name."""
        debug_live("tool_call", tool="run_shortcut")
        result = await asyncio.to_thread(self.shortcuts.run_shortcut, name)
        self._debug_tool_result("run_shortcut", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_shortcuts",
        description=(
            "Liste les Raccourcis (Shortcuts) macOS disponibles, par leur nom. "
            "Pour 'quels raccourcis j'ai', ou pour trouver le bon nom avant "
            "run_shortcut."
        ),
    )
    async def list_shortcuts() -> dict:
        """List available macOS Shortcuts."""
        debug_live("tool_call", tool="list_shortcuts")
        result = await asyncio.to_thread(self.shortcuts.list_shortcuts)
        self._debug_tool_result("list_shortcuts", result)
        return result.to_livekit_dict()

    return {
        "dance_avatar": dance_avatar,
        "set_volume": set_volume,
        "get_volume": get_volume,
        "open_app": open_app,
        "close_app": close_app,
        "is_app_running": is_app_running,
        "play_pause": play_pause,
        "next_track": next_track,
        "previous_track": previous_track,
        "get_media_state": get_media_state,
        "get_battery_status": get_battery_status,
        "get_system_info": get_system_info,
        "get_storage_status": get_storage_status,
        "self_check": self_check,
        "run_shortcut": run_shortcut,
        "list_shortcuts": list_shortcuts,
    }
